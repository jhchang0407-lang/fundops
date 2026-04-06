# FundOps UI Wireframes v1

Status: DRAFT  
Purpose: Low-fidelity wireframes to align on layout, hierarchy, and UX before full frontend build.

These are not visual comps. They are structural wireframes for the most important product surfaces.

---

## 1. Home / Mirror (`/`)

### Goal
This page should feel like opening the product's brain, not opening a dashboard. It is the operating center for the investor's identity, current tension, and system learning.

### Mode A: No Constitution Yet

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ FUNDOPS                                                                     │
│                                                                              │
│                The Mirror                                                    │
│                "A mirror that gets sharper over time."                       │
│                                                                              │
│                Tell me about your investment approach.                       │
│                I'll configure the system around how you think.               │
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────────┐  │
│  │ I'm a concentrated value investor who looks for...                    │  │
│  │                                                                        │  │
│  └────────────────────────────────────────────────────────────────────────┘  │
│                                                      [ Start Conversation ]  │
│                                                                              │
│  Conversation Preview / Running Transcript                                   │
│  ┌────────────────────────────────────────────────────────────────────────┐  │
│  │ FundOps: What kind of businesses do you most want to own?             │  │
│  │ You: Durable compounders with room for rerating...                    │  │
│  │ FundOps: When you say cheap, what does cheap mean to you?             │  │
│  └────────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
│  Quick reply pills                                                           │
│  [ Below intrinsic value ] [ Sector-relative cheap ] [ High ROIC ]          │
└──────────────────────────────────────────────────────────────────────────────┘
```

### Mode B: Constitution Exists

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ Home / The Mirror                                                            │
│ Your investment constitution, behavior, and system learning                  │
├──────────────────────────────────────────────────────────────────────────────┤
│ Constitution Snapshot                                                        │
│ ┌──────────────────────────────────────────────────────────────────────────┐ │
│ │ "Buy quality businesses at a meaningful discount and hold 3-5 years."  │ │
│ │                                                                          │ │
│ │ Style: Concentrated value / quality-at-a-discount   Horizon: 3-5 years  │ │
│ │ Version 4                                         [ Refine conversation ] │ │
│ │                                                                          │ │
│ │ Must-Have Signals            Anti-Signals          IC Hurdles            │ │
│ │ [ High ROIC ]                [ Leverage creep ]    Base 20%              │ │
│ │ [ FCF durability ]           [ Story stocks ]      Bear 15%              │ │
│ │ [ Rerating path ]                                   Haircut 70%          │ │
│ └──────────────────────────────────────────────────────────────────────────┘ │
├──────────────────────────────────────────────────────────────────────────────┤
│ Said vs Did                                      Portfolio + Actions         │
│ ┌──────────────────────────────┐               ┌──────────────────────────┐ │
│ │ Signal Drift                 │               │  Portfolio KPI cards     │ │
│ │ High ROIC violated 22%       │               │  Value / P&L / Pos / Al. │ │
│ │ Quality margin violated 8%   │               │                          │ │
│ │                              │               │  Empty: Import portfolio │ │
│ │ Approval Profile             │               │                          │ │
│ │ Pass rate / conviction dist  │               │  Top allocator actions   │ │
│ └──────────────────────────────┘               └──────────────────────────┘ │
├──────────────────────────────────────────────────────────────────────────────┤
│ Your Attention                                   System Learning             │
│ ┌──────────────────────────────┐               ┌──────────────────────────┐ │
│ │ IC-passed names              │               │ Refinement proposals     │ │
│ │ GOOGL — why this fits you    │               │ "You've dismissed 4      │ │
│ │ META — health changed        │               │ declining-margin names"  │ │
│ │ Thesis health alerts         │               │ [ Accept ] [ Reject ]    │ │
│ └──────────────────────────────┘               └──────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────────────┘
```

### Key UX Notes
- The top card should feel like the user's operating constitution, not a settings summary.
- "Said vs Did" is one of the most differentiated surfaces in the whole product.
- "Your Attention" should be action-oriented.
- "System Learning" should show that the product is getting sharper, not just logging events.

---

## 2. Screener (`/screener`)

