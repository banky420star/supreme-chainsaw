import React from 'react'
import { PromotionGateItem, fetchPromotionGates } from '../services/api'
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
  red: '#ff7b8f',
}

const panelStyle: React.CSSProperties = {
  background: colors.panelBg,
  border: `1px solid ${colors.border}`,
  borderRadius: 10,
  padding: 16,
}

const PromotionGatesPanel: React.FC = () => {
  const [gates, setGates] = React.useState<PromotionGateItem[]>([])
  const [loading, setLoading] = React.useState(true)

  React.useEffect(() => {
    let cancelled = false
    const load = async () => {
      setLoading(true)
      try {
        const data = await fetchPromotionGates()
        if (!cancelled) setGates(Array.isArray(data) ? data : [])
      } catch {
        if (!cancelled) setGates([])
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    const id = setInterval(load, 15_000)
    return () => { cancelled = true; clearInterval(id) }
  }, [])

  const passedCount = gates.filter((g) => g.passed).length
  const totalCount = gates.length

  return (
    <div style={{ background: colors.bg, color: colors.text, padding: 20 }}>
      <h2 style={{ margin: '0 0 16px', fontSize: 18, color: colors.cyan, fontWeight: 700 }}>
        Promotion Gates
      </h2>

      {loading && gates.length === 0 && <LoadingBar label="Loading promotion gates..." />}
      {!loading && gates.length === 0 && (
        <div style={{ ...panelStyle, color: colors.muted }}>
          No promotion gates configured. The endpoint returned empty.
        </div>
      )}

      {gates.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          <div style={{ ...panelStyle, display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap' }}>
            <TruthBadge
              tone={passedCount === totalCount ? 'green' : passedCount > 0 ? 'yellow' : 'red'}
              label={`${passedCount} / ${totalCount} PASSED`}
              dot={false}
            />
            <span style={{ fontSize: 12, color: colors.muted }}>
              {passedCount === totalCount
                ? 'All gates cleared — bundle is promotable.'
                : `${totalCount - passedCount} gate(s) blocking promotion.`}
            </span>
          </div>

          {gates.map((g, idx) => (
            <div
              key={idx}
              style={{
                ...panelStyle,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                gap: 12,
                background: g.passed ? 'rgba(0,255,136,0.03)' : 'rgba(255,51,102,0.03)',
                borderLeft: `3px solid ${g.passed ? colors.green : colors.red}`,
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, flex: 1 }}>
                <span
                  style={{
                    width: 18,
                    height: 18,
                    borderRadius: '50%',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    background: g.passed ? colors.green : colors.red,
                    color: '#000',
                    fontSize: 10,
                    fontWeight: 800,
                    flexShrink: 0,
                  }}
                >
                  {g.passed ? '✓' : '✕'}
                </span>
                <span style={{ fontSize: 13, fontWeight: 600 }}>{g.gate}</span>
                {g.pending && <span style={{ fontSize: 10, color: colors.cyan, border: `1px solid ${colors.cyan}30`, padding: '1px 4px', borderRadius: 4 }}>PENDING</span>}
              </div>
              <div style={{ fontSize: 11, color: colors.muted, fontFamily: 'monospace', textAlign: 'right' }}>
                required: {String(g.required)} | actual: {g.actual != null ? String(g.actual) : '--'}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export default PromotionGatesPanel
