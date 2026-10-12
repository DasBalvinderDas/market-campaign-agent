"""Dates the way people say them: "31st Oct", "31 October 2026", "Oct 31", "31/10", "2026-10-31"."""
import re
from datetime import date

_MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


def parse_date(text: str, today: date | None = None) -> date | None:
    """A date from free text. Without a year it is the next time that day comes round. None if it is not a date."""
    today = today or date.today()
    t = (text or "").strip().lower()
    if not t:
        return None
    m = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", t)
    if m:
        return _make(int(m[1]), int(m[2]), int(m[3]))
    t = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", t)
    day = month = year = None
    m = re.search(r"\b(\d{1,2})\s*(?:of\s+)?([a-z]{3,9})\b(?:,?\s*(\d{4}))?", t)
    if m and m[2][:3] in _MONTHS:
        day, month, year = int(m[1]), _MONTHS[m[2][:3]], int(m[3]) if m[3] else None
    else:
        m = re.search(r"\b([a-z]{3,9})\s+(\d{1,2})\b(?:,?\s*(\d{4}))?", t)
        if m and m[1][:3] in _MONTHS:
            day, month, year = int(m[2]), _MONTHS[m[1][:3]], int(m[3]) if m[3] else None
        else:
            m = re.fullmatch(r"(\d{1,2})[/.-](\d{1,2})(?:[/.-](\d{2,4}))?", t)
            if not m:
                return None
            day, month = int(m[1]), int(m[2])
            year = (int(m[3]) + 2000 if m[3] and len(m[3]) == 2 else int(m[3])) if m[3] else None
    if year:
        return _make(year, month, day)
    d = _make(today.year, month, day)
    if d and d <= today:
        d = _make(today.year + 1, month, day)
    return d


def _make(y, m, d):
    try:
        return date(y, m, d)
    except ValueError:
        return None