### Goal
Show what the machine found and why, with quick feedback loops that teach the system.

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ Screener                                                                     │
│ 1,247 screened · 20 surfaced · Strategy: Thomas Value Pipeline              │
│ [ Dislocation ] [ Compounder ]                         [ Run Screener ]      │
├──────────────────────────────────────────────────────────────────────────────┤
│ Top Results                                                                  │
│ ┌──────────────────────────────────────────────────────────────────────────┐ │
│ │ #  Ticker  Company    Score  ExpRet  Discount  Quality  Growth  Actions │ │
│ │ 1  GOOGL   Alphabet   87.2   28%     35%       8.6      6.2     ▸ ⊕ ⊖   │ │
│ │    Expanded row:                                                         │ │
│ │    "Cheap high-quality platform with muted sentiment..."                 │ │
│ │    Return bar: [discount][growth][margin][dividends]                    │ │
│ │    [ Run Thesis ] [ Promote ] [ Dismiss ]                               │ │
│ └──────────────────────────────────────────────────────────────────────────┘ │
├──────────────────────────────────────────────────────────────────────────────┤
│ Rest of Universe (collapsed by default)                                     │
└──────────────────────────────────────────────────────────────────────────────┘
```

### Key UX Notes
- The table is the main surface.
- Expandable rows matter more than separate detail modals.
- Feedback controls should be frictionless.
- The user should feel the ranking is "for me," not "for investors generally."

---

## 3. Research (`/research` or `/thesis`)

### Goal
This is the decision funnel between idea discovery and deep memo work.

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ Research Pipeline                                                            │
│ Theses generated, IC verdicts, next actions                                 │
│ [ All ] [ PASS ] [ NO_PASS ] [ Pending IC ]                                 │
├──────────────────────────────────────────────────────────────────────────────┤
│ ┌──────────────────────────────────────────────────────────────────────────┐ │
│ │ Ticker  ExpRet  Discount  Verdict   Conviction  Constitution Fit  Next │ │
│ │ GOOGL   28%     35%       PASS      4/5         91               Memo  │ │
│ │                                                                          │ │
│ │ Expanded:                                                                │ │
│ │ Opportunity Summary                                                      │ │
│ │ Variant View                                                             │ │
│ │ Return Decomposition bar                                                 │ │
│ │ Constitution scorecard                                                   │ │
│ │ - Cheapness: pass                                                        │ │
│ │ - Quality durability: pass                                               │ │
│ │ - Balance sheet caution: pass                                            │ │
│ │ Similar names from library                                               │ │
│ │ - Similar to MSFT (approved, thesis intact)                              │ │
│ │ - Similar to ADBE (rejected, later rerated)                              │ │
│ │ Key assumptions                                                          │ │
│ │ [ Generate Memo ] [ View Ticker ] [ Dismiss ]                            │ │
│ └──────────────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────────────┘
```

### Key UX Notes
- This page should feel like a PM workbench.
- The expanded row should be rich enough to decide whether to spend memo cost.
- Constitution fit should become a signature element over time.

---

## 4. Portfolio (`/portfolio`)

### Goal
Dense, trustworthy, and operational. This is where current holdings meet thesis integrity.

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ Portfolio                                                                    │
│ $759K total · +$94K P&L · 14 positions                         [ Refresh ]  │
├──────────────────────────────────────────────────────────────────────────────┤
│ KPI cards: Value | P&L | Positions | Alerts                                 │
├──────────────────────────────────────────────────────────────────────────────┤
│ Holdings Table                                                               │
│ ┌──────────────────────────────────────────────────────────────────────────┐ │
│ │ Ticker Shares Cost Price P&L% Weight Health Type Value                  │ │
│ │ CHKP   120    144  165   +14.6 11.2% 82     Core $19,800                │ │
│ │                                                                          │ │
│ │ Expanded row:                                                            │ │
│ │ Thesis summary                                                           │ │
│ │ Key assumptions                                                          │ │
│ │ Monitoring status                                                        │ │
│ │ Related alerts                                                           │ │
│ └──────────────────────────────────────────────────────────────────────────┘ │
├──────────────────────────────────────────────────────────────────────────────┤
│ Alerts                                                                       │
│ RCAT concentration > limit                                                  │
│ UMAC drawdown breach                                                        │
└──────────────────────────────────────────────────────────────────────────────┘
```

### Key UX Notes
- Portfolio is where "I own this" should feel very different from "I researched this."
- A future version should give thesis health much more visual weight than it has today.

---

## 5. Library (`/library`)

### Goal
Institutional memory, not memo storage.

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ Library                                                                      │
│ Search all research, outcomes, and prior judgment                            │
├──────────────────────────────────────────────────────────────────────────────┤
│ Search bar                                                                   │
│ [ Search tickers, sectors, or ask a question...                        ]     │
│ Filters: [ All ] [ Thesis ] [ IC ] [ Memo ] [ PASS only ] [ Outcomes ]      │
├──────────────────────────────────────────────────────────────────────────────┤
│ Results List                                 Preview Panel                   │
│ ┌──────────────────────────────┐             ┌────────────────────────────┐ │
│ │ GOOGL  Investment Memo PASS  │             │ GOOGL                      │ │
│ │ 2026-03-28  FV $220          │             │ Summary                    │ │
│ │                              │             │ Full abstract              │ │
│ │ AMZN  Thesis NO_PASS         │             │ Outcome / alpha            │ │
│ │ 2026-03-19  FV $196          │             │ Linked artifacts           │ │
│ │                              │             │ [ Read Memo ] [ Ticker ]   │ │
│ └──────────────────────────────┘             └────────────────────────────┘ │
├──────────────────────────────────────────────────────────────────────────────┤
│ Stats bar: Win rate | Best thesis | Worst thesis | Outcomes tracked         │
└──────────────────────────────────────────────────────────────────────────────┘
```

