# FundOps QA Memo
Date: 2026-03-30
Tester: GPT

## Scope and Method
This review was performed against the FundOps project in `the project root` using three sources of evidence:

1. Live backend/API verification against the local FastAPI server on `http://127.0.0.1:8000/api`
2. Frontend source review across the React/Vite app in `frontend/src`
3. Existing browser console and network logs in `.gstack/`

Important limitation:
- I was able to verify live API data and implementation wiring, but I did not have a full interactive browser+DevTools session for manual click-by-click validation of every visual state.
- Where I say a behavior is "likely broken," that is based on code-to-API mismatch or obvious missing handlers.
- Where I say a behavior is "confirmed," that is based on live API responses, explicit code wiring, or existing browser logs.

## Executive Summary
Overall product status is PARTIAL and not launch-ready yet.

The strongest part of the system right now is the backend data pipeline. Real data exists for:
- Dashboard run history
- A 50-stock screener run
- One thesis record for `CALM`
- One IC review record for `CALM`
- Ticker timeline history for `CALM`

The biggest product risk is that several frontend pages present hardcoded sample/demo data instead of true backend state. This is especially serious on:
- Research
- Library
- Allocator

That creates a trust problem: the app can appear populated, functional, and decision-ready when the actual database is empty or only partially populated.

Overall launch recommendation:
- Fail for external launch
- Partial pass for internal demo if positioned clearly as prototype/in-progress

## Environment State Verified
Live backend/API state on 2026-03-30:

- Dashboard recent runs exist
- Screener v2 results exist with `scored_count: 50`
- Thesis list contains 1 row: `CALM`
- IC review list contains 1 row: `CALM`, verdict `no_pass`, base `1.3`, bear `0.4`, conviction `1/5`
- Approved list is empty
- Portfolio is empty
- Library memos are empty
- Allocator has no run yet
- Jobs list is empty
- Ticker detail for `CALM` is sparse, but timeline exists and is rich

## Critical Bugs (must fix before launch)

### 1. Research page shows fake sample data when backend is empty
Severity: Critical

Why this matters:
- This page is core to investment decision flow.
- It currently makes the product look significantly more complete than it is.

What I found:
- `frontend/src/pages/Research.tsx` defines `SAMPLE_THESES`, `SAMPLE_IC`, and `SAMPLE_APPROVED`
- The page uses these fallbacks directly:
  - `data?.results ?? SAMPLE_THESES`
  - `data?.results ?? SAMPLE_IC`
  - `data?.results ?? SAMPLE_APPROVED`
- Tab counts also use fallback sample arrays

Impact:
- Approved tab can show fake approved stocks even though backend returns `{"results":[]}`
- Counts are inflated and not trustworthy
- QA users could incorrectly assume memo generation or approval flow has already produced results

Expected behavior:
- Show true backend data only
- If empty, show empty states

Actual behavior:
- Fake/demo rows are used as if they were real pipeline records

Recommendation:
- Remove sample fallback usage entirely from production code
- Keep sample data only behind an explicit demo/dev flag if needed

### 2. Library page is demo-driven, not data-driven
Severity: Critical

Why this matters:
- Library is supposed to be the archive of generated research
- It currently implies a populated, mature research system when backend memos are empty

What I found:
- `frontend/src/pages/Library.tsx` includes:
  - `SAMPLE_STATS`
  - `SAMPLE_TICKERS`
  - `SAMPLE_MEMO_SECTIONS`
  - `SAMPLE_QA_MESSAGES`
- Browse tab hardcodes `const stats = SAMPLE_STATS`
- Search defaults to `CHKP`
- Ticker detail in Library falls back to `SAMPLE_TICKERS`
- Memo content falls back to fixed sample memo sections
- "Ask the Library" content is sample-driven

Live backend state:
- `/api/library/memos` returns `{"memos":[],"total":0}`

Impact:
- User sees a rich research archive that does not actually exist
- This is likely to mislead product demos and testing
- "Real data vs sample data" is fundamentally broken on this page

