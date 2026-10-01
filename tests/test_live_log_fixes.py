"""Fixes from the 2026-10-01 live run (3 of 20 submitted).
python -m pytest tests/test_live_log_fixes.py -q"""
import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.experience import area_for_question  # noqa: E402
from src.locations import find_location, outside_area, parse_card_text  # noqa: E402
from src.screening_answers import ScreeningAnswerer  # noqa: E402

RESUME = (Path(__file__).parent / "fixtures" / "sample_resume.txt").read_text(encoding="utf-8")


def answerer(extra=None):
    a = ScreeningAnswerer({"screening_answers": dict(extra or {})})
    a.load_resume(resume_text=RESUME)
    return a


# ------------------------------------------------------------------ 1. "currently" questions

def test_currently_phrasing_is_recognised():
    assert area_for_question("how many years of sales experience do you currently have?") == "sales"
    assert area_for_question("how many years of customer service experience do you currently have?") == "customer service"
    assert area_for_question("how many years of bd experience do you currently have?") == "sales"
    # still strict: an extra qualifier still blocks the match
    assert area_for_question("how many years of medical sales experience do you currently have?") is None


def test_currently_questions_get_resume_years():
    a = answerer()
    assert a.answer_for("how many years of sales experience do you currently have?") == "4"
    assert a.answer_for("how many years of customer service experience do you currently have?") == "3"
    assert a.answer_for("how many years of work experience do you currently have?") == "6"


def test_construction_is_still_skipped():
    a = answerer()
    assert a.answer_for("how many years of construction experience do you currently have?") is None
    assert "not an experience area" in a.explain("how many years of construction experience do you currently have?")


# ------------------------------------------------------------------ 2. yes/no questions from the log

LOG_QUESTIONS = {
    "have you completed the following level of education: bachelor's degree?": ("bachelors_degree", "No"),
    "have you completed the following level of education: high school diploma?": ("high_school", "Yes"),
    "do you have a valid driver's license?": ("drivers_license", "Yes"),
    "are you willing to undergo a background check, in accordance with local law/regulations?": ("background_check_ok", "Yes"),
    "will you now, or in the future, require sponsorship for employment visa status (e.g. h-1b visa status)?": ("require_sponsorship", "No"),
    "are you comfortable sitting fully onsite in portland near the airport?": ("onsite_ok", "Yes"),
}


def test_log_questions_map_to_settings():
    filled = answerer({k: v for k, v in LOG_QUESTIONS.values()})
    blank = answerer()
    for q, (key, ans) in LOG_QUESTIONS.items():
        assert filled.answer_for(q) == ans, q
        assert blank.answer_for(q) is None, q
        assert blank.explain(q) == f"no answer saved in Settings ({key})", q


def test_ged_does_not_match_inside_words():
    a = answerer({"high_school": "Yes"})
    assert a.answer_for("have you acknowledged the policy?") is None


# ------------------------------------------------------------------ 3. locations

def test_find_location():
    assert find_location("Sales Rep\nGrimco, Inc.\nPortland, OR (On-site)\nEasy Apply") == "Portland, OR (On-site)"
    assert find_location("Acme · Beaverton, Oregon, United States · 2 days ago · 40 applicants") == "Beaverton, Oregon, United States"
    assert find_location("Acme\nUnited States (Remote)\nPromoted") == "United States (Remote)"
    assert find_location("Account Executive\nAcme Corp\n$60K/yr") is None


def test_parse_card_text():
    card = "Outside Sales Representative\nOutside Sales Representative with verification\nPrecision Truss & Lumber, Inc.\nDallas, TX (On-site)\n$55K/yr - $70K/yr\nEasy Apply"
    p = parse_card_text(card)
    assert p == {"title": "Outside Sales Representative", "company": "Precision Truss & Lumber, Inc.",
                 "location": "Dallas, TX (On-site)"}
    # and the area check can now use it
    assert outside_area(p["location"], "", {"OR"}).startswith("Outside your area (TX")


# ------------------------------------------------------------------ 4. radio selection on a LinkedIn-like form

MODAL = """
<div role="dialog" class="jobs-easy-apply-modal">
 <fieldset data-test-form-builder-radio-button-form-component="true">
  <legend><span class="fb-dash-form-element__label-title--is-required">
     <span aria-hidden="true">Will you now, or in the future, require sponsorship for employment visa status (e.g. H-1B visa status)?</span>
     <span class="visually-hidden">Will you now, or in the future, require sponsorship for employment visa status (e.g. H-1B visa status)?</span>
  </span><span class="visually-hidden">Required</span></legend>
  <div><input type="radio" id="r-yes" name="q1" value="Yes" style="opacity:0;position:absolute">
       <label for="r-yes" data-test-text-selectable-option__label="Yes">Yes</label></div>
  <div><input type="radio" id="r-no" name="q1" value="No" style="opacity:0;position:absolute">
       <label for="r-no" data-test-text-selectable-option__label="No">No</label></div>
 </fieldset>
 <fieldset>
  <legend><span>Do you have the following license or certification: Registered Dietician (RD)?</span></legend>
  <div><input type="radio" id="d-yes" name="q2" value="Yes"><label for="d-yes">Yes</label></div>
  <div><input type="radio" id="d-no" name="q2" value="No"><label for="d-no">No</label></div>
 </fieldset>
</div>
"""


def _chromium():
    try:
        from playwright.async_api import async_playwright  # noqa: F401
    except Exception:
        return None
    for p in ("/opt/pw-browsers/chromium", None):
        if p is None or Path(p).exists():
            return p or ""
    return ""


@pytest.mark.skipif(_chromium() is None, reason="playwright not installed")
def test_fill_step_selects_radio_and_reports():
    from playwright.async_api import async_playwright

    async def run():
        async with async_playwright() as pw:
            exe = _chromium()
            try:
                browser = await pw.chromium.launch(**({"executable_path": exe} if exe else {}))
            except Exception as e:
                pytest.skip(f"no browser: {e}")
            page = await browser.new_page()
            await page.set_content(MODAL)
            modal = page.locator('[role="dialog"]')
            a = answerer({"require_sponsorship": "No"})

            async def label_fn(m, f):
                return ""
            done = await a.fill_step(modal, label_fn)
            checked = await page.locator("#r-no").is_checked()
            dietitian = await page.locator('input[name="q2"]:checked').count()
            await browser.close()
            return done, checked, dietitian, a.given

    done, checked, dietitian, given = asyncio.run(run())
    assert checked, "the 'No' radio must really be selected"
    assert dietitian == 0, "an unrecognised question must stay unanswered"
    assert len(done) == 1 and given[0]["answer"] == "No"
    assert given[0]["question"].startswith("will you now, or in the future, require sponsorship")
    assert given[0]["question"].count("will you now") == 1, "duplicate hidden text must be removed"
