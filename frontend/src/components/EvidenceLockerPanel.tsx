import React from 'react'
import { EvidenceArtifact, fetchEvidence } from '../services/api'
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

function artifactTone(status?: string): any {
  if (!status) return 'gray'
  const s = status.toLowerCase()
  if (s === 'valid' || s === 'verified' || s === 'complete') return 'green'
  if (s === 'pending' || s === 'processing') return 'blue'
  if (s === 'stale' || s === 'unaudited') return 'yellow'
  if (s === 'failed' || s === 'corrupted') return 'red'
  return 'gray'
}

const EvidenceLockerPanel: React.FC = () => {
  const [artifacts, setArtifacts] = React.useState<EvidenceArtifact[]>([])
  const [loading, setLoading] = React.useState(true)

  React.useEffect(() => {
    let cancelled = false
    const load = async () => {
      setLoading(true)
      try {
        const data = await fetchEvidence()
        if (!cancelled) setArtifacts(Array.isArray(data) ? data : [])
      } catch {
        if (!cancelled) setArtifacts([])
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
        Evidence Locker
      </h2>

      {loading && artifacts.length === 0 && <LoadingBar label="Loading evidence locker..." />}
      {!loading && artifacts.length === 0 && (
        <div style={{ ...panelStyle, color: colors.muted }}>
          No artifacts in evidence locker. The endpoint returned empty.
        </div>
      )}

      {artifacts.length > 0 && (
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <thead>
              <tr>
                <th style={thStyle}>Name</th>
                <th style={thStyle}>Created</th>
                <th style={thStyle}>Status</th>
                <th style={thStyle}>Linked Model</th>
                <th style={thStyle}>Path</th>
              </tr>
            </thead>
            <tbody>
              {artifacts.map((a, idx) => (
                <tr key={idx} style={{ background: idx % 2 === 0 ? 'transparent' : 'rgba(90,215,255,0.02)' }}>
                  <td style={{ ...tdStyle, fontWeight: 600 }}>{a.name}</td>
                  <td style={{ ...tdStyle, fontFamily: 'monospace', fontSize: 11 }}>{a.created_at}</td>
                  <td style={tdStyle}><TruthBadge tone={artifactTone(a.status)} label={a.status} dot={false} /></td>
                  <td style={{ ...tdStyle, color: colors.cyan }}>{a.linked_model ?? '--'}</td>
                  <td style={{ ...tdStyle, fontFamily: 'monospace', fontSize: 11, color: colors.muted }}>{a.path}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

export default EvidenceLockerPanel
