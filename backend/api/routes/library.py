"""Library routes (api-contract): known-ticker prefix suggestions.

Known Library Tickers are tickers with retained artifacts, portfolio history,
or saved screener work — the Library never suggests arbitrary symbols.
"""

from __future__ import annotations

from fastapi import APIRouter

from backend.stores import get_stores

router = APIRouter()

_MAX_MATCHES = 20


@router.get("/library/suggest")
async def suggest(q: str = ""):
    prefix = q.strip().upper()
    if not prefix:
        return {"matches": []}
    stores = get_stores()
    matches = []
    for ticker in stores.identity.known_tickers():
        if not ticker.startswith(prefix):
            continue
        entity = stores.identity.resolve_ticker(ticker)
        matches.append({"ticker": ticker, "name": entity["name"] if entity else None})
        if len(matches) >= _MAX_MATCHES:
            break
    return {"matches": matches}
