"""
Years of experience worked out from the resume, so screening questions like
"How many years of customer service experience do you have?" can be answered
without the user typing a skills list.

How it works:
  1. Split the resume into roles. A role starts at a line with a date range
     ("Aug 2019 – Jul 2021", "08/2019 - 07/2021", "2019 - 2021", "Mar 2026 - Present").
  2. Each role's text = the title/company lines just above the dates + the lines
     until the next role.
  3. For each experience area (customer service, sales, account management, IT support...)
     and each tool (Salesforce, Zendesk...), add up the months of the roles that mention it.
     Overlapping roles are merged so time is never double counted.
  4. Years are rounded DOWN (never overstated); anything from 6 to 11 months counts as 1.

Manual entries in Settings (skill_years) always win over these numbers.
"""
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional, Tuple

MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}
_MON = r"(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?"
_END = r"(present|current|now|today)"
_MON_NC = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?"
_DATE = rf"(?:{_MON_NC}\s+\d{{4}}|\d{{1,2}}/\d{{4}}|\d{{4}})"
RANGE_RE = re.compile(rf"(?P<start>{_DATE})\s*(?:-|–|—|to)\s*(?P<end>{_DATE}|present|current|now|today)", re.I)

# Experience areas: canonical key -> words that show a role involved it
AREAS: Dict[str, List[str]] = {
    "customer service": ["customer service", "customer support", "customer care", "client service", "client support",
                         "support specialist", "service desk", "help desk", "helpdesk", "guest service", "member support",
                         "call center", "contact center", "customer experience", "brand advocate"],
    "customer success": ["customer success", "client success", "onboarding", "retention", "renewal"],
    "sales": ["sales", "account executive", "account manager", "business development", "sdr", "bdr", "selling",
              "quota", "pipeline", "prospecting", "inside sales", "outside sales", "brand advocate", "lead generation"],
    "account management": ["account manager", "account management", "key accounts", "client portfolio", "book of business"],
    "b2b sales": ["b2b", "var", "channel", "reseller", "enterprise accounts", "federal", "government"],
    "it support": ["it support", "technician", "help desk", "helpdesk", "desktop support", "service desk", "troubleshoot",
                   "data center", "datacenter", "imaging", "hardware"],
    "healthcare": ["healthcare", "health care", "hospital", "clinic", "medical", "medicare", "health plan", "pharma"],
    "insurance": ["insurance", "medicare", "annuit", "life & health", "benefits"],
    "financial services": ["financial advisor", "financial services", "wealth", "investment"],
    "management": ["team lead", "supervisor", "led a team", "managed a team", "people manager", "managed staff"],
    "writing": ["writer", "content", "copywriting", "editorial"],
}
# Common tools: found by whole-word search in the role text
TOOLS = ["salesforce", "hubspot", "zendesk", "servicenow", "freshdesk", "intercom", "zoho", "dynamics 365", "crm",
         "excel", "microsoft office", "office 365", "microsoft 365", "outlook", "google workspace", "jira",
         "sales navigator", "zoominfo", "outreach.io", "salesloft", "gong", "slack", "microsoft teams", "quickbooks",
         "active directory", "windows", "linux", "aws", "python", "sql"]

