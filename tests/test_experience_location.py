"""Resume-derived experience, local-first search plan, area check.
python -m pytest tests/test_experience_location.py -q"""
import asyncio
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.application_guard import ApplicationGuard  # noqa: E402
from src.experience import build_profile  # noqa: E402
from src.job_scraper import JobScraper  # noqa: E402
from src.locations import home_states, outside_area  # noqa: E402
from src.models import Job, Platform, Resume  # noqa: E402
from src.screening_answers import ScreeningAnswerer  # noqa: E402
from src import tracker as T  # noqa: E402

RESUME = (Path(__file__).parent / "fixtures" / "sample_resume.txt").read_text(encoding="utf-8")


# ------------------------------------------------------------------ experience

def test_profile_from_resume():
    p = build_profile(RESUME).as_dict()
    assert len(p["roles"]) == 8                       # education line is not a job
    assert p["total_years"] == 6
    assert p["areas"]["sales"] == 4 and p["areas"]["customer service"] == 3 and p["areas"]["healthcare"] == 2
    assert p["tools"]["salesforce"] == 2
    assert "zendesk" in p["skills_only"]              # in Skills, no dated job mentions it


def answerer(extra=None, mode=None):
    sa = {"years_experience": "", "sales_experience": ""}
    if mode:
        sa["no_experience_answer"] = mode
    sa.update(extra or {})
    a = ScreeningAnswerer({"screening_answers": sa})
    a.load_resume(resume_text=RESUME)
    return a


def test_years_questions_from_resume():
    a = answerer()
    q = lambda s: a.answer_for(s.lower())
    assert q("How many years of customer service experience do you have?") == "3"
    assert q("How many years of call center experience do you have?") == "3"
    assert q("How many years of sales experience do you have?") == "4"
    assert q("How many years of experience in healthcare?") == "2"
    assert q("How many years of experience do you have with Salesforce?") == "2"
    assert q("How many years of work experience do you have?") == "6"
    assert q("How many years of experience do you have with Zendesk?") is None   # skills-only: years unknown
    assert q("How many years of hospitality experience do you have?") is None    # unrecognised area -> skip


def test_yes_no_experience_questions():
    a = answerer()
    q = lambda s: a.answer_for(s.lower())
    assert q("Do you have experience with Salesforce?") == "Yes"
    assert q("Do you have experience with Zendesk?") == "Yes"
    assert q("Do you have experience in customer service?") == "Yes"
    assert q("Do you have experience with Workday?") is None          # not a known tool -> skip


def test_no_experience_mode():
    honest = answerer()
    skip = answerer(mode="skip")
    question = "how many years of experience do you have with jira?"
    assert honest.answer_for(question) == "0"
    assert skip.answer_for(question) is None
    assert honest.answer_for("do you have experience with jira?") == "No"


def test_manual_settings_override_resume():
    a = answerer({"skill_years": {"salesforce": 5}, "sales_experience": "7", "years_experience": "10"})
    assert a.answer_for("how many years of experience do you have with salesforce?") == "5"
    assert a.answer_for("how many years of sales experience do you have?") == "7"
    assert a.answer_for("how many years of work experience do you have?") == "10"


def test_resume_can_be_turned_off():
    a = ScreeningAnswerer({"screening_answers": {"use_resume_experience": "false"}})
    a.load_resume(resume_text=RESUME)
    assert a.profile is None
    assert a.answer_for("how many years of customer service experience do you have?") is None


# ------------------------------------------------------------------ search plan

def scraper(search):
    cfg = {"search": search}
    return JobScraper(cfg, ApplicationGuard(cfg))


def qs(url):
    return {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}


LOCS = ["Remote", "Portland, OR", "Beaverton, OR"]


def test_plan_local_first_and_remote_in_state():
    sc = scraper({"work_types": ["remote", "hybrid", "onsite"], "locations": LOCS, "distance_miles": 25})
    plan = sc.build_search_plan(["Customer Success", "Account Manager"], LOCS)
    local = [p for p in plan if p["group"] == "local"]
    remote = [p for p in plan if p["group"] == "remote"]
    assert plan[:len(local)] == local                                   # local searches come first
    assert {p["location"] for p in local} == {"Portland, OR", "Beaverton, OR"}
    assert all(p["work_types"] == ["hybrid", "onsite"] for p in local)  # no remote jobs in local searches
    assert {p["location"] for p in remote} == {"Oregon, United States"} and all(p["work_types"] == ["remote"] for p in remote)
    q = qs(sc._build_linkedin_search_url("Account Manager", "Portland, OR", 7, work_types=["hybrid", "onsite"]))
    assert q["f_WT"] == "1,3" and q["distance"] == "25"
    q = qs(sc._build_linkedin_search_url("Account Manager", "Oregon, United States", 7, work_types=["remote"]))
    assert q["f_WT"] == "2" and "distance" not in q


