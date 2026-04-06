"""XBRL tag priority mapping — resolves which tags to use for each line item.

For each financial concept, we try tags in priority order. The first tag found
in a company's XBRL data wins. This handles the fact that different companies
use different GAAP tags for the same concept.
"""

# ── Income Statement ─────────────────────────────────────────────────────────

REVENUE = [
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "Revenues",
    "SalesRevenueNet",
    "RevenueFromContractWithCustomerIncludingAssessedTax",
    "SalesRevenueGoodsNet",
    "SalesRevenueServicesNet",
    "InterestAndDividendIncomeOperating",  # banks fallback
]

COST_OF_REVENUE = [
    "CostOfGoodsAndServicesSold",
    "CostOfRevenue",
    "CostOfGoodsSold",
    "CostOfServices",
]

GROSS_PROFIT = [
    "GrossProfit",
]

RESEARCH_AND_DEVELOPMENT = [
    "ResearchAndDevelopmentExpense",
]

SGA = [
    "SellingGeneralAndAdministrativeExpense",
]

OPERATING_EXPENSES = [
    "OperatingExpenses",
    "CostsAndExpenses",
]

OPERATING_INCOME = [
    "OperatingIncomeLoss",
]

INTEREST_EXPENSE = [
    "InterestExpense",
    "InterestExpenseDebt",
]

INTEREST_INCOME = [
    "InterestIncomeOther",
    "InvestmentIncomeInterest",
    "InterestAndDividendIncomeOperating",
]

INCOME_BEFORE_TAX = [
    "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
    "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
]

INCOME_TAX = [
    "IncomeTaxExpenseBenefit",
]

NET_INCOME = [
    "NetIncomeLoss",
]

EPS_DILUTED = [
    "EarningsPerShareDiluted",
]

EPS_BASIC = [
    "EarningsPerShareBasic",
]

SHARES_DILUTED = [
    "WeightedAverageNumberOfDilutedSharesOutstanding",
]

SHARES_BASIC = [
    "WeightedAverageNumberOfShareOutstandingBasicAndDiluted",
    "WeightedAverageNumberOfSharesOutstandingBasic",
]

DEPRECIATION_AMORTIZATION = [
    "DepreciationDepletionAndAmortization",
    "DepreciationAndAmortization",
    "Depreciation",
]

EBITDA = [
    "EBITDA",  # rarely tagged directly
]

# ── Balance Sheet ─────────────────────────────────────────────────────────────

CASH = [
    "CashAndCashEquivalentsAtCarryingValue",
    "CashCashEquivalentsAndShortTermInvestments",
    "Cash",
]

SHORT_TERM_INVESTMENTS = [
    "ShortTermInvestments",
    "AvailableForSaleSecuritiesDebtSecuritiesCurrent",
    "MarketableSecuritiesCurrent",
]

ACCOUNTS_RECEIVABLE = [
    "AccountsReceivableNetCurrent",
    "AccountsReceivableNet",
    "ReceivablesNetCurrent",
]

INVENTORY = [
    "InventoryNet",
    "InventoryFinishedGoods",
]

TOTAL_CURRENT_ASSETS = [
    "AssetsCurrent",
]

PP_AND_E = [
    "PropertyPlantAndEquipmentNet",
]

GOODWILL = [
    "Goodwill",
]

INTANGIBLE_ASSETS = [
    "IntangibleAssetsNetExcludingGoodwill",
    "FiniteLivedIntangibleAssetsNet",
]

TOTAL_ASSETS = [
    "Assets",
]

ACCOUNTS_PAYABLE = [
    "AccountsPayableCurrent",
    "AccountsPayableAndAccruedLiabilitiesCurrent",
]

SHORT_TERM_DEBT = [
    "ShortTermBorrowings",
    "CommercialPaper",
    "ShortTermDebtWeightedAverageInterestRateOverTime",
]

CURRENT_LONG_TERM_DEBT = [
    "LongTermDebtCurrent",
    "LongTermDebtAndCapitalLeaseObligationsCurrent",
]

TOTAL_CURRENT_LIABILITIES = [
    "LiabilitiesCurrent",
]

LONG_TERM_DEBT = [
    "LongTermDebtNoncurrent",
    "LongTermDebt",
    "LongTermDebtAndCapitalLeaseObligations",
]

TOTAL_LIABILITIES = [
    "Liabilities",
]

