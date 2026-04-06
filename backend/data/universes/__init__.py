"""Stock universe presets.

Bundled ticker lists for screener. Users pick a preset or paste their own list.
Presets are updated with each app release.
"""

import re
from pathlib import Path

_DIR = Path(__file__).parent

PRESETS = {
    "starter_30": {
        "label": "Starter (30 stocks)",
        "description": "Top 30 US large caps. Quick screen for testing.",
        "file": "starter_30.txt",
        "count": 30,
    },
    "nasdaq100": {
        "label": "Nasdaq 100",
        "description": "100 largest non-financial Nasdaq stocks. Tech-heavy.",
        "file": "nasdaq100.txt",
        "count": 101,
    },
    "us_largecap_200": {
        "label": "US Large Cap 200",
        "description": "Top ~200 US stocks by market cap across all sectors.",
        "file": "us_largecap_200.txt",
        "count": 207,
    },
    "sp500": {
        "label": "S&P 500",
        "description": "Full S&P 500 index. ~500 stocks, takes 2-5 min to screen.",
        "file": "sp500.txt",
        "count": 503,
    },
    "sp500_nasdaq100": {
        "label": "S&P 500 + Nasdaq 100",
        "description": "Combined S&P 500 and Nasdaq 100. ~517 unique stocks.",
        "file": "sp500_nasdaq100.txt",
        "count": 517,
    },
    "russell2000": {
        "label": "Russell 2000 (Small Cap)",
        "description": "Russell 2000 small-cap index. ~1900 stocks, takes 5-10 min to screen.",
        "file": "russell2000.txt",
        "count": 1906,
    },
}


# Aliases: handle common name variations the LLM might generate
_ALIASES = {
    "nasdaq_100": "nasdaq100",
    "nasdaq-100": "nasdaq100",
    "ndx100": "nasdaq100",
    "sp_500": "sp500",
    "s&p500": "sp500",
    "s&p_500": "sp500",
    "largecap_200": "us_largecap_200",
    "large_cap_200": "us_largecap_200",
    "sp500_plus_nasdaq100": "sp500_nasdaq100",
    "sp500+nasdaq100": "sp500_nasdaq100",
    "s&p500_nasdaq100": "sp500_nasdaq100",
    "sp500_ndx100": "sp500_nasdaq100",
    "sp500_plus_nasdaq_100": "sp500_nasdaq100",
    # Russell aliases
    "russell_2000": "russell2000",
    "russell-2000": "russell2000",
    "iwm": "russell2000",
    "rut": "russell2000",
}


def load_preset(name: str) -> list[str]:
    """Load ticker list from a bundled preset file."""
    resolved = _ALIASES.get(name.lower(), name)
    preset = PRESETS.get(resolved)
    if not preset:
        available = list(PRESETS.keys())
        raise ValueError(f"Unknown preset: {name}. Available: {available}")
    path = _DIR / preset["file"]
    return [line.strip() for line in path.read_text().splitlines() if line.strip()]


async def load_preset_async(name: str) -> list[str]:
    """Async version of load_preset (same behavior, kept for API compat)."""
    return load_preset(name)


def load_custom(tickers_text) -> list[str]:
    """Parse a user-provided ticker list (comma, newline, or space separated).

    Accepts string or list — AI conversation may store either format.
    """
    if isinstance(tickers_text, list):
        raw = tickers_text
    elif isinstance(tickers_text, str):
        raw = re.split(r'[,\n\s\t]+', tickers_text.strip())
    else:
        return []
    # Validate: 1-6 uppercase letters
    valid = []
    for t in raw:
        t = t.strip().upper()
        if t and re.match(r'^[A-Z]{1,6}$', t):
            valid.append(t)
    return list(dict.fromkeys(valid))  # dedupe preserving order


def list_presets() -> list[dict]:
    """Return preset metadata for the Settings UI."""
    return [
        {"id": k, "label": v["label"], "description": v["description"], "count": v["count"]}
        for k, v in PRESETS.items()
    ]
