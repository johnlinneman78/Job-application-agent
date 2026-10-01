"""
Application Executor - Submit LinkedIn Easy Apply applications with a strict FSM.

Rules this file enforces:
- Only click Next / Review / Submit inside the Easy Apply dialog.
- Skip the job the moment a real screening question appears.
- A job counts as SUBMITTED only after we clicked Submit AND LinkedIn shows
  a visible confirmation. Page source text is never used as proof.
"""
import asyncio
import hashlib
import logging
import random
import re
import time
from datetime import datetime
from enum import Enum, auto
from pathlib import Path
from typing import List, Optional, Tuple

from playwright.async_api import Page, BrowserContext, Locator
from src.models import Job, Application, ApplicationStatus, Platform
from src.application_guard import ApplicationGuard, EASY_APPLY_SELECTORS, DENIED_BUTTON_WORDS

logger = logging.getLogger(__name__)

MODAL_SELECTOR = 'dialog, [role="dialog"], .jobs-easy-apply-modal, .artdeco-modal'
MODAL_PARTS = [s.strip() for s in MODAL_SELECTOR.split(",")]
def in_modal(sel): return ", ".join(f"{m} {sel}" for m in MODAL_PARTS)

# Fields LinkedIn pre-fills from the profile on the "Contact info" step.
# These are NOT screening questions.
CONTACT_FIELD_WORDS = [
    "email", "phone", "country code", "mobile", "first name", "last name",
    "city", "location", "address", "zip", "postal",
]

# Checkbox labels that are safe to leave alone / accept.
SAFE_CHECKBOX_WORDS = [
    "terms", "privacy", "policy", "acknowledge", "agree", "confirm",
    "follow", "top choice", "save this",
]

# Visible confirmation text LinkedIn shows after a successful submit.
SUCCESS_PATTERNS = re.compile(
    r"(application (was )?sent|your application was submitted|application submitted)",
    re.IGNORECASE,
)


class FSMState(Enum):
    JOB_PAGE = auto()
    EASY_APPLY_MODAL_OPEN = auto()
    STEP_IN_PROGRESS = auto()
    REVIEW = auto()
    SUBMIT_CLICKED = auto()
    SUBMITTED = auto()
    SKIPPED = auto()


class TerminalReason(Enum):
    SUBMITTED = "SUBMITTED"
    COVER_LETTER_REQUIRED = "Cover letter required"
    SCREENING_QUESTIONS = "Screening questions present"
    EXTERNAL_REDIRECT = "External redirect"
    SECURITY_CHECKPOINT = "CAPTCHA / security checkpoint"
    UPLOAD_FAILED = "Upload failed / file picker blocked"
    NEXT_DISABLED = "Next button disabled"
    STUCK = "Unknown UI state after recovery attempts"
    NO_EASY_APPLY = "No Easy Apply button found"
    NO_CONFIRMATION = "Clicked Submit but no confirmation was shown"


