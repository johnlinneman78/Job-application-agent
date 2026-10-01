"""
Application tracker: what happened AFTER the bot applied.

Sources (all read-only):
  1. Gmail over IMAP (app password) - LinkedIn "application viewed" emails and
     replies from employers / ATS systems, classified as viewed / rejected /
     interview / offer / reply.
  2. LinkedIn "My Jobs > Applied" page - "Application viewed", "Resume downloaded",
     "No longer accepting applications".
  3. Manual updates from the dashboard (always win).

Data lives on each application record under record["tracking"]:
  {
    "stage": "applied" | "viewed" | "resume_downloaded" | "replied" | "interview"
             | "offer" | "rejected" | "withdrawn" | "no_response",
    "manual": bool,                 # set by the user - automation won't override
    "events": [{"at", "source", "stage", "detail"}],
    "last_activity": iso datetime,
    "follow_up_done": bool,
    "notes": str
  }
Only subject, sender, date and the classification are stored - never email bodies.
"""
import email
import imaplib
import logging
import os
import re
import smtplib
from collections import defaultdict
from datetime import datetime, timedelta
from email.header import decode_header, make_header
from email.message import EmailMessage
from email.utils import parseaddr, parsedate_to_datetime
from typing import Dict, Iterable, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------ stages

STAGE_RANK = {
    "applied": 1, "no_response": 1, "viewed": 2, "resume_downloaded": 3,
    "replied": 4, "interview": 5, "rejected": 6, "offer": 7, "withdrawn": 8,
}
TERMINAL = {"rejected", "offer", "withdrawn"}
ALL_STAGES = list(STAGE_RANK.keys())


def _now() -> datetime:
    return datetime.now()


def _parse_dt(s) -> Optional[datetime]:
    if not s:
        return None
    if isinstance(s, datetime):
        return s.replace(tzinfo=None)
    try:
        return datetime.fromisoformat(str(s).replace("Z", "")).replace(tzinfo=None)
    except Exception:
        return None


def ensure_tracking(rec: dict) -> dict:
    t = rec.setdefault("tracking", {})
    t.setdefault("stage", "applied")
    t.setdefault("manual", False)
    t.setdefault("events", [])
    t.setdefault("last_activity", rec.get("applied_at"))
    t.setdefault("follow_up_done", False)
    t.setdefault("notes", "")
    return t


def apply_event(rec: dict, stage: str, source: str, detail: str = "", at: Optional[datetime] = None) -> bool:
    """
    Record an event and move the stage forward if it is a later stage.
    Never moves backwards, never overrides a manual stage, never leaves a terminal stage.
    Returns True if the stage changed.
    """
    t = ensure_tracking(rec)
    at = at or _now()
    key = (source, stage, detail[:120])
    if any((e.get("source"), e.get("stage"), (e.get("detail") or "")[:120]) == key for e in t["events"]):
        return False  # already recorded
    t["events"].append({"at": at.isoformat(timespec="seconds"), "source": source, "stage": stage, "detail": detail[:300]})
    prev_activity = _parse_dt(t.get("last_activity"))
    if not prev_activity or at > prev_activity:
        t["last_activity"] = at.isoformat(timespec="seconds")
    cur = t["stage"]
    if t.get("manual") or cur in TERMINAL:
        return False
    if STAGE_RANK.get(stage, 0) > STAGE_RANK.get(cur, 0):
        t["stage"] = stage
        return True
    return False


def set_stage_manual(rec: dict, stage: str, notes: Optional[str] = None) -> None:
    if stage not in STAGE_RANK:
        raise ValueError(f"Unknown stage {stage}")
    t = ensure_tracking(rec)
    t["stage"] = stage
    t["manual"] = True
    t["events"].append({"at": _now().isoformat(timespec="seconds"), "source": "manual", "stage": stage, "detail": ""})
    t["last_activity"] = _now().isoformat(timespec="seconds")
    if notes is not None:
        t["notes"] = notes[:2000]


# ------------------------------------------------------- email classifier