# Question wording -> area key
QUESTION_ALIASES = [   # whole words only ("hospitality" must not match "hospital")
    ("customer service", r"\bcustomer[- ]facing\b|\bcustomer (service|support|care|experience)\b|\bclient (service|support)\b|\bcall cent(er|re)s?\b|\bcontact cent(er|re)s?\b|\bhelp ?desk\b|\bguest services?\b|\bmember support\b"),
    ("customer success", r"\bcustomer success\b|\bclient success\b|\baccount onboarding\b"),
    ("account management", r"\baccount manage(ment|r)\b|\bmanaging accounts\b|\bkey accounts?\b"),
    ("b2b sales", r"\bb2b( sales)?\b|\bbusiness[- ]to[- ]business( sales)?\b|\bchannel sales\b|\bvar( sales)?\b"),
    ("sales", r"\binside sales\b|\bsales\b|\bselling\b|\bbusiness development\b|\bsdr\b|\bbdr\b|\blead gen(eration)?\b|\bcold call(ing)?\b|\bquota\b"),
    ("it support", r"\bit support\b|\btechnical support\b|\bdesktop support\b|\btechnician\b|\btroubleshoot(ing)?\b"),
    ("healthcare", r"\bhealth ?care\b|\bmedical\b|\bhospitals?\b|\bclinic(al|s)?\b"),
    ("insurance", r"\binsurance\b|\bmedicare\b|\bbenefits\b"),
    ("financial services", r"\bfinancial (services|advis(or|ory|ing))\b|\bwealth\b|\binvestments?\b"),
    ("management", r"\bmanag(ing|ement) (a )?(team|people|staff)\b|\bpeople management\b|\bsupervis(e|ing|ory|or)\b|\bteam lead\b|\bleadership\b"),
]


def _parse_date(s: str, is_end: bool) -> Optional[Tuple[int, int]]:
    s = s.strip().lower()
    if re.fullmatch(_END, s):
        t = date.today()
        return t.year, t.month
    m = re.fullmatch(rf"{_MON}\s+(\d{{4}})", s)
    if m:
        return int(m.group(2)), MONTHS[m.group(1)[:3]]
    m = re.fullmatch(r"(\d{1,2})/(\d{4})", s)
    if m:
        return int(m.group(2)), max(1, min(12, int(m.group(1))))
    m = re.fullmatch(r"\d{4}", s)
    if m:
        return int(s), (12 if is_end else 1)
    return None


@dataclass
class Role:
    start: Tuple[int, int]
    end: Tuple[int, int]
    text: str
    header: str = ""

    @property
    def months(self) -> int:
        return max(0, (self.end[0] - self.start[0]) * 12 + (self.end[1] - self.start[1]) + 1)


@dataclass
class ExperienceProfile:
    roles: List[Role] = field(default_factory=list)
    areas: Dict[str, float] = field(default_factory=dict)   # key -> years
    tools: Dict[str, float] = field(default_factory=dict)   # key -> years
    total_years: float = 0.0
    skills_only: List[str] = field(default_factory=list)    # listed on resume, no dated role mentions them

    def as_dict(self) -> dict:
        return {
            "total_years": self.total_years,
            "areas": {k: v for k, v in sorted(self.areas.items(), key=lambda kv: -kv[1]) if v > 0},
            "tools": dict(sorted(self.tools.items(), key=lambda kv: -kv[1])),
            "skills_only": self.skills_only,
            "roles": [{"header": r.header[:120], "start": f"{r.start[1]:02d}/{r.start[0]}",
                       "end": f"{r.end[1]:02d}/{r.end[0]}", "months": r.months} for r in self.roles],
        }


def _merged_months(roles: List[Role]) -> int:
    """Total months covered by these roles, counting overlaps once."""
    spans = sorted((r.start[0] * 12 + r.start[1], r.end[0] * 12 + r.end[1]) for r in roles)
    total, cur_s, cur_e = 0, None, None
    for s, e in spans:
        if cur_e is None or s > cur_e + 1:
            if cur_e is not None:
                total += cur_e - cur_s + 1
            cur_s, cur_e = s, e
        else:
            cur_e = max(cur_e, e)
    if cur_e is not None:
        total += cur_e - cur_s + 1
    return total


def years_from_months(months: int) -> int:
    """Nearest whole year (half up); 6-11 months counts as 1 year; under 6 months = 0."""
    if months < 6:
        return 0
    return max(1, int(months / 12 + 0.5))


def _mentions(text: str, word: str) -> bool:
    return re.search(r"(?<![a-z0-9])" + re.escape(word) + r"(?![a-z0-9])", text) is not None


