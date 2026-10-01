"""
Location helpers for the search plan and the "outside my area" check.
"""
import re
from typing import List, Optional, Set

STATES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California", "CO": "Colorado",
    "CT": "Connecticut", "DE": "Delaware", "DC": "District of Columbia", "FL": "Florida", "GA": "Georgia",
    "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
    "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland", "MA": "Massachusetts",
    "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi", "MO": "Missouri", "MT": "Montana",
    "NE": "Nebraska", "NV": "Nevada", "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico",
    "NY": "New York", "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma",
    "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina", "SD": "South Dakota",
    "TN": "Tennessee", "TX": "Texas", "UT": "Utah", "VT": "Vermont", "VA": "Virginia", "WA": "Washington",
    "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming",
}
NAME_TO_CODE = {v.lower(): k for k, v in STATES.items()}
REMOTE_WORDS = ("remote", "anywhere", "united states", "usa", "us", "u.s.", "nationwide", "remote (us)")


def is_remote_location(loc: str) -> bool:
    return (loc or "").strip().lower() in REMOTE_WORDS


def states_in(text: str) -> Set[str]:
    """US state codes mentioned in a location string: 'Portland, OR' / 'Beaverton, Oregon, United States'."""
    t = text or ""
    found = set()
    for m in re.finditer(r",\s*([A-Z]{2})\b", t):
        if m.group(1) in STATES:
            found.add(m.group(1))
    low = t.lower()
    for name, code in NAME_TO_CODE.items():
        if re.search(r"(?<![a-z])" + re.escape(name) + r"(?![a-z])", low):
            # "Washington" in "Washington, DC" is DC, not WA
            if code == "WA" and re.search(r"washington,?\s*d\.?c", low):
                continue
            found.add(code)
    return found


def home_states(locations: List[str]) -> Set[str]:
    out = set()
    for loc in locations or []:
        if not is_remote_location(loc):
            out |= states_in(loc)
    return out


def workplace_type(text: str) -> Optional[str]:
    t = (text or "").lower()
    if "hybrid" in t:
        return "hybrid"
    if "on-site" in t or "onsite" in t or "on site" in t:
        return "onsite"
    if "remote" in t:
        return "remote"
    return None


def outside_area(job_location: str, page_text: str, allowed_states: Set[str]) -> Optional[str]:
    """
    Reason string if this is an on-site/hybrid job in a state the user didn't pick, else None.
    Remote jobs and jobs whose state can't be read are never skipped here.
    """
    if not allowed_states:
        return None
    wtype = workplace_type(job_location) or workplace_type(page_text[:600] if page_text else "")
    if wtype == "remote":
        return None
    st = states_in(job_location)
    if not st or st & allowed_states:
        return None
    return f"Outside your area ({', '.join(sorted(st))}, {wtype or 'not remote'})"
