"""Application services (ADR-0031, ADR-0033).

Services accept explicit command intents from API/UI adapters, coordinate
domain logic + stores, commit canonical records first, then refresh
rebuildable projections. Route handlers must stay thin.
"""
