# FundOps Context

FundOps is an AI-augmented investment workflow for turning a strategy into screened candidates, research artifacts, portfolio decisions, and reviewable learning history. This context names the product concepts so behavior, data ownership, and evals can be discussed without mixing user-facing capabilities with implementation details.

## Product Vision

FundOps is a personal, institutional-grade investment operating system for one individual capital allocator who wants to run a disciplined research process, understand how their strategy behaves over time, and improve their judgment without delegating investment authority to software.

The product should help the Workspace Owner answer seven recurring questions:

- What do I believe, and what exact rules or review criteria express that belief?
- Which companies deserve deeper work, and why did they enter or leave the funnel?
- What evidence supports the current thesis for a company or holding?
- What changed since the thesis was written, and does the change matter?
- Where is the portfolio outside mandate, policy, risk budget, or thesis coverage?
- Which material decisions, exceptions, and alternatives need to be recorded or revisited?
- What have my decisions, misses, outcomes, and retained evidence taught me about the strategy?

FundOps should feel like an evidence-native investment partner, not a market terminal, trading bot, generic analytics dashboard, or document generator. Its core loop is: define a strategy, screen a universe, deepen the strongest ideas into artifacts, monitor thesis durability, surface reviewable attention, and convert retained history into learning.

This context describes the target product contract, not an MVP plan. Near-term implementation constraints may influence sequencing, but they should not redefine product semantics, introduce temporary names as durable concepts, or turn missing implementation into product philosophy.

## Product Principles

- **User authority over investment action**: FundOps may propose, rank, explain, monitor, and draft, but the Workspace Owner owns strategy activation and portfolio action.
- **Evidence before synthesis**: Every material claim, verdict, recommendation, alert, or lesson should be grounded in retained source-backed evidence or explicitly marked as unsupported.
- **Durable artifacts over chat memory**: Chat explains and negotiates behavior, while workflow artifacts, evidence records, approvals, and learning records preserve product truth.
- **Reviewable mutation over silent automation**: Strategy, workflow behavior, local extensions, and learning recommendations change through explicit approvals, not hidden model memory.
- **Local workspace first**: The Local FundOps Workspace owns the user's retained state. External providers, brokers, and future sync surfaces are adapters or import sources, not the source of truth.
- **Fixed contracts, strategy-specific emphasis**: Shared artifact and workflow contracts should stay comparable across companies and time, while the active Constitution changes emphasis, thresholds, and interpretation.
- **Controls before recommendations**: Institutional-grade behavior means explicit mandates, policies, exceptions, decisions, attribution, and audit packages before FundOps attempts stronger portfolio guidance.
- **Long-horizon learning over short-term prediction**: FundOps should learn from thesis durability, evidence quality, missed opportunities, user decisions, and outcomes without pretending to prove the future from price movement alone.

## Target Product Shape

- **Strategy and operating setup**: FundOps Chat, Strategy Chat, Constitution, Strategy Wiring, Settings/Config, provider setup, schedules, and usage controls define what FundOps is allowed to do and how it operates.
- **Opportunity discovery and deepening**: Screener, Research Queue, Thesis, IC Review, Memo, and Pipeline Orchestration move companies from broad universe or directed request to evidence-backed investment artifacts.
- **Company memory**: Company Page, Library, Workflow Artifact Reader, retained evidence, financial observations, and artifact exports make every researched company inspectable over time.
- **Portfolio context**: Portfolio, Portfolio Ledger, Portfolio Thesis Coverage, Thesis Health, and Portfolio Review connect owned positions to memo-backed evidence without becoming broker execution.
- **Investment control plane**: Investment Mandate, Portfolio Policy, Risk & Exposure, Decision Register, Attribution, Data Governance, and Audit Package generation make the workflow institution-grade without requiring a team account.
- **Learning loop**: Learning/Evals, Dashboard Decision Items, Dashboard Attention Items, Archive Q&A, and approval history turn outcomes and user responses into reviewable strategy evolution.
- **Local extensibility**: The Agent-Native Workspace Contract and Extension History let the Workspace Owner change local FundOps behavior through reviewable work orders, validation, previews, and rollback.

## Institutional-Grade Product Layer

Institutional-grade FundOps should mean institutional discipline, not institutional bureaucracy. The product remains one-owner and local-first, but it should produce the same control artifacts a serious investment team would expect: mandate clarity, policy checks, risk exceptions, decision records, attribution, data governance, and audit-ready evidence packages.

The institutional control loop is:

```text
Investment Mandate
      |
Research Constitution
      |
Workflow Evidence and Artifacts
      |
Portfolio Policy
      |
Risk & Exposure
      |
Decision Register
      |
Performance and Thesis Attribution
      |
Learning / Calibration
      |
Audit Package
```

This layer should not add multi-user permissions, compliance theater, broker execution, or generic enterprise workflow by default. It should make the Workspace Owner's investment process legible enough that a future allocator, auditor, partner, or the user's own future self can reconstruct what was believed, what was known, what was decided, what changed, and what was learned.

## Product Contradiction Map

- **AI partner vs. autonomous manager**: FundOps should use AI aggressively for research, interpretation, drafting, and pattern discovery while keeping investment authority with the user. The resolution is reviewable proposals, cited evidence, and explicit approvals.
- **Workflow funnel vs. directed research**: The Screener-led funnel is the default discovery path, but Portfolio coverage and user-directed ticker research are legitimate entry points when they create a clear research obligation.
- **Portfolio monitor vs. Portfolio Review**: Portfolio owns entered holdings, lots, P&L, and coverage state. Portfolio Review owns evidence-backed pressure and opportunity framing. Neither surface should become broker execution or hidden buy/sell instruction.
- **Dashboard vs. archive/status surfaces**: Dashboard is for unresolved decisions and attention. Company Page, Library, Workflow Artifact Reader, Settings/Config, and Activity Timeline carry history, reading, operational setup, and provenance.
- **Strategy specificity vs. comparable artifacts**: The Constitution should change criteria, emphasis, and review thresholds, while Thesis, IC Review, Memo, Thesis Health, and Learning/Evals keep stable contracts so artifacts remain comparable.
- **Learning engine vs. data-mined overfitting**: Learning/Evals may discover associations and propose calibration, but it should separate association from thesis-grounded explanation, show confidence and caveats, and require user acceptance before behavior changes.
- **Local-first product vs. future integrations**: Broker sync, richer providers, exports, and sync-adjacent features may exist later, but the Local FundOps Workspace remains the durable owner of portfolio records, evidence, artifacts, and learning history.
- **Personal workspace vs. institutional controls**: FundOps should stay optimized for one Workspace Owner while adopting institutional-grade discipline through records, policies, exceptions, attribution, and audit packages rather than team-first permissions.
- **Decision support vs. portfolio control**: FundOps should avoid autonomous trading instructions, but it should still name policy breaches, exposure risks, exceptions, and decision options so the user can act with institutional clarity.
- **Implementation staging vs. product vision**: Baseline scope language should describe product boundaries and sequencing without narrowing the long-term vision or preserving proof-of-concept names as product truths.

## Language

**Product Capability**:
A user-facing behavior area with its own purpose, inputs, outputs, and eval criteria.
_Avoid_: Route; component; agent; function when describing product behavior

**Investment Learning Partner**:
The FundOps behavior where retained evidence, thesis-health monitoring, outcome evaluation, and AI-assisted pattern analysis help the retail investor understand how their strategy is working and evolve their judgment without outsourcing the final investment call.
_Avoid_: Autonomous fund manager; trade recommender; backtest oracle; generic analytics dashboard

**Local FundOps Workspace**:
A single user's FundOps environment where their strategy, workflow history, research artifacts, portfolio records, and learning history belong together as portable retained state.
_Avoid_: Hosted tenant; shared team account; cloud-only workspace

**Workspace Owner**:
The one individual capital allocator whose strategy, portfolio, workflow history, credentials setup, and learning history define a Local FundOps Workspace.
_Avoid_: Team member; collaborator; tenant administrator; shared account user

**Institutional Investment Control Plane**:
The FundOps product layer that makes the Workspace Owner's mandate, research process, portfolio policy, risk state, decisions, attribution, data quality, and audit evidence explicit and replayable.
_Avoid_: Multi-user enterprise workflow; compliance theater; autonomous manager; broker execution platform

**Investment Mandate**:
The durable statement of the Workspace Owner's capital allocation purpose, return goals, risk tolerance, time horizon, investable scope, exclusions, liquidity needs, and portfolio-level constraints.
_Avoid_: Single screen filter; generic investor label; broker account profile; model-inferred preference

**Research Constitution**:
The strategy and research subset of the active Constitution that governs opportunity discovery, evidence requirements, Thesis emphasis, IC Review strictness, Memo emphasis, and Learning/Evals calibration.
_Avoid_: Separate active strategy truth; Portfolio Policy; compliance policy; prompt-only research style

**Portfolio Policy**:
The mandate-derived rules and review thresholds that govern portfolio construction concerns such as sizing, concentration, cash, liquidity, exposure, diversification, thesis coverage, and exception handling.
_Avoid_: Broker order instruction; hidden allocation model; Strategy Criterion; Portfolio Ledger entry

**Risk & Exposure**:
The product capability that turns Portfolio Ledger state, Portfolio Policy, thesis health, market data, sector or factor context, and retained evidence into current exposure, risk, breach, and exception views.
_Avoid_: Portfolio page P&L; autonomous risk manager; generic chart dashboard; broker margin system

**Risk Budget**:
The allowed exposure, concentration, drawdown, liquidity, or thesis-break tolerance expressed by the Investment Mandate or Portfolio Policy.
_Avoid_: Position size recommendation; guaranteed loss limit; broker risk limit; hidden model preference

**Exposure Map**:
The current view of portfolio exposure by holding, sector, industry, thesis type, strategy criterion, factor, geography, liquidity, market cap, or other policy-relevant grouping.
_Avoid_: Holdings table; Screener ranking; generic diversification pie chart; unsupported factor model

**Policy Breach**:
A source-backed condition where current portfolio state or workflow state violates a Portfolio Policy, Risk Budget, or mandate constraint.
_Avoid_: Sell instruction; AI recommendation; generic warning; silently tolerated exception

**Portfolio Exception**:
A Workspace Owner-approved or acknowledged departure from Portfolio Policy or Risk Budget, retained with rationale, evidence, scope, duration, and review timing.
_Avoid_: Hidden override; permanent rule deletion; ignored breach; broker exception

**Exception Register**:
The retained list of active and historical Portfolio Exceptions, unresolved Policy Breaches, and exception reviews.
_Avoid_: Dashboard notification list; Portfolio Ledger; generic audit log; deleted warnings

**Decision Register**:
The retained institution-grade record of material investment, strategy, portfolio, exception, and learning decisions, including alternatives considered, evidence used, rationale, action taken, and later outcome links.
_Avoid_: Approval Record only; chat transcript; artifact list; generic activity timeline

**Investment Decision Record**:
One material decision retained in the Decision Register, such as approving a strategy change, passing IC, generating a memo, accepting a policy exception, adding coverage, recording an exit rationale, or accepting a Learning Recommendation.
_Avoid_: Button click; unstructured note; Portfolio Sale Entry alone; completed artifact alone

**Decision Rationale**:
The explicit explanation for why an Investment Decision Record was made under the evidence, mandate, policy, and alternatives available at the decision time.
_Avoid_: Reconstructed model guess; generic approval text; hindsight explanation; hidden chat memory

**Decision Alternative**:
A meaningful path considered but not taken when making an Investment Decision Record, retained when it materially explains the final decision.
_Avoid_: Exhaustive brainstorm list; model hallucinated option; unrelated rejected ticker; hidden opportunity cost

**Attribution**:
The Learning/Evals and Portfolio-adjacent capability that explains what drove portfolio, thesis, decision, and strategy outcomes using retained evidence rather than price movement alone.
_Avoid_: Raw return table; proof of skill; generic performance dashboard; backtest oracle

**Performance Attribution**:
The breakdown of realized or unrealized portfolio performance by benchmark, holding, sector, exposure, thesis state, return driver, or time period when retained evidence supports the explanation.
_Avoid_: Price-only win/loss label; exact accounting ledger; unsupported factor attribution; broker statement replacement

**Thesis Attribution**:
The explanation of whether outcome evidence aligned with, contradicted, bypassed, or failed to test the original thesis, Memo Return Drivers, Thesis Watch Items, and kill criteria.
_Avoid_: Generic news explanation; price target accuracy; post-hoc story; thesis-health status alone

**Decision Attribution**:
The explanation of how prior Investment Decision Records, user responses, overrides, dismissals, policy exceptions, or accepted recommendations contributed to later outcomes.
_Avoid_: Blame assignment; user grading; silent behavioral profile; price-only decision score

**Missed Opportunity Attribution**:
The lower-confidence explanation of retained opportunities not acted on, including whether the miss came from strategy criteria, workflow selection, IC judgment, portfolio policy, user dismissal, data gaps, or noise.
_Avoid_: Hindsight regret feed; broad market scan; unretained universe tracking; automatic strategy change

**Data Governance**:
The product capability that makes data authority, quality, corrections, source conflicts, coverage gaps, mappings, and auditability visible enough to trust workflow outputs.
_Avoid_: Raw database diagnostics; provider settings only; user-authored financial facts; hidden parser behavior

**Data Quality State**:
The current trust state of a data item, metric, source, mapping, or workflow input, such as accepted, stale, contradicted, unmapped, corrected, unsupported, data gap, or under review.
_Avoid_: Generic error flag; visual badge without provenance; investment judgment; permanent exclusion

**Authoritative Source Decision**:
The retained governance decision that selects which source or evidence tier controls a specific conflicted company fact, financial observation, mapping, or workflow input.
_Avoid_: Silent provider precedence; user opinion override; deleting contradicted evidence; one-off parser choice

**Institutional Review Packet**:
A bundled, readable, evidence-linked export for a material review moment, such as IC Review, Portfolio Review, Risk Review, Thesis Break Review, or periodic review.
_Avoid_: Workspace Archive; raw JSON dump; regenerated latest-state report; generic PDF export

**Institutional Review Packet Export**:
The product capability that generates Institutional Review Packets from retained evidence bundles, decision records, policy state, attribution records, and rendered artifacts.
_Avoid_: Browser print; workspace backup; ad hoc report prompt; latest-state recomputation

**IC Packet**:
An Institutional Review Packet for an IC Review decision, containing the Completed Thesis, IC scores, hard hurdle findings, evidence bundle, Constitution Version, alternatives when relevant, and decision rationale.
_Avoid_: Investment Memo; buy recommendation; IC table row; source-free scorecard

**Portfolio Review Packet**:
An Institutional Review Packet for portfolio review, containing portfolio state, Portfolio Policy context, Risk & Exposure views, Policy Breaches, Portfolio Exceptions, thesis-health state, opportunities, and evidence links.
_Avoid_: Broker statement; trade blotter; target-weight recommendation; Dashboard screenshot

**Audit Package**:
A portable evidence package that lets a future reviewer reconstruct a workflow output, decision, exception, data correction, or attribution claim from retained records, sources, versions, and provenance.
_Avoid_: Workspace backup; retail memo PDF; raw database dump; trust-me summary

**Dashboard**:
The cross-workflow attention and decision queue for unresolved FundOps work that may need user review.
_Avoid_: Exhaustive status page; company-specific dossier; artifact reader; detailed Portfolio analysis; Settings configuration form

**Dashboard Item**:
An unresolved unit of work surfaced on the Dashboard as either a Dashboard Decision Item or a Dashboard Attention Item.
_Avoid_: Completed activity row; routine status line; historical artifact

**Dashboard Item Source**:
The owning product record or unresolved product condition that causes a Dashboard Item to appear.
_Avoid_: Duplicated Dashboard-owned truth; copied artifact payload; orphan notification

**Dashboard Item Source Version**:
The specific observed version of a Dashboard Item Source that a Dashboard Item Response applies to.
_Avoid_: Permanent ticker blacklist; broad topic suppression; hidden global preference

**Dashboard Decision Item**:
An unresolved Dashboard item that requires explicit user choice before FundOps proceeds or changes user-visible behavior.
_Avoid_: Passive alert; automatic continuation; informational status; hidden approval

**Needs Decision**:
The Dashboard section that contains Dashboard Decision Items awaiting an explicit user choice.
_Avoid_: Attention feed; passive status; completed activity; informational alert

**Dashboard Attention Item**:
An unresolved Dashboard item that asks the user to inspect evidence without implying a required decision or portfolio action.
_Avoid_: Trade instruction; approval request; automatic strategy change; generic notification

**Needs Attention**:
The Dashboard section that contains evidence-backed Dashboard Attention Items worth user inspection.
_Avoid_: Normal successful run log; routine schedule status; generic notification stream; required approval queue

**Dashboard Item Response**:
A user response to a Dashboard Decision Item or Dashboard Attention Item.
_Avoid_: Uninterpreted click; hidden learning signal; automatic workflow mutation

**Dashboard Response Record**:
The retained record of a Dashboard Item Response needed to remember visibility, timing, resolution, or learning feedback for a Dashboard Item Source.
_Avoid_: Duplicate source artifact; second workflow status; hidden investment decision

**Approval Record**:
The retained record of an explicit user acceptance or rejection of a proposed strategy, workflow continuation, learning recommendation, or agent work result.
_Avoid_: Ambiguous chat yes; overwritten approval state; hidden activation

**Dashboard Item Resurfacing**:
The reappearance of a previously suppressed Dashboard Item because its Dashboard Item Source is still unresolved and has materially changed.
_Avoid_: Repeating the same dismissed item; permanent suppression; unrelated duplicate alert

**Dashboard Hygiene Action**:
A Dashboard Item Response that changes item visibility, timing, or operational handling without being interpreted as investment preference or strategy feedback.
_Avoid_: Learning Feedback Signal; investment judgment; Strategy Change Proposal

**Learning Feedback Signal**:
A structured user response that should inform Learning/Evals because it reveals investment preference, strategy mismatch, thesis judgment, or workflow preference.
_Avoid_: Generic thumbs-up; generic thumbs-down; passive dismissal; operational retry

**Dashboard Response Set**:
The allowed Dashboard Item Responses for a Dashboard item type, chosen to match why the item exists and what kind of user response would be meaningful.
_Avoid_: One universal response pattern; generic feedback controls; hidden item-type behavior

**Portfolio**:
The user-facing holdings function for entering positions and tracking current value, P&L, and latest portfolio-linked thesis health state.
_Avoid_: Allocator; Portfolio Review queue; autonomous trade recommendation; non-held opportunity ranking; thesis-health refresh owner

**Portfolio Ledger**:
The retained investment record of portfolio lots, sales, exits, corrections, valuation marks, and portfolio-linked evidence from which current holdings and P&L are derived.
_Avoid_: Current holdings table as truth; broker order book; allocator recommendation log

**Portfolio Import Source**:
The origin of a Portfolio Ledger entry, such as manual entry, file import, broker sync, or an external account integration.
_Avoid_: Broker-first ownership; hidden source; portfolio truth override

**Portfolio Reconciliation State**:
The retained status describing whether imported or synced Portfolio Ledger entries have been matched, reviewed, corrected, or left unresolved.
_Avoid_: Silent overwrite; assuming broker data is always canonical; hiding duplicate entries

**Portfolio Thesis Coverage Request**:
A Portfolio-originated request to create or refresh memo-backed thesis coverage for a held ticker when no suitable Active Thesis Health Source exists.
_Avoid_: Bulk memo generation button; Portfolio-owned memo generation; thesis-health refresh; allocator action

**Directed Company Research Request**:
A user-requested workflow run for one or more specific tickers outside the default Screener-led funnel.
_Avoid_: Replacing the workflow funnel; chat-only research; unvalidated arbitrary ticker action

**Research Queue**:
The workflow coordination capability that turns selected funnel handoffs, Directed Company Research Requests, and Portfolio Thesis Coverage Requests into queued research work owned by the appropriate downstream capability.
_Avoid_: Generic backlog; Portfolio-owned memo generation; chat-only ticker research; separate artifact store

**Fresh Portfolio Thesis Coverage**:
An Active Thesis Health Source for a held ticker that is recent enough and event-current enough for Portfolio to treat the holding as covered.
_Avoid_: Any historical thesis; stale memo; memo without status-driving watch items; price-only refresh

**Automatic Portfolio Thesis Coverage**:
The automatic creation and execution of memo-backed thesis coverage work for a held ticker that lacks Fresh Portfolio Thesis Coverage.
_Avoid_: User-approved memo queue item; bulk memo button; silent thesis-health refresh; Portfolio-owned memo writing

**Held-Position Coverage Memo**:
An Investment Memo generated for a current holding to establish Fresh Portfolio Thesis Coverage rather than because the ticker passed IC Selection.
_Avoid_: IC-selected opportunity memo; Portfolio-authored memo; lightweight placeholder; thesis-health refresh

**Portfolio Thesis Coverage State**:
The visible per-holding status of automatic memo-backed thesis coverage work, such as queued, running, covered, failed, or stale.
_Avoid_: Dashboard queue item by default; hidden background job; memo artifact status; thesis-health status

**Portfolio Factual Flag**:
A non-prescriptive condition shown on a holding because entered portfolio data or price-derived values crossed a visible threshold.
_Avoid_: Trade recommendation; Portfolio Review decision item; allocator action; hidden sell signal

**Portfolio Position Type**:
An optional user-entered or user-approved label describing the intended role of a held position.
_Avoid_: Silently assigned allocator class; automatic trade instruction; hidden sizing rule; thesis-health status

**Portfolio Purchase Lot**:
A user-entered acquisition record for a held ticker, including shares, cost basis, and purchase date.
_Avoid_: Current holding aggregate; sale record; broker execution; memo coverage state

**Portfolio Entry Correction**:
A change that fixes an erroneous Portfolio entry without treating it as a real investment outcome.
_Avoid_: Sale; exit; Learning Feedback Signal; Portfolio History Milestone

**Portfolio Exit Record**:
A retained record that a held position was partially or fully sold, including exit evidence needed for portfolio history and learning.
_Avoid_: Entry correction; row deletion; allocator recommendation; thesis-health status change

**Portfolio Sale Entry**:
A user-entered sale record for an active holding, including sold shares, sale date, and exit price.
_Avoid_: Row deletion; entry correction; broker order; Portfolio Review recommendation

**Portfolio Entry Intent**:
The explicit user-selected meaning of a Portfolio edit row, such as adding a purchase lot or recording a sale.
_Avoid_: Inferring sale from negative shares; hidden correction; broker order type; allocator action

**Partial Portfolio Exit**:
A Portfolio Exit Record for selling part of a held position while leaving the remaining position active.
_Avoid_: Position edit; full exit; share-count correction; hidden trim recommendation

**Realized Portfolio P&L**:
The gain or loss recorded when a Portfolio Sale Entry is matched against prior Portfolio Purchase Lots.
_Avoid_: Unrealized P&L; price-only refresh; thesis-health status; estimated allocator outcome

**Portfolio Review**:
The Dashboard-owned review surface that gathers portfolio-relevant opportunities and attention items for the user to inspect before deciding whether to act.
_Avoid_: Allocator; autonomous trade instruction; broker execution; held-position source of truth

**Portfolio Review Framing**:
The evidence-first language Portfolio Review uses to explain why a portfolio-relevant item is visible without claiming autonomous investment judgment.
_Avoid_: Buy instruction; sell instruction; AI recommendation; unsupported target weight; best-opportunity claim

**Portfolio Pressure Item**:
A Portfolio Review item for a current holding whose thesis, sizing, concentration, evidence freshness, or policy fit needs inspection.
_Avoid_: Sell instruction; replacement recommendation; switch candidate; hidden portfolio judgment

**Portfolio Pressure List**:
The Portfolio Review subsection listing current holdings with the weakest or most pressured evidence state.
_Avoid_: Sell list; replacement source list; AI-ranked exit queue

**Portfolio Pressure Ranking**:
The source-backed ordering of Portfolio Pressure Items by severity, materiality, and freshness of pressure on current holdings.
_Avoid_: Hidden sell score; model-only conviction; replacement priority

**Constitution-Fit Opportunity**:
A Portfolio Review item for a non-held or not-currently-owned opportunity whose retained workflow evidence shows strong fit with the active Constitution.
_Avoid_: Replacement candidate; best option without source score; autonomous buy recommendation; broad style call

**Constitution-Fit Opportunity List**:
The Portfolio Review subsection listing retained opportunities with the strongest source-backed fit to the active Constitution.
_Avoid_: Buy list; replacement target list; AI-ranked trade queue

**Constitution-Fit Opportunity Ranking**:
The source-backed ordering of Constitution-Fit Opportunities by retained workflow evidence, Constitution fit, thesis health, and freshness.
_Avoid_: Hidden buy score; generic popularity rank; replacement priority

**Portfolio Review Rank Source**:
The visible evidence source explaining why a Portfolio Review item appears high in its list.
_Avoid_: Opaque AI rank; unsupported label; unexplained urgency

**Portfolio Review Projection**:
The automatic Dashboard view of portfolio-relevant source records and current evidence used to build Portfolio Review.
_Avoid_: Separate agent run; recommendation generation button; duplicated portfolio state

**Recent Activity**:
The Dashboard section that shows quiet historical workflow activity without treating completed work as unresolved attention or decision work.
_Avoid_: Work queue; Needs Attention; artifact reader; exhaustive audit log

**Dashboard Product Boundary**:
The Dashboard scope focused on unresolved decisions, evidence-backed attention, and response handling rather than new autonomous portfolio judgment.
_Avoid_: Portfolio optimizer; autonomous buy/sell recommender; broad style-call engine; duplicate workflow database

**FundOps Chat**:
The primary conversational surface for strategy setup, archive questions, output discussion, and reviewable system changes.
_Avoid_: Strategy Chat when referring to the whole chat surface; separate Library chat tab; workflow-specific assistant

**Strategy Chat**:
The strategy-changing behavior inside FundOps Chat for agreeing on the user's investment strategy and proposing canonical strategy/settings changes.
_Avoid_: Archive Q&A; Screener runner; research executor; allocator

**Archive Q&A**:
The read-only FundOps Chat behavior for discussing historical workflow artifacts, ticker history, outcomes, and prior decisions.
_Avoid_: Strategy Change Proposal; workflow generation request; separate Library chat tab

**FundOps Chat Mode**:
The current conversational behavior FundOps Chat applies to a user request, such as Strategy Chat or Archive Q&A.
_Avoid_: Hidden mutation; one-size-fits-all chat response; separate app section

**Archive Answer Source**:
A cited historical artifact, timeline entry, or ticker record used by Archive Q&A to answer a question.
_Avoid_: Unsupported memory; latest-only claim; invisible provenance

**Archive Answer Action**:
A compact action from an Archive Q&A answer that opens a cited source in its owning surface.
_Avoid_: Full artifact dump in chat; generic ticker link only; hidden source

**Screener**:
The workflow capability that evaluates an approved company universe against the active Constitution to produce research candidates.
_Avoid_: Screener function; generic stock table; research agent

**Screening Requirement**:
An exact wireable Strategy Criterion that a company must satisfy before it can become a Screener Candidate.
_Avoid_: Soft preference; ranking hint; hidden scoring weight

**Screener Candidate**:
A company from the screened universe that satisfies the active Screening Requirements and is eligible for downstream research.
_Avoid_: Any stock in the universe; watchlist item; thesis

**Screened Universe**:
The approved company set evaluated by a Screener run before Screening Requirements are applied.
_Avoid_: Screener Candidate list; Thesis queue; visible result set

**Universe Selection**:
The user-approved scope of companies FundOps may evaluate for screening, such as a known index, preset universe, custom list, sector scope, or researched investable set.
_Avoid_: Raw user text; unvalidated ticker list; hidden screener default

**Universe Version**:
An approved resolved snapshot of the Constitution-owned Universe Selection used to explain, replay, and compare Screener behavior over time.
_Avoid_: Latest index membership only; unversioned custom ticker list; hidden universe update

**Universe Validation**:
The harnessed process that resolves a Universe Selection into valid Securities, Security Listings, and Ticker Symbols while excluding broken, ambiguous, unsupported, or unrelated entries.
_Avoid_: Blind ticker acceptance; AI-invented constituent list; failed screener run as validation

**Supported Universe Security Scope**:
The market and security-type boundary that Universe Validation may activate, starting with US-listed stocks.
_Avoid_: Global securities by default; unsupported asset classes; silent foreign-listing inclusion

**Screener Run Evidence**:
The retained per-company facts from a Screener run used for audit, diagnostics, and evals whether or not the company became a Screener Candidate.
_Avoid_: User-facing near-miss list; Screener result; Thesis queue

**Screener Snapshot**:
The immutable saved Screener result state for a ticker in a completed Screener run.
_Avoid_: Current market data; regenerated explanation; mutable candidate row

**Screener Candidate Detail**:
The expanded per-candidate quick view that shows why a visible Screener Candidate passed and how it ranked.
_Avoid_: Capability Wiring Panel; Company Page; hidden failed-company evidence

**Screener Key Financials**:
The concise, configuration-stable financial metric strip inside Screener Candidate Detail that mirrors the active Screener wiring.
_Avoid_: Candidate-specific metric set; local display preference; full ranking blend; exhaustive evidence inventory

**Screening Failure Reason**:
The recorded explanation of which Screening Requirement a company did not satisfy during a Screener run.
_Avoid_: User-facing rejection note; investment opinion; Thesis verdict

**Screening Pass Evidence**:
The recorded proof that a Screener Candidate satisfied a Screening Requirement during a Screener run.
_Avoid_: Thesis argument; ranking explanation; generic metric snapshot

**Screener Ranking Explanation**:
The candidate-specific explanation of why a Screener Candidate ranked where it did after satisfying the Screening Requirements.
_Avoid_: Screening Pass Evidence; Capability Wiring Panel; Thesis argument

**Screener Ranking Source Explanation**:
The fuller grounded ranking explanation from which concise Screener Ranking Explanation prose may be derived.
_Avoid_: Quick-view copy as source of truth; unsupported prose; Thesis argument

**Screener Explanation Format**:
The consistent structure used to produce grounded Screener ranking explanations.
_Avoid_: Free-form prose; inconsistent bullet/prose formats; unsupported claims

**Screener Ranking Component**:
A saved ranking fact or contribution used to explain a Screener Candidate's position among surviving candidates.
_Avoid_: Vague positive trait; unsupported prose claim; hard Screening Requirement

**Screener Ranking**:
The ordering of Screener Candidates used to prioritize which companies move through the workflow first.
_Avoid_: Strategy compliance; pass/fail decision; soft criterion

**Screener Ranking Blend**:
The approved or explicitly defaulted weighting used to order Screener Candidates after Screening Requirements are satisfied.
_Avoid_: Hidden ranking formula; implied preference; AI-invented priority

**Screener Review Set**:
The ranked set of Screener Candidates kept visible for user review after a Screener run.
_Avoid_: Full universe; hidden backlog; Thesis queue

**Screener Run**:
The capability-local execution of Screener that produces or refreshes a Screener Review Set without automatically executing downstream capabilities.
_Avoid_: Full Pipeline Run; Thesis run; Strategy change

**Screener Result Table**:
The ranked table of Screener Candidates visible after a Screener run.
_Avoid_: Valuation table; Thesis queue; full universe

**Screener Handoff**:
The selected Screener Candidates made available to Thesis after a Screener run.
_Avoid_: Thesis execution; all visible results; failed-screen companies

**Screener Handoff Selection**:
The current subset of Screener Candidates selected for Screener Handoff.
_Avoid_: Original rank; Screening Requirement; Thesis verdict

**Top Picks**:
The user-facing label for the current Screener Handoff Selection.
_Avoid_: Abstract score bucket; all Screener Candidates; completed Thesis

**Remaining Candidates**:
The user-facing label for Screener Candidates in the Screener Review Set that are not currently in Top Picks.
_Avoid_: Below-threshold stocks; failed companies; near-misses

**Screener Run Summary**:
The aggregate status shown for a Screener run, such as universe size, passed count, and visible review count.
_Avoid_: Failed-company list; near-miss display; capability wiring

**Screener Review Action**:
A user action on a visible Screener Candidate that adjusts downstream handling or records feedback without changing the active Constitution.
_Avoid_: Strategy change; hidden reranking; failed-company review

**Screener Promotion**:
A Screener Review Action that includes a visible Screener Candidate in the Screener Handoff Selection.
_Avoid_: Passing a failed screen; changing rank; investment approval

**Screener Dismissal**:
A Screener Review Action that excludes a visible Screener Candidate from the Screener Handoff Selection for the current run while keeping it in the Screener Review Set.
_Avoid_: Screening Failure Reason; permanent blacklist; Strategy Criterion change

**Top Picks Removal**:
The neutral feedback record created when a Screener Candidate is removed from Top Picks.
_Avoid_: Investment rejection; Screening Failure Reason; visible stigma

**Top Picks Addition**:
The selection feedback record created when a Screener Candidate is manually added to Top Picks.
_Avoid_: Thesis execution; investment approval; changed Screener Ranking

**Top Picks Selection Order**:
The current order of candidates inside Top Picks after default selection and manual additions/removals.
_Avoid_: Original Screener Ranking; metric score; Thesis verdict

**Live FundOps Server Session**:
The active FundOps continuity while the local app server is still running.
_Avoid_: Permanent active selection; browser tab memory; new Screener run

**Attached Coding-Agent Session**:
An active Codex, Claude Code, or similar workspace coding session that FundOps may use for advanced extension work requiring file edits, tests, previews, or rollback.
_Avoid_: Normal workflow run; hidden background mutation; standalone product API

**Agent-Native Workspace Contract**:
The primary FundOps product contract for an attached coding agent, expressed through workspace files, commands, manifests, harness checks, review flows, and durable local state rather than a public API-first surface.
_Avoid_: Public REST API as product center; raw prompt protocol; undocumented file convention

**UI-Native Agent Workspace**:
The FundOps product shape where the user works through a native UI backed by Python workflow capabilities and an Agent-Native Workspace Contract.
_Avoid_: Terminal-only tool; standalone API product; hidden coding-agent backend

**Agent Work Order**:
A provider-neutral workspace manifest requesting an Attached Coding-Agent Session to perform extension work such as authoring files, running validation, rendering previews, explaining diffs, or preparing rollback.
_Avoid_: Raw prompt passthrough; provider-specific command; normal investment workflow task

**Agent Work Result**:
The file-backed response to an Agent Work Order, including changed files, validation results, previews, diffs, risks, and rollback information.
_Avoid_: Chat-only completion; hidden file mutation; unverifiable agent claim

**Extension History**:
The retained history of accepted Agent Work Results that changed FundOps behavior, including provenance, validation status, preview evidence, and rollback path.
_Avoid_: Invisible file drift; chat-only approval; untraceable local customization

**Application Service**:
The Python workflow-layer boundary that accepts product commands, coordinates validation and durable work, and writes canonical records through platform stores.
_Avoid_: Route handler business logic; UI-owned mutation; direct agent storage write

**Backend Command Intent**:
The explicit product intent attached to a backend command, such as workflow run, strategy change, extension work, universe change, or operational settings change.
_Avoid_: Inferring mutation type from route name; chat text as execution path; one generic command handler

**Completed Workflow Artifact**:
A successfully produced artifact from a workflow capability that remains available as historical output after active workbench state changes.
_Avoid_: Pending queue item; active selection state; deleted work

**Structured Workflow Artifact**:
The schema-versioned machine-readable body of a Completed Workflow Artifact, including its sections, fields, citations, evidence references, and validation state.
_Avoid_: Rendered prose only; HTML as source of truth; reparsed artifact body

**Artifact Kernel**:
The stable required contract every Structured Workflow Artifact carries for identity, artifact type, version, evidence links, validation, provenance, renderability, exportability, and indexing.
_Avoid_: Full writing schema; arbitrary AI JSON; renderer-only convention

**Artifact Writing Template**:
A versioned, testable writing structure that defines artifact body sections, blocks, prompts, and renderer expectations within the Artifact Kernel.
_Avoid_: Core artifact contract; free-form memo prompt; unvalidated schema mutation

**Workspace Extension Proposal**:
A reviewable proposed local extension to FundOps behavior, artifact structure, or workflow capability authored outside normal Strategy Wiring.
_Avoid_: Silent core schema mutation; normal strategy setting; unreviewed coding-agent change

**Extension Pack**:
The complete accepted bundle for a Workspace Extension Proposal, including template contract, prompts, validation, rendering, fixtures, previews, tests, and rollback metadata.
_Avoid_: Standalone schema; prompt-only customization; untested local patch

**Rendered Artifact Snapshot**:
The user-readable representation of a Completed Workflow Artifact generated from its Structured Workflow Artifact for reading or export.
_Avoid_: Canonical artifact body; independent source of truth; regenerated-differently-on-open text

**Retained Workflow Record**:
A durable record of workflow evidence, decisions, artifacts, responses, or outcomes that remains part of the Local FundOps Workspace after current UI state changes.
_Avoid_: Latest-only row; transient UI state; regenerated memory

**Canonical Evidence Record**:
A source-linked retained fact, measurement, claim, citation, user response, or workflow finding that FundOps capabilities may reuse with provenance.
_Avoid_: Function-local datapoint; hidden prompt context; unsupported memory; duplicate evidence copy

**Evidence Family**:
A typed class of Canonical Evidence Records with shared validation, query fields, and interpretation rules.
_Avoid_: Unstructured type string only; workflow-owned evidence silo; one generic payload for all evidence

**Evidence Contract**:
The shared identity, provenance, timing, quality, and linkage fields every Canonical Evidence Record carries regardless of Evidence Family.
_Avoid_: Family-specific provenance; hidden source fields; prompt-only context

**Evidence Source Record**:
The retained identity and provenance for a filing, provider response, web source, document, transcript, or other source from which Canonical Evidence Records are derived.
_Avoid_: Untracked source URL; prompt-only citation; workflow-local source list

**Evidence Source Snapshot**:
A retained raw or normalized capture of source material used to derive, audit, or replay Canonical Evidence Records.
_Avoid_: Mandatory full raw archive for every fetch; source identity only; regenerated source content

**Evidence Source Excerpt**:
A compact retained source span or excerpt sufficient to support a specific Canonical Evidence Record or citation.
_Avoid_: Unsupported quote; whole-document copy by default; citation without backing material

**Evidence Source Retention Tier**:
The retained source depth for an Evidence Source Record, such as identity only, excerpt and hash, normalized payload, or full snapshot.
_Avoid_: One retention rule for all sources; silent raw-data loss; unlimited raw blob retention

**Online Research Evidence Intake**:
The research gateway that turns online sources into Evidence Source Records, Evidence Source Excerpts, Canonical Evidence Records, quality signals, and Execution Provenance before workflows consume them.
_Avoid_: Raw web-search blob; prompt-only research; citation invented after writing

**Research Intake Scope**:
The workflow-provided purpose, allowed topics, entity boundaries, freshness needs, and exclusion rules that guide Online Research Evidence Intake before search begins.
_Avoid_: Broad web crawl; generic company research; summarizer-only filtering

**Online Research Claim**:
A discrete source-backed claim extracted from online research with entity, topic, date or recency context, evidence tier, confidence, and citation support.
_Avoid_: Summary-only research; unsupported prose; source-free current-event claim

**Online Research Claim Validation**:
The quality check that decides whether an Online Research Claim can support workflow conclusions, based on materiality, entity match, source quality, recency, contradiction state, citation support, and claim type.
_Avoid_: Treating every web claim equally; blocking harmless background context; unsupported material conclusion

**Excluded Online Research Claim**:
An Online Research Claim retained with an exclusion reason because it is low-confidence, contradicted, stale, unsupported, or outside the workflow's research scope.
_Avoid_: Accepted evidence; deleted uncertainty; hidden contradiction