Recommendation:
- Replace the sample browse/search experience with true empty states
- Only show a reader if actual memo content exists
- If you want demo content, isolate it behind a dev/demo mode banner

### 3. Allocator page falls back to fake recommendations when allocator has never run
Severity: Critical

Why this matters:
- Allocation recommendations are decision-critical
- Fake trim/add/exit actions are especially dangerous because they look operationally real

What I found:
- `frontend/src/pages/Allocator.tsx` includes large `SAMPLE_DATA`
- Main component uses:
  - `const data: AllocatorData = (raw && Array.isArray(raw.actions_required)) ? raw : SAMPLE_DATA;`

Live backend state:
- `/api/allocator/recommendations` returns `{"actions":null,"message":"No allocator runs yet"}`

Impact:
- Instead of showing an empty allocator state, the page can render realistic sample actions
- A user could believe the system has produced real portfolio actions when it has not

Recommendation:
- Do not fall back to sample allocation data in production
- Interpret missing/empty allocator payload as true empty state
- Consider explicit empty state for "no allocator runs yet"

### 4. Screener lens filtering is wired to the wrong field
Severity: Critical

Why this matters:
- Lens tabs are one of the primary interaction models on Screener
- If broken, filtering and counts are wrong

What I found:
- Frontend expects `r.lens`
- Live backend results use `top_lens`
- Code computes counts and filters with `r.lens?.toLowerCase()`

Live backend sample:
- Screener rows contain `"top_lens":"compounder"` or `"top_lens":"dislocation"`

Impact:
- `Dislocation` and `Compounder` tabs likely show incorrect counts or empty results
- Lens-specific QA expectations fail even though data exists

Recommendation:
- Normalize API shape or map `top_lens` to `lens` in client transform layer

### 5. Dashboard pipeline status uses fields that do not exist in the API payload
Severity: Critical

Why this matters:
- Dashboard is the operational truth center
- Wrong timestamps undermine trust in system status

What I found:
- Dashboard recent runs from `/api/dashboard` contain `run_at`
- `Mirror.tsx` attempts to read `lastPipelineRun.started_at`
- Recent runs card also references `run.started_at`

Impact:
- Last run date can render blank or incorrect
- Recent run dates may not display properly

Recommendation:
- Use `run_at` consistently
- Add a formatter layer so the UI does not depend on inconsistent field naming

## Major Issues (should fix soon)

### 6. Home page route is not the product described in QA instructions
Severity: Major

Expected per QA doc:
- AI investment advisor home page
- Chat knows strategy, recent IC decisions, behavioral patterns, pending proposals

Actual implementation:
- `/` renders `Configure.tsx`
- This is a strategy/configuration conversation page using `api.strategyConversation(...)`
- It is primarily oriented around changing settings and discussing strategy, not operating as the full advisor brain described in the doc

Impact:
- Product reality diverges from QA spec
- Testers and users will experience a different product than described

Recommendation:
- Either update the QA/spec doc to match product reality
- Or implement the advisor-style home page on `/`

### 7. Chat history persistence is fragile and probably resets across remounts
Severity: Major

What I found:
- `Configure.tsx` creates `sessionId` with `configure-${Date.now()}`

Impact:
- If the component remounts, the session id changes
- Previously saved conversation history may no longer be fetched
- This likely breaks the “navigate away and come back” persistence requirement

Recommendation:
- Store stable session id in localStorage or backend profile state

### 8. Dashboard schedules are hardcoded
Severity: Major

What I found:
- In `Mirror.tsx`, Scheduled Runs rows are hardcoded inline
- “Next scheduled” and statuses are not sourced from config/schedule data

Impact:
- Dashboard schedule information can drift from Settings
- QA expectation for real schedule state is not met

Recommendation:
- Read schedule data from backend config
- Reuse the same source that Settings edits

### 9. Screener promote action does not trigger thesis generation as spec requires
Severity: Major

Expected:
- Promote should record feedback and trigger thesis run

