import React from 'react'
import { fetchExecutionDecisions, fetchExecutionLive, fetchExecutionFeedback, fetchTimingInsights } from '../services/api'

/**
 * DecisionExecutionPanel — Rich visibility into Decision PPO outputs + ExecutionAgent.
 * Displays:
 *  - Recent TradeDecisions with full specs (size mode, SL/TP types, trailing, ladders)
 *  - Current managed positions (per-decision attribution)
 *  - Live execution feedback stream
 * Works for both pure-Python execution and MQL5 command bridge (data from FS artifacts + live agent status).
 */
export default function DecisionExecutionPanel() {
  const [data, setData] = React.useState<any>({ decisions: [], count: 0 })
  const [live, setLive] = React.useState<any>(null)
  const [feedback, setFeedback] = React.useState<any>(null)
  const [timing, setTiming] = React.useState<any>(null)
  const [loading, setLoading] = React.useState(true)

  React.useEffect(() => {
    let mounted = true
    const load = async () => {
      setLoading(true)
      try {
        const [decs, liv, fb, tim] = await Promise.all([
          fetchExecutionDecisions(12),
          fetchExecutionLive(),
          fetchExecutionFeedback(10),
          fetchTimingInsights(),
        ])
        if (mounted) {
          setData(decs)
          setLive(liv)
          setFeedback(fb)
          setTiming(tim)
        }
      } catch (e) {
        if (mounted) setData({ decisions: [], count: 0, error: String(e) })
      } finally {
        if (mounted) setLoading(false)
      }
    }
    load()
    const id = setInterval(load, 8000) // live refresh
    return () => { mounted = false; clearInterval(id) }
  }, [])

  const decisions: any[] = data?.decisions ?? []
  const active = live?.active_decisions || live?.active || []

  return (
    <div style={{ padding: 12, background: '#0b0f14', border: '1px solid #334155', borderRadius: 8 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
        <strong style={{ color: '#c026ff' }}>Decision PPO + ExecutionAgent — Rich Telemetry</strong>
        <span style={{ fontSize: 11, color: '#64748b' }}>
          {loading ? 'updating…' : `${decisions.length} recent • ${active.length || 0} managed`} | Python + MQL5 bridge
        </span>
      </div>

      {/* Recent Rich Decisions Table (with TimeExitSpec for news/opens timing) */}
      <div style={{ marginBottom: 12, overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
          <thead>
            <tr style={{ background: '#1e2937', color: '#94a3b8' }}>
              <th style={{ textAlign: 'left', padding: 4 }}>Decision ID</th>
              <th style={{ textAlign: 'left', padding: 4 }}>Symbol/Side</th>
              <th style={{ textAlign: 'left', padding: 4 }}>Size</th>
              <th style={{ textAlign: 'left', padding: 4 }}>SL/TP</th>
              <th style={{ textAlign: 'left', padding: 4 }}>Trailing</th>
              <th style={{ textAlign: 'left', padding: 4, color: '#67e8f9' }}>TimeExit (news/open)</th>
              <th style={{ textAlign: 'left', padding: 4 }}>PnL / Vol</th>
              <th style={{ textAlign: 'left', padding: 4 }}>Status</th>
            </tr>
          </thead>
          <tbody>
            {decisions.length === 0 && (
              <tr><td colSpan={8} style={{ padding: 8, color: '#64748b' }}>No rich decisions yet. Arm harness with decision_ppo or submit via ExecutionAgent.</td></tr>
            )}
            {decisions.slice(0, 8).map((d: any, i: number) => {
              const dec = d.decision || d
              const sz = dec.size || {}
              const sl = dec.sl || {}
              const tp = dec.tp || {}
              const tr = dec.trailing || {}
              const tx = dec.time_exit || {}
              const rep = d
              // Format TimeExit flags for news/opens/session visibility
              const txParts: string[] = []
              if (tx.close_before_high_impact_news) txParts.push('NEWS')
              if (tx.close_at_session_end) txParts.push('SESS')
              if (tx.close_at_eod) txParts.push('EOD')
              if (tx.max_hold_minutes) txParts.push('m' + tx.max_hold_minutes)
              const txStr = txParts.length ? txParts.join(',') : 'std'
              return (
                <tr key={i} style={{ borderTop: '1px solid #1e2937', color: '#e2e8f0' }}>
                  <td style={{ padding: 3, fontFamily: 'monospace', fontSize: 10 }}>{(dec.decision_id || d.decision_id || '').slice(0, 14)}</td>
                  <td style={{ padding: 3 }}>{dec.symbol || '?'} {dec.side || ''}</td>
                  <td style={{ padding: 3 }}>{sz.mode || '?'}:{Number(sz.value || 0).toFixed(3)}</td>
                  <td style={{ padding: 3, color: '#f87171' }}>{sl.type || '?'}:{tp.type || '?'}</td>
                  <td style={{ padding: 3 }}>{tr.type || 'none'}</td>
                  <td style={{ padding: 3, color: '#67e8f9', fontWeight: txParts.length ? 600 : 400 }}>{txStr}</td>
                  <td style={{ padding: 3 }}>{Number(rep.realized_pnl || 0).toFixed(2)} / {Number(rep.open_volume || 0).toFixed(2)}</td>
                  <td style={{ padding: 3 }}>{rep.status || '—'}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      {/* Current Managed Positions with Specs + TimeExit timing */}
      <div style={{ marginBottom: 10 }}>
        <div style={{ fontSize: 12, color: '#22c55e', marginBottom: 4 }}>Current Managed Positions (TradeDecision attribution + TimeExit for news/opens)</div>
        {active && Object.keys(active).length > 0 ? (
          <div style={{ fontSize: 11, color: '#cbd5e1' }}>
            {Object.entries(active).slice(0, 4).map(([did, td]: [string, any]) => {
              const tx = td?.time_exit || {}
              const txFlags = []
              if (tx.close_before_high_impact_news) txFlags.push('NEWS')
              if (tx.close_at_session_end) txFlags.push('SESS')
              const txNote = txFlags.length ? ' time=' + txFlags.join(',') : ''
              return <div key={did} style={{ marginBottom: 2 }}>
                {did.slice(0,12)} {td?.symbol} {td?.side} • trail={td?.trailing?.type || 'n/a'}{txNote} • conf={td?.confidence || '—'}
              </div>
            })}
          </div>
        ) : (
          <div style={{ fontSize: 11, color: '#64748b' }}>No active managed positions (or live agent_status not yet populated — actions via harness/ExecutionAgent populate it).</div>
        )}
      </div>

      {/* Feedback Stream */}
      <div>
        <div style={{ fontSize: 12, color: '#eab308', marginBottom: 4 }}>Execution Feedback Stream (recent events)</div>
        <div style={{ fontSize: 10, fontFamily: 'monospace', color: '#94a3b8', maxHeight: 92, overflow: 'auto', background: '#111827', padding: 6, borderRadius: 4 }}>
          {(feedback?.feedback || []).slice(0, 6).map((f: any, idx: number) => (
            <div key={idx}>{f.ts?.slice(11,19)} {f.event} {String(f.decision_id || '').slice(0,10)} → {(f.report?.status || '')}</div>
          ))}
          {(!feedback || !feedback.feedback || feedback.feedback.length === 0) && 'No feedback events yet.'}
        </div>
      </div>

      {/* NEW: Timing Analyzer Insights (profitable opens/news/session patterns) visible in React UI */}
      <div style={{ marginTop: 10, paddingTop: 8, borderTop: '1px solid #334155' }}>
        <div style={{ fontSize: 12, color: '#67e8f9', marginBottom: 4 }}>Timing Analyzer Insights (Opens / News / Sessions — feeds Dreamer/Rainforest/PPO)</div>
        <div style={{ fontSize: 10, color: '#cbd5e1', background: '#111827', padding: 6, borderRadius: 4 }}>
          {timing && !timing.error ? (
            <>
              <div>Source: {timing.source || 'live'}</div>
              {timing.best_hours_by_pnl && <div>Best hours: {JSON.stringify(timing.best_hours_by_pnl.slice(0,3).map((h:any)=>h.hour))}</div>}
              {timing.news_avoidance_recommendation && <div>News: {timing.news_avoidance_recommendation.suggestion}</div>}
              <div>Profitable in open windows: {timing.profitable_trades_in_open_windows ?? 0} / {timing.total_profitable_trades ?? 0}</div>
            </>
          ) : (
            <span style={{ color: '#64748b' }}>{timing?.error || 'No timing insights yet — run Decision PPO training to populate journal+analyzer.'}</span>
          )}
        </div>
      </div>

      <div style={{ marginTop: 8, fontSize: 10, color: '#475569' }}>
        Data: /api/execution/* (execution_reports/*.json + mql5_commands/decision_*.json + decision_ppo_execution_live.json + execution_feedback.jsonl) + /api/timing/insights. Full visibility for Decision PPO timing decisions (TimeExitSpec news/opens) + ExecutionAgent + analyzer insights.
      </div>
    </div>
  )
}
