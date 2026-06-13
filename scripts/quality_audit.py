"""Artifact quality audit: deterministic checks over every retained artifact.

Quality here means the contracts the prompts promise: schema-valid payloads,
return math that adds up, claims grounded in figures, citations where the
artifact says it cites, no leaked internal tokens, honest gap reporting.
Run:  .venv/bin/python scripts/quality_audit.py [path-to-ws.db] [--kind k] [--limit n]
"""

from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.core.workspace import Workspace, set_workspace  # noqa: E402
from backend.domain import artifact_schemas  # noqa: E402
from backend.stores import Stores  # noqa: E402

# Raw internal ids that must never reach user-facing prose.
LEAK_TOKENS = re.compile(
    r"\b(fcf_yield|revenue_growth|gross_margin|operating_margin|net_margin|"
    r"debt_equity|shares_outstanding|market_cap|ic_review|thesis_intake|"
    r"workbench|run_id|entity_id|metric_key|stage_output)\b")
NUMBERY = re.compile(r"\d")
CITATION = re.compile(r"\[(W?\d+)\]")


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text or "") if len(s.strip()) > 30]


def _figure_density(text: str) -> float:
    """Share of substantive sentences carrying at least one number — the
    'no generic filler' contract."""
    sents = _sentences(text)
    if not sents:
        return 0.0
    return sum(1 for s in sents if NUMBERY.search(s)) / len(sents)


def audit_artifact(art: dict) -> list[str]:
    """Return a list of quality problems (empty = clean)."""
    problems: list[str] = []
    payload = art.get("payload") or {}
    body = payload.get("body") or {}
    md = art.get("rendered_md") or ""
    kind = art["kind"]

    vr = artifact_schemas.validate_artifact(payload)
    if not vr.ok:
        problems.append(f"schema: {'; '.join(vr.errors[:3])}")

    if kind == "thesis":
        rp = body.get("return_potential") or {}
        exp, comps = rp.get("expected_return_pct"), rp.get("components") or {}
        if isinstance(exp, (int, float)) and comps:
            total = sum(v for v in comps.values() if isinstance(v, (int, float)))
            if abs(total - exp) > max(1.5, abs(exp) * 0.05):
                problems.append(f"return math: components sum {total:.1f} != expected {exp:.1f}")
        if rp.get("fair_value") in (None, 0):
            problems.append("no fair value")
        if isinstance(exp, (int, float)) and abs(exp) > 300:
            problems.append(f"implausible expected return {exp:.0f}%")
        scope = body.get("scope") or {}
        for q, answer in scope.items():
            if q == "evidence_freshness":
                continue  # inherently about dates/sources, not figures
            if isinstance(answer, str) and answer and _figure_density(answer) < 0.34:
                problems.append(f"scope.{q}: low figure density "
                                f"({_figure_density(answer):.0%} of sentences carry a number)")

    elif kind == "investment_memo":
        sections = body.get("sections") or {}
        for sid, sec in sections.items():
            for sub, text in (sec.get("subsections") or {}).items():
                words = len((text or "").split())
                if words < 60:
                    problems.append(f"{sid}.{sub}: thin ({words} words)")
                if text and _figure_density(text) < 0.25:
                    problems.append(f"{sid}.{sub}: low figure density ({_figure_density(text):.0%})")
        if body.get("decision") not in artifact_schemas.MEMO_DECISIONS:
            problems.append(f"bad decision {body.get('decision')!r}")
        if not body.get("monitoring_plan_items"):
            problems.append("no monitoring plan")

    elif kind == "ic_verdict":
        for k in ("conviction", "constitution_fit", "data_quality", "gate_score"):
            v = body.get(k)
            if not isinstance(v, (int, float)) or not (0 <= v <= 100):
                problems.append(f"{k} out of range: {v!r}")
        if not body.get("hurdle_findings") and not body.get("hurdle_note"):
            problems.append("no hurdle findings and no explanation why")

    elif kind == "industry_note":
        cited = set(CITATION.findall(md))
        sources = body.get("sources") or []
        if sources and not cited:
            problems.append("sources listed but nothing cited in the text")
        declared = {m.group(1) for s in sources for m in [CITATION.search(str(s))] if m}
        dangling = sorted(c for c in cited if c not in declared)
        if dangling:
            problems.append(f"citations without sources: {dangling[:6]}")
        if len(sources) >= 4 and len(_sentences(md)) >= 8 and len(cited) < 3:
            problems.append(f"weak citation discipline ({len(cited)} distinct citations)")

    if kind != "screener_snapshot" and LEAK_TOKENS.search(md):
        toks = sorted(set(LEAK_TOKENS.findall(md)))[:5]
        problems.append(f"leaked internal tokens in prose: {toks}")

    return problems


def main() -> None:
    args = [a for a in sys.argv[1:]]
    db = Path(args[0]).expanduser() if args and not args[0].startswith("--") \
        else Path.home() / ".fundops" / "workspace.db"
    kind_filter = None
    limit = 400
    for i, a in enumerate(args):
        if a == "--kind":
            kind_filter = args[i + 1]
        if a == "--limit":
            limit = int(args[i + 1])

    ws = Workspace(db)
    set_workspace(ws)
    stores = Stores(ws)
    rows = stores.ws.query(
        "SELECT id FROM artifacts" + (" WHERE kind = ?" if kind_filter else "")
        + " ORDER BY created_at DESC LIMIT ?",
        ((kind_filter, limit) if kind_filter else (limit,)),
    )
    # Stub-written artifacts are deterministic placeholders (offline mode) —
    # report them separately; quality standards apply to model-written output.
    model_by_run: dict[str, str] = {}
    for p in stores.ws.query(
            "SELECT run_id, model FROM execution_provenance "
            "WHERE kind='model' AND run_id IS NOT NULL"):
        if p["model"] != "stub":
            model_by_run[p["run_id"]] = p["model"]
        model_by_run.setdefault(p["run_id"], p["model"])

    counts: Counter = Counter()
    issues: Counter = Counter()
    stubs: Counter = Counter()
    worst: list[tuple[int, str, str, list[str]]] = []
    for r in rows:
        art = stores.artifacts.get(r["id"])
        kind = art["kind"]
        writer = model_by_run.get(art.get("run_id") or "", "unknown")
        if writer == "stub":
            stubs[kind] += 1
            continue
        counts[kind] += 1
        problems = audit_artifact(art)
        if problems:
            issues[kind] += 1
            worst.append((len(problems), kind, f"{art.get('ticker') or ''} {art['id'][:14]}", problems))

    print(f"workspace: {db}")
    for kind, n in counts.most_common():
        bad = issues.get(kind, 0)
        print(f"  {kind:20} {n:4} model-written · {n - bad:4} clean · {bad:3} with issues"
              + (f" · {stubs[kind]} stub (skipped)" if stubs.get(kind) else ""))
    for kind, n in stubs.items():
        if kind not in counts:
            print(f"  {kind:20}    0 model-written · {n} stub (skipped)")
    worst.sort(reverse=True)
    print("\nworst offenders:")
    for n, kind, label, problems in worst[:12]:
        print(f"  [{kind}] {label}")
        for p in problems[:4]:
            print(f"     - {p}")
    if not worst:
        print("  none — all audited artifacts clean")
    ws.close()


if __name__ == "__main__":
    main()