Actual:
- `handlePromote` only calls `api.recordFeedback(...)`
- No `api.runThesis(ticker)` call is made

Impact:
- Promote flow is incomplete
- User expects pipeline progression that does not happen

Recommendation:
- Chain feedback record + thesis run
- Show success/loading/error states for both steps

### 10. Screener expanded financial details likely render blank because of field mismatches
Severity: Major

What I found:
- UI expects:
  - `gross_margin`
  - `roic`
  - `revenue_growth`
  - `fcf_yield`
  - `debt_to_equity`
- API returns:
  - `grossProfitMargin`
  - `returnOnInvestedCapital`
  - `revenueGrowth`
  - `fcfYield`
  - `debtEquity`

Impact:
- Expanded row looks sparse or broken despite data being present

Recommendation:
- Map API fields into view model before rendering

### 11. Research page contains several non-functional action buttons
Severity: Major

What I found:
- `Override` and `Dismiss` buttons exist on thesis/no-pass flows
- Equivalent buttons exist in expanded IC view
- They do not call any mutation or handler

Impact:
- UI suggests actions that do nothing

Recommendation:
- Wire these buttons to real backend actions or hide them until implemented

### 12. Research thesis row data shape does not align cleanly with backend output
Severity: Major

What I found:
- Live thesis API for `CALM` returns `conviction: "LOW"`
- UI expects numeric `conviction/conviction_max`
- Several detail sections assume richer structured fields that may be absent

Impact:
- Rows may show odd or missing values even when live thesis exists

Recommendation:
- Standardize thesis response schema
- Avoid mixing narrative payloads with rigid table assumptions unless normalized

### 13. Portfolio editor and CSV import are UI-only
Severity: Major

What I found:
- Save Changes in `PositionEditor` only calls `onClose`
- Upload CSV button exists without import logic
- Sync flow is visually present but does not persist

Impact:
- Portfolio import/update flow is incomplete
- User cannot actually load holdings from the UI

Recommendation:
- Implement backend mutation for portfolio sync
- Wire manual entry and CSV upload to real persistence

### 14. Settings quick presets likely do nothing
Severity: Major

What I found:
- Buttons exist for:
  - Minimal
  - Recommended
  - Active trader
- No handler is attached to apply schedule presets

Impact:
- Prominent controls appear interactive but are non-functional

Recommendation:
- Add preset handler and persist through config save

### 15. Ticker detail page has live timeline but insufficient live detail payload
Severity: Major

What I found:
- `/api/ticker/CALM` returns only `{"ticker":"CALM","pipeline":{}}`
- `/api/ticker/CALM/timeline` is rich and usable
- The page expects more metrics/detail than currently provided by the detail endpoint

Impact:
- Overview/research/health tabs likely feel empty or underpowered

Recommendation:
- Enrich ticker detail API or reduce page expectations to current payload

### 16. Library reader does not implement requested section navigation
Severity: Major

Expected:
- Previous section / Next section buttons
- Section navigation dots

Actual:
- Reader popup supports close only
- Raw JSON expansion exists in browse cards
- No previous/next section navigation located

Impact:
- Reader experience is less usable than specified

Recommendation:
- Add section index and navigation controls to memo reader

## Minor Issues

### 17. Several labels differ from the QA instructions
Severity: Minor

Examples:
- Portfolio empty state says `Add your portfolio` instead of `No portfolio data`
- Button says `Sync Positions` instead of `Sync Portfolio`
- Refresh button says `Refresh Prices` instead of `Refresh Portfolio`

Impact:
- Mostly copy/spec mismatch, not functional breakage

### 18. Screener action set does not match QA doc exactly
Severity: Minor

What I found:
- Current actions are expand, promote, dismiss
- QA doc expected three specific action icons/behaviors including a promote-with-thesis behavior distinction

Impact:
- Functional mismatch between product and spec

### 19. Dismiss reason list differs from spec
Severity: Minor

Expected examples:
- Poor quality
- Not cheap enough
- Value trap
- Wrong sector