# Order matters: rejection wording often also contains "interview"
# ("we will not be moving forward with an interview").
EMAIL_RULES: List[Tuple[str, List[str]]] = [
    ("offer", [r"\boffer letter\b", r"pleased to (extend|offer)", r"we.d like to offer you", r"job offer"]),
    ("rejected", [
        r"unfortunately", r"not (be )?moving forward", r"decided (not )?to (move|proceed|pursue) (forward )?with other",
        r"pursue other candidates", r"other candidates (whose|who)", r"will not be (proceeding|moving|advancing)",
        r"not (been )?selected", r"position has been filled", r"no longer (being )?consider",
        r"regret to inform", r"decided to go (in )?(a )?different direction", r"not a fit at this time",
    ]),
    ("interview", [
        r"schedule (a|an|your)? ?(call|interview|time|chat|conversation|phone screen)",
        r"\binterview\b", r"phone screen", r"your availability", r"availability (for|this|next)",
        r"calendly\.com", r"book a time", r"would (love|like) to (chat|speak|talk|connect) with you",
        r"next steps? in (the|our) (process|hiring)", r"set up a (call|time)",
    ]),
    ("viewed", [r"application was viewed", r"viewed your application", r"your application was seen"]),
    ("applied", [
        r"application was sent", r"thank(s| you) for (applying|your application|your interest)",
        r"we.ve received your application", r"we have received your application", r"application (has been )?received",
    ]),
]

ATS_DOMAINS = ["greenhouse", "lever.co", "workday", "myworkday", "icims", "smartrecruiters", "ashbyhq",
               "jobvite", "bamboohr", "breezy", "workable", "jazzhr", "recruitee", "paylocity", "adp", "ultipro",
               "dayforce", "paycom", "taleo", "successfactors", "rippling", "gusto", "applytojob", "hire.", "careers"]

LINKEDIN_SUBJECT_COMPANY = [
    re.compile(r"your application was sent to (?P<c>.+?)\s*$", re.I),
    re.compile(r"your application was viewed by (?P<c>.+?)\s*$", re.I),
    re.compile(r"application (?:to|for) .+? at (?P<c>.+?)\s*$", re.I),
]


def classify_email(subject: str, body: str, sender: str = "") -> Optional[str]:
    """Return a stage for a job-related email, or None if it doesn't look job-related."""
    text = f"{subject}\n{body[:6000]}".lower()
    for stage, patterns in EMAIL_RULES:
        if any(re.search(p, text) for p in patterns):
            # A plain 'unfortunately' in a non-job email is not a rejection:
            if stage == "rejected" and not re.search(r"application|position|role|candidacy|candidate|opportunit|interest in", text):
                continue
            if stage == "interview" and re.search(r"unsubscribe|webinar|newsletter|job alert", text) and "your application" not in text:
                continue
            return stage
    # A human reply about the application that fits no rule above
    if re.search(r"your (application|candidacy)|the .{0,40} (role|position) you applied", text):
        return "replied"
    return None


_SUFFIX = re.compile(r"\b(inc|llc|l\.l\.c|ltd|limited|corp|corporation|co|company|group|holdings|plc|gmbh|the|usa|us|llp|pc|pllc)\b\.?", re.I)


def norm_company(name: str) -> str:
    n = (name or "").lower()
    n = re.sub(r"[’'`]", "", n)
    n = _SUFFIX.sub(" ", n)
    n = re.sub(r"[^a-z0-9]+", " ", n)
    return re.sub(r"\s+", " ", n).strip()


def _company_in(company_norm: str, haystack_norm: str) -> bool:
    if not company_norm or len(company_norm) < 3:
        return False
    return re.search(r"(?<![a-z0-9])" + re.escape(company_norm) + r"(?![a-z0-9])", haystack_norm) is not None


