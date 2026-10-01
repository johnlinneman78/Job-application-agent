"""
Skill matching shared by the ranker, the dashboard badges and the recruiter pitch.

Why this exists: the old ranker matched a developer-only word list as raw
substrings, so "capital" matched "api", "digital" matched "git", "interest"
matched "rest" and "good" matched "go". Sales jobs got badges like
"Api, Git, Rest" and real matches (Salesforce, HubSpot, CRM) were ignored.

Rules here:
- whole-word / whole-phrase matching only
- vocabulary = skills from the resume + a sales / customer success / IT list
- each skill has a display name with correct casing (CRM, not Crm)
- skills are ordered by how specific they are, not alphabetically
"""
import re
from typing import Dict, Iterable, List

# canonical key -> (display name, aliases)
SKILL_VOCAB: Dict[str, tuple] = {
    # CRM / sales tools
    "salesforce": ("Salesforce", ["salesforce", "sfdc"]),
    "hubspot": ("HubSpot", ["hubspot"]),
    "crm": ("CRM", ["crm"]),
    "zoominfo": ("ZoomInfo", ["zoominfo"]),
    "outreach": ("Outreach.io", ["outreach.io"]),
    "salesloft": ("Salesloft", ["salesloft"]),
    "linkedin sales navigator": ("LinkedIn Sales Navigator", ["sales navigator"]),
    "gong": ("Gong", ["gong.io"]),
    # sales motions
    "account management": ("account management", ["account management", "account manager", "managing accounts"]),
    "consultative selling": ("consultative selling", ["consultative selling", "consultative sales", "solution selling", "solutions selling"]),
    "pipeline management": ("pipeline management", ["pipeline management", "manage pipeline", "manage your pipeline", "pipeline generation"]),
    "prospecting": ("prospecting", ["prospecting", "prospect new", "outbound prospecting"]),
    "lead qualification": ("lead qualification", ["lead qualification", "qualify leads", "qualifying leads"]),
    "cold calling": ("cold calling", ["cold calling", "cold call"]),
    "closing": ("closing deals", ["close deals", "closing deals", "closing business"]),
    "negotiation": ("negotiation", ["negotiation", "negotiating"]),
    "quota": ("quota attainment", ["quota attainment", "exceed quota", "meet quota", "quota"]),
    "b2b sales": ("B2B sales", ["b2b sales", "b2b"]),
    "saas": ("SaaS", ["saas"]),
    "channel sales": ("channel sales", ["channel sales", "channel partners", "var", "value added reseller"]),
    "customer success": ("customer success", ["customer success"]),
    "client relationships": ("client relationships", ["client relationships", "relationship building", "relationship management"]),
    "renewals": ("renewals & upsell", ["renewals", "upsell", "upselling", "cross-sell", "expansion revenue"]),
    "product demos": ("product demos", ["product demo", "product demonstrations", "demos"]),
    "customer service": ("customer service", ["customer service", "customer support"]),
    "insurance": ("insurance", ["insurance"]),
    "medicare": ("Medicare", ["medicare"]),
    # IT
    "it support": ("IT support", ["it support", "help desk", "helpdesk", "service desk", "desktop support"]),
    "data center": ("data center operations", ["data center", "datacenter"]),
    "networking": ("networking", ["networking", "tcp/ip", "lan/wan"]),
    "windows": ("Windows", ["windows 10", "windows 11", "windows server", "microsoft windows"]),
    "linux": ("Linux", ["linux"]),
    "active directory": ("Active Directory", ["active directory"]),
    "microsoft 365": ("Microsoft 365", ["microsoft 365", "office 365", "o365"]),
    "ticketing": ("ticketing systems", ["ticketing", "servicenow", "zendesk", "jira service"]),
    "aws": ("AWS", ["aws", "amazon web services"]),
    "azure": ("Azure", ["azure"]),
    "excel": ("Excel", ["excel"]),
    # tech (only whole words, so "capital"/"digital" no longer match)
    "python": ("Python", ["python"]),
    "javascript": ("JavaScript", ["javascript"]),
    "sql": ("SQL", ["sql"]),
    "api": ("APIs", ["api", "apis", "rest api"]),
}

# Higher = mentioned first in the pitch (tools/specific motions beat generic words)
SPECIFICITY = {
    "salesforce": 9, "hubspot": 9, "zoominfo": 8, "linkedin sales navigator": 8, "outreach": 8, "salesloft": 8, "gong": 8,
    "account management": 8, "consultative selling": 8, "channel sales": 8, "customer success": 7, "renewals": 7,
    "pipeline management": 7, "b2b sales": 7, "saas": 7, "medicare": 7, "insurance": 6, "it support": 7, "data center": 7,
    "crm": 6, "prospecting": 6, "lead qualification": 6, "closing": 6, "quota": 5, "negotiation": 5,
    "client relationships": 5, "product demos": 5, "customer service": 4, "cold calling": 4,
}


def _pattern(alias: str) -> re.Pattern:
    return re.compile(r"(?<![a-z0-9])" + re.escape(alias.lower()) + r"(?![a-z0-9])")


_ALIAS_PATTERNS = {key: [_pattern(a) for a in aliases] for key, (_, aliases) in SKILL_VOCAB.items()}


def _key_for(skill: str) -> str:
    """Map any resume skill string to a canonical key (or itself)."""
    s = skill.strip().lower()
    for key, (display, aliases) in SKILL_VOCAB.items():
        if s == key or s == display.lower() or s in aliases:
            return key
    return s


def display_name(key: str) -> str:
    if key in SKILL_VOCAB:
        return SKILL_VOCAB[key][0]
    # keep acronyms upper-case, otherwise leave as written in the resume
    return key.upper() if len(key) <= 4 and key.isalpha() else key


def find_skills(text: str, extra_skills: Iterable[str] = ()) -> List[str]:
    """Canonical skill keys mentioned in `text` (whole words only)."""
    t = (text or "").lower()
    found = []
    for key, pats in _ALIAS_PATTERNS.items():
        if any(p.search(t) for p in pats):
            found.append(key)
    for s in extra_skills:
        k = _key_for(s)
        if k and k not in found and len(k) > 2 and _pattern(k).search(t):
            found.append(k)
    return found


def matched_skills(resume_skills: Iterable[str], job_text: str, limit: int = 6) -> List[str]:
    """Display names of skills that appear in BOTH the resume and the job text, most specific first."""
    resume_keys = {_key_for(s) for s in resume_skills if s}
    job_keys = set(find_skills(job_text, extra_skills=resume_skills))
    both = resume_keys & job_keys
    ordered = sorted(both, key=lambda k: (-SPECIFICITY.get(k, 3), k))
    return [display_name(k) for k in ordered[:limit]]


def skill_score(resume_skills: Iterable[str], job_text: str) -> float:
    """0..1 share of the job's recognised skills that the resume also has. 0.5 if none recognised."""
    resume_keys = {_key_for(s) for s in resume_skills if s}
    job_keys = set(find_skills(job_text, extra_skills=resume_skills))
    if not job_keys:
        return 0.5
    return min(len(resume_keys & job_keys) / len(job_keys), 1.0)
