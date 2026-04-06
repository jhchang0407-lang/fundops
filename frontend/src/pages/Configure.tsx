import { useState, useRef, useEffect } from 'react';
import DOMPurify from 'dompurify';
import type { FormEvent } from 'react';
import { Link as _Link } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../api/client';

type ChatMessage = { role: string; content: string };

/* ------------------------------------------------------------------ */
/*  Agent definitions for chip strip + overlays                        */
/* ------------------------------------------------------------------ */
const AGENTS = [
  {
    id: 'screener',
    icon: 'SC',
    label: 'Screener',
    subtitle: 'Scores stocks using AI-generated Python',
    description: 'Scores every stock in your universe against your strategy. AI generates the Python scoring code from your constitution. Regenerates automatically when your strategy changes.',
    sections: [
      {
        title: 'SCORING WEIGHTS',
        type: 'weights' as const,
        items: [
          { label: 'Quality', value: 45, color: 'var(--accent)' },
          { label: 'Cheapness', value: 30, color: 'var(--info)' },
          { label: 'Growth', value: 25, color: 'var(--positive)' },
        ],
      },
      {
        title: 'HANDOFF FILTERS',
        type: 'rows' as const,
        items: [
          { label: 'Min expected return', value: '20%' },
          { label: 'Min gross margin', value: '30%' },
          { label: 'Max D/E', value: '3.0x' },
          { label: 'Max candidates', value: '15' },
        ],
      },
      {
        title: 'LENSES',
        type: 'pills' as const,
        items: [
          { label: 'Dislocation', className: 'pill-accent' },
          { label: 'Compounder', className: 'pill-info' },
        ],
      },
    ],
  },
  {
    id: 'thesis',
    icon: 'TH',
    label: 'Thesis',
    subtitle: 'Quick thesis with web research + valuation',
    description: 'Generates an investment thesis with independent valuation, return decomposition, and constitution fit check. Uses web research to understand why a stock is cheap.',
    sections: [
      {
        title: 'FOCUS AREAS',
        type: 'pills' as const,
        items: [
          { label: 'unit economics', className: 'pill-accent' },
          { label: 'moat durability', className: 'pill-accent' },
          { label: '3-5yr horizon', className: 'pill-accent' },
        ],
      },
      {
        title: 'SETTINGS',
        type: 'rows' as const,
        items: [
          { label: 'Web research', value: 'Enabled', valueColor: 'var(--positive)' },
          { label: 'Constitution fit check', value: 'Active', valueColor: 'var(--positive)' },
          { label: 'Library similarity', value: 'Active', valueColor: 'var(--positive)' },
        ],
      },
    ],
  },
  {
    id: 'ic',
    icon: 'IC',
    label: 'IC Review',
    subtitle: 'Stress-test with bear case + AI narrative',
    description: 'Every thesis gets a mechanical stress-test (70% haircut on growth assumptions) plus an AI narrative review for style fit. Binary PASS/NO_PASS verdict.',
    sections: [
      {
        title: 'HURDLES',
        type: 'rows' as const,
        items: [
          { label: 'Base return hurdle', value: '20%' },
          { label: 'Bear return hurdle', value: '15%' },
          { label: 'Bear case haircut', value: '70%' },
        ],
      },
      {
        title: 'DISCOUNT FLOORS',
        type: 'rows' as const,
        items: [
          { label: 'High-growth (15%+ rev, 60%+ GM)', value: '15%' },
          { label: 'Moderate (10%+ rev, 50%+ GM)', value: '20%' },
          { label: 'Steady-state', value: '30%' },
        ],
      },
      {
        title: 'AI REVIEW',
        type: 'rows' as const,
        items: [
          { label: 'AI can override mechanical', value: 'Yes', valueColor: 'var(--positive)' },
          { label: 'Style fit check', value: 'Active', valueColor: 'var(--positive)' },
        ],
      },
    ],
  },
  {
    id: 'memo',
    icon: 'MM',
    label: 'Memo',
    subtitle: 'Full deep-dive analysis ',
    description: 'Two formats, both available on any IC-passed ticker from the Research page. Your strategy shapes what each section emphasizes — same structure, different analytical lens.',
    sections: [
      {
        title: 'RESEARCH REPORT · 13 SECTIONS',
        type: 'pills' as const,
        items: [
          { label: 'Business Overview', className: 'pill-accent' },
          { label: 'Industry & Competitive Position', className: 'pill-accent' },
          { label: 'Financial Analysis', className: 'pill-accent' },
          { label: 'Management & Governance', className: 'pill-accent' },
          { label: 'Valuation', className: 'pill-accent' },
          { label: 'Growth Catalysts', className: 'pill-accent' },
          { label: 'Key Risks', className: 'pill-accent' },
          { label: 'Bull / Bear / Base Cases', className: 'pill-accent' },
          { label: 'Thesis Summary', className: 'pill-accent' },
        ],
      },
      {
        title: 'INVESTMENT MEMO · 4 SECTIONS',
        type: 'pills' as const,
        items: [
          { label: 'The Opportunity', className: 'pill-info' },
          { label: 'Variant View', className: 'pill-info' },
          { label: 'Return Sources', className: 'pill-info' },
          { label: 'Key Risks & Monitors', className: 'pill-info' },
        ],
      },
    ],
  },
  {
    id: 'portfolio',
    icon: 'PF',
    label: 'Portfolio',
    subtitle: 'P&L + thesis health + alerts',
    description: 'Tracks every held position daily: price performance, P&L vs entry, and thesis health per assumption. Alerts when something deviates from why you bought it — not just price.',
    sections: [
      {
        title: 'DAILY MONITORING',
        type: 'rows' as const,
        items: [
          { label: 'Price & unrealized P&L', value: 'All positions', valueColor: 'var(--positive)' },
          { label: 'Return vs entry thesis', value: 'Tracked', valueColor: 'var(--positive)' },
          { label: 'Thesis health score', value: 'Per assumption', valueColor: 'var(--positive)' },
          { label: 'Key metric drift', value: 'Revenue, margins, ROIC', valueColor: 'var(--text-muted)' },
        ],
      },
      {
        title: 'ALERT TRIGGERS',
        type: 'rows' as const,
        items: [
          { label: 'Concentration limit breach', value: '> 20%' },
          { label: 'Position drawdown', value: '< -15%' },
          { label: 'Thesis health breach', value: '< 25 / 100' },
          { label: 'Revenue miss vs thesis', value: 'Flagged' },
        ],
      },
      {
        title: 'THESIS HEALTH TRACKS',
        type: 'pills' as const,
        items: [
          { label: 'Revenue growth trajectory', className: 'pill-accent' },
          { label: 'Margin expansion / contraction', className: 'pill-accent' },
          { label: 'ROIC stability', className: 'pill-accent' },
          { label: 'Return vs entry target', className: 'pill-accent' },
          { label: 'Key assumption validity', className: 'pill-accent' },
        ],
      },
    ],
  },
  {
    id: 'allocator',
    icon: 'AL',
    label: 'Allocator',
    subtitle: 'Position sizing + action recommendations',
    description: 'Classifies each position as core / tactical / legacy and outputs TRIM, ADD, SWAP, or EXIT recommendations based on return profiles, conviction, and concentration rules.',
    sections: [
      {
        title: 'POSITION SIZING',
        type: 'rows' as const,
        items: [
          { label: 'Max single position', value: '15%' },
          { label: 'Portfolio concentration cap', value: '20%' },
          { label: 'Min expected return to size', value: '8%' },
        ],
      },
      {
        title: 'ACTION TRIGGERS',
        type: 'rows' as const,
        items: [
          { label: 'ADD', value: 'Bear case still passes hurdle', valueColor: 'var(--positive)' },
          { label: 'TRIM', value: 'At/above concentration limit', valueColor: 'var(--warning)' },
          { label: 'SWAP', value: 'Higher conviction name available', valueColor: 'var(--info)' },
          { label: 'EXIT', value: 'Thesis broken or target reached', valueColor: 'var(--negative)' },
        ],
      },
      {
        title: 'POSITION TYPES',
        type: 'rows' as const,
        items: [
          { label: 'Core compounder', value: '5–10%' },
          { label: 'Tactical / dislocation', value: '2–5%' },
          { label: 'Balanced', value: '3–7%' },
        ],
      },
    ],
  },
  {
    id: 'universe',
    icon: 'UV',
    label: 'Universe',
    subtitle: 'Stock universe for screening',
    description: 'The pool of stocks the Screener evaluates. Starter 30 is great for testing. Nasdaq 100 or S&P 500 for a real screen. You can also give a custom list of tickers.',
    sections: [
      {
        title: 'PRESETS',
        type: 'rows' as const,
        items: [
          { label: 'Starter 30', value: '30 stocks' },
          { label: 'Nasdaq 100', value: '101 stocks' },
          { label: 'US Large Cap 200', value: '207 stocks' },
          { label: 'S&P 500', value: '503 stocks' },
        ],
      },
      {
        title: 'CUSTOM',
        type: 'pills' as const,
        items: [
          { label: 'Paste comma-separated tickers in chat', className: 'pill-accent' },
        ],
      },
    ],
  },
  {
    id: 'me',
    icon: 'ME',
    label: 'Strategy',
    subtitle: 'Your investment constitution',
    description: 'Your north star, must-have signals, anti-signals, and IC hurdles. Everything the system uses to evaluate stocks through your lens.',
    sections: [
      {
        title: 'MUST-HAVE SIGNALS',
        type: 'pills' as const,
        items: [
          { label: 'High ROIC', className: 'pill-positive' },
          { label: 'High margins', className: 'pill-positive' },
          { label: 'Revenue growth', className: 'pill-positive' },
          { label: 'FCF positive', className: 'pill-positive' },
        ],
      },
      {
        title: 'ANTI-SIGNALS',
        type: 'pills' as const,
        items: [
          { label: 'D/E > 2x', className: 'pill-negative' },
          { label: 'Declining rev 2+ yrs', className: 'pill-negative' },
        ],
      },
      {
        title: 'IC HURDLES',
        type: 'rows' as const,
        items: [
          { label: 'Base return hurdle', value: '20%' },
          { label: 'Bear return hurdle', value: '15%' },
          { label: 'Bear case haircut', value: '70%' },
        ],
      },
      {
        title: 'DISCOUNT FLOORS',
        type: 'rows' as const,
        items: [
          { label: 'High-growth compounder', value: '15%' },
          { label: 'Moderate growth', value: '20%' },
          { label: 'Steady-state', value: '30%' },
        ],
      },
    ],
  },
] as const;