TOTAL_EQUITY = [
    "StockholdersEquity",
    "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
]

RETAINED_EARNINGS = [
    "RetainedEarningsAccumulatedDeficit",
]

TOTAL_DEBT = [
    "DebtLongTermAndShortTermCombinedAmount",  # rarely tagged
]

DEFERRED_REVENUE = [
    "ContractWithCustomerLiability",
    "DeferredRevenueCurrent",
    "ContractWithCustomerLiabilityCurrent",
    "DeferredRevenue",
]

# ── Cash Flow Statement ──────────────────────────────────────────────────────

OPERATING_CASH_FLOW = [
    "NetCashProvidedByUsedInOperatingActivities",
]

CAPITAL_EXPENDITURE = [
    "PaymentsToAcquirePropertyPlantAndEquipment",
    "PaymentsToAcquireProductiveAssets",
]

ACQUISITIONS = [
    "PaymentsToAcquireBusinessesNetOfCashAcquired",
    "PaymentsToAcquireBusinessesGross",
]

INVESTING_CASH_FLOW = [
    "NetCashProvidedByUsedInInvestingActivities",
]

DIVIDENDS_PAID = [
    "PaymentsOfDividendsCommonStock",
    "PaymentsOfDividends",
]

SHARE_REPURCHASES = [
    "PaymentsForRepurchaseOfCommonStock",
    "PaymentsForRepurchaseOfEquity",
]

DEBT_REPAYMENT = [
    "RepaymentsOfLongTermDebt",
    "RepaymentsOfDebt",
]

DEBT_ISSUANCE = [
    "ProceedsFromIssuanceOfLongTermDebt",
    "ProceedsFromDebtNetOfIssuanceCosts",
]

FINANCING_CASH_FLOW = [
    "NetCashProvidedByUsedInFinancingActivities",
]

STOCK_BASED_COMPENSATION = [
    "ShareBasedCompensation",
    "AllocatedShareBasedCompensationExpense",
]

CHANGE_IN_WORKING_CAPITAL = [
    "IncreaseDecreaseInOperatingCapital",
    "IncreaseDecreaseInOtherOperatingCapital",
]

DEFERRED_REVENUE_NONCURRENT = [
    "ContractWithCustomerLiabilityNoncurrent",
    "DeferredRevenueNoncurrent",
]

# ── Bank-Specific Income Statement ───────────────────────────────────────────

NET_INTEREST_INCOME = [
    "InterestIncomeExpenseNet",
]

INTEREST_INCOME_OPERATING = [
    "InterestIncomeOperating",
    "InterestAndDividendIncomeOperating",
    "InterestAndFeeIncomeLoansAndLeases",
]

INTEREST_EXPENSE_OPERATING = [
    "InterestExpense",
    "InterestExpenseDeposits",
]

NON_INTEREST_INCOME = [
    "NoninterestIncome",
]

NON_INTEREST_EXPENSE = [
    "NoninterestExpense",
]

PROVISION_FOR_CREDIT_LOSSES = [
    "ProvisionForLoanLeaseAndOtherLosses",
    "ProvisionForLoanAndLeaseLosses",
    "ProvisionForCreditLosses",
]

# ── Insurance-Specific ───────────────────────────────────────────────────────

PREMIUMS_EARNED = [
    "PremiumsEarnedNet",
    "PremiumsEarned",
]

POLICYHOLDER_BENEFITS = [
    "PolicyholderBenefitsAndClaimsIncurredNet",
    "PolicyholderBenefitsAndClaimsIncurred",
    "IncurredClaimsPropertyCasualtyAndLiability",
    "BenefitsLossesAndExpenses",
]

NET_INVESTMENT_INCOME = [
    "NetInvestmentIncome",
    "InvestmentIncomeNet",
    "InvestmentIncomeInterestAndDividend",
]

# ── Additional / Cross-statement ─────────────────────────────────────────────

COMMON_SHARES_OUTSTANDING = [
    "CommonStockSharesOutstanding",
    "EntityCommonStockSharesOutstanding",
]

# ── Master mapping: line_item_name → tag priority list ────────────────────────

