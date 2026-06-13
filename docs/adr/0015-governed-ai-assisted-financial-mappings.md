# Governed AI-Assisted Financial Mappings

FundOps may use AI to propose mappings from previously unmapped reported financial fields to known financial concepts, but those proposals are governed internal data-pipeline decisions rather than per-tag user approval tasks. A high-confidence mapping may be accepted company-locally first when evidence checks support it, while global mappings require stronger repeated evidence before reuse across companies. We chose this because unmapped XBRL tags can otherwise drop useful data, but silently promoting first-seen AI guesses into global screening inputs would make deterministic investment metrics harder to audit and debug.

Company-supplied field definitions are the primary semantic evidence for AI-assisted mappings. Deterministic validation should still check that the field's unit, period type, statement context, value shape, and conflicts match the target financial concept before the mapping can be treated as accepted.

When a mapping candidate has a plausible reported definition but fails validation, FundOps should retain the candidate and failure reason as data-quality evidence rather than using it in hard screening, deterministic calculated metrics, or fully supported Strategy Criteria.

AI-assisted mapping should apply to reported or company-filed fields where a Reported Field Definition and taxonomy context exist. Market-data and enrichment-provider fields should be handled through explicit provider adapters and the Financial Metric Catalog rather than AI guessing the meaning of arbitrary provider keys.

AI-assisted mapping should run lazily when deterministic mappings leave a useful Supported Financial Metric missing or create a Material Financial Coverage Gap. FundOps should not exhaustively analyze every custom tag by default; the mapping work should be driven by missing useful metrics so robustness improves without unnecessary complexity or cost.

When a useful metric is missing, FundOps should try to recover the actual reported field through governed AI-assisted mapping before falling back to a Proxy Criterion. Proxies are appropriate when reported-field recovery fails validation or the company does not report the needed concept.
