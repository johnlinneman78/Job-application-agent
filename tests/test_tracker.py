"""Tests for src/tracker.py - run with:  python -m pytest tests/test_tracker.py -q"""
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import tracker as T  # noqa: E402


def rec(company, title="Account Executive", days_ago=5, status="submitted", app_id=None, recruiter=None):
    return {
        "id": app_id or f"app_{company[:4]}",
        "status": status,
        "applied_at": (datetime.now() - timedelta(days=days_ago)).isoformat(),
        "failure_reason": None if status == "submitted" else "Screening questions present",
        "job": {"id": f"linkedin_40{abs(hash(company)) % 10**8:08d}", "title": title, "company": company,
                "url": "", "recruiter_name": recruiter, "recruiter_url": "https://www.linkedin.com/in/x" if recruiter else None},
    }


# ---------------------------------------------------------------- classify

def test_classify_rejection_beats_interview_word():
    body = "Thank you for your interest in the Account Executive role. Unfortunately, we will not be moving forward with an interview."
    assert T.classify_email("Your application to Acme", body) == "rejected"


def test_classify_interview():
    assert T.classify_email("Next steps - Acme", "Hi John, we'd love to schedule a phone screen. What's your availability this week?") == "interview"
    assert T.classify_email("Acme / John", "Grab a time here: https://calendly.com/recruiter/30min") == "interview"


def test_classify_linkedin_viewed_and_sent():
    assert T.classify_email("Your application was viewed by Acme Corporation", "") == "viewed"
    assert T.classify_email("John, your application was sent to Acme", "") == "applied"


def test_classify_offer():
    assert T.classify_email("Offer - Account Executive", "We are pleased to extend an offer for the role.") == "offer"


def test_classify_ignores_non_job_mail():
    assert T.classify_email("Your order shipped", "Unfortunately your package is delayed.") is None
    assert T.classify_email("Weekly newsletter", "Join our webinar on interview tips. Unsubscribe here.") is None


# ---------------------------------------------------------------- matching

def test_match_by_linkedin_subject():
    recs = [rec("Acme Corporation"), rec("Globex")]
    m = T.match_application(recs, "Your application was viewed by Acme Corporation", "jobs-noreply@linkedin.com", "")
    assert m["job"]["company"] == "Acme Corporation"


def test_match_by_sender_domain_and_name():
    recs = [rec("Acme Corp"), rec("Globex Inc")]
    m = T.match_application(recs, "Update on your application", "Globex Talent <talent@globex.com>", "Hi John")
    assert m["job"]["company"] == "Globex Inc"


def test_match_ats_email_with_company_in_body():
    recs = [rec("Initech"), rec("Hooli")]
    body = "Thank you for applying to the Account Manager position at Hooli. Unfortunately..."
    m = T.match_application(recs, "Your application", "no-reply@greenhouse.io", body)
    assert m["job"]["company"] == "Hooli"


def test_no_match_returns_none():
    assert T.match_application([rec("Acme")], "Hello", "friend@gmail.com", "lunch?") is None


def test_skipped_applications_never_matched():
    assert T.match_application([rec("Acme", status="skipped")], "Your application was viewed by Acme", "", "") is None


# ---------------------------------------------------------------- stage logic

def test_stage_only_moves_forward_and_respects_manual():
    r = rec("Acme")
    assert T.apply_event(r, "viewed", "linkedin", "viewed")
    assert T.apply_event(r, "interview", "email", "schedule")
    assert not T.apply_event(r, "viewed", "linkedin", "viewed again")   # no going back
    assert r["tracking"]["stage"] == "interview"
    T.set_stage_manual(r, "withdrawn")
    assert not T.apply_event(r, "offer", "email", "offer")             # manual wins
    assert r["tracking"]["stage"] == "withdrawn"


def test_duplicate_event_ignored():
    r = rec("Acme")
    T.apply_event(r, "viewed", "linkedin", "LinkedIn: viewed")
    T.apply_event(r, "viewed", "linkedin", "LinkedIn: viewed")
    assert len(r["tracking"]["events"]) == 1


def test_no_response_after_21_days():
    old, new = rec("Old Co", days_ago=30), rec("New Co", days_ago=2)
    assert T.refresh_no_response([old, new]) == 1
    assert old["tracking"]["stage"] == "no_response" and new["tracking"]["stage"] == "applied"


def test_follow_ups_due_prioritises_viewed():
    a = rec("Acme", days_ago=8, recruiter="Sarah Kim", app_id="a")
    b = rec("Globex", days_ago=8, recruiter="Tom Lee", app_id="b")
    c = rec("Initech", days_ago=8, recruiter=None, app_id="c")          # no recruiter -> not listed
    d = rec("Hooli", days_ago=0, recruiter="Ann", app_id="d")           # too new
    T.apply_event(b, "viewed", "linkedin", "viewed")
    due = T.follow_ups_due([a, b, c, d])
    assert [r["id"] for r in due] == ["b", "a"]


def test_stats_and_skip_reasons():
    recs = [rec("A"), rec("B"), rec("C", status="skipped"), rec("D", status="skipped", title="SDR")]
    T.apply_event(recs[0], "interview", "email", "x")
    s = T.compute_stats(recs)
    assert s["overall"]["applied"] == 2 and s["overall"]["interviews"] == 1
    assert s["submit_rate"] == 50.0
    assert s["skip_reasons"] == {"Screening questions present": 2}


# ---------------------------------------------------------------- linkedin + note + digest

def test_parse_linkedin_status():
    assert T.parse_linkedin_status("Account Executive\nAcme\nApplication viewed 2d ago") == "viewed"
    assert T.parse_linkedin_status("Resume downloaded 1d ago") == "resume_downloaded"
    assert T.parse_linkedin_status("No longer accepting applications") == "closed"
    assert T.parse_linkedin_status("Applied 3d ago") is None


def test_note_is_short_and_honest():
    job = {"title": "Regional Strategic Enterprise Healthcare Technology Account Executive II",
           "company": "International Business Machines Corporation", "recruiter_name": "Alexandra Smith"}
    applied = T.build_follow_up_note(job, "Jordan Sample", ["account management"], applied=True)
    queued = T.build_follow_up_note(job, "Jordan Sample", ["account management"], applied=False)
    assert len(applied) <= 200 and len(queued) <= 200
    assert "applied" in applied and "applied" not in queued


def test_digest_builds():
    recs = [rec("Acme", recruiter="Sarah", days_ago=6)]
    T.apply_event(recs[0], "viewed", "email", "Your application was viewed by Acme", datetime.now())
    subject, body = T.build_digest(recs, {"unmatched": []})
    assert "Job tracker" in subject and "VIEWED" in body and "Follow-ups due" in body
