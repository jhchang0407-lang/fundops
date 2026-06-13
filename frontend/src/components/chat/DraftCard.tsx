import type { CriterionRule, ProposalCard, VersionSummary } from '../../api/client';
import { humanizeLabel } from '../../utils/formatFinancials';
import { criterionRuleLine, humanize } from './criterionDisplay';
import type { SettingsRecord } from './criterionDisplay';
import { Fragment } from 'react';

export type DraftResolution = 'accepted' | 'rejected';

export function DraftCard({
  draft,
  activeVersion,
  pendingId,
  fromHistory,
  resolution,
  busy,
  onApprove,
  onRequestChanges,
  onCancel,
}: {
  draft: ProposalCard;
  activeVersion: VersionSummary | null | undefined;
  pendingId: string | null | undefined;
  fromHistory?: boolean;
  resolution?: DraftResolution;
  busy: boolean;
  onApprove: (id: string) => void;
  onRequestChanges: () => void;
  onCancel: (id: string) => void;
}) {
  const nextVersion = (activeVersion?.version_number ?? 0) + 1;
  // Drafts replayed from history are only actionable while still the pending
  // proposal. pendingId === undefined means the strategy query hasn't resolved
  // yet — don't mark anything stale until we know.
  const stale = !resolution && fromHistory === true && pendingId !== undefined && pendingId !== draft.id;
  const rules = draft.rules ?? [];

  return (
    <div className="draft-card">
      <div className="draft-card-header">
        <span>Strategy Draft — Proposal</span>
        <span className="locked-tag">awaiting approval</span>
      </div>
      <div className="draft-body">
        {draft.summary && (
          <div style={{ fontSize: 'var(--text-sm)', lineHeight: 1.6 }}>{draft.summary}</div>
        )}
        {draft.north_star && (
          <div style={{ marginTop: 6, fontSize: 'var(--text-xs)', color: 'var(--text-secondary)' }}>
            North star: {draft.north_star}
          </div>
        )}

        {rules.length > 0 && (
          <>
            <div className="draft-section-label">Rules</div>
            <div className="table-shell" style={{ boxShadow: 'none' }}>
              <table className="draft-rules-table">
                <thead>
                  <tr>
                    <th>Criterion</th>
                    <th>Rule</th>
                    <th>Interpretation</th>
                  </tr>
                </thead>
                <tbody>
                  {rules.map((r, i) => (
                    <tr key={r.criterion_id ?? i}>
                      <td>
                        <div style={{ fontWeight: 600, fontSize: 'var(--text-xs)' }}>
                          {r.metric_label ?? (r.metric ? humanizeLabel(r.metric) : humanize(r.kind))}
                        </div>
                        <div
                          style={{
                            fontFamily: 'var(--font-data)',
                            fontSize: 9,
                            color: 'var(--text-muted)',
                            textTransform: 'uppercase',
                            letterSpacing: '0.05em',
                          }}
                        >
                          {r.kind_label ?? humanize(r.kind)}
                          {r.data_support_level && r.data_support_level !== 'fully'
                            ? ` · ${humanize(r.data_support_level)}`
                            : ''}
                        </div>
                      </td>
                      <td className="rule-value">
                        {criterionRuleLine(r as CriterionRule & SettingsRecord)}
                      </td>
                      <td style={{ color: 'var(--text-secondary)', fontSize: 'var(--text-xs)' }}>
                        {r.interpretation ?? r.rule_rationale ?? '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}

        {draft.wiring_preview && Object.keys(draft.wiring_preview).length > 0 && (
          <>
            <div className="draft-section-label">Wiring preview</div>
            <dl className="wiring-dl">
              {Object.entries(draft.wiring_preview).map(([cap, line]) => (
                <Fragment key={cap}>
                  <dt>{humanize(cap)}</dt>
                  <dd>{line}</dd>
                </Fragment>
              ))}
            </dl>
          </>
        )}

        {(draft.unsupported_preferences?.length ?? 0) > 0 && (
          <>
            <div className="draft-section-label">Not enforceable with current data</div>
            <ul className="draft-muted-list">
              {draft.unsupported_preferences!.map((p, i) => (
                <li key={i}>{p}</li>
              ))}
            </ul>
          </>
        )}

        {(draft.tradeoffs?.length ?? 0) > 0 && (
          <>
            <div className="draft-section-label">Tradeoffs</div>
            {draft.tradeoffs!.map((t, i) => (
              <div key={i} className="draft-tradeoff">
                {t}
              </div>
            ))}
          </>
        )}

        <div className="draft-approval">
          {draft.approval_prompt && <div style={{ marginBottom: 6 }}>{draft.approval_prompt}</div>}
          <div
            style={{
              fontFamily: 'var(--font-data)',
              fontSize: 'var(--text-xs)',
              color: 'var(--accent)',
            }}
          >
            Approving creates Constitution v{nextVersion} and wires these settings. Nothing changes
            until you approve.
          </div>
        </div>

        {resolution === 'accepted' && (
          <div style={{ marginTop: 8, fontSize: 'var(--text-xs)', color: 'var(--positive)' }}>
            Approved — Constitution activated.
          </div>
        )}
        {resolution === 'rejected' && (
          <div style={{ marginTop: 8, fontSize: 'var(--text-xs)', color: 'var(--text-muted)' }}>
            Cancelled — nothing was changed.
          </div>
        )}
        {stale && (
          <div style={{ marginTop: 8, fontSize: 'var(--text-xs)', color: 'var(--text-muted)' }}>
            This draft is no longer pending.
          </div>
        )}

        {!resolution && !stale && (
          <div className="draft-actions">
            <button
              className="btn btn-accent"
              disabled={busy}
              onClick={() => onApprove(draft.id)}
            >
              Approve
            </button>
            <button className="btn" disabled={busy} onClick={onRequestChanges}>
              Request changes
            </button>
            <button
              className="btn btn-ghost"
              disabled={busy}
              style={{ color: 'var(--text-muted)' }}
              onClick={() => onCancel(draft.id)}
            >
              Cancel
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
