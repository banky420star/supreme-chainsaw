import React from 'react'
import { PatternRecord, PatternVerification, fetchPatternsVerified } from '../services/api'
import { LSTMExplanation } from '../services/api'
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

interface Props {
  patterns: PatternRecord[]
  status: import('../types').StatusPayload
  lstmExpl: Record<string, LSTMExplanation>
}

const PatternsPanel: React.FC<Props> = ({ patterns, status, lstmExpl }) => {
  const [verified, setVerified] = React.useState<PatternVerification[]>([])
  const [loading, setLoading] = React.useState(true)

  React.useEffect(() => {
    let cancelled = false
    const load = async () => {
      setLoading(true)
      try {
        const data = await fetchPatternsVerified()
        if (!cancelled) setVerified(Array.isArray(data) ? data : [])
      } catch {
        if (!cancelled) setVerified([])
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    const id = setInterval(load, 15_000)
    return () => { cancelled = true; clearInterval(id) }
  }, [])

  const verifiedCount = verified.filter((p) => p.verified).length
  const fallbackCount = verified.reduce((sum, p) => sum + (p.fallback_incidents ?? 0), 0)

  return (
    <div style={{ background: colors.bg, color: colors.text, padding: 20 }}>
      <h2 style={{ margin: '0 0 16px', fontSize: 18, color: colors.cyan, fontWeight: 700 }}>
        Patterns
      </h2>

      <div style={{ ...panelStyle, display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap', marginBottom: 16 }}>
        <div style={{ textAlign: 'center', minWidth: 80 }}>
          <div style={{ fontSize: 11, color: colors.muted, textTransform: 'uppercase', letterSpacing: 0.5 }}>Discovered</div>
          <div style={{ fontSize: 22, fontWeight: 700, color: colors.text }}>{patterns.length}</div>
        </div>
        <div style={{ textAlign: 'center', minWidth: 80 }}>
          <div style={{ fontSize: 11, color: colors.muted, textTransform: 'uppercase', letterSpacing: 0.5 }}>Verified</div>
          <div style={{ fontSize: 22, fontWeight: 700, color: colors.green }}>{verifiedCount}</div>
        </div>
        <div style={{ textAlign: 'center', minWidth: 80 }}>
          <div style={{ fontSize: 11, color: colors.muted, textTransform: 'uppercase', letterSpacing: 0.5 }}>Fallback Incidents</div>
          <div style={{ fontSize: 22, fontWeight: 700, color: fallbackCount > 0 ? colors.red : colors.text }}>{fallbackCount}</div>
        </div>
      </div>

      <div style={panelStyle}>
        <h3 style={{ margin: '0 0 12px', fontSize: 14, color: colors.muted, fontWeight: 600 }}>Verified Patterns</h3>
        {loading && verified.length === 0 && <LoadingBar label="Loading verified patterns..." />}
        {!loading && verified.length === 0 && (
          <div style={{ color: colors.muted }}>No verified patterns yet.</div>
        )}
        {verified.length > 0 && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {verified.map((p) => (
              <div
                key={p.pattern_id}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  padding: '8px 10px',
                  background: 'rgba(20,32,52,0.6)',
                  borderRadius: 6,
                  borderLeft: `3px solid ${p.verified ? colors.green : colors.amber}`,
                }}
              >
                <div style={{ flex: 1 }}>
                  <div style={{ fontWeight: 600, fontSize: 13 }}>
                    {p.pattern_name}
                    <span style={{ fontSize: 10, color: colors.muted, marginLeft: 8 }}>{p.pattern_id.slice(0, 8)}</span>
                  </div>
                  <div style={{ fontSize: 11, color: colors.muted, marginTop: 2 }}>
                    regime: {p.regime} | outcome: {p.outcome}
                  </div>
                </div>
                <TruthBadge tone={p.verified ? 'green' : 'yellow'} label={p.verified ? 'VERIFIED' : 'UNVERIFIED'} dot={false} />
                <div style={{ fontSize: 11, color: colors.muted, fontFamily: 'monospace', marginLeft: 10 }}>
                  conf: {p.confidence != null ? p.confidence.toFixed(2) : '--'}
                </div>
                {p.fallback_incidents > 0 && (
                  <div style={{ fontSize: 11, color: colors.red, marginLeft: 10 }}>
                    {p.fallback_incidents} fallback
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      <div style={{ ...panelStyle, marginTop: 16 }}>
        <h3 style={{ margin: '0 0 12px', fontSize: 14, color: colors.muted, fontWeight: 600 }}>LSTM Explanations</h3>
        {Object.keys(lstmExpl).length === 0 ? (
          <div style={{ color: colors.muted }}>No LSTM explanations available.</div>
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))', gap: 10 }}>
            {Object.entries(lstmExpl).map(([symbol, expl]) => (
              <div key={symbol} style={{ background: colors.bg, borderRadius: 6, padding: 10, border: `1px solid ${colors.border}` }}>
                <div style={{ fontSize: 13, fontWeight: 700, color: colors.cyan, marginBottom: 4 }}>{symbol}</div>
                <div style={{ fontSize: 11, color: colors.muted, marginBottom: 4 }}>
                  Regime: <span style={{ color: colors.text }}>{expl.regime}</span>
                </div>
                <div style={{ fontSize: 11, color: colors.muted, marginBottom: 4 }}>
                  Confidence: <span style={{ color: colors.text }}>{expl.confidence?.toFixed(3) ?? '--'}</span>
                </div>
                {expl.top_indicators && expl.top_indicators.length > 0 && (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                    {expl.top_indicators.slice(0, 3).map((ind) => (
                      <div key={ind.indicator} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, fontFamily: 'monospace' }}>
                        <span style={{ color: colors.muted }}>{ind.indicator}</span>
                        <span style={{ color: colors.text }}>{ind.importance.toFixed(3)}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

export default PatternsPanel