def match_application(records: List[dict], subject: str, sender: str, body: str,
                      received_at: Optional[datetime] = None) -> Optional[dict]:
    """Find the submitted application this email is about (by company name)."""
    candidates = [r for r in records if r.get("status") == "submitted"]
    if received_at:
        candidates = [r for r in candidates
                      if not _parse_dt(r.get("applied_at")) or _parse_dt(r.get("applied_at")) <= received_at + timedelta(hours=1)]

    # 1) LinkedIn subjects name the company exactly
    for rx in LINKEDIN_SUBJECT_COMPANY:
        m = rx.search(subject or "")
        if m:
            target = norm_company(m.group("c"))
            hits = [r for r in candidates if norm_company((r.get("job") or {}).get("company", "")) == target]
            if hits:
                return max(hits, key=lambda r: r.get("applied_at") or "")

    name, addr = parseaddr(sender or "")
    domain = addr.split("@")[-1].lower() if "@" in addr else ""
    head = norm_company(f"{name} {subject} {domain.replace('.', ' ')}")
    body_n = norm_company(body[:3000])

    def score(r):
        c = norm_company((r.get("job") or {}).get("company", ""))
        if _company_in(c, head):
            return 2
        if _company_in(c, body_n):
            return 1
        compact = c.replace(" ", "")
        if compact and len(compact) >= 4 and compact in domain.replace("-", "").replace(".", ""):
            return 2
        return 0

    scored = [(score(r), r.get("applied_at") or "", r) for r in candidates]
    scored = [s for s in scored if s[0] > 0]
    if not scored:
        return None
    best = max(s[0] for s in scored)
    top = [s for s in scored if s[0] == best]
    # same company applied twice -> if the job title is in the email, prefer that one
    if len(top) > 1:
        text = f"{subject} {body[:3000]}".lower()
        titled = [s for s in top if ((s[2].get("job") or {}).get("title", "").lower() or "\x00") in text]
        if titled:
            top = titled
    return max(top, key=lambda s: s[1])[2]


def is_job_related_sender(sender: str) -> bool:
    _, addr = parseaddr(sender or "")
    addr = addr.lower()
    return "linkedin.com" in addr or any(d in addr for d in ATS_DOMAINS)


# ---------------------------------------------------------------- Gmail

def _dec(v) -> str:
    try:
        return str(make_header(decode_header(v or "")))
    except Exception:
        return v or ""


def _body_text(msg: email.message.Message) -> str:
    parts = []
    for part in msg.walk() if msg.is_multipart() else [msg]:
        ctype = part.get_content_type()
        if ctype in ("text/plain", "text/html") and "attachment" not in str(part.get("Content-Disposition", "")):
            try:
                payload = part.get_payload(decode=True) or b""
                txt = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
            except Exception:
                continue
            if ctype == "text/html":
                txt = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", txt, flags=re.S | re.I)
                txt = re.sub(r"<[^>]+>", " ", txt)
            parts.append(txt)
            if ctype == "text/plain":
                break
    return re.sub(r"\s+", " ", " ".join(parts))


def sync_gmail(records: List[dict], state: dict, address: str, app_password: str,
               days: int = 30, host: str = "imap.gmail.com") -> Dict[str, int]:
    """
    Read-only scan of the inbox for job emails from the last `days` days.
    Uses BODY.PEEK so nothing is marked as read. Updates `records` in place.
    `state` keeps processed Message-IDs and unmatched emails between runs.
    """
    seen = set(state.setdefault("seen_message_ids", []))
    unmatched = state.setdefault("unmatched", [])
    counts = defaultdict(int)

    since = (_now() - timedelta(days=days)).strftime("%d-%b-%Y")
    conn = imaplib.IMAP4_SSL(host)
    try:
        conn.login(address, app_password)
        conn.select("INBOX", readonly=True)
        query = ('X-GM-RAW', f'"newer_than:{days}d (application OR applying OR applied OR interview '
                             f'OR candidacy OR position OR role OR opportunity)"')
        try:
            typ, data = conn.search(None, *query)
        except Exception:
            typ, data = conn.search(None, "SINCE", since)
        ids = (data[0] or b"").split() if typ == "OK" else []
        logger.info(f"Gmail: {len(ids)} candidate emails")
        for mid in ids[-500:]:
            typ, msg_data = conn.fetch(mid, "(BODY.PEEK[])")
            if typ != "OK" or not msg_data or not isinstance(msg_data[0], tuple):
                continue
            msg = email.message_from_bytes(msg_data[0][1])
            message_id = (msg.get("Message-ID") or f"{mid.decode()}").strip()
            if message_id in seen:
                continue
            seen.add(message_id)
            subject, sender = _dec(msg.get("Subject")), _dec(msg.get("From"))
            try:
                received = parsedate_to_datetime(msg.get("Date")).replace(tzinfo=None)
            except Exception:
                received = _now()
            body = _body_text(msg)
            stage = classify_email(subject, body, sender)
            if not stage:
                continue
            counts["job_emails"] += 1
            rec = match_application(records, subject, sender, body, received)
            if rec is None:
                if stage != "applied":
                    unmatched.append({"at": received.isoformat(timespec="seconds"), "from": sender[:120],
                                      "subject": subject[:200], "stage": stage, "message_id": message_id})
                    counts["unmatched"] += 1
                continue
            if apply_event(rec, stage, "email", f"{subject[:150]} — {parseaddr(sender)[0] or parseaddr(sender)[1]}", received):
                counts[f"moved_to_{stage}"] += 1
            counts["matched"] += 1
    finally:
        try:
            conn.logout()
        except Exception:
            pass
    state["seen_message_ids"] = list(seen)[-5000:]
    state["unmatched"] = unmatched[-200:]
    state["last_gmail_sync"] = _now().isoformat(timespec="seconds")
    return dict(counts)


