import React from 'react'
import { TradeCoronerState, fetchTradeCoroner } from '../services/api'
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

const TradeCoronerPanel: React.FC = () => {
  const [state, setState] = React.useState<TradeCoronerState | null>(null)
  const [loading, setLoading] = React.useState(true)

  React.useEffect(() => {
    let cancelled = false
    const load = async () => {
      setLoading(true)
      try {
        const data = await fetchTradeCoroner()
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

  const clusters = state?.clusters ?? []

  return (
    <div style={{ background: colors.bg, color: colors.text, padding: 20 }}>
      <h2 style={{ margin: '0 0 16px', fontSize: 18, color: colors.cyan, fontWeight: 700 }}>
        Trade Coroner
      </h2>

      {loading && !state && <LoadingBar label="Loading trade coroner..." />}
      {!loading && !state && (
        <div style={{ ...panelStyle, color: colors.muted }}>
          No trade coroner data available. The endpoint returned empty.
        </div>
      )}

      {state && (
        <>
          <div style={{ ...panelStyle, display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap', marginBottom: 16 }}>
            <div style={{ textAlign: 'center', minWidth: 80 }}>
              <div style={{ fontSize: 11, color: colors.muted, textTransform: 'uppercase', letterSpacing: 0.5 }}>Mistakes</div>
              <div style={{ fontSize: 22, fontWeight: 700, color: colors.red }}>{state.total_mistakes}</div>
            </div>
            <div style={{ textAlign: 'center', minWidth: 80 }}>
              <div style={{ fontSize: 11, color: colors.muted, textTransform: 'uppercase', letterSpacing: 0.5 }}>Reviewed</div>
              <div style={{ fontSize: 22, fontWeight: 700, color: colors.text }}>{state.total_reviewed}</div>
            </div>
            <div style={{ textAlign: 'center', minWidth: 80 }}>
              <div style={{ fontSize: 11, color: colors.muted, textTransform: 'uppercase', letterSpacing: 0.5 }}>Clusters</div>
              <div style={{ fontSize: 22, fontWeight: 700, color: colors.amber }}>{clusters.length}</div>
            </div>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {clusters.length === 0 ? (
              <div style={{ ...panelStyle, color: colors.muted }}>No mistake clusters found.</div>
            ) : (
              clusters.map((c) => (
                <div
                  key={c.cluster_id}
                  style={{
                    ...panelStyle,
                    borderLeft: `3px solid ${c.retraining_eligible ? colors.amber : colors.red}`,
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                    <span style={{ fontSize: 13, fontWeight: 700 }}>{c.cluster_id}</span>
                    <TruthBadge
                      tone={c.retraining_eligible ? 'yellow' : 'red'}
                      label={c.retraining_eligible ? 'RETRAINING ELIGIBLE' : 'NOT ELIGIBLE'}
                      dot={false}
                    />
                  </div>
                  <div style={{ fontSize: 12, color: colors.muted, marginBottom: 4 }}>
                    Count: <span style={{ color: colors.text, fontWeight: 600 }}>{c.count}</span>
                  </div>
                  <div style={{ fontSize: 12, color: colors.muted, marginBottom: 4 }}>
                    Root Cause: <span style={{ color: colors.text }}>{c.root_cause}</span>
                  </div>
                  <div style={{ fontSize: 12, color: colors.muted, marginBottom: 4 }}>
                    Symbols: <span style={{ color: colors.cyan }}>{c.affected_symbols.join(', ')}</span>
                  </div>
                  <div style={{ fontSize: 11, color: colors.amber }}>
                    Recommended Experiment: {c.recommended_experiment}
                  </div>
                </div>
              ))
            )}
          </div>
        </>
      )}
    </div>
  )
}

export default TradeCoronerPanel
