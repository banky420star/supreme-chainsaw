import React from 'react'
import { StatusPayload, SystemHeaderState } from '../types'
import TruthBadge from './TruthBadge'

interface Props {
  status: StatusPayload
  header: SystemHeaderState | null
}

const cardStyle: React.CSSProperties = {
  background: 'linear-gradient(145deg, rgba(255,255,255,0.04) 0%, rgba(255,255,255,0.01) 100%), var(--panel)',
  border: '1px solid var(--line)',
  borderRadius: 'var(--radius-md)',
  padding: 20,
  position: 'relative',
  overflow: 'hidden',
}

const cardTitle: React.CSSProperties = {
  fontFamily: 'var(--orbitron)',
  fontSize: '0.72rem',
  fontWeight: 700,
  letterSpacing: '0.08em',
  color: 'var(--cyan)',
  marginBottom: 14,
  textTransform: 'uppercase',
}

const row: React.CSSProperties = {
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'center',
  padding: '6px 0',
  borderBottom: '1px solid rgba(255,255,255,0.03)',
  fontSize: 13,
}

const label: React.CSSProperties = {
  color: 'var(--muted)',
  fontFamily: 'var(--mono)',
  fontSize: 12,
}

const val: React.CSSProperties = {
  color: 'var(--text)',
  fontFamily: 'var(--mono)',
  fontWeight: 600,
  fontSize: 12,
}

function truthTone(status?: string | null): any {
  if (!status) return 'gray'
  const s = status.toLowerCase()
  if (['passing', 'online', 'valid', 'trained', 'champion', 'active', 'running', 'clean', 'unlocked'].includes(s)) return 'green'
  if (['stale', 'unaudited', 'validating', 'training', 'candidate', 'demo_canary', 'degraded', 'locked', 'failed', 'failing', 'invalid', 'undertrained', 'rejected'].includes(s)) return 'yellow'
  if (['offline', 'blocked', 'halted', 'error', 'critical'].includes(s)) return 'red'
  return 'gray'
}

function truthValue(value?: string | boolean | number | null, fallback = 'unknown'): string {
  if (value == null) return fallback
  if (typeof value === 'boolean') return value ? 'yes' : 'no'
  return String(value)
}

