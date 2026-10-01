"""
Salary helpers: read the pay a job posts, compare it to the user's range,
and decide what number to give when a form asks for desired salary.

User settings (config["salary"]):
    salary_min                 lowest annual pay you'll accept, e.g. 60000
    salary_max                 top of your target range, e.g. 90000
    salary_target              number to answer "desired salary" with
                               (blank -> middle of min and max, rounded to $1,000)
    skip_if_listed_below_min   true -> skip jobs whose posted TOP pay is below salary_min
    only_listed_salary         true -> LinkedIn search only shows jobs that list pay
                               (uses LinkedIn's salary filter; hides most postings)
"""
import re
from typing import List, Optional, Tuple

HOURS_PER_YEAR = 2080

_NUM = r"\$\s?(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)\s?([kK])?"
_UNIT = r"(?:\s*(?:/|per|an?)\s*(yr|year|annum|annually|hr|hour|hourly))?"
RANGE_RE = re.compile(_NUM + _UNIT + r"\s*(?:-|–|—|to)\s*" + _NUM + _UNIT, re.I)
SINGLE_RE = re.compile(_NUM + _UNIT, re.I)


def _to_number(num: str, k: Optional[str]) -> float:
    v = float(num.replace(",", ""))
    return v * 1000 if k else v


def _annualize(v: float, unit: Optional[str]) -> int:
    unit = (unit or "").lower()
    if unit.startswith("h") or (not unit and v < 300):   # "$25" with no unit is an hourly rate
        return int(round(v * HOURS_PER_YEAR))
    return int(round(v))


def parse_salary_range(text: str) -> Optional[Tuple[int, int]]:
    """'$60K/yr - $75K/yr', '$25/hr - $32/hr', '$60,000 to $80,000' -> (low, high) per year."""
    if not text:
        return None
    m = RANGE_RE.search(text)
    if m:
        lo_n, lo_k, lo_u, hi_n, hi_k, hi_u = m.groups()
        unit = lo_u or hi_u
        lo = _annualize(_to_number(lo_n, lo_k), unit)
        hi = _annualize(_to_number(hi_n, hi_k), unit)
        if 5000 <= lo <= hi <= 2_000_000:
            return lo, hi
    for m in SINGLE_RE.finditer(text):
        n, k, u = m.groups()
        v = _to_number(n, k)
        if not u and not k and v < 1000 and v >= 300:
            continue  # "$500 signing bonus" - not pay
        annual = _annualize(v, u)
        if 15000 <= annual <= 2_000_000:
            return annual, annual
    return None


def _num(v) -> Optional[int]:
    try:
        s = re.sub(r"[^\d.]", "", str(v))
        return int(float(s)) if s else None
    except Exception:
        return None


def salary_settings(config: dict) -> dict:
    s = dict((config or {}).get("salary") or {})
    lo, hi, tgt = _num(s.get("salary_min")), _num(s.get("salary_max")), _num(s.get("salary_target"))
    # backwards compatibility with the old single "expected_salary" answer
    if tgt is None:
        legacy = _num(((config or {}).get("screening_answers") or {}).get("expected_salary"))
        if legacy and not (lo or hi):
            tgt = legacy
    if tgt is None and lo and hi:
        tgt = int(round((lo + hi) / 2 / 1000.0) * 1000)
    if tgt is None:
        tgt = lo or hi
    return {
        "min": lo, "max": hi, "target": tgt,
        "skip_if_listed_below_min": bool(s.get("skip_if_listed_below_min", True)),
        "only_listed_salary": bool(s.get("only_listed_salary", False)),
    }


def below_minimum(posted: Optional[Tuple[int, int]], config: dict) -> bool:
    """True if the job lists pay and even its TOP is under the user's minimum."""
    st = salary_settings(config)
    if not posted or not st["min"] or not st["skip_if_listed_below_min"]:
        return False
    return posted[1] < st["min"]


def answer_for_question(question: str, config: dict) -> Optional[str]:
    """Number to type for a desired-salary question (annual, or hourly if the question says hourly)."""
    st = salary_settings(config)
    if not st["target"]:
        return None
    q = (question or "").lower()
    if re.search(r"hour|hourly|/hr|per hr", q):
        return str(int(round(st["target"] / HOURS_PER_YEAR)))
    return str(st["target"])


# LinkedIn search salary filter (f_SB2): 1=$40K+ 2=$60K+ 3=$80K+ 4=$100K+ 5=$120K+ ... 9=$200K+
_SB2 = [(40000, 1), (60000, 2), (80000, 3), (100000, 4), (120000, 5), (140000, 6), (160000, 7), (180000, 8), (200000, 9)]


def linkedin_salary_filter(config: dict) -> Optional[int]:
    st = salary_settings(config)
    if not st["only_listed_salary"] or not st["min"]:
        return None
    code = None
    for floor, c in _SB2:
        if st["min"] >= floor:
            code = c
    return code


def pick_numeric_option(options: List[str], value: float) -> Optional[str]:
    """
    For dropdowns/radios that offer ranges: '0-1 years', '3-5 years', '5+ years',
    '$50,000 - $70,000', 'More than 10'. Picks the option containing `value`.
    """
    best = None
    for o in options:
        ol = o.lower().replace(",", "")
        if "select" in ol:
            continue
        nums = [float(n) * (1000 if k else 1) for n, k in re.findall(r"(\d+(?:\.\d+)?)\s?(k)?\b", ol)]
        if not nums:
            continue
        if re.search(r"\+|or more|more than|over|above|at least", ol) and len(nums) == 1:
            lo, hi = nums[0], float("inf")
        elif re.search(r"less than|under|below|fewer", ol) and len(nums) == 1:
            lo, hi = float("-inf"), nums[0] - 1e-9
        elif len(nums) >= 2:
            lo, hi = nums[0], nums[1]
        else:
            lo = hi = nums[0]
        if lo <= value <= hi:
            return o
        if lo == hi and best is None and abs(lo - value) < 0.5:
            best = o
    return best