### Key UX Notes
- Search should eventually support semantic lookup, but the first version can still feel strong if the information hierarchy is right.
- The preview panel should make the library feel alive, not archival.

---

## 6. Ticker Detail (`/ticker/:ticker`)

### Goal
One company, all relevant system judgment in one place.

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ GOOGL                                                        [ Open Memo ]  │
│ One company, full research chain                                            │
├──────────────────────────────────────────────────────────────────────────────┤
│ Judgment Chain                                                               │
│ [ SCREENED ] -> [ THESIS ] -> [ IC PASS ] -> [ MEMO ] -> [ OUTCOME ]        │
├──────────────────────────────────────────────────────────────────────────────┤
│ Thesis                                      IC Review                        │
│ ┌──────────────────────────────┐           ┌──────────────────────────────┐ │
│ │ ExpRet / Discount / FV       │           │ PASS / base / bear / conv    │ │
│ │ Variant view                 │           │ key risk / AI review         │ │
│ └──────────────────────────────┘           └──────────────────────────────┘ │
├──────────────────────────────────────────────────────────────────────────────┤
│ Timeline                                    Library                          │
│ screener run                               research memo                     │
│ thesis generated                           investment memo                   │
│ ic pass                                    archived outputs                  │
└──────────────────────────────────────────────────────────────────────────────┘
```

### Key UX Notes
- This should become the deepest page in the product over time.
- It should feel like a single-name decision workspace, not a thin wrapper around agent logs.

---

## 7. Navigation / Global Shell

```
┌───────────────┬──────────────────────────────────────────────────────────────┐
│ FUNDOPS       │ Job / pipeline activity bar                                 │
│ Personal OS   ├──────────────────────────────────────────────────────────────┤
│               │ Main page content                                            │
│ Home          │                                                              │
│ Screener      │                                                              │
│ Research      │                                                              │
│ IC Review     │                                                              │
│ ───────────   │                                                              │
│ Portfolio     │                                                              │
│ Library       │                                                              │
│ Allocator     │                                                              │
│ ───────────   │                                                              │
│ Settings      │                                                              │
│               │                                                              │
│ [Run Pipeline]│                                                              │
└───────────────┴──────────────────────────────────────────────────────────────┘
```

### Key UX Notes
- Sidebar should feel dense and serious.
- Job bar should feel like system activity, not a toast.
- Home should remain the conceptual center of gravity.

---

## Build Recommendation

If these wireframes feel right, build in this order:

1. Global shell
2. Home / Mirror
3. Screener polish
4. Research page
5. Ticker Detail
6. Library
7. Portfolio
8. Allocator

---

## Questions To Confirm Before Full UI Build

1. Should Home stay a blended page with constitution + behavior + actions, or do you want it even more conversation-heavy after onboarding?
2. Do you want Research and IC Review merged into one page eventually, or kept separate?
3. Should Ticker Detail use tabs, or one long vertically stacked page?
4. Should Library feel more like a terminal table, or more like a research browser with a richer preview pane?