class ApplicationExecutor:
    """Execute job applications with strict FSM logic and resume-only policy."""

    def __init__(self, config: dict, guard: ApplicationGuard):
        self.config = config
        self.guard = guard
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.resume = None
        self.resume_path: Optional[str] = None
        self.applications: List[Application] = []
        self._recovery_attempts = 0

    # ------------------------------------------------------------------ login

    async def is_logged_in(self, page: Page) -> bool:
        """
        Logged in = (#global-nav OR .global-nav__me OR img.global-nav__me-photo is visible)
        AND no visible 'a[href*="/login"]' or "Sign in" button AND url has no login/checkpoint/authwall.
        """
        try:
            url = page.url.lower()
            if any(k in url for k in ["login", "checkpoint", "authwall"]):
                return False

            sign_in = page.locator('a[href*="/login"], button:has-text("Sign in"), a:has-text("Sign in")')
            for i in range(await sign_in.count()):
                if await sign_in.nth(i).is_visible():
                    return False

            nav = page.locator('#global-nav, .global-nav__me, img.global-nav__me-photo, [data-testid="primary-nav"]')
            for i in range(await nav.count()):
                if await nav.nth(i).is_visible():
                    return True

            return False
        except Exception:
            return False

    async def login_to_linkedin(self, page: Page, timeout_ms: int = 300000) -> bool:
        """
        Open LinkedIn. If already signed in (saved browser profile), return at once.
        Otherwise wait up to `timeout_ms` for the user to sign in by hand.
        """
        logger.info("Checking LinkedIn login...")
        await page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(3000)
        if await self.is_logged_in(page):
            logger.info("Already logged in to LinkedIn.")
            return True

        logger.info("[PAUSE] Please log in to LinkedIn in the browser window (5 minute limit)...")
        deadline = time.time() + timeout_ms / 1000
        while time.time() < deadline:
            await page.wait_for_timeout(2000)
            if await self.is_logged_in(page):
                logger.info("LinkedIn login successful!")
                return True
        logger.error("LinkedIn login not detected within the time limit.")
        return False

    # ------------------------------------------------------------ main flow

    async def apply_to_linkedin_job(self, job: Job, resume_path: str) -> Application:
        """Apply to a single LinkedIn job using the strict FSM."""
        self.resume_path = resume_path
        app = Application(job=job, resume_path=resume_path, status=ApplicationStatus.PREPARED)
        state = FSMState.JOB_PAGE
        terminal_reason: Optional[TerminalReason] = None
        transitions: List[str] = []
        buttons_clicked: List[str] = []
        self._recovery_attempts = 0

        logger.info(f"--- Starting Application: {job.company} - {job.title} ---")

        try:
            await self.page.goto(job.url, wait_until="domcontentloaded", timeout=45000)
            await self.page.wait_for_timeout(2000)

            if "checkpoint" in self.page.url or "login" in self.page.url:
                state = FSMState.SKIPPED
                terminal_reason = TerminalReason.SECURITY_CHECKPOINT

            for _ in range(25):  # hard cap on steps per job
                transitions.append(state.name)

                if state == FSMState.JOB_PAGE:
                    ea_btn = await self._find_ea_button_robust()
                    if not ea_btn:
                        state, terminal_reason = FSMState.SKIPPED, TerminalReason.NO_EASY_APPLY
                        continue
                    await self._click_robustly(ea_btn)
                    buttons_clicked.append("EASY_APPLY")
                    try:
                        await self.page.locator(MODAL_SELECTOR).first.wait_for(state="visible", timeout=10000)
                    except Exception:
                        # Easy Apply sometimes opens an external site in a new tab
                        state, terminal_reason = FSMState.SKIPPED, TerminalReason.EXTERNAL_REDIRECT
                        continue
                    state = FSMState.EASY_APPLY_MODAL_OPEN

                elif state in (FSMState.EASY_APPLY_MODAL_OPEN, FSMState.STEP_IN_PROGRESS, FSMState.REVIEW):
                    modal = self.page.locator(MODAL_SELECTOR).first
                    if not await modal.count() or not await modal.is_visible():
                        state, terminal_reason = FSMState.SKIPPED, TerminalReason.STUCK
                        continue

                    # Resume step: attach resume if LinkedIn asks for it
                    if not await self._ensure_resume_selected(modal):
                        state, terminal_reason = FSMState.SKIPPED, TerminalReason.UPLOAD_FAILED
                        continue

                    reason = await self._screening_reason(modal)
                    if reason:
                        auto_answer = self.config.get("application", {}).get("auto_answer_screening", True)
                        if auto_answer:
                            answered_ok, fail_reason = await self._auto_answer_step_questions(modal)
                            if not answered_ok:
                                logger.info(f"  Skip: {fail_reason or reason}")
                                state = FSMState.SKIPPED
                                terminal_reason = (TerminalReason.COVER_LETTER_REQUIRED
                                                   if "cover letter" in (fail_reason or reason).lower()
                                                   else TerminalReason.SCREENING_QUESTIONS)
                                continue
                            else:
                                logger.info("  Screening questions successfully answered on this step.")
                        else:
                            logger.info(f"  Skip: {reason}")
                            state = FSMState.SKIPPED
                            terminal_reason = (TerminalReason.COVER_LETTER_REQUIRED
                                               if "cover letter" in reason.lower()
                                               else TerminalReason.SCREENING_QUESTIONS)
                            continue

                    btn, btn_type = await self._find_priority_button(modal)
                    if not btn:
                        if await self._attempt_recovery(modal, job):
                            continue
                        state, terminal_reason = FSMState.SKIPPED, TerminalReason.STUCK
                        continue

                    if await btn.is_disabled():
                        state, terminal_reason = FSMState.SKIPPED, TerminalReason.NEXT_DISABLED
                        continue

                    old_fp = await self._get_modal_fingerprint(modal)
                    if btn_type == "SUBMIT":
                        await self._uncheck_follow_company_if_present(modal)
                    await self._click_robustly(btn)
                    buttons_clicked.append(btn_type)
                    await self.page.wait_for_timeout(2000)

                    if btn_type == "SUBMIT":
                        state = FSMState.SUBMIT_CLICKED
                        continue

                    # LinkedIn shows inline errors when a required field is empty
                    if await self._has_inline_errors(modal):
                        state, terminal_reason = FSMState.SKIPPED, TerminalReason.SCREENING_QUESTIONS
                        continue

                    new_fp = await self._get_modal_fingerprint(modal)
                    if new_fp == old_fp:
                        logger.warning(f"  No progress detected after clicking {btn_type}")
                        if await self._attempt_recovery(modal, job):
                            continue
                        state, terminal_reason = FSMState.SKIPPED, TerminalReason.STUCK
                        continue

                    self._recovery_attempts = 0
                    state = FSMState.REVIEW if btn_type == "REVIEW" else FSMState.STEP_IN_PROGRESS

                elif state == FSMState.SUBMIT_CLICKED:
                    if await self._wait_for_success_proof(timeout_ms=10000):
                        state, terminal_reason = FSMState.SUBMITTED, TerminalReason.SUBMITTED
                    else:
                        state, terminal_reason = FSMState.SKIPPED, TerminalReason.NO_CONFIRMATION
                        await self._capture_failure_artifacts("no_confirmation")

                elif state == FSMState.SUBMITTED:
                    app.status = ApplicationStatus.SUBMITTED
                    app.submission_timestamp = datetime.now()
                    await self._close_modal_if_open(discard=False)
                    break

                elif state == FSMState.SKIPPED:
                    app.status = ApplicationStatus.SKIPPED
                    app.error_message = terminal_reason.value if terminal_reason else "Unknown"
                    await self._close_modal_if_open(discard=True)
                    break
            else:
                app.status = ApplicationStatus.SKIPPED
                app.error_message = TerminalReason.STUCK.value
                await self._close_modal_if_open(discard=True)

            self._log_terminal_state(job, transitions, terminal_reason, buttons_clicked)
            return app

        except Exception as e:
            logger.exception(f"Unexpected error on {job.url}: {e}")
            app.status = ApplicationStatus.FAILED
            app.error_message = f"{type(e).__name__}: {e}"
            try:
                await self._capture_failure_artifacts("exception")
                await self._close_modal_if_open(discard=True)
            except Exception:
                pass
            return app

    # Kept for the web backend, which calls this name.
    async def submit_application(self, job: Job, resume_path: str) -> Application:
        return await self.apply_to_linkedin_job(job, resume_path)

    # -------------------------------------------------------- button finding

    async def _find_ea_button_robust(self) -> Optional[Locator]:
        """Find the Easy Apply button (two passes, same selectors as the guard)."""
        logger.info("Starting Easy Apply detection...")
        for attempt in range(2):
            await self._wait_for_content_settle()
            for selector in EASY_APPLY_SELECTORS:
                try:
                    btn = self.page.locator(selector).first
                    if not await btn.count() or not await btn.is_visible():
                        continue
                    label = ((await btn.inner_text()) + " " + (await btn.get_attribute("aria-label") or "")).lower()
                    if any(w in label for w in DENIED_BUTTON_WORDS):
                        continue
                    # Same element id is used for the external "Apply" button;
                    # only "Easy Apply" stays inside LinkedIn.
                    if "easy apply" not in label:
                        continue
                    logger.info(f"Found Easy Apply button via: {selector}")
                    return btn
                except Exception as e:
                    logger.debug(f"Selector {selector} failed: {e}")
            if attempt == 0:
                await self.page.wait_for_timeout(1500)

        logger.error("Easy Apply button NOT FOUND after 2 attempts")
        await self._capture_failure_artifacts("no_easy_apply_button")
        return None

    async def _find_priority_button(self, modal: Locator) -> Tuple[Optional[Locator], Optional[str]]:
        """Priority: Submit application > Review > Next/Continue. Only inside the dialog."""
        checks = [
            ('button[aria-label*="Submit application" i]', "SUBMIT"),
            ('button:has-text("Submit application")', "SUBMIT"),
            ('button[aria-label*="Review your application" i]', "REVIEW"),
            ('button:has-text("Review")', "REVIEW"),
            ('button[aria-label*="Continue to next step" i]', "NEXT"),
            ('button:has-text("Next")', "NEXT"),
            ('button:has-text("Continue")', "NEXT"),
        ]
        for selector, kind in checks:
            loc = modal.locator(selector).first
            try:
                if await loc.count() and await loc.is_visible():
                    return loc, kind
            except Exception:
                continue
        return None, None

    # ------------------------------------------------------ step inspection

    async def _uncheck_follow_company_if_present(self, modal: Locator):
        """Uncheck 'Follow company' on the final review step to prevent feed clutter (LinkedHelper tip)."""
        try:
            follow_cb = modal.locator('input#follow-company-checkbox, input[id*="follow-company"], input[name*="followCompany"]')
            for i in range(await follow_cb.count()):
                cb = follow_cb.nth(i)
                if await cb.is_visible() and await cb.is_checked():
                    await cb.uncheck(force=True)
                    logger.info("  Unchecked 'Follow company' to keep your feed clean.")
        except Exception as e:
            logger.debug(f"Could not uncheck follow company: {e}")

    async def _field_label(self, modal: Locator, field: Locator) -> str:
        """Best-effort human label for an input/select/textarea."""
        parts = []
        try:
            parts.append(await field.get_attribute("aria-label") or "")
            fid = await field.get_attribute("id")
            if fid:
                lab = modal.locator(f'label[for="{fid}"]').first
                if await lab.count():
                    parts.append(await lab.inner_text())
            # legend of the enclosing fieldset (radio groups)
            parts.append(await field.evaluate(
                "el => { const fs = el.closest('fieldset'); const lg = fs && fs.querySelector('legend'); return lg ? lg.innerText : ''; }"
            ))
        except Exception:
            pass
        return " ".join(p for p in parts if p).strip().lower()

    async def _auto_answer_step_questions(self, modal: Locator) -> Tuple[bool, Optional[str]]:
        """
        Attempts to automatically answer standard screening questions on the current modal step:
        - Radio buttons: Work authorization (Yes), sponsorship (No), remote/commute (Yes), experience/skills (Yes).
        - Dropdowns: Work authorization, language/proficiency, education level, yes/no.
        - Text/Number fields: Years of experience, expected salary, availability/start date, location/city.
        - Checkboxes: Terms/authorization/certification agreements.
        - Textarea: Cover letter (if required -> skip; if optional -> leave empty), essay questions (if required -> skip).
        """
        screening = self.config.get("screening_answers", {})
        personal = self.config.get("personal_info", {})

        # 1. Textareas (Cover letter & essays)
        for ta in await modal.locator("textarea").all():
            if not await ta.is_visible():
                continue
            label = await self._field_label(modal, ta)
            is_required = (await ta.get_attribute("required") is not None) or ("required" in label)
            if "cover letter" in label:
                if is_required:
                    return False, "Cover letter required"
                continue
            if is_required:
                val = (await ta.input_value()).strip()
                if not val:
                    return False, f"Essay question required: '{label[:60]}'"

        # 2. Radio button groups
        radios = await modal.locator('input[type="radio"]').all()
        handled_radio_names = set()
        for r in radios:
            if not await r.is_visible():
                continue
            label = await self._field_label(modal, r)
            # Check if this is part of resume selection
            in_resume_picker = await r.evaluate("el => !!el.closest('[class*=\"document\"], [class*=\"resume\"], [class*=\"jobs-resume\"]')")
            if in_resume_picker or "resume" in label or ".pdf" in label or ".docx" in label:
                continue

            r_name = await r.get_attribute("name") or label[:30]
            if r_name in handled_radio_names:
                continue

            # Find all radios in this group
            r_attr = await r.get_attribute("name")
            if r_attr:
                group_radios = await modal.locator(f'input[type="radio"][name="{r_attr}"]').all()
            else:
                group_radios = [r]

            # Check if any in group is already checked
            any_checked = False
            for gr in group_radios:
                if await gr.is_checked():
                    any_checked = True
                    break
            if any_checked:
                handled_radio_names.add(r_name)
                continue

            # Determine best answer ("Yes" or "No")
            target_answer = "Yes"
            q_lower = label.lower()
            if any(w in q_lower for w in ["sponsorship", "require visa", "visa sponsorship", "need sponsorship"]):
                target_answer = screening.get("require_sponsorship", "No")
            elif any(w in q_lower for w in ["authorized", "authorization", "legally authorized", "eligible to work", "right to work"]):
                target_answer = screening.get("work_authorization", "Yes")
            elif any(w in q_lower for w in ["relocate", "relocation"]):
                target_answer = screening.get("willing_to_relocate", "No")
            elif any(w in q_lower for w in ["remote", "work from home", "commute", "travel"]):
                target_answer = screening.get("remote_preference", "Yes")
            elif any(w in q_lower for w in ["previously employed", "worked for us", "former employee", "relatives"]):
                target_answer = "No"
            else:
                target_answer = "Yes"

            chosen = None
            for gr in group_radios:
                r_id = await gr.get_attribute("id")
                btn_label = ""
                if r_id:
                    lab_el = modal.locator(f'label[for="{r_id}"]').first
                    if await lab_el.count():
                        btn_label = (await lab_el.inner_text()).strip()
                if not btn_label:
                    try:
                        btn_label = (await gr.evaluate("el => (el.closest('label') || el.parentElement).innerText") or "").strip()
                    except Exception:
                        btn_label = ""
                if not btn_label:
                    btn_label = (await gr.get_attribute("value") or "").strip()

                if target_answer.lower() in btn_label.lower():
                    chosen = gr
                    break

            if chosen:
                await chosen.check(force=True)
                logger.info(f"  Auto-selected radio '{label[:50]}': {target_answer}")
                handled_radio_names.add(r_name)
            else:
                is_req = await r.get_attribute("required") is not None
                if is_req:
                    return False, f"Could not match radio option for '{label[:50]}'"

        # 3. Dropdown selects
        selects = await modal.locator("select").all()
        for sel in selects:
            if not await sel.is_visible():
                continue
            label = await self._field_label(modal, sel)
            current_val = (await sel.input_value() or "").strip()

            opts = await sel.locator("option").all()
            opt_data = []
            for opt in opts:
                val = await opt.get_attribute("value") or ""
                txt = (await opt.inner_text()).strip()
                if txt and not any(p in txt.lower() for p in ["select an option", "choose", "select...", "--"]):
                    opt_data.append((val, txt))

            if not opt_data:
                continue

            if current_val and any(val == current_val for val, _ in opt_data):
                continue

            q_lower = label.lower()
            selected_val = None
            selected_text = None

            if any(w in q_lower for w in ["sponsorship", "visa"]):
                target = screening.get("require_sponsorship", "No").lower()
                for val, txt in opt_data:
                    if target in txt.lower():
                        selected_val, selected_text = val, txt
                        break
            elif any(w in q_lower for w in ["authorized", "authorization", "legally", "citizen"]):
                target = screening.get("work_authorization", "Yes").lower()
                for val, txt in opt_data:
                    if target in txt.lower() or "citizen" in txt.lower() or "authorized" in txt.lower():
                        selected_val, selected_text = val, txt
                        break
            elif any(w in q_lower for w in ["proficiency", "language", "english", "level"]):
                for pref in ["native", "fluent", "professional", "advanced", "conversational"]:
                    for val, txt in opt_data:
                        if pref in txt.lower():
                            selected_val, selected_text = val, txt
                            break
                    if selected_val:
                        break
            elif any(w in q_lower for w in ["education", "degree"]):
                for pref in ["bachelor", "master", "associate", "degree", "high school"]:
                    for val, txt in opt_data:
                        if pref in txt.lower():
                            selected_val, selected_text = val, txt
                            break
                    if selected_val:
                        break
            elif any(w in q_lower for w in ["years", "experience"]):
                exp_yrs = str(screening.get("default_experience_years", 4))
                for val, txt in opt_data:
                    if exp_yrs in txt or "3" in txt or "4" in txt or "5" in txt:
                        selected_val, selected_text = val, txt
                        break
            else:
                for val, txt in opt_data:
                    if "yes" in txt.lower():
                        selected_val, selected_text = val, txt
                        break

            if selected_val is not None:
                await sel.select_option(value=selected_val)
                logger.info(f"  Auto-selected dropdown for '{label[:50]}': {selected_text}")
            else:
                is_req = await sel.get_attribute("required") is not None
                if is_req:
                    return False, f"Could not determine dropdown answer for '{label[:50]}'"

        # 4. Text and Number inputs
        inputs = await modal.locator(
            'input[type="text"], input[type="number"], input:not([type])'
        ).all()
        for inp in inputs:
            if not await inp.is_visible():
                continue
            label = await self._field_label(modal, inp)
            val = (await inp.input_value() or "").strip()
            if val:
                continue

            itype = (await inp.get_attribute("type") or "").lower()
            if itype in ["file", "radio", "checkbox", "hidden", "submit", "button"]:
                continue

            q_lower = label.lower()
            fill_val = None

            if any(w in q_lower for w in ["years", "how many years", "experience"]):
                fill_val = str(screening.get("default_experience_years", 4))
            elif any(w in q_lower for w in ["salary", "compensation", "expected", "desired", "pay", "rate"]):
                fill_val = str(screening.get("expected_salary", "120000"))
            elif any(w in q_lower for w in ["notice", "start date", "availability", "how soon", "when can you start"]):
                fill_val = str(screening.get("start_date", "Immediately"))
            elif any(w in q_lower for w in ["city", "location", "address"]):
                fill_val = personal.get("city") or "Remote"
            elif any(w in q_lower for w in ["phone", "mobile", "telephone"]):
                fill_val = personal.get("phone", "")
            elif any(w in q_lower for w in ["zip", "postal"]):
                fill_val = personal.get("zip_code", "")
            elif any(w in q_lower for w in ["linkedin", "website", "portfolio", "url"]):
                fill_val = personal.get("linkedin_url") or personal.get("portfolio_url") or ""

            if fill_val:
                await inp.fill(fill_val)
                try:
                    await inp.dispatch_event("change")
                    await inp.dispatch_event("input")
                except Exception:
                    pass
                logger.info(f"  Auto-filled input for '{label[:50]}': {fill_val}")
            else:
                is_req = await inp.get_attribute("required") is not None
                if is_req:
                    return False, f"Unrecognized required field: '{label[:50]}'"

        # 5. Checkboxes
        checkboxes = await modal.locator('input[type="checkbox"]').all()
        for cb in checkboxes:
            if not await cb.is_visible():
                continue
            label = await self._field_label(modal, cb)
            if "follow" in label.lower():
                continue
            is_req = await cb.get_attribute("required") is not None or any(
                w in label.lower() for w in ["certify", "agree", "terms", "acknowledge", "consent", "confirm", "authorized"]
            )
            if is_req and not await cb.is_checked():
                await cb.check(force=True)
                logger.info(f"  Auto-checked consent checkbox: '{label[:50]}'")

        return True, None

    async def _screening_reason(self, modal: Locator) -> Optional[str]:
        """
        Return a reason string if this step contains a real screening question,
        or None if the step only has contact info / resume / consent items.
        """
        # Free-text answers (cover letter, "why do you want...") -> always skip
        for ta in await modal.locator("textarea").all():
            if await ta.is_visible():
                label = await self._field_label(modal, ta)
                if "cover letter" in label:
                    return "Cover letter required"
                return f"Free-text question: '{label[:60]}'"

        # Text inputs and dropdowns: allowed only if they are contact fields
        fields = await modal.locator(
            'input[type="text"], input[type="email"], input[type="tel"], input[type="number"], input:not([type]), select'
        ).all()
        for f in fields:
            if not await f.is_visible():
                continue
            label = await self._field_label(modal, f)
            if any(w in label for w in CONTACT_FIELD_WORDS):
                continue
            return f"Question field: '{label[:60] or 'unlabeled'}'"

        # Radio buttons: allowed only for choosing which resume to send
        for r in await modal.locator('input[type="radio"]').all():
            label = await self._field_label(modal, r)
            in_resume_picker = await r.evaluate("el => !!el.closest('[class*=\"document\"], [class*=\"resume\"], [class*=\"jobs-resume\"]')")
            if in_resume_picker or "resume" in label or ".pdf" in label or ".docx" in label:
                continue
            return f"Multiple-choice question: '{label[:60] or 'unlabeled'}'"

        # Checkboxes: allowed only for consent / follow-company
        for c in await modal.locator('input[type="checkbox"]').all():
            label = await self._field_label(modal, c)
            if not label:
                try:
                    label = (await c.evaluate("el => (el.closest('label') || el.parentElement).innerText") or "").lower()
                except Exception:
                    label = ""
            if any(w in label for w in SAFE_CHECKBOX_WORDS):
                continue
            return f"Checkbox question: '{label[:60] or 'unlabeled'}'"

        return None

    # Backwards-compatible name used by older code/tests
    async def _is_screening_required(self, modal: Locator) -> bool:
        return await self._screening_reason(modal) is not None

    async def _ensure_resume_selected(self, modal: Locator) -> bool:
        """
        If this step asks for a resume, make sure one is attached.
        Returns False only if an upload was required and failed.
        """
        file_inputs = modal.locator('input[type="file"]')
        if not await file_inputs.count():
            return True  # not a resume step

        # Already a resume chosen (LinkedIn remembers your pre-uploaded resume)
        chosen = modal.locator(
            'input[type="radio"]:checked, [aria-checked="true"], '
            '[aria-label*="Selected" i][class*="document"], '
            '[class*="jobs-document-upload-redesign-card__container--selected"], '
            '[class*="jobs-document-upload-redesign-card"][class*="selected"], '
            'div[class*="resume-card--selected"]'
        )
        if await chosen.count():
            logger.info("  Using LinkedIn pre-uploaded/saved resume.")
            return True

        # A previous resume card exists on LinkedIn: select the first one
        first_radio = modal.locator('input[type="radio"], [role="radio"], [class*="jobs-document-upload-redesign-card"]').first
        if await first_radio.count():
            try:
                await first_radio.click(force=True)
                await self.page.wait_for_timeout(1000)
                logger.info("  Selected LinkedIn pre-loaded resume card.")
                return True
            except Exception as e:
                logger.debug(f"  Could not click resume card: {e}")

        # Fallback to local resume path if exists
        fallback_path = self.resume_path
        if not fallback_path or not Path(fallback_path).is_file():
            cand = Path("data/resume.pdf")
            if cand.is_file():
                fallback_path = str(cand.absolute())
            else:
                fallback_path = None

        if not fallback_path or not Path(fallback_path).is_file():
            logger.info("  No local resume file provided; proceeding with LinkedIn profile defaults.")
            return True

        # LinkedHelper best practice: LinkedIn Easy Apply fails for resumes over 2 MB
        try:
            file_size_mb = Path(fallback_path).stat().st_size / (1024 * 1024)
            if file_size_mb > 2.0:
                logger.warning(
                    f"  [WARNING] Resume file size is {file_size_mb:.2f} MB. "
                    "LinkedIn Easy Apply often rejects uploads > 2.0 MB. Please optimize/compress data/resume.pdf."
                )
        except Exception:
            pass
        try:
            await file_inputs.first.set_input_files(str(Path(fallback_path).absolute()))
            await self.page.wait_for_timeout(3000)
            logger.info("  Resume uploaded")
            return True
        except Exception as e:
            logger.error(f"  Resume upload failed: {e}")
            return False

    async def _get_modal_fingerprint(self, modal: Locator) -> str:
        """Hash of the dialog's visible text, used to detect 'nothing happened'."""
        try:
            text = await modal.inner_text()
        except Exception:
            text = ""
        return hashlib.md5(text.encode("utf-8", "ignore")).hexdigest()

    async def _has_inline_errors(self, modal: Locator) -> bool:
        try:
            err = modal.locator('.artdeco-inline-feedback--error, [role="alert"]:visible')
            return await err.count() > 0
        except Exception:
            return False

    async def _click_robustly(self, btn: Locator):
        """Scroll into view, normal click; fall back to force click, then JS click."""
        try:
            await btn.scroll_into_view_if_needed(timeout=3000)
        except Exception:
            pass
        try:
            await btn.click(timeout=5000)
            return
        except Exception:
            pass
        try:
            await btn.click(force=True, timeout=5000)
            return
        except Exception:
            pass
        await btn.evaluate("el => el.click()")

    async def _attempt_recovery(self, modal: Locator, job: Job) -> bool:
        self._recovery_attempts += 1
        if self._recovery_attempts > 2:
            return False
        logger.warning(f"  Recovery attempt {self._recovery_attempts} for {job.company}")
        try:
            await modal.evaluate(
                "el => { const c = el.querySelector('.artdeco-modal__content') || el; c.scrollTop = c.scrollHeight; }"
            )
        except Exception:
            pass
        await self.page.wait_for_timeout(1500)
        return True

    # ----------------------------------------------------------- success

    async def _detect_success_proof(self) -> bool:
        """
        Only VISIBLE confirmation counts:
        - a dialog saying 'Application sent' / 'Your application was submitted'
        - or the top card now showing an 'Applied' status line
        """
        try:
            dialogs = self.page.locator(MODAL_SELECTOR)
            for i in range(await dialogs.count()):
                d = dialogs.nth(i)
                if await d.is_visible() and SUCCESS_PATTERNS.search(await d.inner_text() or ""):
                    return True
            applied = self.page.locator(
                '.artdeco-inline-feedback--success:visible, .jobs-s-apply__application-link:visible'
            )
            if await applied.count():
                txt = (await applied.first.inner_text() or "").lower()
                if "applied" in txt or "submitted" in txt:
                    return True
        except Exception:
            pass
        return False

    async def _wait_for_success_proof(self, timeout_ms: int = 10000) -> bool:
        waited = 0
        while waited < timeout_ms:
            if await self._detect_success_proof():
                return True
            await self.page.wait_for_timeout(1000)
            waited += 1000
        return False

    # ------------------------------------------------------------- cleanup

    async def _close_modal_if_open(self, discard: bool = True):
        """Close the dialog. When skipping, LinkedIn asks 'Save this application?' -> Discard."""
        for _ in range(3):
            modal = self.page.locator(MODAL_SELECTOR).first
            if not await modal.count() or not await modal.is_visible():
                return
            if discard:
                discard_btn = self.page.locator(
                    'button[data-control-name="discard_application_confirm_btn"], '
                    + in_modal('button:has-text("Discard")')
                ).first
                if await discard_btn.count() and await discard_btn.is_visible():
                    await discard_btn.click(force=True)
                    await self.page.wait_for_timeout(1000)
                    continue
            close = self.page.locator(
                in_modal('button:has-text("Done")')
                + ", "
                + in_modal('button[aria-label*="Dismiss" i]')
                + ", .artdeco-modal__dismiss"
            ).first
            if await close.count() and await close.is_visible():
                await close.click(force=True)
                await self.page.wait_for_timeout(1000)
            else:
                return

    async def _wait_for_content_settle(self):
        await self.page.wait_for_load_state("domcontentloaded")
        await self.page.wait_for_timeout(500)
        try:
            await self.page.wait_for_load_state("networkidle", timeout=5000)
        except Exception:
            pass

    async def _capture_failure_artifacts(self, reason: str):
        """Screenshot + list of visible buttons, saved to data/."""
        ts = int(time.time())
        Path("data").mkdir(exist_ok=True)
        try:
            await self.page.screenshot(path=f"data/failure_{reason}_{ts}.png")
        except Exception as e:
            logger.error(f"Failed to capture screenshot: {e}")
        try:
            lines = []
            for i, btn in enumerate((await self.page.get_by_role("button").all())[:40]):
                try:
                    if await btn.is_visible():
                        text = (await btn.inner_text() or "").strip().replace("\n", " ")
                        aria = (await btn.get_attribute("aria-label") or "").strip()
                        bid = await btn.get_attribute("id") or ""
                        lines.append(f"{i+1}. id='{bid}' text='{text}' aria='{aria}'")
                except Exception:
                    continue
            with open(f"data/button_inventory_{ts}.txt", "w", encoding="utf-8") as f:
                f.write(f"Reason: {reason}\nURL: {self.page.url}\n\nVISIBLE BUTTONS:\n")
                f.write("\n".join(lines) or "None")
        except Exception as e:
            logger.warning(f"Failed to capture button inventory: {e}")

    def _log_terminal_state(self, job: Job, transitions: List[str], reason: Optional[TerminalReason], buttons: List[str]):
        logger.info(f"Job: {job.title} @ {job.company}")
        logger.info(f"States traversed: {' -> '.join(transitions)}")
        logger.info(f"Buttons clicked: {buttons}")
        logger.info(f"Final outcome: {reason.value if reason else 'UNKNOWN'}")

    # ------------------------------------------------------------ batch

    def _delay_seconds(self) -> int:
        app_cfg = self.config.get("application", {})
        lo = int(app_cfg.get("min_delay", 30))
        hi = int(app_cfg.get("max_delay", lo))
        return random.randint(min(lo, hi), max(lo, hi))

    async def apply_to_jobs(self, jobs: List[Job], resume_path: str, context: BrowserContext) -> List[Application]:
        logger.info(f"Starting execution for {len(jobs)} jobs...")
        self.context = context
        if not self.page:
            self.page = await self.context.new_page()
        for i, job in enumerate(jobs):
            if job.platform != Platform.LINKEDIN:
                continue
            app = await self.apply_to_linkedin_job(job, resume_path)
            self.applications.append(app)
            if i < len(jobs) - 1:
                delay = self._delay_seconds()
                logger.info(f"Waiting {delay}s before next application...")
                await asyncio.sleep(delay)
        return self.applications
