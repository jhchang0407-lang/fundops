"""Quality composite scores computed from SEC XBRL data.

All inputs are raw financial statement dicts from statements.py.
No precomputed data from yfinance/FMP. Pure math on XBRL.
"""

from __future__ import annotations
from backend.core.utils import safe_float


def piotroski_f_score(
    inc_current: dict,
    inc_prior: dict,
    bs_current: dict,
    bs_prior: dict,
    cf_current: dict,
) -> int:
    """Piotroski F-Score: 9-point financial strength indicator.

    Profitability (4 points):
      1. Positive net income
      2. Positive operating cash flow
      3. ROA improving (current > prior)
      4. Cash flow > net income (accrual quality)

    Leverage/Liquidity (3 points):
      5. Debt ratio decreasing (total debt / total assets)
      6. Current ratio improving
      7. No new share dilution (shares outstanding not increased)

    Operating Efficiency (2 points):
      8. Gross margin improving
      9. Asset turnover improving (revenue / total assets)

    Returns: 0-9 score. >7 = strong, <3 = weak.
    """
    score = 0

    # Current year values
    ni = safe_float(inc_current.get("netIncome", 0))
    ocf = safe_float(cf_current.get("operatingCashFlow", 0))
    revenue = safe_float(inc_current.get("revenue", 0))
    gross_profit = safe_float(inc_current.get("grossProfit", 0))
    total_assets = safe_float(bs_current.get("totalAssets", 0))
    total_debt = safe_float(bs_current.get("totalDebt", 0))
    current_assets = safe_float(bs_current.get("totalCurrentAssets", 0))
    current_liabs = safe_float(bs_current.get("totalCurrentLiabilities", 0))
    shares = safe_float(inc_current.get("weightedAverageShsOutDil", 0))

    # Prior year values
    ni_prior = safe_float(inc_prior.get("netIncome", 0))
    revenue_prior = safe_float(inc_prior.get("revenue", 0))
    gross_profit_prior = safe_float(inc_prior.get("grossProfit", 0))
    total_assets_prior = safe_float(bs_prior.get("totalAssets", 0))
    total_debt_prior = safe_float(bs_prior.get("totalDebt", 0))
    current_assets_prior = safe_float(bs_prior.get("totalCurrentAssets", 0))
    current_liabs_prior = safe_float(bs_prior.get("totalCurrentLiabilities", 0))
    shares_prior = safe_float(inc_prior.get("weightedAverageShsOutDil", 0))

    # 1. Positive net income
    if ni > 0:
        score += 1

    # 2. Positive operating cash flow
    if ocf > 0:
        score += 1

    # 3. ROA improving
    roa = ni / total_assets if total_assets > 0 else 0
    roa_prior = ni_prior / total_assets_prior if total_assets_prior > 0 else 0
    if roa > roa_prior:
        score += 1

    # 4. Accrual quality: OCF > net income
    if ocf > ni:
        score += 1

    # 5. Debt ratio decreasing
    debt_ratio = total_debt / total_assets if total_assets > 0 else 0
    debt_ratio_prior = total_debt_prior / total_assets_prior if total_assets_prior > 0 else 0
    if debt_ratio < debt_ratio_prior:
        score += 1

    # 6. Current ratio improving
    cr = current_assets / current_liabs if current_liabs > 0 else 0
    cr_prior = current_assets_prior / current_liabs_prior if current_liabs_prior > 0 else 0
    if cr > cr_prior:
        score += 1

    # 7. No dilution
    if shares <= shares_prior or shares_prior == 0:
        score += 1

    # 8. Gross margin improving
    gm = gross_profit / revenue if revenue > 0 else 0
    gm_prior = gross_profit_prior / revenue_prior if revenue_prior > 0 else 0
    if gm > gm_prior:
        score += 1

    # 9. Asset turnover improving
    at = revenue / total_assets if total_assets > 0 else 0
    at_prior = revenue_prior / total_assets_prior if total_assets_prior > 0 else 0
    if at > at_prior:
        score += 1

    return score


