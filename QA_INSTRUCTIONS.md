# FundOps QA Instructions — Full Product Review

## What This Is

FundOps is a personal investment operating system modeled after a hedge fund. It has 7 AI agents that run a pipeline: Screener → Thesis → IC Review → Library → Portfolio → Allocator. The frontend is a React app. The backend is a FastAPI server.

**Access the app at:** `http://localhost:5173`
**Backend API at:** `http://localhost:8000/api`

You are a QA tester. Your job is to test every page, every button, every tab, every interactive element. For each item, note:
- Does it work as expected?
- Does it show real data or sample/placeholder data?
- Is there anything broken, missing, visually wrong, or confusing?

Write a structured memo with findings organized by page.

---

## HOW THE SYSTEM WORKS (Context for QA)

The pipeline flows: **Screener** (finds cheap quality stocks) → **Research** (thesis + IC gate) → **Library** (stores memos) → **Portfolio** (tracks held positions) → **Allocator** (sizes positions).

The **Chat** page is the AI brain you talk to. It knows your investment constitution (who you are as an investor) and learns from your decisions over time.

The **Dashboard** is ops status — when things ran, what's scheduled, what needs attention.

---

## PAGE 1: CHAT (`/`)

**What it is:** The home page. An AI chat interface where you talk to your investment advisor AI. The AI knows your strategy, your recent IC decisions, behavioral patterns, and pending proposals from the learning loop.

**Left panel (Agent Strip):**
- **ME chip** — Your investment constitution. Click it. A slide-out overlay should appear showing:
  - MUST-HAVE SIGNALS (pills like "High ROIC", "FCF positive", "Revenue growth")
  - ANTI-SIGNALS (pills like "Earnings driven by multiple expansion", "Cyclical re-rating")
  - IC HURDLES (rows: Base return hurdle 20%, Bear return hurdle 15%, Haircut 70%)
  - DISCOUNT FLOORS (rows: High-growth compounder 15%, Moderate-growth 20%, Steady-state 30%)
  - Footer text: "Tell the AI to change any setting. Close to return to chat."
  - **Check:** Does clicking ME open the overlay? Does clicking outside close it?

- **SC chip (Screener)** — Click it. Overlay should show:
  - SCORING WEIGHTS bar chart (Quality, Cheapness, Growth with percentages)
  - HANDOFF FILTERS (Min expected return 20%, Min gross margin, Max D/E, Max candidates)
  - LENSES pills (Dislocation, Compounder)
  - **Check:** Opens and closes correctly?

- **TH chip (Thesis)** — Click it. Overlay should show:
  - FOCUS AREAS pills
  - DEPTH/TONE rows
  - **Check:** Opens and closes correctly?

- **IC chip (IC Review)** — Click it. Should show IC hurdles and scoring config.

- **LB chip (Library)** — Click it. Should show what Library stores/indexes.

- **PF chip (Portfolio)** — Click it. Should show what Portfolio monitors.

- **AL chip (Allocator)** — Click it. Should show sizing policy info.

**Only one overlay should be open at a time.** Clicking a different chip should close the current one and open the new one.

**North Star bar (top center):**
- Should show a one-sentence investment goal in accent color (amber/gold)
- Example: "Buy quality businesses at a meaningful discount to intrinsic value and hold for 3-5 years"
- **Check:** Is it showing? Is it centered? Correct font?

**Chat area (right panel):**
- Text input at the bottom with a send button (paper plane icon or "Send")
- Try typing: "Hello, what's my investment strategy?" and pressing Enter or clicking Send
- The AI should respond conversationally about your strategy
- Try: "What patterns have you noticed in my decisions?" — AI should reference behavioral learning context
- Try: "What does my screener weight quality at?" — AI should reference actual screener config
- Messages should appear in order: your message (right-aligned or labeled "You"), AI response (left or labeled "AI")
- **Check:** Does the chat work? Do messages appear? Does the AI respond? Does the conversation history persist if you navigate away and come back?

---

## PAGE 2: DASHBOARD (`/mirror`)

**What it is:** Operations center. Shows pipeline status, portfolio KPIs, recent agent runs, scheduled runs, what needs attention, and the learning loop status (behavioral analysis, proposals).

**Top section:**
- Section label "DASHBOARD", title "Operations", subtitle text
- **Check:** Is the page heading visible?

