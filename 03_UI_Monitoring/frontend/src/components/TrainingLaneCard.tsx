import React from 'react'

interface PhaseState {
  status: 'queued' | 'training' | 'done' | 'failed' | 'skipped'
  progress_pct: number
  epoch: number
  epochs_total: number
  loss: number | null
  val_loss: number | null
  fail_reason: string | null
}

interface ParallelLane {
  symbol: string
  status: 'queued' | 'training' | 'done' | 'failed'
  current_phase: 'LSTM' | 'PPO' | 'Dreamer' | 'Champion' | 'Done' | 'Failed'
  total_progress: number
  eta_seconds: number | null
  lstm: PhaseState
  ppo: PhaseState
  dreamer: PhaseState
}

interface Props {
  lane: ParallelLane
  index: number
}

const PHASE_COLORS: Record<string, string> = {
  queued:   'var(--dim)',
  training: 'var(--cyan)',
  done:     'var(--green)',
  failed:   'var(--red)',
  skipped:  'var(--amber)',
}

const PhaseBar: React.FC<{ label: string; phase: PhaseState; isCurrent: boolean }> = ({ label, phase, isCurrent }) => {
  const color = PHASE_COLORS[phase.status] ?? 'var(--dim)'
  return (
    <div style={{ flex: 1 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 3, fontSize: '0.6rem', fontFamily: 'var(--mono)', color: isCurrent ? color : 'var(--dim)' }}>
        <span>{label}</span>
        <span>{phase.progress_pct.toFixed(0)}%</span>
      </div>
      <div style={{ height: 4, background: 'rgba(255,255,255,0.06)', borderRadius: 2, overflow: 'hidden' }}>
        <div style={{
          width: `${phase.progress_pct}%`,
          height: '100%',
          background: color,
          borderRadius: 2,
          transition: 'width 0.5s ease',
          boxShadow: isCurrent ? `0 0 6px ${color}` : 'none',
          animation: isCurrent && phase.status === 'training' ? 'progressShimmer 2s ease-in-out infinite' : 'none',
        }} />
      </div>
      {phase.loss != null && isCurrent && (
        <div style={{ fontSize: '0.58rem', fontFamily: 'var(--mono)', color: 'var(--muted)', marginTop: 2 }}>
          loss: {phase.loss.toFixed(4)} {phase.val_loss != null ? `| val: ${phase.val_loss.toFixed(4)}` : ''}
        </div>
      )}
    </div>
  )
}

const TrainingLaneCard: React.FC<Props> = ({ lane, index }) => {
  const statusColor = PHASE_COLORS[lane.status] ?? 'var(--dim)'
  const isActive = lane.status === 'training'

  const etaLabel = lane.eta_seconds != null
    ? lane.eta_seconds > 60 ? `${Math.round(lane.eta_seconds / 60)}m` : `${lane.eta_seconds}s`
    : null

  return (
    <div
      className="agit-panel"
      style={{
        padding: 16,
        borderLeftWidth: 3,
        borderLeftStyle: 'solid',
        borderLeftColor: statusColor,
        animation: `fadeSlide 0.5s ease-out both ${index * 0.06}s`,
        position: 'relative',
      }}
    >
      {/* Active pulse indicator */}
      {isActive && (
        <div style={{
          position: 'absolute', top: 10, right: 10,
          width: 8, height: 8, borderRadius: '50%',
          background: 'var(--cyan)',
          boxShadow: '0 0 8px var(--cyan)',
          animation: 'markPulse 2s ease-in-out infinite',
        }} />
      )}

      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{ fontFamily: 'var(--orbitron)', fontWeight: 700, fontSize: '0.85rem', color: 'var(--text)' }}>
            {lane.symbol}
          </span>
          <span className={`agit-badge ${
            lane.status === 'done' ? 'agit-badge-win' :
            lane.status === 'failed' ? 'agit-badge-loss' :
            lane.status === 'training' ? 'agit-badge-info' : 'agit-badge-idle'
          }`}>
            {lane.current_phase}
          </span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {etaLabel && isActive && (
            <span style={{ fontFamily: 'var(--mono)', fontSize: '0.65rem', color: 'var(--amber)' }}>
              ETA {etaLabel}
            </span>
          )}
          <span style={{ fontFamily: 'var(--mono)', fontSize: '0.72rem', color: statusColor, fontWeight: 700 }}>
            {lane.total_progress.toFixed(0)}%
          </span>
        </div>
      </div>

      {/* Phase progress bars */}
      <div style={{ display: 'flex', gap: 8 }}>
        <PhaseBar label="LSTM" phase={lane.lstm} isCurrent={lane.current_phase === 'LSTM'} />
        <PhaseBar label="PPO" phase={lane.ppo} isCurrent={lane.current_phase === 'PPO'} />
        <PhaseBar label="Dreamer" phase={lane.dreamer} isCurrent={lane.current_phase === 'Dreamer'} />
      </div>

      {/* Fail reason */}
      {lane.status === 'failed' && (
        <div style={{ marginTop: 8, fontSize: '0.7rem', color: 'var(--red)', fontFamily: 'var(--mono)', padding: '4px 8px', background: 'rgba(255,51,102,0.06)', borderRadius: 4 }}>
          {lane.lstm.fail_reason || lane.ppo.fail_reason || lane.dreamer.fail_reason || 'Pipeline failed'}
        </div>
      )}
    </div>
  )
}

export default TrainingLaneCard