const OverviewPanel: React.FC<Props> = ({ status, header }) => {
  const system = status.system
  const data = status.data
  const models = status.models
  const tests = status.tests
  const account = status.account
  const training = status.training
  const canary = status.canary_gate

  const cards = [
    {
      title: 'Mode',
      rows: [
        { label: 'System Mode', value: truthValue(system?.system_mode), tone: truthTone(system?.system_mode) },
        { label: 'Transport', value: truthValue(system?.execution_transport), tone: truthTone(system?.execution_transport) },
        { label: 'Real Money', value: system?.real_money_locked ? 'LOCKED' : 'unlocked', tone: system?.real_money_locked ? 'red' : 'green' },
        { label: 'Lock Reason', value: truthValue(system?.live_lock_reason, 'none'), tone: system?.live_lock_reason ? 'yellow' : 'gray' },
      ],
    },
    {
      title: 'Safety',
      rows: [
        { label: 'Risk Halt', value: status.risk?.halt ? 'HALTED' : 'clear', tone: status.risk?.halt ? 'red' : 'green' },
        { label: 'Can Trade', value: truthValue(status.risk?.canTrade), tone: status.risk?.canTrade ? 'green' : 'yellow' },
        { label: 'Drawdown', value: `${truthValue(status.risk?.drawdownPct ?? status.risk?.max_drawdown_pct, '--')}%`, tone: 'gray' },
        { label: 'Tests', value: truthValue(tests?.status), tone: truthTone(tests?.status) },
        { label: 'Test Failures', value: truthValue(tests?.open_failures, '0'), tone: (tests?.open_failures ?? 0) > 0 ? 'red' : 'gray' },
      ],
    },
    {
      title: 'Account',
      rows: [
        { label: 'Type', value: truthValue(account?.mode ?? header?.account_type), tone: truthTone(account?.mode ?? header?.account_type) },
        { label: 'Verified', value: truthValue(header?.account_type_verified), tone: header?.account_type_verified ? 'green' : 'yellow' },
        { label: 'Telemetry', value: truthValue(header?.account_telemetry_valid), tone: header?.account_telemetry_valid === false ? 'red' : 'green' },
        { label: 'Balance', value: account?.balance != null ? `$${account.balance.toFixed(2)}` : '--', tone: 'gray' },
        { label: 'Equity', value: account?.equity != null ? `$${account.equity.toFixed(2)}` : '--', tone: 'gray' },
        { label: 'Positions', value: truthValue(account?.open_positions, '0'), tone: 'gray' },
      ],
    },
    {
      title: 'Champion',
      rows: [
        { label: 'Status', value: truthValue(header?.champion_status), tone: truthTone(header?.champion_status) },
        { label: 'Bundle ID', value: truthValue(header?.active_bundle_id?.slice(0, 16), 'none'), tone: header?.active_bundle_id ? 'blue' : 'gray' },
        { label: 'Canary Ready', value: truthValue(canary?.ready), tone: canary?.ready ? 'green' : 'yellow' },
        { label: 'Canary Reason', value: truthValue(canary?.reason, 'none'), tone: canary?.reason ? 'yellow' : 'gray' },
      ],
    },
    {
      title: 'Training',
      rows: [
        { label: 'Cycle', value: truthValue(training?.cycle_running ? 'running' : 'idle'), tone: training?.cycle_running ? 'blue' : 'gray' },
        { label: 'LSTM', value: truthValue(training?.lstm_running ? 'training' : 'idle'), tone: training?.lstm_running ? 'blue' : 'gray' },
        { label: 'PPO', value: truthValue(training?.drl_running ? 'training' : 'idle'), tone: training?.drl_running ? 'blue' : 'gray' },
        { label: 'Dreamer', value: truthValue(training?.dreamer_running ? 'training' : 'idle'), tone: training?.dreamer_running ? 'blue' : 'gray' },
        { label: 'Active Symbols', value: truthValue(training?.configured_symbols?.length, '0'), tone: 'gray' },
      ],
    },
    {
      title: 'Pipeline',
      rows: [
        { label: 'Data', value: truthValue(data?.status), tone: truthTone(data?.status) },
        { label: 'Features', value: 'unaudited', tone: 'yellow' },
        { label: 'LSTM', value: truthValue(models?.lstm_status), tone: truthTone(models?.lstm_status) },
        { label: 'Rainforest', value: truthValue(models?.rainforest_status), tone: truthTone(models?.rainforest_status) },
        { label: 'Dreamer', value: truthValue(models?.dreamer_status), tone: truthTone(models?.dreamer_status) },
        { label: 'PPO', value: truthValue(models?.ppo_status), tone: truthTone(models?.ppo_status) },
      ],
    },
    {
      title: 'Test',
      rows: [
        { label: 'Status', value: truthValue(tests?.status), tone: truthTone(tests?.status) },
        { label: 'Failures', value: truthValue(tests?.open_failures, '0'), tone: (tests?.open_failures ?? 0) > 0 ? 'red' : 'gray' },
        { label: 'Errors', value: truthValue(tests?.open_errors, '0'), tone: (tests?.open_errors ?? 0) > 0 ? 'yellow' : 'gray' },
      ],
    },
    {
      title: 'Dreamer',
      rows: [
        { label: 'Status', value: truthValue(models?.dreamer_status), tone: truthTone(models?.dreamer_status) },
        { label: 'Stub', value: models?.dreamer_status === 'stub_disabled' ? 'DISABLED' : 'N/A', tone: models?.dreamer_status === 'stub_disabled' ? 'yellow' : 'gray' },
        { label: 'Used For Decisions', value: truthValue(models?.dreamer_used ?? false), tone: (models?.dreamer_used ?? false) ? 'green' : 'gray' },
      ],
    },
  ]

  return (
    <div style={{ padding: '0 0 20px' }}>
      <h2
        style={{
          fontFamily: 'var(--orbitron)',
          fontSize: '0.9rem',
          fontWeight: 700,
          letterSpacing: '0.1em',
          color: 'var(--cyan)',
          marginBottom: 20,
          textTransform: 'uppercase',
        }}
      >
        Overview — Truth Dashboard
      </h2>

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))',
          gap: 'var(--gap)',
        }}
      >
        {cards.map((card) => (
          <div key={card.title} style={cardStyle}>
            <div style={cardTitle}>{card.title}</div>
            {card.rows.map((r) => (
              <div key={r.label} style={row}>
                <span style={label}>{r.label}</span>
                <TruthBadge tone={r.tone} label={r.value} dot={false} />
              </div>
            ))}
          </div>
        ))}
      </div>
    </div>
  )
}

export default OverviewPanel