**Research Source Hierarchy**:
The source-priority rule for online research where filings, reported financials, and formal company disclosures outrank secondary market commentary for company facts and fundamentals.
_Avoid_: Flat source list; blending contradictory claims; treating news as equal to filings

**Execution Provenance Record**:
The retained record of a model, tool, parser, validation, or workflow step that transformed inputs into evidence, findings, artifacts, or rejected outputs.
_Avoid_: Final artifact only; usage summary; untraceable model claim

**Rejected Generated Output**:
A model, parser, renderer, or workflow output retained for debugging or repair after validation rejected it from becoming a completed artifact or canonical finding.
_Avoid_: Completed Workflow Artifact; silent discard; user-facing result

**Point-in-Time Evidence**:
A Canonical Evidence Record interpreted as it was available to FundOps at a specific workflow moment, with source, as-of, capture, and supersession context preserved.
_Avoid_: Latest-data rewrite; hindsight evidence; source-free replay

**Evidence As-Of Time**:
The business, market, fiscal, filing, or publication time that a Canonical Evidence Record describes.
_Avoid_: Capture time; UI refresh time; workflow run time

**Evidence Capture Time**:
The time FundOps obtained, generated, or retained a Canonical Evidence Record inside the Local FundOps Workspace.
_Avoid_: Fiscal period; provider publication date; market as-of time

**Evidence Supersession**:
The retained relationship showing that later evidence, restatement, correction, remapping, or revised finding changes how earlier evidence should be interpreted without deleting the earlier record.
_Avoid_: Silent overwrite; latest-only correction; hidden restatement

**Workflow Evidence Bundle**:
The frozen set of Point-in-Time Evidence selected for a workflow output, decision, or artifact.
_Avoid_: Latest evidence lookup; copied evidence payload; hidden prompt context

**Evidence Bundle Manifest**:
The retained record of which evidence, versions, sources, configuration, prompts, and inclusion decisions belonged to a Workflow Evidence Bundle.
_Avoid_: Full duplicate archive; latest-only source list; unverifiable citation list

**Current Workflow Projection**:
A derived current view over Retained Workflow Records used to make active screens fast and understandable.
_Avoid_: Source of truth; duplicate workflow history; independent artifact store

**Durable Local Work Record**:
A retained operational record for local FundOps work that may be queued, running, failed, retrying, completed, paused, or continued across app sessions.
_Avoid_: In-memory task; hidden route side effect; unobservable background job

**Local Work Queue**:
The ordered execution surface for Durable Local Work Records that need coordination because they use constrained providers, run long enough to outlive a request, or affect user-visible state.
_Avoid_: Queueing every backend action; per-capability scheduler; process-local queue only; uncoordinated provider-heavy work

**Workflow Run Record**:
The durable record of a workflow execution, including its trigger, status, steps, evidence bundles, outputs, failures, and produced artifacts.
_Avoid_: HTTP request; transient job handle; page-local loading state

**Workflow Step Record**:
The durable record of one stage or operation inside a Workflow Run Record.
_Avoid_: Log line only; hidden async task; untracked agent call

**Active Workflow Workbench State**:
The live in-session queue, selection, progress, and pending work state for a workflow capability.
_Avoid_: Completed Workflow Artifact; historical record; permanent library item

**Abandoned Workflow Work**:
Pending or in-flight workflow work that is intentionally not resumed after a Live FundOps Server Session ends.
_Avoid_: Completed Workflow Artifact; failed investment judgment; deleted historical output

**Workflow Stage Retry**:
An automatic retry attempt for a workflow stage item after that stage fails operationally.
_Avoid_: User reselection; row dismissal; investment judgment

**Workflow Stage Operational Failure**:
The final operational failure state for a workflow stage item after automatic retries are exhausted.
_Avoid_: Failed investment judgment; row dismissal; downstream verdict

**Thesis Intake**:
The Thesis-visible pool of Screener Handoff candidates that have not yet had Thesis generated.
_Avoid_: Completed Thesis; IC Review queue; failed Screener candidates

**Thesis Candidate List**:
The Thesis-visible candidates available for Thesis generation from the current Screener Handoff.
_Avoid_: Failed Screener candidates; IC Review queue; removed research artifact

**Thesis Generation Scope**:
The active Thesis Candidate List whose candidates should receive Completed Thesis artifacts when Thesis runs.
_Avoid_: Thesis Selection; IC Review handoff; selected subset

**Thesis Generation Queue**:
The ordered backlog created from Thesis Generation Scope and scheduled for Thesis execution.
_Avoid_: Thesis Intake; completed Thesis; Screener Review Set; active generation slot

**Active Thesis Generation**:
The small subset of the Thesis Generation Queue currently being researched and written.
_Avoid_: Thesis Generation Queue; Thesis Candidate List; completed Thesis

**Pending Thesis Row**:
A visible Thesis table row for a queued candidate whose Completed Thesis has not been generated yet.
_Avoid_: Completed Thesis; failed Thesis; unselected Thesis Candidate

**Thesis Generation Retry**:
An automatic retry attempt for a queued Thesis candidate after generation fails operationally.
_Avoid_: User reselection; Thesis Dismissal; IC Review retry

**Thesis Generation Failure**:
The final operational failure state for a queued Thesis candidate after automatic retries are exhausted.
_Avoid_: Failed investment judgment; Thesis Dismissal; IC Verdict

**Thesis Run**:
A capability-local execution that generates Thesis artifacts without automatically executing downstream capabilities.
_Avoid_: Pipeline Run; IC Review run; Memo generation

**Thesis Run Resume**:
The continuation of an interrupted or partially completed Thesis Run within the same Live FundOps Server Session.
_Avoid_: New Thesis Run; historical completed Thesis; Pipeline Run

**New Thesis Run**:
A fresh Thesis execution created from a new active Thesis Intake after a new Screener Run or a new Live FundOps Server Session.
_Avoid_: Thesis Run Resume; daily regeneration; historical artifact refresh

**Completed Thesis**:
A short generated investment argument used to judge whether a Screener Candidate has enough merit to deserve IC Review.
_Avoid_: Thesis Candidate; IC Review verdict; Investment Memo; full research memo

**Thesis Research Scope**:
The fixed set of research questions a Completed Thesis answers before an opportunity can deserve IC Review.
_Avoid_: Investment Memo outline; configurable Thesis section list; full company report

**Thesis Research Emphasis**:
The Constitution-derived focus that tells Thesis which evidence and framing matter most inside the fixed Thesis Research Scope.
_Avoid_: Hidden screening rule; user-configured section set; IC Gate scoring model

**Thesis Return Potential**:
The raw estimated upside or expected return profile a Completed Thesis presents as the opportunity.
_Avoid_: IC Conviction; realized return; portfolio target

**Thesis Return Potential Component**:
A retained source contribution that explains the raw Thesis Return Potential percentage.
_Avoid_: IC Score; IC Verdict; unexplained upside

**IC Conviction**:
The IC Gate score for whether the Completed Thesis is credible, likely enough, and strong enough to justify Memo spend.
_Avoid_: Thesis Return Potential; IC Verdict; portfolio conviction

**IC Constitution Fit**:
The IC Gate score for how well the Completed Thesis and opportunity align with the active Constitution's strategy criteria, North Star, and preferences.
_Avoid_: Screening Requirement pass/fail; Thesis Selection Ranking; IC Verdict

**IC Data Quality**:
The IC Gate score for whether the Completed Thesis is based on fresh, grounded, complete, and internally consistent evidence.
_Avoid_: IC Conviction; Thesis Return Potential; data availability alone

**IC Gate Scoring Model**:
The measurable scoring approach IC Gate uses to produce IC Conviction, IC Constitution Fit, and IC Data Quality before making an IC Verdict.
_Avoid_: Thesis worker scoring; free-form prose judgment; hidden AI preference

**IC Gate Score**:
The blended 0-100 memo-worthiness score IC Gate computes from IC Conviction, IC Constitution Fit, and IC Data Quality after Hard IC Hurdles are evaluated.
_Avoid_: Thesis Selection Score; IC Verdict; portfolio allocation score

**IC Gate Score Blend**:
The Constitution-owned top-level weighting used to combine IC Conviction, IC Constitution Fit, and IC Data Quality into the IC Gate Score.
_Avoid_: IC Score Component Weight; Screener Ranking Blend; hidden backend preference

**IC Pass Cutoff**:
The minimum IC Gate Score required for an automated IC Pass after Hard IC Hurdles are satisfied.
_Avoid_: IC Hurdle; Memo capacity cap; Thesis Selection Count

**IC Score**:
A normalized 0-100 score produced by the IC Gate Scoring Model for a qualitative IC Gate judgment.
_Avoid_: Thesis Return Potential; raw metric value; IC Verdict

**IC Score Component**:
An auditable subcomponent that contributes to an IC Score.
_Avoid_: Free-form prose reason; hidden model preference; downstream verdict

**Unknown IC Score Component**:
An IC Score Component that lacks enough evidence to measure confidently in the current IC Review Evidence Package.
_Avoid_: Failed criterion; zero score; excluded component

**Contradicted IC Score Component**:
An IC Score Component whose available evidence materially conflicts or undermines the claimed signal.
_Avoid_: Unknown IC Score Component; neutral score; unsupported claim

**IC Score Component Weight**:
The fixed internal weighting used to combine IC Score Components into an IC Score.
_Avoid_: User-facing ranking preference; Thesis Selection Ranking; Strategy Criterion weight

**IC Constitution Fit Component**:
An IC Score Component that explains part of the IC Constitution Fit score.
_Avoid_: Hidden screening rule; IC Verdict; free-form strategy vibe

**IC Data Quality Component**:
An IC Score Component that explains part of the IC Data Quality score.
_Avoid_: Investment conviction; return potential; unsupported trust label

**IC Conviction Component**:
An IC Score Component that explains part of the IC Conviction score.
_Avoid_: Thesis Return Potential; IC Data Quality; IC Verdict

**Completed Thesis Detail**:
The expanded quick-view surface for a Completed Thesis row.
_Avoid_: Company Page; Investment Memo; IC Review detail

**Completed Thesis Return Profile Panel**:
The Completed Thesis Detail panel that shows the key return-profile data used to rank the Thesis for IC Review.
_Avoid_: Full Thesis prose; Company Page; IC Review scorecard

**Completed Thesis Prose Panel**:
The Completed Thesis Detail panel that shows a short prose summary of the Thesis writeup.
_Avoid_: Investment Memo; full Company Page dossier; raw data strip

**Thesis Opportunity Explanation**:
The concise explanation of why a Completed Thesis opportunity exists and may be worth attention.
_Avoid_: Ranking explanation; IC Verdict rationale; full Investment Memo

**Thesis Ranking Explanation**:
The explanation of why a Completed Thesis ranked where it did within Thesis Selection Ranking.
_Avoid_: Thesis Opportunity Explanation; IC Verdict rationale; default table column

**Completed Thesis Table**:
The ranked table of Completed Thesis artifacts visible in the Thesis capability.
_Avoid_: Screener Result Table; IC Review queue; full Memo list

**Thesis Review Action**:
A row-level user action that adjusts Thesis handling or next-stage selection without changing the Thesis Selection Ranking.
_Avoid_: Strategy change; hidden reranking; IC Review verdict

**Thesis Promotion**:
A Thesis Review Action that includes a Completed Thesis in Thesis Selection.
_Avoid_: IC Review verdict; changed Thesis Selection Ranking; Memo approval

**Thesis Dismissal**:
A Thesis Review Action that excludes a Completed Thesis from Thesis Selection for the current run while keeping it in Remaining Theses.
_Avoid_: Failed Thesis; IC Review rejection; deleted research artifact

**Thesis Selection Addition**:
The selection feedback record created when a Completed Thesis is manually added to Thesis Selection.
_Avoid_: IC Review verdict; Memo approval; changed Thesis Selection Ranking

**Thesis Selection Removal**:
The neutral feedback record created when a Completed Thesis is removed from Thesis Selection.
_Avoid_: Failed Thesis; IC Review rejection; deleted research artifact

**Workflow Funnel**:
The staged narrowing of opportunities as each capability performs deeper work and passes fewer candidates onward.
_Avoid_: One-off ranking; static watchlist; arbitrary batch size

**Workflow Stage Selection**:
The current subset of ranked stage outputs chosen to advance to the next workflow capability.
_Avoid_: Stage ranking; capability verdict; deleted item

**Workflow Stage Execution Action**:
The capability-local action that runs a workflow stage's function for eligible active stage intake items.
_Avoid_: Row promotion; downstream execution; Run Full Pipeline

**Workflow Stage Handoff**:
The movement of selected stage outputs into the next workflow capability's active workbench.
_Avoid_: Executing the next capability; final approval; hidden reranking

**Workflow Stage Selection Count**:
The current number of items a workflow stage selected block tries to keep when enough eligible items remain.
_Avoid_: Ranking score; fixed system-wide constant; row dismissal

**Remaining Stage Items**:
The ranked stage outputs not currently included in Workflow Stage Selection.
_Avoid_: Failed items; hidden backlog; rejected investments

**Workflow Stage Promotion**:
A row-level action that includes a ranked stage output in Workflow Stage Selection.
_Avoid_: Changed ranking; downstream verdict; automatic execution

**Workflow Stage Dismissal**:
A row-level action that excludes a ranked stage output from Workflow Stage Selection while keeping it visible as a remaining item.
_Avoid_: Failed item; deletion; changed ranking

**Workflow Stage Selection Feedback**:
The retained record of a Workflow Stage Promotion or Workflow Stage Dismissal.
_Avoid_: Ranking component; downstream verdict; strategy change

**Thesis Selection**:
The completed Thesis artifacts chosen to advance from Thesis into IC Review.
_Avoid_: Thesis Generation Queue; Top Picks; IC Review verdict

**Thesis Selection Count**:
The number of completed Thesis artifacts the Thesis selected block tries to advance to IC Review when enough eligible completed Theses remain.
_Avoid_: Thesis Generation concurrency; fixed IC capacity; row dismissal

**Remaining Theses**:
The completed Thesis artifacts that were ranked but not included in Thesis Selection.
_Avoid_: Thesis Candidate List; failed Thesis; IC Review rejection

**Thesis Selection Ranking**:
The ordering of completed Thesis artifacts used to decide which Theses advance to IC Review.
_Avoid_: Raw expected return sort; IC Review verdict; Screener Ranking

**Thesis Selection Ranking Model**:
The simple, auditable model used to rank completed Thesis artifacts for IC Review based on return profile rather than memo-worthiness judgment.
_Avoid_: IC Gate Scoring Model; hidden AI preference; Screener Ranking Blend

**Thesis Selection Ranking Component**:
A saved Thesis fact or contribution used to explain a completed Thesis artifact's selection rank.
_Avoid_: Unsupported prose claim; IC Review score; Screener Ranking Component

**Thesis Selection Score**:
The simple return-profile ranking score produced from Thesis Selection Ranking Components for ordering Completed Thesis artifacts.
_Avoid_: Visible default table column; IC Verdict; standalone investment decision

**Thesis Selection Score Cap**:
A maximum Thesis Selection Score imposed when the return profile is too weak or unsupported to deserve automatic IC Review.
_Avoid_: IC Verdict; hard Screening Requirement; deleted Thesis

**Thesis Selection Score Cap Threshold**:
The fixed global threshold at which a weak or unsupported return profile imposes a Thesis Selection Score Cap.
_Avoid_: Strategy setting; user-facing ranking preference; IC hurdle

**IC Review**:
The workflow capability that stress-tests a Completed Thesis and produces an IC Verdict before Memo spend.
_Avoid_: Thesis Selection; Memo approval; portfolio decision

**IC Review Evidence Package**:
The inputs IC Review must consider for an opportunity: Completed Thesis prose, Thesis Return Potential and return components, key Thesis evidence notes, the active Constitution, and explicit IC hurdles.
_Avoid_: Thesis Selection Ranking alone; Screener metrics alone; Memo draft

**IC Review Intake**:
The Completed Thesis artifacts handed off from Thesis Selection and eligible for IC Review.
_Avoid_: All Completed Theses; Memo handoff; Screener Candidate list

**IC Review Run**:
A capability-local execution that produces IC Verdicts for every eligible item in IC Review Intake without automatically executing Memo.
_Avoid_: Thesis Run; Memo generation; manual IC Override

**IC Review Table**:
The scan-first table of opportunities in IC Review.
_Avoid_: IC Review Detail; Company Page; Memo Intake

**IC Review Summary Row**:
The collapsed IC Review Table row that shows only the minimum information needed to identify the opportunity and see the IC path.
_Avoid_: IC Detail Evidence Snapshot; full scorecard; memo thesis preview

**IC Hurdle**:
An explicit Constitution-owned memo-worthiness condition IC Review applies when deciding whether a Completed Thesis deserves Memo spend.
_Avoid_: Thesis Selection Ranking Model; soft Screener preference; Portfolio allocation rule

**Hard IC Hurdle**:
The default form of IC Hurdle: a memo-worthiness gate that must be satisfied for an automated IC Pass.
_Avoid_: Ranking preference; advisory warning; hidden score boost

**IC Hurdle Miss**:
An IC Semantic Thesis Review finding that a Hard IC Hurdle was truly not satisfied by the evidence package.
_Avoid_: Operational failure; user override; low table rank

**IC Semantic Thesis Review**:
The interpretive IC Review step that reads and understands the Completed Thesis argument before producing IC scores, hurdle findings, and an IC Verdict.
_Avoid_: Numeric threshold only; reranking; Memo writing

**IC Verdict**:
The pass or fail outcome that determines whether an opportunity follows the Memo path after IC Review.
_Avoid_: Thesis Selection Ranking; Memo approval; portfolio decision

**Saved IC Verdict Evidence**:
The frozen evidence snapshot stored with an IC Verdict so the decision remains explainable after Thesis artifacts, strategy, or market data change.
_Avoid_: Live lookup only; latest ticker state; memo content

**IC Review Detail**:
The expanded quick-view surface for an IC-reviewed row.
_Avoid_: Company Page; Investment Memo; Completed Thesis Detail

**IC Detail Evidence Snapshot**:
The compact evidence bundle shown inside IC Review Detail: short verdict rationale, hard hurdle state, IC Conviction, IC Constitution Fit, and IC Data Quality.
_Avoid_: Full IC review writeup; key-risk section; full Completed Thesis; Company Page dossier

**IC Verdict Rationale**:
The concise explanation of why IC Review produced an IC Pass or IC Fail.
_Avoid_: Full IC review writeup; Thesis Ranking Explanation; portfolio decision rationale

**IC Pass**:
An IC Verdict that allows the opportunity to move toward Memo generation.
_Avoid_: Thesis Selection; buy decision; completed Memo

**IC Fail**:
An IC Verdict that stops the opportunity from moving toward Memo generation by default.
_Avoid_: Thesis Dismissal; deleted Thesis; permanent blacklist

**IC Review Retry**:
An automatic retry attempt for an IC Review item after IC Review fails operationally.
_Avoid_: IC Promotion; IC Removal; IC Fail

**IC Review Failure**:
The final operational failure state for an IC Review item after automatic retries are exhausted.
_Avoid_: IC Fail; IC Override; deleted Thesis

**IC Override**:
A user-created IC Verdict that sets or replaces the IC path for a ticker.
_Avoid_: Hidden AI verdict; changed Thesis Ranking; Memo approval

**IC Selection**:
The IC-reviewed opportunities currently selected to advance from IC Review into Memo.
_Avoid_: All IC Review Intake; Completed Thesis Selection; buy list

**Remaining IC Reviews**:
The IC-reviewed candidate list not currently included in IC Selection.
_Avoid_: Deleted opportunities; permanent blacklist; failed Screener candidates

**IC Promotion**:
An IC Review action that creates an IC Override to IC Pass and includes the opportunity in IC Selection.
_Avoid_: Automated IC Pass; changed Thesis Selection Ranking; Memo approval

**IC Removal**:
An IC Review action that excludes an opportunity from IC Selection by creating an IC Override to IC Fail.
_Avoid_: Deleted research; Screener dismissal; portfolio sell decision

**Memo**:
The workflow capability that turns IC-selected opportunities into long-form memo artifacts.
_Avoid_: IC Review; Company Page; portfolio decision

**Memo Intake**:
The IC Selection made available to Memo after IC Review.
_Avoid_: IC Review execution; all IC Review Intake; Completed Memo

**Completed Memo**:
A long-form post-IC artifact that combines company research depth with investment-oriented analysis for one IC-selected opportunity.
_Avoid_: Separate Research Memo and Investment Memo pair; IC Verdict; portfolio decision

**Pipeline Orchestration**:
The capability that coordinates multi-stage workflow execution, stage handoffs, queueing, retries, and produced records across Screener, Thesis, IC Review, and Memo while preserving each stage's own product contract.
_Avoid_: Monolithic super-agent; hidden auto-execution; replacing capability-local runs; bypassing stage selection

**Pipeline Run**:
A Run Full Pipeline execution that starts with Screener and continues through downstream capabilities using each stage's handoff.
_Avoid_: Screener Run; row promotion; Strategy Chat setup

**Constitution**:
The canonical investment strategy that downstream workflow capabilities use as their source of truth.
_Avoid_: Prompt preferences; temporary chat memory; one-off settings

**Constitution Version**:
An approved immutable snapshot of the Constitution used to explain, replay, and compare workflow behavior over time.
_Avoid_: In-place strategy mutation; hidden current settings

**Constitution Diff**:
A human-readable and machine-readable comparison between two Constitution Versions.
_Avoid_: Bare version number; unexplained strategy change

**Constitution Reset**:
A destructive user-initiated maintenance action that removes the active Constitution so FundOps can start strategy setup over.
_Avoid_: Strategy Change Proposal; Constitution Version; normal strategy edit; Learning Recommendation Acceptance

**Strategy Change Proposal**:
A reviewable proposed change to the Constitution created by Strategy Chat or the learning loop before any workflow settings are wired.
_Avoid_: Silent strategy update; unversioned tweak; direct settings mutation

**Strategy Proposal Envelope**:
The stable review and lifecycle wrapper around a Strategy Change Proposal, including approval state, validation state, evidence status, wiring preview, rationale, and source links.
_Avoid_: Rigid full strategy schema; raw model response; executable settings payload

**Strategy Draft**:
A non-active conversational draft of what FundOps thinks the user wants before asking for approval.
_Avoid_: Saved strategy; active Constitution; hidden auto-save

**Strategy Draft Summary**:
The plain-English explanation inside a Strategy Draft that tells the user what FundOps thinks their strategy means.
_Avoid_: Raw rules only; jargon-only contract

**Strategy Draft Rules**:
The exact criteria inside a Strategy Draft that FundOps would use if the user approves it.
_Avoid_: Hidden machine criteria; vague prose-only promise

**Strategy Draft Wiring Preview**:
The derived per-capability explanation inside a Strategy Draft that shows how the proposed Constitution would affect FundOps workflows if approved.
_Avoid_: Vague impact summary; hidden wiring; independent settings source; post-approval surprise

**Strategy Draft Format**:
The standard presentation structure used when Strategy Chat asks the user to approve a Strategy Draft.
_Avoid_: Unstructured proposal; missing tradeoffs; hidden approval consequences

**Strategy Change Format**:
The compact presentation structure used when Strategy Chat asks the user to approve a focused post-setup change.
_Avoid_: Full setup draft for tiny edits; hidden affected workflow; missing tradeoff

**Strategy Readiness Check**:
The plain-language completeness judgment that Strategy Chat uses before it is allowed to show a Strategy Draft.
_Avoid_: Fixed number of chat turns; survey checklist; premature save

**Strategy Proposal Acceptance**:
An explicit user confirmation that a Strategy Change Proposal should become a new active Constitution Version.
_Avoid_: Ambiguous apply button; silent activation; accidental settings change

**Strategy Approval Prompt**:
The explicit request asking the user to approve a Strategy Draft or proposed Constitution change.
_Avoid_: Looks good?; should I continue?; vague confirmation

**Current Pending Draft**:
The single latest Strategy Draft that is still awaiting the user's approval or requested changes.
_Avoid_: Any old draft; ambiguous pending proposal; hidden approval target

**Draft Revision**:
An updated Strategy Draft created after the user corrects, rejects, or tweaks a pending draft.
_Avoid_: Defending the old draft; random patch; saving rejected interpretation

**Draft Cancellation**:
The user intentionally abandons a pending Strategy Draft without saving or wiring it.
_Avoid_: Hidden approval target; resurrected old draft; silent activation

**Live Strategy Chat Session**:
The active Strategy Chat continuity while the local FundOps app is still running.
_Avoid_: Durable memory; permanent conversation identity; new chat after tab switch

**Strategy Continuation Memory**:
The prior strategy context available after the local FundOps app has been stopped and started again.
_Avoid_: Pretending a restarted app is the same live chat; forgetting prior strategy context

**Strategy Activation Confirmation**:
The short message shown after an approved strategy change is saved and wired.
_Avoid_: Repeating the full draft; duplicate proposal summary; silent success

**Strategy Exploration**:
A non-committal discussion where the user is thinking through a possible strategy idea without asking FundOps to change settings yet.
_Avoid_: Automatic draft; accidental criterion addition; premature wiring

**Strategy Status Answer**:
A read-only answer about the current Constitution or workflow settings.
_Avoid_: Change proposal; draft; activation

**Conversation Evidence**:
The archived original chat messages retained for audit, history, and source lookup.
_Avoid_: Primary working memory; repeatedly reread prompt context

**Structured Strategy Memory**:
The extracted durable facts that FundOps uses as normal recall and operating memory.
_Avoid_: Raw chat transcript as memory; model-only memory; unstructured recall

**Strategy Tradeoff Explanation**:
A balanced explanation of what a contemplated criterion may improve, what it may narrow, and what false signals it may introduce.
_Avoid_: One-sided recommendation; more criteria is always better; unexplained filter creep

**Restrictiveness Warning**:
A warning that a wireable strategy combination may be unusually narrow, rare, or dependent on market conditions.
_Avoid_: Blocking user choice; pretending rare means impossible; silent zero-result risk

**Inferred Strategy Intent**:
The plain-language interpretation of what specific criteria imply about the kind of companies or opportunities the user wants.
_Avoid_: Replacing user criteria; judging the strategy; vague style label without evidence

**Strategy North Star**:
The durable plain-language strategic aim that summarizes what the user's criteria and preferences are trying to find.
_Avoid_: Single hard threshold; generic investor label; hidden model memory

**Strategy Intent Mismatch**:
A conflict between the user's plain-English strategy label and the specific criteria they are choosing.
_Avoid_: Silently preserving inconsistent prose; ignoring specific criteria; false coherence

**Strategy Self-Discovery**:
The process where a user's stated strategy becomes clearer or changes as Strategy Chat helps them make choices.
_Avoid_: Treating the first label as a fixed contract; framing evolution as error

**Strategy Proposal Guardrail**:
A deterministic validation check that prevents malformed, unsupported, or inconsistent strategy proposals from becoming active.
_Avoid_: Trusting AI output directly; prose-only validation

**Strategy Proposal Evidence Check**:
The Strategy Chat preparation step that verifies relevant evidence before drafting when a desired strategy depends on market reality, universe membership, or data availability.
_Avoid_: Researching every chat turn; unsupported confident proposal; post-approval surprise

**Strategy Wiring**:
The deterministic activation step that projects an accepted Strategy Change Proposal into workflow settings.
_Avoid_: AI-applied settings; direct chat mutation; independent settings truth

**Wiring Capability Boundary**:
The set of workflow settings and criteria that FundOps can actually project and activate.
_Avoid_: Offering impossible wiring; hallucinated setting; unsupported activation promise

**Strategy Criterion**:
A typed, measurable, or explicitly enumerable rule inside the Constitution that can be deterministically evaluated or projected into workflow settings.
_Avoid_: Vague preference; prose-only trait; aesthetic label

**Rule Rationale**:
The saved explanation for why a Strategy Criterion or projected workflow setting exists.
_Avoid_: Reconstructing intent from model memory; reason hidden only in chat transcript

**Rule Source**:
The saved link from a Strategy Criterion or projected workflow setting back to the proposal, chat turn, or version event that created it.
_Avoid_: Untraceable setting; orphaned rule; "AI said so"

**Version Rationale**:
The saved explanation for why a Constitution Version was created.
_Avoid_: Bare version number; unexplained batch of changes

**Unsupported Criterion**:
A user-desired rule or preference that FundOps cannot currently evaluate deterministically with available data.
_Avoid_: Silently ignored preference; hallucinated measurable rule

**Strategy Preference Memory**:
Saved user investment preferences that are not wireable Strategy Criteria and are not part of the active executable Constitution.
_Avoid_: Active setting; continuously displayed missing requirement

**Proxy Criterion**:
A measurable substitute offered when the user's desired criterion cannot be directly evaluated with available data.
_Avoid_: Pretending proxy equals the original criterion

**Data Support Level**:
The degree to which a Strategy Criterion can be evaluated from available data sources.
_Avoid_: Binary supported/unsupported when a proxy or manual review path exists

**Research Review Criterion**:
A user preference that should influence Thesis or IC Review analysis but should not be used as an automatic screen or gate.
_Avoid_: Automatic numeric rule; unsupported active setting

**Observable Signal**:
A user-understandable evidence point that FundOps can actually inspect through its supported data and research pipeline.
_Avoid_: Generic trait; aspirational label; unsupported proxy

**Interpretation Layer**:
A novice-friendly explanation shown alongside Strategy Criteria to describe plain-English intent, tradeoffs, and expected workflow behavior.
_Avoid_: Hidden criteria; unexplained financial jargon; raw thresholds without meaning

**Strategy Change Explanation**:
Well-drafted prose that explains a proposed or activated strategy change using human summary, exact criteria, and workflow impact.
_Avoid_: Raw list of fields; config dump; unexplained diff

**Strategy Metadata Panel**:
The centered Strategy Chat card that summarizes the active Constitution after setup.
_Avoid_: Duplicate current strategy card; raw settings table; onboarding copy after setup

**Capability Wiring Panel**:
The Strategy Chat inspection surface for how the active Constitution configures one workflow capability.
_Avoid_: Operational results page; hidden settings dump; duplicate wiring card

**Capability Wiring Summary**:
The compact read-only summary shown in a workflow capability chip, dropdown, or panel header to describe that capability's current Settings Projection.
_Avoid_: Editable control; transient UI copy; separate settings source

**Settings/Config**:
The operational control surface for provider setup, data-source health, model and usage controls, schedules, data export, and reset actions.
_Avoid_: Constitution editor; manual workflow-tuning surface; screener-filter source of truth; strategy setup

**Settings Visit**:
A low-frequency user visit to Settings/Config for setup, verification, troubleshooting, maintenance, or data ownership tasks.
_Avoid_: Daily workflow; investment review session; research workspace

**Settings Job Group**:
A user-understandable grouping of Settings/Config tasks around a maintenance job rather than an implementation subsystem.
_Avoid_: Raw config section; backend module tab; workflow tuning category

**Settings Health Summary**:
The compact first-view Settings/Config summary of whether FundOps is operationally ready.
_Avoid_: Dashboard; workflow attention queue; exhaustive system status page

**Settings Operational Explanation**:
A short Settings/Config explanation that clarifies operational impact, capability limits, or destructive-action scope before the user acts.
_Avoid_: Product onboarding; investment workflow tutorial; long-form documentation

**Operational Settings Change**:
A user-initiated Settings/Config change to operational setup such as providers, credentials, models, usage controls, schedules, export, or reset actions.
_Avoid_: Strategy Change Proposal; Learning Recommendation; hidden workflow tuning

**Local Credential Store**:
The user's operating-system credential store used to hold provider API keys and other secrets outside the Local FundOps Workspace.
_Avoid_: Workspace Archive; FundOps data export; plain settings row

**Workspace Secret Reference**:
A non-secret retained pointer showing which configured provider credential FundOps should request from the Local Credential Store.
_Avoid_: API key; copied credential; backup-contained secret

**Data Source Setup**:
The Settings/Config area for configuring provider credentials, provider selection, capability tier, and manual provider health checks.
_Avoid_: Workflow failure inbox; data-gap triage queue; workflow evidence status

**Web Research Capability Setup**:
The Settings/Config setup for whether FundOps can search and read web sources during research workflows.
_Avoid_: Standalone workflow; Library search; Archive Q&A

**AI Model Setup**:
The Settings/Config area for choosing the AI provider, model, endpoint, credentials, and manual AI connection test.
_Avoid_: Strategy setting; Constitution Version; workflow-specific prompt tuning

**AI Usage Record**:
The retained evidence for one AI call, including model name, input tokens, output tokens, workflow capability, and time.
_Avoid_: Estimated bill line item; prompt content archive; investment result

**AI Usage Summary**:
The Settings/Config view that aggregates AI Usage Records by model, token usage, workflow capability, and time period.
_Avoid_: Authoritative bill; exact cost ledger; strategy performance metric

**Estimated AI Cost**:
A non-canonical dollar approximation derived from model and token usage when reliable pricing metadata is available.
_Avoid_: Billing source of truth; budget enforcement proof; durable accounting record

**AI Usage Warning**:
A non-blocking Settings/Config signal that AI usage is high or has crossed a user-visible threshold.
_Avoid_: Hard workflow stop; billing enforcement; hidden quota

**Schedule Setup**:
The Settings/Config area for choosing when recurring FundOps workflow runs should execute, pause, resume, or remain manual.
_Avoid_: Dashboard work queue; workflow result status; strategy cadence preference

**Schedule Preset**:
An initial Schedule Setup starting point that sets a coherent recurring workflow cadence the user can later customize.
_Avoid_: Locked automation mode; strategy preference; hidden behavior permission

**FundOps Data Export**:
A user-initiated Settings/Config action for downloading retained FundOps data for inspection, backup, or portability.
_Avoid_: Workflow artifact reader; Dashboard report; selective ticker export

**Workspace Archive**:
A portable backup or restore package for a Local FundOps Workspace containing retained data, artifacts, source snapshots, render outputs, and workspace version metadata.
_Avoid_: Retail Artifact PDF; single-artifact export; raw database dump without metadata

**Pipeline Data Clear**:
A destructive user-initiated maintenance action that removes generated workflow run outputs while preserving durable strategy and portfolio source records.
_Avoid_: Constitution Reset; portfolio deletion; hidden server restart cleanup

**Destructive Settings Action**:
A Settings/Config maintenance action that deletes, clears, resets, or irreversibly changes retained FundOps state.
_Avoid_: Normal settings save; workflow action; hidden cleanup

**Strategy Lens**:
A non-exclusive grouping of Strategy Criteria used to seed or organize a strategy style.
_Avoid_: Fixed archetype; mutually exclusive investor identity

**Starter Template**:
An optional default set of Strategy Criteria that a user can accept, modify, combine, or reject.
_Avoid_: Mandatory strategy; hard-coded investor type

**Settings Projection**:
A deterministic per-capability compilation of the Constitution into concrete workflow behavior.
_Avoid_: AI wiring agent; separately authored settings truth; user-edited second source of truth

**Review Item**:
An ambiguity or missing decision that must be shown to the user before derived settings become active.
_Avoid_: Hallucinated default; silent assumption

**Clarifying Prompt**:
A single broad follow-up question used when the user's strategy language could mean several different things.
_Avoid_: Survey; interrogation; premature default

**Learning/Evals**:
The product capability that turns user behavior, workflow evidence, thesis-health history, and investment outcomes into auditable evaluations and reviewable strategy-calibration recommendations.
_Avoid_: Raw backtest; price-only performance page; silent model memory; automatic strategy mutation

**Strategy Calibration**:
A reviewable adjustment to how the active Constitution or workflow criteria express the user's investment strategy based on observed evidence.
_Avoid_: Autonomous strategy rewrite; market-timing call; proving the future from the past

**Learning Evaluation Window**:
A fixed elapsed-time checkpoint used by Learning/Evals to compare retained workflow evidence with later thesis-health and outcome evidence.
_Avoid_: Arbitrary backtest period; strategy-specific hidden horizon; price-check reminder

**Outcome Evaluation**:
A structured Learning/Evals judgment for one company at one Learning Evaluation Window that combines realized performance, benchmark-relative performance, thesis-health state, and goal-alignment evidence.
_Avoid_: Raw return only; price-only winner/loser label; proof that the original strategy was right or wrong

**Outcome Horizon Context**:
The intended return path or holding-period context used by Learning/Evals to interpret an Outcome Evaluation Window.
_Avoid_: Same-window judgment for every strategy; treating early underperformance as automatic failure; ignoring stated horizon

**Outcome Evaluation Result**:
The qualitative Learning/Evals classification of an Outcome Evaluation as thesis worked, right thesis slow market, lucky result, or thesis failed.
_Avoid_: Win/loss label; price-only grade; deterministic proof of skill

**No Clear Learning Signal**:
An Outcome Evaluation Result where the evidence does not support a responsible strategy, pipeline, or investor-learning inference.
_Avoid_: Forced lesson; overfit explanation; treating every price move as meaningful

**No Clear Learning Signal Reason**:
The high-level explanation for why an Outcome Evaluation does not support a responsible learning inference.
_Avoid_: Overbuilt taxonomy; hidden uncertainty; pretending no-signal means no outcome

**Outcome Driver Evidence**:
Source-backed evidence explaining what drove an Outcome Evaluation, such as earnings, filings, business developments, sector or macro catalysts, valuation rerating, or thesis-driver deterioration.
_Avoid_: Generic news reaction; unsupported return story; price movement with no causal evidence

**Learning Evidence Pattern**:
A repeated source-backed relationship across multiple Outcome Evaluations that connects initial workflow evidence, later thesis-health state, return path, outcome-driver evidence, or user feedback.
_Avoid_: Single-company anecdote; raw correlation; model-only inference; one noisy market move

**Learning Association**:
A discovered relationship between retained evidence and later outcomes that may be useful even before FundOps has a complete thesis-grounded explanation for why it exists.
_Avoid_: Strategy rule; causal proof; ignored unexplained pattern; automatic recommendation

**Learning Pattern Sufficiency**:
The judgment that a Learning Evidence Pattern has enough comparable datapoints, directional consistency, evidence quality, and source-backed explanation to support a responsible inference.
_Avoid_: Magic count threshold; one-off anecdote; correlation without evidence quality; false precision

**Learning Confidence Label**:
A qualitative confidence label for Learning/Evals interpretation, such as exploratory, promising, recommendation-ready, superseded, or inconclusive.
_Avoid_: Fake precision; unexplained numeric confidence; opaque score

**Learning Pattern Data Support**:
The deterministic evidence-quality check for a Learning Evidence Pattern, including datapoint count, comparable windows, retained metrics, cited sources, and missing-field state.
_Avoid_: AI-only confidence; unsupported sample; hidden missing data

**Learning Pattern Interpretation**:
The AI-assisted investment judgment about whether a Learning Evidence Pattern is coherent, comparable, plausibly causal, and useful for strategy calibration.
_Avoid_: Mechanical correlation; opaque confidence; unsupported model intuition

**Learning Version Scope**:
The Constitution Version relationship used when judging a Learning Evidence Pattern, with same-version evidence strongest, materially related versions useful with caveats, and unrelated older versions exploratory.
_Avoid_: Mixing all history as equivalent; ignoring strategy changes; current-strategy-only amnesia

**Learning Cohort Context**:
The company, strategy, and thesis context where a Learning Evidence Pattern applies, such as sector, business model, market cap, strategy version, thesis type, holding horizon, or catalyst type.
_Avoid_: Global lesson from unlike companies; metric meaning without context; one-size-fits-all inference

**Discovered Strategy Signal**:
A retained metric, metric trend, or evidence pattern that was not necessarily part of the active Constitution but appears repeatedly linked to desired Outcome Evaluation Results, better strategy fit, or durable thesis health.
_Avoid_: Hidden active criterion; automatic screen rule; data-mined fact without review