type AgentId = typeof AGENTS[number]['id'];

/* ================================================================== */
/*  Filter label formatter (raw DB keys → human-readable)             */
/* ================================================================== */
const FILTER_LABEL_MAP: Record<string, string> = {
  revenue_growth_ttm_yoy: 'Revenue growth (TTM YoY)',
  revenue_growth_yoy: 'Revenue growth (YoY)',
  operating_margin_yoy_change_bps: 'Operating margin expansion',
  operating_margin_latest_pct: 'Operating margin (min)',
  gross_margin_pct: 'Gross margin (min)',
  revenue_not_declining: 'Revenue not declining',
  revenue_cagr_3yr: 'Revenue CAGR (3yr)',
  rs_percentile_3m: 'Relative strength (3M)',
  rs_percentile_6m: 'Relative strength (6M)',
  roic: 'ROIC (min)',
  roe: 'ROE (min)',
  debt_equity: 'Debt / Equity (max)',
  fcf_yield: 'FCF yield (min)',
  pe_ratio: 'P/E ratio (max)',
  ev_ebitda: 'EV/EBITDA (max)',
  price_to_book: 'Price / Book (max)',
  net_margin: 'Net margin (min)',
};

function formatFilterSignal(key: string, val: unknown): string {
  const label = FILTER_LABEL_MAP[key] ?? key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
  const strVal = String(val ?? '');
  if (strVal === 'true') return label;
  if (strVal === 'false') return `No ${label.toLowerCase()}`;
  // Clean up value: ">=100" → "≥ 100bps", ">20%" → "> 20%"
  const cleanVal = strVal
    .replace(/^>=/, '≥ ')
    .replace(/^<=/, '≤ ')
    .replace(/^>(?!=)/, '> ')
    .replace(/^<(?!=)/, '< ');
  return `${label} ${cleanVal}`;
}