**Portfolio KPIs card:**
- If no portfolio imported: shows "Import your portfolio to see P&L, thesis health, and action items." with a "Go to Settings" button
- If portfolio exists: shows PORTFOLIO (total value), P&L (total return %), POSITIONS (count), THESIS HEALTH (weighted avg score)
- **Check:** Does "Go to Settings" link work? Does it navigate to /settings?

**Pipeline Status card:**
- Shows: Last full run (date), Next scheduled (e.g. "Sun 8:00 AM"), Status ("Idle" or "Running")
- **Check:** Is real data showing (dates from actual pipeline runs)?

**Recent Agent Runs card:**
- Table showing up to 8 recent runs: agent name (colored), ticker/message, status (completed/failed), date
- Agent names: screener, thesis, ic_review, pipeline
- **Check:** Is real data showing? Are runs listed?

**Scheduled Runs card:**
- Table: Agent | Frequency | Next Run | Status
- Rows: Screener (Weekly), Portfolio (Daily), Outcome Checker (Daily), Library Sync (Weekly), Full Pipeline (Weekly/Paused)
- "Manage schedules →" link in bottom right — should navigate to /settings
- **Check:** Does the link work?

**Your Attention / Proposals Queue (two-column):**
- Left: "Your Attention" — shows IC-passed tickers with conviction score and base return. Empty state: "No recent attention items. Run the screener or pipeline."
- Right: "Proposals Queue" — shows pending learning proposals labeled BEHAVIORAL or PATTERN. Empty state explains what triggers proposals.
- **Check:** Renders without crashing?

**Said vs Did card:**
- If fewer than 5 IC decisions: shows a progress bar (X/5) and explanation that behavioral insights unlock at 5 decisions
- If 5+ decisions: shows Signal Drift table and Anti-Signal Breaches table
- **Check:** Progress bar is visible? Shows correct count?

**Approval Profile card:**
- Only appears with 5+ IC decisions
- Shows pass/fail counts, mean conviction, range bars for base/bear returns
- **Check:** Hidden when not enough data?

**Constitution Evolution card:**
- Only appears if constitution has been updated at least once (has changelog entries)
- Timeline of changes with colored dots (behavioral = info color, conversation = accent)
- **Check:** Hidden when no changelog?

---

## PAGE 3: SCREENER (`/screener`)

**What it is:** The AI stock screener. Shows scored stocks from the last screener run. Each stock can be promoted to thesis or dismissed.

**Top bar:**
- "Run Screener" button (top right, accent color)
- Clicking it should trigger a screener run (async job). A job status bar/indicator should appear.
- While running: button may disable or show a loading state
- **Check:** Does clicking Run Screener work? Does it show a running indicator?

**Empty state (no runs yet):**
- Shows "No screener runs yet" with a Run Screener button and explanation text
- **Check:** Is this shown when appropriate?

**Results view (after runs):**
- "X scored" subtitle showing how many stocks were scored
- Tab bar: ALL (X) | Dislocation (X) | Compounder (X) — X = count of stocks in each lens
- "Top 20 Picks" section label
- **Check:** Tab switching works? Each tab shows filtered subset?

**Stock rows:**
- Columns: # | TICKER | COMPANY | SECTOR | PRICE | SCORE | QUALITY | CHEAPNESS | GROWTH | RETURN | ACTIONS
- TICKER shown in accent color (clickable link to /ticker/{ticker})
- **Expand row:** Click anywhere on the row (not the ticker link or action buttons) to expand it
  - Expanded view shows: Scoring breakdown, Return sources (Discount/Growth/Margin/Dividends), "Run Thesis" button
  - **Check:** Does expansion work? Does "Run Thesis" button appear?

- **Action buttons (3 icons in ACTIONS column):**
  - ▶ (Play/arrow) — Promote to thesis. Should fire POST /screener/v2/feedback with feedback="promoted" and POST /thesis/{ticker}. A brief success indicator should appear.
  - ✓ (green circle) — Same as promote? Or just promote without thesis run. Check behavior.
  - ✗ (red circle) — Dismiss. Should open the Dismiss Modal.
  - **Check:** Do all three buttons respond to clicks?

- **Dismiss Modal:**
  - Appears when clicking the dismiss button
  - Shows list of dismiss reason buttons: "Poor quality", "Not cheap enough", "Value trap", "Wrong sector", "Needs more research", "Overvalued", "High debt"
  - Text input for custom dismiss reason
  - Clicking a reason button OR submitting custom reason should dismiss the stock and close modal
  - **Check:** Modal opens? Reason buttons work? Custom input works? Modal closes after dismiss?