**Recommendation-Ready Signal**:
A Discovered Strategy Signal with enough repeated, directional, source-backed evidence to justify a Learning Recommendation.
_Avoid_: Interesting correlation; single-window anomaly; unsupported metric promotion

**Learning Recommendation Scope**:
The allowed behavior surface a Learning Recommendation may propose changing: Strategy Criteria, Research Review Criteria, Screener ranking, IC emphasis, Thesis questions, Memo questions, or Thesis Watch Items.
_Avoid_: Portfolio action; trade instruction; autonomous buy/sell recommendation; hidden workflow mutation

**Learning Recommendation Escalation**:
The preference for proposing the least aggressive useful Learning Recommendation before turning a discovered signal into a hard Strategy Criterion.
_Avoid_: Immediate hard filter; overfitting response; skipping review-oriented changes

**Learning Recommendation Evidence Card**:
The Dashboard Decision Item presentation for a Learning Recommendation, showing the proposed change, supporting companies, initial metrics, evaluation windows, thesis-health evidence, outcome-driver evidence, confidence, caveats, and response actions.
_Avoid_: Bare suggestion; unexplained recommendation; hidden evidence; automatic activation

**Learning Teaching Note**:
A short plain-language explanation inside a Learning Recommendation Evidence Card that explains what the pattern may mean for the user's investing judgment.
_Avoid_: Lecture; generic investing education; unexplained settings diff; overconfident lesson

**Idle Learning Analysis**:
Background Learning/Evals pattern analysis that runs only when higher-priority workflow work and provider requests are not queued or running.
_Avoid_: Interactive workflow run; work-queue blocker; always-on expensive analysis; hidden behavior mutation

**AI-Assisted Pattern Analysis**:
LLM-supported Learning/Evals analysis that proposes possible Learning Evidence Patterns from retained workflow evidence and source-backed enrichment.
_Avoid_: Deterministic-only metric scan; unsupported model intuition; automatic strategy rewrite

**Learning Recommendation**:
A suggested Strategy Change Proposal based on observed workflow results, investment outcomes, or user behavior.
_Avoid_: Automatic Constitution rewrite

**Thesis-Grounded Learning Recommendation**:
A Learning Recommendation whose proposed behavior change is supported by a Learning Association, cohort context, filing-first evidence, and a plausible investment rationale tied to thesis durability or return path.
_Avoid_: Hard rule from unexplained correlation; fake causal certainty; black-box strategy mutation

**Empirical Strategy Signal**:
A user-accepted Strategy Criterion or ranking factor based on observed association rather than a thesis-grounded investment rationale.
_Avoid_: Fake thesis rationale; hidden black-box rule; unsupported wireability

**Learning Recommendation Acceptance**:
The explicit Dashboard decision that approves a Learning Recommendation before it changes FundOps behavior.
_Avoid_: Silent learning update; background behavior mutation; global permission toggle

**Learning Recommendation Response**:
A user response to a Learning Recommendation Evidence Card, such as accepting the recommendation, dismissing it, or keeping watch for more evidence.
_Avoid_: Hidden approval; uninterpreted click; overly granular response taxonomy

**Learning Recommendation Resurfacing**:
The reappearance of a kept-watching Learning Recommendation only after materially new evidence changes the pattern, confidence, affected holdings, or interpretation.
_Avoid_: Time-based nag; repeated unchanged evidence card; generic reminder

**Learning/Evals Product Boundary**:
The Learning/Evals scope focused on Outcome Evaluations, filing-first AI-assisted thesis-health findings, retained outcome-driver evidence, idle pattern analysis, evidence cards, and explicit recommendation responses.
_Avoid_: Auto-changing scoring code; silent strategy mutation; portfolio trade recommendations; broad performance dashboard without evidence cards

**Learning/Evals Review Surface**:
The user-facing place where Learning/Evals evidence becomes reviewable, primarily Dashboard evidence cards with Company Page drilldown history.
_Avoid_: Separate analytics product; Settings configuration page; chat-only approval flow; hidden background report

**Learning/Evals Record**:
An append-only structured record that preserves Learning/Evals evidence, interpretation, recommendation, or user response with source links.
_Avoid_: Live-only recomputation; UI-owned truth; untraceable learning note; overwritten conclusion

**Learning Evidence Lineage**:
The retained source links that connect a Learning/Evals Record to its originating Screener Snapshot, Constitution Version, memo or watch item, filing, outcome window, AI finding, or user response.
_Avoid_: Unsupported learning claim; latest-state inference; source hidden in prose

**Learning Idea Source**:
The origin of a company datapoint used by Learning/Evals, such as FundOps-surfaced, user-added, manually researched, or portfolio-held.
_Avoid_: Treating all datapoints as pipeline recommendations; hidden source context; source-free performance claim

**Near-Miss Learning**:
Lower-confidence Pipeline Learning from companies that were retained by FundOps but did not advance through the full research pipeline before later evidence became meaningful.
_Avoid_: Full memo-backed outcome; ignored missed opportunity; high-confidence strategy verdict

**Learning-Eligible Miss**:
A retained company that did not advance or was dismissed but still has enough source context to be useful for lower-confidence Learning/Evals analysis.
_Avoid_: Entire screened universe; unretained raw candidate; random market hindsight

**Learning Comparison Group**:
A set of retained accepted, rejected, missed, held, or non-held companies used by Learning/Evals to compare pattern strength across similar ideas.
_Avoid_: Unretained universe sample; perfect control group claim; uncaveated hindsight comparison

**Pipeline Learning**:
Learning/Evals interpretation about whether FundOps workflow capabilities surfaced, researched, judged, or monitored evidence well.
_Avoid_: User strategy flaw; market outcome alone; investor preference

**Strategy Learning**:
Learning/Evals interpretation about whether the active Constitution and related strategy criteria describe ideas that hold up over time.
_Avoid_: Pipeline execution quality; portfolio action; one-company outcome

**Investor Learning**:
Learning/Evals interpretation about the user's revealed preferences, judgment patterns, accepted recommendations, rejected recommendations, and decision behavior.
_Avoid_: Autonomous behavior change; user grading; quiz or training module

**Learning Recommendation Outcome**:
The later Learning/Evals assessment of whether an accepted Learning Recommendation appears to have helped, harmed, or remained inconclusive after enough evidence accumulates.
_Avoid_: Assuming accepted recommendations were correct forever; hidden self-evaluation; blame-free silence

**Learning Record Supersession**:
A newer Learning/Evals Record that revises, narrows, or replaces the current interpretation of an earlier Learning/Evals Record without overwriting the earlier record.
_Avoid_: Silent overwrite; pretending earlier evidence never existed; latest-state-only truth

**Current Learning View**:
The latest synthesized interpretation of append-only Learning/Evals Records for a ticker, pattern, or strategy question.
_Avoid_: Source of truth; permanent conclusion; erased history

**Investment Entity**:
The stable FundOps identity for a researched investable target that retained evidence and artifacts attach to even when display tickers or listings change.
_Avoid_: Current ticker as permanent identity; page-local company row; provider-only symbol

**Issuer**:
The company or legal entity behind one or more supported investable securities.
_Avoid_: Ticker symbol; exchange listing; portfolio lot

**Security**:
An investable instrument associated with an Issuer, such as common stock, ADR, preferred stock, or another supported instrument.
_Avoid_: Ticker symbol; company name alone; broker position row

**Security Listing**:
An exchange-specific tradable listing for a Security used for lookup, pricing, and display.
_Avoid_: Stable company identity; artifact owner; issuer

**Ticker Symbol**:
The market symbol used to look up or display a Security Listing at a point in time.
_Avoid_: Permanent investment identity; artifact primary key; company identity

**Ticker Alias History**:
The retained mapping of Ticker Symbols to Security Listings across symbol changes, exchange changes, and time.
_Avoid_: Current ticker only; overwriting old symbols; losing historical lookup context

**Company Page**:
A read-only ticker-first dossier that resolves to an Investment Entity and aggregates current and previous workflow results for that researched target.
_Avoid_: Separate duplicate ticker page; interactive workspace; search-only Library result

**Company Page Timeline**:
The chronological ticker-specific history of completed workflow artifacts and relevant events on a Company Page.
_Avoid_: Library result list; active workbench queue; memo-only version history

**Workspace Activity Timeline**:
The backend-wide chronological lineage of meaningful workspace events such as workflow runs, approvals, strategy versions, universe versions, extension history, major operational failures, and artifact creation.
_Avoid_: Ticker-only Company Page Timeline; noisy log stream; UI notification feed

**Company Page Workflow Map**:
The first-view function-by-function map of a ticker's retained FundOps workflow outputs and important event markers as lane rows of dated milestone cards.
_Avoid_: Generic price chart; scaled calendar chart; separate history graph; workflow queue; artifact list only

**Company Page Workflow Lane**:
A workflow-stage row inside the Company Page Workflow Map that groups dated milestone cards by originating FundOps capability.
_Avoid_: Arbitrary category; status column; separate workflow page

**Company Page Workflow Milestone**:
A user-facing workflow output, decision, action, or outcome shown by default in the Company Page Workflow Map.
_Avoid_: Operational retry; background sync event; raw implementation log

**Workflow Milestone Card**:
The minimal clickable card shown inside a Company Page Workflow Lane for one dated milestone.
_Avoid_: Mini report; inline artifact summary; financial metric card

**Portfolio History Milestone**:
A portfolio-relevant Company Page Workflow Milestone that records ownership actions such as purchase, sale, size, and price.
_Avoid_: Routine allocator suggestion; unrealized generic market movement; workflow chatter

**Company Page Milestone Preview**:
A compact read-only side panel opened from a Company Page Workflow Milestone before the user chooses to read the full artifact.
_Avoid_: Full artifact reader; editable workflow detail; modal that hides the graph

**Milestone Preview Field**:
A compact shared field shown in a Company Page Milestone Preview to identify and summarize the selected milestone.
_Avoid_: Full artifact section; raw payload key; implementation debug metadata

**Company Page Section**:
A top-level read-only dossier view inside a Company Page, such as History, Financials, or Learning.
_Avoid_: Workflow workspace tab; duplicated artifact reader; deep scroll anchor

**Company Page Financials Section**:
The Company Page section for clean current company fundamentals and financial metrics.
_Avoid_: Screener evidence history; workflow artifact preview; investment-decision timeline

**Financials Snapshot**:
The compact first view of valuation, growth, margins, profitability, cash flow, leverage, and business context inside the Company Page Financials Section.
_Avoid_: Full financial statement workbook; Screener scorecard; artifact evidence detail

**Company Page Full Financials**:
The detailed financial statement view inside the Company Page Financials Section, grounded in retained annual or quarterly fundamentals.
_Avoid_: Screener evidence replay; memo artifact reader; raw unformatted SEC payload

**Financials Lookback**:
The recent historical financial data used to support Company Page financial analysis and Memo-Backed Thesis Health, starting with up to five fiscal years of annual fundamentals and twelve quarters of quarterly fundamentals when available.
_Avoid_: Full financial statement workbook by default; workflow artifact history; Screener evidence replay

**Financial Observation**:
A period-specific Supported Financial Metric value for an Investment Entity or Security, with fiscal period, period type, source, unit, currency, provenance, and quality state retained.
_Avoid_: Latest fundamentals blob; display-only metric; source-free ratio

**Reported Financial Fact**:
A source-backed period financial field value as reported or supplied before FundOps transforms it into a Supported Financial Metric.
_Avoid_: Calculated metric; normalized ratio; inferred value; source-free figure

**Unmapped Reported Financial Fact**:
A retained Reported Financial Fact whose source field has not yet been accepted as a Financial Concept Mapping or Supported Financial Metric input.
_Avoid_: Supported metric; ignored data; trusted workflow signal; ad hoc provider variable

**Calculated Financial Observation**:
A Financial Observation produced by FundOps from Reported Financial Facts, accepted mappings, formulas, derivations, or lookback rules.
_Avoid_: Reported fact; raw source field; display-only calculation; ungrounded ratio

**Financial Observation Lineage**:
The retained relationship from a Calculated Financial Observation to its input Reported Financial Facts, mappings, formula provenance, derivations, and quality decisions.
_Avoid_: Comment-only provenance; hidden formula; unverifiable metric; display tooltip

**Financial Data Correction**:
A restatement, amended filing, provider correction, accepted mapping change, or formula-version change that revises the current interpretation of historical financial data.
_Avoid_: In-place edit; routine projection refresh; unrelated price move; silent value change

**Financial Data Supersession**:
The retained relationship marking earlier Reported Financial Facts or Calculated Financial Observations as replaced for current use by corrected financial records.
_Avoid_: Delete; overwrite; hidden correction; artifact migration

**Eager Financial Recalculation**:
The retained refresh of affected Calculated Financial Observations, Latest Financial Projections, and active financial monitoring state after new or corrected financial inputs.
_Avoid_: Lazy read-time calculation; completed artifact rewrite; hidden projection drift

**Latest Financial Projection**:
A current-view projection over Financial Observations used by Company Page, Screener, Memo, Thesis Health, or other workflows when they need the latest relevant financial values.
_Avoid_: Source of truth; overwriting period history; one-off provider snapshot

**Financial Data Pipeline**:
The shared FundOps data foundation that turns reported and provider-supplied company financial data into Supported Financial Metrics with provenance and quality signals.
_Avoid_: Pipeline Run; replacement workflow; provider-specific parser; one-off agent data fetch

**Financial Data Robustness Improvement**:
A scoped improvement that increases coverage, validation, provenance, or comparability of Supported Financial Metrics without changing FundOps workflow boundaries.
_Avoid_: Data pipeline redesign; new workflow; complexity for its own sake; metric sprawl

**Financial Data Source Role**:
The trusted responsibility a data source has inside the Financial Data Pipeline, such as reported fundamentals, market data, or optional enrichment.
_Avoid_: Treating every provider field as equally authoritative; provider preference without capability boundary; hidden fallback semantics

**Reported Financial Source**:
A Financial Data Source Role for company-reported financial statements, filing text, taxonomy definitions, and statement-derived metrics.
_Avoid_: Market-price source; analyst estimate source; unsupported web summary

**Market Data Source**:
A Financial Data Source Role for current price, market capitalization, volume, beta, price history, and other market-context values.
_Avoid_: Authoritative financial statement source; replacement for reported fundamentals; filing evidence

**Financial Enrichment Source**:
An optional Financial Data Source Role for estimates, peers, analyst context, or forward-looking inputs that improve research depth without owning core reported fundamentals.
_Avoid_: Required core pipeline dependency; replacement for reported financials; hidden source of hard screening truth

**Financial Coverage Gap**:
A missing or unmapped source field that prevents FundOps from measuring a Supported Financial Metric even though company-reported evidence may exist.
_Avoid_: Unsupported company; failed investment signal; ignored raw tag

**Material Financial Coverage Gap**:
A Financial Coverage Gap that changes the interpretation, confidence, or evaluability of a user-facing workflow result.
_Avoid_: Routine internal missing field; raw data-debug note; harmless parser miss

**Reported Financial Concept**:
An investment-relevant financial statement item, ratio, sector KPI, or operating metric FundOps may measure from company-reported or provider-supplied data.
_Avoid_: Raw provider field; implementation variable; unsupported custom metric

**Supported Financial Metric**:
A Reported Financial Concept that every FundOps workflow may use because its definition, source or formula, unit, expected range, sector applicability, comparability, and missing-data behavior are known.
_Avoid_: Ad hoc variable; one-surface metric; undocumented calculation

**Financial Metric Catalog**:
The canonical set of Supported Financial Metrics available across FundOps workflows.
_Avoid_: Per-page field list; agent-specific metric vocabulary; hidden calculation inventory

**Financial Metric Catalog Version**:
A retained version of a Supported Financial Metric's definition, formula, applicability, decision authority, and missing-data behavior.
_Avoid_: Runtime constant only; undocumented formula revision; mutable metric definition

**Financial Metric Applicability**:
The known company, sector, period, or business-model conditions under which a Supported Financial Metric is meaningful and comparable.
_Avoid_: Workflow permission; hiding useful metrics; treating not-applicable as a failing value

**Financial Metric Decision Authority**:
The degree to which a Supported Financial Metric may determine a hard gate when its data support, applicability, and comparability are strong enough.
_Avoid_: Arbitrary workflow gatekeeping; display-only by default; using weak data as a hard pass/fail

**Financial Metric Formula Provenance**:
The retained explanation of a calculated Supported Financial Metric's formula, inputs, period basis, lookback basis, sector exclusions, and missing-data behavior.
_Avoid_: Unexplained ratio; interchangeable formula assumption; hidden arithmetic

**Financial Calculation Reference**:
The Settings/Config guide map that explains how Supported Financial Metrics and key calculated observations are defined, sourced, calculated, and versioned.
_Avoid_: Editable formula console; raw code view; hidden calculation inventory

**Financial Concept Mapping**:
An accepted relationship between a Reported Financial Concept and the source fields FundOps may use to measure it.
_Avoid_: One-off parser guess; user-approved tag chore; hidden unsupported proxy

**Financial Mapping Rule Version**:
A retained version of the source-field mapping rule FundOps used to connect Reported Financial Facts to a Reported Financial Concept.
_Avoid_: Parser heuristic; silent mapping update; provider-key assumption

**Company-Local Financial Mapping**:
A Financial Concept Mapping accepted only for the company whose reported source field supplied the mapping evidence.
_Avoid_: Global taxonomy rule; temporary parsing guess; user-facing exception

**Global Financial Mapping**:
A Financial Concept Mapping accepted as reusable across companies after stronger evidence than a single-company match.
_Avoid_: First-seen AI guess; company-specific disclosure assumption; hidden mapping drift

**Reported Field Definition**:
The company-supplied label, documentation, and taxonomy context that explains what a reported source field means.
_Avoid_: AI-invented description; raw tag name alone; provider field without meaning

**Financial Mapping Candidate**:
A proposed relationship between an unmapped source field and a Reported Financial Concept that requires internal evidence checks before FundOps treats it as accepted.
_Avoid_: Active metric; user-facing approval item; silently trusted AI guess

**Financial Mapping Validation**:
The deterministic check that a Financial Mapping Candidate's reported definition, unit, period type, statement context, value shape, and conflicts are consistent with the target Reported Financial Concept.
_Avoid_: AI-only acceptance; retail-investor approval; unvalidated parser fallback

**Financial Mapping Governance**:
The internal evidence, quality, and audit standard that decides whether Financial Mapping Candidates may become Financial Concept Mappings.
_Avoid_: Per-tag user review; unreviewed AI enrichment; hiding material data gaps

**Retained Quarterly Financial History**:
The quarterly company fundamental history FundOps keeps so Thesis Health and Company Page analysis can evaluate quarter-by-quarter changes, trailing-twelve-months values, year-over-year quarters, and multi-period averages.
_Avoid_: Latest quarter only; annual-only proxy; unreconciled provider blob; hidden one-off fetch

**Derived Q4 Financial Metric**:
A fourth-quarter flow metric calculated from annual 10-K data minus the first three fiscal quarters when no standalone Q4 10-Q exists.
_Avoid_: Directly reported quarter; unproven arithmetic; derived ratio without components; hidden restatement adjustment

**Company Page Thesis Health Section**:
The Company Page section for tracking the health and evolution of a ticker's memo-backed investment thesis.
_Avoid_: Broad system learning dashboard; Constitution recommendation queue; generic outcome analytics

**Memo-Backed Thesis Health**:
Ticker-specific tracking of whether the assumptions and return path from a Completed Memo are holding, weakening, or broken.
_Avoid_: Completed Thesis quality; generic watchlist health; broad Learning Recommendation

**Active Thesis Health Source**:
The Completed Memo version and Investment Memo Monitoring Plan currently driving Memo-Backed Thesis Health for a ticker.
_Avoid_: Hidden latest artifact; blended memo history; arbitrary user-selected memo; carried-forward old watch items

**Thesis Watch Item**:
A memo-derived condition, driver, risk, or kill criterion tracked after a Completed Memo to determine whether the investment thesis still holds.
_Avoid_: Generic health metric; IC-only assumption; untracked memo prose

**Thesis Watch Item Status**:
The current state of a Thesis Watch Item, such as intact, watch, broken, or unknown.
_Avoid_: Investment verdict; portfolio action; invented conviction score

**Current Thesis Watch Item State**:
The latest accepted status, evidence, checked time, and data-gap state retained on an active Thesis Watch Item after its most recent Thesis Watch Item Check.
_Avoid_: Recomputed-only history view; hand-edited status; Dashboard alert payload; portfolio instruction

**Thesis Health Summary Label**:
The qualitative summary of active Memo-Backed Thesis Health, such as Intact, Watching, Broken, or Not Checked.
_Avoid_: Pseudo-score; portfolio action; hidden conviction rating

**Thesis Health Operational Record**:
The retained product record that owns an Investment Memo Monitoring Plan, Thesis Watch Items, Thesis Health Refresh results, filing metadata checks, data gaps, and active or historical Thesis Health state.
_Avoid_: Dashboard alert payload; timeline-only event; transient score; reparsed memo prose

**Thesis Watch Item Check**:
The retained result of evaluating one Thesis Watch Item during a Thesis Health Refresh, including the observed evidence, resulting status, and any data gap for that item.
_Avoid_: Whole-plan blob only; Dashboard alert; inferred memo note; hidden one-off calculation

**Thesis Health Baseline Check**:
The initial Thesis Watch Item Check created from memo-time evidence when a Thesis-Health Ready Memo first creates active Thesis Watch Items.
_Avoid_: Later filing refresh; stale scheduler-dependent first state; ungrounded default status; portfolio action

**Material Thesis Break**:
A confirmed deterioration in memo-backed Thesis Watch Items that materially undermines a kill criterion, core return driver, or the broader memo-backed investment case.
_Avoid_: One noisy quarter; minor watch-state drift; generic bad news; non-material metric wobble

**Thesis Watch Item Tracking Mode**:
The declared way a Thesis Watch Item can be monitored, such as quantitative filing or financial data, qualitative evidence review, or unsupported.
_Avoid_: Hidden monitoring method; implicit news scrape; status change without trackable evidence

**Thesis Watch Item Measurement Cadence**:
The reporting-period rhythm a Thesis Watch Item expects for evaluation and confirmation, such as quarterly, annual, trailing-twelve-months, or slower-cycle.
_Avoid_: Ambiguous next period; calendar reminder; provider polling interval; one-size-fits-all confirmation

**Thesis Watch Item Lookback Basis**:
The evidence window a quantitative Thesis Watch Item compares against its threshold, such as latest quarter, year-over-year quarter, trailing-twelve-months, annual, or multi-period average.
_Avoid_: Ambiguous metric value; hidden seasonal adjustment; cadence substitute; one noisy period treated as full thesis evidence

**Deterministic Thesis Health Evaluation**:
The rule-based calculation that turns a validated quantitative Thesis Watch Item and current supported evidence into intact, watch, broken, unknown, or data-gap status.
_Avoid_: LLM rejudging thesis health; prose interpretation during refresh; hidden analyst opinion; manual status choice

**AI-Assisted Thesis Health Review**:
A source-backed qualitative review that uses AI to interpret filing evidence and secondary market research for thesis-health context without directly replacing Deterministic Thesis Health Evaluation.
_Avoid_: Silent Thesis Watch Item Status mutation; news-only thesis health; unsupported AI judgment; always-on market chatter

**New Filing Thesis Health Review**:
An AI-Assisted Thesis Health Review run for a thesis-health-ready ticker after a new company filing or formal company disclosure is detected, without requiring a pre-filter that proves the filing touches an existing Thesis Watch Item.
_Avoid_: Skipping unexpected filing evidence; watch-item-only relevance gate; assuming thesis risk must appear in known metrics

**Operating Thesis Disclosure**:
A company disclosure category that normally deserves AI-Assisted Thesis Health Review because it can change business, financial, guidance, risk, or management understanding.
_Avoid_: Purely administrative filing; market rumor; unrelated corporate paperwork

**Administrative Filing Record**:
A retained low-priority filing record that does not normally receive full AI-Assisted Thesis Health Review unless it touches governance, dilution, capital structure, ownership, or a known thesis risk.
_Avoid_: Ignored filing; full research trigger by default; operating disclosure

**AI-Assisted Thesis Health Finding**:
The structured output of an AI-Assisted Thesis Health Review, including filing evidence, metric changes, bounded market context, thesis-health implication, confidence, evidence gaps, suggested watch-item changes, and Learning/Evals relevance.
_Avoid_: Free-form research note; unsupported status change; hidden learning input

**AI-Assisted Thesis Health Attention**:
A Dashboard Attention Item created from a material AI-Assisted Thesis Health Finding that deserves user review without prescribing a portfolio action.
_Avoid_: Routine intact finding; automatic sell alert; noisy news notification; hidden Thesis Watch Item Status change

**Filing-First Thesis Health Evidence**:
The evidence hierarchy for AI-Assisted Thesis Health Review where company filings and reported financials control thesis-health interpretation when they conflict with market research or news.
_Avoid_: Treating news as equal to filings; averaging conflicting evidence; price narrative as thesis evidence; uncited market rumor

**Thesis Health Evidence Tier**:
The source-priority level used by AI-Assisted Thesis Health Review: controlling filings and reported financials, high-value company disclosures, or secondary market context.
_Avoid_: Flat source list; treating commentary as equivalent to filings; unranked evidence bundle

**Bounded Market Research Window**:
The limited recent-lookback period used by AI-Assisted Thesis Health Review for secondary online market research, defaulting to roughly the prior three months.
_Avoid_: Open-ended web crawl; full company reread; stale news treated as current evidence

**Held Thesis Health Review Cadence**:
The higher-priority thesis-health review rhythm for portfolio-held thesis-health-ready tickers, starting around weekly metadata checks and trigger-based AI-assisted review.
_Avoid_: Same cadence as archived non-held ideas; price-only portfolio refresh; always-on AI monitoring

**Non-Held Thesis Health Review Cadence**:
The lower-priority thesis-health review rhythm for non-held thesis-health-ready tickers, usually slower than held positions and driven by filings, outcome windows, or idle learning needs.
_Avoid_: Portfolio urgency; equal provider priority; automatic expiration from learning

**Supported Thesis Health Field**:
A known financial or filing-derived field that FundOps can retrieve and compare consistently during Thesis Health Refresh.
_Avoid_: Memo-invented metric; unsupported custom KPI; qualitative proxy disguised as quantitative

**Supported Thesis Health Field Catalog**:
The approved set of already-registered Supported Thesis Health Fields and their valid measurement cadence and lookback-basis combinations that Memo may use for quantitatively monitored Thesis Watch Items.
_Avoid_: Memo-invented metric; unsupported field name; qualitative proxy disguised as quantitative; metric-only allowlist without computable evidence windows

**Thesis-Health Ready Memo**:
A Completed Memo whose Investment Memo Monitoring Plan contains at least one quantitative Thesis Watch Item with a catalog-allowed metric, measurement cadence, lookback basis, and available baseline evidence.
_Avoid_: Memo with only unsupported watch items; generic memo completion; hidden pseudo-monitoring; supported metric name without computable baseline evidence

**Long-Horizon Thesis Tracking**:
Continuing to refresh Memo-Backed Thesis Health for thesis-health-ready tickers over time so FundOps can learn whether memo assumptions and return drivers later held or broke.
_Avoid_: Portfolio-only monitoring; short-lived watchlist reminder; stale research with no outcome signal

**Thesis Health Refresh**:
A scheduled or user-initiated check that updates memo-backed Thesis Watch Item statuses using approved monitoring sources.
_Avoid_: Company Page page-load side effect; always-on unseen monitoring; automatic startup catch-up; parsing memo prose again

**Thesis Health Filing Metadata Check**:
A lightweight check for whether a ticker has a new relevant 10-Q or 10-K since the last Thesis Health Refresh.
_Avoid_: Full statement refresh; predicted filing-date requirement; hidden page-load request

**Metadata-Only Thesis Health Refresh**:
A Thesis Health Refresh result where a Thesis Health Filing Metadata Check found no new relevant filing, so filing recency is updated while Thesis Watch Item statuses remain unchanged.
_Avoid_: Full recalculation; silent no-op; invented status update; page-load side effect

**Portfolio Price and P&L Refresh**:
A price-driven portfolio update that refreshes current prices, market value, and unrealized P&L without changing Memo-Backed Thesis Health.
_Avoid_: Thesis assumption check; filing-driven health update; memo-backed watch item status change; position lot rewrite; cash rewrite

**Shared Data Provider Budget**:
The limited external data-provider capacity shared by FundOps workflows such as Screener, Thesis, Portfolio, Pipeline, and Thesis Health Refresh.
_Avoid_: Per-capability unlimited pulls; hidden background spend; treating scheduled maintenance as free

**Data Provider Request Queue**:
The shared sequencing and throttling behavior that lets FundOps workflows use external data providers without exceeding the Shared Data Provider Budget.
_Avoid_: Capability-specific bypass; uncoordinated parallel provider calls; invisible rate-limit contention

**User-Initiated Workflow Run**:
A workflow run explicitly started by the user, such as running Screener, Pipeline, Thesis, Memo, Portfolio, Portfolio Review, or a Manual Thesis Health Refresh.
_Avoid_: Scheduled maintenance; background catch-up; automatic page-load action

**Interactive Workflow Run**:
A user-initiated workflow run whose result the user is actively waiting on, such as Screener, Pipeline, Thesis, IC Review, Memo, Portfolio, or Portfolio Review.
_Avoid_: Scheduled maintenance; background thesis-health refresh; passive status update

**Manual Thesis Health Refresh**:
A user-triggered Thesis Health Refresh for all due thesis-health-ready tickers when the user explicitly wants current thesis-health status outside the normal schedule.
_Avoid_: Background catch-up; automatic page-load refresh; hidden data-provider spend

**Company Page Identity Strip**:
The compact company, ticker, price, and current-state reference shown above or alongside Company Page sections.
_Avoid_: Financial metric dashboard; workflow action bar; generic page title only

**Library**:
The searchable archive and lookup entry point for ticker dossiers and historical workflow artifacts.
_Avoid_: Company Page when referring to the ticker dossier itself

**Library Projection**:
The derived searchable index that lets Library find Known Library Tickers and route to Company Page history.
_Avoid_: Artifact source of truth; duplicate memo store; independent research archive

**Archive Retrieval Projection**:
A rebuildable search or semantic retrieval view over retained FundOps evidence, source records, bundles, and artifacts.
_Avoid_: Source of truth; standalone memory store; uncited RAG answer store

**Library Entry Point**:
The standalone user-facing doorway for directly looking up Known Library Tickers and opening their Company Page.
_Avoid_: Hidden internal archive; workflow-only ticker access; general market search

**Library Search**:
The ticker-only lookup behavior that resolves a searched ticker to its Company Page dossier before exposing related artifacts.
_Avoid_: Artifact-first document search; company-name search; thematic archive search; separate Thesis/IC/Memo result feed; duplicate ticker dossier

**Known Library Ticker**:
A Ticker Symbol that resolves to an Investment Entity with at least one retained FundOps workflow artifact, event, portfolio record, or other archived data record.
_Avoid_: Any valid market ticker; permanent investment identity; on-demand company lookup; empty Company Page candidate

**Saved Screener Work**:
The retained top Screener Review Set records for a completed Screener run, including generated ranking work and evidence worth reopening later.
_Avoid_: Entire raw Screened Universe; unsaved market scan; hidden exhaustive failed-company list

**Library Match Suggestion**:
A selectable fuzzy match for a Known Library Ticker shown while the user is typing in Library Search.
_Avoid_: Unknown ticker suggestion; company-name search result; artifact search result

**Library Search Panel**:
The left Library panel containing ticker lookup, fuzzy Known Library Ticker suggestions, and search controls.
_Avoid_: Memo navigation panel; stats sidebar; full ticker directory

**Library Search Panel Toggle**:
The control that collapses and reopens the Library Search Panel.
_Avoid_: One-way hide action; separate navigation link; full page reload

**Library Result Panel**:
The main Library panel that embeds the selected Known Library Ticker's Company Page dossier.
_Avoid_: Separate Company Page clone; artifact reader; empty unknown-ticker dossier

**Selected Library Ticker**:
The Known Library Ticker currently shown in the Library Result Panel.
_Avoid_: Hidden-only UI state; unknown ticker; artifact selection

**Library Browse**:
The Library surface for ticker-first archive lookup that displays the matching Company Page dossier.
_Avoid_: Memo tab; artifact reader; document-result workspace

**Library Sync**:
A non-user-facing maintenance or backfill operation that refreshes archive projections when needed.
_Avoid_: Main Library button; required user step; visible workflow action

**Library Stats**:
Archive-level counts or performance metrics derived from retained FundOps history.
_Avoid_: Library Browse sidebar summary; unexplained win-rate badge; ticker lookup content

**Workflow Artifact Reader**:
The focused read-only surface for opening the exact Completed Workflow Artifact selected from a Company Page Timeline.
_Avoid_: Library Memo Reader; workflow generation page; mutable editing surface

**Workflow Artifact Reader Shell**:
The shared reader frame for all completed workflow artifacts, including navigation back to the Company Page and artifact metadata.
_Avoid_: Artifact-specific page chrome; workflow generation controls; editable workspace

**Workflow Artifact Body Renderer**:
The artifact-type-specific rendering behavior inside the Workflow Artifact Reader Shell.
_Avoid_: One-size-fits-all memo layout; raw JSON dump; duplicated reader shell

**Artifact Export**:
A user-initiated action that exports one Completed Workflow Artifact from the Workflow Artifact Reader, Library, or Company Page history.
_Avoid_: Bulk workspace backup; raw database dump; regenerating the artifact during export

**Retail Artifact PDF**:
The polished user-facing PDF export of a Completed Workflow Artifact for retail-investor reading, saving, or sharing.
_Avoid_: Raw markdown export; browser print dump; internal debug artifact

**PDF Rendering Pipeline**:
The versioned artifact-export behavior that turns a Structured Workflow Artifact into a polished Retail Artifact PDF.
_Avoid_: Browser print shortcut; one-off memo formatter; rerunning the workflow for export

**Internal Artifact Markdown**:
A markdown representation of a Completed Workflow Artifact used for internal rendering, testing, portability, or developer workflows.
_Avoid_: Primary retail export; canonical artifact body; polished investor report

**Workflow Artifact Identifier**:
A stable identifier that opens one exact Completed Workflow Artifact regardless of ticker, date, or artifact type collisions.
_Avoid_: Ticker-date lookup; latest artifact pointer; mutable display label

**Workflow Artifact Read Action**:
A Company Page Timeline action that opens a selected Completed Workflow Artifact in the Workflow Artifact Reader.
_Avoid_: Regeneration action; generic latest-only memo link; workflow stage rerun

**Ticker Link**:
A ticker-symbol navigation affordance that resolves the displayed Ticker Symbol to the appropriate Company Page from workflow and history surfaces.
_Avoid_: View in Library button; ticker as permanent identity; duplicate company-page action; non-clickable ticker text

**Company Page Timeline Row**:
A compact preview of one completed workflow artifact or relevant ticker event inside the Company Page Timeline.
_Avoid_: Full artifact rendering; expanded memo body; detailed scorecard surface

**Company Page Timeline Event Marker**:
A compact non-reader timeline row for a user action, workflow transition, feedback event, or outcome snapshot.
_Avoid_: Completed Workflow Artifact; full document; hidden audit trail

**Research Memo**:
A legacy neutral company-report concept whose company, financial, and valuation research depth belongs inside a Completed Memo by default.
_Avoid_: Separate active Memo output; Constitution-independent workflow artifact

**Research Memo Foundation**:
The resolved lineage for the active Investment Memo: preserve the rich Research Memo depth and section-specific evidence behavior while replacing the old neutral report shape with the fixed Investment Memo outline.
_Avoid_: Lightweight four-section Investment Memo path; starting from Thesis; generic web-search memo

**Investment Memo Company Context**:
The concise company background needed to understand the Investment Memo case, with history focused on recent developments and why the opportunity exists.
_Avoid_: Standalone company-history narrative; encyclopedic background; chronology without investment relevance

**Investment Memo**:
The user-facing name for the strategy-tailored Completed Memo that uses memo-native research and valuation to produce one investment argument for an IC-selected opportunity.
_Avoid_: Separate companion to Research Memo; portfolio decision; legacy doc type

**Investment Memo Artifact**:
The canonical active stored and rendered Memo output.
_Avoid_: Research Memo artifact; dual memo output; backward-compatibility record

**Investment Memo Version**:
A dated Investment Memo Artifact for the same resolved Investment Entity or Security generated at a distinct point in time.
_Avoid_: Separate memo type; overwritten latest-only memo; Research Memo variant

**Investment Memo Generation Action**:
The single user-facing action that runs active Memo generation for an eligible opportunity.
_Avoid_: Research Report toggle; both mode; separate memo buttons

**Investment Memo Generation Mode**:
The single active backend generation mode for producing an Investment Memo Artifact.
_Avoid_: research mode; both mode; product-visible legacy branch

**Superseded Lightweight Investment Memo Path**:
The older four-section Investment Memo flow that produced a shorter opportunity, valuation, financial quality, and risk memo from lighter prompts.
_Avoid_: Foundation for the active Investment Memo; replacement for Research Memo depth; active artifact model

**Investment Memo Outline**:
The fixed top-level section structure used by every Investment Memo so memo outputs remain comparable across opportunities.
_Avoid_: Strategy-specific section list; ad hoc memo shape

**Investment Memo Generation Order**:
The dependency-driven order in which Investment Memo sections are produced internally, which may differ from the final reading order.
_Avoid_: User-facing outline order; ad hoc section dependency

**Investment Memo Core Body Section**:
An Investment Memo section that primarily develops section-native evidence rather than synthesizing the completed memo body.
_Avoid_: Final memo conclusion; opening synthesis; valuation synthesis

**Investment Memo Synthesis Section**:
An Investment Memo section that is generated from previously written memo sections and structured outputs.
_Avoid_: Introducing new evidence; first-pass company research; section-native evidence development

**Investment Memo Subsection**:
A fixed, strategy-neutral subsection within the Investment Memo Outline that can carry different emphasis across strategies without being renamed or rearranged.
_Avoid_: Strategy-specific heading; AI-renamed section; optional custom outline slot

**Investment Memo Section Thesis**:
The internal one-argument summary of what a top-level Investment Memo section is saying.
_Avoid_: Visible subsection heading; whole-memo thesis; Thesis workflow output

**Investment Memo Source Registry**:
The memo-native source map that tracks the filing, financial, and external evidence references made available to Investment Memo writers.
_Avoid_: Writer-invented citation; ad hoc source list; uncited evidence pool

**Investment Memo Evidence Reference**:
A structured pointer from an Investment Memo section or subsection back to an evidence source supplied through the Investment Memo Source Registry or section evidence package.
_Avoid_: Unsupported claim; free-form source mention; citation invented after writing

**Investment Memo Visible Citation**:
A reader-facing citation marker, filing reference, table source label, or source appendix entry that makes Investment Memo evidence traceable without overwhelming the memo prose.
_Avoid_: Citation after every sentence; hidden-only provenance; decorative citation

**Investment Memo Financial Citation**:
The special visible citation marker for filing and financial data used throughout an Investment Memo.
_Avoid_: Treating filing financials as ordinary web article; uncited financial table

**Investment Memo Citation Popover**:
The reader-facing citation detail bubble opened from an Investment Memo visible citation.
_Avoid_: Raw URL display; full-page navigation; citation detail hidden from reader

**Investment Memo Structured Output Schema**:
The machine-readable contract for a versioned Investment Memo writing template's sections, blocks, required fields, and evidence slots.
_Avoid_: Platform artifact kernel; free-form memo prompt; AI-invented output shape; renderer-only convention

