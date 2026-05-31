import React from 'react'
import { SystemHeaderState } from '../types'
import TruthBadge from './TruthBadge'

interface Props {
  header: SystemHeaderState | null
}

const SystemCommandBar: React.FC<Props> = ({ header }) => {
  if (!header) {
    return (
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          padding: '6px 16px',
          background: 'rgba(4,8,16,0.95)',
          borderBottom: '1px solid rgba(0,240,255,0.08)',
          minHeight: 40,
        }}
      >
        <TruthBadge tone="gray" label="SYSTEM" value="NO DATA" />
      </div>
    )
  }

  const badges: Array<{ tone: any; label: string; value?: string | number | null; pulse?: boolean }> = [
    { tone: modeTone(header.system_mode), label: 'MODE', value: header.system_mode },
    { tone: header.execution_transport === 'mt5' ? 'blue' : 'gray', label: 'TRANSPORT', value: header.execution_transport },
    ...(header.real_money_locked ? [{ tone: 'red' as const, label: 'LOCKED', value: header.live_lock_reason || undefined, pulse: true }] : []),
    { tone: apiTone(header.api_status), label: 'API', value: header.api_status },
    { tone: apiTone(header.mt5_bridge_status), label: 'MT5', value: header.mt5_bridge_status },
    { tone: accountTone(header.account_type, header.account_type_verified), label: 'ACCT', value: header.account_type },
    ...(header.account_telemetry_valid === false ? [{ tone: 'yellow' as const, label: 'TELEMETRY', value: 'INVALID' }] : []),
    { tone: testTone(header.tests_status), label: 'TESTS', value: header.tests_status },
    ...(header.open_test_failures > 0 ? [{ tone: 'red' as const, label: 'FAILURES', value: header.open_test_failures }] : []),
    ...(header.open_test_errors > 0 ? [{ tone: 'yellow' as const, label: 'ERRORS', value: header.open_test_errors }] : []),
    ...(header.active_bundle_id ? [{ tone: 'blue' as const, label: 'BUNDLE', value: header.active_bundle_id.slice(0, 12) }] : []),
    { tone: championTone(header.champion_status), label: 'CHAMPION', value: header.champion_status },
  ]

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 8,
        flexWrap: 'wrap',
        padding: '6px 16px',
        background: 'rgba(4,8,16,0.95)',
        borderBottom: '1px solid rgba(0,240,255,0.08)',
        minHeight: 40,
      }}
    >
      {badges.map((b, i) => (
        <TruthBadge key={`${b.label}-${i}`} tone={b.tone} label={b.label} value={b.value} pulse={b.pulse} />
      ))}
    </div>
  )
}

function modeTone(mode: string): any {
  if (mode === 'paper_sim') return 'blue'
  if (mode === 'demo_live') return 'yellow'
  if (mode === 'real_live') return 'green'
  if (mode === 'real_live_locked') return 'red'
  return 'gray'
}

function apiTone(status: string): any {
  if (status === 'online') return 'green'
  if (status === 'degraded') return 'yellow'
  if (status === 'offline') return 'red'
  return 'gray'
}

function accountTone(type: string, verified: boolean): any {
  if (!verified) return 'yellow'
  if (type === 'real') return 'green'
  if (type === 'demo') return 'blue'
  return 'gray'
}

function testTone(status: string): any {
  if (status === 'passing') return 'green'
  if (status === 'failing') return 'red'
  return 'gray'
}

function championTone(status: string): any {
  if (status === 'champion') return 'green'
  if (status === 'candidate') return 'blue'
  if (status === 'rejected') return 'red'
  return 'gray'
}

export default SystemCommandBar