- **Run Thesis button** (inside expanded row):
  - Should trigger POST /thesis/{ticker}
  - Should show some kind of loading/success state
  - **Check:** Does it respond?

**Job tracker (while screener is running):**
- Progress indicator showing job ID and status
- "Dismiss" button to hide the tracker
- **Check:** Appears when job is submitted? Disappears on completion or dismiss?

---

## PAGE 4: RESEARCH (`/research`)

**What it is:** Three-tab pipeline view showing all tickers at different stages: Thesis written → IC Review done → Approved (IC passed, ready for memos).

**Tab bar:** Thesis (X) | IC Review (X) | Approved (X)
- Counts should be dynamic (reflecting real data, not hardcoded 12/8/5)
- **Check:** Do tab counts match actual data? Tab switching works?

### Thesis tab

**Stock rows:**
- Columns: TICKER | COMPANY | FAIR VALUE | EXPECTED RETURN | DISCOUNT | IC VERDICT | CONVICTION | WHY IT EXISTS | NEXT STEP
- IC VERDICT shown as pill: green "PASS", red "NO PASS", gray "PENDING"
- CONVICTION shown as "X/5"
- WHY IT EXISTS: short text explaining why the stock is cheap
- NEXT STEP column: "Run IC Review" button (if no IC yet) or "Override" / "Dismiss" buttons (if IC done)
- Clicking on a row should expand it showing Thesis Narrative, Web Research Note, Constitution Criteria (met/not met), Anti-signals, Similar tickers, Valuation details
- **Check:** Rows show real data? Expansion works? Buttons in NEXT STEP column work?

- **Run IC Review button:**
  - Triggers POST /ic-review/{ticker}
  - Should show running state
  - **Check:** Does it respond?

- **Override button:**
  - What does it do? Overrides IC verdict? Check behavior.

- **Dismiss button:**
  - Should dismiss the thesis from the pipeline
  - **Check:** Does it work?

### IC Review tab

**Stock rows:**
- Columns: TICKER | VERDICT | BASE RETURN | BEAR RETURN | CONVICTION | KEY RISK | SCORECARD
- Expanded view shows: detailed IC scorecard (criteria met/not met), anti-signal breakdown, full AI IC review text, key assumptions to monitor
- **Check:** Real data showing? CALM should appear with NO_PASS verdict, 1.3% base return, 0.4% bear return, conviction 1/5

### Approved tab

**Stock rows:**
- Only shows IC-PASSED tickers
- Columns: TICKER | APPROVED DATE | EXPECTED RETURN | CONVICTION | RESEARCH REPORT | INVESTMENT MEMO
- Two action buttons per row:
  - "Research Report" — triggers POST /research/report/{ticker} — full ~$1 deep dive
  - "Investment Memo" — triggers POST /research/memo/{ticker} — constitution-adapted memo
- Both show estimated cost (e.g., "$1.00")
- Empty state if no tickers have passed IC: "No tickers have passed IC review yet."
- **Check:** Empty state shows correctly? Buttons work when tickers exist?

---

## PAGE 5: PORTFOLIO (`/portfolio`)

**What it is:** Tracks your held positions. Shows P&L, thesis health, key assumptions to monitor, and alert-worthy items.

**Empty state (no portfolio):**
- Shows "No portfolio data" message
- "Sync Portfolio" button — opens a sync/import flow
- **Check:** Empty state visible? Button appears?

**Sync flow:**
- Clicking "Sync Portfolio" should open a modal or panel
- Allows importing positions via:
  - Manual entry (ticker, shares, cost basis)
  - CSV upload
  - "Save Changes" and "Cancel" buttons
- **Check:** Does the modal open? Can you add a row? Upload CSV button visible?

**Portfolio loaded state:**
- "Refresh Portfolio" button (ghost) — triggers POST /portfolio/run to update prices/health
- "Sync Portfolio" button (accent) — opens import modal to update positions
- Holdings table: TICKER | COMPANY | SHARES | COST BASIS | CURRENT PRICE | RETURN | THESIS HEALTH | ALERT
- Clicking a ticker navigates to /ticker/{ticker} detail page
- **Check:** Buttons respond? Table renders?

**Alert items:**
- If any positions have thesis health concerns, they appear in an alerts section
- **Check:** Alerts section present? (may be empty with no positions)

---

## PAGE 6: LIBRARY (`/library`)

**What it is:** The research archive. Every memo the system generates lives here. Three tabs: Browse (all memos), Search (find by ticker/keyword), and a timeline view.

**Tab bar:** Browse | Search | (possibly a third tab)
- Tab switching should work
- **Check:** Tab switching works?