# ------------------------------------------------- LinkedIn applied page

LINKEDIN_APPLIED_URL = "https://www.linkedin.com/my-items/saved-jobs/?cardType=APPLIED"

LINKEDIN_STATUS_RULES = [
    ("resume_downloaded", r"resume (was )?downloaded"),
    ("viewed", r"application viewed|viewed by|was viewed"),
    ("closed", r"no longer accepting applications"),
]


def parse_linkedin_status(card_text: str) -> Optional[str]:
    t = (card_text or "").lower()
    for stage, rx in LINKEDIN_STATUS_RULES:
        if re.search(rx, t):
            return stage
    return None


def _job_num(job_id_or_url: str) -> Optional[str]:
    m = re.search(r"(\d{6,})", job_id_or_url or "")
    return m.group(1) if m else None


async def sync_linkedin_applied(page, records: List[dict], max_pages: int = 4) -> Dict[str, int]:
    """
    Read LinkedIn's 'My Jobs > Applied' list (logged-in page) and record
    'Application viewed' / 'Resume downloaded' / 'No longer accepting applications'.
    """
    by_id = {}
    for r in records:
        n = _job_num((r.get("job") or {}).get("id", "")) or _job_num((r.get("job") or {}).get("url", ""))
        if n:
            by_id[n] = r
    counts = defaultdict(int)
    await page.goto(LINKEDIN_APPLIED_URL, wait_until="domcontentloaded", timeout=45000)
    await page.wait_for_timeout(3000)

    for page_no in range(max_pages):
        cards = await page.eval_on_selector_all(
            'a[href*="/jobs/view/"]',
            """els => els.map(a => {
                const card = a.closest('li') || a.closest('[data-chameleon-result-urn]') || a.parentElement;
                return {href: a.href, text: card ? card.innerText : a.innerText};
            })""",
        )
        for c in cards:
            n = _job_num(c.get("href", ""))
            rec = by_id.get(n)
            if not rec:
                continue
            counts["seen"] += 1
            status = parse_linkedin_status(c.get("text", ""))
            if status == "closed":
                t = ensure_tracking(rec)
                if not t.get("posting_closed"):
                    t["posting_closed"] = True
                    t["events"].append({"at": _now().isoformat(timespec="seconds"), "source": "linkedin",
                                        "stage": t["stage"], "detail": "No longer accepting applications"})
                    counts["closed"] += 1
            elif status and apply_event(rec, status, "linkedin", "LinkedIn: " + status.replace("_", " ")):
                counts[f"moved_to_{status}"] += 1
        nxt = page.locator('button[aria-label*="Next" i]:not([disabled]), button.artdeco-pagination__button--next:not([disabled])').first
        if await nxt.count() and await nxt.is_visible():
            await nxt.click()
            await page.wait_for_timeout(2500)
        else:
            break
    return dict(counts)


# ---------------------------------------------------- derived views

def refresh_no_response(records: List[dict], days: int = 21) -> int:
    """Mark submitted applications with no activity for `days` days as no_response."""
    changed = 0
    cutoff = _now() - timedelta(days=days)
    for r in records:
        if r.get("status") != "submitted":
            continue
        t = ensure_tracking(r)
        if t["manual"] or t["stage"] != "applied":
            continue
        applied = _parse_dt(r.get("applied_at"))
        if applied and applied < cutoff:
            t["stage"] = "no_response"
            changed += 1
    return changed


def _business_days_since(d: datetime) -> int:
    days, cur = 0, d.date()
    end = _now().date()
    while cur < end:
        cur += timedelta(days=1)
        if cur.weekday() < 5:
            days += 1
    return days


