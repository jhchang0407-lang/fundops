"""Machine-readable map of every frontend API call → backend endpoint → expected response shape.

Each entry maps a client.ts method name to its HTTP details and expected response contract.
The parametrized test_all_endpoints_respond.py uses this map to verify every endpoint.

Response shapes were verified against actual API responses (not guessed from frontend types).
"""

# ── GET endpoints (no ticker in path) ────────────────────────────

GET_CONTRACTS = {
    "dashboard": {
        "path": "/api/dashboard",
        "response_keys": ["recent_runs", "agent_run_counts", "latest_portfolio", "running_jobs"],
    },
    "getConfig": {
        "path": "/api/config",
        "response_keys": ["agents", "connectors"],
    },
    "getPresets": {
        "path": "/api/config/presets",
        "response_keys": ["presets"],
    },
    "getUniverses": {
        "path": "/api/config/universes",
        "response_keys": ["presets"],
    },
    "screenerResults": {
        "path": "/api/screener/results",
        "response_keys": ["results"],
    },
    "listTheses": {
        "path": "/api/thesis",
        "response_keys": ["results"],
    },
    "listICReviews": {
        "path": "/api/ic-review",
        "response_keys": ["results"],
    },
    "listApproved": {
        "path": "/api/research/approved",
        "response_keys": ["results"],
    },
    "getMemos": {
        "path": "/api/library/memos",
        "response_keys": ["memos"],
    },
    "getPortfolio": {
        "path": "/api/portfolio",
        "response_keys": ["holdings"],
    },
    "portfolioStatus": {
        "path": "/api/portfolio/status",
        "response_keys": [],
    },
    "allocatorRecs": {
        "path": "/api/allocator/recommendations",
        "response_keys": [],
    },
    "pipelineStatus": {
        "path": "/api/pipeline/status",
        "response_keys": [],
    },
    "pipelineHistory": {
        "path": "/api/pipeline/history",
        "response_keys": ["history"],
    },
    "listPendingApprovals": {
        "path": "/api/pipeline/pending",
        "response_keys": ["pending"],
    },
    "listJobs": {
        "path": "/api/jobs",
        "response_keys": ["jobs"],
    },
    "getCosts": {
        "path": "/api/costs",
        "response_keys": [],
    },
    "getScreenerConfig": {
        "path": "/api/screener/config",
        "response_keys": [],
    },
    "getScreenerFilters": {
        "path": "/api/config/screener-filters",
        "response_keys": [],
    },
    "getStrategy": {
        "path": "/api/strategy",
        "response_keys": [],
    },
    "listStrategies": {
        "path": "/api/strategy/list",
        "response_keys": ["strategies"],
    },
    "getConstitution": {
        "path": "/api/constitution",
        "response_keys": [],
    },
    "getConstitutionChangelog": {
        "path": "/api/constitution/changelog",
        "response_keys": ["changelog"],
    },
    "getRecentEvents": {
        "path": "/api/events/recent",
        "response_keys": ["events"],
    },
    "getLibraryStats": {
        "path": "/api/library/stats",
        "response_keys": [],
    },
    "getRefinementProposals": {
        "path": "/api/strategy/refinement-proposals",
        "response_keys": ["proposals"],
    },
    "getLearningProposals": {
        "path": "/api/learning/proposals",
        "response_keys": [],
    },
    "getLearningDrift": {
        "path": "/api/learning/drift",
        "response_keys": [],
    },
    "getLearningOutcomes": {
        "path": "/api/learning/outcomes",
        "response_keys": [],
    },
    "screenerV2Results": {
        "path": "/api/screener/v2/results",
        "response_keys": [],
    },
    "getConversationHistory": {
        "path": "/api/strategy/conversation/history",
        "response_keys": [],
    },
}

# ── Ticker-specific GET endpoints ────────────────────────────────

TICKER_GET_CONTRACTS = {
    "getThesis": {
        "path": "/api/thesis/{ticker}",
        "response_keys": [],
    },
    "getICReview": {
        "path": "/api/ic-review/{ticker}",
        "response_keys": [],
    },
    "tickerDetail": {
        "path": "/api/ticker/{ticker}",
        "response_keys": [],
    },
    "tickerTimeline": {
        "path": "/api/ticker/{ticker}/timeline",
        "response_keys": ["ticker", "timeline"],
    },
    "getReviewData": {
        "path": "/api/review/{ticker}",
        "response_keys": [],
    },
    "getEvidence": {
        "path": "/api/evidence/{ticker}",
        "response_keys": ["ticker", "artifacts"],
    },
    "getTickerEvents": {
        "path": "/api/events/ticker/{ticker}",
        "response_keys": ["events", "ticker"],
    },
    "findSimilar": {
        "path": "/api/library/similar/{ticker}",
        "response_keys": [],
    },
    "getLibraryTicker": {
        "path": "/api/library/ticker/{ticker}",
        "response_keys": [],
    },
    "getMemo": {
        "path": "/api/library/memos/{ticker}",
        "response_keys": [],
    },
}

# ── POST endpoints (mutations, no ticker) ────────────────────────

POST_CONTRACTS = {
    "runScreener": {
        "path": "/api/screener/run",
        "body": {},
        "response_keys": ["job_id"],
    },
    "runPortfolio": {
        "path": "/api/portfolio/run",
        "body": {},
        "response_keys": ["job_id"],
    },
    "runAllocator": {
        "path": "/api/allocator/run",
        "body": {},
        "response_keys": ["job_id"],
    },
    "runPipeline": {
        "path": "/api/pipeline/run",
        "body": {},
        "response_keys": ["job_id"],
    },
    "testConnection": {
        "path": "/api/config/test-connection?source=yfinance",
        "body": {},
        "response_keys": [],  # may return error with mocked connectors
        "allow_500": True,
    },
    "savePositions": {
        "path": "/api/portfolio/positions",
        "body": {"positions": [
            {"ticker": "AAPL", "shares": 50, "cost_basis": 170.0},
        ]},
        "response_keys": [],
    },
    "clearPipelineData": {
        "path": "/api/config/clear-pipeline",
        "body": {},
        "response_keys": [],
    },
}

# ── POST endpoints (with ticker) ─────────────────────────────────

TICKER_POST_CONTRACTS = {
    "runThesis": {
        "path": "/api/thesis/{ticker}",
        "body": {},
        "response_keys": ["job_id"],
    },
    "runICReview": {
        "path": "/api/ic-review/{ticker}",
        "body": {},
        "response_keys": ["job_id"],
    },
    "dismissTicker": {
        "path": "/api/research/dismiss/{ticker}",
        "body": {"reason": "too expensive"},
        "response_keys": [],
    },
    "promoteTicker": {
        "path": "/api/research/promote/{ticker}",
        "body": {},
        "response_keys": [],
    },
}
