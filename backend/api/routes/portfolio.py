"""Portfolio + ledger routes (api-contract). Thin adapters over
PortfolioService and the portfolio store; HTTP is a UI adapter (ADR-0050)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.domain.ledger import LedgerError
from backend.services.portfolio_service import PortfolioService
from backend.stores import get_stores

router = APIRouter()


class LotIn(BaseModel):
    ticker: str
    shares: float
    cost_basis: float
    purchase_date: str
    position_type: str | None = None
    note: str | None = None


class SaleIn(BaseModel):
    ticker: str
    shares: float
    price: float
    sale_date: str
    note: str | None = None


class LotCorrectionIn(BaseModel):
    shares: float | None = None
    cost_basis: float | None = None
    purchase_date: str | None = None
    remove: bool = False


@router.get("/portfolio")
async def get_portfolio():
    stores = get_stores()
    svc = PortfolioService(stores)
    return {"holdings": svc.holdings_view(), "totals": stores.portfolio.totals()}


@router.post("/portfolio/lots")
async def add_lot(body: LotIn):
    svc = PortfolioService(get_stores())
    try:
        return svc.add_lot(body.ticker, body.shares, body.cost_basis,
                           body.purchase_date, body.position_type, body.note)
    except LedgerError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


class PositionTypeIn(BaseModel):
    ticker: str
    position_type: str | None = None


@router.post("/portfolio/position-type")
async def set_position_type(body: PositionTypeIn):
    """Portfolio Position Type is user-entered (never auto-assigned)."""
    stores = get_stores()
    stores.portfolio.set_position_type(body.ticker, body.position_type)
    return {"ok": True}


@router.post("/portfolio/sales")
async def record_sale(body: SaleIn):
    svc = PortfolioService(get_stores())
    try:
        return svc.record_sale(body.ticker, body.shares, body.price,
                               body.sale_date, body.note)
    except LedgerError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/portfolio/lots/{lot_id}/correct")
async def correct_lot(lot_id: str, body: LotCorrectionIn):
    from backend.services.portfolio_service import _reject_future_date

    stores = get_stores()
    try:
        if body.purchase_date:
            _reject_future_date(body.purchase_date, "corrected lot purchase")
        if body.remove:
            stores.portfolio.remove_lot_as_correction(lot_id)
        else:
            stores.portfolio.correct_lot(lot_id, shares=body.shares,
                                         cost_basis=body.cost_basis,
                                         purchase_date=body.purchase_date)
    except LedgerError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True}


@router.post("/portfolio/refresh")
async def refresh_portfolio():
    """Portfolio Price and P&L Refresh — price-only, never thesis health."""
    svc = PortfolioService(get_stores())
    updated = await svc.refresh_prices()
    return {"updated": updated}


@router.get("/portfolio/ledger")
async def get_ledger(ticker: str | None = None):
    stores = get_stores()
    return {"lots": stores.portfolio.lots(ticker),
            "sales": stores.portfolio.sales(ticker)}


@router.get("/portfolio/analytics")
async def portfolio_analytics(range: str = "1y"):
    """Benchmark-relative performance, contribution, exposure, risk — all
    projected from the ledger x retained daily bars. Local-only."""
    from backend.services import portfolio_analytics as pa

    if range not in pa.RANGE_DAYS:
        range = "1y"
    return pa.analytics_view(get_stores(), range)
