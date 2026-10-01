"""Search settings, salary rules and screening answers.  python -m pytest tests/test_settings.py -q"""
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import salary as S  # noqa: E402
from src.application_guard import ApplicationGuard  # noqa: E402
from src.job_scraper import JobScraper  # noqa: E402
from src.models import Job, Platform  # noqa: E402
from src.screening_answers import ScreeningAnswerer  # noqa: E402


def scraper(search=None, salary=None):
    cfg = {"search": search or {}, "salary": salary or {}}
    return JobScraper(cfg, ApplicationGuard(cfg))


def qs(url):
    return {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}


def test_search_url_uses_settings():
    sc = scraper({"work_types": ["remote", "hybrid"], "experience_levels": ["entry", "associate"], "distance_miles": 25},
                 {"salary_min": 65000, "only_listed_salary": True})
    q = qs(sc._build_linkedin_search_url("Account Manager", "Portland, OR", 7))
    assert q["keywords"] == "Account Manager" and q["location"] == "Portland, OR"
    assert q["f_AL"] == "true" and q["f_TPR"] == "r604800"
    assert q["f_WT"] == "2,3" and q["f_E"] == "2,3" and q["distance"] == "25" and q["f_SB2"] == "2"


def test_remote_location_becomes_us_plus_remote_filter():
    q = qs(scraper()._build_linkedin_search_url("SDR", "Remote", 14))
    assert q["location"] == "United States" and q["f_WT"] == "2" and "distance" not in q


def test_no_optional_filters_when_unset():
    q = qs(scraper()._build_linkedin_search_url("SDR", "Seattle, WA", 30))
    assert "f_WT" not in q and "f_E" not in q and "f_SB2" not in q and q["f_TPR"] == "r2592000"


def test_exclusions():
    sc = scraper({"exclude_title_words": ["Senior", "commission only"], "exclude_companies": ["Acme"]})
    job = lambda t, c="Globex": Job(job_id="1", platform=Platform.LINKEDIN, title=t, company=c, location="", url="u")
    assert sc.excluded_reason(job("Senior Account Executive"))
    assert sc.excluded_reason(job("Sales Rep - Commission Only"))
    assert sc.excluded_reason(job("Account Manager", "Acme Corporation"))
    assert sc.excluded_reason(job("Seniority Program Manager")) is None   # whole words only
    assert sc.excluded_reason(job("Account Manager")) is None


def test_salary_parsing_and_minimum():
    assert S.parse_salary_range("$60K/yr - $75K/yr") == (60000, 75000)
    assert S.parse_salary_range("$25/hr - $32/hr") == (52000, 66560)
    assert S.parse_salary_range("Includes a $500 signing bonus") is None
    cfg = {"salary": {"salary_min": 60000, "salary_max": 90000}}
    assert S.below_minimum((40000, 55000), cfg) is True
    assert S.below_minimum((50000, 70000), cfg) is False      # range reaches your minimum -> apply
    assert S.below_minimum(None, cfg) is False                 # no pay listed -> apply
    assert S.below_minimum((40000, 55000), {"salary": {"salary_min": 60000, "skip_if_listed_below_min": False}}) is False


def test_salary_answer():
    cfg = {"salary": {"salary_min": 60000, "salary_max": 90000}}
    assert S.answer_for_question("desired salary", cfg) == "75000"
    assert S.answer_for_question("desired hourly rate", cfg) == "36"
    assert S.answer_for_question("desired salary", {"salary": {"salary_min": 60000, "salary_max": 90000, "salary_target": 80000}}) == "80000"
    assert S.answer_for_question("desired salary", {}) is None


def test_numeric_options():
    assert S.pick_numeric_option(["0-2 years", "3-5 years", "6-10 years", "10+ years"], 8) == "6-10 years"
    assert S.pick_numeric_option(["Under $50,000", "$50,000 - $70,000", "$70,000 - $90,000"], 75000) == "$70,000 - $90,000"
    assert S.pick_numeric_option(["Less than 1 year", "1-3 years", "5+ years"], 12) == "5+ years"


CFG = {"personal_info": {"city": "Portland, Oregon", "phone": "5035550100"},
       "salary": {"salary_min": 60000, "salary_max": 90000},
       "screening_answers": {"work_authorization": "Yes", "require_sponsorship": "No", "years_experience": "8",
                             "sales_experience": "6", "skill_years": {"salesforce": 3}, "veteran": "No", "gender": "Decline"}}


def test_answers_known_and_refuses_unknown():
    a = ScreeningAnswerer(CFG)
    assert a.answer_for("are you authorized to work in the us without sponsorship?") == "Yes"
    assert a.answer_for("will you require visa sponsorship?") == "No"
    assert a.answer_for("what is your desired salary?") == "75000"
    assert a.answer_for("how many years of experience do you have with salesforce?") == "3"
    assert a.answer_for("do you have experience with salesforce?") == "Yes"
    assert a.answer_for("city") == "Portland, Oregon"
    for q in ["do you have a valid cdl?", "have you been convicted of a felony?", "how many years of python?",
              "do you have experience with workday?", "why do you want this job?", "are you willing to relocate?"]:
        assert a.answer_for(q) is None, q


def test_option_matching():
    pick = ScreeningAnswerer._pick_option
    assert pick(["Select an option", "Yes", "No"], "No") == "No"
    assert pick(["Male", "Female", "I don't wish to answer"], "Decline") == "I don't wish to answer"
    assert pick(["Female", "Male"], "Male") == "Male"
    assert pick(["I am a protected veteran", "I am not a protected veteran", "I don't wish to answer"], "No") == "I am not a protected veteran"
    assert pick(["Yes", "No"], "Maybe") is None