/* ================================================================== */
/*  Agent Overlay Panel                                                */
/* ================================================================== */
function AgentOverlay({ agentId, onClose }: { agentId: AgentId; onClose: () => void }) {
  const agent = AGENTS.find((a) => a.id === agentId);
  if (!agent) return null;

  // Always fetch live — so overlay reflects saves that happen while it's open
  const { data: strategyData } = useQuery({ queryKey: ['strategy'], queryFn: api.getStrategy });
  const constitution = strategyData?.constitution ?? strategyData?.strategy ?? null;

  // For universe overlay: show live current universe
  const { data: configData } = useQuery({ queryKey: ['config'], queryFn: api.getConfig, enabled: agentId === 'universe' });
  const { data: universesData } = useQuery({ queryKey: ['universes'], queryFn: api.getUniverses, enabled: agentId === 'universe' });

  // Constitution is the source of truth for universe; fall back to workflow.yaml config
  const constitutionUniverse = strategyData?.constitution ?? strategyData?.strategy;
  const isCustomUniverse = constitutionUniverse?.universe_type === 'custom';
  const customTickers: string[] = constitutionUniverse?.universe_custom ?? [];
  const currentUniverseId: string = constitutionUniverse?.universe_name
    || configData?.agents?.scout?.config?.universe
    || 'starter_30';
  const universePresets: Array<{ id: string; label: string; count: number; description: string }> = universesData?.presets ?? [];

  // Build live sections by merging DB constitution values over the static defaults
  const liveSections = agent.sections.map((section) => {
    if (!constitution) return section;

    // Strategy (me) agent — show actual must_have_signals, anti_signals, ic_hurdles
    if (agentId === 'me') {
      if (section.title === 'MUST-HAVE SIGNALS') {
        // Use explicit signals if set, otherwise derive from screener filters (formatted)
        const signals: string[] = Array.isArray(constitution.must_have_signals) && constitution.must_have_signals.length > 0
          ? constitution.must_have_signals
          : Object.entries((constitution.agent_profiles?.screener?.filters as Record<string, unknown> | undefined) ?? {})
              .filter(([, v]) => v !== null && v !== undefined && typeof v !== 'object' && String(v) !== 'false')
              .slice(0, 6)
              .map(([k, v]) => formatFilterSignal(k, v));
        if (signals.length > 0) {
          return { ...section, items: signals.map((s: string) => ({ label: s, className: 'pill-positive' })) };
        }
      }
      if (section.title === 'ANTI-SIGNALS') {
        let signals: string[] = [];
        if (Array.isArray(constitution.anti_signals) && constitution.anti_signals.length > 0) {
          signals = constitution.anti_signals;
        } else if (Array.isArray(constitution.disqualifiers) && constitution.disqualifiers.length > 0) {
          signals = constitution.disqualifiers;
        } else {
          // Derive from filters: boolean=false entries and "not" keys
          const filters = (constitution.agent_profiles?.screener?.filters as Record<string, unknown> | undefined) ?? {};
          signals = Object.entries(filters)
            .filter(([k, v]) => v !== null && v !== undefined && typeof v !== 'object' && (String(v) === 'false' || k.includes('not') || k.includes('declining')))
            .map(([k, v]) => formatFilterSignal(k, v));
        }
        if (signals.length > 0) {
          return { ...section, items: signals.map((s: string) => ({ label: s, className: 'pill-negative' })) };
        }
      }
      if (section.title === 'IC HURDLES' && constitution.ic_hurdles) {
        const h = constitution.ic_hurdles;
        return {
          ...section, items: [
            { label: 'Base return hurdle', value: h.base_return_pct != null ? `${h.base_return_pct}%` : '20%' },
            { label: 'Bear return hurdle', value: h.bear_return_pct != null ? `${h.bear_return_pct}%` : '15%' },
            { label: 'Bear case haircut', value: h.haircut_pct != null ? `${h.haircut_pct}%` : '70%' },
          ],
        };
      }
    }

    // IC Review agent — show actual hurdles
    if (agentId === 'ic' && section.title === 'HURDLES' && constitution.ic_hurdles) {
      const h = constitution.ic_hurdles;
      return {
        ...section, items: [
          { label: 'Base return hurdle', value: h.base_return_pct != null ? `${h.base_return_pct}%` : '20%' },
          { label: 'Bear return hurdle', value: h.bear_return_pct != null ? `${h.bear_return_pct}%` : '15%' },
          { label: 'Bear case haircut', value: h.haircut_pct != null ? `${h.haircut_pct}%` : '70%' },
        ],
      };
    }

    // Screener — replace hardcoded handoff filters with live ones from constitution
    // Deduplicates overlapping keys (e.g., gross_margin_pct vs gross_margin_floor)
    if (agentId === 'screener' && section.title === 'HANDOFF FILTERS') {
      const filters = constitution.agent_profiles?.screener?.filters as Record<string, unknown> | undefined;
      if (filters && Object.keys(filters).length > 0) {
        // Normalize keys to canonical metric names to deduplicate
        // e.g., gross_margin_pct, gross_margin_floor, gross_margin_min → all map to "gross_margin"
        const CANONICAL_MAP: Record<string, string> = {
          gross_margin_pct: 'gross_margin', gross_margin_floor: 'gross_margin', gross_margin_min: 'gross_margin',
          roic_floor: 'roic', roic_min: 'roic',
          net_income_margin_floor: 'net_margin', net_margin_floor: 'net_margin', net_margin_min: 'net_margin',
          debt_to_equity_limit: 'debt_equity', debt_equity_max: 'debt_equity', debt_limit: 'debt_equity',
          revenue_growth_floor: 'revenue_growth', revenue_growth_cagr_3y: 'revenue_growth', revenue_cagr_3yr: 'revenue_growth',
        };
        // Deduplicate: keep the LAST entry per canonical key (latest user intent wins)
        const bestByCanonical = new Map<string, [string, unknown]>();
        for (const [k, v] of Object.entries(filters)) {
          if (v === null || v === undefined || typeof v === 'object' || String(v) === 'false') continue;
          const canonical = CANONICAL_MAP[k] ?? k;
          // Always overwrite — last entry wins (newest user setting)
          bestByCanonical.set(canonical, [k, v]);
        }
        const items = Array.from(bestByCanonical.values())
          .slice(0, 8)
          .map(([k, v]) => {
            const sv = String(v ?? '');
            const cleanVal = sv === 'true' ? '\u2713' : sv.replace(/^>=/, '\u2265 ').replace(/^<=/, '\u2264 ').replace(/^>(?!=)/, '> ').replace(/^<(?!=)/, '< ');
            return { label: FILTER_LABEL_MAP[k] ?? k.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase()), value: cleanVal };
          });
        if (items.length > 0) return { ...section, items };
      }
    }

    // Screener agent — show actual scoring weights from agent_profiles
    if (agentId === 'screener' && section.title === 'SCORING WEIGHTS') {
      const weights = (constitution.agent_profiles?.screener?.weights) as Record<string, number> | undefined;
      if (weights && Object.keys(weights).length > 0) {
        const colors = ['var(--accent)', 'var(--info)', 'var(--positive)', 'var(--warning)'];
        const total = Object.values(weights).reduce((a, b) => a + (b as number), 0) || 100;
        const items = Object.entries(weights).map(([key, val], i) => ({
          label: key.charAt(0).toUpperCase() + key.slice(1),
          value: Math.round(((val as number) / total) * 100),
          color: colors[i % colors.length],
        }));
        return { ...section, items };
      }
    }

    // Allocator — show live position sizing from constitution
    if (agentId === 'allocator' && section.title === 'POSITION SIZING') {
      const ps = (constitution.position_sizing ?? {}) as Record<string, any>;
      return {
        ...section, items: [
          { label: 'Max single position', value: ps.max_position_pct != null ? `${ps.max_position_pct}%` : '15%' },
          { label: 'Portfolio concentration cap', value: ps.concentration_limit_pct != null ? `${ps.concentration_limit_pct}%` : '20%' },
          { label: 'Min expected return to size', value: ps.min_expected_return_pct != null ? `${ps.min_expected_return_pct}%` : '8%' },
        ],
      };
    }

    // Allocator — show live position type ranges
    if (agentId === 'allocator' && section.title === 'POSITION TYPES') {
      const al = constitution.agent_profiles?.allocator as Record<string, any> | undefined;
      const pt = al?.position_types ?? {};
      return {
        ...section, items: [
          { label: 'Core compounder', value: pt.core_compounder ?? pt.core ?? '5–10%' },
          { label: 'Tactical / dislocation', value: pt.tactical ?? pt.tactical_dislocation ?? '2–5%' },
          { label: 'Balanced', value: pt.balanced ?? '3–7%' },
        ],
      };
    }

    // Allocator — show live action triggers
    if (agentId === 'allocator' && section.title === 'ACTION TRIGGERS') {
      const al = constitution.agent_profiles?.allocator as Record<string, any> | undefined;
      const at = al?.action_triggers ?? {};
      return {
        ...section, items: [
          { label: 'ADD', value: at.add ?? 'Bear case still passes hurdle', valueColor: 'var(--positive)' },
          { label: 'TRIM', value: at.trim ?? 'At/above concentration limit', valueColor: 'var(--warning)' },
          { label: 'SWAP', value: at.swap ?? 'Higher conviction name available', valueColor: 'var(--info)' },
          { label: 'EXIT', value: at.exit ?? 'Thesis broken or target reached', valueColor: 'var(--negative)' },
        ],
      };
    }

    // Thesis — show live focus areas
    if (agentId === 'thesis' && section.title === 'FOCUS AREAS') {
      const th = constitution.agent_profiles?.thesis as Record<string, any> | undefined;
      if (th?.focus_areas) {
        const areas = typeof th.focus_areas === 'string'
          ? th.focus_areas.split(',').map((s: string) => s.trim()).filter(Boolean)
          : Array.isArray(th.focus_areas) ? th.focus_areas : [];
        if (areas.length > 0) {
          return { ...section, items: areas.map((a: string) => ({ label: a, className: 'pill-accent' })) };
        }
      }
    }

    // Thesis — show live settings
    if (agentId === 'thesis' && section.title === 'SETTINGS') {
      const th = constitution.agent_profiles?.thesis as Record<string, any> | undefined;
      return {
        ...section, items: [
          { label: 'Web research', value: th?.web_research === false ? 'Disabled' : 'Enabled', valueColor: th?.web_research === false ? 'var(--text-muted)' : 'var(--positive)' },
          { label: 'Constitution fit check', value: th?.constitution_fit === false ? 'Disabled' : 'Active', valueColor: th?.constitution_fit === false ? 'var(--text-muted)' : 'var(--positive)' },
          { label: 'Library similarity', value: th?.library_similarity === false ? 'Disabled' : 'Active', valueColor: th?.library_similarity === false ? 'var(--text-muted)' : 'var(--positive)' },
        ],
      };
    }

    // IC Review — show live discount floors
    if (agentId === 'ic' && section.title === 'DISCOUNT FLOORS') {
      const ic = constitution.agent_profiles?.ic_review as Record<string, any> | undefined;
      const df = ic?.discount_floors ?? {};
      return {
        ...section, items: [
          { label: 'High-growth (15%+ rev, 60%+ GM)', value: df.high_growth != null ? `${df.high_growth}%` : '15%' },
          { label: 'Moderate (10%+ rev, 50%+ GM)', value: df.moderate != null ? `${df.moderate}%` : '20%' },
          { label: 'Steady-state', value: df.steady_state != null ? `${df.steady_state}%` : '30%' },
        ],
      };
    }

    // IC Review — show live AI review settings
    if (agentId === 'ic' && section.title === 'AI REVIEW') {
      const ic = constitution.agent_profiles?.ic_review as Record<string, any> | undefined;
      return {
        ...section, items: [
          { label: 'AI can override mechanical', value: ic?.ai_override === false ? 'No' : 'Yes', valueColor: ic?.ai_override === false ? 'var(--text-muted)' : 'var(--positive)' },
          { label: 'Style fit check', value: ic?.style_fit === false ? 'Disabled' : 'Active', valueColor: ic?.style_fit === false ? 'var(--text-muted)' : 'var(--positive)' },
        ],
      };
    }

    // Portfolio — show live monitoring settings
    if (agentId === 'portfolio' && section.title === 'DAILY MONITORING') {
      const pf = constitution.agent_profiles?.portfolio as Record<string, any> | undefined;
      return {
        ...section, items: [
          { label: 'Price + P&L', value: pf?.price_pnl ?? 'All held positions', valueColor: 'var(--positive)' },
          { label: 'Thesis health', value: pf?.thesis_health ?? 'Key assumption check', valueColor: 'var(--positive)' },
          { label: 'Earnings calendar', value: pf?.earnings_calendar ?? 'Upcoming for held', valueColor: 'var(--info)' },
          { label: 'News + filings', value: pf?.news_filings ?? 'SEC 8-K, 10-Q alerts', valueColor: 'var(--info)' },
        ],
      };
    }

    // Portfolio — show live alert triggers
    if (agentId === 'portfolio' && section.title === 'ALERT TRIGGERS') {
      const pf = constitution.agent_profiles?.portfolio as Record<string, any> | undefined;
      const at = pf?.alert_triggers ?? {};
      return {
        ...section, items: [
          { label: 'Concentration', value: at.concentration ?? '> 20% single name', valueColor: 'var(--warning)' },
          { label: 'Drawdown', value: at.drawdown ?? '> -15% from cost', valueColor: 'var(--negative)' },
          { label: 'Thesis health', value: at.thesis_health ?? '< 25 score', valueColor: 'var(--warning)' },
          { label: 'Revenue miss', value: at.revenue_miss ?? '> 2 consecutive quarters', valueColor: 'var(--negative)' },
        ],
      };
    }

    // Portfolio — show live thesis health tracks
    if (agentId === 'portfolio' && section.title === 'THESIS HEALTH TRACKS') {
      const pf = constitution.agent_profiles?.portfolio as Record<string, any> | undefined;
      if (pf?.thesis_health_tracks && Array.isArray(pf.thesis_health_tracks)) {
        return { ...section, items: pf.thesis_health_tracks.map((t: string) => ({ label: t, className: 'pill-accent' })) };
      }
    }

    // Strategy/ME — show live discount floors
    if (agentId === 'me' && section.title === 'DISCOUNT FLOORS') {
      const ic = constitution.agent_profiles?.ic_review as Record<string, any> | undefined;
      const df = ic?.discount_floors ?? {};
      return {
        ...section, items: [
          { label: 'High-growth (15%+ rev, 60%+ GM)', value: df.high_growth != null ? `${df.high_growth}%` : '15%' },
          { label: 'Moderate (10%+ rev, 50%+ GM)', value: df.moderate != null ? `${df.moderate}%` : '20%' },
          { label: 'Steady-state', value: df.steady_state != null ? `${df.steady_state}%` : '30%' },
        ],
      };
    }

    return section;
  });

  return (
    <>
      {/* Backdrop */}
      <div
        onClick={onClose}
        style={{
          position: 'absolute',
          inset: 0,
          background: 'rgba(0,0,0,0.5)',
          zIndex: 10,
        }}
      />
      {/* Panel */}
      <div style={{
        position: 'absolute',
        top: 90,
        left: '50%',
        transform: 'translateX(-50%)',
        width: 560,
        maxHeight: 'calc(100vh - 160px)',
        background: 'var(--bg-secondary)',
        border: '1px solid var(--border)',
        borderRadius: 12,
        zIndex: 20,
        display: 'flex',
        flexDirection: 'column',
        boxShadow: '0 16px 48px rgba(0,0,0,0.6)',
        overflow: 'hidden',
      }}>
        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '14px 20px', borderBottom: '1px solid var(--border)', flexShrink: 0 }}>
          <div>
            <h2 style={{ fontFamily: 'var(--font-display)', fontSize: 'var(--text-lg)', fontWeight: 600, margin: 0 }}>{agent.label}</h2>
            <div style={{ fontFamily: 'var(--font-data)', fontSize: 'var(--text-xs)', color: 'var(--text-muted)' }}>{agent.subtitle}</div>
          </div>
          <button
            onClick={onClose}
            style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', fontSize: 20, padding: '4px 8px', borderRadius: 4 }}
          >
            x
          </button>
        </div>

        {/* Body */}
        <div style={{ padding: '16px 20px', overflowY: 'auto', flex: 1 }}>
          <div style={{
            fontSize: 'var(--text-xs)',
            color: 'var(--text-muted)',
            lineHeight: 1.6,
            marginBottom: 12,
            padding: '8px 10px',
            background: 'var(--bg-tertiary)',
            borderRadius: 'var(--radius-md)',
          }}>
            {agent.description}
          </div>

          {agentId === 'universe' ? (
            <div>
              {/* Currently active */}
              <div style={{ marginBottom: 14 }}>
                <div style={{ fontFamily: 'var(--font-data)', fontSize: 'var(--text-xs)', color: 'var(--text-muted)', letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: 8 }}>
                  CURRENTLY ACTIVE
                </div>
                <div style={{ padding: '10px 14px', background: 'var(--accent-subtle)', border: '1px solid var(--accent)', borderRadius: 6 }}>
                  {isCustomUniverse ? (
                    <div>
                      <div style={{ fontFamily: 'var(--font-data)', fontWeight: 600, color: 'var(--accent)', marginBottom: 6 }}>
                        Custom list · {customTickers.length} stocks
                      </div>
                      <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-muted)', lineHeight: 1.6, wordBreak: 'break-word' }}>
                        {customTickers.slice(0, 30).join(', ')}{customTickers.length > 30 ? ` +${customTickers.length - 30} more` : ''}
                      </div>
                    </div>
                  ) : (
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                      <span style={{ fontFamily: 'var(--font-data)', fontWeight: 600, color: 'var(--accent)' }}>
                        {universePresets.find(p => p.id === currentUniverseId)?.label ?? currentUniverseId}
                      </span>
                      <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-muted)' }}>
                        {universePresets.find(p => p.id === currentUniverseId)?.count ?? '—'} stocks
                      </span>
                    </div>
                  )}
                </div>
              </div>

              {/* Presets */}
              <div style={{ marginBottom: 14 }}>
                <div style={{ fontFamily: 'var(--font-data)', fontSize: 'var(--text-xs)', color: 'var(--text-muted)', letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: 8 }}>
                  AVAILABLE PRESETS
                </div>
                {universePresets.map((p) => {
                  const isActive = !isCustomUniverse && p.id === currentUniverseId;
                  return (
                    <div key={p.id} style={{
                      display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                      padding: '7px 0', borderBottom: '1px solid var(--border)', fontSize: 'var(--text-sm)',
                      opacity: isActive ? 1 : 0.7,
                    }}>
                      <span style={{ color: isActive ? 'var(--accent)' : 'var(--text-secondary)', fontWeight: isActive ? 600 : 400 }}>
                        {p.label}
                        {isActive && <span style={{ marginLeft: 6, fontSize: 10, color: 'var(--accent)', fontFamily: 'var(--font-data)' }}>ACTIVE</span>}
                      </span>
                      <span style={{ fontFamily: 'var(--font-data)', color: 'var(--text-muted)', fontSize: 'var(--text-xs)' }}>{p.count} stocks</span>
                    </div>
                  );
                })}
                <div style={{ padding: '7px 0', fontSize: 'var(--text-sm)', opacity: isCustomUniverse ? 1 : 0.7 }}>
                  <span style={{ color: isCustomUniverse ? 'var(--accent)' : 'var(--text-secondary)', fontWeight: isCustomUniverse ? 600 : 400 }}>
                    Custom list
                    {isCustomUniverse && <span style={{ marginLeft: 6, fontSize: 10, color: 'var(--accent)', fontFamily: 'var(--font-data)' }}>ACTIVE</span>}
                  </span>
                  <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-muted)', marginTop: 2 }}>
                    Any tickers you name in the chat
                  </div>
                </div>
              </div>

              <div style={{ padding: '10px 12px', background: 'var(--bg-tertiary)', borderRadius: 6, fontSize: 'var(--text-xs)', color: 'var(--text-muted)', lineHeight: 1.6 }}>
                <strong style={{ color: 'var(--text-secondary)' }}>To change:</strong> Close this and tell the AI below.{' '}
                Try: <em>"Switch to Nasdaq 100"</em> or <em>"Screen just these: AAPL, MSFT, GOOG"</em> or <em>"Screen the 50 largest healthcare companies"</em>
              </div>
            </div>
          ) : null}

          {agentId !== 'universe' && !constitution && (
            <div style={{ padding: '24px 0', textAlign: 'center' }}>
              <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-muted)', marginBottom: 8 }}>
                Not configured yet
              </div>
              <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-muted)', lineHeight: 1.6, maxWidth: 320, margin: '0 auto' }}>
                Close this and tell the AI your investment approach. It will configure all agents — including this one — based on what you describe.
              </div>
            </div>
          )}

          {/* Memo: show strategy emphasis block when constitution exists */}
          {agentId === 'memo' && constitution && (() => {
            const memoProfile = constitution.agent_profiles?.memo as Record<string, any> | undefined;
            const thesisProfile = constitution.agent_profiles?.thesis as Record<string, any> | undefined;
            const focusAreas: string[] = memoProfile?.focus_areas
              ? (Array.isArray(memoProfile.focus_areas) ? memoProfile.focus_areas : [memoProfile.focus_areas])
              : thesisProfile?.focus_areas
              ? (Array.isArray(thesisProfile.focus_areas) ? thesisProfile.focus_areas : [thesisProfile.focus_areas])
              : [];
            if (focusAreas.length === 0) return null;
            return (
              <div style={{ marginBottom: 16 }}>
                <div style={{ fontFamily: 'var(--font-data)', fontSize: 'var(--text-xs)', color: 'var(--text-muted)', letterSpacing: '0.08em', textTransform: 'uppercase' as const, marginBottom: 8 }}>
                  EMPHASIS FOR YOUR STRATEGY
                </div>
                {focusAreas.map((f: string) => (
                  <div key={f} style={{
                    display: 'flex', alignItems: 'center', gap: 8,
                    padding: '7px 0', borderBottom: '1px solid var(--border)',
                    fontSize: 'var(--text-sm)', color: 'var(--text-secondary)',
                  }}>
                    <span style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--accent)', flexShrink: 0 }} />
                    {f}
                  </div>
                ))}
              </div>
            );
          })()}

          {agentId !== 'universe' && constitution && liveSections.map((section) => (
            <div key={section.title} style={{ marginBottom: 16 }}>
              <div style={{
                fontFamily: 'var(--font-data)',
                fontSize: 'var(--text-xs)',
                color: 'var(--text-muted)',
                letterSpacing: '0.08em',
                textTransform: 'uppercase' as const,
                marginBottom: 8,
              }}>
                {section.title}
              </div>

              {section.type === 'weights' && section.items.map((item) => (
                <div key={item.label} style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                  <span style={{ width: 80, fontSize: 'var(--text-xs)', color: 'var(--text-secondary)', fontFamily: 'var(--font-data)' }}>
                    {item.label}
                  </span>
                  <div style={{ flex: 1, height: 6, background: 'var(--bg-primary)', borderRadius: 3, overflow: 'hidden' }}>
                    <div style={{ height: 6, borderRadius: 3, width: `${'value' in item ? item.value : 0}%`, background: 'color' in item ? item.color : 'var(--accent)' }} />
                  </div>
                  <span style={{ width: 30, fontSize: 'var(--text-xs)', fontFamily: 'var(--font-data)', color: 'var(--text-muted)', textAlign: 'right' }}>
                    {'value' in item ? `${item.value}%` : ''}
                  </span>
                </div>
              ))}

              {section.type === 'rows' && section.items.map((item) => (
                <div key={item.label} style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  padding: '7px 0',
                  borderBottom: '1px solid var(--border)',
                  fontSize: 'var(--text-sm)',
                }}>
                  <span style={{ color: 'var(--text-secondary)' }}>{item.label}</span>
                  <span style={{
                    fontFamily: 'var(--font-data)',
                    color: ('valueColor' in item && item.valueColor) ? item.valueColor : 'var(--accent)',
                    fontWeight: 500,
                  }}>
                    {'value' in item ? item.value : ''}
                  </span>
                </div>
              ))}

              {section.type === 'pills' && (
                <div style={{ textAlign: 'center' }}>
                  {section.items.map((item) => (
                    <span
                      key={item.label}
                      className={`pill ${'className' in item ? item.className : 'pill-accent'}`}
                    >
                      {item.label}
                    </span>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>

        {/* Footer */}
        <div style={{ padding: '10px 20px', borderTop: '1px solid var(--border)', fontSize: 'var(--text-xs)', color: 'var(--text-muted)', textAlign: 'center', flexShrink: 0 }}>
          Tell the AI to change any setting. Close to return to chat.
        </div>
      </div>
    </>
  );
}

/* ================================================================== */
/*  MAIN EXPORT: Configure Page                                        */
/* ================================================================== */
export default function Configure() {
  const queryClient = useQueryClient();
  const [message, setMessage] = useState('');
  const [history, setHistory] = useState<ChatMessage[]>([]);
  const [selectedAgent, setSelectedAgent] = useState<AgentId | null>(null);
  const [sessionId] = useState(() => {
    // sessionStorage: survives tab switches but clears on app close
    const stored = sessionStorage.getItem('configure-session-id');
    if (stored) return stored;
    const id = `configure-${Date.now()}`;
    sessionStorage.setItem('configure-session-id', id);
    return id;
  });
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Load strategy to check existence
  const { data: strategyData } = useQuery({ queryKey: ['strategy'], queryFn: api.getStrategy });
  const { data: learningProposals } = useQuery({ queryKey: ['learning-proposals'], queryFn: api.getLearningProposals, staleTime: 120000 });
  const { data: learningDrift } = useQuery({ queryKey: ['learning-drift'], queryFn: api.getLearningDrift, staleTime: 120000 });
  const { data: configData } = useQuery({ queryKey: ['config'], queryFn: api.getConfig });

  // Load conversation history — fetch by sessionId always (no strategy required)
  const { data: historyData } = useQuery({
    queryKey: ['configure-history', sessionId],
    queryFn: () => api.getConversationHistory(strategyData?.strategy?.id, sessionId),
    staleTime: Infinity, // don't refetch in background — we own the state
  });

  // If assistant content looks like raw JSON with a "message" key, extract just the message
  const cleanContent = (content: string): string => {
    const trimmed = content.trim();
    if (trimmed.startsWith('{') && trimmed.includes('"message"')) {
      try {
        const obj = JSON.parse(trimmed);
        if (obj.message) return obj.message;
      } catch {
        // Try regex extraction for malformed JSON
        const m = trimmed.match(/"message"\s*:\s*"((?:[^"\\]|\\.)*)"/);
        if (m) return m[1].replace(/\\"/g, '"').replace(/\\n/g, '\n');
      }
    }
    return content;
  };

  // Seed history from server on mount (component remounts on navigation)
  useEffect(() => {
    if (historyData?.history?.length && history.length === 0) {
      setHistory(historyData.history.map((h: any) => ({
        ...h,
        content: h.role === 'assistant' ? cleanContent(h.content) : h.content,
      })));
    }
  }, [historyData, history.length]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [history]);

  const [lastActionResult, setLastActionResult] = useState<{ applied: string[]; isComplete: boolean } | null>(null);
  const [pendingIntent, setPendingIntent] = useState<'thinking' | 'wiring' | 'saving'>('thinking');
  const [labelIdx, setLabelIdx] = useState(0);
  const [isPending, setIsPending] = useState(false);

  const PENDING_LABELS: Record<'thinking' | 'wiring' | 'saving', string[]> = {
    thinking: ['Thinking...', 'Analyzing...', 'Reading your strategy...'],
    wiring:   ['Wiring up your settings...', 'Configuring agents...', 'Saving your strategy...', 'Almost there...'],
    saving:   ['Updating settings...', 'Applying changes...', 'Saving...'],
  };

  const pendingLabel = PENDING_LABELS[pendingIntent][labelIdx % PENDING_LABELS[pendingIntent].length];

  // Rotate label every 2.5s while waiting for response
  useEffect(() => {
    if (!isPending) { setLabelIdx(0); return; }
    const interval = setInterval(() => setLabelIdx(i => i + 1), 2500);
    return () => clearInterval(interval);
  }, [isPending]);

  const detectIntent = (msg: string): 'thinking' | 'wiring' | 'saving' => {
    if (/wire|go ahead|set it up|apply|push|save|confirm|yes|sure|do it|sounds good|lock|commit/i.test(msg)) {
      return 'wiring';
    }
    if (/change|update|adjust|tweak|modify|set|use|switch/i.test(msg)) {
      return 'saving';
    }
    return 'thinking';
  };

  const conversation = useMutation({
    mutationFn: (nextMessage: string) =>
      api.strategyConversation(nextMessage, history, strategyData?.strategy?.id, sessionId),
    onSuccess: (data) => {
      setIsPending(false);
      setHistory((prev) => [...prev, { role: 'assistant', content: data.message }]);
      const applied: string[] = data.applied_actions || [];
      // Backend auto-saves when is_complete — check strategy_saved flag
      const isComplete = !!(data.strategy_saved || (data.is_complete && data.strategy_profile));

      if (applied.length > 0 || isComplete) {
        setLastActionResult({ applied, isComplete });
        setTimeout(() => setLastActionResult(null), 6000);
        // Refresh so north star, chip configs, and portfolio strategy gate all update
        queryClient.invalidateQueries({ queryKey: ['strategy'] });
        queryClient.invalidateQueries({ queryKey: ['config'] });
      }
    },
    onError: () => setIsPending(false),
  });

  const send = (content: string) => {
    const trimmed = content.trim();
    if (!trimmed || isPending) return;
    setPendingIntent(detectIntent(trimmed));
    setLabelIdx(0);
    setIsPending(true);
    setHistory((prev) => [...prev, { role: 'user', content: trimmed }]);
    setMessage('');
    conversation.mutate(trimmed);
  };

  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    send(message);
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden', position: 'relative' }}>
      {/* North star — show a short plain-words tagline, not the full spec */}
      <div style={{
        padding: '10px 20px',
        borderBottom: '1px solid var(--border)',
        flexShrink: 0,
        textAlign: 'center',
      }}>
        <span style={{
          fontFamily: 'var(--font-display)',
          fontSize: 'var(--text-sm)',
          fontWeight: 500,
          color: 'var(--accent)',
        }}>
          {(() => {
            const raw = strategyData?.strategy?.north_star || strategyData?.constitution?.north_star || '';
            if (!raw) return 'Define your investment approach to get started';
            // Strip everything after the first metric/number indicator to keep it plain-words
            // Try to cut before "by buying", commas with numbers, or after the first verb clause
            const firstClause = raw
              .replace(/,?\s*(holding|targeting|using|by buying|by screening|requiring|with\s+\d|>\d|>=\d|\d+%)[^.]*/i, '')
              .replace(/\.$/, '')
              .trim();
            return firstClause.length > 20 ? firstClause : raw.split(/[,;]/)[0].trim();
          })()}
        </span>
      </div>

      {/* Agent chip strip */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 6,
        padding: '10px 20px',
        borderBottom: '1px solid var(--border)',
        flexShrink: 0,
      }}>
        {AGENTS.map((agent) => (
          <button
            key={agent.id}
            onClick={() => setSelectedAgent(selectedAgent === agent.id ? null : agent.id)}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 6,
              padding: '6px 12px',
              background: selectedAgent === agent.id ? 'var(--accent-subtle)' : 'var(--bg-tertiary)',
              border: `1px solid ${selectedAgent === agent.id ? 'var(--accent)' : 'var(--border)'}`,
              borderRadius: 6,
              cursor: 'pointer',
              transition: 'all 0.15s ease',
              fontSize: 'var(--text-xs)',
              color: selectedAgent === agent.id ? 'var(--accent)' : 'var(--text-secondary)',
              fontFamily: 'var(--font-data)',
            }}
          >
            <span style={{
              width: 20,
              height: 20,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              borderRadius: 4,
              background: selectedAgent === agent.id ? 'rgba(245,166,35,0.2)' : 'rgba(255,255,255,0.04)',
              fontSize: 9,
              fontWeight: 600,
            }}>
              {agent.icon}
            </span>
            {agent.label}
          </button>
        ))}
      </div>

      {/* Scrollable messages — flex: 1 + minHeight: 0 keeps it from overflowing the column */}
      <div style={{ flex: 1, overflowY: 'auto', minHeight: 0, padding: '16px 0' }}>
        <div style={{ maxWidth: 720, margin: '0 auto', padding: '0 20px' }}>
            {/* Proactive recommendation banner — always visible when proposals exist */}
            {history.length > 0 && (() => {
              const autoMode = configData?.system?.autonomy_mode || 'suggest';
              if (autoMode === 'manual') return null;
              const props = learningProposals?.proposals || [];
              const pCount = props.length;
              if (!pCount) return null;
              return (
                <div style={{ marginBottom: 12, padding: '10px 14px', borderRadius: 8, background: 'rgba(245,166,35,0.08)', border: '1px solid rgba(245,166,35,0.2)' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6 }}>
                    <span style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--accent)', display: 'inline-block', animation: 'pulse 2s ease-in-out infinite' }} />
                    <span style={{ fontWeight: 600, fontSize: 'var(--text-xs)', color: 'var(--accent)' }}>{pCount} scoring refinement{pCount > 1 ? 's' : ''} based on your feedback</span>
                  </div>
                  <button
                    onClick={() => send('Walk me through the scoring refinement proposals. What patterns did you find in my feedback and what do you think should be different?')}
                    style={{ padding: '4px 12px', fontSize: 'var(--text-xs)', color: 'var(--accent)', background: 'rgba(245,166,35,0.1)', border: '1px solid var(--accent-muted)', borderRadius: 4, cursor: 'pointer', fontFamily: 'var(--font-ui)' }}
                  >
                    Let's discuss these →
                  </button>
                </div>
              );
            })()}
            {/* Welcome message if no history */}
            {history.length === 0 && (
              <div style={{
                padding: '12px 16px',
                borderRadius: 12,
                marginBottom: 8,
                lineHeight: 1.6,
                fontSize: 'var(--text-sm)',
                background: 'rgba(255,255,255,0.02)',
                border: '1px solid var(--border)',
              }}>
                <div style={{ fontFamily: 'var(--font-data)', fontSize: 10, color: 'var(--text-muted)', letterSpacing: '0.06em', textTransform: 'uppercase' as const, marginBottom: 5 }}>
                  FundOps
                </div>
                {strategyData?.strategy ? (
                  <>
                    Your strategy is loaded. Click any agent above to see its configuration, or just tell me what you want to change.
                    {/* Proactive recommendation — only in suggest/autopilot mode */}
                    {(() => {
                      const autoMode = configData?.system?.autonomy_mode || 'suggest';
                      if (autoMode === 'manual') return null;
                      const proposals = learningProposals?.proposals || [];
                      const pCount = proposals.length;
                      const hasDrift = learningDrift?.has_enough_data && (
                        (learningDrift.style_drift?.length > 0) ||
                        (learningDrift.signal_drift?.length > 0) ||
                        (learningDrift.anti_signal_violations?.length > 0)
                      );
                      if (!pCount && !hasDrift) return null;
                      return (
                        <div style={{ marginTop: 12, padding: '10px 14px', borderRadius: 8, background: 'rgba(245,166,35,0.08)', border: '1px solid rgba(245,166,35,0.2)' }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6 }}>
                            <span style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--accent)', display: 'inline-block', animation: 'pulse 2s ease-in-out infinite' }} />
                            <span style={{ fontWeight: 600, fontSize: 'var(--text-xs)', color: 'var(--accent)' }}>I have recommendations</span>
                          </div>
                          {pCount > 0 && (
                            <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-secondary)', marginBottom: 4 }}>
                              {pCount} scoring refinement{pCount > 1 ? 's' : ''} based on your feedback patterns:
                              <ul style={{ margin: '6px 0 0', paddingLeft: 16, listStyle: 'none' }}>
                                {proposals.slice(0, 3).map((p: any, i: number) => (
                                  <li key={i} style={{ marginBottom: 4, lineHeight: 1.4 }}>
                                    <span style={{ color: 'var(--text-muted)' }}>{p.pattern_count} {p.pattern_tag === 'scoring_mismatch' ? 'high-score dismissals' : `"${p.pattern_tag}" dismissals`}:</span>{' '}
                                    <span style={{ color: 'var(--text-primary)' }}>{p.proposal?.split('.')[0]}.</span>
                                  </li>
                                ))}
                              </ul>
                              <button
                                onClick={() => send('Walk me through the scoring refinement proposals. What patterns did you find in my feedback and what do you think should be different?')}
                                style={{ marginTop: 8, padding: '4px 12px', fontSize: 'var(--text-xs)', color: 'var(--accent)', background: 'rgba(245,166,35,0.1)', border: '1px solid var(--accent-muted)', borderRadius: 4, cursor: 'pointer', fontFamily: 'var(--font-ui)' }}
                              >
                                Let's discuss these →
                              </button>
                            </div>
                          )}
                          {hasDrift && (
                            <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-secondary)' }}>
                              Behavioral drift detected — your IC decisions may be diverging from your stated strategy.{' '}
                              <button
                                onClick={() => send('Walk me through the behavioral drift you detected. How are my IC decisions diverging from my strategy?')}
                                style={{ padding: '2px 8px', fontSize: 'var(--text-xs)', color: 'var(--accent)', background: 'none', border: '1px solid var(--accent-muted)', borderRadius: 4, cursor: 'pointer', fontFamily: 'var(--font-ui)' }}
                              >
                                Explain →
                              </button>
                            </div>
                          )}
                        </div>
                      );
                    })()}
                  </>
                ) : (
                  <>
                    <div style={{ marginBottom: 10 }}>Welcome to FundOps. Three things to get started:</div>
                    <div style={{ display: 'grid', gap: 8, marginBottom: 10 }}>
                      <div style={{ display: 'flex', gap: 10, alignItems: 'flex-start' }}>
                        <span style={{ background: 'var(--accent)', color: '#0a0a0f', borderRadius: '50%', width: 20, height: 20, display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: 'var(--font-data)', fontSize: 11, fontWeight: 700, flexShrink: 0, marginTop: 1 }}>1</span>
                        <div>
                          <span style={{ fontWeight: 600 }}>Add your AI API key</span>
                          <span style={{ color: 'var(--text-muted)' }}> — go to <a href="/settings" style={{ color: 'var(--accent)', textDecoration: 'none' }}>Settings → AI Model</a> and paste your OpenAI (or Anthropic) key. The AI won't respond without it.</span>
                        </div>
                      </div>
                      <div style={{ display: 'flex', gap: 10, alignItems: 'flex-start' }}>
                        <span style={{ background: 'var(--bg-tertiary)', color: 'var(--text-muted)', borderRadius: '50%', width: 20, height: 20, display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: 'var(--font-data)', fontSize: 11, fontWeight: 700, flexShrink: 0, marginTop: 1 }}>2</span>
                        <div>
                          <span style={{ fontWeight: 500, color: 'var(--text-secondary)' }}>Tell me your strategy</span>
                          <span style={{ color: 'var(--text-muted)' }}> — describe your approach below. What kind of investor are you? What return do you target? What do you avoid?</span>
                        </div>
                      </div>
                      <div style={{ display: 'flex', gap: 10, alignItems: 'flex-start' }}>
                        <span style={{ background: 'var(--bg-tertiary)', color: 'var(--text-muted)', borderRadius: '50%', width: 20, height: 20, display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: 'var(--font-data)', fontSize: 11, fontWeight: 700, flexShrink: 0, marginTop: 1 }}>3</span>
                        <div>
                          <_Link to="/screener" style={{ fontWeight: 500, color: 'var(--accent)', textDecoration: 'none' }}>Run the Screener →</_Link>
                          <span style={{ color: 'var(--text-muted)' }}> — it will surface candidates that fit your strategy. The pipeline (Thesis → IC Review → Memo) runs from there.</span>
                        </div>
                      </div>
                    </div>
                    <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-muted)', borderTop: '1px solid var(--border)', paddingTop: 8 }}>
                      Try: "I'm a concentrated value investor. I target 20% annual returns. I look for quality businesses with high ROIC that are temporarily cheap. I avoid high leverage and commodity businesses."
                    </div>
                  </>
                )}
              </div>
            )}

            {history.map((entry, index) => (
              <div
                key={`${entry.role}-${index}`}
                style={{
                  padding: '12px 16px',
                  borderRadius: 12,
                  marginBottom: 8,
                  lineHeight: 1.6,
                  fontSize: 'var(--text-sm)',
                  ...(entry.role === 'user'
                    ? { background: 'rgba(245,166,35,0.06)', border: '1px solid rgba(245,166,35,0.12)', maxWidth: '80%', marginLeft: 'auto' }
                    : { background: 'rgba(255,255,255,0.02)', border: '1px solid var(--border)' }),
                }}
              >
                <div style={{ fontFamily: 'var(--font-data)', fontSize: 10, color: 'var(--text-muted)', letterSpacing: '0.06em', textTransform: 'uppercase' as const, marginBottom: 5 }}>
                  {entry.role === 'assistant' ? 'FundOps' : 'You'}
                </div>
                <div style={{ whiteSpace: 'pre-wrap' }} dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(entry.content.replace(/\n/g, '<br>')) }} />
              </div>
            ))}

            {isPending && (
              <div style={{
                padding: '12px 16px',
                borderRadius: 12,
                background: pendingIntent === 'wiring'
                  ? 'rgba(245,166,35,0.06)'
                  : 'rgba(255,255,255,0.02)',
                border: `1px solid ${pendingIntent === 'wiring' ? 'rgba(245,166,35,0.2)' : 'var(--border)'}`,
                fontSize: 'var(--text-sm)',
                color: pendingIntent === 'wiring' ? 'var(--accent)' : 'var(--text-muted)',
                display: 'flex',
                alignItems: 'center',
                gap: 8,
              }}>
                <span style={{
                  display: 'inline-block',
                  width: 8, height: 8, borderRadius: '50%',
                  background: pendingIntent === 'wiring' ? 'var(--accent)' : 'var(--text-muted)',
                  animation: 'pulse 1.2s ease-in-out infinite',
                }} />
                {pendingLabel}
              </div>
            )}

            {lastActionResult && (
              <div style={{
                padding: '10px 14px',
                borderRadius: 10,
                background: 'rgba(52,168,83,0.08)',
                border: '1px solid rgba(52,168,83,0.25)',
                fontSize: 'var(--text-xs)',
                color: 'var(--positive)',
                display: 'flex',
                alignItems: 'center',
                gap: 8,
              }}>
                <span>✓</span>
                <span>
                  {lastActionResult.isComplete
                    ? 'Strategy saved and wired into all agents.'
                    : `Settings applied: ${lastActionResult.applied.join(', ')}.`}
                </span>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>
      </div>

      {/* Input bar — pinned at bottom, never scrolls */}
      <form onSubmit={onSubmit} style={{ padding: '12px 20px', borderTop: '1px solid var(--border)', flexShrink: 0 }}>
          <div style={{ maxWidth: 720, margin: '0 auto', display: 'flex', gap: 8 }}>
            <input
              type="text"
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              placeholder="Change a setting, ask a question, or discuss your approach..."
              style={{
                flex: 1,
                padding: '12px 16px',
                background: 'var(--bg-tertiary)',
                border: '1px solid var(--border)',
                borderRadius: 'var(--radius-lg)',
                color: 'var(--text-primary)',
                fontFamily: 'var(--font-ui)',
                fontSize: 'var(--text-sm)',
                outline: 'none',
              }}
            />
            <button className="btn btn-accent" type="submit" disabled={isPending || !message.trim()}>
              Send
            </button>
          </div>
        </form>

      {/* Agent overlay */}
      {selectedAgent && (
        <AgentOverlay
          agentId={selectedAgent}
          onClose={() => setSelectedAgent(null)}
        />
      )}
    </div>
  );
}