### Browse tab
- List of memos with ticker, date, summary snippet
- Empty state: "No memos yet. Generate research reports from the Approved tab."
- Clicking a memo opens a reader view
- **Check:** Empty state visible? Reader popup works if memos exist?

### Search tab
- Text input to search by ticker or keyword
- Results appear as the user types (or on submit)
- Empty search should show all or nothing
- **Check:** Input is interactive? Results update?

**Memo reader (if memos exist):**
- Popup or slide-out showing full memo
- Navigation: Previous section / Next section buttons
- Section dots/indicators in sidebar
- Raw JSON toggle button (shows underlying data)
- Close button to dismiss
- **Check:** Navigation buttons work? Close works? Raw toggle works?

---

## PAGE 7: ALLOCATOR (`/allocator`)

**What it is:** Position sizing recommendations. Shows what to buy, hold, trim, or exit based on return profiles and your allocation policy.

**Empty state (no allocator run):**
- Shows "No allocation data" with explanation
- "Run Allocator" button (accent color)
- "View Policy" button (ghost) — should open a policy modal/popup
- **Check:** Both buttons visible? View Policy button opens a popup showing sizing thresholds?

**Policy modal (from "View Policy" button):**
- Should show: Max position size %, concentration limit, trim triggers, position types (tactical/core/balanced)
- Closes when clicking X or outside
- **Check:** Modal opens? Content shows? Closes correctly?

**Allocator with data (after a run):**
- Actions Required section: list of tickers with recommended action (BUY, TRIM, EXIT, HOLD)
- Each action card shows: ticker, current weight, target weight, return profile, reasoning
- "Discuss with AI" button on each card — should trigger the Chat page or an inline chat
- Position summaries section
- **Check:** Cards render? Buttons respond?

**Run Allocator button:**
- Should trigger POST /allocator/run
- Shows loading state while running
- **Check:** Button works? Loading state appears?

---

## PAGE 8: SETTINGS (`/settings`)

**What it is:** Configuration for all data sources, AI model, schedules, and system settings.

**Tab bar:** Data Sources | AI Model | Schedule | System
- **Check:** All 4 tabs switch correctly?

### Data Sources tab

**SEC EDGAR section:**
- Status indicator (Connected / Not Connected) with a green/red dot
- "Test Connection" button — calls GET /api/config/test-connection?source=sec — should show "Connected" or error
- **Check:** Test button works? Status updates?

**FMP (Financial Modeling Prep) section:**
- Status indicator
- "Test Connection" button
- API key input field (type to enter a key)
- "Save" button — saves the FMP key
- **Check:** Input is editable? Save responds? Test works?

**yFinance section:**
- Status indicator
- "Test Connection" button
- **Check:** Works?

**AI Model section (quick link or within Data Sources):**
- Status indicator for AI connectivity
- "Test Connection" button
- **Check:** Works?

### AI Model tab

**Provider selection:**
- Radio options: OpenAI, Anthropic, Groq, Ollama (local), Custom
- Clicking a radio option should select it (visual highlight on selected)
- **Check:** Radio selection works? Only one active at a time?

**Model dropdown:**
- After selecting provider, a dropdown or text input shows available models
- Should be interactive
- **Check:** Dropdown works?

**API Key input:**
- Masked text input for the API key
- **Check:** Is it editable?

**Base URL (for custom/Ollama):**
- Text input for custom API endpoint
- Only shown for Ollama or Custom provider
- **Check:** Conditionally shown?

**Save button:**
- Should save the AI model configuration
- **Check:** Button responds?

**Test Connection button:**
- Should call the backend and verify the API key works
- **Check:** Works? Shows success/error?

**Budget inputs:**
- Monthly budget ($) input
- Warning threshold ($) input
- **Check:** Inputs are editable?

### Schedule tab

**Agent schedule cards (7 agents):**
Each card shows: Agent name, description, frequency, next run, cost estimate, status badge (ACTIVE/PAUSED/MANUAL)

Agents: Screener, Portfolio Monitor, Outcome Checker, Library Sync, Full Pipeline, Thesis Batch, Memo Generation

**Per-card interactions:**
- Status badge color: ACTIVE = green, PAUSED = amber, MANUAL = muted
- "Edit" button (or inline toggle to edit mode):
  - Frequency dropdown: Daily / Weekly / Monthly / Manual
  - Time input (HH:MM format)
  - "Save" to confirm, "Cancel" to discard
