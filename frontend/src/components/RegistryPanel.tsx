import React from 'react'
import { ModelBundle, fetchRegistry } from '../services/api'
import TruthBadge from './TruthBadge'

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

const thStyle: React.CSSProperties = {
  textAlign: 'left',
  padding: '8px 10px',
  borderBottom: `1px solid ${colors.border}`,
  color: colors.muted,
  fontSize: 11,
  fontWeight: 600,
  textTransform: 'uppercase',
  letterSpacing: 0.5,
}

const tdStyle: React.CSSProperties = {
  padding: '7px 10px',
  fontSize: 13,
  color: colors.text,
  borderBottom: '1px solid rgba(255,255,255,0.03)',
}

function bundleTone(status?: string): any {
  if (!status) return 'gray'
  const s = status.toLowerCase()
  if (s === 'champion' || s === 'promoted' || s === 'live') return 'green'
  if (s === 'candidate' || s === 'canary' || s === 'review') return 'blue'
  if (s === 'rejected' || s === 'failed' || s === 'blocked') return 'red'
  if (s === 'stale' || s === 'unaudited') return 'yellow'
  return 'gray'
}

function fmtNum(v: number | null | undefined, digits = 4): string {
  if (v == null || isNaN(v)) return '--'
  return v.toFixed(digits)
}

const RegistryPanel: React.FC = () => {
  const [bundles, setBundles] = React.useState<ModelBundle[]>([])
  const [loading, setLoading] = React.useState(true)

  React.useEffect(() => {
    let cancelled = false
    const load = async () => {
      setLoading(true)
      try {
        const data = await fetchRegistry()
        if (!cancelled) setBundles(Array.isArray(data) ? data : [])
      } catch {
        if (!cancelled) setBundles([])
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    const id = setInterval(load, 15_000)
    return () => { cancelled = true; clearInterval(id) }
  }, [])

  return (
    <div style={{ background: colors.bg, color: colors.text, padding: 20 }}>
      <h2 style={{ margin: '0 0 16px', fontSize: 18, color: colors.cyan, fontWeight: 700 }}>
        Registry — Model Bundles
      </h2>

      {loading && bundles.length === 0 && (
        <div style={{ ...panelStyle, color: colors.muted }}>Loading registry...</div>
      )}
      {!loading && bundles.length === 0 && (
        <div style={{ ...panelStyle, color: colors.muted }}>
          No bundles in registry. The endpoint returned empty.
        </div>
      )}

      {bundles.length > 0 && (
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <thead>
              <tr>
                <th style={thStyle}>Bundle ID</th>
                <th style={thStyle}>Symbol</th>
                <th style={thStyle}>Timeframe</th>
                <th style={thStyle}>Status</th>
                <th style={thStyle}>Data</th>
                <th style={thStyle}>LSTM</th>
                <th style={thStyle}>RF</th>
                <th style={thStyle}>Dreamer</th>
                <th style={thStyle}>PPO</th>
                <th style={thStyle}>Backtest</th>
                <th style={thStyle}>Walk-Forward</th>
                <th style={thStyle}>Canary</th>
                <th style={thStyle}>Decision</th>
              </tr>
            </thead>
            <tbody>
              {bundles.map((b, idx) => (
                <tr key={b.bundle_id} style={{ background: idx % 2 === 0 ? 'transparent' : 'rgba(90,215,255,0.02)' }}>
                  <td style={{ ...tdStyle, fontFamily: 'monospace', fontSize: 11, maxWidth: 140, overflow: 'hidden', textOverflow: 'ellipsis' }}>
                    {b.bundle_id.slice(0, 16)}
                  </td>
                  <td style={tdStyle}><span style={{ color: colors.cyan, fontWeight: 600 }}>{b.symbol}</span></td>
                  <td style={tdStyle}>{b.timeframe}</td>
                  <td style={tdStyle}><TruthBadge tone={bundleTone(b.status)} label={b.status} dot={false} /></td>
                  <td style={tdStyle}>{b.data_source ?? '--'}</td>
                  <td style={tdStyle}>{b.lstm ?? '--'}</td>
                  <td style={tdStyle}>{b.rainforest ?? '--'}</td>
                  <td style={tdStyle}>{b.dreamer ?? '--'}</td>
                  <td style={tdStyle}>{b.ppo ?? '--'}</td>
                  <td style={tdStyle}>{fmtNum(b.backtest_return)}</td>
                  <td style={tdStyle}>{fmtNum(b.walk_forward)}</td>
                  <td style={tdStyle}>{fmtNum(b.canary)}</td>
                  <td style={tdStyle}>
                    {b.promotion_decision ? (
                      <TruthBadge tone={bundleTone(b.promotion_decision)} label={b.promotion_decision} dot={false} />
                    ) : (
                      <span style={{ color: colors.muted }}>--</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

export default RegistryPanel