**Investment Memo Structured Artifact**:
The canonical stored Investment Memo artifact containing structured section outputs, citations, source registry, valuation outputs, evidence gaps, and rendered markdown text.
_Avoid_: HTML as source of truth; prose-only memo blob; lossy export-only artifact

**Investment Memo Rendered Snapshot**:
The user-readable markdown representation of an Investment Memo generated from the structured artifact.
_Avoid_: Canonical data model; citation source of truth; unstructured-only storage

**Investment Memo Evidence Package**:
The memo-native evidence gathered for a Completed Memo from opportunity research, company research, filings, financial data, valuation work, and current market context.
_Avoid_: Completed Thesis as source material; generic unscoped data dump

**Investment Memo Evidence Gap**:
A missing, stale, low-confidence, or unavailable evidence item that materially affects the trustworthiness of an Investment Memo conclusion.
_Avoid_: Every fetch warning; harmless missing optional field; visual clutter in memo prose

**Investment Memo Filing and Financial Evidence**:
The memo-native evidence from SEC filings, financial statements, calculated metrics, sector KPIs, peer data, and valuation work.
_Avoid_: Live current-events research; Thesis-derived assumptions; unsupported financial estimates

**Investment Memo Market Intelligence Evidence**:
The memo-native evidence from current online research about recent events, market expectations, catalysts, risks, analyst views, competitive developments, ownership, and price context.
_Avoid_: SEC-only company background; evergreen business description; ungrounded web summary

**Normalized Investment Memo Market Evidence**:
A source-tracked market-intelligence evidence item that extracts a material web-research claim, readable source label, citation target, date or recency context when available, and relevance before section distribution.
_Avoid_: Raw web-search blob as citation; ugly URL in memo prose; uncited current-event claim

**Investment Memo Evidence Distribution**:
The canonical section-level allocation of filing and financial evidence, market intelligence evidence, valuation evidence, strategy emphasis, and evidence-quality signals into the specific evidence package for each Investment Memo section.
_Avoid_: Whole-corpus prompt; one shared memo context; section writer choosing its own sources

**Investment Memo Research Agent Stage**:
The memo-native qualitative research stage that runs before section writing to create richer section inputs from filings, financial evidence, valuation context, and market intelligence.
_Avoid_: Section writer improvisation; Thesis ingestion; whole-memo synthesis before body sections

**Investment Memo Section Evidence Package**:
The section-scoped evidence slice used to write one top-level Investment Memo section from only the facts relevant to that section.
_Avoid_: Whole research corpus; Completed Thesis narrative; unconstrained prompt context

**Investment Memo Provenance**:
The minimal workflow history showing how an opportunity reached Memo without influencing the Investment Memo argument itself.
_Avoid_: Memo evidence; IC rationale as prompt context; Thesis narrative as prompt context

**Investment Memo Strategy Emphasis**:
The Constitution-derived focus that changes what evidence, risks, and interpretation receive more attention inside the fixed Investment Memo Outline.
_Avoid_: Replacing the memo outline; hidden strategy drift

**Investment Memo Business Quality Section**:
The fixed Investment Memo section that covers business model quality, moat durability, and management or capital allocation evidence.
_Avoid_: Standalone management report; optional strategy-specific section

**Current Setup & Variant View**:
The opening Investment Memo section that explains why the opportunity matters now and how the memo-native variant view differs from the market view.
_Avoid_: Generic company overview; historical background first

**Investment Memo Industry and Growth Section**:
The fixed Investment Memo section that explains industry structure, customer or demand dynamics, growth drivers, competitive position, and growth watch items.
_Avoid_: Near-term catalyst section; valuation return bridge

**Investment Memo Financial Quality Section**:
The fixed Investment Memo section that explains revenue and margin quality, cash flow, balance sheet, returns on capital, peer benchmarking, and financial watch items.
_Avoid_: Standalone peer report; raw financial statement dump

**Investment Memo Valuation Section**:
The fixed Investment Memo section that explains memo-native valuation, upside and downside cases, return drivers, and key assumptions.
_Avoid_: Thesis return decomposition; fair-value math without return path

**Investment Memo Valuation Judgment**:
The memo-native judgment about valuation assumptions, scenario drivers, probability weights, and which return drivers matter most.
_Avoid_: Unchecked dollar output; Thesis valuation; unsupported scenario narrative

**Investment Memo Valuation Math**:
The grounded valuation calculation that turns valuation anchors, peer inputs, and scenario assumptions into fair-value and sensitivity outputs.
_Avoid_: Writer-improvised arithmetic; prose-only fair value; unsupported price target

**Memo Return Driver**:
A memo-native source of expected return such as valuation gap, growth, margin expansion, capital returns, multiple re-rating, balance sheet change, or catalyst timing.
_Avoid_: Thesis Return Potential Component; unsupported upside claim

**Investment Memo Risk Section**:
The fixed Investment Memo section that explains key risks, bear case, sensitivity factors, kill criteria, and risk watch items.
_Avoid_: Generic risk list; IC hurdle repeat; operational failure

**Kill Criteria**:
Memo-native conditions that would invalidate or materially impair the Investment Memo case if observed.
_Avoid_: Generic risk; IC Hurdle; portfolio sell rule

**Investment Memo Decision Summary Section**:
The final visible Investment Memo section that summarizes the memo-native investment case, decision, open questions, and evidence gaps.
_Avoid_: Portfolio trade instruction; IC Verdict; full memo restatement

**Memo Decision**:
The memo-native conclusion of an Investment Memo, such as attractive, watchlist, avoid, or needs more evidence.
_Avoid_: IC Pass; IC Fail; buy order; sell order

**Investment Memo Monitoring Plan**:
The separate structured memo-native watch list produced with a Completed Memo and used by the Company Page Thesis Health Section to follow key assumptions, return drivers, risks, and kill criteria after the memo is completed.
_Avoid_: Generic follow-up reminder; portfolio rebalancing rule; IC Review queue; prose that Thesis Health must re-parse

## Relationships