Actual reasons include:
- Too much debt
- Cyclical/commodity business
- Management concerns
- Too small / too large

Impact:
- Mostly a product alignment issue

### 20. `index.html` title is still generic
Severity: Cosmetic

What I found:
- `frontend/index.html` title is `frontend`

Recommendation:
- Change to `FundOps`

### 21. Existing console logs show React style warnings
Severity: Minor

From `.gstack/browse-console.log`:
- React warns about mixing `border` and `borderBottom` during rerender

Impact:
- Not necessarily user-breaking
- Should still be cleaned up because it can cause inconsistent styling

### 22. Existing dev console/network logs show transient dev errors
Severity: Minor to Major depending on recurrence

Observed in logs:
- Vite/HMR 500 reload failures on `Mirror.tsx`
- Some 502 Bad Gateway responses during prior browsing session

Impact:
- May have been transient dev-time issues
- Worth retesting in a clean browser session before launch

## Findings by Page

### Chat (`/`)
Status: PARTIAL
Real Data: Partial

Working:
- North star text is driven by live strategy data
- Agent overlay open/close logic appears correct
- Only one overlay should be open at a time
- Chat sends strategy conversation requests to backend

Issues:
- This is not the advisor-style chat described in the QA instructions
- Overlay contents are mostly hardcoded/static configuration content
- Session persistence is unstable due to timestamp-based session id

Verdict:
- Works as a strategy/configuration chat
- Does not fully match documented product role

### Dashboard (`/mirror`)
Status: PARTIAL
Real Data: Partial

Working:
- Uses live strategy presence to determine page mode
- Pulls live dashboard/recent events/proposals/constitution data
- Portfolio empty-state CTA to Settings exists
- Recent Agent Runs is sourced from real API history

Issues:
- Pipeline timestamps likely broken due to wrong field names
- Schedule section is hardcoded
- “Next scheduled” / status text are not truly live

Verdict:
- Useful as an operational snapshot
- Not fully trustworthy for schedule/status accuracy yet

### Screener (`/screener`)
Status: PARTIAL
Real Data: Yes

Working:
- Live screener v2 data exists and is queried
- Run Screener mutation is wired
- Feedback mutation for promote/dismiss is wired
- Dismiss modal exists

Issues:
- Lens counts/filtering likely broken due to `lens` vs `top_lens`
- Expanded metrics likely blank due to field-name mismatch
- Promote does not run thesis
- Run Thesis button does not show proper job/success state

Verdict:
- Core page is close, but important data-mapping and workflow steps are incomplete

### Research (`/research`)
Status: FAIL
Real Data: Partial

Working:
- Live thesis and IC queries exist
- Run IC Review mutation is wired
- Approved report/memo generation mutations are wired

Issues:
- Sample fallback corrupts all three tabs
- Counts are not trustworthy
- Override/Dismiss actions are non-functional
- Live thesis schema does not cleanly fit the UI contract

Verdict:
- This page should not ship until sample fallbacks are removed

### Portfolio (`/portfolio`)
Status: PARTIAL
Real Data: Yes

Working:
- Real empty state can be reached from true empty backend
- Sync panel/editor UI exists
- Refresh portfolio mutation is wired

Issues:
- Manual save is not implemented
- CSV upload is not implemented
- Flow is visually convincing but not operational

Verdict:
- Good shell, incomplete actual sync/import behavior

### Library (`/library`)
Status: FAIL
Real Data: No

Working:
- UI is rich and thoughtfully designed
- Reader popup component is implemented

Issues:
- Almost the entire current experience is sample-driven
- Does not reflect actual memo/archive state
- Missing requested section navigation

Verdict:
- Strong prototype/demo page, not an accurate production library

### Allocator (`/allocator`)
Status: FAIL
Real Data: No

Working:
- Policy modal exists
- Run Allocator mutation is wired

Issues:
- Empty backend state is masked by sample action data
- Recommendation cards are misleading when allocator has never run

Verdict:
- Must remove sample fallback before launch