def parse_roles(resume_text: str) -> List[Role]:
    lines = [l.strip() for l in (resume_text or "").splitlines()]
    # Work history only: stop at the education / certifications / references sections
    for i, line in enumerate(lines):
        if re.fullmatch(r"(education|certifications?|licenses?( & certifications)?|references|projects|volunteer.*)\s*:?", line, re.I):
            lines = lines[:i]
            break
    today = (date.today().year, date.today().month)
    marks = []
    for i, line in enumerate(lines):
        m = RANGE_RE.search(line)
        if not m:
            continue
        if re.search(r"expected|university|college|degree|bachelor|b\.s\.|b\.a\.|diploma", line, re.I):
            continue
        start, end = _parse_date(m.group("start"), False), _parse_date(m.group("end"), True)
        if not start or not end or start[0] < 1970 or start > today:
            continue
        end = min(end, today)
        if end < start:
            continue
        marks.append((i, start, end))
    roles = []
    for k, (i, start, end) in enumerate(marks):
        nxt = marks[k + 1][0] if k + 1 < len(marks) else len(lines)
        # header: the date line plus up to 2 non-empty lines just above it (title / company)
        above = [l for l in lines[max(0, i - 2):i] if l]
        header = " | ".join(above + [lines[i]])
        body_end = nxt - 2 if k + 1 < len(marks) else nxt   # stop before the next role's title lines
        body = "\n".join(lines[i + 1:max(i + 1, body_end)])
        roles.append(Role(start=start, end=end, text=(header + "\n" + body).lower(), header=header))
    return roles


def build_profile(resume_text: str) -> ExperienceProfile:
    roles = parse_roles(resume_text)
    prof = ExperienceProfile(roles=roles)
    if not roles:
        return prof
    prof.total_years = years_from_months(_merged_months(roles))
    for area, words in AREAS.items():
        hits = [r for r in roles if any(_mentions(r.text, w) for w in words)]
        prof.areas[area] = years_from_months(_merged_months(hits)) if hits else 0
    for tool in TOOLS:
        hits = [r for r in roles if _mentions(r.text, tool)]
        if hits:
            prof.tools[tool] = years_from_months(_merged_months(hits))
    # tools listed only in a Skills section: "has experience" = yes, years unknown
    whole = (resume_text or "").lower()
    prof.skills_only = sorted(t for t in TOOLS if t not in prof.tools and _mentions(whole, t))
    return prof


# Words that don't change what a question is asking about
FILLER = set("""how many much years year yrs of experience experiences do you have has had with in using use working work
the a an your any at least minimum min prior previous total overall paid direct hands on hands-on professional relevant
related field industry setting environment role roles position positions space sector type similar level based facing
as for on within doing performing providing this or and is are what number please enter including include
software platform platforms tool tools system systems application applications crm program programs suite
""".split())


def _leftover(q: str, start: int, end: int) -> List[str]:
    rest = (q[:start] + " " + q[end:]).lower()
    words = re.findall(r"[a-z0-9+#.]+", rest)
    return [w.strip(".") for w in words if w.strip(".") and w.strip(".") not in FILLER and not w.isdigit()]


def area_for_question(question: str, strict: bool = True) -> Optional[str]:
    """
    Experience area a question asks about, or None.
    strict: the question must be about exactly that area - "years of medical billing"
    is NOT "healthcare", "years of Salesforce administration" is NOT "Salesforce".
    """
    q = (question or "").lower()
    for area, rx in QUESTION_ALIASES:
        m = re.search(rx, q)
        if m and (not strict or not _leftover(q, m.start(), m.end())):
            return area
    return None


def tool_for_question(question: str, strict: bool = True) -> Optional[str]:
    q = (question or "").lower()
    for tool in sorted(TOOLS, key=len, reverse=True):
        m = re.search(r"(?<![a-z0-9])" + re.escape(tool) + r"(?![a-z0-9])", q)
        if m and (not strict or not _leftover(q, m.start(), m.end())):
            return tool
    return None
