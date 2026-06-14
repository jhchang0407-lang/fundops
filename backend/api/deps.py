"""Minimal API dependencies: platform stores access.

Routes call `get_stores()` directly (or import it from here). All writes go
through stores (ADR-0031); there are no per-route singletons anymore.
"""

from __future__ import annotations

from backend.stores import Stores, get_stores

__all__ = ["Stores", "get_stores"]
