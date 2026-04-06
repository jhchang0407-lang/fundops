"""FundOps Shared Utilities — deduplicated helpers used across agents.

These were originally duplicated in scout_screener.py, val_analyzer.py, etc.
Now shared via a single import.
"""

import json
import requests
import time
from pathlib import Path
from typing import Any, Optional


def safe_float(val: Any, default: float = 0.0) -> float:
    """Safely convert a value to float, returning default on failure."""
    if val is None:
        return default
    try:
        f = float(val)
        if f != f:  # NaN check
            return default
        return f
    except (ValueError, TypeError):
        return default


def safe_int(val: Any, default: int = 0) -> int:
    """Safely convert a value to int."""
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return default


def valid(val: Any) -> bool:
    """Check if a value is non-None, non-zero, and not NaN."""
    if val is None:
        return False
    try:
        f = float(val)
        return f != 0 and f == f  # not zero and not NaN
    except (ValueError, TypeError):
        return bool(val)


def clamp(val: float, lo: float, hi: float) -> float:
    """Clamp a value between lo and hi."""
    return max(lo, min(hi, val))


def clean_text(val: Any) -> str:
    """Clean and normalize text values."""
    if val is None:
        return ""
    return str(val).strip().lower().replace("-", "_")


def first_nonempty(*args) -> str:
    """Return the first non-empty string argument."""
    for a in args:
        if a and str(a).strip():
            return str(a).strip()
    return ""


def fetch_json(url: str, timeout: int = 15, retries: int = 3,
               delay: float = 1.0, session: requests.Session = None) -> Optional[dict]:
    """Fetch JSON from a URL with retry logic.

    Args:
        url: URL to fetch
        timeout: Request timeout in seconds
        retries: Number of retry attempts
        delay: Base delay between retries (exponential backoff)
        session: Optional requests.Session for connection pooling
    """
    requester = session or requests
    for attempt in range(retries):
        try:
            resp = requester.get(url, timeout=timeout)
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code == 429:  # Rate limited
                wait = delay * (4 ** attempt)
                time.sleep(wait)
                continue
            return None
        except (requests.RequestException, json.JSONDecodeError):
            if attempt < retries - 1:
                time.sleep(delay * (2 ** attempt))
    return None


def load_json(path: Path | str) -> Optional[dict]:
    """Load a JSON file safely."""
    path = Path(path)
    if not path.exists():
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return None


def save_json(data: Any, path: Path | str, indent: int = 2) -> None:
    """Save data as JSON file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=indent, default=str)


def fmt_pct(val: Any, decimals: int = 1) -> str:
    """Format a number as percentage string."""
    f = safe_float(val)
    return f"{f:.{decimals}f}%"


def fmt_money(val: Any, decimals: int = 0) -> str:
    """Format a number as money string."""
    f = safe_float(val)
    if abs(f) >= 1_000_000_000:
        return f"${f/1e9:.1f}B"
    if abs(f) >= 1_000_000:
        return f"${f/1e6:.1f}M"
    if abs(f) >= 1_000:
        return f"${f/1e3:.1f}K"
    return f"${f:,.{decimals}f}"


# ---------------------------------------------------------------------------
# Data freshness
# ---------------------------------------------------------------------------

def check_data_freshness(
    data: dict,
    max_age_days: int = 90,
) -> dict:
    """Check if financial data is stale based on filing/reporting dates.

    Looks for date fields commonly found in SEC filings and FMP data:
    - latestFilingDate, fillingDate, acceptedDate, date, reportDate, fiscalDateEnding

    Returns:
        {"fresh": bool, "age_days": int | None, "warning": str | None}
    """
    from datetime import datetime, date as dt_date

    date_keys = [
        "latestFilingDate", "fillingDate", "acceptedDate",
        "date", "reportDate", "fiscalDateEnding",
    ]

    newest_date = None

    def _try_parse(val):
        if isinstance(val, (datetime, dt_date)):
            return val if isinstance(val, dt_date) else val.date()
        if not isinstance(val, str) or not val:
            return None
        for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
            try:
                return datetime.strptime(val[:19], fmt).date()
            except ValueError:
                continue
        return None

    # Check top-level dict
    for key in date_keys:
        parsed = _try_parse(data.get(key))
        if parsed and (newest_date is None or parsed > newest_date):
            newest_date = parsed

    # Check nested lists (e.g., financials_annual: [{date: "2024-01-01"}, ...])
    for key in ("financials_annual", "financials_quarterly", "ratios"):
        items = data.get(key)
        if isinstance(items, list):
            for item in items[:4]:  # check recent entries only
                if isinstance(item, dict):
                    for dk in date_keys:
                        parsed = _try_parse(item.get(dk))
                        if parsed and (newest_date is None or parsed > newest_date):
                            newest_date = parsed

    if newest_date is None:
        return {"fresh": True, "age_days": None, "warning": None}

    age_days = (dt_date.today() - newest_date).days
    fresh = age_days <= max_age_days

    warning = None
    if not fresh:
        warning = (
            f"Data may be stale: most recent filing date is {newest_date.isoformat()} "
            f"({age_days} days ago, threshold: {max_age_days} days)"
        )

    return {"fresh": fresh, "age_days": age_days, "warning": warning}
