"""FundOps API Routes.

All endpoints organized by domain.
"""

from fastapi import FastAPI

from backend.api.routes.dashboard import router as dashboard_router
from backend.api.routes.agents import router as agents_router
from backend.api.routes.pipeline import router as pipeline_router
from backend.api.routes.config_routes import router as config_router
from backend.api.routes.portfolio_routes import router as portfolio_router
from backend.api.routes.screener_config import router as screener_config_router
from backend.api.routes.strategy import router as strategy_router
from backend.api.routes.learning import router as learning_router
from backend.api.routes.learning import library_router
from backend.api.routes.review import router as review_router
from backend.api.routes.memory import router as memory_router


def register_routes(app: FastAPI):
    """Register all API route groups."""
    app.include_router(dashboard_router, prefix="/api", tags=["dashboard"])
    app.include_router(agents_router, prefix="/api", tags=["agents"])
    app.include_router(pipeline_router, prefix="/api", tags=["pipeline"])
    app.include_router(config_router, prefix="/api", tags=["config"])
    app.include_router(portfolio_router, prefix="/api", tags=["portfolio"])
    app.include_router(screener_config_router, prefix="/api", tags=["screener-config"])
    app.include_router(strategy_router, prefix="/api", tags=["strategy"])
    app.include_router(learning_router, prefix="/api", tags=["learning"])
    app.include_router(library_router, prefix="/api", tags=["library"])
    app.include_router(review_router, prefix="/api", tags=["review"])
    app.include_router(memory_router, prefix="/api", tags=["memory"])
