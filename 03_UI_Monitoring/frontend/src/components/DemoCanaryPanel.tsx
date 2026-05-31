import React from 'react'
import { DemoCanaryState, fetchDemoCanary } from '../services/api'
import TruthBadge from './TruthBadge'
import LoadingBar from './LoadingBar'

const colors = {
  bg: '#0d1726',
  panelBg: 'rgba(13,23,38,0.92)',
  border: 'rgba(255,255,255,0.08)',
  text: '#eef5ff',
  muted: '#97a9c6',
  cyan: '#5ad7ff',
  green: '#39d98a',
  amber: '#f3bb4a',
  red: '#ff7b8f',
}

const panelStyle: React.CSSProperties = {
  background: colors.panelBg,
  border: `1px solid ${colors.border}`,
  borderRadius: 10,
  padding: 16,
}

function fmtMoney(v: number | null | undefined): string {
  if (v == null || isNaN(v)) return '--'
  return v.toFixed(2)
}

function fmtPct(v: number | null | undefined): string {
  if (v == null || isNaN(v)) return '--'
  return `${(v * 100).toFixed(1)}%`
}

const DemoCanaryPanel: React.FC = () => {
  const [state, setState] = React.useState<DemoCanaryState | null>(null)
  const [loading, setLoading] = React.useState(true)

  React.useEffect(() => {
    let cancelled = false
    const load = async () => {
      setLoading(true)
      try {
        const data = await fetchDemoCanary()
        if (!cancelled) setState(data)
      } catch {
        if (!cancelled) setState(null)
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    const id = setInterval(load, 15_000)
    return () => { cancelled = true; clearInterval(id) }
  }, [])

  const metrics = state?.metrics

  return (
    <div style={{ background: colors.bg, color: colors.text, padding: 20 }}>
      <h2 style={{ margin: '0 0 16px', fontSize: 18, color: colors.cyan, fontWeight: 700 }}>
        Demo Canary
      </h2>

      {loading && !state && <LoadingBar label="Loading demo canary..." />}
      {!loading && !state && (
        <div style={{ ...panelStyle, color: colors.muted }}>
          No demo canary data available. The endpoint returned empty.
        </div>
      )}

      {state && (
        <>
          <div style={{ ...panelStyle, display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap', marginBottom: 16 }}>
            <TruthBadge tone="blue" label="DEMO" dot={false} />
            <TruthBadge tone="red" label="REAL MONEY LOCKED" dot={false} />
            <span style={{ fontSize: 12, color: colors.muted }}>
              This is the demo execution dashboard. No real capital is at risk.
            </span>
          </div>

          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))',
              gap: 12,
              marginBottom: 16,
            }}
          >
            {[
              { label: 'Trades', value: metrics?.trades ?? '--' },
              { label: 'Days', value: metrics?.days ?? '--' },
              { label: 'PnL', value: `$${fmtMoney(metrics?.pnl)}` },
              { label: 'Drawdown', value: `${fmtMoney(metrics?.drawdown)}%` },
              { label: 'Profit Factor', value: metrics?.profit_factor != null ? fmtMoney(metrics.profit_factor) : '--' },
              { label: 'Win Rate', value: fmtPct(metrics?.win_rate) },
            ].map((kpi) => (
              <div key={kpi.label} style={{ ...panelStyle, textAlign: 'center' }}>
                <div style={{ fontSize: 11, color: colors.muted, textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 4 }}>
                  {kpi.label}
                </div>
                <div style={{ fontSize: 20, fontWeight: 700, color: colors.text }}>{kpi.value}</div>
              </div>
            ))}
          </div>

          <div style={panelStyle}>
            <h3 style={{ margin: '0 0 12px', fontSize: 14, color: colors.muted, fontWeight: 600 }}>Timeline</h3>
            {(state.timeline ?? []).length === 0 ? (
              <div style={{ color: colors.muted, fontSize: 13 }}>No timeline events yet.</div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {state.timeline.map((ev, idx) => {
                  const s = ev.status.toLowerCase()
                  const tone = s === 'passed' || s === 'complete' ? 'green' : s === 'failed' || s === 'blocked' ? 'red' : 'yellow'
                  return (
                    <div
                      key={idx}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: 10,
                        padding: '8px 10px',
                        background: 'rgba(20,32,52,0.6)',
                        borderRadius: 6,
                        borderLeft: `3px solid ${tone === 'green' ? colors.green : tone === 'red' ? colors.red : colors.amber}`,
                      }}
                    >
                      <div style={{ flex: 1 }}>
                        <div style={{ fontWeight: 600, fontSize: 13 }}>{ev.step}</div>
                        <div style={{ fontSize: 11, color: colors.muted, marginTop: 2 }}>{ev.detail}</div>
                      </div>
                      <TruthBadge tone={tone} label={ev.status} dot={false} />
                      <div style={{ fontSize: 11, color: colors.muted, fontFamily: 'monospace', whiteSpace: 'nowrap' }}>
                        {ev.ts}
                      </div>
                    </div>
                  )
                })}
              </div>
            )}
          </div>
        </>
      )}
    </div>
  )
}

export default DemoCanaryPanel
