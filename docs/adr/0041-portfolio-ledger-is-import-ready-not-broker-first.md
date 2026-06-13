# Portfolio Ledger Is Import-Ready, Not Broker-First

FundOps will design the Portfolio Ledger to support manual entry and future import or broker-sync provenance without making external account integration a baseline product dependency. Ledger entries should be able to retain import source, external identifiers, reconciliation state, and correction history when those sources exist, but the core portfolio model should remain useful without linked brokerage accounts.

This keeps the product focused on investment workflow, thesis health, and learning before taking on account-linking complexity such as reconciliation, duplicate detection, cash movements, broker permissions, corporate actions, and sync failure states. Broker integration can be added later as another source feeding the Portfolio Ledger.
