"""
Screening-question answerer for LinkedIn Easy Apply.

Answers ONLY questions it recognises AND has an answer for in the user's
settings. Anything else is left alone, and the executor then skips the job
exactly as before. It never invents an answer.

Where answers come from (first one found wins):
    config["screening_answers"]            (dashboard settings)
    config["guards"]["screening_answers"]  (config.local.yaml)

Supported keys (all optional - a missing / blank / "CHANGE_ME" key means
"don't answer, skip the job"):
    work_authorization     Yes/No   "Are you legally authorized to work in the US?"
    require_sponsorship    Yes/No   "Will you now or in the future require sponsorship?"
    willing_to_relocate    Yes/No
    commute_ok             Yes/No   "Are you comfortable commuting to this job's location?"
    onsite_ok              Yes/No   "...work onsite / in office / hybrid...?"
    remote_preference      Yes/No   "Are you comfortable working remotely?"
    background_check_ok    Yes/No
    drug_test_ok           Yes/No
    drivers_license        Yes/No
    bachelors_degree       Yes/No   "Have you completed a Bachelor's degree?"
    high_school            Yes/No
    english_proficiency    e.g. "Native or bilingual"
    start_date             text, e.g. "Immediately" / "2 weeks"
    expected_salary        number (legacy) - prefer config["salary"] range, see src/salary.py
    located_in_us          Yes/No   "Are you currently located in the United States?"
    city / zip_code / phone / linkedin_url / portfolio_url  - taken from personal_info
    years_experience       number - generic "How many years of work experience"
    sales_experience       number - years of sales / account management / customer success
    skill_years            mapping, e.g. {"salesforce": 3, "hubspot": 2, "crm": 5}
    gender / race / veteran / disability  - EEO; "Decline" picks the decline option
"""
import logging
import re
from typing import Dict, List, Optional, Tuple

from playwright.async_api import Locator

from src import salary as salary_mod

logger = logging.getLogger(__name__)

PLACEHOLDERS = {"", "change_me", "changeme", "todo", "none", "null"}
DECLINE_WORDS = ["decline", "prefer not", "don't wish", "do not wish", "not to answer", "choose not", "i don't want"]

# (key, regex on the lower-cased question label) - order matters, first match wins
RULES: List[Tuple[str, str]] = [
    # "authorized to work ... WITHOUT sponsorship" is an authorization question (answer Yes),
    # it must be checked before the plain sponsorship rule (answer No).
    ("work_authorization", r"(authori[sz]ed|eligible|permitted|right) to work.*without.*sponsor|without.*sponsor.*(authori[sz]ed|eligible)"),
    ("require_sponsorship", r"sponsor|visa status|h-?1b"),
    ("work_authorization", r"(legally )?(authori[sz]ed|eligible|permitted|right) to work|work authori[sz]ation"),
    ("willing_to_relocate", r"relocat"),
    ("commute_ok", r"commut"),
    ("onsite_ok", r"(comfortable|willing|able|open)\b.{0,40}(on-?site|in[- ]office|in person|hybrid)"),
    ("remote_preference", r"(comfortable|willing|able|open|prefer)\b.{0,30}remote|work(ing)? remotely"),
    ("background_check_ok", r"background check"),
    ("drug_test_ok", r"drug (test|screen)"),
    ("drivers_license", r"driver'?s? licen[cs]e"),
    ("bachelors_degree", r"bachelor"),
    ("high_school", r"high school|ged"),
    ("english_proficiency", r"english"),
    ("start_date", r"start date|when can you start|available to start|notice period|how soon"),
    ("expected_salary", r"salary|compensation|pay (rate|expectation)|desired pay|expected pay|hourly rate|desired rate"),
    ("located_in_us", r"(currently )?(located|based|reside|residing|live|living) in (the )?(united states|u\.?s\.?a?\b)"),
    ("linkedin_url", r"linkedin (profile|url)|linkedin\.com"),
    ("portfolio_url", r"portfolio|personal website|website url"),
    ("city", r"^(current )?city\b|location \(city\)|city you live in|what city"),
    ("zip_code", r"zip|postal code"),
    ("phone", r"phone"),
    ("gender", r"\bgender\b|\bsex\b"),
    ("race", r"race|ethnicity|hispanic"),
    ("veteran", r"veteran|military"),
    ("disability", r"disabilit"),
    # years questions are resolved separately (see _years_answer)
]

