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


_LOC_RX = re.compile(
    r"^(?:[A-Za-z .'\-]+,\s*[A-Z]{2}\b"                       # Portland, OR
    r"|[A-Za-z .'\-]+(?:,\s*[A-Za-z .'\-]+)?,\s*United States"   # Beaverton, Oregon, United States
    r"|United States"                                           # remote, US-wide
    r"|[A-Za-z .'\-]+ Metropolitan Area"                        # Portland, Oregon Metropolitan Area
    r"|Remote)"
    r"(?:\s*\((?:On-?site|Hybrid|Remote)\))?$", re.I)


def find_location(text: str) -> Optional[str]:
    """
    First thing that looks like a job location in a block of LinkedIn text
    (a job card or the job page's top card). Lines are also split on the " · "
    separators LinkedIn uses ("Portland, OR · 2 days ago · 40 applicants").
    """
    for line in (text or "").splitlines():
        for seg in line.split("\u00b7"):
            seg = " ".join(seg.split()).strip()
            if not seg or len(seg) > 80:
                continue
            if _LOC_RX.match(seg):
                if seg.lower() == "remote" or seg.lower().startswith("united states") or seg.endswith(")") \
                        or states_in(seg) or "metropolitan" in seg.lower():
                    return seg
    return None


def parse_card_text(text: str) -> dict:
    """
    Title / company / location from a job card's visible text, e.g.
    "Sales Rep\nSales Rep with verification\nGrimco, Inc.\nPortland, OR (On-site)\n$55K/yr\nEasy Apply".
    """
    lines = [" ".join(l.split()) for l in (text or "").splitlines() if l.strip()]
    out = {"title": None, "company": None, "location": find_location(text or "")}
    if not lines:
        return out
    out["title"] = lines[0]
    t = lines[0].lower()
    for l in lines[1:]:
        low = l.lower()
        if low == t or low.startswith(t) or "verification" in low or l == out["location"]:
            continue
        if find_location(l):
            break
        out["company"] = l
        break
    return out