- FundOps behavior is specified by **Product Capability** before implementation details such as routes, agents, pages, or database tables.
- Backend modules should be organized around domain capabilities and platform stores such as Constitution/Strategy, Evidence, Research Intake, Workflow Runs, Artifacts, Portfolio Ledger, Learning/Evals, Projections, and Extension Harness rather than current pages or routes.
- The current proof-of-concept backend should be treated mostly as design lineage and behavioral reference, not as the target architecture.
- Useful current pieces such as financial calculations, data fetching lessons, strategy-saving behavior, prompts, and evals may be refined and reused when they fit the new architecture.
- The top-level **Product Capabilities** are Dashboard, FundOps Chat, Screener, Research Queue, Thesis, IC Review, Memo, Company Page, Library, Portfolio, Portfolio Review, Risk & Exposure, Decision Register, Attribution, Data Governance, Learning/Evals, Settings/Config, Institutional Review Packet Export, and Pipeline Orchestration.
- A **Local FundOps Workspace** owns **Retained Workflow Records** and **Current Workflow Projections** for one user's investment workflow history.
- A **Local FundOps Workspace** has one **Workspace Owner** by default and should not model baseline behavior around collaborators, shared permissions, or multi-writer conflict resolution.
- Backup, restore, or sync-adjacent features may preserve stable identifiers, timestamps, provenance, and archive metadata without making collaboration a baseline product requirement.
- A **Local FundOps Workspace** should have one active **Investment Mandate**, one active **Constitution**, and one primary **Portfolio Ledger** by default, while preserving historical mandate changes, Constitution Versions, prior workflow outputs, and portfolio history.
- The **Institutional Investment Control Plane** should make FundOps institution-grade by adding controls and records for one Workspace Owner, not by adding collaborators, shared permissions, or enterprise workflow by default.
- An **Investment Mandate** should frame the Workspace Owner's capital allocation purpose and portfolio-level constraints before FundOps projects research or portfolio behavior.
- A **Research Constitution** should govern opportunity discovery, evidence requirements, Thesis, IC Review, Memo, and learning calibration without becoming a separate active strategy truth.
- A **Portfolio Policy** should govern portfolio construction, exposure, risk-budget, thesis-coverage, and exception-review behavior without becoming a broker instruction or hidden allocation engine.
- **Research Constitution** and **Portfolio Policy** may be expressed as governed sections or projections of the active Constitution and Investment Mandate, but product behavior should keep their responsibilities distinct.
- FundOps should be a **UI-Native Agent Workspace** rather than a terminal-only tool or public API-first product.
- The user-facing product surface should be native UI, while the **Agent-Native Workspace Contract** coordinates Python workflow capabilities and attached coding-agent work.
- HTTP APIs may exist as UI adapters, but should not be treated as the primary FundOps product contract.
- Durable artifacts and retained records should be the primary outputs of FundOps workflows; chat responses should explain, guide, or discuss those outputs rather than replace them.
- A **UI-Native Agent Workspace** should have three explicit layers: native UI, Python workflow capabilities, and agent workspace harness.
- The native UI layer owns user-facing review, navigation, artifact reading, and workflow controls.
- The Python workflow layer owns investment workflow execution, evidence handling, validation, local storage, and projections.
- State-changing UI, chat, workflow, or adapter actions should flow through **Application Services** rather than directly mutating storage.
- **Application Services** should receive an explicit **Backend Command Intent** before deciding execution path.
- **Backend Command Intent** should determine required validation, approval, queueing, provenance, and whether the action can produce learning input.
- Backend commands should produce either a durable record or an explicit no-op reason such as already current, invalid input, unsupported scope, approval required, provider unavailable, or validation failed.
- **Application Services** should coordinate durable work, validation, canonical writes, and projection updates through platform stores.
- **Application Services** should commit canonical records before refreshing rebuildable projections such as Dashboard rows, Library indexes, search indexes, wiring summaries, current views, and UI caches.
- Projection refresh failures should not corrupt committed canonical records and should be retryable or rebuildable.
- The backend should maintain a **Workspace Activity Timeline** so product surfaces and debugging tools can answer what happened, why, from which inputs, under which versions, and what changed afterward.
- The **Workspace Activity Timeline** is a lineage and provenance source, not necessarily a single user-facing activity feed.
- The agent workspace harness owns manifests, Agent Work Orders, Extension Packs, previews, tests, diffs, and rollback preparation.
- Normal investment workflow actions from the UI should create **Workflow Run Records** or **Durable Local Work Records**, not **Agent Work Orders**.
- Strategy Chat UI owns the conversational surface, Strategy Draft review, Strategy Approval Prompt, and Strategy Activation Confirmation.
- The Python workflow layer owns Strategy Proposal Envelopes, Strategy Proposal Guardrails, Strategy Proposal Evidence Checks, Constitution Versions, Strategy Wiring, and Structured Strategy Memory.
- The agent workspace harness should enter Strategy Chat only when a requested strategy or artifact behavior requires a Workspace Extension Proposal.
- Agent harness work should flow through normal FundOps UI surfaces and the attached coding-agent console rather than a separate FundOps developer console.
- Extension work should appear contextually through Strategy Chat, proposal review, artifact preview, diffs, tests, and accept or rollback actions.
- Agent work should be limited to strict build tasks and UI/chat-assisted change discussion, not normal investment workflow execution.
- FundOps should distinguish customization requests that change product behavior from investment research requests that run existing workflow capabilities.
- Customization requests may create **Agent Work Orders** or **Workspace Extension Proposals**, while investment research requests should create **Workflow Run Records** or **Durable Local Work Records**.
- An **Attached Coding-Agent Session** may author files, run tests, render previews, and prepare rollback for a **Workspace Extension Proposal**, but should not silently mutate normal workflow state.
- FundOps should send **Agent Work Orders** through the **Agent-Native Workspace Contract** instead of passing raw provider-specific prompts through the product surface.
- The native UI may create an **Agent Work Order** as a workspace manifest, then display its status and eventual **Agent Work Result**.
- The attached coding agent should fulfill **Agent Work Orders** through workspace files and commands rather than an opaque provider-specific API call.
- The Python workflow layer should validate **Agent Work Results** before the UI presents accept, reject, or rollback actions.
- **Agent Work Orders** should describe the intended extension outcome and required checks while provider adapters translate them into Codex, Claude Code, or other coding-agent interactions.
- **Agent Work Results** should not affect active product behavior until the user explicitly accepts the reviewed result.
- User acceptance for **Agent Work Results** should preserve provenance back to the originating UI action, proposal, or work order.
- Accepted **Agent Work Results** that change FundOps behavior should become **Extension History**.
- **Retained Workflow Records** should preserve point-in-time evidence and decisions, while **Current Workflow Projections** should make the latest active view easy to read without becoming independent truth.
- **Canonical Evidence Records** should let Screener, Thesis, IC Review, Memo, Thesis Health, Portfolio, Portfolio Review, Company Page, Archive Q&A, and Learning/Evals reuse the same source-linked evidence instead of creating workflow-local datapoints.
- **Supported Financial Metrics** are the typed financial-measurement subset of **Canonical Evidence Records**, not the full boundary of retained evidence.
- **Financial Observations** should retain periodized Supported Financial Metric values, while **Latest Financial Projections** should serve current screens and workflow inputs without replacing multi-period history.
- **Reported Financial Facts** and **Calculated Financial Observations** should be retained separately, with **Financial Observation Lineage** connecting calculated metrics back to source facts, mappings, formulas, derivations, and quality decisions.
- **Unmapped Reported Financial Facts** may be retained for mapping, audit, restatement handling, and coverage-gap analysis, but should not become workflow-decision evidence until mapping governance promotes them.
- **Calculated Financial Observations** should reference the **Financial Metric Catalog Version** and **Financial Mapping Rule Version** that governed their formula, applicability, source mappings, and missing-data behavior.
- Changes to formulas, applicability, mapping rules, or missing-data behavior should create new retained versions rather than silently changing the meaning of historical financial observations or completed artifacts.
- **Financial Data Corrections** should create new Reported Financial Facts or Calculated Financial Observations plus **Financial Data Supersession** relationships rather than overwriting prior financial records.
- New Reported Financial Facts, **Financial Data Corrections**, accepted mapping changes, and formula-version changes should trigger **Eager Financial Recalculation** for affected entities, metrics, periods, Latest Financial Projections, and active financial monitoring state.
- **Latest Financial Projections** should prefer the current accepted financial records after supersession, while completed artifacts and Workflow Evidence Bundles remain linked to the exact records used at completion time.
- User behavior records such as **Dashboard Response Records** and **Learning Feedback Signals** may feed **Learning/Evals**, but should not mutate **Reported Financial Facts**, **Calculated Financial Observations**, or **Financial Data Corrections**.
- Canonical evidence should share an **Evidence Contract** while allowing separate **Evidence Families** for financial metric observations, filing citations, market data, qualitative research claims, model findings, user responses, workflow judgments, and portfolio events.
- Every **Canonical Evidence Record** should link to an **Evidence Source Record** when source-backed, and material citations should retain either an **Evidence Source Excerpt**, normalized payload, hash, external locator, or **Evidence Source Snapshot** sufficient for audit.
- **Evidence Source Retention Tiers** should preserve source identity by default and retain full source snapshots selectively when the source is material to a completed artifact, expensive to reacquire, or needed for replay.
- Online research should enter FundOps through **Online Research Evidence Intake** before Thesis, Memo, Strategy Proposal Evidence Checks, Thesis Health, or Learning/Evals consume it.
- Each workflow that requests online research should provide a **Research Intake Scope** before search starts.
- **Online Research Evidence Intake** should use the **Research Intake Scope** to decide search targets, accepted topics, freshness needs, and exclusion reasons.
- **Online Research Evidence Intake** should inspect retained evidence, source freshness, and prior Online Research Claims before fetching new web sources.
- New online research fetches should be reserved for freshness needs, missing scoped topics, contradiction resolution, or confidence improvement.
- **Online Research Evidence Intake** should behave as a bounded research harness that avoids irrelevant datapoints, minimizes token-heavy source ingestion, prefers high-quality sources, and extracts structured claims before synthesis.
- **Online Research Evidence Intake** should be a shared Python workflow capability used by Strategy Proposal Evidence Checks, Thesis, Memo, Thesis Health, and Learning/Evals with workflow-specific Research Intake Scopes.
- **Online Research Evidence Intake** should return structured evidence, exclusions, quality signals, and provenance first, with compact synthesis as a readable derivative.
- **Online Research Evidence Intake** should retain source identity, extracted claims, citation support, quality signals, recency context, and execution provenance rather than passing raw search results directly into prompts.
- **Online Research Evidence Intake** should extract **Online Research Claims** before generating workflow summaries or prose.
- Workflow summaries that use online research should be composed from accepted **Online Research Claims** rather than directly from raw web-search results.
- Material **Online Research Claims** should pass **Online Research Claim Validation** before supporting Thesis, Memo, IC Review, Strategy Proposal Evidence Checks, Thesis Health, or Learning/Evals conclusions.
- **Online Research Claim Validation** should scale with materiality so harmless background context can remain lightweight while decision-relevant claims receive stricter checks.
- **Online Research Evidence Intake** should retain accepted **Online Research Claims** separately from **Excluded Online Research Claims**.
- **Excluded Online Research Claims** may explain evidence gaps, contradictions, or caveats, but should not support workflow conclusions.
- **Online Research Evidence Intake** should apply the **Research Source Hierarchy** so filings, reported financials, and formal company disclosures control company facts and fundamentals when they conflict with secondary commentary.
- When online sources conflict across evidence tiers, FundOps should retain the contradiction and source context rather than blending the claims into one unsupported conclusion.
- **Point-in-Time Evidence** should preserve both **Evidence As-Of Time** and **Evidence Capture Time** so completed artifacts, workflow decisions, and Learning/Evals can be replayed without hindsight.
- **Evidence Supersession** should revise interpretation through a retained relationship rather than overwriting the earlier evidence that a completed workflow used.
- Meaningful workflow outputs should retain a **Workflow Evidence Bundle** through an **Evidence Bundle Manifest** so FundOps can tell exactly which point-in-time evidence, prompts, configuration, and inclusion decisions produced them.
- Workflow-specific evidence packages, such as **IC Review Evidence Package** and **Investment Memo Evidence Package**, are specialized forms of **Workflow Evidence Bundle**.
- Model, tool, parser, and validation steps that materially create or transform evidence, findings, or artifacts should retain **Execution Provenance Records** linked to their inputs and outputs.
- **AI Usage Records** are the usage-reporting subset of execution provenance, not a replacement for prompt, model, validation, tool, and output lineage.
- Product capabilities should produce and consume shared retained records, evidence, and artifacts, while Dashboard, Company Page, Library, Portfolio Review, and workflow screens should read **Current Workflow Projections** rather than owning separate truth.
- An **Investment Entity** is the durable researched target in FundOps; **Ticker Symbols** are lookup and display aliases that may change over time.
- An **Issuer** may have multiple **Securities**, and a **Security** may have multiple **Security Listings** or **Ticker Symbols** over time.
- **Canonical Evidence Records**, **Completed Workflow Artifacts**, portfolio records, and learning records should attach to stable **Investment Entity** or **Security** identity when possible, while preserving the observed **Ticker Symbol** used at the time.
- **Data Governance** should own the product interpretation of data trust, source conflicts, corrections, mapping promotion, and coverage gaps; Settings/Config owns provider setup, while workflow capabilities consume governed data states.
- A **Data Quality State** should be visible when it materially changes workflow confidence, policy interpretation, thesis health, attribution, or decision readiness.
- **Authoritative Source Decisions** should be retained when source conflicts would otherwise change a material workflow result, financial observation, policy breach, attribution claim, or completed artifact.
- **Authoritative Source Decisions** should prefer filing-first and reported-source hierarchy for company fundamentals while preserving lower-tier contradictory evidence as context or caveat.
- Data governance records may create Dashboard Attention Items when trust degradation needs user inspection, but routine internal parser diagnostics should remain out of the main Dashboard.
- The **Investment Learning Partner** optimizes first for better investor judgment, second for better research process, and third for better executable strategy rules.
- The **Investment Learning Partner** should learn like an investment partner rather than an oracle: retain point-in-time evidence, monitor thesis durability, discover associations across all retained metrics, use AI to interpret patterns and filings, separate association from explanation, and require user approval before strategy behavior changes.
- **Attribution** should explain outcome drivers across performance, thesis, decision, and missed-opportunity dimensions before Learning/Evals proposes strategy calibration.
- **Performance Attribution** should distinguish portfolio return, benchmark-relative return, exposure effects, thesis-driven effects, and unexplained residuals when retained evidence supports the distinction.
- **Thesis Attribution** should compare later evidence against the original Completed Memo, Memo Return Drivers, Thesis Watch Items, and kill criteria rather than inventing a post-hoc thesis.
- **Decision Attribution** should link outcomes back to Investment Decision Records without blaming or grading the user.
- **Missed Opportunity Attribution** should use retained opportunities and workflow history, not broad hindsight scans of unretained market data.
- Attribution outputs may feed Learning/Evals, Portfolio Review, Company Page history, and Institutional Review Packets, but should not directly mutate strategy, policy, or portfolio state.
- **Dashboard** prioritizes unresolved attention and decision work over passive system status, schedules, or exhaustive activity history.
- A **Dashboard Item** should be projected from a **Dashboard Item Source** rather than becoming a duplicated Dashboard-owned copy of another capability's work.
- The **Dashboard Item Source** should remain the source of truth for the underlying approval, portfolio review item, thesis break, workflow failure, data gap, or learning proposal.
- A **Dashboard Item Response** should apply to a **Dashboard Item Source Version** rather than permanently suppressing an underlying ticker, topic, or capability.
- A dismissed or snoozed **Dashboard Item** should not reappear for the same **Dashboard Item Source Version**.
- **Dashboard Item Resurfacing** should happen when the source condition is still unresolved and a later source version adds material new evidence, a new run failure, a changed valuation, a changed thesis-health state, or another meaningful change.
- **Dashboard Decision Items** that block continuation should be resolved by explicit decision responses rather than generic dismissal.
- A **Dashboard Decision Item** requires a user choice before FundOps proceeds or changes behavior.
- Explicit accept or reject decisions should create **Approval Records** separate from the approved or rejected target.
- **Approval Records** should retain the target, target version, user action, timestamp, resulting effect, and provenance needed for later explanation.
- **Approval Records** may also produce **Learning Feedback Signals** when the decision reveals investment judgment, strategy fit, thesis judgment, durable preference, or workflow preference.
- FundOps should distinguish the operational fact that a user approved an action from the learning interpretation that the approval revealed a preference.
- Not every **Approval Record** should automatically become a **Learning Feedback Signal**.
- A material approval, override, exception, exit, learning acceptance, or workflow judgment should create or attach to an **Investment Decision Record** when the future user needs to understand why the decision happened.
- The **Decision Register** should use **Approval Records** as one input, but should not be reduced to approval state because institutional decisions also need rationale, alternatives, evidence, mandate context, policy context, and later outcome links.
- **Decision Rationale** should be captured at decision time when practical rather than reconstructed from later artifacts or model memory.
- **Decision Alternatives** should be retained when they materially explain a decision, such as why a user accepted an exception, rejected a Constitution-fit opportunity, overrode IC, or exited a position.
- The **Decision Register** should link to Workflow Evidence Bundles, Constitution Versions, Investment Mandates, Portfolio Policies, Portfolio Exceptions, and Learning/Evals Records rather than copying their payloads.
- A **Dashboard Attention Item** surfaces evidence for review without prescribing the user's decision.
- **Portfolio** is distinct from **Portfolio Review**: Portfolio owns entered holdings, current value, P&L, and portfolio-linked thesis-health tracking, while Portfolio Review owns reviewable portfolio pressure and opportunity items.
- **Risk & Exposure** is distinct from **Portfolio** and **Portfolio Review**: Portfolio owns ledger-derived holdings, Portfolio Review owns reviewable attention framing, and Risk & Exposure owns policy, risk-budget, exposure, breach, and exception interpretation.
- **Risk & Exposure** should read Portfolio Ledger state, Portfolio Policy, Latest Financial Projections, market data, thesis health, completed artifacts, and retained evidence before producing Exposure Maps, Policy Breaches, and Portfolio Exceptions.
- An **Exposure Map** should be source-backed and policy-relevant rather than a decorative chart.
- A **Policy Breach** should create a Dashboard Attention Item or Dashboard Decision Item depending on whether it requires explicit exception approval, but it should not become a sell instruction.
- A **Portfolio Exception** should require explicit Workspace Owner approval or acknowledgement and should retain its scope, duration, review timing, evidence, and Decision Rationale.
- The **Exception Register** should preserve active and historical exceptions even after the underlying Policy Breach resolves.
- Adding or updating a held position may create a **Portfolio Thesis Coverage Request** when the ticker lacks a suitable **Active Thesis Health Source**; Memo or Research Queue should own the generation work that satisfies the request.
- **Fresh Portfolio Thesis Coverage** should require a **Thesis-Health Ready Memo** from roughly the last 90 days unless a newer material filing or event makes the memo stale sooner.
- **Automatic Portfolio Thesis Coverage** should run for newly added or updated held tickers that lack **Fresh Portfolio Thesis Coverage** so every held position can have memo-backed thesis health to display and refresh later.
- **Automatic Portfolio Thesis Coverage** should start the coverage memo workflow directly when coverage is missing or stale, rather than asking the user to choose between memo generation and thesis-health refresh.
- **Automatic Portfolio Thesis Coverage** should start from explicit portfolio sync or save actions, not from simply loading Portfolio or starting a new **Live FundOps Server Session**.
- **Automatic Portfolio Thesis Coverage** should use the Memo or Research Queue generation workflow rather than making Portfolio the memo author or thesis-health refresh owner.
- **Automatic Portfolio Thesis Coverage** may create a **Directed Company Research Request** for memo coverage when a held ticker lacks a suitable memo-backed thesis-health source.
- Multiple **Automatic Portfolio Thesis Coverage** jobs should all be queued automatically, but execution should respect the **Shared Data Provider Budget** and may run sequentially or with controlled concurrency.
- **Automatic Portfolio Thesis Coverage** may bypass Screener, Thesis, and IC Review for current holdings because ownership itself creates the need for coverage.
- A **Held-Position Coverage Memo** should still be a normal **Investment Memo** with an **Investment Memo Monitoring Plan**, but its **Investment Memo Provenance** should say it came from **Automatic Portfolio Thesis Coverage** rather than **IC Selection**.
- Normal **Automatic Portfolio Thesis Coverage** progress should appear as **Portfolio Thesis Coverage State** on the affected holding row rather than as a Dashboard item.
- Failed or stuck **Automatic Portfolio Thesis Coverage** may create a **Dashboard Attention Item** because the holding lacks usable thesis coverage.
- **Portfolio Position Type** should be user-entered or user-approved; automatic systems may suggest it, but should not silently assign it.
- **Portfolio** should display **Portfolio Position Type**, while **Portfolio Review** may use it as context for pressure or sizing interpretation.
- **Portfolio** current holdings, market value, unrealized P&L, and realized P&L should be projections from the **Portfolio Ledger** rather than independent source-of-truth rows.
- **Portfolio Ledger** entries should retain **Portfolio Import Source** and may retain **Portfolio Reconciliation State** so manual entry, file import, and broker sync can coexist without making broker integration mandatory.
- The Portfolio edit or sync flow should support both **Portfolio Purchase Lots** and **Portfolio Sale Entries** so users can record buys and sales from the same holdings surface.
- Portfolio edit rows should use explicit **Portfolio Entry Intent** rather than inferring sales from negative share values.
- **Portfolio Sale Entry** should require only ticker, sold shares, sale date, and sale price in the baseline product; notes may be optional, but sale reason and thesis judgment should not be required.
- Removing a holding from Portfolio should distinguish **Portfolio Entry Correction** from **Portfolio Exit Record**.
- **Portfolio Entry Correction** should not feed Learning/Evals or Company Page history, while **Portfolio Exit Record** should become portfolio history and may inform Learning/Evals.
- **Partial Portfolio Exit** should reduce the active holding while retaining a sale record for the exited portion.
- **Portfolio Sale Entries** should produce **Realized Portfolio P&L** by matching sold shares against prior **Portfolio Purchase Lots**, using FIFO by default unless the user later chooses specific lots.
- The primary **Dashboard** sections should be **Needs Decision**, **Portfolio Review**, **Needs Attention**, and **Recent Activity**.
- Institution-grade Dashboard behavior should make the same underlying control work legible as a decision queue, exception queue, and monitoring queue without duplicating source truth or turning Dashboard into a full audit log.
- **Portfolio Review** should be a dedicated Dashboard section for **Portfolio Pressure Items**, **Constitution-Fit Opportunities**, held-position thesis breaks, concentration, cash, and sizing attention items.
- **Portfolio Review** items are still **Dashboard Attention Items** unless they explicitly block continuation or require approval.
- **Portfolio Review Framing** should explain why an item is worth reviewing using evidence-first language rather than prescriptive recommendation language.
- **Portfolio Review Framing** may rank urgency or explain source evidence, but should not claim the system has made the user's investment judgment.
- Portfolio Review should show the **Portfolio Pressure List** and **Constitution-Fit Opportunity List** back to back so the user can compare portfolio pressure and available opportunities without FundOps prescribing a switch.
- **Portfolio Review** should be built from the **Portfolio Review Projection** rather than requiring a separate user-facing run action.
- The **Portfolio Review Projection** should read existing source records such as portfolio state, Thesis Health, IC outcomes, completed memos, Screener rankings, Learning/Evals items, and workflow failures.
- Portfolio Review should use targeted refresh actions such as refreshing portfolio data, checking Thesis Health, running Screener, or opening evidence instead of a general recommendation-generation action.
- If Portfolio Review evidence is stale, the stale evidence should be shown as the item reason rather than replaced with freshly invented judgment.
- Portfolio Review should show current holdings under pressure separately from Constitution-fit opportunities rather than framing one as a replacement for the other.
- Portfolio Review labels should prefer phrases such as worth reviewing, thesis pressure, new opportunity surfaced, position needs inspection, Constitution-fit opportunity, or evidence changed.
- Portfolio Review labels should avoid buy, sell, exit now, best opportunity, AI recommends, and target-weight language unless the value comes from explicit user-approved sizing policy.
- A **Portfolio Pressure Item** should explain the current holding evidence that changed or needs review without naming a replacement opportunity.
- A **Constitution-Fit Opportunity** should explain the retained score, rank, IC outcome, memo state, thesis-health state, or other source evidence that makes it visible.
- The **Portfolio Pressure List** and **Constitution-Fit Opportunity List** should not create paired recommendations, replacement links, or trade instructions by default.
- The **Portfolio Pressure List** should use **Portfolio Pressure Ranking**, prioritizing broken thesis health, watching thesis health with material evidence change, sizing or concentration policy breaches, stale memo or thesis-health checks, and the weakest evidence trends among current holdings.
- The **Constitution-Fit Opportunity List** should use **Constitution-Fit Opportunity Ranking**, prioritizing completed memo or IC-passed opportunities with strong Constitution fit, intact thesis health when available, IC Gate Score or IC Constitution Fit, Screener rank for earlier-stage names, and evidence freshness.
- Each Portfolio Review row should show a **Portfolio Review Rank Source** so the user can see why the item appears high in its list.
- Portfolio Review rows should expose shared **Dashboard Hygiene Actions** such as opening evidence, snoozing, and dismissing the current **Dashboard Item Source Version**.
- **Portfolio Pressure Items** should also expose reasoned responses such as reviewed, not material, thesis still intact, and already acted.
- **Constitution-Fit Opportunities** should also expose reasoned responses such as interested, watch, not strategy fit, too risky, and already know this.
- Portfolio Review reasoned responses should become **Learning Feedback Signals** only when they reveal investment judgment, strategy fit, thesis judgment, or durable preference.
- **Recent Activity** should remain a quiet history section and should not be treated as a work queue.
- The **Dashboard Product Boundary** should include existing pending approval gates, Learning/Evals strategy proposals, grounded Portfolio Review items, workflow failures, stale or missing data, learning drift, thesis-health data gaps, and existing run history.
- The **Dashboard Product Boundary** should exclude portfolio optimization, AI-generated target weights, autonomous buy/sell recommendations, and broad out-of-flavor style calls unless they are grounded in explicit evidence and framed as review items.
- A **Dashboard Response Record** should be retained when FundOps needs to remember a user's response across sessions, suppress or snooze a Dashboard Item, resolve a Dashboard Item, or feed Learning/Evals.
- A **Dashboard Response Record** should not duplicate the **Dashboard Item Source** payload or become the source of truth for the underlying workflow condition.
- A **Dashboard Item Response** can be a **Dashboard Hygiene Action**, a **Learning Feedback Signal**, or both when the user response both changes item handling and expresses a durable preference.
- **Dashboard Hygiene Actions** should include visibility and operational handling choices such as opening evidence, snoozing, dismissing, hiding, or retrying an item.
- **Learning Feedback Signals** should be structured enough to explain what the user revealed, such as interest level, strategy fit, risk concern, thesis-break agreement, materiality judgment, or workflow preference.
- **Learning Recommendations** should be generated from retained evidence, workflow outputs, outcomes, thesis health, Approval Records, explicit feedback, and structured memory rather than raw chat vibes or hidden model memory.
- Chat should influence Learning/Evals only when it becomes Structured Strategy Memory, Conversation Evidence used for source lookup, an Approval Record, or an explicit Learning Feedback Signal.
- Routine workflow failures, data gaps, and stale operational statuses should default to **Dashboard Hygiene Actions** rather than **Learning Feedback Signals** unless the user response explicitly reveals a durable preference.
- Generic thumbs-up or thumbs-down should not be used as a canonical **Learning Feedback Signal** when a more specific response can be captured.
- A **Dashboard Item** should expose a **Dashboard Response Set** matched to the item type rather than using one universal dismiss/view/feedback pattern.
- A **Dashboard Response Set** may combine shared **Dashboard Hygiene Actions** with item-specific **Learning Feedback Signals**.
- Portfolio opportunity, thesis-break, Learning drift, workflow-failure, and data-gap items should not share identical **Dashboard Response Sets** because they reveal different kinds of user intent.
- **Needs Decision** should include only explicit approval or continuation gates such as Strategy Change Proposals, pending Strategy Draft approvals, Pipeline approval gates, and user-requested workflow continuations that paused for consent.
- A **Learning Recommendation** that would change strategy, workflow behavior, scoring, wiring, or learning behavior should become a **Dashboard Decision Item** requiring **Learning Recommendation Acceptance**.
- Portfolio Review items, thesis breaks, failed runs, stale data, and read-only Learning drift are **Dashboard Attention Items** unless they require explicit approval to proceed or change behavior.
- Proposed learning or behavior changes should require explicit Dashboard acceptance before they activate.
- **Needs Attention** should include evidence-backed review items such as Portfolio Review items, Material Thesis Breaks, monitoring degradation, workflow failures, and Learning drift.
- **Needs Attention** should also include material Policy Breaches, unresolved Portfolio Exceptions nearing review, Data Quality States that degrade decision evidence, and attribution findings that require inspection.
- Normal successful runs, routine schedule status, and ordinary recent activity should not become **Needs Attention** items.
- **FundOps Chat** contains **Strategy Chat** and **Archive Q&A** behaviors.
- **FundOps Chat Mode** should be selected from the user's intent and visible enough that strategy-changing answers do not feel identical to read-only archive answers.
- **Archive Q&A** should answer questions about completed outputs, ticker history, decisions, and outcomes without mutating the **Constitution**, Settings Projection, workflow selections, or completed artifacts.
- **Archive Q&A** should answer only from **Known Library Tickers** and retained FundOps history by default.
- **Archive Q&A** should search globally across retained FundOps history rather than filtering to the current Constitution or strategy version by default.
- **Archive Q&A** should not perform fresh unknown-ticker lookup or new company research as part of archive recall.
- **Archive Q&A** may use **Archive Retrieval Projections** to find candidate sources, but its claims and citations should resolve back to retained evidence, source records, evidence bundles, or completed artifacts.
- If the user asks **Archive Q&A** about an unknown ticker, **FundOps Chat** should say there is no retained FundOps history for that ticker and suggest an explicit workflow if the user wants fresh research.
- **Archive Q&A** should use **Archive Answer Sources** when it makes claims about prior workflow outputs.
- **Archive Q&A** should expose **Archive Answer Actions** for cited artifacts, backed by **Workflow Artifact Identifiers** when the source is a Completed Workflow Artifact.
- An **Archive Answer Action** for a Completed Workflow Artifact should open the **Workflow Artifact Reader** rather than dumping the whole artifact into **FundOps Chat**.
- **FundOps Chat** may summarize and discuss long artifacts inline, but full artifact reading should remain in the **Workflow Artifact Reader**.
- If an archive discussion turns into a requested strategy, settings, or workflow behavior change, **FundOps Chat** should switch into **Strategy Chat** or the appropriate workflow-changing behavior before proposing any mutation.
- The **Workflow Funnel** should use a consistent **Workflow Stage Selection** pattern across Screener, Thesis, IC Review, Memo, and later downstream handoffs.
- The default FundOps investment workflow should remain a durable hedge-fund-like funnel from strategy to Screener, Thesis, IC Review, Memo, monitoring, and learning.
- A **Directed Company Research Request** may run a specific workflow capability for validated tickers when the user already knows the company they want to research.
- A **Directed Company Research Request** may start at the requested capability, including Thesis or Memo, without requiring the ticker to pass Screener, Thesis Selection, or IC Review first.
- Directed company research should gather the minimum evidence package required by the requested capability and record provenance that the work was user-directed rather than funnel-selected.
- Directed company research should still create normal **Workflow Run Records**, evidence, and **Completed Workflow Artifacts** rather than chat-only answers.
- Directed company research artifacts should join the same **Company Page** and **Library** history as funnel-generated artifacts, with provenance showing that the work was user-directed.
- Directed company research should not replace the default workflow funnel or silently bypass required validation for the requested capability.
- A **Workflow Stage Selection** and **Remaining Stage Items** should partition the ranked outputs from the same workflow stage.
- The visible row order inside each workflow stage should express that stage's ranking.
- Workflow stage selection surfaces should use the same plus, minus, row expansion, selected block, and remaining block behavior across capabilities.
- The capability-specific difference between workflow stages should be the function being executed and the artifact generated, not the basic selection user experience.
- Provider fetches that use constrained sources such as SEC and Yahoo Finance, plus **Eager Financial Recalculation**, projection rebuilds, **PDF Rendering Pipeline** work, workflow continuations, and **Workflow Run Records**, should use **Durable Local Work Records** when they can outlive a request or affect user-visible state.
- Online research, memo generation, pipeline runs, evidence refreshes, extension validation, projection rebuilds, and artifact rendering should use **Durable Local Work Records** when they depend on constrained provider calls, run long enough to outlive a request, or affect user-visible state.
- Cheap synchronous work that does not use constrained providers, does not outlive the request, and does not need durable user-visible status may complete immediately without entering the **Local Work Queue**.
- Backend workflow execution should choose immediate execution or queued execution based on constrained-provider use, expected duration, and need for user-visible retry, status, or provenance.
- The **Local Work Queue** should coordinate durable work by priority, dependencies, retry state, and **Shared Data Provider Budget** rather than letting each capability run uncoordinated background work.
- Workflows that use SEC, Yahoo Finance, FMP, or other constrained providers should declare provider needs and priority to the **Data Provider Request Queue** rather than implementing separate throttling.
- The **Data Provider Request Queue** should own sequencing and concurrency for shared provider calls across Screener, Thesis, Memo, Portfolio, Thesis Health, Learning/Evals, and related workflow capabilities.
- **Durable Local Work Records** should retain enough trigger, status, affected entity or artifact, retry, failure, dependency, and provenance context for restart recovery and Dashboard surfacing.
- User actions, API calls, or schedules should create or inspect **Workflow Run Records** rather than being treated as the durable workflow state themselves.
- **Workflow Run Records** should own **Workflow Step Records**, retries, failures, handoffs, evidence bundle links, and produced artifact links for long-running workflow execution.
- A completed workflow output should commit workflow status, evidence references, evidence bundle manifest, artifact identity, structured artifact body, validation state, and key typed records as one canonical unit.
- Completed workflow outputs should retain the **Constitution Version** and relevant **Settings Projection** that produced them.
- Historical workflow outputs should replay or debug from their retained evidence bundle, Constitution Version, Settings Projection, prompt or template version, and execution provenance.
- Re-running live research or workflow execution should create a new run or version rather than silently changing the explanation of an old artifact.
- Meaningful generated outputs should pass validation before becoming **Completed Workflow Artifacts**.
- Validation should cover artifact shape, required fields, evidence references, citation support, source support, and rendering or export readiness where relevant.
- Invalid generated outputs may be repaired, retried, or retained as rejected output provenance, but should not be marked as completed artifacts.
- **Rejected Generated Outputs** should be retained as **Execution Provenance Records** with validation errors, model or tool context, and input evidence links when useful for debugging or repair.
- If the canonical write for a completed workflow output fails, the output should not appear as a partially completed artifact or decision.
- Provider failures, schema validation errors, model failures, renderer failures, and projection rebuild failures should be visible as operational state with retry or debug context.
- Operational failures should not be converted into investment judgments such as failed theses, bad companies, IC fails, or negative strategy evidence.
- Workflow stages should share the same lifecycle behavior for intake, execution, progress, retry, failure, selection, handoff, and session boundaries unless a capability documents an explicit domain exception.
- **Workflow Stage Selection** should appear as the contiguous selected block, while **Remaining Stage Items** should appear as the lower unselected block.
- **Workflow Stage Selection Count** should determine how many eligible ranked items the selected block tries to show.
- **Workflow Stage Selection Count** is a target count, not a requirement to fill the selected block with ineligible items.
- A workflow stage surface may change the meaning of its selected block as the stage lifecycle advances, but the block behavior should remain consistent.
- Row-level **Workflow Stage Promotion** and **Workflow Stage Dismissal** controls should become available only after the current workflow stage has produced the stage output that can be judged.
- Pending or in-flight stage work may show progress state, but should not expose plus/minus handoff controls until that stage output exists.
- A **Workflow Stage Promotion** should add the selected stage output to **Workflow Stage Selection** and record **Workflow Stage Selection Feedback**.
- A **Workflow Stage Dismissal** should remove the selected stage output from **Workflow Stage Selection** and keep it visible in **Remaining Stage Items** without visible stigma.
- A manual **Workflow Stage Promotion** should expand **Workflow Stage Selection** rather than silently displacing another selected item.
- A manual **Workflow Stage Promotion** may increase **Workflow Stage Selection Count** when it adds an item beyond the current selected block size.
- A **Workflow Stage Dismissal** from the default selection should let the ranking reflow so lower-ranked items move up into the selected block when enough eligible items remain.
- A **Workflow Stage Dismissal** should exclude the dismissed item from the selected block without itself reducing **Workflow Stage Selection Count**.
- A **Workflow Stage Dismissal** should not create a visible stigma on the removed item.
- **Workflow Stage Promotion** and **Workflow Stage Dismissal** should not change the stage ranking, ranking blend, original artifact, or downstream verdict unless the stage action is explicitly a manual verdict such as an **IC Override**.
- Manually promoted stage outputs should append to the end of the current **Workflow Stage Selection**.
- **Workflow Stage Selection Feedback** may inform learning-loop analysis or future Strategy Change Proposals, but should not silently change workflow behavior.
- **Workflow Stage Selection Feedback** should be scoped to the active workflow context that created it.
- Manual workflow actions should affect the current **Workflow Stage Handoff** and remain preserved as historical feedback, but should not automatically carry into future workflow runs.
- General plus and minus behavior in later workflow stages should refer back to the **Screener Review Action** pattern unless that stage has an explicit lifecycle-specific exception.
- A **Workflow Stage Execution Action** should remain available on its capability surface and should run eligible active stage intake items that still need that stage's function in the current active context.
- A **Workflow Stage Execution Action** should not rerun already completed stage outputs by default.
- If a workflow stage function fails operationally for an item, the item should enter **Workflow Stage Retry** rather than becoming a failed investment judgment.
- **Workflow Stage Retry** should be automatic by default rather than requiring a separate retry button.
- Workflow stage items should retry operational failures up to three total attempts by default.
- While automatic retry attempts remain, the row should remain visible with a progress or retry state.
- If automatic retries are exhausted, the item should enter **Workflow Stage Operational Failure**, remain visible, and be excluded from the next **Workflow Stage Handoff**.
- **Workflow Stage Operational Failure** should be treated as an operational state, not a row dismissal, ranking change, or capability verdict.
- A completed stage should create or refresh the appropriate **Workflow Stage Handoff** for selected outputs without treating that handoff as execution of the next workflow capability.
- A **Workflow Stage Execution Action** should stop after refreshing the next stage's active workbench unless it is being run as part of a **Pipeline Run**.
- **Run Full Pipeline** is the user-facing action for a **Pipeline Run**.
- A **Pipeline Run** should execute workflow capabilities sequentially, using each completed stage's **Workflow Stage Handoff** as the active intake for the next capability.
- **Workflow Stage Promotion** and **Workflow Stage Dismissal** may update an existing **Workflow Stage Handoff** when downstream work has not already made the change unsafe or irreversible.
- Updating a **Workflow Stage Handoff** should affect active downstream workbench state, not delete historical **Completed Workflow Artifacts**.
- If downstream work has already produced **Completed Workflow Artifacts**, later upstream selection or handoff changes should not delete those downstream artifacts.
- Completed downstream artifacts should remain available as history even when the upstream item is later removed from the current selected path.
- Later upstream selection or handoff changes should affect only future or active downstream workbench state unless the user explicitly requests artifact deletion.
- Across workflow capabilities, ending a **Live FundOps Server Session** may abandon **Active Workflow Workbench State** but should not delete **Completed Workflow Artifacts**.
- Across workflow capabilities, pending or in-flight work at a session boundary should become **Abandoned Workflow Work** unless that capability has an explicit resume rule within the same **Live FundOps Server Session**.
- Workflow capabilities should not automatically resume **Abandoned Workflow Work** after localhost restarts.
- **Completed Workflow Artifacts** should remain available as historical records through the appropriate history, library, or company surfaces.
- Completed outputs from Screener, Thesis, IC Review, Memo, Thesis Health, Portfolio, Portfolio Review, and Learning/Evals should be retained as **Completed Workflow Artifacts** when they produce readable or reopenable workflow history.
- Every **Completed Workflow Artifact** should have a **Workflow Artifact Identifier** so Company Page, Library, Archive Q&A, Dashboard, and workflow surfaces can open the same exact artifact without creating separate artifact truth.
- Readable **Completed Workflow Artifacts** should retain a **Structured Workflow Artifact** as canonical artifact body and may retain **Rendered Artifact Snapshots** for stable reading and export.
- Readable **Structured Workflow Artifacts** should keep a stable **Artifact Kernel** while allowing writing-heavy bodies to vary through versioned **Artifact Writing Templates**.
- **Artifact Writing Templates** may be built in or proposed through a **Workspace Extension Proposal**, but they must preserve the **Artifact Kernel**.
- A **Workspace Extension Proposal** for a new **Artifact Writing Template** should become an **Extension Pack** only when validation, rendering, fixtures, previews, tests, and rollback metadata are included.
- A **Workspace Extension Proposal** may propose new artifact structure or workflow behavior, but normal **Strategy Wiring** should not silently mutate core artifact contracts.
- **Artifact Export** should export from the stored structured artifact or rendered snapshot rather than re-running the workflow or reparsing prose.
- **Institutional Review Packet Export** should assemble packets from retained Workflow Evidence Bundles, Investment Decision Records, Portfolio Policy state, Risk & Exposure records, Attribution records, Data Governance records, and Completed Workflow Artifacts rather than recomputing latest-state conclusions.
- **IC Packets**, **Portfolio Review Packets**, and **Audit Packages** should preserve point-in-time versions, source links, decision rationale, and known caveats so a future reviewer can replay the review moment.
- **Strategy Chat** creates or updates the **Constitution**, and downstream capabilities consume the **Constitution** rather than inventing their own strategy rules.
- The **Screener** applies exact wireable **Strategy Criteria** as **Screening Requirements** before a company becomes a **Screener Candidate**.
- A Screener run evaluates one **Screened Universe**.
- Users should be able to request a **Universe Selection** in natural language, including common scopes such as S&P 500, Nasdaq 100, Russell 2000, sector lists, or custom ticker sets.
- Custom **Universe Selections** should be allowed when the user intentionally requests a specific custom scope or ticker set.
- A requested **Universe Selection** should pass **Universe Validation** before becoming the active **Screened Universe**.
- **Universe Validation** should verify ticker existence and the **Supported Universe Security Scope** before activation.
- **Universe Validation** should resolve known indices or presets through trusted constituent sources when possible and should reject, flag, or ask about broken tickers, ambiguous names, non-US listings, unsupported securities, or unrelated entries.
- A **Universe Selection** may activate with only the valid subset after review, as long as excluded entries and reasons are shown before approval.
- If too many universe entries are invalid, unsupported, or ambiguous, FundOps should ask the user to fix the universe before activation.
- The attached coding agent may help research unusual or custom **Universe Selections**, but FundOps should still run **Universe Validation** and require approval before activation.
- **Universe Selection** belongs to the **Constitution** and should appear as a Strategy UI function chip alongside other capability wiring.
- Updating the active **Universe Selection** should be reviewable through Strategy Chat or another explicit workflow-changing behavior rather than a hidden screener-side mutation.
- **Universe Selection** changes should use a Strategy Change Proposal or equivalent compact approval flow before activation.
- A proposed **Universe Selection** change should show resolved scope, approximate company count, exclusions or ambiguous entries, and affected workflow capabilities before approval.
- Activating a **Universe Selection** should create a **Universe Version**.
- A **Screener Run** should retain the exact **Universe Version** it evaluated so historical results can replay even when index membership or custom ticker lists later change.
- **Screener Ranking** orders only companies that already satisfy the **Screening Requirements**.
- A **Screener Ranking Blend** should not convert a **Screening Requirement** into a ranking preference unless the user approves that preference.
- Strategy Chat should infer a proposed **Screener Ranking Blend** from what the user says they care about most.
- If the user has not expressed ranking priorities, Strategy Chat should propose an equal-weight **Screener Ranking Blend**.
- A proposed **Screener Ranking Blend** must be shown in the **Strategy Draft Wiring Preview** before approval.
- The **Screener Review Set** should keep the top 50 ranked **Screener Candidates** visible after a run.
- The **Screener Handoff** should pass the top 20 ranked **Screener Candidates** to Thesis.
- By default, the first 20 candidates in the **Screener Review Set** should become **Top Picks**.
- By default, the remaining candidates in the **Screener Review Set** should appear as **Remaining Candidates**.
- **Top Picks** and **Remaining Candidates** should partition the same **Screener Review Set**.
- The **Screener Review Set** should remain capped at 50 candidates even when manual **Top Picks** changes alter the split between **Top Picks** and **Remaining Candidates**.
- Screener page selection actions should not add arbitrary tickers outside the **Screener Review Set**.
- Manually researching a ticker outside the **Screener Review Set** belongs to **Research Queue**, Thesis, or Company Page workflows rather than Screener.
- **Remaining Candidates** may be collapsible, but they should not disappear from the **Screener Review Set** merely because they are outside **Top Picks**.
- **Top Picks** should remain visible by default and should not be the collapsible section.
- A **Screener Run** should produce and rank **Screener Candidates** without automatically executing Thesis or other downstream capabilities.
- A **Screener Run** should still create or refresh **Thesis Intake** from the current **Screener Handoff Selection**.
- A completed **Screener Run** should immediately make the default **Top Picks** visible in **Thesis Intake** without waiting for a separate send action.
- Making **Top Picks** visible in **Thesis Intake** should not execute Thesis.
- Changes to **Top Picks** after a **Screener Run** should immediately update **Thesis Intake**.
- **Top Picks** and **Thesis Intake** should stay synchronized until Thesis is executed or a newer **Screener Run** replaces the selection.
- During a **Pipeline Run**, **Top Picks** should determine the Thesis-visible candidates after Screener completes.
- During a **Pipeline Run**, the 20 **Top Picks** should become the Thesis-visible **Thesis Candidate List** by default.
- By default, every candidate in the active **Thesis Candidate List** belongs to the **Thesis Generation Scope**.
- A **Thesis Run** should generate Thesis artifacts for the full **Thesis Generation Scope** rather than only a smaller selected subset.
- **Thesis Generation Scope** should follow **Screener Handoff** order for queueing, while **Thesis Selection Ranking** later decides which completed artifacts advance.
- Row-level plus and minus actions in Thesis should control **Thesis Selection** after Thesis artifacts exist, not which candidates receive Thesis generation.
- A bold yellow border around Thesis rows should visually indicate **Thesis Selection**, the completed Thesis artifacts currently selected to advance to IC Review.
- **Thesis Selection** should appear as a contiguous selected block after Thesis artifacts exist, following the same surface pattern as **Top Picks** in Screener.
- Completed Thesis artifacts outside **Thesis Selection** should appear below the selected block as **Remaining Theses**.
- Thesis row-level plus and minus actions should become available only after a **Completed Thesis** exists.
- **Pending Thesis Rows** should not support **Thesis Promotion** or **Thesis Dismissal** before Thesis generation completes.
- A user should not be able to pre-remove a pending or in-flight Thesis row from future **Thesis Selection**.
- When a **Thesis Run** starts, the current **Thesis Generation Scope** should become the **Thesis Generation Queue**.
- The **Thesis Generation Queue** may contain more candidates than can be generated at once.
- **Active Thesis Generation** should be limited so Thesis work proceeds gradually instead of starting every queued Thesis simultaneously.
- Before generation completes, queued candidates that have not generated yet should remain visible with empty generated Thesis fields.
- During a **Thesis Run**, queued candidates that have not generated yet should remain visible as **Pending Thesis Rows**.
- **Pending Thesis Rows** should appear in the Thesis table surface so users can see queued candidates and generation state.
- **Pending Thesis Rows** should show empty or placeholder values for generated Thesis fields until generation populates them.
- It should be visually noticeable which Thesis rows have completed generation and which are still pending.
- If Thesis generation fails operationally for a queued ticker, the ticker should move to the back of the active **Thesis Generation Queue** for automatic retry.
- **Thesis Generation Retry** should be automatic rather than requiring a separate retry button by default.
- Thesis generation should retry a failed queued ticker up to three total attempts.
- While automatic retry attempts remain, the row should remain in the queue with a visible retry state.
- If automatic retries are exhausted, the queued ticker should enter **Thesis Generation Failure** and show a visible error state.
- A Thesis generation failure should be treated as an operational failure rather than a user deselection, ranking change, or failed investment judgment.
- After **Thesis Generation Failure**, the failed ticker should be excluded from **Thesis Selection** and should remain visible as an operational failure rather than a failed investment judgment.
- When a **Thesis Run** completes, every candidate in the relevant **Thesis Generation Queue** should have a **Completed Thesis** artifact unless generation failed.
- As each **Completed Thesis** is added, **Thesis Selection Ranking** should refresh so the current top-ranked completed Theses stay visible at the top.
- A **Completed Thesis** should be roughly a page or less.
- A **Completed Thesis** should give IC Review enough signal about the opportunity, **Thesis Return Potential**, return sources, path or catalyst, key risks, and evidence context to decide whether the opportunity deserves IC Review.
- A **Completed Thesis** should not try to replace **Completed Memo** depth.
- A **Completed Thesis** should answer the fixed **Thesis Research Scope** rather than use a strategy-specific section list.
- **Thesis Research Scope** should cover why the opportunity exists, why the stock may be mispriced, the source of **Thesis Return Potential**, the relationship to the active **Constitution** and **Strategy North Star**, the path or catalyst that could make the Thesis work, the key risk or assumption that could break it, and evidence freshness or grounding.
- **Thesis Research Scope** should use SEC and financial pipeline data as the factual anchor and recent external research or news as context for what has changed.
- **Thesis Research Scope** should not expand into an exhaustive company report, industry primer, or full **Completed Memo**.
- **Thesis Research Emphasis** should be derived from the active **Constitution**, **Strategy North Star**, and investment goals captured by Strategy Chat.
- **Thesis Research Emphasis** may change which evidence receives more attention and how the Thesis is framed, but it should not remove required **Thesis Research Scope** questions.
- Strategy Chat should not ask users to configure which **Thesis Research Scope** components exist.
- Strategy Chat should capture enough **Strategy North Star** and investment-goal context for Thesis to apply **Thesis Research Emphasis**.
- Thesis should behave as a worker agent that writes the opportunity and return profile, not as the final memo-worthiness judge.
- Thesis should not produce **IC Conviction**, **IC Constitution Fit**, **IC Data Quality**, or **IC Verdict**.
- Historical Thesis artifacts or current implementation payloads may still contain legacy `conviction` or `constitution_fit` fields, but new active Thesis behavior should treat those fields as deprecated and should not display or rely on them for Thesis Selection, IC Review Intake, or Memo handoff.
- Implementation migration should move memo-worthiness interpretation out of Thesis surfaces and into **Saved IC Verdict Evidence**, leaving Thesis with **Thesis Return Potential**, **Thesis Return Potential Components**, return-source validation, and concise opportunity prose.
- **Thesis Return Potential** should remain a raw expected return percentage because it represents an estimated payoff profile rather than a qualitative memo-worthiness score.
- **Thesis Return Potential** should retain **Thesis Return Potential Components** so the raw expected return percentage can be explained.
- **Thesis Return Potential Components** should include valuation gap, growth, margin expansion, capital returns or dividends, and multiple re-rating when applicable.
- Thesis may include concise evidence notes or warnings that IC Gate can later use, but those notes should not be presented as final scoring.
- The visible row order in **Completed Thesis Table** should be the user-facing expression of **Thesis Selection Ranking**.
- **Completed Thesis Table** row order should reflect **Thesis Selection Ranking Model**, not an opaque qualitative judgment.
- **Thesis Selection Ranking** ties should break by **Thesis Return Potential**, then original handoff or generation order for stability.
- **Completed Thesis Table** should show current price, fair value, and expected return as the default valuation columns.
- In **Completed Thesis Table**, **Thesis Return Potential** should display as an expected return percentage.
- **Completed Thesis Table** should not show discount as a default valuation column because the core scan should focus on current price, fair value, and expected return.
- **Completed Thesis Table** should not need a rank-status column because row order and section placement communicate selection rank.
- **Completed Thesis Table** should not show **IC Conviction**, **IC Constitution Fit**, or **IC Data Quality** as default columns because IC Gate has not produced them yet.
- **Completed Thesis Table** should not show **Thesis Selection Score** as a default column because row order and section placement should communicate selection rank.
- **Thesis Review Actions** should be available directly from **Completed Thesis Table** rows.
- **Thesis Review Actions** should follow the same user experience pattern as **Screener Review Actions**.
- A **Thesis Promotion** should add the selected **Completed Thesis** to **Thesis Selection** and record the promotion as feedback.
- A **Thesis Dismissal** should remove the selected **Completed Thesis** from **Thesis Selection** for the current run while keeping it in **Remaining Theses**.
- A manual **Thesis Promotion** should expand **Thesis Selection** rather than silently displacing another selected Thesis.
- Reducing the number of selected completed Theses should be treated as a **Workflow Stage Selection Count** change rather than the default meaning of a row-level **Thesis Dismissal**.
- A **Thesis Dismissal** from the default **Thesis Selection** should let **Thesis Selection Ranking** reflow so lower-ranked completed Theses move up into **Thesis Selection** when enough eligible completed Theses remain.
- **Thesis Review Actions** should not change the **Thesis Selection Ranking Model** or original **Thesis Selection Ranking**.
- A manually promoted **Completed Thesis** should appear in **Thesis Selection** even if its original **Thesis Selection Ranking** was outside the default selection count.
- Manually promoted **Completed Thesis** artifacts should be appended to the end of **Thesis Selection** rather than inserted by original **Thesis Selection Ranking**.
- A removed **Completed Thesis** that is manually promoted again should be appended to the current end of **Thesis Selection**.
- The non-selected completed portion should preserve original **Thesis Selection Ranking** order while excluding current **Thesis Selection** members.
- A **Completed Thesis** removed from **Thesis Selection** should appear in **Remaining Theses** rather than disappearing or moving to a failed section.
- A **Completed Thesis** removed from **Thesis Selection** should not carry a visible stigma or rejection marker in **Remaining Theses**.
- Removing a **Completed Thesis** from **Thesis Selection** should create a **Thesis Selection Removal** record for learning-loop analysis.
- A **Thesis Selection Removal** should be treated as neutral deselection feedback, not as a rejection of the company, the Thesis, or the IC Review outcome.
- Manually adding a **Completed Thesis** to **Thesis Selection** should create a **Thesis Selection Addition** record for learning-loop analysis.
- A **Thesis Selection Addition** should be treated as selection feedback, not as IC Review execution, Memo approval, or a change to **Thesis Selection Ranking**.
- A **Thesis Selection Addition** should not regenerate the Completed Thesis, Thesis Selection Ranking explanation, or **Thesis Selection Ranking Components**.
- A **Completed Thesis** row should expand into **Completed Thesis Detail** when the user clicks the row rather than the ticker.
- **Completed Thesis Detail** should show the short Thesis prose alongside the **Completed Thesis Return Profile Panel**.
- **Completed Thesis Detail** should default to two quick-view panels: **Completed Thesis Return Profile Panel** and **Completed Thesis Prose Panel**.
- **Completed Thesis Detail** should give **Completed Thesis Prose Panel** more visual space than **Completed Thesis Return Profile Panel**.
- **Completed Thesis Return Profile Panel** should use the space freed by removing qualitative Thesis scores to expand the **Thesis Return Potential Components** breakdown.
- **Completed Thesis Return Profile Panel** should include current price, fair value, **Thesis Return Potential**, valuation method, and a component breakdown for valuation gap, growth, margin expansion, capital returns or dividends, and multiple re-rating when applicable.
- **Completed Thesis Return Profile Panel** should show whether return components sum coherently to **Thesis Return Potential** and surface concise return-source warnings when available.
- **Completed Thesis Return Profile Panel** may include a compact visual return stack or bar because return composition is the core Thesis quick-view evidence.
- **Completed Thesis Return Profile Panel** should include at most a short key-risk or evidence-warning line when available.
- **Completed Thesis Return Profile Panel** should not show **IC Conviction**, **IC Constitution Fit**, **IC Data Quality**, or other IC Gate scores.
- Fuller review of source support, **Thesis Return Potential Components**, and supporting data should happen on the **Company Page**, not inside **Completed Thesis Detail**.
- **Completed Thesis Prose Panel** should show a basic short prose summary of the Thesis writeup.
- **Completed Thesis Prose Panel** should emphasize **Thesis Opportunity Explanation** rather than **Thesis Ranking Explanation**.
- **Completed Thesis Prose Panel** should show a compressed summary of why the opportunity exists because expanded table rows have limited quick-view space.
- Full Completed Thesis reading should happen on the **Company Page** or **Library**, not inside **Completed Thesis Detail**.
- **Thesis Ranking Explanation** should live on the **Company Page** or another fuller detail surface, not in **Completed Thesis Detail** or the default table.
- Clicking the ticker in a **Completed Thesis** row should navigate to the **Company Page** rather than expanding the row.
- A **Thesis Run** should generate Thesis artifacts only and should not automatically execute IC Review or other downstream capabilities.
- A **Thesis Run** should remain available as the Thesis **Workflow Stage Execution Action**.
- A **Thesis Run** should generate every candidate in the current **Thesis Generation Scope** that does not already have a **Completed Thesis** artifact for that run context.
- A **Thesis Run** should preserve existing **Completed Thesis** artifacts rather than regenerating them by default.
- A **Thesis Run** should not be treated as a daily refresh or regeneration mechanism for existing **Completed Thesis** artifacts.
- Re-running Thesis within the same **Live FundOps Server Session** should behave as a **Thesis Run Resume** when the same Thesis Generation Queue was partially completed.
- A **Thesis Run Resume** should continue generating pending queued candidates rather than regenerating completed Thesis artifacts by default.
- A new completed **Screener Run** should create a **New Thesis Run** context by replacing the active **Thesis Intake**, **Thesis Candidate List**, **Thesis Generation Scope**, and **Thesis Generation Queue**.
- If a ticker from a **New Thesis Run** has a historical **Completed Thesis**, the active Thesis row should still be treated as not generated for the new run.
- A **New Thesis Run** should generate a new **Completed Thesis** artifact rather than silently reusing a historical **Completed Thesis** for the same ticker.
- After the **Live FundOps Server Session** ends, prior Thesis **Active Workflow Workbench State** should not remain the active **Thesis Intake**, **Thesis Candidate List**, or **Thesis Generation Queue**.
- Pending or in-flight Thesis generation state should become **Abandoned Workflow Work** when the **Live FundOps Server Session** ends.
- A **Thesis Run Resume** should not cross **Live FundOps Server Session** boundaries.
- Thesis should not automatically resume **Abandoned Workflow Work** after localhost restarts.
- After the **Live FundOps Server Session** ends, the user should run Screener again to create a new active **Thesis Intake** before starting Thesis.
- Clearing prior active Thesis workbench state should not delete or hide historical **Completed Thesis** artifacts.
- Historical **Completed Thesis** artifacts should not automatically repopulate the active Thesis workbench after a new **Live FundOps Server Session** starts.
- During a **Pipeline Run**, queued Thesis work should complete before **Thesis Selection** determines which completed Theses advance to IC Review.
- During a **Pipeline Run**, **Thesis Selection** should advance eligible completed Thesis artifacts up to the current **Thesis Selection Count**.
- The default **Thesis Selection Count** should be 10.
- During a **Pipeline Run**, IC Review should wait until the Thesis Generation Queue has completed and **Thesis Selection Ranking** has filled the current **Thesis Selection Count** when enough eligible completed Theses remain.
- During a **Pipeline Run**, a ticker in **Thesis Generation Failure** should not advance to IC Review because it has no **Completed Thesis** artifact.
- A completed **Thesis Run** should create or refresh the IC Review **Workflow Stage Handoff** for **Thesis Selection** without automatically executing IC Review.
- **Thesis Promotion** and **Thesis Dismissal** may update the IC Review **Workflow Stage Handoff** while preserving completed Thesis and IC artifacts as history.
- **IC Review Intake** should contain the **Thesis Selection** handed off from Thesis.
- IC Review should behave as a memo-worthiness gate, not a ranking stage.
- IC Review should consume the full **IC Review Evidence Package** rather than relying only on **Thesis Selection Score**, table rank, or a single numeric threshold.
- IC Review should apply **IC Semantic Thesis Review** to understand the Completed Thesis argument rather than copying a worker-agent judgment forward.
- **IC Semantic Thesis Review** should consider the **Thesis Return Potential**, **Thesis Return Potential Components**, Completed Thesis prose, key risks, evidence notes, active **Constitution**, and **IC Hurdles**.
- IC Gate should behave as the judging agent that produces **IC Conviction**, **IC Constitution Fit**, **IC Data Quality**, hard hurdle findings, and **IC Verdict**.
- **IC Conviction**, **IC Constitution Fit**, and **IC Data Quality** should be produced through an **IC Gate Scoring Model** rather than ad hoc prose judgment.
- **IC Scores** should use a normalized 0-100 internal scale so IC Gate decisions are auditable.
- **IC Scores** should be derived from **IC Score Components** rather than produced as unsupported single AI judgments.
- **IC Score Components** should be retained so IC scoring can be explained, compared, and tuned systematically.
- An **Unknown IC Score Component** should score as neutral 50 rather than zero or being excluded from the score average.
- Missing evidence behind an **Unknown IC Score Component** should reduce **IC Data Quality** rather than automatically destroying **IC Conviction** or **IC Constitution Fit**.
- A **Contradicted IC Score Component** should score below neutral because conflicting evidence is worse than missing evidence.
- A **Contradicted IC Score Component** should reduce the affected qualitative IC score and also reduce **IC Data Quality**.
- **IC Score Component Weights** should be fixed defaults rather than user-configurable strategy settings.
- Within each IC qualitative score, **IC Score Component Weights** should be equal because each retained subcomponent is considered important.
- The **IC Gate Scoring Model** should use the same qualitative score components and component weights across strategies.
- The top-level **IC Gate Score Blend** is separate from **IC Score Component Weights** because it combines the three final IC Scores into one memo-worthiness score.
- The default **IC Gate Score Blend** should weight **IC Conviction** at 45%, **IC Constitution Fit** at 35%, and **IC Data Quality** at 20%.
- Strategy Chat may define, default, or change the **IC Gate Score Blend** through reviewable **Strategy Drafts** or **Strategy Change Proposals**.
- Proposed **IC Gate Score Blend** changes should appear in the **Strategy Draft Wiring Preview** before approval.
- **IC Gate Score Blend** should be projected into IC Review through **Strategy Wiring** and **Settings Projection**.
- The default **IC Pass Cutoff** should be 70/100.
- Strategy Chat may define, default, or change the **IC Pass Cutoff** through reviewable **Strategy Drafts** or **Strategy Change Proposals**.
- Automated **IC Pass** should require all **Hard IC Hurdles** to be satisfied and **IC Gate Score** to meet or exceed the active **IC Pass Cutoff**.
- A confirmed **IC Hurdle Miss** should produce an automated **IC Fail** regardless of **IC Gate Score** unless the user manually creates an **IC Promotion**.
- Very low **IC Conviction**, **IC Constitution Fit**, or **IC Data Quality** may impose an IC Gate score cap or forced fail guardrail because a severe weakness in any one dimension can make Memo spend inappropriate.
- **IC Conviction** should be separate from **Thesis Return Potential** because return potential describes payoff size while IC Conviction describes confidence that the argument is credible enough for Memo spend.
- **IC Conviction Components** should include argument strength, evidence support, catalyst or path clarity, risk-adjusted downside, assumption sensitivity, and precedent or similar-case support.
- **IC Constitution Fit** should be separate from **IC Conviction** because Constitution fit describes strategy alignment while conviction describes argument credibility.
- **IC Constitution Fit** should not automatically become zero when a Completed Thesis misses one numeric Strategy Criterion.
- **IC Constitution Fit** should evaluate proportional alignment with the active **Constitution**, **Strategy North Star**, and **Inferred Strategy Intent**.
- Numeric **Strategy Criteria** should be interpreted as evidence of the user's desired company profile, not as the only expression of strategy fit inside IC Gate.
- **Strategy North Star** and **Inferred Strategy Intent** should inform **IC Constitution Fit** as interpretive evidence, not replace exact **Strategy Criteria** or create hidden Screening Requirements.
- **IC Constitution Fit Components** should include exact **Strategy Criteria** alignment, **Strategy North Star** or **Inferred Strategy Intent** alignment, anti-signal avoidance, and data-support or proxy confidence for the fit evidence.
- Exact **Strategy Criteria** alignment should remain the primary evidence inside **IC Constitution Fit**.
- **Strategy North Star** and **Inferred Strategy Intent** alignment should explain strategic meaning, not override exact criteria.
- **IC Data Quality** should be separate from **IC Conviction** because data quality describes trust in the inputs while conviction describes strength of the investment argument.
- **IC Data Quality Components** should include data freshness, financial data completeness, source grounding confidence, entity or source correctness, return-source validation warnings, and contradictions or unsupported claims.
- **IC Hurdles** should be applied as explicit memo-worthiness gates inside IC Review rather than as hidden ranking preferences.
- **IC Hurdles** should be owned by the active **Constitution** rather than hidden agent configuration.
- Strategy Chat should define, default, or change **IC Hurdles** through reviewable **Strategy Drafts** or **Strategy Change Proposals**.
- Proposed **IC Hurdles** should appear in the **Strategy Draft Wiring Preview** before approval.
- **IC Hurdles** should be projected into IC Review through **Strategy Wiring** and **Settings Projection**.
- Agent configuration may provide fallback IC Hurdle defaults, but should not become the user-facing source of truth after a **Constitution** exists.
- IC Review should record or reference the **Constitution Version** whose **IC Hurdles** produced the IC Verdict.
- IC Review should treat explicit **IC Hurdles** as **Hard IC Hurdles** by default.
- A confirmed **IC Hurdle Miss** should be evaluated before the **IC Gate Score** and should produce an automated **IC Fail** rather than an automated **IC Pass**.
- **IC Semantic Thesis Review** should decide whether the evidence package truly satisfies or misses each **Hard IC Hurdle**, especially when the raw signal is ambiguous.
- **IC Semantic Thesis Review** may conclude that an ambiguous raw signal still satisfies a **Hard IC Hurdle** when the Completed Thesis and retained signal rationale support that conclusion.
- **IC Semantic Thesis Review** should preserve the explanation for each **Hard IC Hurdle** decision so the user can see why the hurdle was treated as met or missed.
- A user may manually override an automated **IC Fail** from an **IC Hurdle Miss** through **IC Promotion**.
- An **IC Review Run** should automatically run IC Review on every eligible item in **IC Review Intake** that does not already have an IC Verdict in the current active context.
- Re-running IC Review within the same active IC Review context should not rerun already completed **IC Verdicts** by default.
- A refreshed **IC Review Intake** from a new active Thesis context should create a new active IC Review context.
- If a ticker in a new active IC Review context has a historical **IC Verdict**, the active IC row should still be treated as pending until IC Review runs for the current context.
- A new active IC Review context should produce fresh **IC Verdicts** for the current **Completed Thesis** artifacts under the current **Constitution Version** rather than silently reusing historical **IC Verdicts**.
- Historical **IC Verdicts** should remain available through the **Company Page**, **Library**, or other history surfaces without automatically repopulating the active IC Review context.
- Each saved **IC Verdict** should preserve **Saved IC Verdict Evidence**.
- **Saved IC Verdict Evidence** should include the judged **Completed Thesis** reference, **Thesis Return Potential** and return components consumed, **IC Conviction**, **IC Constitution Fit**, **IC Data Quality**, **IC Gate Score**, **IC Gate Score Blend**, **IC Pass Cutoff**, hard hurdle pass or miss state, **Constitution Version**, and short **IC Verdict Rationale**.
- **Saved IC Verdict Evidence** should be frozen at verdict time rather than reconstructed only from latest ticker, latest Thesis, or latest Constitution state.
- **Saved IC Verdict Evidence** should let **Company Page**, **Library**, and history surfaces explain why IC Review passed or failed the opportunity later.
- The exact database schema and storage design for **Saved IC Verdict Evidence** belong in the database design spec; this context defines the product behavior that the evidence must be preserved.
- An **IC Review Run** should produce **IC Verdicts** and create or refresh **Memo Intake** from **IC Selection** without automatically executing Memo.
- If IC Review fails operationally for an item, the item should enter **IC Review Retry** rather than **IC Fail**.
- **IC Review Retry** should follow the same automatic retry behavior as peer workflow capabilities.
- If IC Review retries are exhausted, the item should enter **IC Review Failure**, remain visible as an operational failure, and be excluded from **Memo Intake**.
- **IC Review Failure** should not count as an **IC Verdict** and should not be treated as a failed investment judgment.
- After an **IC Review Run**, opportunities with **IC Pass** should appear in **IC Selection**.
- After an **IC Review Run**, opportunities with **IC Fail** should appear in **Remaining IC Reviews**.
- An **IC Pass** should mean IC Review judged the opportunity worthy of Memo spend after interpreting the Completed Thesis, return profile, active Constitution, **IC Scores**, and **IC Hurdles**.
- An **IC Fail** should mean IC Review judged the opportunity not worthy of Memo spend in the current active context.
- Every **IC Pass** should enter **IC Selection** by default because the IC Verdict means the opportunity is worthy of Memo spend.
- **IC Selection** should not apply a separate target count or cap after IC Verdicts are produced.
- **IC Selection** should appear as the contiguous yellow-bordered selected block that advances to Memo.
- The yellow-bordered **IC Selection** block should contain automated **IC Pass** rows and user-promoted rows.
- **IC Selection** should become **Memo Intake** after an **IC Review Run**.
- **IC Pass** rows in **IC Selection** should be handed to **Memo Intake** automatically without a separate send action.
- Running IC Review from the IC Review capability should stop after updating **Memo Intake**.
- During a **Pipeline Run**, Memo should run after IC Review using the **Memo Intake** created from **IC Selection**.
- A Memo run should produce one **Completed Memo** per eligible **Memo Intake** item by default.
- The user-facing label for a **Completed Memo** should be **Investment Memo**.
- The active Memo workflow starts clean: the active Memo output should be an **Investment Memo Artifact**.
- The new **Investment Memo Artifact** cleanly replaces both the old Research Memo and the old lightweight Investment Memo.
- The active Memo workflow should not preserve separate Research Memo versus Investment Memo artifact types for active Memo generation.
- Prior Research Memo behavior is a foundation for depth and evidence handling, not an active stored artifact type or backward-compatibility obligation.
- The UI and workflow adapter should expose one **Investment Memo Generation Action** for active Memo generation.
- The user-facing label for the **Investment Memo Generation Action** should be Generate Investment Memo.
- The active Memo workflow should not expose Research Report, Investment Memo, or both-mode generation choices by default.
- The backend product contract for Memo should use a single **Investment Memo Generation Mode**.
- Product behavior should not preserve `research`, `investment`, or `both` mode branching for active Memo generation.
- Memo implementation should prioritize a straightforward active **Investment Memo** pipeline over preserving compatibility with existing Research Report or lightweight Investment Memo branches.
- Existing memo code may be reused as source material for behavior, schemas, data distribution, and rendering, but should not constrain the active product contract.
- Memo implementation should define the **Investment Memo Structured Output Schema**, evidence distribution, source registry use, generation order, and structured artifact assembly before UI changes.
- UI changes for Memo should follow the backend **Investment Memo Artifact** contract.
- A **Completed Memo** should combine company, financial, valuation, risk, and industry research depth with investment-oriented and Constitution-tailored analysis.
- **Completed Memo** research, valuation, return path, assumptions, and risks should be memo-native rather than inherited from **Completed Thesis**.
- **Completed Thesis** may provide upstream provenance for why the opportunity reached IC Review, but it should not be the source of truth for **Completed Memo** analysis.
- **Investment Memo** writing should use an **Investment Memo Evidence Package** rather than treating **Completed Thesis** as reference material.
- An **Investment Memo Evidence Package** should combine **Investment Memo Filing and Financial Evidence** with **Investment Memo Market Intelligence Evidence**.
- **Investment Memo Filing and Financial Evidence** should provide company history, business description, reported financials, valuation inputs, peer comparisons, and filing-disclosed risks.
- **Investment Memo Market Intelligence Evidence** should provide recent events, current market expectations, catalysts, active risks, analyst views, ownership context, price context, and competitive developments that may not appear in filings.
- **Investment Memo Market Intelligence Evidence** should be normalized into **Normalized Investment Memo Market Evidence** before section distribution when it supports material memo claims.
- **Normalized Investment Memo Market Evidence** should use readable source labels and citation targets rather than exposing raw URLs in memo prose.
- **Investment Memo Evidence Distribution** should decide which filing, financial, market-intelligence, and strategy-emphasis inputs belong in each section-specific evidence package.
- **Investment Memo Evidence Distribution** should be the canonical boundary that turns memo-native evidence into section-specific evidence packages before section writing.
- Every **Investment Memo Section Evidence Package** should use a shared section-evidence contract while only populating the evidence lanes relevant to that section.
- **Investment Memo Section Evidence Packages** should preserve the existing Research Memo behavior where section writers receive curated section-specific inputs instead of a rigid whole-memo envelope.
- Empty or unavailable evidence lanes should be represented when they matter for evidence quality, but not forced into every section when irrelevant.
- Each top-level Investment Memo section should be written from an **Investment Memo Section Evidence Package**.
- An **Investment Memo Section Evidence Package** should include only the memo-native evidence needed for that section.
- **Completed Thesis** should not be included in **Investment Memo Section Evidence Packages**.
- **IC Verdict**, **IC Verdict Rationale**, **IC Scores**, and **Saved IC Verdict Evidence** should not be included in **Investment Memo Section Evidence Packages**.
- **Investment Memo Provenance** may record that an opportunity reached Memo through **IC Selection**, but that provenance should not influence the memo argument.
- Every **Investment Memo** should use a fixed **Investment Memo Outline** so users can compare memo artifacts across companies and runs.
- The final rendered **Investment Memo Outline** should have exactly seven top-level sections: Current Setup & Variant View, Business Quality, Industry and Growth, Financial Quality, Valuation, Risks, Bear Case & Kill Criteria, and Decision Summary.
- Every top-level **Investment Memo Outline** section should include an internal **Investment Memo Section Thesis**.
- **Investment Memo Section Thesis** should support validation, synthesis, and section coherence but should not render as a visible memo subsection by default.
- The active **Investment Memo** should preserve the **Investment Memo Source Registry** behavior from the **Research Memo Foundation**.
- The **Investment Memo Source Registry** should deduplicate the same source across filing, financial, market-intelligence, table, and section evidence where appropriate.
- Distinct filings, dated pages, or materially different source records may keep separate citation identities.
- Each **Investment Memo Section Evidence Package** should carry the source-registry references for evidence made available to that section.
- Each top-level section and material subsection should be able to produce **Investment Memo Evidence References** back to supplied source-registry entries or financial evidence references.
- Section writers should only use **Investment Memo Evidence References** that were supplied through the section evidence package.
- **Investment Memo Evidence References** should be retained as internal structured provenance and rendered as **Investment Memo Visible Citations** where useful to the reader.
- **Investment Memo Visible Citations** should make material subsections and tables source-traceable without requiring citation markers after every sentence.
- Filing and financial data should keep an **Investment Memo Financial Citation** such as a distinct filing marker rather than being forced into ordinary web-source numbering.
- Investment Memo tables should show provenance through a nearby caption, title note, or footnote rather than citation markers inside table cells.
- **Investment Memo Visible Citations** should use global numbering across the whole Investment Memo rather than restarting per section.
- Clicking an **Investment Memo Visible Citation** should open an **Investment Memo Citation Popover** rather than exposing a raw URL inline.
- An **Investment Memo Citation Popover** should show the clean source title or label, publisher or domain when available, a hyperlink action to open the source, and a clear close control.
- An **Investment Memo Citation Popover** does not need to repeat the memo section or subsection because the clicked citation marker already provides local context.
- The **Investment Memo Generation Order** should run evidence collection, **Investment Memo Research Agent Stage**, **Investment Memo Evidence Distribution**, **Investment Memo Core Body Section** writing, valuation writing and math correction, **Current Setup & Variant View** synthesis, **Investment Memo Decision Summary Section** synthesis, and deterministic final assembly.
- **Investment Memo Generation Order** may differ from the final **Investment Memo Outline** reading order when later sections need earlier section evidence.
- Core evidence sections may be generated before synthesis-like sections even if they appear later in the final **Investment Memo Outline**.
- **Investment Memo Business Quality Section**, **Investment Memo Industry and Growth Section**, **Investment Memo Financial Quality Section**, and **Investment Memo Risk Section** are **Investment Memo Core Body Sections** by default.
- **Current Setup & Variant View** and **Investment Memo Decision Summary Section** are **Investment Memo Synthesis Sections** by default.
- The **Investment Memo Risk Section** should be generated before the **Investment Memo Valuation Section** so risk evidence can inform bear-case assumptions, sensitivity factors, and probability weights.
- The final **Investment Memo Outline** should still render the **Investment Memo Valuation Section** before the **Investment Memo Risk Section**.
- **Current Setup & Variant View** should be generated after core evidence and valuation sections so it can synthesize current events, business quality, financial quality, risks, and valuation conclusions.
- The final **Investment Memo Outline** should still render **Current Setup & Variant View** first.
- The **Investment Memo Decision Summary Section** should be generated last from the completed body sections and structured risk and valuation outputs.
- The **Investment Memo Decision Summary Section** should synthesize existing memo evidence rather than introduce new evidence.
- Every **Investment Memo Subsection** should use a fixed strategy-neutral name that works across strategy styles.
- Investment Memo generation should use an **Investment Memo Structured Output Schema** rather than free-form prose as the primary output contract.
- The **Investment Memo Structured Output Schema** should be applied per top-level **Investment Memo Outline** section rather than as one whole-document schema.
- The **Investment Memo Structured Artifact** should be the canonical stored Memo artifact.
- **Investment Memo Rendered Snapshot** may be stored for reading and export, but should be generated from the **Investment Memo Structured Artifact**.
- HTML should be treated as a render-time output or optional cache rather than the canonical Investment Memo artifact.
- The **Investment Memo Structured Artifact** should retain a compact record of the **Investment Memo Section Evidence Packages** actually given to section writers.
- Stored section-evidence provenance should prefer evidence item IDs, source references, normalized snippets, and hashes over large raw filing or web-research blobs.
- **Investment Memo Evidence Gaps** should be curated and severity-ranked rather than exhaustively dumped into the memo body.
- Material **Investment Memo Evidence Gaps** should live primarily in the Evidence Gaps subsection of the **Investment Memo Decision Summary Section**.
- The rendered Evidence Gaps subsection should usually show only the top three to five decision-relevant **Investment Memo Evidence Gaps**.
- Inline evidence-gap notes should appear only when a gap directly weakens a specific section conclusion.
- Non-material operational data gaps should remain in metadata or provenance rather than making the rendered memo feel unfinished.
- If too many material **Investment Memo Evidence Gaps** remain, the **Memo Decision** should lean toward needs more evidence.
- The active **Investment Memo** should not add a separate evidence-quality badge or extra reader-facing data-quality surface by default.
- Per-section Investment Memo structured output should allow failed sections to be retried and validated without regenerating the entire memo.
- Completed per-section Investment Memo outputs should be assembled deterministically into the final **Completed Memo**.
- The active **Constitution** should change **Investment Memo Strategy Emphasis** inside the fixed outline rather than replacing the top-level section structure.
- **Investment Memo Strategy Emphasis** should not rename, remove, or rearrange **Investment Memo Subsections**.
- The first section in the fixed **Investment Memo Outline** should be **Current Setup & Variant View**.
- **Current Setup & Variant View** should include fixed **Investment Memo Subsections** named Why Now, Recent Events, Market View, Variant View, and Evidence Quality.
- **Current Setup & Variant View** should absorb the current-events, price-action, earnings-and-guidance, macro, and sector context that was previously scattered through neutral research-report sections.
- The fixed **Investment Memo Outline** should include an **Investment Memo Business Quality Section**.
- The **Investment Memo Business Quality Section** should include fixed **Investment Memo Subsections** named Business Model, Products and Value Chain, Moat and Defensibility, Management and Capital Allocation, and Quality Watch Items.
- Products and Value Chain content should adapt to sector context while keeping the subsection name fixed.
- Management and capital allocation should be fixed content inside the **Investment Memo Business Quality Section** rather than a separate top-level memo section by default.
- **Investment Memo Strategy Emphasis** may expand management and capital allocation analysis when leadership, governance, reinvestment, buybacks, or M&A quality are central to the strategy or thesis.
- The fixed **Investment Memo Outline** should include an **Investment Memo Industry and Growth Section**.
- The **Investment Memo Industry and Growth Section** should include fixed **Investment Memo Subsections** named Industry Structure, Customer and Demand Dynamics, Growth Drivers, Competitive Position, and Growth Watch Items.
- Near-term catalysts should live in **Current Setup & Variant View**, while durable growth context should live in the **Investment Memo Industry and Growth Section**.
- The fixed **Investment Memo Outline** should include an **Investment Memo Financial Quality Section**.
- The **Investment Memo Financial Quality Section** should include fixed **Investment Memo Subsections** named Revenue and Margin Quality, Cash Flow and Balance Sheet, Returns on Capital, Peer Benchmarking, and Financial Watch Items.
- Sector-specific financial analysis should adapt inside the fixed **Investment Memo Financial Quality Section** subsection names rather than creating separate top-level financial sections.
- The fixed **Investment Memo Outline** should include an **Investment Memo Valuation Section**.
- The **Investment Memo Valuation Section** should include fixed **Investment Memo Subsections** named Valuation Method, Base Case, Upside and Downside Cases, Memo Return Drivers, and Key Assumptions.
- **Investment Memo Valuation Judgment** should be allowed to interpret the memo-native evidence and choose scenario assumptions, probability weights, and key return drivers.
- **Investment Memo Valuation Math** should ground, validate, or correct fair-value, upside, downside, and sensitivity outputs produced from valuation assumptions.
- The **Investment Memo Valuation Section** should combine **Investment Memo Valuation Judgment** with **Investment Memo Valuation Math** rather than being purely mechanical or purely prose-driven.
- **Memo Return Drivers** should be memo-native rather than copied from **Thesis Return Potential Components**.
- A **Memo Return Driver** should be marked not applicable or unsupported when the memo-native evidence does not support it.
- The fixed **Investment Memo Outline** should include an **Investment Memo Risk Section**.
- The **Investment Memo Risk Section** should include fixed **Investment Memo Subsections** named Key Risks, Bear Case, Sensitivity Factors, Kill Criteria, and Risk Watch Items.
- **Kill Criteria** should be concrete memo-native conditions rather than generic downside possibilities.
- The fixed **Investment Memo Outline** should end with an **Investment Memo Decision Summary Section**.
- The **Investment Memo Decision Summary Section** should include fixed **Investment Memo Subsections** named Investment Case Summary, Decision, Open Questions, and Evidence Gaps.
- The **Investment Memo Monitoring Plan** should be retained separately from the visible **Investment Memo Decision Summary Section** so the **Company Page Thesis Health Section** can use it directly.
- Each **Investment Memo Monitoring Plan** should be tied to the specific **Completed Memo** version that produced it.
- Generating a new **Completed Memo** should create a new **Investment Memo Monitoring Plan** rather than mutating the prior memo version's plan in place.
- The newest **Completed Memo** should automatically become the active source for **Memo-Backed Thesis Health**.
- Older **Investment Memo Monitoring Plans** should remain historical rather than continuing to drive current Thesis Health after a newer **Completed Memo** exists.
- Older **Thesis Watch Items** should be frozen as historical when a newer **Completed Memo** becomes active, even when the new memo tracks a similar metric or threshold.
- Similar **Thesis Watch Items** across memo versions may be linked later for continuity analysis, but should not be automatically carried forward as the active memo's judgment.
- Historical **Investment Memo Monitoring Plans** and prior Thesis Health checks should be inspectable as Company Page history rows or milestones.
- Selecting a historical Thesis Health row or milestone should open detail in the **Company Page Milestone Preview** pattern rather than expanding the active Thesis Health section inline.
- Routine historical **Investment Memo Monitoring Plans** and Thesis Health checks should appear inside the **Company Page Thesis Health Section** history list rather than the main **Company Page Workflow Map**.
- The **Company Page Thesis Health Section** should show active watch items first, followed by a compact Thesis Health history list.
- The **Company Page Thesis Health Section** should not use nested tabs for baseline history access.
- A **Memo Decision** should be memo-native rather than an **IC Verdict** or portfolio trade instruction.
- An **Investment Memo Monitoring Plan** should translate memo assumptions, return drivers, risks, and kill criteria into concrete watch items.
- Memo generation should be harnessed to produce supported quantitative **Thesis Watch Items** from the memo evidence and available supported metrics whenever possible.
- Memo generation should receive the **Supported Thesis Health Field Catalog** directly when producing the **Investment Memo Monitoring Plan**.
- Memo generation should choose quantitatively monitored **Thesis Watch Items** from the **Supported Thesis Health Field Catalog** rather than free-typing metric names.
- Memo generation should propose thesis-relevant thresholds for quantitatively monitored **Thesis Watch Items**.
- FundOps should validate proposed Thesis Watch Item thresholds against available current and historical data before allowing them to drive **Memo-Backed Thesis Health** status.
- Memo generation should produce the **Investment Memo Monitoring Plan** as structured output that deterministic validation can check before Thesis Watch Items become status-driving.
- If **Investment Memo Monitoring Plan** validation fails, the repair attempt should happen inside the memo generation harness using precise validation errors.
- Investment Memo Monitoring Plan repair should target invalid **Thesis Watch Items** only, preserving valid watch items from the same plan.
- If bounded repair still cannot produce a valid supported quantitative **Thesis Watch Item**, the affected item should be downgraded to unsupported rather than silently driving status.
- A **Completed Memo** should still complete even if the **Investment Memo Monitoring Plan** has no supported quantitative **Thesis Watch Items**.
- The company-research depth previously described as a standalone **Research Memo** should be folded into the **Completed Memo** unless a separate product decision explicitly reintroduces a neutral company report.
- A **Pipeline Run** should generate **Completed Memos** rather than separate **Research Memo** and **Investment Memo** artifacts.
- The active **Investment Memo** should use the **Research Memo Foundation** rather than the legacy lightweight Investment Memo path.
- The **Research Memo Foundation** should be restructured into the fixed **Investment Memo Outline** and trimmed where old neutral-report sections no longer earn their place.
- The **Research Memo Foundation** should preserve the rich company, filing, financial, valuation, table, and section-specific evidence behavior from the old Research Memo.
- **Investment Memo Company Context** should remain in the active **Investment Memo**, but should be concise and oriented around recent history and why the opportunity exists.
- The legacy standalone Company History & Key Milestones research-report section should not remain a top-level **Investment Memo Outline** section.
- Company history should be distributed into **Current Setup & Variant View**, Business Model, Products and Value Chain, or Management and Capital Allocation when it explains the current opportunity.
- The legacy standalone Product & Technology Strategy research-report section should not remain a top-level **Investment Memo Outline** section.
- Product, service, technology, asset, and value-chain depth from the **Research Memo Foundation** should live inside the Products and Value Chain subsection of the **Investment Memo Business Quality Section**.
- Products and Value Chain should adapt its content to sector context while keeping its fixed subsection name.
- The legacy standalone Competitive Moats research-report section should not remain a top-level **Investment Memo Outline** section.
- Moat, defensibility, brand, switching-cost, scale, network-effect, cost-advantage, regulatory, data, distribution, and durability analysis from the **Research Memo Foundation** should live inside the Moat and Defensibility subsection of the **Investment Memo Business Quality Section**.
- **Investment Memo Strategy Emphasis** may expand Moat and Defensibility when business quality or durability is central to the active Constitution.
- The legacy standalone Management & Capital Allocation research-report section should not remain a top-level **Investment Memo Outline** section by default.
- Management, governance, incentives, buybacks, dividends, reinvestment, M&A, leverage choices, and capital discipline analysis from the **Research Memo Foundation** should live inside the Management and Capital Allocation subsection of the **Investment Memo Business Quality Section**.
- The legacy standalone Customer Analysis research-report section should not remain a top-level **Investment Memo Outline** section.
- Customer, channel, counterparty, tenant, policyholder, borrower, demand, retention, volume, and distribution analysis from the **Research Memo Foundation** should live inside the Customer and Demand Dynamics subsection of the **Investment Memo Industry and Growth Section**.
- Customer and Demand Dynamics should adapt its content to sector context while keeping its fixed subsection name.
- The legacy standalone Industry & Competitive Dynamics research-report section should not remain a top-level **Investment Memo Outline** section.
- Industry structure, market size, cyclicality, regulation, supply and demand, value-chain power, structural tailwinds, and structural headwinds from the **Research Memo Foundation** should live inside the Industry Structure subsection of the **Investment Memo Industry and Growth Section**.
- Competitive position, market share, relative advantages, rivals, and share-gain or share-loss evidence from the **Research Memo Foundation** should live inside the Competitive Position subsection of the **Investment Memo Industry and Growth Section**.
- The legacy standalone Growth Prospects & Catalysts research-report section should not remain a top-level **Investment Memo Outline** section.
- Durable medium-term and long-term growth drivers from the **Research Memo Foundation** should live inside the Growth Drivers subsection of the **Investment Memo Industry and Growth Section**.
- Near-term catalysts, upcoming events, and recent developments that explain why the opportunity matters now should live inside **Current Setup & Variant View**.
- The legacy standalone Financial Analysis and Peer Benchmarking research-report sections should not remain separate top-level **Investment Memo Outline** sections.
- Revenue, margin, cash-flow, balance-sheet, returns-on-capital, peer-comparison, precomputed-table, and sector-KPI behavior from the **Research Memo Foundation** should live inside the **Investment Memo Financial Quality Section**.
- Peer comparison depth from the **Research Memo Foundation** should live inside the Peer Benchmarking subsection of the **Investment Memo Financial Quality Section**.
- The legacy standalone Risk Assessment research-report section should map into the **Investment Memo Risk Section**.
- Filing-disclosed risks, sector-specific risk metrics, litigation, regulatory issues, active market-intelligence risks, bear-case framing, sensitivity factors, kill criteria, and risk watch items should live inside the **Investment Memo Risk Section**.
- The legacy Executive Summary & Investment Thesis and Key Takeaways or Conclusion research-report sections should not remain separate top-level **Investment Memo Outline** sections.
- Opening synthesis behavior from the **Research Memo Foundation** should live inside **Current Setup & Variant View**.
- Closing synthesis behavior from the **Research Memo Foundation** should live inside the **Investment Memo Decision Summary Section**.
- The active **Investment Memo** should avoid duplicate summary and conclusion sections.
- The **Superseded Lightweight Investment Memo Path** should be deprecated for the active Memo workflow.
- Useful pieces from the **Superseded Lightweight Investment Memo Path** may be reused as inputs, framing, or prompts, but its structure and writer flow should not define the active **Investment Memo**.
- The active **Investment Memo** should preserve an **Investment Memo Research Agent Stage** before section writing.
- The **Investment Memo Research Agent Stage** should be reshaped around the fixed **Investment Memo Outline** and memo-native evidence planes rather than the old neutral Research Memo section map.
- Outputs from the **Investment Memo Research Agent Stage** should flow through **Investment Memo Evidence Distribution** rather than being given wholesale to every section writer.
- **Remaining IC Reviews** should appear below **IC Selection** and preserve the IC Verdict context rather than disappearing.
- **Remaining IC Reviews** should serve as the lower IC-reviewed candidate list for automated **IC Fail** rows and manually removed rows.
- **IC Review Table** should keep collapsed rows very simple.
- **IC Review Summary Row** should default to ticker, company name, current price, and **IC Verdict**.
- Before an automated **IC Verdict** exists, the IC Verdict position in **IC Review Summary Row** may show pending, running, retry, or operational failure state.
- **IC Review Summary Row** should not show base return, bear return, **IC Scores**, key risk, hard hurdle detail, constitution scorecard, date, similar research, or full rationale as default columns.
- Row-level selection controls, when available, should remain compact action affordances and should not turn the collapsed row into an analysis table.
- An IC Review row should expand into **IC Review Detail** when the user clicks the row rather than the ticker.
- **IC Review Detail** should follow the same expanded-row interaction pattern as **Screener Candidate Detail** and **Completed Thesis Detail**.
- **IC Review Detail** should display capability-specific IC content rather than changing the shared expanded-row behavior.
- **IC Review Detail** should be a concise quick-view panel, not the full IC review, full Completed Thesis, or full Memo thesis.
- **IC Review Detail** should be organized around the **IC Detail Evidence Snapshot**.
- **IC Review Detail** should show a short **IC Verdict Rationale** explaining why the opportunity passed or failed IC Review.
- **IC Detail Evidence Snapshot** should include hard hurdle pass or miss state, **IC Conviction**, **IC Constitution Fit**, and **IC Data Quality**.
- **IC Review Detail** should show those three IC scores compactly rather than expanding into the raw IC score component breakdown.
- **IC Review Detail** should not include a key-risk section by default; key risk can live in the fuller **Company Page** or historical evidence surface.
- **IC Review Detail** should avoid defaulting to long AI review prose, full constitution scorecards, full bear-case workups, or full similar-research discussion.
- Concise IC dropdown content may link to fuller **Company Page** evidence rather than expanding in place.
- Full supporting evidence behind the IC decision should live on the **Company Page** or historical artifact surfaces rather than crowding **IC Review Detail**.
- **IC Promotion** and **IC Removal** should become available only after an automated **IC Verdict** exists for the opportunity in the current active context.
- A row-level plus action on an **IC Fail** should create an **IC Promotion** by recording an **IC Override** to **IC Pass** and adding the opportunity to **IC Selection**.
- A row-level minus action on an **IC Pass** should create an **IC Removal** by recording an **IC Override** to **IC Fail** and moving the opportunity to **Remaining IC Reviews**.
- Pressing plus in **Remaining IC Reviews** should move that opportunity up into the yellow-bordered **IC Selection** block.
- Pressing minus in **IC Selection** should move that opportunity down into **Remaining IC Reviews**.
- **IC Removal** should mean the opportunity manually failed IC Review, not that it was softly skipped because of Memo capacity.
- An **IC Override** should preserve whether the path was set by the user rather than produced by the automated IC Review.
- An **IC Override** should preserve the prior automated IC Verdict when one exists.
- **IC Override** should be scoped to the active IC Review context that created it.
- A future active IC Review context should start from its own automated **IC Verdict** rather than automatically carrying forward a historical **IC Override**.
- Historical **IC Overrides** may inform learning-loop analysis or future **Strategy Change Proposals**, but should not silently change future IC Review behavior.
- After all queued Thesis work finishes, the Thesis capability should separate **Thesis Selection** from **Remaining Theses**.
- **Thesis Selection** and **Remaining Theses** should partition the completed Thesis artifacts from the relevant Thesis Generation Queue.
- **Remaining Theses** may be empty when the number of completed Theses does not exceed the **Thesis Selection** count.
- After a completed **Thesis Run**, the Thesis capability should not keep a separate pending-candidate table for candidates that successfully generated Theses.
- After Thesis generation finishes, the Thesis surface should show **Thesis Selection** rather than a generation-selection surface.
- Manually expanding **Thesis Selection** should expand the **Thesis Selection Count** for the active handoff.
- Expanded **Thesis Selection Count** should cause additional eligible completed Theses to advance to IC Review by default.
- The post-generation **Thesis Selection** block should follow the same selected/remaining surface behavior as **Top Picks** and **Remaining Candidates** in Screener.
- **Thesis Selection Ranking** should decide which completed Thesis artifacts fill the current **Thesis Selection Count** for IC Review.
- **Thesis Selection Ranking** should use a simple **Thesis Selection Ranking Model** based on **Thesis Return Potential**, return-source support, and stable handoff or generation order.
- **Thesis Selection Ranking** should not use **IC Conviction**, **IC Constitution Fit**, **IC Data Quality**, or any other IC Gate score because those are produced after IC Review.
- The default **Thesis Selection Ranking Model** should prioritize **Thesis Return Potential** while considering whether return components are present and internally coherent.
- **Thesis Selection Ranking Model** should be simpler than **Screener Ranking Blend** because Thesis is selecting attractive opportunities for IC Review, not making the memo-worthiness judgment.
- Very weak or unsupported **Thesis Return Potential** may impose a **Thesis Selection Score Cap** because the opportunity is not attractive enough to deserve automatic IC Review.
- **Thesis Selection Score Cap Thresholds** should be fixed globally rather than configurable through Strategy Chat.
- A **Thesis Selection Score Cap** should limit ranking priority without deleting the **Completed Thesis** or treating it as an IC Review verdict.
- A capped **Completed Thesis** should remain visible without being branded as failed.
- A capped **Completed Thesis** may show a compact warning in **Completed Thesis Detail** or the **Company Page** explaining that the return profile imposed the cap.
- A capped **Completed Thesis** should remain eligible for manual **Thesis Promotion**.
- Manual **Thesis Promotion** of a capped **Completed Thesis** should preserve the cap warning rather than hiding the weak return profile.
- A capped **Completed Thesis** should not automatically enter the selected or bordered **Thesis Selection** block.
- A capped **Completed Thesis** should require manual **Thesis Promotion** to enter **Thesis Selection**.
- After Thesis ranking, a capped **Completed Thesis** should move out of the bordered **Thesis Selection** block into **Remaining Theses**.
- A capped **Completed Thesis** should not be sent to IC Review automatically.
- If fewer eligible completed Theses remain than the current **Thesis Selection Count**, the **Thesis Selection** block should contain fewer items rather than automatically including capped or ineligible Theses.
- **Thesis Selection Ranking Components** should be retained so a user can understand why one completed Thesis advanced before another.
- During a **Pipeline Run**, manually adding a candidate to **Top Picks** before Thesis work begins should add it to the **Thesis Candidate List** and **Thesis Generation Scope** by default.
- During a **Pipeline Run**, Thesis controls should not expose **Thesis Promotion** or **Thesis Dismissal** until Thesis artifacts exist.
- Once **Completed Thesis** artifacts exist, **Thesis Promotion** and **Thesis Dismissal** may update **Thesis Selection** and the IC Review handoff without deleting completed artifacts.
- Detailed controls for **Thesis Selection** belong to the Thesis capability, not the Screener capability.
- The **Workflow Funnel** should normally narrow from 50 visible Screener Candidates to 20 Thesis candidates, then 10 IC Review candidates, then however many IC Review candidates pass to Memo.
- "About 5 Memo candidates" is an expected result of IC Review strictness, not a separate IC Selection cap.
- A new completed **Screener Run** should replace the prior **Top Picks** and pending **Thesis Intake** selection.
- Prior **Top Picks Addition** and **Top Picks Removal** records should remain available as feedback/history after a new **Screener Run**, but should not automatically override the new run's default selection.
- Repeated **Top Picks Addition** or **Top Picks Removal** patterns may inform future learning-loop analysis or **Strategy Change Proposals**, but should not silently change Screener behavior.
- **Top Picks** selection state should persist within the **Live FundOps Server Session** until a new **Screener Run** replaces it.
- **Top Picks** selection state should survive browser refresh or navigation while the **Live FundOps Server Session** continues.
- **Top Picks** selection state should not persist as the active selection after the **Live FundOps Server Session** ends.
- Historical **Top Picks** selection state and manual selection changes should remain inspectable as run history after the **Live FundOps Server Session** ends.
- Removing a **Screener Candidate** from **Top Picks** should affect pending **Thesis Intake** only and should not delete or hide a completed Thesis artifact.
- Completed Thesis artifacts should remain available through Thesis, **Company Page**, and **Library** even if the candidate is later removed from **Top Picks**.
- A **Pipeline Run** should use the **Screener Handoff Selection** to execute Thesis and downstream capabilities.
- If fewer than 20 companies satisfy the **Screening Requirements**, the **Screener Handoff** should pass only the surviving **Screener Candidates** to Thesis.
- The **Screener Handoff** should not fill unused Thesis capacity with near-misses or relaxed-rule candidates.
- If no companies satisfy the **Screening Requirements**, the Screener should report that zero candidates passed and should not run Thesis.
- The Screener should not propose relaxed **Screening Requirements** from the Screener page.
- The visible Screener results should include only **Screener Candidates**.
- The Screener page should show a lightweight **Screener Run Summary** with aggregate counts such as Screened Universe size, number of candidates that passed, and number shown in the **Screener Review Set**.
- **Screener Run Summary** should not expose failed-company rows, near-misses, or detailed **Screening Failure Reasons**.
- **Screener Run Summary** does not need to show **Constitution Version** in the active Screener page.
- **Screener Run Summary** should stay simple and should not duplicate universe, strategy wiring, or other information owned by Strategy Chat chips.
- A Screener run may retain **Screener Run Evidence** for companies that did not satisfy the **Screening Requirements**.
- **Screener Run Evidence** should not be presented as visible near-misses or alternatives to **Screener Candidates**.
- **Screener Run Evidence** should record the **Constitution Version** used by the run.
- **Screener Run Evidence** should record the **Screened Universe** used by the run.
- A completed Screener run should create **Screener Snapshots** for **Screener Candidates**.
- A **Screener Snapshot** should preserve the candidate's values, **Screener Ranking**, **Top Picks** selection state, **Screening Pass Evidence**, **Screener Ranking Components**, and **Screener Ranking Source Explanation** from that run.
- A **Screener Snapshot** should be immutable after the run completes; newer data or a newer **Constitution Version** should create a newer snapshot rather than rewriting the old one.
- Manual **Top Picks Addition** and **Top Picks Removal** events should be stored as selection events attached to the relevant Screener run rather than mutating the original **Screener Snapshot**.
- **Screener Run Evidence** should preserve **Screening Failure Reasons** for companies that did not satisfy the **Screening Requirements**.
- **Screening Failure Reasons** should include every failed **Screening Requirement** for a company, not only the first failure.
- Each **Screening Failure Reason** should preserve the required threshold and the observed company value.
- **Screener Run Evidence** should preserve **Screening Pass Evidence** for **Screener Candidates**.
- Each **Screening Pass Evidence** item should preserve the required threshold and the observed company value.
- A **Screener Candidate Detail** should show **Screening Pass Evidence** for that visible candidate.
- A **Screener Candidate Detail** should show a **Screener Ranking Explanation** for that visible candidate.
- A **Screener Candidate Detail** should distinguish **Screening Pass Evidence** from **Screener Ranking Explanation**.
- A **Screener Candidate Detail** may present **Screening Pass Evidence** as compact metric evidence while the retained evidence still preserves the required threshold and observed company value.
- A metric may serve as both **Screening Pass Evidence** and a **Screener Ranking Component** for the same **Screener Candidate**.
- **Screener Candidate Detail** should not duplicate the same metric solely because it serves both as **Screening Pass Evidence** and as a **Screener Ranking Component**.
- **Screener Key Financials** should show the financial metrics that the active Screener wiring uses as **Screening Requirements**.
- If the active Screener wiring screens for ROIC and gross margin, **Screener Key Financials** should show ROIC and gross margin for each **Screener Candidate**.
- Changing the **Screener Key Financials** metric set should come from an approved Screener configuration change, not from a local display-only preference.
- When more wired financial **Screening Requirements** exist than fit in **Screener Key Financials**, the displayed metrics should follow the priority order of the approved **Screener Ranking Blend**.
- If multiple wired financial **Screening Requirements** have equal **Screener Ranking Blend** priority, **Screener Key Financials** should use the approved Strategy Criterion order as the tie-breaker.
- If the approved strategy does not provide an order, **Screener Key Financials** should use a stable canonical financial metric order as the final tie-breaker.
- **Screener Key Financials** should show observed candidate values only, not threshold comparisons.
- Threshold-versus-observed **Screening Pass Evidence** belongs on the **Company Page**, not in **Screener Key Financials**.
- A **Screener Candidate Detail** should remain concise and focused rather than presenting every retained evidence point for a company.
- **Screener Key Financials** should stay a concise quick-view metric strip rather than expanding into the full **Screener Ranking Blend**, exhaustive **Screening Pass Evidence**, or **Capability Wiring Panel** content.
- **Screener Key Financials** should use the same selected metrics in the same order across **Screener Candidates** from the same run so users can compare candidates directly.
- **Screener Key Financials** should use the same selected metrics in the same order across Screener runs until the approved Screener configuration changes.
- **Screener Key Financials** should not be reselected from the composition of each run's surviving candidates.
- **Screener Key Financials** should preserve the metric slot when a candidate has missing data rather than substituting a different metric for that candidate.
- A **Screener Ranking Explanation** explains why a candidate ranked where it did among surviving candidates, not why the Screening Requirements exist.
- A **Screener Ranking Explanation** should be derived from the **Screener Ranking Source Explanation** and grounded in saved **Screener Ranking Components**.
- The **Screener Ranking Source Explanation** and **Screener Ranking Components** are the source material for concise quick-view ranking prose.
- The exact concise **Screener Ranking Explanation** text shown in **Screener Candidate Detail** does not need to be preserved separately when the **Screener Ranking Source Explanation** is retained.
- **Screener Ranking Source Explanation** and **Screener Ranking Explanation** should follow the **Screener Explanation Format**.
- A fuller **Screener Ranking Source Explanation** may be longer than the quick-view explanation but should remain grounded, consistent, and constrained by **Screener Ranking Components**.
- **Screener Explanation Format** should include rank context, main positive ranking drivers, any material offset, and why the candidate belongs in **Top Picks** or **Remaining Candidates**.
- **Screener Explanation Format** may use internal slots to enforce consistency, but the rendered explanation should be prose rather than bullets.
- **Screener Explanation Format** should explain the candidate's original run placement rather than regenerating after manual **Top Picks** changes.
- **Screener Explanation Format** should phrase placement historically, such as initial **Top Picks** or initial **Remaining Candidates**, so the explanation remains true after manual selection changes.
- Manual **Top Picks Addition** and **Top Picks Removal** events should remain separate from **Screener Ranking Source Explanation**.
- **Screener Ranking Source Explanation** should include original placement context.
- Concise **Screener Ranking Explanation** in **Screener Candidate Detail** may omit original placement context when space is tight.
- **Screener Candidate Detail** does not need a separate initial-placement marker because current **Top Picks** or **Remaining Candidates** section membership communicates current selection.
- A **Screener Ranking Component** should come from a fact that directly contributed to the approved **Screener Ranking Blend**.
- A **Screener Ranking Explanation** may mention a candidate's strongest weighted metrics, weakest weighted metrics when relevant, composite rank position, and expected return contribution only when those facts are part of the approved **Screener Ranking Blend**.
- A **Screener Ranking Explanation** should not mention unrelated favorable facts merely because they are available.
- A **Screener Ranking Explanation** may mention a material weakness or offset only when it fits the quick-view word budget and the weakness affected the approved **Screener Ranking Blend**.
- A **Screener Ranking Explanation** in **Screener Candidate Detail** should prioritize the highest-impact **Screener Ranking Components** rather than trying to mention every component.
- A **Screener Ranking Explanation** may omit lower-impact **Screener Ranking Components** when space is tight.
- A **Screener Ranking Explanation** may include exact observed values when those values materially explain the candidate's rank and fit the quick-view surface.
- A **Screener Ranking Explanation** should use consistent concise prose rather than bullets or variable free-form structures.
- A **Screener Ranking Explanation** in **Screener Candidate Detail** should be fit-bounded for the quick-view surface, with the exact word budget calibrated to the available UI space.
- **Screener Ranking Explanation** generation should target the quick-view fit budget, and the user interface should defensively prevent overflow from breaking **Screener Candidate Detail**.
- **Screener Candidate Detail** should default to two quick-view sections: **Screener Ranking Explanation** and **Screener Key Financials**.
- **Screener Candidate Detail** should not include return breakdown as a default section because Screener is not the owner of valuation or return-thesis analysis.
- Removing return breakdown from **Screener Candidate Detail** should give the remaining quick-view sections more space rather than adding another unrelated section.
- **Screener Candidate Detail** should not include a Run Thesis action.
- Thesis execution should happen in the Thesis capability UI or through **Pipeline Run**, not from the Screener page.
- **Screener Result Table** should not show expected return as a default column because Screener is not the owner of valuation or return-thesis analysis.
- **Screener Result Table** should not show an abstract ranking score as a default column.
- The visible row order in **Screener Result Table** is the user-facing expression of **Screener Ranking**.
- **Screener Result Table** does not need a separate rank column because row order already communicates rank.
- **Screener Result Table** should default to company-identifying columns such as ticker, company name, sector, and current price.
- **Screener Result Table** should use sector as the compact default classification field and does not need industry as a default column.
- Detailed metrics belong in **Screener Candidate Detail** rather than crowding the default **Screener Result Table**.
- **Screener Review Actions** should be available directly from **Screener Result Table** rows.
- **Screener Review Actions** should apply only to visible **Screener Candidates**, not to companies that failed the **Screening Requirements**.
- A **Screener Promotion** should add the selected **Screener Candidate** to the **Screener Handoff Selection** and record the promotion as feedback.
- A **Screener Dismissal** should remove the selected **Screener Candidate** from the **Screener Handoff Selection** for the current run while keeping it in the **Screener Review Set**.
- A manual **Screener Promotion** should expand the **Screener Handoff Selection** rather than silently displacing another selected candidate.
- Reducing the number of **Top Picks** should be treated as a **Workflow Stage Selection Count** change rather than the default meaning of a row-level **Screener Dismissal**.
- A **Screener Dismissal** from the default **Screener Handoff Selection** should let **Screener Ranking** reflow so lower-ranked candidates move up into **Screener Handoff Selection** when enough eligible candidates remain.
- **Screener Review Actions** should not change **Screening Requirements**, **Screener Ranking Blend**, or the original **Screener Ranking**.
- The Screener page should visually distinguish the current **Screener Handoff Selection** from other **Screener Candidates** in the **Screener Review Set**.
- The Screener page may label the current **Screener Handoff Selection** as **Top Picks**.
- The Screener page should show lightweight counts for **Top Picks** and **Remaining Candidates**.
- The Screener page should not emphasize whether a **Top Picks** member was manually added; manual-selection provenance belongs in historical surfaces such as **Company Page**.
- A manually promoted **Screener Candidate** should appear in **Top Picks** even if its original **Screener Ranking** was outside the default handoff count.
- **Top Picks** membership should represent the current **Screener Handoff Selection**, not only the original top-ranked candidates.
- **Top Picks** should preserve the default selected candidates in original **Screener Ranking** order.
- Manually promoted **Screener Candidates** should be appended to the end of **Top Picks** rather than inserted by original **Screener Ranking**.
- A removed **Screener Candidate** that is manually promoted again should be appended to the current end of **Top Picks**.
- **Top Picks Selection Order** should be stored separately from original **Screener Ranking**.
- Original **Screener Ranking** should remain available after manual **Top Picks** changes.
- The non-selected portion of the **Screener Review Set** should preserve original **Screener Ranking** order while excluding current **Top Picks** members.
- A **Screener Candidate** removed from **Top Picks** should appear in **Remaining Candidates** rather than disappearing or moving to a failed-candidate section.
- A **Screener Candidate** removed from **Top Picks** should not carry a visible stigma or dismissal marker in **Remaining Candidates**.
- Removing a **Screener Candidate** from **Top Picks** should create a **Top Picks Removal** record for learning-loop analysis.
- A **Top Picks Removal** should be treated as neutral deselection feedback, not as a rejection of the company or a **Screening Failure Reason**.
- Manually adding a **Screener Candidate** to **Top Picks** should create a **Top Picks Addition** record for learning-loop analysis.
- A **Top Picks Addition** should be treated as selection feedback, not as Thesis execution, investment approval, or a change to **Screener Ranking**.
- A **Top Picks Addition** should not regenerate **Screener Ranking Explanation**, **Screener Key Financials**, or other **Screener Candidate Detail** content for the selected candidate.
- **Screener Candidate Detail** content should persist from the Screener run that produced it unless a newer **Screener Run** replaces it.
- The Screener page should label non-selected surviving **Screener Candidates** as **Remaining Candidates**, not as below-threshold stocks.
- **Screening Failure Reasons** support evals, debugging, later explainability, and learning-loop analysis without changing visible Screener results.
- **Strategy Chat** can propose Constitution changes at any time as the user's strategy evolves.
- **Strategy Chat** uses a **Strategy Readiness Check** rather than a fixed number of back-and-forth turns.
- If the user's answers are detailed, **Strategy Chat** can produce a **Strategy Draft** quickly.
- If the user's answers are vague, **Strategy Chat** should ask more questions before producing a **Strategy Draft**.
- A **Strategy Draft** is not active and does not change workflow settings.
- A **Strategy Draft** must include a **Strategy Draft Summary** and **Strategy Draft Rules** before asking for approval.
- A **Strategy Draft Summary** explains the strategy in investor-friendly prose.
- **Strategy Draft Rules** show the exact criteria FundOps will use if the draft is approved.
- A **Strategy Draft** must include a **Strategy Draft Wiring Preview** before asking for approval.
- A **Strategy Draft** should follow the **Strategy Draft Format**.
- The **Strategy Draft Format** includes plain-English strategy, style blend, rules FundOps will wire, workflow wiring preview, saved preferences not wired yet, tradeoffs, and approval language.
- Small post-setup edits should use the **Strategy Change Format** instead of the full **Strategy Draft Format**.
- The **Strategy Change Format** includes proposed change, exact diff, affected workflow, tradeoff, and approval language.
- A **Strategy Draft Wiring Preview** shows specific projected settings, thresholds, and workflow effects so the user can request targeted changes before approval.
- A **Strategy Draft Wiring Preview** can duplicate some agent-chip information because it is part of the approval contract, not the persistent metadata panel.
- First-time Strategy Chat setup should show a full **Strategy Draft Wiring Preview** across the major workflow capabilities.
- Later Strategy Chat edits should show a focused **Constitution Diff** and the affected wiring, and explicitly say when no other workflow settings will change.
- Post-setup Strategy Chat changes require a focused preview and **Strategy Approval Prompt** before wiring, even when the requested change is simple.
- A **Strategy Draft** must end with a **Strategy Approval Prompt** before it can be accepted.
- A **Strategy Approval Prompt** must state that approval creates a new **Constitution Version** and wires the listed settings.
- For later edits, a **Strategy Approval Prompt** must state which settings will change and whether any other workflow settings remain unchanged.
- A **Strategy Draft** should ask the user for approval before becoming a **Strategy Change Proposal** that can be activated.
- Strategy Chat should perform a **Strategy Proposal Evidence Check** before showing a **Strategy Draft** when the proposed strategy depends on market reality, universe membership, or data availability.
- Strategy Chat may draft first and validate afterward when the user's desired criteria are already within known supported strategy vocabulary.
- A **Strategy Proposal Evidence Check** should produce or reuse **Canonical Evidence Records** and **Execution Provenance Records** rather than relying on hidden chat-time research.
- Strategy Chat should consume retained evidence through the Python workflow layer when explaining data support, universe checks, or wiring limits.
- A **Strategy Proposal Envelope** should keep proposal lifecycle, validation, evidence, rationale, source, and approval state stable while allowing inner strategy content to vary by strategy style.
- A **Strategy Proposal Envelope** should not be treated as executable workflow settings.
- Natural approval language such as "yes", "ok", "approve", or "go ahead" accepts only the **Current Pending Draft**.
- If there is no **Current Pending Draft**, or if approval target is ambiguous, Strategy Chat must ask what the user wants to approve instead of guessing.
- Strategy Chat should preserve the **Live Strategy Chat Session** across tab/page changes while the local FundOps app is still running.
- A **Current Pending Draft** should remain available across tab/page changes during the **Live Strategy Chat Session**.
- After the local FundOps app is stopped and started again, Strategy Chat should begin as a new chat while using **Strategy Continuation Memory** for prior context.
- **Strategy Continuation Memory** should let the user continue generally from prior strategy context without treating the restarted app as the same live chat.
- Natural approval language should not activate an old pending draft after the local FundOps app has been stopped and started again.
- After restart, Strategy Chat may recall a prior pending draft, but must show it again before asking for approval.
- If the user rejects a **Current Pending Draft**, Strategy Chat must not save or wire that draft.
- If the user's correction is vague, Strategy Chat should ask what part of the draft is wrong.
- If the user's correction is specific, Strategy Chat should create a **Draft Revision** and ask for approval again.
- If the user requests **Draft Cancellation**, Strategy Chat must discard the **Current Pending Draft** and confirm that nothing was saved or wired.
- After **Draft Cancellation**, natural approval language must not activate the canceled draft.
- Strategy Chat should not partially activate a **Current Pending Draft**.
- If the user approves only part of a draft or rejects one section, Strategy Chat should create a **Draft Revision** for the full final draft before asking for approval again.
- After approval and wiring, Strategy Chat should show a **Strategy Activation Confirmation** instead of repeating the full draft.
- A **Strategy Activation Confirmation** should identify the new **Constitution Version** and briefly state what changed.
- When the user is contemplating an idea rather than requesting a change, Strategy Chat is in **Strategy Exploration**.
- When the user asks about current strategy or settings, Strategy Chat should provide a **Strategy Status Answer** without creating a draft.
- A **Strategy Status Answer** should not enter the approval flow unless the user asks to change something.
- In **Strategy Exploration**, Strategy Chat should provide a **Strategy Tradeoff Explanation** before offering to draft a change.
- A **Strategy Tradeoff Explanation** should make clear that adding criteria can narrow the opportunity pool or introduce false signals.
- Strategy Chat should not create a **Strategy Draft** from contemplation language unless the user asks to turn the idea into a change.
- Meaningful Strategy Criteria changes should include a brief **Strategy Tradeoff Explanation** before the **Strategy Approval Prompt**.
- If a requested criteria combination is wireable but likely very narrow or market-dependent, Strategy Chat should provide a **Restrictiveness Warning** rather than blocking it.
- A **Restrictiveness Warning** should explain the tradeoff and allow the user to proceed if they still want the criteria.
- Approved strict or rare criteria should become a normal **Constitution**, not an experimental Constitution label.
- Strategy Chat should not label a user's approved strategy as experimental merely because it is restrictive.
- When the user gives specific criteria, Strategy Chat should preserve the exact criteria and also capture **Inferred Strategy Intent**.
- **Inferred Strategy Intent** supports later explanation, recall, and learning-loop behavior without overriding the user's explicit rules.
- Strategy Chat should capture a **Strategy North Star** from the user's exact criteria, rationale, and preferences so downstream capabilities can evaluate strategic alignment.
- A **Strategy North Star** should help downstream capabilities understand what the criteria are trying to identify, such as high-quality moat businesses, without replacing exact **Strategy Criteria**.
- When exact criteria and plain-English strategy label conflict, Strategy Chat should flag a **Strategy Intent Mismatch** before approval.
- In a **Strategy Intent Mismatch**, the specific criteria usually reveal the user's real intended behavior, but Strategy Chat should ask whether to change the rules or update the plain-English description.
- **Strategy Self-Discovery** is expected, especially for novice users.
- Strategy Chat should treat the user's initial strategy label as a starting hypothesis, not a binding contract.
- When the conversation moves away from the initial label, Strategy Chat should help the user notice the evolution without treating it as a mistake.
- The final **Strategy Draft** should reflect the user's clarified current strategy rather than narrating how far they moved from the initial label.
- Strategy Chat should not hold the user to their original label once more specific preferences reveal what they actually want.
- Activating a **Strategy Change Proposal** creates a new **Constitution Version** instead of mutating the prior version in place.
- A **Strategy Change Proposal** requires **Strategy Proposal Acceptance** before activation.
- **Strategy Proposal Acceptance** can happen through explicit chat confirmation or a dedicated review surface, but should not rely on a vague generic apply button.
- A **Strategy Change Proposal** must pass **Strategy Proposal Guardrails** before it can become active.
- **Strategy Proposal Guardrails** validate supported criterion ids, value types, ranges, required explanations, projection compatibility, and prose-to-structure consistency.
- **Strategy Wiring** happens only after **Strategy Proposal Acceptance** and successful **Strategy Proposal Guardrails**.
- Strategy Chat should not offer to wire settings outside the **Wiring Capability Boundary**.
- If a desired strategy idea is outside the **Wiring Capability Boundary**, Strategy Chat should explain that before approval rather than promising activation.
- **Settings Projections** should be inspectable as per-capability behavior, but changes to them should route through a **Strategy Draft** or **Strategy Change Proposal** rather than direct editing.
- UI surfaces should present **Settings Projections** as what each workflow capability will do, not as independently editable controls.
- A user request to change a **Settings Projection** should open Strategy Chat or a proposal review flow.
- A **Strategy Draft** should separate wireable rules from unsupported or not-yet-wireable ideas.
- Unsupported or not-yet-wireable ideas should remain visible in the approval draft as preserved preferences, not executable rules.
- If wiring still fails after approval, Strategy Chat must not show silent failure or fake success.
- Wiring failure behavior is a UX requirement; exact backend transaction and recovery design belong in the wiring/backend implementation design.
- Before **Strategy Proposal Acceptance**, Strategy Chat must not create a new active Constitution Version or apply workflow settings.
- Every active **Strategy Criterion** should have a **Rule Rationale** and **Rule Source**.
- Every projected workflow setting created by **Strategy Wiring** should have a **Rule Rationale** and **Rule Source**.
- Every **Constitution Version** should have a **Version Rationale**.
- **Version Rationale** explains the overall accepted change, while **Rule Rationale** explains individual criteria and projected settings.
- A **Strategy Criterion** or projected workflow setting should not be activated without a saved **Rule Rationale** and **Rule Source**.
- **Rule Rationale** and **Rule Source** support later explainability, learning-loop analysis, and user recall behavior.
- **Strategy Status Answers** about why a rule exists should use saved **Rule Rationale** and **Rule Source** before falling back to general explanation.
- **Conversation Evidence** should be retained for audit and source lookup, but should not be the primary memory used for normal Strategy Chat behavior.
- **Structured Strategy Memory** should be the primary recall source for normal Strategy Chat behavior.
- Raw **Conversation Evidence** should be consulted only when the user asks for history, when a source needs verification, or when structured memory is insufficient.
- A user-desired criterion without enough available data becomes an **Unsupported Criterion** stored in **Strategy Preference Memory**, not in the active executable Constitution.
- FundOps can offer **Proxy Criteria** for an **Unsupported Criterion**, but must explain the proxy's limits.
- A **Proxy Criterion** becomes executable only after the user understands and accepts the proxy.
- Every Strategy Criterion should have a **Data Support Level** based on current data sources such as Yahoo Finance, SEC data, and optional FMP data.
- Valid **Data Support Levels** are fully supported, partially supported, proxy available, research review, and unsupported.
- **Data Support Level** is primarily for proposal validation and chip-level explanations, not for the Strategy Metadata Panel.
- If a user states a vague preference such as "good management," Strategy Chat should ask what observable signals matter before wiring it.
- When Strategy Chat asks about a vague trait, suggested examples should be **Observable Signals** that FundOps can actually inspect.
- Strategy Chat should not offer unsupported examples as if they can become automatic screen rules.
- The active Constitution should emphasize executable Strategy Criteria and should not continuously display every unsupported preference.
- A **Constitution Version** must be inspectable as a full snapshot.
- Users must be able to compare two Constitution Versions through a **Constitution Diff**.
- Workflow outputs record the **Constitution Version** that produced them.
- **Learning Recommendations** can suggest **Strategy Change Proposals**, but should not activate them without **Learning Recommendation Acceptance** on the **Dashboard**.
- Default **Learning Evaluation Windows** are 3 months, 6 months, 12 months, 24 months, and 36 months.
- An **Outcome Evaluation** should combine price outcome, benchmark-relative outcome, thesis-health state, and goal-alignment evidence rather than treating market return alone as the learning result.
- An **Outcome Evaluation** should use **Outcome Horizon Context** from the relevant **Constitution Version**, Completed Memo, or thesis evidence when available.
- The default **Outcome Evaluation Result** set is thesis worked, right thesis slow market, lucky result, thesis failed, and **No Clear Learning Signal**.
- **No Clear Learning Signal Reasons** should stay high-level, such as broad market or sector move, insufficient time elapsed, insufficient filing evidence, conflicting evidence, outcome unrelated to original thesis, or data quality gap.
- A **No Clear Learning Signal** result and its **No Clear Learning Signal Reason** should be retained as a **Learning/Evals Record** so later evidence can supersede the no-signal interpretation rather than starting from scratch.
- **Learning Recommendations** should require a **Learning Evidence Pattern** rather than a single **Outcome Evaluation**.
- **Learning Evidence Patterns** should satisfy **Learning Pattern Sufficiency** before they support a **Learning Recommendation**.
- A **Learning Evidence Pattern** should compare initial **Screener Run Evidence** or **Screener Snapshot** financial metrics with later **Outcome Evaluation Results**, **Memo-Backed Thesis Health**, **Outcome Driver Evidence**, and relevant **Learning Feedback Signals**.
- A **Learning Association** may be surfaced as exploratory evidence before FundOps has a full thesis-grounded explanation.
- Learning/Evals should search all retained initial financial metrics for **Learning Evidence Patterns**, not only the metrics already named by the active **Constitution**.
- Learning/Evals should look for metric trends as well as point-in-time metric levels when discovering **Discovered Strategy Signals**.
- A **Discovered Strategy Signal** may reveal that a trend, such as improving cash conversion cycle, better explains strategy fit or thesis durability than the explicit criteria originally named by the user.
- A **Discovered Strategy Signal** may become evidence for a **Learning Recommendation**, but should not become an active **Strategy Criterion** without user review and **Learning Recommendation Acceptance**.
- **Learning Pattern Sufficiency** should consider sample size, comparability of companies, directional consistency, evidence quality, filing-first support, thesis-health connection, outcome-driver explanation, and whether enough time has passed for the strategy's intended return path.
- **Learning Pattern Sufficiency** should combine **Learning Pattern Data Support** and **Learning Pattern Interpretation** rather than relying only on deterministic checks or only on AI judgment.
- Learning/Evals should use **Learning Confidence Labels** rather than numeric confidence as the primary user-facing confidence expression.
- A **Learning Evidence Pattern** should state its **Learning Cohort Context** before becoming recommendation-ready.
- Learning/Evals may discover broad cross-company patterns, but should not present a pattern as globally applicable unless its **Learning Cohort Context** supports that breadth.
- A **Learning Recommendation Evidence Card** should distinguish deterministic **Learning Pattern Data Support** from AI-assisted **Learning Pattern Interpretation**.
- **Learning Version Scope** should affect confidence: same **Constitution Version** evidence is strongest, materially related **Constitution Versions** can support a pattern with caveats, and unrelated older versions should be exploratory.
- A **Recommendation-Ready Signal** should require **Learning Pattern Sufficiency**, a link to **Memo-Backed Thesis Health** or **Outcome Driver Evidence**, and a plain-English investment rationale.
- Hard **Strategy Criteria** changes should usually require a **Thesis-Grounded Learning Recommendation**, not a bare **Learning Association**.
- A **Learning Association** may support research prompts, ranking emphasis, IC emphasis, or keep-watching behavior with caveats before it becomes thesis-grounded enough for a hard strategy rule.
- An unexplained but strong **Learning Association** may guide attention, research questions, ranking emphasis, IC emphasis, or keep-watching behavior, but should not become a hard **Strategy Criterion** by default.
- FundOps should make the black-box nature of an unexplained **Learning Association** visible when the user reviews it.
- A user may explicitly accept a wireable **Learning Association** as an **Empirical Strategy Signal** even when it is not thesis-grounded.
- An **Empirical Strategy Signal** should preserve an empirical or associational rationale rather than inventing a thesis-grounded explanation.
- When a **Learning Evidence Pattern** contradicts the active **Constitution**, FundOps should frame it as **Strategy Self-Discovery** rather than declaring the user or strategy wrong.
- A contradiction-focused **Learning Recommendation Evidence Card** should offer reviewable choices such as refine the rule, treat the signal as a **Research Review Criterion**, keep the current discipline, or keep watching.
- Accepted **Learning Recommendations** that change executable strategy behavior should create a new **Constitution Version**.
- Accepted **Learning Recommendations** that keep watching a signal or add review-only questions may remain **Structured Strategy Memory**, workflow configuration, or review criteria until promoted into executable strategy behavior.
- **Learning Recommendations** should not auto-accept or silently graduate into behavior changes, even after repeated prior approvals.
- FundOps may make repeated high-confidence **Learning Recommendations** easier to review, but **Learning Recommendation Acceptance** should remain explicit.
- A **Learning Recommendation Response** should become a **Learning Feedback Signal** when it reveals acceptance, dismissal, optional rejection rationale, or preference for more evidence.
- Accepting a **Learning Recommendation** should apply the approved change through the appropriate behavior path and create a new **Constitution Version** when executable strategy behavior changes.
- Dismissing a **Learning Recommendation** means the user does not want to take the recommendation; FundOps may retain an optional rationale when the user provides one.
- Keeping watch on a **Learning Recommendation** should preserve the pattern without changing behavior and should require additional evidence before resurfacing.
- **Learning Recommendation Resurfacing** should happen only when materially new evidence appears, such as another comparable company joining the pattern, a later **Learning Evaluation Window** changing the pattern, new filing-first evidence changing interpretation, a held position becoming affected, or a material confidence or caveat change.
- FundOps should not require a separate user-learning quiz or training loop; **Learning Recommendation Responses** and later investment workflow behavior are the user-visible learning interface.
- A weaker **Discovered Strategy Signal** may be surfaced as exploratory Learning/Evals evidence, but should not be presented as a **Learning Recommendation**.
- A **Learning Recommendation** should stay inside **Learning Recommendation Scope** and should not create portfolio buy, sell, trim, or add instructions.
- If a **Discovered Strategy Signal** is useful but not deterministic enough for screening, the **Learning Recommendation** may propose a **Research Review Criterion** before proposing a hard **Strategy Criterion**.
- **Learning/Evals Product Boundary** should prioritize retained evidence and reviewable learning before behavior mutation: create **Outcome Evaluations**, create filing-first **AI-Assisted Thesis Health Findings**, persist **Outcome Driver Evidence**, run **Idle Learning Analysis** across all retained initial metrics, produce **Learning Recommendation Evidence Cards**, and capture explicit **Learning Recommendation Responses**.
- **Learning Recommendation Escalation** should default to the least aggressive useful change: use a **Research Review Criterion** or Thesis/Memo question for contextual signals, ranking or IC emphasis for useful but non-exclusive signals, **Thesis Watch Items** for thesis-durability signals, and hard **Strategy Criteria** only when the signal is deterministic, broadly available, and repeatedly necessary.
- A **Learning Recommendation** should be shown as a **Learning Recommendation Evidence Card** rather than a bare suggestion.
- A **Learning Recommendation Evidence Card** should include the proposed change, rationale, supporting companies, initial metrics at screening time, relevant **Learning Evaluation Windows**, **Memo-Backed Thesis Health**, **Outcome Driver Evidence**, confidence, caveats, and accept, reject, or keep-watching actions.
- A **Learning Recommendation Evidence Card** should include a **Learning Teaching Note** that briefly explains what the pattern may mean for the user's investing judgment.
- A **Learning Teaching Note** should be evidence-linked and humble rather than generic education or an overconfident lesson.
- The primary **Learning/Evals Review Surface** should be the **Dashboard** for evidence cards that need decisions or attention.
- **Company Page** should show ticker-specific **Outcome Evaluations**, **AI-Assisted Thesis Health Findings**, and learning-relevant history as drilldown evidence.
- **FundOps Chat** may explain Learning/Evals evidence and answer questions about it, but should not be the primary approval surface for **Learning Recommendation Acceptance**.
- **Settings/Config** should control cadence, provider, and operational settings for Learning/Evals, not serve as the learning review surface.
- Learning/Evals should not be framed as an always-visible standalone analytics page by default; a dedicated Learning view is appropriate when enough **Learning/Evals Records** exist to summarize patterns, accepted recommendations, superseded conclusions, and strategy evolution.
- Learning/Evals source of truth should be append-only **Learning/Evals Records** rather than live recomputation from latest state.
- **Outcome Evaluations**, **Outcome Driver Evidence**, **AI-Assisted Thesis Health Findings**, **Learning Evidence Patterns**, **Learning Recommendation Evidence Cards**, and **Learning Recommendation Responses** should be retained as **Learning/Evals Records**.
- Each **Learning/Evals Record** should preserve **Learning Evidence Lineage** back to relevant source records such as **Screener Snapshots**, **Constitution Versions**, **Thesis Watch Items**, filings, **Learning Evaluation Windows**, AI findings, and user responses.
- Each company datapoint used by Learning/Evals should retain its **Learning Idea Source**.
- FundOps-surfaced ideas are strongest for judging Screener, Thesis, and IC behavior; user-added or manually researched ideas are useful for investor preference and judgment learning; portfolio-held ideas are important for thesis health and investor judgment regardless of original source.
- **Near-Miss Learning** may use retained Screener or selection evidence for companies that did not advance through the full pipeline, but should carry lower confidence when no Completed Memo, Thesis Watch Items, or memo-backed thesis-health evidence exists.
- **Near-Miss Learning** is primarily **Pipeline Learning** because it can reveal missed selection, ranking, or handoff behavior.
- **Learning-Eligible Misses** may include retained top Screener results, user-dismissed candidates, IC fails, user-added watch items, or other retained candidates with meaningful source context.
- Learning/Evals should not actively track the entire **Screened Universe** for near-miss learning.
- Learning/Evals may use **Learning Comparison Groups** to compare accepted ideas against retained rejected, missed, held, or non-held ideas when enough comparable evidence exists.
- **Learning Comparison Groups** should caveat lower confidence when rejected or missed ideas have thinner research coverage than accepted memo-backed ideas.
- Learning/Evals should distinguish **Pipeline Learning**, **Strategy Learning**, and **Investor Learning** rather than treating every outcome as a strategy verdict.
- A **Learning Recommendation Evidence Card** should make clear whether it is primarily about pipeline behavior, strategy calibration, investor judgment, or a combination.
- Accepted **Learning Recommendations** should later receive **Learning Recommendation Outcomes** when enough evidence accumulates.
- A negative or inconclusive **Learning Recommendation Outcome** should create superseding learning evidence rather than silently preserving the accepted recommendation as correct.
- Later evidence should create **Learning Record Supersession** rather than overwriting earlier **Learning/Evals Records**.
- A **Current Learning View** may summarize the latest interpretation, but append-only **Learning/Evals Records** and their **Learning Evidence Lineage** remain the source of truth.
- The **Learning/Evals Review Surface** should show the **Current Learning View** by default while making superseded interpretations and evidence history available through drilldown.
- **Idle Learning Analysis** should run only when higher-priority user-facing workflow jobs and **Data Provider Request Queue** work are not queued or running.
- **Idle Learning Analysis** should pause, defer, or skip work when an **Interactive Workflow Run** or other higher-priority workflow enters the queue.
- **Idle Learning Analysis** should first scan retained FundOps evidence, then use **AI-Assisted Pattern Analysis** and external **Outcome Driver Evidence** enrichment only for promising patterns while idle capacity remains available.
- **AI-Assisted Pattern Analysis** may propose **Learning Evidence Patterns**, but **Learning Recommendations** still require source-backed evidence, an evidence card, and **Learning Recommendation Acceptance** before behavior changes.
- A **Constitution** can include narrative philosophy, but deterministic workflow behavior depends on **Strategy Criteria**.
- **Strategy Criteria** must be shown before activation, with an **Interpretation Layer** explaining what each criterion means and implies.
- The **Interpretation Layer** explains what each criterion means, why it matters, and how it changes FundOps behavior.
- A **Strategy Criterion** includes criterion id, machine rule, plain-English meaning, rationale, workflow implication, confidence, source, and status.
- A **Strategy Change Explanation** presents structured criteria and diffs as readable prose, not as a raw list.
- A **Strategy Change Explanation** includes a human summary, exact machine criteria, and downstream workflow impact.
- Before the user has a Constitution, Strategy Chat shows onboarding guidance in the centered card.
- After the user has a Constitution, the centered card becomes the **Strategy Metadata Panel**.
- The **Strategy Metadata Panel** summarizes the active Constitution without duplicating the agent-chip detail sections.
- The **Strategy Metadata Panel** should not repeat the North Star primary goal.
- The **Strategy Metadata Panel** can show style blend as a breakdown of the North Star.
- Detailed workflow wiring and research-review details belong behind the agent chips, not in the **Strategy Metadata Panel**.
- The **Strategy Metadata Panel** should not include a data-support summary.
- The **Strategy Metadata Panel** should not include executable criteria counts, criteria groups, or other function wiring information.
- The **Strategy Metadata Panel** is limited to strategy identity and change metadata such as Constitution Version, Style Blend, Last Changed, and Pending Proposals.
- Agent/function chips are the authoritative UI for inspecting how the Constitution wires into each workflow capability.
- Agent/function chips should show **Capability Wiring Summaries** as durable read-only summaries of each capability's active Settings Projection.
- A **Capability Wiring Panel** is the authoritative UI for detailed per-capability wiring such as the **Screener Ranking Blend**.
- **Capability Wiring Summaries** should be derived from the active Constitution Version and Settings Projection, not hand-edited UI text.
- **Capability Wiring Summaries** should be generated when a Constitution Version activates or its Settings Projection changes, then stored as durable projection text with source version provenance.
- The Screener page should not duplicate detailed **Capability Wiring Panel** content.
- The Screener page should not add a separate wiring trace, wiring summary, or wiring link for settings already owned by the Strategy Chat **Capability Wiring Panel**.
- A **Constitution** can combine Strategy Criteria from multiple **Strategy Lenses**.
- A **Strategy Lens** is a starting vocabulary for discussion, not a fixed schema that defines the user's whole strategy.
- A **Starter Template** can seed Strategy Criteria, but user-specific criteria override template defaults.
- Saying "value investor" or "momentum investor" does not automatically activate every criterion in that lens without confirmation.
- When the user uses broad language such as "good companies," Strategy Chat should ask one **Clarifying Prompt** before proposing defaults.
- A **Clarifying Prompt** should invite the user to define the broad idea in their own words rather than forcing a checklist of metrics.
- For broad traits that may become criteria, a **Clarifying Prompt** should ask for the user's meaning and offer data-backed **Observable Signal** examples in the same message.
- After a **Clarifying Prompt**, Strategy Chat can propose explained defaults if the user wants guidance or remains vague.
- Narrative philosophy that cannot be mapped to **Strategy Criteria** creates a **Review Item**.
- **Screener**, Thesis, IC Review, Memo, and Portfolio Review behavior are configured from the **Constitution**.
- A **Settings Projection** is derived deterministically from the **Constitution**.
- A **Settings Projection** configures Screener, Thesis, IC Review, Memo, Portfolio Review, and Settings/Config behavior.
- **Settings/Config** owns operational controls, not direct strategy-derived workflow tuning.
- **Settings/Config** should be a low-traffic operational surface; normal investment work belongs in FundOps Chat, Dashboard, workflow capabilities, Portfolio, Portfolio Review, Library, and Company Page.
- A **Settings Visit** should usually happen for setup, verification, troubleshooting, maintenance, or data ownership rather than routine investment review.
- **Settings/Config** should organize controls by **Settings Job Groups** rather than raw implementation categories.
- Primary **Settings Job Groups** may include connecting services, checking reliability, controlling AI usage, managing automation, and owning data.
- **Settings Health Summary** should answer whether FundOps is operationally ready without duplicating Dashboard's attention and decision queues.
- **Settings Health Summary** may summarize service connectivity, AI readiness, schedule health, data ownership actions, and blocking setup issues.
- **Settings Health Summary** should link setup problems into **Settings/Config** and workflow-impacting problems to Dashboard or the affected product surface.
- **Settings Operational Explanations** should be used when they prevent operational mistakes, such as misunderstanding provider limits, model tradeoffs, token usage, schedule consequences, or destructive-action scope.
- **Settings Operational Explanations** should stay short and should not become product onboarding, investment workflow teaching, or long-form documentation.
- **Settings/Config** may expose **Settings Projection** for inspection, but should not become a separate source of truth for **Constitution**-owned behavior.
- **Settings/Config** should keep **Settings Projection** inspection compact, such as status rows or links, while detailed workflow wiring belongs in the **Capability Wiring Panel**.
- **Settings/Config** should include a **Financial Calculation Reference** for inspecting how important Supported Financial Metrics are calculated, sourced, versioned, and applied.
- **Financial Calculation Reference** should be read-only guidance by default rather than a calculation panel shown throughout the app.
- A user may ask the attached coding agent to propose calculation or definition changes, but accepted changes should still flow through governed Financial Data Robustness Improvement work and versioned metric or mapping records.
- Workflow behavior guidance should remain in Strategy UI function chips, **Capability Wiring Summaries**, and **Capability Wiring Panels** rather than being duplicated in **Settings/Config**.
- **Data Source Setup** belongs in **Settings/Config** and should cover provider configuration, provider status, provider capability tier, and manual test actions.
- Provider API keys and other secrets should live in the **Local Credential Store** rather than inside the **Local FundOps Workspace** or **Workspace Archive**.
- The **Local FundOps Workspace** may retain provider choices, connection status, capability tiers, non-secret configuration, and **Workspace Secret References** needed to retrieve credentials locally.
- **Web Research Capability Setup** belongs with connected service setup and should answer whether FundOps can search and read web sources for research workflows.
- **Web Research Capability Setup** should not become a separate research workflow, Library search surface, or archive question-answering surface.
- Provider failures or data gaps that block or degrade workflow output should appear as **Dashboard Attention Items** with a path back to **Data Source Setup** when configuration may fix the issue.
- **AI Model Setup** belongs in **Settings/Config** and may apply directly as an **Operational Settings Change** because model and provider selection are operational resources rather than strategy rules.
- **AI Model Setup** should make quality, latency, capability, and usage implications visible without treating model changes as **Constitution Versions**.
- **AI Usage Records** should be the reliable basis for AI usage reporting.
- **AI Usage Summary** should aggregate observed model names, input tokens, output tokens, call counts, workflow capability, and time period from **AI Usage Records**.
- **AI Usage Summary** is for visibility rather than workflow enforcement.
- **AI Usage Warnings** may alert users to high usage, but should not hard-stop workflow execution in the baseline product.
- **Estimated AI Cost** may be shown only as an approximation and should not be the canonical usage record unless exact provider billing data is available.
- Settings/Config should avoid presenting estimated AI spend as authoritative cost tracking.
- **Schedule Setup** belongs in **Settings/Config** and should cover direct schedule editing, pause, resume, manual mode, and schedule presets.
- **Schedule Presets** should provide the initial recurring workflow cadence, but users should be able to change individual schedules afterward.
- **Schedule Presets** are operational cadence defaults, not **Strategy Criteria** or behavior permissions.
- Dashboard may show schedule-derived status or exceptions, but recurring schedule tuning should remain in **Schedule Setup**.
- Missed runs, failed scheduled runs, stale outputs, or blocked scheduled work may become **Dashboard Attention Items** when the user needs to inspect or fix them.
- **FundOps Data Export** belongs in **Settings/Config** and should be framed as user data ownership, backup, or portability rather than workflow analysis.
- **FundOps Data Export** is distinct from **Artifact Export**: Settings owns bulk retained-data portability, while Library, Company Page, and the Workflow Artifact Reader own exporting individual completed artifacts.
- A **Workspace Archive** is the whole-workspace backup and restore form of **FundOps Data Export**, separate from polished **Retail Artifact PDFs** and internal artifact formats.
- A **Workspace Archive** should preserve enough workspace version metadata to support restore, app upgrade, and forward migration without treating individual artifact exports as backup packages.
- A **Workspace Archive** should not include provider API keys or other secrets by default; restored workspaces should reconnect through local credential setup.
- **Settings/Config** should not expose raw database paths, table lists, or storage internals as normal product content.
- Storage internals should remain implementation diagnostics rather than a user-facing Settings concept.
- **Settings/Config** should show current operational state and action confirmations rather than maintaining a dedicated user-facing operational change history.
- **Pipeline Data Clear** may live in **Settings/Config** as a destructive maintenance action when it has confirmation and clearly names what durable records are preserved.
- **Pipeline Data Clear** should be explicit and user-initiated rather than an automatic side effect of restarting a **Live FundOps Server Session**.
- A user-initiated **Operational Settings Change** may apply directly from **Settings/Config** with appropriate local confirmation when the action is sensitive or destructive.
- A **Constitution Reset** may live in **Settings/Config** as a destructive maintenance action when it has strong confirmation and clearly explains that strategy setup will restart.
- A **Constitution Reset** should not be presented as editing, versioning, refining, or tuning the current **Constitution**.
- **Destructive Settings Actions** should be few, visually separated from normal settings, require confirmation, and state what FundOps records are removed versus preserved.
- A requested strategy, universe, screener filter, IC hurdle, or portfolio-review behavior change that starts from **Settings/Config** should route through **Strategy Chat** or another explicit workflow-changing behavior before mutation.
- A FundOps-proposed or Learning/Evals-proposed behavior change should become a **Dashboard Decision Item** rather than applying through **Settings/Config**.
- User-facing navigation, schedules, and settings should label the Dashboard-owned review surface as **Portfolio Review**, not Allocator.
- Historical or legacy entry points for Allocator should lead users to **Portfolio Review** rather than preserving a separate user-facing Allocator surface.
- IC Review **Settings Projection** includes **IC Hurdles** so IC Gate behavior can be reviewed, versioned, and replayed from the **Constitution**.
- IC Review **Settings Projection** includes **IC Gate Score Blend** and **IC Pass Cutoff** so memo-worthiness strictness is reviewable and replayable from the **Constitution**.
- If the **Constitution** is ambiguous or incomplete, the projection creates a **Review Item** instead of inventing a setting.
- **Completed Memo** structure includes company-research depth and investment-oriented analysis by default.
- **Completed Memo** content and emphasis are tailored by the **Constitution**.
- A **Company Page** belongs to one resolved **Investment Entity** or **Security** and may be opened by current or historical **Ticker Symbols**.
- A **Company Page** can be opened from Screener, Research Queue, Thesis, IC Review, Memo, Portfolio, or Portfolio Review views.
- A **Company Page** can be reached from **Library** search or direct **Ticker Links** across the workflow.
- A **Company Page** does not create, mutate, or rerun workflow analysis.
- A **Company Page** shows the latest known state for a resolved Investment Entity or Security while preserving the historical path of prior workflow results.
- A **Company Page** is the appropriate user-facing place for detailed ticker-specific **Screening Pass Evidence** such as required threshold versus observed company value.
- A **Company Page** should preserve historical Screener results for a ticker, including how its values, **Screener Ranking**, and **Top Picks** selection state changed across runs.
- A **Company Page** should preserve history for **Screener Candidates** that were manually selected into **Top Picks** or the **Thesis Candidate List**.
- A **Company Page** should show the fuller **Screener Ranking Source Explanation** for historical Screener snapshots.
- If the same resolved Investment Entity or Security becomes a **Screener Candidate** in multiple Screener runs, the **Company Page** should show the latest Screener snapshot as the default state while preserving prior Screener snapshots in history.
- A **Company Page** may show a small historical indicator when a ticker was manually selected into **Top Picks**.
- A **Company Page** should reconstruct historical **Top Picks** state from the **Screener Snapshot** plus attached **Top Picks Addition** and **Top Picks Removal** events.
- A **Company Page** for a ticker that only has **Saved Screener Work** may surface that retained screening history because FundOps already generated work for the ticker, while detailed presentation belongs in the Company Page design spec.
- A **Company Page** defaults to the Workflow Map **Company Page Section**, with other top-level sections for Financials and Thesis Health.
- The first **Company Page Section** should be labeled Workflow Map in the UI.
- A **Company Page** should use top-level **Company Page Sections** rather than forcing users to scroll through every dossier area in one long page.
- **Company Page Sections** should not recreate the old Overview, Research, Health, and Evidence workspace tabs.
- A **Company Page Identity Strip** should give current company context before the History view, including company name, ticker, price, and minimal current state.
- The **Company Page Identity Strip** should persist across all **Company Page Sections**.
- The **Company Page Identity Strip** should not become a financial metrics dashboard; detailed financials belong in the Financials **Company Page Section**.
- The **Company Page Identity Strip** may show ticker, company name, current price, sector or industry, latest FundOps stage, latest verdict or status, and owned or watchlisted state.
- Price change should be optional in the **Company Page Identity Strip** and should not make the strip feel like a market terminal.
- Market cap, valuation multiples, growth, margins, fair value, thesis health, and other financial KPIs should stay out of the **Company Page Identity Strip** by default.
- The **Company Page Financials Section** should be a clean company fundamentals page rather than a replay of Screener evidence.
- Historical Screener rankings, pass evidence, and threshold-versus-observed detail should remain discoverable through History milestones and their artifact previews or readers, not duplicated in the **Company Page Financials Section**.
- The **Company Page Financials Section** should optimize for a **Financials Snapshot** first, with deeper financial tables or trends added only when they serve a clear user need.
- The **Financials Snapshot** should cover valuation, growth, margins, profitability, cash flow, leverage, and concise business context when available.
- The **Financials Snapshot** should be grounded by a **Financials Lookback** rather than relying only on a single latest-period data point.
- The **Company Page Financials Section** should review current financial state through **Latest Financial Projections** while keeping multi-period **Financial Observations** available for trends, tables, Thesis Health, Memo evidence, and Learning/Evals.
- The **Company Page Financials Section** should consume **Calculated Financial Observations** by default while keeping **Reported Financial Facts** and **Financial Observation Lineage** inspectable for audit, gaps, and source explanation.
- The **Company Page Financials Section** should show current accepted financial values by default while making material **Financial Data Corrections** and **Financial Data Supersession** inspectable.
- The starting **Financials Lookback** should use up to five fiscal years of annual fundamentals when available.
- The starting **Financials Lookback** should also retain twelve quarters, or roughly three years, of quarterly fundamentals when available.
- **Retained Quarterly Financial History** is required for **Memo-Backed Thesis Health** because quarterly cadence, year-over-year quarter, trailing-twelve-months, and multi-period-average watch items need quarter-level evidence.
- **Derived Q4 Financial Metrics** may be used in **Retained Quarterly Financial History** when direct Q4 quarterly filing values are not available.
- A **Derived Q4 Financial Metric** should retain derivation provenance, including the annual filing, the first three quarterly periods, the calculation method, and whether the derivation was complete.
- If a Q4 derivation is incomplete, ambiguous, or affected by unreconciled restatement/tag issues, FundOps should treat the affected **Thesis Watch Item Check** as a data gap rather than silently using the value.
- **Company Page Full Financials** should mark **Derived Q4 Financial Metrics** subtly and make their derivation provenance inspectable.
- **Company Page Full Financials** should not present **Derived Q4 Financial Metrics** as if they were directly reported quarterly values.
- The **Company Page Thesis Health Section** should not clutter default watch-item status or detail with **Derived Q4 Financial Metric** provenance when the derivation is complete and accepted.
- **Derived Q4 Financial Metric** provenance should remain retained and inspectable through source/provenance paths such as **Company Page Full Financials**, rather than becoming a default Thesis Health badge.
- The **Company Page Financials Section** should show summary metrics at the top and **Company Page Full Financials** below.
- Summary metrics in the **Company Page Financials Section** should use a fixed core set in the baseline product rather than adapting by sector.
- The fixed core Financials summary should emphasize valuation and growth, with market cap for company size context.
- The starting fixed core Financials summary may include Market Cap, P/E or EV/EBITDA, Revenue Growth, Gross Margin, Operating Margin, FCF Yield, ROIC, and Debt/Equity.
- **Company Page Full Financials** should include a five-year financial view when available.
- **Company Page Full Financials** should default to annual financials.
- Quarterly financials should be retained for Thesis Health and may be exposed in **Company Page Full Financials** without changing the default annual view.
- **Company Page Full Financials** should group annual data into Income Statement, Balance Sheet, and Cash Flow views.
- **Company Page Full Financials** should use a small internal control to switch between Income Statement, Balance Sheet, and Cash Flow rather than showing all three at once.
- The **Company Page Thesis Health Section** should focus on **Memo-Backed Thesis Health** rather than broad system learning.
- The **Company Page Thesis Health Section** should be rebuilt around **Thesis Watch Items** rather than the old score-first Health tab.
- The **Company Page Thesis Health Section** should be meaningful only for tickers whose history includes a **Completed Memo** or memo-derived thesis-health tracking.
- The **Company Page Thesis Health Section** should still appear as a stable section for tickers without a **Completed Memo**, using an empty state instead of hiding the section.
- The **Company Page Thesis Health Section** empty state should explain that thesis health begins after a **Completed Memo** establishes trackable assumptions.
- For a **Completed Memo** that is not thesis-health ready, the **Company Page Thesis Health Section** should use neutral empty-state language such as no thesis health checks yet.
- The **Company Page Thesis Health Section** empty state should not include a Memo generation action because **Company Page** is read-only.
- The **Company Page Thesis Health Section** should quietly show the **Active Thesis Health Source**, such as the active memo version or memo date, when thesis-health tracking exists.
- The **Company Page Thesis Health Section** should show an overall thesis-health score only when a real persisted thesis-health score exists.
- The **Company Page Thesis Health Section** should not invent a pseudo-score when only partial assumptions or fallback data are available.
- The canonical source for **Memo-Backed Thesis Health** should be the **Investment Memo Monitoring Plan** from a **Completed Memo**.
- Memo should own creation of the **Investment Memo Monitoring Plan** because it is part of the investment judgment made in the **Completed Memo**.
- The **Investment Memo Monitoring Plan** should be retained as a separate structured memo output so the **Company Page Thesis Health Section** can use it directly without reparsing memo prose.
- **Thesis Health Operational Records** should be the product source of truth for active and historical **Memo-Backed Thesis Health** state.
- **Thesis Health Operational Records** should distinguish the **Investment Memo Monitoring Plan**, **Thesis Watch Items**, **Thesis Health Refreshes**, and **Thesis Watch Item Checks** rather than retaining only one opaque plan or check blob.
- The raw structured **Investment Memo Monitoring Plan** may still be retained for audit and export, but status-driving Thesis Health behavior should use the separable operational records.
- When a **Thesis-Health Ready Memo** creates active **Thesis Watch Items**, FundOps should also create **Thesis Health Baseline Checks** from memo-time evidence.
- A **Thesis Health Baseline Check** should be marked as memo-time evidence rather than a later filing-driven **Thesis Health Refresh**.
- A **Thesis Health Baseline Check** should usually initialize **Current Thesis Watch Item State** as intact, watch, unknown, or data gap rather than broken.
- A **Thesis Health Baseline Check** should not mark a **Thesis Watch Item** broken from generic memo-time evidence; baseline broken status should require an explicit immediate kill criterion in the **Investment Memo Monitoring Plan**.
- Confirmed broken **Thesis Watch Item Status** should generally come from post-memo **Thesis Health Refresh** evidence.
- Each active **Thesis Watch Item** should retain its **Current Thesis Watch Item State** so the **Company Page Thesis Health Section** and **Dashboard** can read current status directly.
- Every **Thesis Health Refresh** should still append immutable **Thesis Watch Item Checks** so current status remains auditable and useful for Learning/Evals.
- **Current Thesis Watch Item State** should be derived from the latest accepted **Thesis Watch Item Check** rather than maintained as an independent judgment.
- **Dashboard Attention Items** and **Company Page Timeline Event Markers** may mirror material Thesis Health moments, but should not be the source of truth for **Thesis Watch Items** or routine check state.
- Historical **Memo-Backed Thesis Health** states should remain traceable to the **Investment Memo Monitoring Plan** and **Completed Memo** version that produced the tracked watch items.
- A later extraction or parsing step may normalize explicit **Investment Memo Monitoring Plan** items into **Thesis Watch Items**, but it should not invent watch items from broader memo prose.
- In the baseline product, **Memo-Backed Thesis Health** should use explicit **Investment Memo Monitoring Plan** items only, rather than extracting implicit watch items from broader memo prose.
- IC Review key assumptions may be useful legacy or fallback inputs, but they are not the canonical source for redesigned **Memo-Backed Thesis Health**.
- The **Company Page Thesis Health Section** should not use IC Review key assumptions as a legacy fallback when no **Investment Memo Monitoring Plan** exists.
- If no **Investment Memo Monitoring Plan** exists, the **Company Page Thesis Health Section** should use the empty state.
- **Thesis Watch Items** should cover core thesis assumptions, return drivers, kill criteria, risk watch items, and evidence checks when the **Completed Memo** provides them.
- A **Thesis Watch Item** should track the originating memo version, item type, expected condition, current evidence or value, **Thesis Watch Item Status**, last checked date, why it matters, and source or evidence link when available.
- A **Thesis Watch Item** should declare its **Thesis Watch Item Tracking Mode**.
- A quantitatively monitored **Thesis Watch Item** should define an exact or computable threshold, comparator, metric, and reporting period.
- A quantitatively monitored **Thesis Watch Item** should declare its **Thesis Watch Item Measurement Cadence** so confirmation rules have an unambiguous period boundary.
- A quantitatively monitored **Thesis Watch Item** should declare its **Thesis Watch Item Lookback Basis** so FundOps knows which evidence window to compare against the threshold.
- The default **Thesis Watch Item Measurement Cadence** should be quarterly for 10-Q/10-K-driven operating metrics and annual for annual-only fields.
- An **Investment Memo Monitoring Plan** may explicitly use trailing-twelve-months or slower-cycle **Thesis Watch Item Measurement Cadence** when the memo evidence supports it.
- The **Thesis Watch Item Lookback Basis** should distinguish latest-period checks from year-over-year, trailing-twelve-month, annual, or multi-period-average checks.
- Cyclical or seasonal businesses should prefer year-over-year, trailing-twelve-month, or multi-period-average **Thesis Watch Item Lookback Basis** when a latest-period check would create noisy false breaks.
- A quantitatively monitored **Thesis Watch Item** should map to a **Supported Thesis Health Field**.
- A quantitatively monitored **Thesis Watch Item** should use a metric, measurement cadence, and lookback-basis combination allowed by the **Supported Thesis Health Field Catalog**.
- The **Supported Thesis Health Field Catalog** should prevent Memo generation from choosing metric, cadence, and lookback-basis combinations that FundOps cannot compute from retained evidence.
- Once a quantitatively monitored **Thesis Watch Item** has validated metric, comparator, threshold, measurement cadence, lookback basis, and confirmation rule, its status should be produced through **Deterministic Thesis Health Evaluation**.
- LLM judgment should shape the **Investment Memo Monitoring Plan** during Memo generation, but should not rejudge quantitative **Thesis Watch Item Status** during **Thesis Health Refresh**.
- **AI-Assisted Thesis Health Review** may explain filing and market evidence, support **Outcome Driver Evidence**, suggest new or revised **Thesis Watch Items**, and create reviewable attention, but should not directly replace **Deterministic Thesis Health Evaluation** for quantitative watch items.
- **AI-Assisted Thesis Health Review** should produce **AI-Assisted Thesis Health Findings** rather than unstructured prose.
- An **AI-Assisted Thesis Health Finding** should state its thesis-health implication as intact pressure, watch concern, likely break, or unclear.
- An **AI-Assisted Thesis Health Finding** may suggest new or revised **Thesis Watch Items** and may mark whether the finding should feed Learning/Evals.
- A likely-break **AI-Assisted Thesis Health Finding** should create an **AI-Assisted Thesis Health Attention**.
- A watch-concern **AI-Assisted Thesis Health Finding** should create an **AI-Assisted Thesis Health Attention** only when the ticker is held, the concern is repeated, or the concern is tied to a core **Thesis Watch Item**.
- An intact-pressure **AI-Assisted Thesis Health Finding** should stay in Thesis Health history by default rather than creating Dashboard attention.
- An unclear **AI-Assisted Thesis Health Finding** should create Dashboard attention only when the evidence gap materially degrades thesis monitoring.
- A single-company **AI-Assisted Thesis Health Finding** may create company-specific Dashboard attention, but should not create a strategy-level **Learning Recommendation** unless it contributes to a repeated **Learning Evidence Pattern**.
- **AI-Assisted Thesis Health Review** should use **Filing-First Thesis Health Evidence**, treating market research and news as secondary context after filings, reported financials, earnings materials, and management disclosures.
- When filings or reported financials conflict with market research or news, **Filing-First Thesis Health Evidence** means filings control the thesis-health implication and market research should be shown as context, contradiction, or caveat.
- **Thesis Health Evidence Tiers** are: Tier 1 controlling filings and reported financials such as 10-Q, 10-K, 8-K, filed exhibits, and formally reported statements; Tier 2 high-value company disclosures such as earnings releases, earnings-call transcripts, investor presentations, and management guidance; and Tier 3 secondary market context such as analyst notes, news, sector commentary, social media, and market reaction.
- Tier 1 **Thesis Health Evidence** should control when it conflicts with Tier 2 or Tier 3 evidence; Tier 2 should usually control when it conflicts with Tier 3 evidence, with caveats when the conflict matters.
- **AI-Assisted Thesis Health Review** should be triggered by new filings or earnings materials, due **Outcome Evaluations**, watch/broken/data-gap thesis-health evidence, promising **Idle Learning Analysis** patterns, or explicit user request.
- A new filing or formal company disclosure for a thesis-health-ready ticker should create a **New Filing Thesis Health Review** rather than requiring a prior relevance gate.
- A **New Filing Thesis Health Review** may discover thesis risks, thesis support, or suggested **Thesis Watch Items** that were not named in the original **Investment Memo Monitoring Plan**.
- **Operating Thesis Disclosures** should receive **New Filing Thesis Health Review** by default and include operating filings and company disclosures such as 10-Q, 10-K, 8-K, relevant 20-F or 6-K disclosures, earnings releases, guidance, transcripts, and investor presentations.
- **Administrative Filing Records** should be retained but should not receive full **AI-Assisted Thesis Health Review** by default unless they touch governance, dilution, capital structure, ownership, or a known thesis risk.
- When **AI-Assisted Thesis Health Review** uses secondary online research, it should use a **Bounded Market Research Window** by default rather than broad open-ended research.
- Held thesis-health-ready tickers should follow **Held Thesis Health Review Cadence**, while non-held thesis-health-ready tickers should follow **Non-Held Thesis Health Review Cadence**.
- **Held Thesis Health Review Cadence** should be higher priority and may start around weekly metadata checks, while **Non-Held Thesis Health Review Cadence** should be slower or filing-driven.
- Different thesis-health review cadences should not change the default **Learning Evaluation Windows**, which remain comparable across held and non-held tickers.
- **Deterministic Thesis Health Evaluation** should produce intact, watch, broken, unknown, or data-gap status from supported evidence and validated watch item rules.
- In the baseline product, the **Supported Thesis Health Field Catalog** may include any already-registered metric that FundOps can retrieve and compare consistently during **Thesis Health Refresh**.
- Sector-specific and SEC data-point refinement for the **Supported Thesis Health Field Catalog** belongs in the Thesis Health field-catalog design.
- Vague watch language may be retained as qualitative or unsupported, but should not affect **Memo-Backed Thesis Health** status.
- Custom or unsupported metrics should be retained as unsupported **Thesis Watch Items**, but should not drive **Memo-Backed Thesis Health** status in the baseline product.
- Unsupported **Thesis Watch Items** should be hidden from the default **Company Page Thesis Health Section** in the baseline product.
- Unsupported **Thesis Watch Items** may become visible later when FundOps adds an explicit monitoring source such as online search or qualitative evidence review.
- Unsupported **Thesis Watch Items** should not be counted in user-facing Thesis Health coverage stats in the baseline product.
- FundOps should not expose hidden unsupported watch items in a way that makes the user feel a promised Thesis Health feature is missing.
- The default **Company Page Thesis Health Section** should not mention implementation limits such as quantitative-only tracking.
- The default **Company Page Thesis Health Section** should present supported tracked items naturally rather than caveating hidden unsupported items.
- A **Completed Memo** should be considered a **Thesis-Health Ready Memo** only when it has at least one quantitative **Thesis Watch Item** with a catalog-allowed metric, measurement cadence, lookback basis, and available baseline evidence.
- A supported metric name alone should not make a **Completed Memo** thesis-health ready if FundOps cannot create an initial **Thesis Health Baseline Check** for that watch item.
- If a **Completed Memo** is not thesis-health ready, the **Company Page Thesis Health Section** should show an empty or partial state rather than pretending the thesis can be monitored.
- A **Thesis Watch Item** should declare or inherit its confirmation rule for moving from watch to broken.
- The default confirmation rule should be two consecutive relevant reporting periods before a **Thesis Watch Item** becomes broken.
- The **Investment Memo Monitoring Plan** may override the default confirmation rule when a watch item is explicitly immediate, seasonal, cyclical, or slower-cycle.
- If a new filing is detected but required data is unavailable or cannot be parsed, FundOps should preserve the prior status-driving **Thesis Watch Item Status** and mark the item with a data gap rather than treating missing data as thesis deterioration.
- The **Company Page Thesis Health Section** should show a data gap quietly inline on the affected **Thesis Watch Item**.
- Fuller data-gap explanation should live in the Thesis Health history row or **Company Page Milestone Preview** detail.
- Repeated Thesis Watch Item data gaps should create a lower-priority **Dashboard Attention Item** because monitoring coverage is degraded.
- Repeated Thesis Watch Item data gaps should mean two consecutive relevant filings where a status-driving watch item cannot be evaluated.
- **Dashboard Attention Items** for repeated data gaps should remain distinct from **Material Thesis Break** attention.
- **Dashboard Attention Items** for repeated data gaps should link first to the relevant **Company Page Thesis Health Section** detail.
- Repeated data-gap detail may include a secondary path to Settings/Data provider checks when the issue appears provider- or configuration-related.
- FundOps should not introduce a separate diagnostics page for Thesis Health data gaps in the baseline product.
- In the baseline product, only quantitatively trackable **Thesis Watch Items** should affect **Memo-Backed Thesis Health** status.
- Qualitative or news-dependent **Thesis Watch Items** may remain visible, but should stay unknown or not monitored until FundOps has an explicit qualitative or online-search monitoring source.
- FundOps should not run always-on LLM or news monitoring for **Memo-Backed Thesis Health** by default in the baseline product.
- **Memo-Backed Thesis Health** should update through **Thesis Health Refresh** rather than when a user opens the **Company Page**.
- **Portfolio Price and P&L Refresh** may run daily or when a new **Live FundOps Server Session** starts because it is separate from filing-driven thesis-health updates.
- A user-triggered Portfolio refresh should run **Portfolio Price and P&L Refresh** by default and should not trigger **Thesis Health Refresh** or web thesis monitoring.
- **Portfolio Price and P&L Refresh** should preserve user-entered lots, purchase dates, cash, position type, Portfolio Thesis Coverage State, and Active Thesis Health Source while updating only price-derived fields.
- Portfolio may show concentration, drawdown, or similar **Portfolio Factual Flags** inline, but the decision-support interpretation of those conditions belongs in **Portfolio Review**.
- **Thesis Health Refresh** should cover all due **Thesis-Health Ready Memos**, not only currently held positions.
- **Long-Horizon Thesis Tracking** should be an intentional purpose of **Thesis Health Refresh** so non-held memo-backed tickers can contribute to Learning/Evals over time.
- Non-held thesis-health-ready tickers should not automatically expire from **Thesis Health Refresh** solely because they are not currently held.
- Non-held thesis-health-ready tickers may use a lower **Thesis Health Refresh** cadence than held positions.
- Held thesis-health-ready tickers should have higher **Data Provider Request Queue** priority than non-held thesis-health-ready tickers.
- The exact non-held **Thesis Health Refresh** cadence should be tuned around user experience and available **Shared Data Provider Budget** rather than fixed prematurely.
- Non-held **Long-Horizon Thesis Tracking** should stay metadata-gated and should not run full quantitative recalculation unless a new relevant 10-Q or 10-K is detected.
- **Thesis Health Filing Metadata Checks** should run on a lower-frequency schedule, such as weekly, for thesis-health-ready tickers rather than every **Portfolio Price and P&L Refresh**.
- A **Thesis Health Refresh** should first use a **Thesis Health Filing Metadata Check** to decide whether expensive quantitative recalculation is needed.
- Quantitative **Memo-Backed Thesis Health** recalculation should run only when a new relevant 10-Q or 10-K is detected or when the user explicitly requests a refresh that allows rechecking stale data.
- If a **Thesis Health Filing Metadata Check** finds no new relevant 10-Q or 10-K, FundOps should record a **Metadata-Only Thesis Health Refresh**.
- A **Metadata-Only Thesis Health Refresh** should update filings-last-checked recency while leaving **Current Thesis Watch Item State** unchanged.
- The **Company Page Thesis Health Section** should distinguish metadata-only checks from full recalculation, such as showing filings checked more recently than watch items recalculated.
- A **Thesis Health Refresh** may run as part of Portfolio monitoring or an equivalent scheduled monitoring capability.
- A **Thesis Health Refresh** should also be available through a **Manual Thesis Health Refresh** action.
- The primary **Manual Thesis Health Refresh** action should live on the **Dashboard**.
- The **Dashboard** label for **Manual Thesis Health Refresh** should use metadata-gated language such as checking for thesis updates or new filings rather than implying every click recomputes all Thesis Health.
- The **Dashboard** and **Company Page Thesis Health Section** should distinguish the latest Thesis Health Filing Metadata Check time from the latest full Thesis Health recalculation time.
- The **Company Page Thesis Health Section** should not include its own manual refresh action in the baseline product.
- **Company Page** should remain read-only for Thesis Health checks; the **Dashboard** owns user-initiated Thesis Health checking.
- A **Manual Thesis Health Refresh** should refresh all due thesis-health-ready tickers rather than asking the user to pick arbitrary tickers.
- The **Dashboard** should make the number of due thesis-health-ready tickers clear before a **Manual Thesis Health Refresh** runs.
- A **Manual Thesis Health Refresh** may override the normal metadata-check cadence and run **Thesis Health Filing Metadata Checks** for due thesis-health-ready tickers immediately.
- A **Manual Thesis Health Refresh** should still run full quantitative recalculation only when the metadata check detects a new relevant 10-Q or 10-K.
- Missed scheduled **Thesis Health Refreshes** should not automatically catch up when a new **Live FundOps Server Session** starts.
- When a scheduled **Thesis Health Refresh** is missed, the latest Thesis Health state should remain stale or overdue until the next scheduled refresh or a **Manual Thesis Health Refresh**.
- **Thesis Health Refresh** should be data-provider-budget aware because it shares quantitative data sources with Pipeline, Screener, Thesis, Portfolio, and other workflow capabilities.
- **Thesis Health Refresh** should use the **Data Provider Request Queue** rather than owning a separate provider path.
- A scheduled **Thesis Health Refresh** may modestly slow other workflow capabilities when they share the same provider source, but it should remain bounded by the **Shared Data Provider Budget**.
- Scheduled **Thesis Health Refreshes** should have lower **Data Provider Request Queue** priority than **Interactive Workflow Runs**.
- A **Manual Thesis Health Refresh** should still sit below **Interactive Workflow Runs** in the **Data Provider Request Queue** because it is maintenance work.
- A **Thesis Health Refresh** may wait, pause, or resume behind interactive work because it is monitoring rather than an interactive workflow.
- Routine **Thesis Health Refresh** queue waiting should remain quiet by default rather than becoming a prominent Dashboard alert.
- The **Dashboard** may expose queued Thesis Health status in operational details, but should emphasize stale, overdue, failed, or completed states over routine queue contention.
- The **Company Page Thesis Health Section** should read the latest retained Thesis Health state and show when it was last checked.
- The **Company Page Thesis Health Section** should make clear when filings were last checked even if Thesis Health status did not need recalculation.
- Routine Thesis Watch Item updates should remain inside the **Company Page Thesis Health Section** rather than becoming **Company Page Workflow Milestones**.
- Only material **Memo-Backed Thesis Health** breaks should become **Company Page Workflow Milestones** by default.
- A **Material Thesis Break** should generally require confirmation across more than one reporting period, especially for cyclical or seasonal businesses.
- A single adverse reporting period should usually move a **Thesis Watch Item** to watch rather than broken unless the **Investment Memo Monitoring Plan** explicitly defines it as a one-period kill criterion.
- A **Material Thesis Break** may occur when a quantitative watch item tied to a kill criterion or core return driver becomes confirmed broken, or when multiple related watch items move to watch or broken in the same Thesis Health Refresh.
- **Memo-Backed Thesis Health** should answer which memo-derived watch items still hold, which are weakening, and which have broken.
- The **Company Page Thesis Health Section** should show a qualitative thesis-health summary in the baseline product rather than a numeric score.
- The baseline **Thesis Health Summary Label** set should be Intact, Watching, Broken, and Not Checked.
- When all checked status-driving watch items are intact, the **Thesis Health Summary Label** should be Intact and may use plain-language copy such as thesis healthy.
- When no active watch items are broken but one or more are in watch status, the **Thesis Health Summary Label** should be Watching.
- The Watching summary should explain when a watch item needs another reporting period before it can become confirmed broken.
- When a confirmed **Material Thesis Break** exists, the **Thesis Health Summary Label** should be Broken.
- A Broken **Thesis Health Summary Label** should surface the confirmed thesis condition for review rather than automatically creating a sell instruction.
- A **Material Thesis Break** should create a high-priority **Dashboard Attention Item**.
- A **Dashboard Attention Item** for a **Material Thesis Break** should link into the relevant **Company Page Thesis Health Section** detail rather than prescribing a portfolio action.
- **Dashboard Attention Items** for **Material Thesis Breaks** should include all affected thesis-health-ready tickers, not only currently held positions.
- **Dashboard Attention Items** for **Material Thesis Breaks** should distinguish held positions from non-held memo-backed tickers.
- A **Dashboard Attention Item** for a **Material Thesis Break** should clear automatically when the active **Thesis Health Summary Label** is no longer Broken.
- Cleared Material Thesis Break attention items should remain preserved in **Company Page** history.
- When a **Material Thesis Break** resolves, the original break history row should show the resolved state rather than creating a duplicate main story milestone by default.
- The Thesis Health Refresh that resolved the break should still appear in the **Company Page Thesis Health Section** history list.
- Portfolio or Portfolio Review capabilities may consider Broken Thesis Health later, but **Memo-Backed Thesis Health** itself should not own portfolio action recommendations.
- The qualitative thesis-health summary should derive from **Thesis Watch Item Status** counts, such as intact, watch, broken, or unknown.
- The **Company Page Thesis Health Section** should group **Thesis Watch Items** by status first, such as broken, watch, unknown, and intact.
- The default **Thesis Watch Item** status order should be broken, watch, unknown, then intact.
- A **Thesis Watch Item** may still display its item type inside the status grouping.
- Constitution-level recommendations and broad Learning/Evals outcomes should not dominate the **Company Page Thesis Health Section**.
- A **Company Page** should lead with the **Company Page Workflow Map** so the user's first view is the ticker's retained FundOps workflow history.
- The **Company Page Workflow Map** should organize history into **Company Page Workflow Lanes** by workflow stage.
- The **Company Page Workflow Map** should use dated milestone cards rather than a proportional or scaled calendar chart.
- Dated milestone cards inside each **Company Page Workflow Lane** should be ordered newest first by default.
- Each **Company Page Workflow Lane** should show the latest few milestone cards by default and offer a show-all expansion when more retained history exists.
- Showing the latest three milestone cards per **Company Page Workflow Lane** is the default starting point.
- A **Workflow Milestone Card** should stay minimal, showing the milestone date plus a tiny type, status, rank, version, or action cue when available.
- Compact milestone details belong in the **Company Page Milestone Preview**, not inside the **Workflow Milestone Card**.
- **Company Page Workflow Lanes** should include Screener, Thesis, IC Review, Memo, and Portfolio.
- **Company Page Workflow Lanes** should use the fixed order Screener, Thesis, IC Review, Memo, then Portfolio.
- Thesis Health should remain a separate **Company Page Section** rather than a default **Company Page Workflow Lane**.
- Routine **Memo-Backed Thesis Health** checks should live in the **Company Page Thesis Health Section** rather than appearing as default **Company Page Workflow Milestones**.
- Major thesis breaks, resolved outcomes, or portfolio-relevant thesis-health events may appear in the **Company Page Workflow Map** when they materially change the ticker story.
- The Portfolio **Company Page Workflow Lane** should focus on portfolio history such as purchases, sales, position size, and transaction price.
- Portfolio Review items should appear in the Portfolio lane only when they resulted in or directly explain a portfolio-relevant action.
- The **Company Page Workflow Map** should show the core workflow lanes even when a lane has no milestones, using de-emphasized empty lanes to show where the ticker has not progressed.
- Empty **Company Page Workflow Lanes** should show a quiet "Not reached" state rather than appearing broken or blank.
- Empty **Company Page Workflow Lanes** should be informational only and should not open previews, launch workflows, or create placeholder artifacts.
- The **Company Page Workflow Map** should show meaningful **Company Page Workflow Milestones** by default rather than every retained operational event.
- **Company Page Workflow Milestones** should include user-facing outputs and decisions such as Screener snapshots, Completed Thesis artifacts, IC Verdicts or overrides, Completed Memo versions, Portfolio or Portfolio Review actions, thesis-health checks, and outcome checks.
- Operational retries, background sync events, raw data refreshes, and minor status transitions should not appear as default **Company Page Workflow Milestones**.
- Selecting a **Company Page Workflow Milestone** should open a **Company Page Milestone Preview** before full artifact reading.
- A **Company Page Milestone Preview** should keep the **Company Page Workflow Map** visible and provide a clear action to open the exact artifact in the **Workflow Artifact Reader** when one exists.
- The **Company Page Milestone Preview** should appear as a right-side panel in the desktop Company Page layout.
- The **Company Page Milestone Preview** should be closed by default and should open only after the user selects a real **Workflow Milestone Card**.
- The **Company Page Milestone Preview** should slide out from the right side as an overlay on top of the Company Page rather than resizing or pushing the Workflow Map.
- The **Company Page Milestone Preview** should not use a dimmed backdrop because it is an inspection drawer, not a modal.
- The **Company Page Milestone Preview** should have a close control at the top left of the panel.
- The **Company Page Milestone Preview** should close only through its explicit close control.
- When the **Company Page Milestone Preview** is open, selecting another **Workflow Milestone Card** should update the existing panel content in place.
- The selected **Workflow Milestone Card** should remain visually highlighted while its **Company Page Milestone Preview** is open.
- The **Company Page Milestone Preview** should have a top-right reader action that opens the exact artifact in the **Workflow Artifact Reader** when a readable artifact exists.
- Opening the **Workflow Artifact Reader** from the **Company Page Milestone Preview** should navigate the whole Company Page into the reader rather than opening another overlay or split view.
- The Company Page interaction model should be responsive, but this context does not define a separate mobile-specific behavior model.
- Common **Milestone Preview Fields** should include date, workflow stage, one-line summary, status or verdict when applicable, key numbers, source or provenance, and a read action when the milestone has a readable artifact.
- **Company Page Milestone Preview** content may add artifact-specific fields over time without changing the shared preview baseline.
- Detailed **Company Page** layout, content hierarchy, and visual treatment belong in the Company Page design spec; Library decisions should define only access, lookup, embedding, timeline read actions, and reader boundaries.
- The chronological ticker timeline on a **Company Page** is the **Company Page Timeline**.
- A **Company Page Timeline** should be the primary place where users find and reopen prior Thesis, IC Review, Memo, Screener, and other ticker-specific workflow outputs.
- A **Company Page Timeline** should include both **Completed Workflow Artifacts** and relevant **Company Page Timeline Event Markers**.
- A **Company Page Timeline Row** should stay compact by default.
- A **Company Page Timeline Row** should show artifact type, date or time, one-line summary, verdict, decision, or status when the artifact has one, and a **Workflow Artifact Read Action**.
- User actions, selection feedback, IC overrides, allocator actions, portfolio outcome snapshots, and workflow transitions should appear as **Company Page Timeline Event Markers** when they matter to the ticker's history.
- A **Company Page Timeline Event Marker** should not open the **Workflow Artifact Reader** unless it has a retained payload substantial enough to read as an artifact.
- A **Workflow Artifact Read Action** should open the exact **Completed Workflow Artifact** attached to the selected **Company Page Timeline** entry.
- A **Workflow Artifact Read Action** should address its target by **Workflow Artifact Identifier** rather than by ticker, date, or artifact type alone.
- The **Workflow Artifact Reader** should render full artifact output for the selected Thesis, IC Verdict, Screener Snapshot, Investment Memo, or other completed workflow artifact.
- The **Workflow Artifact Reader** should use a shared **Workflow Artifact Reader Shell** with a type-specific **Workflow Artifact Body Renderer**.
- The **Workflow Artifact Reader Shell** should show the originating ticker, artifact type, generation date, artifact metadata, and a clear way back to the **Company Page**.
- **Workflow Artifact Body Renderers** should adapt to artifact type: Investment Memo needs section navigation, citations, tables, and source handling; IC Verdict needs scorecard and rationale; Thesis needs the concise argument and return profile; Screener Snapshot needs ranking and evidence details.
- The **Workflow Artifact Reader** may display ticker, artifact type, generation date, and a back link, but those display fields should not be the identity of the artifact being read.
- Opening a **Workflow Artifact Read Action** should navigate to the standalone **Workflow Artifact Reader** rather than rendering the full artifact inside the **Company Page** or **Library Result Panel**.
- The **Workflow Artifact Reader** back link should return to the originating context when practical, such as Library with the same **Selected Library Ticker** or the standalone **Company Page**.
- Full artifact body, detailed scorecards, citations, tables, source registry, and section navigation belong in the **Workflow Artifact Reader** rather than the **Company Page Timeline Row**.
- **Artifact Export** should be available from the **Workflow Artifact Reader** for readable Completed Workflow Artifacts and may also be exposed through Library or Company Page artifact actions.
- **Retail Artifact PDF** should be the primary user-facing **Artifact Export** format for retail users.
- **Retail Artifact PDFs** should be produced through a versioned **PDF Rendering Pipeline** rather than by printing the current reader UI.
- **Internal Artifact Markdown** may support rendering, testing, portability, or internal workflows, but should not be treated as the polished retail export.
- The **Workflow Artifact Reader Shell** should prioritize on-screen reading while keeping export available as a secondary action.
- The **Workflow Artifact Reader** should provide a clear way back to the originating **Company Page**.
- **Library Search** should be ticker-only and ticker-first rather than artifact-first.
- A **Library Search** result should resolve only for a **Known Library Ticker**.
- A **Library Search** result should resolve to the corresponding **Company Page** dossier for the **Known Library Ticker**.
- A ticker with **Saved Screener Work** is a **Known Library Ticker** even if it did not advance to Thesis, IC Review, Memo, Portfolio, or Portfolio Review.
- Library discoverability from Screener should follow the saved top Screener Review Set work, not the entire raw **Screened Universe**.
- A ticker with a retained Portfolio holding or Portfolio history is a **Known Library Ticker** even if it has not gone through Screener, Thesis, IC Review, or Memo.
- Library should remain a standalone **Library Entry Point** for directly opening known ticker history without relying on another workflow surface to expose the ticker first.
- A user should not need to encounter a ticker in Screener, Research Queue, Portfolio, Portfolio Review, or another workflow surface before opening its **Company Page** from Library.
- Library should show no ticker dossier by default before the user searches or selects a ticker.
- Library should not show a default list of all Known Library Tickers by default.
- While the user types, Library may show **Library Match Suggestions** for ticker-prefix matches among **Known Library Tickers**.
- **Library Match Suggestions** should search globally across **Known Library Tickers** rather than only the current Constitution or strategy version.
- **Library Match Suggestions** should prefer predictable ticker-prefix matching over broad fuzzy matching in the baseline product.
- **Library Match Suggestions** should not need special labels for Screener-only, Portfolio-only, or richer-history tickers by default.
- The selected **Company Page** timeline should reveal what kind of retained history exists for the ticker.
- Selecting a **Library Match Suggestion** should reveal the matching **Company Page** dossier.
- An exact ticker match should reveal the matching **Company Page** dossier only after the user presses Enter or explicitly selects the match.
- Library should start blank on ordinary new visits.
- The **Selected Library Ticker** should be restorable only when the visit explicitly carries selected ticker state, such as refresh or a direct URL with that ticker.
- Restoring a **Selected Library Ticker** should keep the user in the Library two-pane layout rather than redirecting to a separate Company Page route.
- Library should show the selected **Company Page** dossier inside a **Library Result Panel** rather than navigating away by default.
- Selecting a different **Known Library Ticker** should replace the current **Selected Library Ticker** in the **Library Result Panel** without requiring a clear step.
- **Company Page** should still remain available as a standalone route or surface outside Library.
- Library is another access method to **Company Page**, not the owner of **Company Page** behavior.
- Embedded **Company Page** content and behavior inside Library should match the standalone **Company Page**.
- Library may adjust only surrounding presentation or duplicate page chrome when embedding **Company Page**.
- Across workflow surfaces, the **Ticker Link** should be the primary way to open a **Company Page**.
- Workflow surfaces should not add a separate "View in Library" button when clicking the ticker can open the **Company Page**.
- **Library Search Panel** should sit beside the **Library Result Panel** and should be collapsible so the **Company Page** dossier can use more horizontal space.
- The same **Library Search Panel Toggle** should collapse and reopen the **Library Search Panel**.
- A collapsed **Library Search Panel** should keep the **Library Search Panel Toggle** visible.
- Library should not create or show an empty **Company Page** for an unknown ticker.
- Unknown ticker searches in Library should show a no-result state rather than triggering company lookup or artifact generation.
- Company-name, thematic, and natural-language archive questions should belong to **Archive Q&A**, not **Library Search**.
- A **Library** search for a ticker should show the corresponding **Company Page** dossier in the main/right content area.
- Library should expose **Library Browse** as its main surface by default.
- **Library Browse** should provide ticker-first lookup and reuse the **Company Page** dossier for ticker results.
- **Library Sync** should not appear as a primary user-facing action in Library.
- Library should feel like a live archive projection over retained workflow data rather than a manually synchronized database.
- Library should use a **Library Projection** over canonical workflow artifacts and records rather than owning artifact truth.
- Library and Archive Q&A retrieval indexes should be rebuildable projections; deleting or changing them should not delete retained evidence, source records, evidence bundles, or completed artifacts.
- Canonical artifact truth belongs to the originating workflow artifacts and ticker history surfaced on **Company Page**.
- Retained history should remain globally available across Constitution and strategy changes.
- Company Page should be responsible for formatting a ticker's retained history across Constitution and strategy changes.
- Library should remain only the ticker lookup mechanism for opening Company Page history.
- **Library Stats** should not be part of **Library Browse** by default.
- Win rate, accuracy, and other performance metrics belong in Learning/Evals or Dashboard surfaces where methodology and context can be explained.
- Cross-artifact archive questions should live in **FundOps Chat** as **Archive Q&A**, not in a separate Library tab by default.
- **Archive Q&A** should answer questions across archived Thesis, IC Review, Memo, Screener, Portfolio, Portfolio Review, and outcome history when available.
- Full-length **Investment Memo** reading should happen in the **Workflow Artifact Reader** when opened from the **Company Page Timeline**.
- Library should not keep a dedicated memo-specific reading tab by default.
- A **Company Page**, Memo workflow row, or other workflow surface may link to the relevant **Company Page Timeline** entry or **Workflow Artifact Reader** for an **Investment Memo**.
- The Memo workflow capability should own **Investment Memo Generation Action**, not long-form memo reading.
- Multiple **Investment Memo Versions** for the same resolved Investment Entity or Security should appear as dated **Company Page Timeline** entries.
- Opening a dated **Investment Memo Version** from the **Company Page Timeline** should render that exact version in the **Workflow Artifact Reader**.
- A **Library** view can keep search/results and memo navigation in its left or top control area while reusing the **Company Page** as the ticker result surface.
- Direct ticker links and Library ticker lookup share one **Company Page** dossier behavior.