SALES_WORDS = ["sales", "account management", "account manager", "business development", "customer success",
               "selling", "quota", "b2b", "inside sales", "outside sales", "client"]


def _clean(v) -> Optional[str]:
    if v is None:
        return None
    s = str(v).strip()
    return None if s.lower() in PLACEHOLDERS else s


class ScreeningAnswerer:
    def __init__(self, config: dict):
        cfg = config or {}
        answers = {}
        answers.update((cfg.get("guards") or {}).get("screening_answers") or {})
        answers.update(cfg.get("screening_answers") or {})
        self.answers: Dict = answers
        self.enabled = bool(
            (cfg.get("guards") or {}).get("auto_answer_screening",
                                           (cfg.get("application") or {}).get("auto_answer_screening", True))
        )
        self.skill_years = {str(k).lower(): v for k, v in (answers.get("skill_years") or {}).items()}
        self.config = cfg
        personal = cfg.get("personal_info") or {}
        # contact fields come from the profile, not the screening section
        for key in ("city", "zip_code", "phone", "linkedin_url", "portfolio_url"):
            if key not in self.answers and personal.get(key):
                self.answers[key] = personal.get(key)
        self.given: List[Dict[str, str]] = []   # audit log for the current application

    def reset(self):
        self.given = []

    # ------------------------------------------------------------ decision

    def answer_for(self, label: str) -> Optional[str]:
        """The configured answer for a question label, or None if we must not answer."""
        if not self.enabled or not label:
            return None
        q = label.lower()

        if "years" in q and ("experience" in q or "years of" in q):
            return self._years_answer(q)

        # "Do you have experience with Salesforce?" -> Yes only if listed in skill_years
        m = re.search(r"(do you have|have you (had|got)?|any)\s.{0,25}experience (with|in|using|working with) (.+?)\??$", q)
        if m:
            subject = m.group(4)
            for skill, yrs in self.skill_years.items():
                if re.search(r"(?<![a-z0-9])" + re.escape(skill) + r"(?![a-z0-9])", subject):
                    n = _clean(yrs)
                    return "Yes" if n and re.sub(r"[^\d.]", "", n) and float(re.sub(r"[^\d.]", "", n)) > 0 else None
            if any(w in subject for w in SALES_WORDS) and _clean(self.answers.get("sales_experience")):
                return "Yes"
            return None

        for key, rx in RULES:
            if re.search(rx, q):
                if key == "expected_salary":
                    return salary_mod.answer_for_question(q, self.config) or _clean(self.answers.get(key))
                return _clean(self.answers.get(key))
        return None

    def _years_answer(self, q: str) -> Optional[str]:
        # specific tool / skill first ("years of experience with Salesforce")
        for skill, yrs in self.skill_years.items():
            if re.search(r"(?<![a-z0-9])" + re.escape(skill) + r"(?![a-z0-9])", q):
                return _clean(yrs)
        if any(w in q for w in SALES_WORDS):
            return _clean(self.answers.get("sales_experience"))
        # generic "years of (work / professional) experience" only - not "years of Python"
        if re.search(r"years of (total |overall |professional |relevant |work |full[- ]time )?(work )?experience\??\s*$", q) \
                or re.search(r"how many years of (total |overall |professional |work )?experience do you have\??\s*$", q):
            return _clean(self.answers.get("years_experience"))
        return None

    # ------------------------------------------------------------ filling

    async def fill_step(self, modal: Locator, label_fn) -> List[str]:
        """
        Fill every recognised, still-empty question on the current step.
        `label_fn(modal, field)` is the executor's _field_label.
        Returns the labels it answered.
        """
        answered = []
        if not self.enabled:
            return answered

        # text / number inputs
        for f in await modal.locator('input[type="text"], input[type="number"], input:not([type])').all():
            try:
                if not await f.is_visible() or (await f.input_value()).strip():
                    continue
                label = await label_fn(modal, f)
                ans = self.answer_for(label)
                if ans is None:
                    continue
                if (await f.get_attribute("type")) == "number" or "years" in label or re.search(r"salary|compensation|pay|rate", label):
                    digits = re.sub(r"[^\d.]", "", ans)
                    if not digits:
                        continue
                    ans = digits
                await f.fill(ans)
                answered.append(self._log(label, ans))
            except Exception as e:
                logger.debug(f"text answer failed: {e}")

        # dropdowns
        for sel in await modal.locator("select").all():
            try:
                if not await sel.is_visible():
                    continue
                label = await label_fn(modal, sel)
                current = (await sel.evaluate("el => el.options[el.selectedIndex] ? el.options[el.selectedIndex].text : ''")).strip().lower()
                if current and "select" not in current:
                    continue  # already chosen (e.g. pre-filled contact info)
                ans = self.answer_for(label)
                if ans is None:
                    continue
                options = await sel.evaluate("el => Array.from(el.options).map(o => o.text.trim())")
                choice = self._pick_option(options, ans)
                if choice is None:
                    continue
                await sel.select_option(label=choice)
                answered.append(self._log(label, choice))
            except Exception as e:
                logger.debug(f"select answer failed: {e}")

        # radio groups (one decision per fieldset)
        for fs in await modal.locator("fieldset").all():
            try:
                radios = fs.locator('input[type="radio"]')
                if not await radios.count() or await fs.locator('input[type="radio"]:checked').count():
                    continue
                legend = fs.locator("legend, span[data-test-form-builder-radio-button-form-component__title]").first
                label = ((await legend.inner_text()) if await legend.count() else "").strip().lower()
                ans = self.answer_for(label)
                if ans is None:
                    continue
                texts = []
                for i in range(await radios.count()):
                    r = radios.nth(i)
                    rid = await r.get_attribute("id")
                    lab = fs.locator(f'label[for="{rid}"]').first if rid else None
                    texts.append(((await lab.inner_text()) if lab is not None and await lab.count() else (await r.get_attribute("value") or "")).strip())
                choice = self._pick_option(texts, ans)
                if choice is None:
                    continue
                idx = texts.index(choice)
                r = radios.nth(idx)
                rid = await r.get_attribute("id")
                if rid and await fs.locator(f'label[for="{rid}"]').count():
                    await fs.locator(f'label[for="{rid}"]').first.click()
                else:
                    await r.check(force=True)
                answered.append(self._log(label, choice))
            except Exception as e:
                logger.debug(f"radio answer failed: {e}")

        return answered

    async def is_answered(self, modal: Locator, field: Locator, label: str) -> bool:
        """True if this field is a recognised question that now has a value."""
        if self.answer_for(label) is None:
            return False
        try:
            tag = await field.evaluate("el => el.tagName.toLowerCase()")
            if tag == "select":
                cur = (await field.evaluate("el => el.options[el.selectedIndex] ? el.options[el.selectedIndex].text : ''")).strip().lower()
                return bool(cur) and "select" not in cur
            if (await field.get_attribute("type")) == "radio":
                return await field.evaluate(
                    "el => { const fs = el.closest('fieldset'); return !!(fs && fs.querySelector('input[type=radio]:checked')); }")
            return bool((await field.input_value()).strip())
        except Exception:
            return False

    # ------------------------------------------------------------ helpers

    @staticmethod
    def _pick_option(options: List[str], answer: str) -> Optional[str]:
        a = answer.strip().lower()
        if re.fullmatch(r"\d+(\.\d+)?", a):          # number vs. options like "3-5 years" / "$60k-$80k"
            exact = [o for o in options if o.strip().lower() == a]
            return exact[0] if exact else salary_mod.pick_numeric_option(options, float(a))
        opts = [(o, o.strip().lower()) for o in options if o and "select an option" not in o.lower()]
        if a in ("decline", "prefer not to say", "decline to self identify", "decline to self-identify"):
            for o, ol in opts:
                if any(w in ol for w in DECLINE_WORDS):
                    return o
            return None
        for o, ol in opts:                      # exact
            if ol == a:
                return o
        if a in ("yes", "no"):                  # "Yes, I am authorized" style
            for o, ol in opts:
                if re.match(rf"^{a}\b", ol):
                    return o
            # EEO wording: "I am not a protected veteran", "No, I do not have a disability"
            real = [(o, ol) for o, ol in opts if not any(w in ol for w in DECLINE_WORDS)]
            neg = [o for o, ol in real if re.match(r"^(i am not|i'm not|i do not|i don't|not a )", ol)]
            pos = [o for o, ol in real if re.match(r"^(i am a|i identify as|i have a|i have had)", ol)]
            pick = neg if a == "no" else pos
            return pick[0] if len(pick) == 1 else None
        for o, ol in opts:                      # contains
            if a in ol or ol in a:
                return o
        return None

    def _log(self, label: str, answer: str) -> str:
        self.given.append({"question": label[:200], "answer": answer})
        logger.info(f"  Auto-answered: '{label[:70]}' -> '{answer}'")
        return label