def altman_z_score(inc: dict, bs: dict) -> float | None:
    """Altman Z-Score: bankruptcy risk predictor.

    Z = 1.2*A + 1.4*B + 3.3*C + 0.6*D + 1.0*E

    Where:
      A = Working Capital / Total Assets
      B = Retained Earnings / Total Assets
      C = EBIT / Total Assets
      D = Market Cap / Total Liabilities (we use book equity as proxy)
      E = Revenue / Total Assets

    >2.99 = safe zone, 1.81-2.99 = grey zone, <1.81 = distress zone.
    Returns None if insufficient data.
    """
    total_assets = safe_float(bs.get("totalAssets", 0))
    if total_assets <= 0:
        return None

    working_capital = (
        safe_float(bs.get("totalCurrentAssets", 0))
        - safe_float(bs.get("totalCurrentLiabilities", 0))
    )
    retained_earnings = safe_float(bs.get("retainedEarnings", 0))
    ebit = safe_float(inc.get("operatingIncome", 0))
    equity = safe_float(bs.get("totalStockholdersEquity", 0))
    total_liabs = safe_float(bs.get("totalLiabilities", 0))
    revenue = safe_float(inc.get("revenue", 0))

    a = working_capital / total_assets
    b = retained_earnings / total_assets
    c = ebit / total_assets
    d = equity / total_liabs if total_liabs > 0 else 10  # Very low debt = safe
    e = revenue / total_assets

    z = 1.2 * a + 1.4 * b + 3.3 * c + 0.6 * d + 1.0 * e
    return round(z, 2)


def compute_quality_scores(
    income_statements: list[dict],
    balance_sheets: list[dict],
    cash_flows: list[dict],
) -> dict:
    """Compute all quality scores from SEC financial data.

    Returns dict with:
      piotroski: 0-9
      altman_z: float
      quality_composite: 0-10 (our own composite)
    """
    result = {
        "piotroski": None,
        "altman_z": None,
        "quality_composite": None,
    }

    if len(income_statements) < 2 or len(balance_sheets) < 2 or len(cash_flows) < 1:
        return result

    inc_current = income_statements[0]
    inc_prior = income_statements[1]
    bs_current = balance_sheets[0]
    bs_prior = balance_sheets[1]
    cf_current = cash_flows[0]

    # Piotroski F-Score
    result["piotroski"] = piotroski_f_score(
        inc_current, inc_prior, bs_current, bs_prior, cf_current
    )

    # Altman Z-Score
    result["altman_z"] = altman_z_score(inc_current, bs_current)

    # Quality composite (0-10): margins + returns + cash quality + leverage
    revenue = safe_float(inc_current.get("revenue", 0))
    gross_profit = safe_float(inc_current.get("grossProfit", 0))
    op_income = safe_float(inc_current.get("operatingIncome", 0))
    net_income = safe_float(inc_current.get("netIncome", 0))
    ocf = safe_float(cf_current.get("operatingCashFlow", 0))
    fcf = safe_float(cf_current.get("freeCashFlow", 0))
    total_assets = safe_float(bs_current.get("totalAssets", 0))
    equity = safe_float(bs_current.get("totalStockholdersEquity", 0))
    total_debt = safe_float(bs_current.get("totalDebt", 0))

    gm = gross_profit / revenue if revenue > 0 else 0
    om = op_income / revenue if revenue > 0 else 0
    roic_proxy = op_income / (equity + total_debt) if (equity + total_debt) > 0 else 0
    fcf_conv = fcf / net_income if net_income > 0 else 0
    de = total_debt / equity if equity > 0 else 10

    # Score components (each 0-2.5, total 0-10)
    margin_score = min(gm * 2.5 + om * 2.5, 2.5)  # High margins
    return_score = min(roic_proxy * 10, 2.5)  # High ROIC
    cash_score = min(fcf_conv * 1.5, 2.5) if fcf_conv > 0 else 0  # Good cash conversion
    leverage_score = max(0, 2.5 - de * 0.5)  # Low leverage

    result["quality_composite"] = round(
        margin_score + return_score + cash_score + leverage_score, 1
    )

    return result