- "Pause" button → changes agent status to PAUSED, button becomes "Resume"
- "Resume" button → changes agent status back to ACTIVE
- **Check:** Edit mode works? Frequency dropdown options appear? Time input is editable? Save/Cancel work? Pause/Resume toggle works?

**Quick presets section (bottom of tab):**
- "Minimal" preset button — sets conservative schedule (weekly screener, manual everything else)
- "Recommended" preset button — sets suggested schedule
- "Active trader" preset button — sets aggressive schedule (daily everything)
- **Check:** All three buttons respond? Do they update the agent cards?

### System tab

**Database stats:**
- Shows counts (total runs, events, strategies, etc.)
- **Check:** Stats are visible?

**Danger zone:**
- "Reset Database" or similar destructive action (if present)
- Should require confirmation
- **Check:** Is there a confirmation step?

---

## SIDEBAR NAVIGATION

The left sidebar is present on all pages.

**Top:**
- "FUNDOPS" logo (text)
- "PERSONAL INVESTMENT OS" subtitle
- **Check:** Visible on all pages?

**Nav items:**
- Chat (/) — home icon "AI"
- Dashboard (/mirror) — icon "DB"
- --- separator ---
- Screener (/screener) — icon "SC"
- Research (/research) — icon "RS"
- Portfolio (/portfolio) — icon "PF"
- Library (/library) — icon "LB"
- Allocator (/allocator) — icon "AL"
- --- separator ---
- Settings (/settings) — icon "ST"

**Active state:** The current page's nav item should have:
- Amber/gold text color
- Amber border (1px solid var(--accent-strong))
- Slight amber background glow
- **Check:** Active state shows correctly on each page?

**Bottom:**
- "Run Pipeline" button (full width, amber/accent)
  - Triggers the full pipeline: Screener → Thesis → IC Review for top candidates
  - While running: button shows "● Running..." and is disabled
  - Starting state: shows "Starting..." for ~3 seconds
  - If pipeline job is running: sidebar shows "X jobs active" counter below the button
  - **Check:** Button works? Running/Starting states appear? Job counter shows?

---

## TICKER DETAIL PAGE (`/ticker/:ticker`)

Accessible by clicking any ticker link throughout the app (orange ticker symbols).

**Check:**
- Does clicking a ticker link navigate to the ticker page?
- Does the page load without crashing?
- Shows runs/timeline for that ticker (thesis, IC review, etc.)?

---

## GLOBAL BEHAVIORS TO CHECK

1. **Navigation:** Every sidebar link navigates to the correct page without a full page reload (SPA behavior)
2. **Loading states:** Pages that fetch data should show a loading indicator while fetching
3. **Error states:** If an API call fails (e.g., backend is down), does the page show an error gracefully or just show sample data?
4. **Sample data vs real data:** Some pages show sample/placeholder data when real data is empty. Note which pages are showing sample data and which are showing real data.
5. **Responsiveness:** Is the layout intact at standard browser widths? Does anything overflow or break?
6. **Console errors:** Open browser DevTools (F12) → Console. Are there any red JavaScript errors? List them.

---

## MEMO FORMAT REQUESTED

Please write your findings as a structured QA memo with the following format:

```
# FundOps QA Memo
Date: [today]
Tester: [your name/GPT]

## Executive Summary
[2-3 sentences: overall quality, major issues found, overall pass/fail]

## Findings by Page

### [Page Name]
**Status:** PASS / PARTIAL / FAIL
**Real Data:** Yes / No / Partial
**Issues Found:**
- [issue description] — [severity: Critical/Major/Minor/Cosmetic]
...
**Notes:** [anything else]

## Critical Bugs (must fix before launch)
- [list]

## Major Issues (should fix soon)
- [list]

## Minor / Cosmetic Issues
- [list]

## What's Working Well
- [list]

## Real Data Status
| Page | Using Real Data? | Notes |
|------|-----------------|-------|
| Chat | Yes/No/Partial | ... |
...
```

---

## TIPS FOR TESTING

- The app runs at `http://localhost:5173` — open this in your browser
- Open DevTools Console (F12) to catch JS errors
- The backend is at `http://localhost:8000/api` — you can test endpoints directly
- There is currently 1 ticker (CALM - Cal-Maine Foods) that has gone through Screener + Thesis + IC Review (result: NO_PASS)
- The screener has 50 stocks from the last run
- No positions are currently held in the portfolio
- No memos have been generated yet
- There is 1 IC decision (CALM, NO_PASS) — behavioral learning unlocks at 5 decisions