def follow_ups_due(records: List[dict], after_business_days: int = 3) -> List[dict]:
    """
    Applications worth a personal follow-up today:
    submitted, no reply yet (applied / viewed / resume downloaded), posting still open,
    a recruiter is known, not followed up yet, and at least N business days old.
    'Viewed' or 'resume downloaded' jobs are listed first - someone is looking.
    """
    due = []
    for r in records:
        if r.get("status") != "submitted":
            continue
        t = ensure_tracking(r)
        job = r.get("job") or {}
        if t["stage"] not in ("applied", "viewed", "resume_downloaded") or t.get("follow_up_done") or t.get("posting_closed"):
            continue
        if not job.get("recruiter_name") and not job.get("recruiter_url"):
            continue
        applied = _parse_dt(r.get("applied_at"))
        if not applied or _business_days_since(applied) < after_business_days:
            continue
        due.append(r)
    pri = {"resume_downloaded": 0, "viewed": 1, "applied": 2}
    return sorted(due, key=lambda r: (pri.get(r["tracking"]["stage"], 3), r.get("applied_at") or ""))


def _title_bucket(title: str) -> str:
    t = (title or "").lower()
    for bucket, words in [
        ("Account Executive", ["account executive", " ae "]),
        ("Account Manager", ["account manager", "account management"]),
        ("SDR / BDR", ["sdr", "bdr", "sales development", "business development rep"]),
        ("Customer Success", ["customer success", "csm", "client success"]),
        ("Inside Sales", ["inside sales"]),
        ("Customer Service", ["customer service", "client service", "customer support"]),
        ("IT Support", ["it support", "help desk", "helpdesk", "desktop support", "technician"]),
        ("Sales (other)", ["sales"]),
    ]:
        if any(w in f" {t} " for w in words):
            return bucket
    return "Other"


def compute_stats(records: List[dict]) -> dict:
    """Funnel numbers overall and per job-title group, plus why jobs were skipped."""
    submitted = [r for r in records if r.get("status") == "submitted"]
    skipped = [r for r in records if r.get("status") in ("skipped", "failed")]

    def funnel(rs):
        stages = [ensure_tracking(r)["stage"] for r in rs]
        n = len(rs)
        viewed = sum(STAGE_RANK.get(s, 0) >= 2 and s not in ("withdrawn",) for s in stages)
        replied = sum(s in ("replied", "interview", "offer", "rejected") for s in stages)
        positive = sum(s in ("replied", "interview", "offer") for s in stages)
        interviews = sum(s in ("interview", "offer") for s in stages)
        pct = lambda x: round(100 * x / n, 1) if n else 0.0
        return {"applied": n, "viewed": viewed, "any_reply": replied, "positive_reply": positive,
                "interviews": interviews, "rejected": stages.count("rejected"), "offers": stages.count("offer"),
                "no_response": stages.count("no_response"),
                "view_rate": pct(viewed), "reply_rate": pct(replied), "interview_rate": pct(interviews)}

    by_title = defaultdict(list)
    for r in submitted:
        by_title[_title_bucket((r.get("job") or {}).get("title", ""))].append(r)

    skip_reasons = defaultdict(int)
    blocking = defaultdict(int)
    for r in skipped:
        reason = r.get("failure_reason") or "Unknown"
        skip_reasons[reason.split(":")[0]] += 1
        m = re.search(r"'(.+?)'\s*$", reason)          # "...: Question field: 'how many years of ...'"
        if m and m.group(1) not in ("unlabeled", ""):
            blocking[m.group(1).strip().lower()] += 1

    attempts = len(submitted) + len(skipped)
    return {
        "overall": funnel(submitted),
        "by_title": {k: funnel(v) for k, v in sorted(by_title.items(), key=lambda kv: -len(kv[1]))},
        "attempts": attempts,
        "submit_rate": round(100 * len(submitted) / attempts, 1) if attempts else 0.0,
        "skip_reasons": dict(sorted(skip_reasons.items(), key=lambda kv: -kv[1])),
        # the exact screening questions that blocked applications, most common first
        "blocking_questions": dict(sorted(blocking.items(), key=lambda kv: -kv[1])[:25]),
    }


# ----------------------------------------------------------- pitch

