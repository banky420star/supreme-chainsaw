import React from 'react'
import { AgentStatus, StatusPayload } from '../types'
import { extractAgentStatus } from '../services/api'

interface Props {
  status: StatusPayload
}

const STATUS_COLOR: Record<AgentStatus['status'], string> = {
  Online: '#00ff88',
  Training: '#00f0ff',
  Idle: '#7a94b0',
  Error: '#ff3366',
}

const STATUS_GLOW: Record<AgentStatus['status'], string> = {
  Online: 'rgba(0,255,136,0.15)',
  Training: 'rgba(0,240,255,0.15)',
  Idle: 'rgba(122,148,176,0.08)',
  Error: 'rgba(255,51,102,0.15)',
}

const AgentCard: React.FC<{ agent: AgentStatus; index: number }> = ({ agent, index }) => {
  const isActive = agent.status === 'Online' || agent.status === 'Training'
  const color = STATUS_COLOR[agent.status]
  const glow = STATUS_GLOW[agent.status]

  return (
    <div
      className="agit-panel"
      style={{
        padding: 18,
        display: 'flex',
        flexDirection: 'column',
        gap: 10,
        animation: `fadeSlide 0.5s ease-out both ${index * 0.05}s`,
        position: 'relative',
        overflow: 'hidden',
      }}
    >
      {/* Active pulse ring */}
      {isActive && (
        <div
          style={{
            position: 'absolute',
            top: 8,
            right: 8,
            width: 10,
            height: 10,
            borderRadius: '50%',
            background: color,
            boxShadow: `0 0 8px ${color}, 0 0 16px ${glow}`,
            animation: 'markPulse 2s ease-in-out infinite',
          }}
        />
      )}

      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <div
          style={{
            width: 36,
            height: 36,
            borderRadius: 8,
            background: `linear-gradient(135deg, ${glow}, transparent)`,
            border: `1px solid ${color}`,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontFamily: 'var(--orbitron)',
            fontSize: 14,
            fontWeight: 700,
            color,
            textShadow: `0 0 8px ${glow}`,
            flexShrink: 0,
          }}
        >
          {agent.name.charAt(0)}
        </div>
        <div style={{ minWidth: 0 }}>
          <div
            style={{
              fontFamily: 'var(--orbitron)',
              fontSize: '0.8rem',
              fontWeight: 700,
              letterSpacing: '0.04em',
              color: 'var(--text)',
              whiteSpace: 'nowrap',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
            }}
          >
            {agent.name}
          </div>
          <div
            style={{
              fontSize: '0.65rem',
              color: 'var(--dim)',
              fontFamily: 'var(--mono)',
              letterSpacing: '0.06em',
              textTransform: 'uppercase',
            }}
          >
            {agent.role}
          </div>
        </div>
      </div>

      {/* Status badge */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 2 }}>
        <span
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 6,
            padding: '3px 10px',
            borderRadius: 4,
            fontSize: '0.7rem',
            fontWeight: 700,
            textTransform: 'uppercase',
            fontFamily: 'var(--mono)',
            letterSpacing: '0.05em',
            background: `${glow}`,
            color,
            border: `1px solid ${color}`,
            boxShadow: `0 0 8px ${glow}`,
          }}
        >
          <span
            style={{
              width: 6,
              height: 6,
              borderRadius: '50%',
              background: color,
              boxShadow: `0 0 6px ${color}`,
            }}
          />
          {agent.status}
        </span>
        <span
          style={{
            fontSize: '0.65rem',
            color: 'var(--dim)',
            fontFamily: 'var(--mono)',
          }}
        >
          {agent.lastActivity}
        </span>
      </div>

      {/* KPI metric */}
      <div
        style={{
          marginTop: 4,
          padding: '8px 10px',
          borderRadius: 8,
          background: 'rgba(0,240,255,0.04)',
          border: '1px solid rgba(0,240,255,0.08)',
        }}
      >
        <div
          style={{
            fontSize: '0.65rem',
            textTransform: 'uppercase',
            letterSpacing: '0.12em',
            color: 'var(--dim)',
            fontFamily: 'var(--mono)',
            fontWeight: 500,
            marginBottom: 2,
          }}
        >
          KPI
        </div>
        <div
          style={{
            fontSize: '0.95rem',
            fontWeight: 700,
            fontFamily: 'var(--mono)',
            color: 'var(--cyan)',
            textShadow: '0 0 10px rgba(0,240,255,0.1)',
          }}
        >
          {agent.metric}
        </div>
      </div>

      {/* Log snippet */}
      <div
        style={{
          marginTop: 2,
          fontSize: '0.75rem',
          color: 'var(--muted)',
          fontFamily: 'var(--mono)',
          lineHeight: 1.4,
          minHeight: 32,
          overflow: 'hidden',
          display: '-webkit-box',
          WebkitLineClamp: 2,
          WebkitBoxOrient: 'vertical',
        }}
      >
        {agent.logs}
      </div>
    </div>
  )
}

const AgentTeamPanel: React.FC<Props> = ({ status }) => {
  const agents = React.useMemo(() => extractAgentStatus(status), [status])

  return (
    <div style={{ padding: '20px 0' }}>
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: 20,
        }}
      >
        <h2
          style={{
            margin: 0,
            fontFamily: 'var(--orbitron)',
            fontSize: '1.1rem',
            fontWeight: 700,
            letterSpacing: '0.08em',
            color: 'var(--cyan)',
            textShadow: '0 0 15px rgba(0,240,255,0.2)',
          }}
        >
          AUTONOMOUS AGENT TEAM
        </h2>
        <div
          style={{
            fontSize: '0.7rem',
            color: 'var(--dim)',
            fontFamily: 'var(--mono)',
            letterSpacing: '0.1em',
            textTransform: 'uppercase',
          }}
        >
          {agents.filter((a) => a.status === 'Online' || a.status === 'Training').length} / {agents.length} active
        </div>
      </div>

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
          gap: 16,
        }}
      >
        {agents.map((agent, idx) => (
          <AgentCard key={agent.id} agent={agent} index={idx} />
        ))}
      </div>
    </div>
  )
}

export default AgentTeamPanel