## Example dialogue

> **Dev:** "If a user clicks PAYC from the Screener, do they land in the Library?"
> **Domain expert:** "They land on the **Company Page** for PAYC. The Library can search for that same ticker dossier, but the dossier is the thing being viewed."

## Flagged ambiguities

- "Ticker Detail" is the current implementation/page name, while **Company Page** is the product behavior name. Resolved: use **Company Page** in behavior specs and eval language; keep `TickerDetail` as an implementation alias unless the UI is renamed later.
- "Strategy Chat" was previously used for the whole conversational product surface. Resolved: **FundOps Chat** is the whole conversational surface, while **Strategy Chat** is the strategy-changing behavior inside it.
- **Library** and **Company Page** were previously described as separate pages. Resolved: **Library** is the search/archive entry point; **Company Page** is the ticker dossier result reused by Library and all ticker links.
- The Library surface could have been renamed to a more literal lookup label. Resolved: keep the user-facing name **Library**.
- Removing Library as a standalone visible surface would make direct ticker lookup depend on other workflow surfaces exposing the ticker first. Resolved: keep Library as a standalone **Library Entry Point** for known ticker history.
- **Library Search** could have been ticker-first or artifact-first. Resolved: **Library Search** is ticker-first, while artifact content can still support reading and **Archive Q&A** behind the scenes.
- **Ask the Library** was previously a separate Library tab. Resolved: cross-artifact archive questions belong in **FundOps Chat** as **Archive Q&A**, and Library defaults to **Library Browse**.
- Current workflow UIs include "View in Library" buttons. Resolved product direction: use **Ticker Links** to open **Company Page** instead of separate Library-view buttons.
- **Completed Memo** content needs a larger reading footprint than the **Company Page** dossier. Resolved: open full memo content through the generic **Workflow Artifact Reader**, not a memo-specific Library tab.
- The current implementation points memo timeline actions toward the Library Memos tab and also has a Company Page memo popup. Resolved product direction: converge reading for Memo, Thesis, IC Review, Screener, and other completed outputs into **Workflow Artifact Read Actions** from the **Company Page Timeline**.
- **Research Memo** and **Investment Memo** were previously separate Memo outputs. Resolved: the active Memo workflow produces one merged **Completed Memo** labeled **Investment Memo** in the UI, with company-research depth folded into the investment argument.
- The current Company Page UI is tabbed like an active workspace. Resolved product direction: use top-level read-only **Company Page Sections** for History, Financials, and Learning, with a persistent **Company Page Identity Strip** and History as the default section.
- **Allocator** was previously used as a top-level product surface for sizing and action recommendations. Resolved: use **Portfolio Review** for the user-facing review queue; keep Allocator only as a legacy or internal implementation name until renamed, and do not preserve Allocator as a separate visible product surface.
- "Settings" was previously used for both operational controls and strategy-derived workflow tuning. Resolved: **Settings/Config** is operational; **Constitution**-owned workflow behavior changes through **Strategy Chat** or another explicit workflow-changing behavior, with **Settings Projection** as the derived inspection view.
- "Cost Tracking" implies exact AI spend, but current usage evidence is model and token counts with optional pricing estimates. Resolved: use **AI Usage Summary** as the canonical concept and treat **Estimated AI Cost** as approximate unless provider billing data is available.
- Current implementation surfaces are not the source of truth for the bottom-up product redesign. Resolved: use the glossary to describe target product behavior first, then decide which existing routes, pages, and controls should be kept, replaced, or removed during implementation planning.
- Current proof-of-concept data and schema are not migration constraints for the new platform architecture. Resolved: the new Local FundOps Workspace schema may start clean, with forward migrations applying from that new baseline.
- "User correction" should not imply user-authored financial fact overrides. Resolved: user behavior is retained through **Dashboard Response Records**, **Learning Feedback Signals**, portfolio corrections, strategy revisions, and workflow judgments, while source-backed financial facts are corrected through **Financial Data Corrections**.