LINE_ITEMS = {
    # Income Statement
    "revenue": REVENUE,
    "costOfRevenue": COST_OF_REVENUE,
    "grossProfit": GROSS_PROFIT,
    "researchAndDevelopmentExpenses": RESEARCH_AND_DEVELOPMENT,
    "sellingGeneralAndAdministrativeExpenses": SGA,
    "operatingExpenses": OPERATING_EXPENSES,
    "operatingIncome": OPERATING_INCOME,
    "interestExpense": INTEREST_EXPENSE,
    "interestIncome": INTEREST_INCOME,
    "incomeBeforeTax": INCOME_BEFORE_TAX,
    "incomeTaxExpense": INCOME_TAX,
    "netIncome": NET_INCOME,
    "epsDiluted": EPS_DILUTED,
    "epsBasic": EPS_BASIC,
    "weightedAverageSharesDiluted": SHARES_DILUTED,
    "weightedAverageSharesBasic": SHARES_BASIC,
    "depreciationAndAmortization": DEPRECIATION_AMORTIZATION,
    "ebitda": EBITDA,
    "stockBasedCompensation": STOCK_BASED_COMPENSATION,

    # Balance Sheet
    "cashAndCashEquivalents": CASH,
    "shortTermInvestments": SHORT_TERM_INVESTMENTS,
    "accountsReceivables": ACCOUNTS_RECEIVABLE,
    "inventory": INVENTORY,
    "totalCurrentAssets": TOTAL_CURRENT_ASSETS,
    "propertyPlantAndEquipment": PP_AND_E,
    "goodwill": GOODWILL,
    "intangibleAssets": INTANGIBLE_ASSETS,
    "totalAssets": TOTAL_ASSETS,
    "accountsPayables": ACCOUNTS_PAYABLE,
    "shortTermDebt": SHORT_TERM_DEBT,
    "currentPortionOfLongTermDebt": CURRENT_LONG_TERM_DEBT,
    "totalCurrentLiabilities": TOTAL_CURRENT_LIABILITIES,
    "longTermDebt": LONG_TERM_DEBT,
    "totalLiabilities": TOTAL_LIABILITIES,
    "totalStockholdersEquity": TOTAL_EQUITY,
    "retainedEarnings": RETAINED_EARNINGS,
    "totalDebt": TOTAL_DEBT,
    "deferredRevenue": DEFERRED_REVENUE,

    # Cash Flow
    "operatingCashFlow": OPERATING_CASH_FLOW,
    "capitalExpenditure": CAPITAL_EXPENDITURE,
    "acquisitionsNet": ACQUISITIONS,
    "investingCashFlow": INVESTING_CASH_FLOW,
    "dividendsPaid": DIVIDENDS_PAID,
    "shareRepurchases": SHARE_REPURCHASES,
    "debtRepayment": DEBT_REPAYMENT,
    "debtIssuance": DEBT_ISSUANCE,
    "financingCashFlow": FINANCING_CASH_FLOW,
    "changeInWorkingCapital": CHANGE_IN_WORKING_CAPITAL,

    # Balance Sheet - additional
    "deferredRevenueNonCurrent": DEFERRED_REVENUE_NONCURRENT,

    # Other
    "commonSharesOutstanding": COMMON_SHARES_OUTSTANDING,

    # Bank-Specific Income Statement
    "netInterestIncome": NET_INTEREST_INCOME,
    "interestIncomeOperating": INTEREST_INCOME_OPERATING,
    "interestExpenseOperating": INTEREST_EXPENSE_OPERATING,
    "nonInterestIncome": NON_INTEREST_INCOME,
    "nonInterestExpense": NON_INTEREST_EXPENSE,
    "provisionForCreditLosses": PROVISION_FOR_CREDIT_LOSSES,

    # Insurance-Specific
    "premiumsEarned": PREMIUMS_EARNED,
    "policyholderBenefits": POLICYHOLDER_BENEFITS,
    "netInvestmentIncome": NET_INVESTMENT_INCOME,
}


def resolve_tag(available_facts: dict, tag_list: list[str]) -> str | None:
    """Given a company's us-gaap facts dict and a priority list of tags,
    return the first tag that exists in the data, or None."""
    for tag in tag_list:
        if tag in available_facts:
            return tag
    return None


def build_tag_map(available_facts: dict) -> dict[str, str | None]:
    """Build a mapping from line_item_name → resolved XBRL tag for a company."""
    return {
        item: resolve_tag(available_facts, tags)
        for item, tags in LINE_ITEMS.items()
    }