### Settings (`/settings`)
Status: PARTIAL
Real Data: Partial

Working:
- Data Sources tab has test/save logic
- AI Model tab save/test logic is implemented
- Schedule edit/save and pause/resume appear wired
- System tab has autonomy mode and export actions

Issues:
- Quick presets likely do nothing
- Danger zone behavior is narrower than a true “reset database” expectation
- Some system/schedule values rely on defaults

Verdict:
- Best-wired admin page in the app, but still has incomplete controls

### Sidebar Navigation
Status: PARTIAL
Real Data: Partial

Working:
- Nav structure matches app routing
- Active state styling is implemented
- Run Pipeline button exists with running/starting states

Issues:
- “Chat” routes to configuration page rather than advisor-style home

Verdict:
- Functionally solid, but route meaning differs from spec

### Ticker Detail (`/ticker/:ticker`)
Status: PARTIAL
Real Data: Partial

Working:
- Route exists
- Timeline endpoint has real historical entries for `CALM`

Issues:
- Main ticker detail payload is too sparse
- Page likely renders partial/empty sections because backend detail contract is thin

Verdict:
- Timeline is promising, but page data model is incomplete

## Real Data Status Table

| Page | Using Real Data? | Notes |
|------|------------------|-------|
| Chat | Partial | Strategy is live, but chat is config-oriented and overlays are mostly static |
| Dashboard | Partial | Recent runs/events are live; schedule/status sections are partly hardcoded |
| Screener | Yes | Live 50-stock dataset, but field mapping issues likely break filters/details |
| Research | Partial | Live thesis/IC exist, but sample fallback contaminates all tabs |
| Portfolio | Yes | Real empty state from backend |
| Library | No | Sample stats, sample ticker files, sample memos |
| Allocator | No | Sample recommendation fallback masks true empty backend state |
| Settings | Partial | Config is live; some sections rely on defaults and some controls are incomplete |
| Ticker Detail | Partial | Timeline is live, detail payload is sparse |

## Evidence Snapshot

### Confirmed live API facts
- `/api/dashboard` shows real screener, thesis, ic_review, and pipeline history
- `/api/screener/v2/results` returns 50 scored rows and `run_id`
- `/api/thesis` returns one thesis for `CALM`
- `/api/ic-review` returns one IC review for `CALM`
- `/api/research/approved` returns empty list
- `/api/portfolio` returns empty holdings
- `/api/library/memos` returns empty list
- `/api/allocator/recommendations` returns `No allocator runs yet`
- `/api/ticker/CALM/timeline` returns populated historical records

### Notable console/network evidence from existing logs
- React style warning about shorthand/non-shorthand border mixing
- Prior Vite HMR failures for `Mirror.tsx`
- Some 502 responses in earlier local browsing session

## What’s Working Well
- Backend pipeline data is real and internally coherent
- The app structure/routes are clean and understandable
- Dashboard, Screener, and Settings have the most real product substance
- Ticker timeline/history model is a strong foundation
- UI styling/system consistency is generally good

## Recommended Fix Order

### Highest priority
1. Remove sample fallbacks from Research
2. Remove sample fallbacks from Library
3. Remove sample fallbacks from Allocator
4. Fix Screener field mapping (`top_lens`, metric names)
5. Fix Dashboard date/status field usage

### Next priority
6. Make Screener promote trigger thesis
7. Implement Portfolio save/import
8. Wire Research override/dismiss actions
9. Stabilize chat session persistence
10. Enrich ticker detail API

### Lower priority
11. Wire Settings quick presets
12. Align copy/labels to spec
13. Clean React style warnings
14. Update document title and polish minor UX mismatches

## Final Verdict
FundOps has a real backend core and several strong UI foundations, but the frontend is currently mixing real investment data with demo/sample content in a way that makes the product materially misleading.

If this were positioned as:
- an internal prototype: acceptable with caveats
- a user-facing launch: not ready

The single biggest theme is trust. Before launch, the UI needs to become strictly honest about what data is real, what is empty, and what is not implemented yet.