TOOL_SKILLS = {"Salesforce", "HubSpot", "CRM", "ZoomInfo", "Outreach.io", "Salesloft", "LinkedIn Sales Navigator",
               "Gong", "Excel", "Microsoft 365", "Active Directory", "AWS", "Azure", "Linux", "Windows", "Python",
               "JavaScript", "SQL", "APIs", "ticketing systems"}

def build_follow_up_note(job: dict, candidate_name: str, skills: Iterable[str] = (), applied: bool = True,
                         max_len: int = 200) -> str:
    """
    Short LinkedIn connection note to the recruiter / hiring manager.
    Kept under 200 characters (free-account limit for connection notes).
    Only claims "I applied" when the application was actually submitted.
    """
    first = (job.get("recruiter_name") or "").split()[0] if job.get("recruiter_name") else "there"
    role, company = job.get("title") or "the open role", job.get("company") or "your team"
    skill = next((s for s in skills if s), None)
    me = (candidate_name or "").split()[0] if candidate_name else ""
    lead = f"Hi {first}, I just applied for the {role} role at {company}." if applied \
        else f"Hi {first}, I'm interested in the {role} role at {company}."
    variants = [
        (f"{lead} I've worked hands-on with {skill} and I'd welcome the chance to connect. {me}".strip()
         if skill in TOOL_SKILLS else
         f"{lead} My background is in {skill} and I'd welcome the chance to connect. {me}".strip()) if skill else None,
        f"{lead} I'd welcome the chance to connect and share a bit about my background. {me}".strip(),
        f"{lead} I'd welcome the chance to connect. {me}".strip(),
        lead,
    ]
    for v in variants:
        if v and len(v) <= max_len:
            return v
    return lead[:max_len]


# ------------------------------------------------------------- digest

def build_digest(records: List[dict], state: dict) -> Tuple[str, str]:
    """Plain-text daily summary (subject, body)."""
    stats = compute_stats(records)
    o = stats["overall"]
    since = _now() - timedelta(days=1)
    recent = []
    for r in records:
        for e in ensure_tracking(r)["events"]:
            at = _parse_dt(e.get("at"))
            if at and at >= since and e.get("source") != "manual":
                j = r.get("job") or {}
                recent.append(f"- {e['stage'].upper()}: {j.get('title')} @ {j.get('company')} ({e.get('detail', '')[:90]})")
    today_apps = [r for r in records if r.get("status") == "submitted" and (_parse_dt(r.get("applied_at")) or datetime.min) >= since]
    due = follow_ups_due(records)
    lines = [
        f"Applied in the last 24h: {len(today_apps)}",
        f"Total applied: {o['applied']} | viewed {o['view_rate']}% | any reply {o['reply_rate']}% | interviews {o['interviews']}",
        f"Submit rate (submitted / attempted): {stats['submit_rate']}%",
        "",
        "New activity (24h):" if recent else "No new replies in the last 24h.",
        *recent[:30],
        "",
        f"Follow-ups due today ({len(due)}):" if due else "No follow-ups due.",
        *[f"- {(r['job'].get('recruiter_name') or 'Recruiter')} — {r['job'].get('title')} @ {r['job'].get('company')} "
          f"[{r['tracking']['stage']}] {r['job'].get('recruiter_url') or ''}" for r in due[:15]],
    ]
    if state.get("unmatched"):
        lines += ["", f"Job emails I couldn't match to an application: {len(state['unmatched'])} (see Tracker page)"]
    if stats["skip_reasons"]:
        lines += ["", "Why jobs were skipped:", *[f"- {k}: {v}" for k, v in stats["skip_reasons"].items()]]
    subject = f"Job tracker: {len(today_apps)} applied, {len([x for x in recent if x.startswith('- INTERVIEW')])} interview replies"
    return subject, "\n".join(lines)


def send_digest(subject: str, body: str, address: str, app_password: str, to: Optional[str] = None,
                host: str = "smtp.gmail.com", port: int = 587) -> None:
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = subject, address, to or address
    msg.set_content(body)
    with smtplib.SMTP(host, port, timeout=30) as s:
        s.starttls()
        s.login(address, app_password)
        s.send_message(msg)


def gmail_credentials() -> Tuple[Optional[str], Optional[str]]:
    """GMAIL_ADDRESS / GMAIL_APP_PASSWORD from the environment (.env). Never from config files in git."""
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except Exception:
        pass
    return os.environ.get("GMAIL_ADDRESS"), os.environ.get("GMAIL_APP_PASSWORD")