def test_plan_remote_scope_us_and_off():
    us = scraper({"work_types": ["remote", "onsite"], "remote_scope": "us"}).build_search_plan(["SDR"], ["Portland, OR"])
    assert [p["location"] for p in us if p["group"] == "remote"] == ["United States"]
    off = scraper({"work_types": ["remote", "onsite"], "remote_scope": "off"}).build_search_plan(["SDR"], ["Portland, OR"])
    assert all(p["group"] == "local" for p in off)
    remote_only = scraper({"work_types": ["remote"]}).build_search_plan(["SDR"], ["Portland, OR"])
    assert all(p["group"] == "remote" for p in remote_only)


def test_quotas_spread_across_titles_and_respect_mix():
    sc = scraper({"work_types": ["remote", "hybrid", "onsite"], "locations": LOCS, "max_discovered": 40, "local_share": 70})
    calls = []

    async def fake_search(page, url, title, location):
        calls.append((title, location))
        tag = f"{title}|{location}"
        return [Job(job_id=f"{tag}-{i}", platform=Platform.LINKEDIN, title=title, company="C", location=location, url="u")
                for i in range(25)]

    sc._scrape_one_search = fake_search
    sc.context = None
    titles = ["T1", "T2", "T3", "T4"]
    jobs = asyncio.run(sc._scrape_linkedin(titles, LOCS, 14, page=object()))
    assert len(jobs) == 40
    local = [j for j in jobs if j.search_group == "local"]
    assert len(local) == 28                                          # 70% of 40
    assert {t for t, _ in calls} == set(titles)                       # every title gets searched
    assert jobs[:28] == local                                         # local jobs first (applied first)


def test_outside_area():
    allowed = home_states(LOCS)
    assert allowed == {"OR"}
    assert outside_area("Austin, TX (Hybrid)", "", allowed)
    assert outside_area("Chicago, IL (On-site)", "", allowed)
    assert outside_area("Portland, OR (On-site)", "", allowed) is None
    assert outside_area("United States (Remote)", "", allowed) is None
    assert outside_area("Unknown", "", allowed) is None


def test_ranker_prefers_local():
    from src.job_ranker import JobRanker
    r = JobRanker(Resume(name="", email="", phone=""), LOCS)
    assert r._score_location_match("Portland, OR (Hybrid)") > r._score_location_match("United States (Remote)") > r._score_location_match("Austin, TX")


# ------------------------------------------------------------------ blocking questions

def test_blocking_questions_in_stats():
    recs = [{"status": "skipped", "failure_reason": "Screening questions present: Question field: 'how many years of zendesk?'"},
            {"status": "skipped", "failure_reason": "Screening questions present: Question field: 'how many years of zendesk?'"},
            {"status": "skipped", "failure_reason": "Screening questions present: Multiple-choice question: 'do you have a cdl?'"},
            {"status": "skipped", "failure_reason": "No Easy Apply button found"}]
    s = T.compute_stats(recs)
    assert s["blocking_questions"] == {"how many years of zendesk?": 2, "do you have a cdl?": 1}
    assert s["skip_reasons"]["Screening questions present"] == 3


def test_area_matching_is_strict():
    from src.experience import area_for_question as area, tool_for_question as tool
    assert area("How many years of B2B sales experience?") == "b2b sales"
    assert area("How many years of inside sales experience?") == "sales"
    assert area("How many years of experience do you have in customer-facing roles?") == "customer service"
    # extra qualifiers mean a different skill -> don't reuse a broader number
    assert area("How many years of medical billing experience?") is None
    assert area("How many years of outside sales experience?") is None
    assert area("How many years of SaaS sales experience?") is None
    assert area("How many years of hospitality experience?") is None
    assert tool("How many years of experience using Salesforce CRM?") == "salesforce"
    assert tool("How many years of Salesforce administration experience?") is None
