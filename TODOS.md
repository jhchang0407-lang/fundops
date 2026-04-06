# TODOS

## Outcome Tracking Display UI
**What:** Design and build the outcome tracking display UI (thesis integrity scores, goal-relative grading, performance vs benchmark over time). Generate mock data for 90/180/365 day outcome checks to test the UI with realistic data.
**Why:** Users need to see whether their screener is actually working. Without this, outcome tracking runs in the background with no visibility. The feedback loop is invisible.
**Pros:** Closes the feedback loop visually. Users can see "your screener found 8 stocks that maintained thesis integrity after 90 days."
**Cons:** Needs outcome backend + mock data generation before UI can be meaningful.
**Context:** Phase 2 build. Natural home is a 'Performance' tab in Settings > Strategy. Design with mock data first, then wire to real backend.
**Depends on:** F8 (outcome tracking) backend being built. Generate mock outcome data to unblock UI design.
**Added:** 2026-03-28 by /plan-design-review
