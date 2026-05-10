import React from 'react'
import { AgentOperationalStatus, fetchAgentsOperational } from '../services/api'
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

function agentTone(status?: string): any {
  if (!status) return 'gray'
  const s = status.toLowerCase()
  if (s === 'online' || s === 'active' || s === 'healthy') return 'green'
  if (s === 'training' || s === 'busy') return 'blue'
  if (s === 'idle' || s === 'standby') return 'gray'
  if (s === 'error' || s === 'crashed' || s === 'offline') return 'red'
  return 'yellow'
}

const AgentsPanel: React.FC = () => {
  const [agents, setAgents] = React.useState<AgentOperationalStatus[]>([])
  const [loading, setLoading] = React.useState(true)

  React.useEffect(() => {
    let cancelled = false
    const load = async () => {
      setLoading(true)
      try {
        const data = await fetchAgentsOperational()
        if (!cancelled) setAgents(Array.isArray(data) ? data : [])
      } catch {
        if (!cancelled) setAgents([])
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    const id = setInterval(load, 15_000)
    return () => { cancelled = true; clearInterval(id) }
  }, [])

  const onlineCount = agents.filter((a) => {
    const s = a.status?.toLowerCase()
    return s === 'online' || s === 'active' || s === 'healthy'
  }).length
  const errorCount = agents.filter((a) => {
    const s = a.status?.toLowerCase()
    return s === 'error' || s === 'crashed' || s === 'offline'
  }).length

  return (
    <div style={{ background: colors.bg, color: colors.text, padding: 20 }}>
      <h2 style={{ margin: '0 0 16px', fontSize: 18, color: colors.cyan, fontWeight: 700 }}>
        Agents — Operational Board
      </h2>

      {loading && agents.length === 0 && (
        <div style={{ ...panelStyle, color: colors.muted }}>Loading agents...</div>
      )}
      {!loading && agents.length === 0 && (
        <div style={{ ...panelStyle, color: colors.muted }}>
          No agent data available. The endpoint returned empty.
        </div>
      )}

      {agents.length > 0 && (
        <>
          <div style={{ ...panelStyle, display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap', marginBottom: 16 }}>
            <TruthBadge tone="green" label={`${onlineCount} ONLINE`} dot={false} />
            <TruthBadge tone={errorCount > 0 ? 'red' : 'gray'} label={`${errorCount} ERROR`} dot={false} />
            <span style={{ fontSize: 12, color: colors.muted }}>{agents.length} total agents registered</span>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 12 }}>
            {agents.map((a) => (
              <div key={a.agent_id} style={panelStyle}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                  <div>
                    <div style={{ fontSize: 13, fontWeight: 700 }}>{a.agent_name}</div>
                    <div style={{ fontSize: 10, color: colors.muted, fontFamily: 'monospace' }}>{a.agent_id}</div>
                  </div>
                  <TruthBadge tone={agentTone(a.status)} label={a.status ?? 'unknown'} dot={false} />
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 12 }}>
                  <div>
                    <span style={{ color: colors.muted }}>Task: </span>
                    <span style={{ color: colors.text }}>{a.current_task ?? 'idle'}</span>
                  </div>
                  <div>
                    <span style={{ color: colors.muted }}>Heartbeat: </span>
                    <span style={{ color: colors.text, fontFamily: 'monospace' }}>{a.heartbeat ?? 'never'}</span>
                  </div>
                  <div>
                    <span style={{ color: colors.muted }}>Last Artifact: </span>
                    <span style={{ color: colors.text, fontFamily: 'monospace' }}>{a.last_artifact ?? 'none'}</span>
                  </div>
                  <div>
                    <span style={{ color: colors.muted }}>Errors: </span>
                    <span style={{ color: a.error_count > 0 ? colors.red : colors.muted, fontWeight: a.error_count > 0 ? 700 : 400 }}>{a.error_count}</span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  )
}

export default AgentsPanel
