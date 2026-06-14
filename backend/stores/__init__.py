"""Platform stores: the only write path to the workspace database (ADR-0031).

Each store owns a stable boundary (identity, constitution, evidence, financial
data, runs, artifacts, portfolio ledger, dashboard, learning, ops). Services
compose stores inside transactions; canonical writes commit before projections
refresh (ADR-0033).
"""

from __future__ import annotations

from backend.core.workspace import Workspace, get_workspace
from backend.stores.identity import IdentityStore
from backend.stores.constitution import ConstitutionStore
from backend.stores.evidence import EvidenceStore
from backend.stores.financial import FinancialStore
from backend.stores.runs import RunStore
from backend.stores.artifacts import ArtifactStore
from backend.stores.portfolio import PortfolioStore
from backend.stores.dashboard import DashboardStore
from backend.stores.learning import LearningStore
from backend.stores.ops import OpsStore
from backend.stores.bulk import BulkStore
from backend.stores.context import ContextStore


class Stores:
    """Facade bundling every platform store over one workspace."""

    def __init__(self, ws: Workspace | None = None):
        self.ws = ws or get_workspace()
        self.identity = IdentityStore(self.ws)
        self.constitution = ConstitutionStore(self.ws)
        self.evidence = EvidenceStore(self.ws)
        self.financial = FinancialStore(self.ws)
        self.runs = RunStore(self.ws)
        self.artifacts = ArtifactStore(self.ws)
        self.portfolio = PortfolioStore(self.ws)
        self.dashboard = DashboardStore(self.ws)
        self.learning = LearningStore(self.ws)
        self.ops = OpsStore(self.ws)
        self.bulk = BulkStore(self.ws)
        self.context = ContextStore(self.ws)


_stores: Stores | None = None


def get_stores() -> Stores:
    global _stores
    if _stores is None or _stores.ws is not get_workspace():
        _stores = Stores()
    return _stores
