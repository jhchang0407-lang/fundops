# Design System — FundOps

## Product Context
- **What this is:** AI-native hedge fund operations platform. The AI runs the investment pipeline continuously. The PM intervenes at decision points.
- **Who it's for:** Solo/small fund PMs (1-3 person teams) running concentrated value portfolios
- **Space/industry:** Investment research and portfolio management. Peers: Bloomberg Terminal, Koyfin, FactSet
- **Project type:** Web app (dashboard + AI conversation + data-dense tables)
- **Key differentiator:** AI-first. Every other tool is a data terminal where humans query data. FundOps is "human-augmented AI workflow" where AI drives and humans decide.

---

## Aesthetic Direction
- **Direction:** Industrial/Utilitarian + AI-native
- **Decoration level:** Intentional. Minimal chrome on data surfaces. Frosted glass treatment on AI interaction surfaces.
- **Mood:** Bloomberg's data density meets Linear's polish. Dark, calm, trustworthy, but alive where the AI is working. If it moves, the AI is doing something.
- **Anti-patterns:** No playful illustrations. No emoji as design elements. No purple gradients. No SaaS card grids. No generic hero sections. Not a marketing site.
- **Reference sites:** [Linear](https://linear.app) (dark theme, density), [Koyfin](https://koyfin.com) (terminal-style finance UI), Bloomberg Terminal (data-first)

---

## Typography

```css
/* Display: Geist for headings and hero KPIs — subtle warmth without losing technical feel */
--font-display: 'Geist', -apple-system, BlinkMacSystemFont, sans-serif;

/* UI: Inter for body text — proven readable at small sizes, data-dense contexts */
--font-ui: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;

/* Data: JetBrains Mono for numbers, tickers, financial data — monospace for alignment */
--font-data: 'JetBrains Mono', 'SF Mono', 'Fira Code', monospace;
```

### Loading
Google Fonts CDN: `https://fonts.googleapis.com/css2?family=Geist:wght@400;500;600;700&family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500;600&display=swap`

### Scale
```css
--text-xs: 0.6875rem;   /* 11px - labels, timestamps, badge text */
--text-sm: 0.8125rem;   /* 13px - secondary text, table cells */
--text-base: 0.875rem;  /* 14px - body text (intentionally dense) */
--text-lg: 1rem;        /* 16px - section headers */
--text-xl: 1.25rem;     /* 20px - page titles (Geist 600) */
--text-2xl: 1.375rem;   /* 22px - secondary KPIs */
--text-3xl: 2rem;       /* 32px - hero KPIs, portfolio value (Geist 700) */
```

### Typography Rules
- ALL financial numbers use `--font-data` (monospace)
- ALL tickers use `--font-data`, uppercase, letter-spacing: 0.05em
- Page titles use `--font-display` at `--text-xl`, font-weight: 600
- Hero KPIs use `--font-display` at `--text-3xl`, font-weight: 700
- Body text uses `--font-ui` at `--text-base` (14px, intentionally dense)
- Section headers use `--font-data` at `--text-xs`, uppercase, letter-spacing: 0.08em, `--text-muted`
- Labels and timestamps use `--font-data` at `--text-xs`

---

## Color

### Approach
Restrained with semantic purpose. Single accent color (amber). AI surfaces get a distinct blue-shifted background.

```css
:root {
  /* Backgrounds */
  --bg-primary: #0a0a0f;        /* Main background - near black with subtle blue */
  --bg-secondary: #12131a;      /* Cards, panels, sidebar */
  --bg-tertiary: #1a1b24;       /* Hover states, active items, input backgrounds */
  --bg-elevated: #22232e;       /* Modals, dropdowns, tooltips, toasts */
  --bg-ai: #141520;             /* AI conversation panels - slightly blue-shifted */
  --bg-ai-glass: rgba(20, 21, 32, 0.85); /* Frosted glass AI surfaces */

  /* Text */
  --text-primary: #e8eaed;      /* Primary text - high contrast */
  --text-secondary: #9aa0a6;    /* Secondary text, descriptions */
  --text-muted: #5f6368;        /* Disabled, placeholder, timestamps */

  /* Accent - single accent color: amber/gold (money, finance) */
  --accent: #f5a623;            /* Primary accent - warm amber */
  --accent-muted: #c4841d;      /* Accent hover/pressed */
  --accent-subtle: rgba(245, 166, 35, 0.12); /* Accent backgrounds, active tabs */
  --accent-pulse: rgba(245, 166, 35, 0.20);  /* AI working pulse animation */

  /* Semantic */
  --positive: #34a853;          /* Gains, PASS, healthy, connected */
  --negative: #ea4335;          /* Losses, NO_PASS, alerts, errors */
  --warning: #fbbc04;           /* Warnings, approaching limits */
  --info: #4285f4;              /* Informational, links, thesis events */

  /* Borders */
  --border: #2a2b36;            /* Default border */
  --border-hover: #3a3b46;      /* Border on hover */

  /* Shadows */
  --shadow-sm: 0 1px 2px rgba(0,0,0,0.3);
  --shadow-md: 0 4px 12px rgba(0,0,0,0.4);
  --shadow-lg: 0 8px 24px rgba(0,0,0,0.5);
}
```

### Color Rules
- Green (#34a853) ONLY for positive numbers, PASS verdicts, connected status
- Red (#ea4335) ONLY for negative numbers, NO_PASS verdicts, errors, alerts
- Amber accent (#f5a623) for interactive elements, CTAs, selected states, AI working indicators
- Blue (#4285f4) for informational content, links, thesis/research events
- Never use color alone to convey meaning (a11y: pair with icon or text)
- AI surfaces use `--bg-ai-glass` with `backdrop-filter: blur(12px)` to visually separate AI-generated content from static data

---

## Spacing

### Base Unit: 4px
### Density: Compact (appropriate for fund management tool)

```css
--space-1: 4px;
--space-2: 8px;
--space-3: 12px;
--space-4: 16px;
--space-5: 20px;
--space-6: 24px;
--space-8: 32px;
--space-10: 40px;
--space-12: 48px;
```

### Spacing Rules
- Table cell padding: `--space-2` vertical, `--space-3` horizontal (dense)
- Card padding: `--space-4`
- Section gaps: `--space-6`
- Page padding: `--space-6` on desktop
- Sidebar width: 200px
- Split-pane config panel: 420px

---

## Layout

### Approach: Grid-disciplined for data, creative-editorial for AI
- **Data pages** (Screener, Portfolio, Research, Allocator): strict grid, data tables, sortable columns
- **Strategy page**: split-pane (conversation left, config right)
- **Dashboard**: hybrid (KPI cards + activity feed)

### Border Radius
```css
--radius-sm: 4px;    /* badges, pills, small elements */
--radius-md: 6px;    /* buttons, inputs, cards */
--radius-lg: 8px;    /* panels, modals, page sections */
--radius-xl: 12px;   /* mockup containers, major sections */
--radius-full: 9999px; /* pills, floating trigger button */
```

---

## Motion

### Approach: Intentional, AI-focused
Static UI stays static. Animation only appears on AI-driven surfaces. This creates a clear visual language: if it moves, the AI is doing something.

### AI Motion Patterns
- **Typing indicator:** 3 amber dots, pulse animation 1.2s ease-in-out infinite, staggered 0.2s
- **Streaming text:** content height expansion as text arrives
- **Progress bar fill:** amber fill, smooth transition 0.3s
- **Strategy profile fill:** dimension values animate from muted to primary as AI extracts them
- **Toast slide-in:** bottom-right, translateY(20px) to 0, 0.3s ease-out, auto-dismiss 3s
- **Feedback glow:** promoted rows get 200ms accent glow, dismissed rows fade 300ms

### Easing
- Enter: `ease-out`
- Exit: `ease-in`
- Move: `ease-in-out`

### Duration
- Micro: 50-100ms (hover states, border color)
- Short: 150-250ms (button press, badge appear)
- Medium: 250-400ms (panel slide, toast)
- Long: 400-700ms (page transition, skeleton shimmer)

### Pulse Animation (AI working)
```css
@keyframes pulse {
  0%, 100% { opacity: 0.4; }
  50% { opacity: 1; }
}
.ai-pulse { animation: pulse 1.5s ease-in-out infinite; }
```

### Skeleton Loading
```css
@keyframes shimmer {
  0% { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}
.skeleton {
  background: linear-gradient(90deg, var(--bg-tertiary) 25%, var(--bg-secondary) 50%, var(--bg-tertiary) 75%);
  background-size: 200% 100%;
  animation: shimmer 1.5s infinite;
  border-radius: 4px;
}
```

---

## Component Patterns

### Data Table
Primary component. Used for Screener results, portfolio holdings, agent history.
- Monospace numbers (`--font-data`), right-aligned
- Sortable headers with subtle indicator
- Row hover: `--bg-tertiary`
- Alternating rows: NO (too noisy in dark mode)
- Borders: horizontal only, `--border`
- Sticky header on scroll
- Positive numbers: `--positive`, negative: `--negative`
- Ticker column: `--font-data`, `--accent` on hover (clickable to detail page)
- Max 5 visible dynamic columns; "Show all columns" toggle if more

### Score/Verdict Badge
Used for IC decisions, agent status, conviction levels.
- PASS: `--positive` background at 12% opacity, `--positive` text
- NO_PASS: `--negative` background at 12% opacity, `--negative` text
- RUNNING: `--accent-subtle` background, `--accent` text, pulsing dot
- Pill shape, `--text-xs`, uppercase, `--font-data`, font-weight: 600

### KPI Card
Used on Dashboard for portfolio value, pipeline counts.
- `--bg-secondary` background, `--border` border
- Label: `--font-data`, `--text-xs`, `--text-muted`, uppercase, letter-spacing
- Hero value: `--text-3xl`, `--font-display`, font-weight: 700
- Secondary value: `--text-2xl`, `--font-data`
- Change indicator: `--positive` or `--negative`
- No decorative borders or shadows

### Buttons
- **Primary:** `--accent` background, `#0a0a0f` text. Hover: `--accent-muted`
- **Secondary:** transparent background, `--text-primary` text, `--border` border. Hover: `--accent` border + text
- **Ghost:** transparent, `--text-secondary` text, no border. Hover: `--accent` text

### Input
- `--bg-tertiary` background, `--border` border, `--radius-md`
- Focus: `--accent` border
- Placeholder: `--text-muted`
- Font: `--font-ui`, `--text-base`

### Alerts
- Left border 3px solid + matching background at 8% opacity
- Success: `--positive`. Warning: `--warning`. Error: `--negative`. Info: `--info`

### Toast
- Position: fixed bottom-right, above floating trigger
- `--bg-elevated` background, `--border` border, `--shadow-md`
- Slide-in animation 0.3s, auto-dismiss 3s

### AI Surface (frosted glass)
Used for all AI-generated content: conversation panels, deep reasoning, learning proposals.
```css
.ai-surface {
  background: var(--bg-ai-glass);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border: 1px solid rgba(245, 166, 35, 0.08);
  border-radius: var(--radius-lg);
}
```
Visual rule: if a panel has frosted glass, the AI generated/is generating its content.

### Terminal Conversation
Used on Strategy page and floating panel. NOT chat bubbles.
- Single-column text log (like a terminal)
- AI messages: `--text-primary` color, no prefix
- User messages: `--accent` colored `>` prefix
- Suggested responses: pill-shaped buttons (`--bg-tertiary`, `--border`, hover: `--accent` border)
- Input at bottom: full-width, `--bg-tertiary`

### Return Decomposition Bar
Stacked horizontal bar showing where return comes from.
- Discount closing: `--info` (blue)
- Revenue growth: `--positive` (green)
- Margin expansion: `--accent` (amber)
- Dividends: `--text-muted` (gray)
- Legend below with colored dots

### Progress Bar
Used during Screener runs (5-8 minute operations).
- Phase label + cancel button on top
- `--bg-tertiary` track, `--accent` fill, `--radius-sm`
- Count (47/200) and elapsed time below
- Streaming partial results appear in table during run

### Pipeline Timeline (vertical)
Used on Ticker Detail page for research history.
- Vertical line: 2px `--border`
- Event dots: 16px circles, color-coded by type:
  - Green: IC decisions
  - Blue: thesis events
  - Amber: screener appearances
  - Gray: older events (reduced opacity)
- Event cards: `--bg-secondary`, full detail of what happened at each point

### Floating Strategy Panel
Global slide-out drawer for AI conversation, accessible from any page.
- Trigger: 48px amber circle, bottom-right corner, `--accent` background
- Panel: 400px wide, `--bg-secondary`, slides from right
- Context-aware: pre-fills based on current page
- Close: click outside, Escape, or X button

---

## Navigation Structure

**NOTE: Wireframes are the source of truth. This section updated to match approved wireframes.**

```
Home (MR)           Mirror / Configure toggle
Screener (SC)       AI-scored results + feedback
Research (RS)       Thesis | IC Review | Approved tabs
─────────
Portfolio (PF)      Holdings, P&L, alerts, sync positions
Library (LB)        Full research archive (standalone page, NOT a Research sub-tab)
Allocator (AL)      Position sizing with scenario comparison
─────────
Settings (ST)       Data Sources, AI Model, System
```

### Sidebar
- 208px wide, `--bg-secondary` with subtle gradient, left side
- Brand: "FUNDOPS" in `--font-data`, `--accent`, letter-spacing 0.08em
- Tagline below brand: "PERSONAL INVESTMENT OS" in 10px, `--text-muted`
- Nav items: 26px icon box + label, `--text-sm`
- Active: `--accent` text + accent border (rgba(245,166,35,0.25)) + accent-subtle background (rgba(245,166,35,0.08))
- Separator: 1px `--border` line
- Bottom: "Run Pipeline" button (amber background, always)

### Key decisions (wireframe-approved)
- Home = Mirror page (Said vs Did + Constitution). Configure = AI strategy conversation (separate page, toggle at top)
- Strategy page absorbed into Home Configure (02-home-configure.html). No standalone Strategy page.
- Library is its own sidebar nav item, NOT a tab inside Research
- Ticker Detail has 3 tabs: Overview, Research, Health (no Library tab — link to Library page instead)
- Research page has 3 tabs: Thesis, IC Review, Approved (no Library tab)
- Approved tab shows two memo types independently: Research Report + Investment Memo
- Portfolio position editor is a popup overlay, not a separate page state

---

## Page Layouts

### Dashboard
- **Hero KPIs (2x size):** Portfolio Value + Daily P&L (`--text-3xl`, `--font-display`)
- **Secondary KPIs (1x):** Pipeline funnel, Agent Runs, Alerts count (`--text-2xl`)
- **Recent Activity:** data table with agent, ticker, verdict badge, timestamp
- **Agent Status:** collapsible section with colored dots
- **Empty state:** "Welcome to FundOps" with "Try with Sample Data" (primary) + "Set Up Your Strategy" (secondary)
- **Stale data:** "Last updated X ago" with amber badge if >5 min

### Strategy (split-pane)
- **Autonomy mode:** compact segmented control (Copilot | Advisor | Autopilot)
- **Tab bar:** Conversation | Profile | Outcomes | Learning
- **Left pane:** terminal-style conversation with AI surface treatment
- **Right pane (420px):** Strategy profile (2x2 grid of dimension cards) + Agent config with subtabs (IC Review, Screener, Thesis, Portfolio, Allocator)
- **Agent config shows full detail:** hero numbers, growth-aware discount floors table, rubric weight bars, all inline-editable
- **Learning signals:** AI improvement proposals with evidence, accept/reject/discuss buttons, learning stats (feedback count, outcomes tracked, proposals accepted)
- **Profile tab:** read-only strategy view + scoring code viewer (JetBrains Mono, syntax highlighted, version selector)
- **Outcomes tab:** 3 views (run history table, thesis integrity heatmap at 30d/60d/90d/6m/9m/12m, learning curve chart)
- **Learning tab:** full list of AI proposals with evidence

### Screener
- **Run summary card:** strategy name, timestamp, stocks scored, top pick, AI summary
- **Scoring code viewer:** collapsible, JetBrains Mono, dark syntax highlighting
- **Tab bar:** Results | Past Runs
- **Results table:** Top 20 (highlighted) + Rest of Universe (collapsed). Max 5 dynamic columns.
- **Running state:** phase indicator (Filtering → Enriching → Scoring), progress bar, streaming partial results (faded rows), cancel button
- **Feedback:** promote (accent glow + toast) / dismiss (fade + reason modal + toast). Counter: "12 of 47 rated"
- **"Ask AI" links:** on expanded rows, opens floating panel with context

### Research (tabbed)
- **Thesis tab:** table (Ticker, Fair Value, Expected Return, Verdict, Date), expandable rows
- **IC Review tab:** table (Ticker, Verdict, Base Return, Bear Return, Conviction, Date), expandable rows
- **Approved tab:** IC-passed tickers only. Table with Ticker, Approved Date, Fair Value, Expected Return, Memo Status (checkmark/circle), Action buttons (View Memo / Gen Memo / + Portfolio)
- **Library tab:** master-detail with full memo reader. Left panel: search + sector filter + memo list. Right panel: quick facts bar (pinned), sticky TOC (scroll-synced), rendered markdown, PDF/MD export, return decomposition bar, mode toggle (Research Report / Investment Memo)
- **Ticker Timeline:** vertical timeline showing all research events for a ticker across time: screener appearances (with score, rank, price at that time), theses, IC decisions, memos. Color-coded dots, older events fade.

### Ticker Detail
- **Hero section:** IC Review verdict as large badge (green PASS or red NO_PASS), conviction, one-line reasoning
- **Pipeline timeline:** 16px dots connected by line (filled=complete, empty=pending, pulsing=active)
- **Agent cards:** most recent agent gets 2x height, older agents compact
- **Generate Memo card:** cost estimate + button
- **"Ask AI" links** on each card

### Portfolio
- **Header:** title + summary (value, P&L, positions, % invested) + Refresh Prices + Sync Positions buttons
- **Holdings table:** Ticker, Shares, Cost, Price, P&L%, Weight (red if >20%), Type
- **Sync Positions panel** (AI surface): 3 methods as cards
  - Tell the AI: "I sold 500 shares of PLTR at $120"
  - Upload File: CSV, Excel, or brokerage PDF. AI parses and reconciles.
  - Edit Manually: add/edit/remove positions in table
- **Alerts:** below table with warning/error alerts
- **No broker connection.** FundOps recommends, PM executes externally, then syncs back.

### Allocator
- **3 sections grouped by urgency:**
  - Action Required (red left border): TRIM, EXIT cards
  - Monitoring (amber left border): ADD_ON_WEAKNESS cards
  - No Action (gray): HOLD tickers
- **Deep Reasoning panel** per action card (AI surface treatment):
  - Why now: quantified risk exposure
  - Thesis status: what changed vs original thesis
  - Scenario comparison: "If you trim" vs "If you hold" side-by-side cards
  - Key question: frames the real decision
  - Buttons: "Discuss with AI" (primary), "Mark as Done" (secondary), "Dismiss" (ghost)
  - Footer: "After you execute this trade in your brokerage, tell the AI or upload your updated positions to sync."

### Settings (infrastructure only)
- **Tab bar:** Data Sources | AI Model | Schedules
- **Data Sources:** connector cards (SEC EDGAR, FMP, yfinance) with status dots, Test/Edit buttons, "+ Add Data Source"
- **AI Model:** model selector dropdown, API key masked, cost tracking
- **Schedules:** table with agent, frequency, day, time, active/manual status
- **Agent config has moved to Strategy page** (not in Settings)

---

## Empty States

Every empty state has: a headline, a description, and a primary action.

| Page | Empty State | Action |
|------|------------|--------|
| Dashboard (first visit) | "Welcome to FundOps" | "Try with Sample Data" / "Set Up Your Strategy" |
| Screener (never run) | "Ready to screen" | "Run your first screen" |
| Screener (no results) | "No opportunities found" | "Run Screener" or "Adjust hurdles" |
| Research > Thesis | "No theses yet. Run Screener to surface candidates." | Link to Screener |
| Research > IC Review | "No IC decisions yet. Generate theses first." | Link to Thesis |
| Research > Approved | "No approved names yet. Run IC Review." | Link to IC Review |
| Research > Library | "Select a memo from the list" | Search input focused |
| Portfolio (no holdings) | "Add your portfolio" | "Sync Positions" panel |
| Strategy (no strategy) | "Define your investment strategy" | "Start Conversation" button |
| Strategy > Outcomes | "Need at least 3 screener runs" | Link to Screener |
| Strategy > Learning | "Accumulating data. Proposals appear after 50+ feedback signals." | — |

---

## Loading States

- **Tables:** 8 skeleton rows, shimmering `--bg-tertiary` to `--bg-secondary`
- **KPI cards:** skeleton card shapes
- **Screener running:** phase indicator + progress bar + streaming partial results
- **AI conversation:** 3 amber dots typing indicator, pulsing
- **Agent running:** pulsing dot in sidebar button, agent badge in job tracker

---

## Error States

- **API key invalid:** red banner at top with "Fix in Settings" link
- **Agent failed:** red badge on nav item, error detail in activity feed
- **Network error:** "Connection lost" banner, auto-retry indicator
- **AI conversation error:** red-tinted card with "Retry" button (no alert())
- **Scoring code gen failure:** "Generation failed" + "Retry Generation" button
- **Stale data:** amber "Stale" badge next to "Last updated X ago" timestamp

---

## Demo Mode

- **Entry:** "Try with Sample Data" button on welcome screen
- **Banner:** persistent amber bar at top of every page: "Viewing sample data. [Set Up Your Strategy →]"
- **Data:** 10 tickers with 30 days of screener results, theses, IC decisions, portfolio data
- **Functional:** feedback buttons work in demo, conversation works in demo
- **Exit:** clicking "Set Up Your Strategy" or configuring API keys in Settings

---

## First-Time User Experience

1. Dashboard shows welcome screen with demo/setup paths
2. "Set Up Your Strategy" → Strategy page, fresh conversation
3. AI starts: "What kind of investing do you do?"
4. 5-10 exchange conversation extracts strategy profile
5. Scoring code generated
6. Success state: "Your strategy is ready. [Run Your First Screen →]"
7. Button navigates to Screener, auto-triggers run
8. Results stream in with phase indicator + progress bar

---

## Responsive Breakpoints

| Viewport | Layout |
|----------|--------|
| Desktop (>1024px) | Full sidebar (200px) + main content |
| Tablet (768-1024px) | Collapsed sidebar (icons only, 64px) + main content |
| Mobile (<768px) | Deferred to v2+ |

Tables scroll horizontally on narrow viewports. KPI cards stack vertically.

---

## Accessibility

- All colors meet WCAG AA contrast on `--bg-primary`
- Keyboard nav: Tab through interactive elements, Enter to activate
- ARIA landmarks: `role="navigation"` sidebar, `role="main"` content, `role="status"` job tracker
- Focus indicator: 2px `--accent` outline, 2px offset
- Touch targets: minimum 44x44px on buttons
- Screen reader labels on icon-only buttons (promote, dismiss, expand)
- Never use color alone: PASS/NO_PASS always has text + color

---

## Preview Page

Interactive HTML preview with all components and 11 page mockups: `/tmp/fundops-design-preview-1774752202.html`

---

## Decisions Log

| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-03-29 | Updated from FundOps to FundOps design system | Full v2 redesign based on design review + consultation |
| 2026-03-29 | Added Geist font for display headings | Adds warmth to Inter+JetBrains stack without losing technical feel |
| 2026-03-29 | Added AI surface color (#141520) | Blue-shifted dark to visually separate AI content from static data |
| 2026-03-29 | Terminal-style conversation (no chat bubbles) | Bloomberg aesthetic, professional tool not chatbot |
| 2026-03-29 | Frosted glass AI surfaces | Visual language: frosted = AI generated/thinking |
| 2026-03-29 | Motion only on AI surfaces | Opposite of typical apps. Makes AI feel alive, data stays calm |
| 2026-03-29 | Split Strategy from Settings | Strategy is operational (conversation + config + learning). Settings is infrastructure (API keys, schedules) |
| 2026-03-29 | Grouped Research tabs (Thesis, IC Review, Approved, Library) | Reduced nav from 10 to 7 items |
| 2026-03-29 | Library absorbs Memo page | Master-detail layout where right panel IS the full memo reader |
| 2026-03-29 | Added Approved tab | Pipeline output: IC-passed tickers with memo status and action buttons |
| 2026-03-29 | Ticker Timeline in Library | Full research history per ticker across all pipeline runs over time |
| 2026-03-29 | Split-pane Strategy with full agent config | Config needs real screen width, not a narrow sidebar |
| 2026-03-29 | Learning signals inline with agent config | AI proposals visible next to the thresholds they want to change |
| 2026-03-29 | Allocator deep reasoning panels | Portfolio decisions need full argument, not just "trim 40%" |
| 2026-03-29 | No broker connection, 3-way sync | Tell AI, upload file (CSV/Excel/PDF), or edit manually |
| 2026-03-29 | Compact autonomy mode selector | Segmented control, not 3 big cards. Users don't switch often |
