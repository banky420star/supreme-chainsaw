import React from 'react'
import { StatusPayload } from '../types'

interface Props {
  status: StatusPayload
}

/* ─── Stage pipeline definition ─── */
const STAGES = [
  { id: 'ingestion', label: 'Data Ingestion' },
  { id: 'feature_engineering', label: 'Feature Engineering' },
  { id: 'lstm_training', label: 'LSTM Training' },
  { id: 'ppo_training', label: 'PPO Training' },
  { id: 'dreamer_training', label: 'Dreamer Training' },
  { id: 'backtesting', label: 'Backtesting' },
  { id: 'promotion', label: 'Promotion' },
]

/* ─── Pre-written LLM narrative templates ─── */
const EXPLANATIONS: Record<string, string> = {
  ingestion:
    'Ingesting 100,000 M5 candles from MT5 for the active symbol, building the raw dataset for downstream models...',
  feature_engineering:
    'Engineering 150 features using Fibonacci windows and multi-timeframe resampling...',
  lstm_training:
    'LSTM is learning to classify market regime (bull/bear/ranging/breakout/reversal)...',
  ppo_training:
    'PPO is learning a policy for position sizing using risk-adjusted reward...',
  dreamer_training:
    'Dreamer is imagining future states via RSSM world model...',
  backtesting:
    'Backtesting on 60d/90d/120d forward windows with drawdown/sharpe gates...',
  promotion:
    'Promoting champion model to live trading after passing canary gates and risk-adjusted performance thresholds...',
}

/* ─── Derive active stage from payload ─── */
function deriveActiveStageId(status: StatusPayload): string {
  const label = status.training?.visual?.active_label?.toLowerCase() ?? ''
  if (label.includes('ingest')) return 'ingestion'
  if (label.includes('feature')) return 'feature_engineering'
  if (label.includes('lstm')) return 'lstm_training'
  if (label.includes('ppo') || label.includes('drl')) return 'ppo_training'
  if (label.includes('dreamer')) return 'dreamer_training'
  if (label.includes('backtest')) return 'backtesting'
  if (label.includes('promot') || label.includes('champion')) return 'promotion'

  // Fallback from boolean flags
  if (status.training?.dreamer_running) return 'dreamer_training'
  if (status.training?.drl_running) return 'ppo_training'
  if (status.training?.lstm_running) return 'lstm_training'
  if (status.training?.cycle_running) return 'backtesting'
  return 'ingestion'
}

/* ─── Format seconds into human readable ETA ─── */
function formatETA(etaSeconds?: number | null): string {
  if (etaSeconds == null || etaSeconds <= 0) return '--'
  if (etaSeconds < 60) return `${Math.round(etaSeconds)}s`
  if (etaSeconds < 3600) return `${Math.round(etaSeconds / 60)}m`
  const h = Math.floor(etaSeconds / 3600)
  const m = Math.round((etaSeconds % 3600) / 60)
  return `${h}h ${m}m`
}

/* ─── Simple typewriter effect for the LLM panel ─── */
const TypewriterText: React.FC<{ text: string; speed?: number }> = ({
  text,
  speed = 18,
}) => {
  const [display, setDisplay] = React.useState('')

  React.useEffect(() => {
    let i = 0
    setDisplay('')
    const id = setInterval(() => {
      setDisplay(text.slice(0, i + 1))
      i++
      if (i >= text.length) clearInterval(id)
    }, speed)
    return () => clearInterval(id)
  }, [text, speed])

  return <span>{display}</span>
}

/* ─── Single stage badge ─── */
const StageBadge: React.FC<{
  label: string
  state: 'completed' | 'active' | 'pending'
}> = ({ label, state }) => {
  const color =
    state === 'completed'
      ? 'var(--green)'
      : state === 'active'
        ? 'var(--cyan)'
        : 'var(--dim)'

  const bg =
    state === 'completed'
      ? 'rgba(0,255,136,0.06)'
      : state === 'active'
        ? 'rgba(0,240,255,0.08)'
        : 'transparent'

  const border =
    state === 'completed'
      ? 'rgba(0,255,136,0.25)'
      : state === 'active'
        ? 'rgba(0,240,255,0.35)'
        : 'rgba(255,255,255,0.06)'

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 8,
        padding: '8px 12px',
        borderRadius: 8,
        border: `1px solid ${border}`,
        background: bg,
        boxShadow: state === 'active' ? '0 0 16px rgba(0,240,255,0.10)' : 'none',
        transition: 'all 0.35s ease',
        position: 'relative',
      }}
    >
      {/* Status dot / check */}
      <span
        style={{
          width: 18,
          height: 18,
          borderRadius: '50%',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          background:
            state === 'completed'
              ? 'var(--green)'
              : state === 'active'
                ? 'var(--cyan)'
                : 'transparent',
          border: `2px solid ${state === 'pending' ? 'var(--dim)' : 'transparent'}`,
          fontSize: '0.65rem',
          color: '#000',
          fontWeight: 800,
          flexShrink: 0,
        }}
      >
        {state === 'completed' ? '✓' : null}
        {state === 'active' ? (
          <span
            style={{
              width: 8,
              height: 8,
              borderRadius: '50%',
              background: 'var(--cyan)',
              boxShadow: '0 0 6px var(--cyan)',
              animation: 'markPulse 2s ease-in-out infinite',
            }}
          />
        ) : null}
      </span>

      <span
        style={{
          fontFamily: 'var(--mono)',
          fontSize: '0.68rem',
          fontWeight: 600,
          color,
          textTransform: 'uppercase',
          letterSpacing: '0.05em',
          whiteSpace: 'nowrap',
        }}
      >
        {label}
      </span>
    </div>
  )
}

/* ─── Model progress card ─── */
const ModelCard: React.FC<{
  title: string
  accent: string
  accentGlow: string
  state?: string
  progressPct?: number
  primary?: { label: string; current: number; total: number }
  metrics?: { label: string; value: string }[]
  etaSeconds?: number | null
}> = ({
  title,
  accent,
  accentGlow,
  state,
  progressPct = 0,
  primary,
  metrics,
  etaSeconds,
}) => {
  return (
    <div
      className="agit-panel"
      style={{
        borderTop: `2px solid ${accent}`,
        animation: 'fadeSlide 0.5s ease-out both',
      }}
    >
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: 14,
        }}
      >
        <span
          style={{
            fontFamily: 'var(--orbitron)',
            fontSize: '0.82rem',
            fontWeight: 700,
            color: accent,
            textShadow: `0 0 10px ${accentGlow}`,
          }}
        >
          {title}
        </span>
        <span
          className="agit-badge"
          style={{
            background: `${accentGlow.replace('0.15', '0.10')}`,
            color: accent,
            border: `1px solid ${accentGlow.replace('0.15', '0.20')}`,
          }}
        >
          {state ?? 'Idle'}
        </span>
      </div>

      {primary && (
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            marginBottom: 10,
            fontFamily: 'var(--mono)',
            fontSize: '0.72rem',
            color: 'var(--muted)',
          }}
        >
          <span>
            {primary.label} {primary.current.toLocaleString()} / {primary.total.toLocaleString()}
          </span>
          <span style={{ color: 'var(--text)', fontWeight: 600 }}>
            {progressPct.toFixed(0)}%
          </span>
        </div>
      )}

      <div className="agit-progress-track" style={{ marginBottom: 12 }}>
        <div
          className="agit-progress-fill"
          style={{
            width: `${Math.min(100, Math.max(0, progressPct))}%`,
            background: `linear-gradient(90deg, ${accent}88, ${accent})`,
            boxShadow: `0 0 10px ${accentGlow}`,
          }}
        />
      </div>

      {metrics && metrics.length > 0 && (
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            flexWrap: 'wrap',
            gap: 8,
            fontFamily: 'var(--mono)',
            fontSize: '0.65rem',
            color: 'var(--dim)',
            marginBottom: 8,
          }}
        >
          {metrics.map((m) => (
            <span key={m.label}>
              {m.label}: <span style={{ color: 'var(--muted)' }}>{m.value}</span>
            </span>
          ))}
        </div>
      )}

      <div
        style={{
          marginTop: 'auto',
          fontFamily: 'var(--mono)',
          fontSize: '0.62rem',
          color: 'var(--amber)',
          display: 'flex',
          alignItems: 'center',
          gap: 6,
        }}
      >
        <span>ETA</span>
        <span style={{ fontWeight: 600 }}>{formatETA(etaSeconds)}</span>
      </div>
    </div>
  )
}

/* ─── Main component ─── */
const TrainingProgressPanel: React.FC<Props> = ({ status }) => {
  const activeStageId = deriveActiveStageId(status)
  const activeIndex = STAGES.findIndex((s) => s.id === activeStageId)

  const training = status.training
  const visual = training?.visual

  const lstm = visual?.lstm
  const ppo = visual?.ppo
  const dreamer = visual?.dreamer

  const activeSymbol =
    lstm?.current_symbol ??
    ppo?.current_symbol ??
    dreamer?.current_symbol ??
    status.training?.configured_symbols?.[0] ??
    '—'

  const overallProgress = Math.round(
    ((lstm?.progress_pct ?? 0) +
      (ppo?.progress_pct ?? 0) +
      (dreamer?.progress_pct ?? 0)) /
      3
  )

  const explanation =
    EXPLANATIONS[activeStageId] ??
    'Monitoring pipeline state and awaiting next training trigger...'

  return (
    <section className="agit-section animate-in">
      {/* ── Header ── */}
      <div className="agit-panel" style={{ marginBottom: 'var(--gap)' }}>
        <div className="agit-panel-title">Training Progress</div>
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            flexWrap: 'wrap',
            gap: 16,
          }}
        >
          <div>
            <div
              style={{
                fontSize: '0.62rem',
                textTransform: 'uppercase',
                letterSpacing: '0.14em',
                color: 'var(--dim)',
                fontFamily: 'var(--mono)',
                marginBottom: 6,
              }}
            >
              Active Symbol
            </div>
            <div
              style={{
                fontFamily: 'var(--orbitron)',
                fontSize: '1.4rem',
                fontWeight: 700,
                color: 'var(--cyan)',
                textShadow: '0 0 12px var(--cyan-glow)',
              }}
            >
              {activeSymbol}
            </div>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
            <span
              className={`agit-badge ${activeIndex >= 0 ? 'agit-badge-info' : 'agit-badge-idle'}`}
            >
              {STAGES[activeIndex]?.label ?? 'Idle'}
            </span>
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 6,
                fontFamily: 'var(--mono)',
                fontSize: '0.85rem',
                color: 'var(--text)',
              }}
            >
              <span style={{ color: 'var(--dim)', fontSize: '0.72rem' }}>Overall</span>
              <span style={{ fontWeight: 700 }}>{overallProgress}%</span>
            </div>
          </div>
        </div>
      </div>

      {/* ── Model cards ── */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
          gap: 'var(--gap)',
          marginBottom: 'var(--gap)',
        }}
      >
        <ModelCard
          title="LSTM Brain"
          accent="var(--purple)"
          accentGlow="rgba(185,103,255,0.15)"
          state={lstm?.state}
          progressPct={lstm?.progress_pct ?? 0}
          primary={{
            label: 'Epoch',
            current: lstm?.current_epoch ?? 0,
            total: lstm?.total_epochs ?? 0,
          }}
          metrics={[
            {
              label: 'loss',
              value: lstm?.loss != null ? lstm.loss.toFixed(4) : '--',
            },
            {
              label: 'val_loss',
              value: lstm?.val_loss != null ? lstm.val_loss.toFixed(4) : '--',
            },
          ]}
          etaSeconds={lstm?.eta_seconds}
        />

        <ModelCard
          title="PPO Brain"
          accent="var(--green)"
          accentGlow="rgba(0,255,136,0.15)"
          state={ppo?.state}
          progressPct={ppo?.progress_pct ?? 0}
          primary={{
            label: 'Timestep',
            current: ppo?.current_timestep ?? 0,
            total: ppo?.target_timesteps ?? 0,
          }}
          etaSeconds={ppo?.eta_seconds}
        />

        <ModelCard
          title="Dreamer"
          accent="var(--magenta)"
          accentGlow="rgba(255,0,160,0.12)"
          state={dreamer?.state}
          progressPct={dreamer?.progress_pct ?? 0}
          primary={{
            label: 'Step',
            current: dreamer?.current_step ?? 0,
            total: dreamer?.target_steps ?? 0,
          }}
          etaSeconds={dreamer?.eta_seconds}
        />
      </div>

      {/* ── Stage pipeline ── */}
      <div className="agit-panel" style={{ marginBottom: 'var(--gap)' }}>
        <div className="agit-panel-title">Pipeline Stage</div>

        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            flexWrap: 'wrap',
            gap: '10px 6px',
          }}
        >
          {STAGES.map((stage, idx) => {
            const state =
              idx < activeIndex
                ? 'completed'
                : idx === activeIndex
                  ? 'active'
                  : 'pending'
            const isLast = idx === STAGES.length - 1

            return (
              <React.Fragment key={stage.id}>
                <StageBadge label={stage.label} state={state} />
                {!isLast && (
                  <span
                    style={{
                      color:
                        idx < activeIndex ? 'var(--green)' : 'var(--dim)',
                      fontSize: '0.75rem',
                      fontFamily: 'var(--mono)',
                      padding: '0 2px',
                    }}
                  >
                    →
                  </span>
                )}
              </React.Fragment>
            )
          })}
        </div>

        <div
          style={{
            marginTop: 14,
            fontFamily: 'var(--mono)',
            fontSize: '0.65rem',
            color: 'var(--dim)',
            display: 'flex',
            alignItems: 'center',
            gap: 8,
          }}
        >
          <span>Estimated time remaining for current stage:</span>
          <span style={{ color: 'var(--amber)', fontWeight: 600 }}>
            {formatETA(visual?.eta_seconds)}
          </span>
        </div>
      </div>

      {/* ── LLM Narrative Panel ── */}
      <div
        className="agit-panel"
        style={{ borderTop: '2px solid var(--amber)' }}
      >
        <div
          className="agit-panel-title"
          style={{ color: 'var(--amber)', textShadow: '0 0 10px var(--amber-glow)' }}
        >
          Learning Narrative
        </div>

        <div
          style={{
            background: 'rgba(4,8,16,0.6)',
            border: '1px solid rgba(255,215,0,0.15)',
            borderRadius: 10,
            padding: 18,
            fontFamily: 'var(--mono)',
            fontSize: '0.8rem',
            lineHeight: 1.65,
            color: 'var(--text)',
            minHeight: 90,
            position: 'relative',
          }}
        >
          <div
            style={{
              position: 'absolute',
              top: 10,
              right: 14,
              fontSize: '0.58rem',
              color: 'var(--dim)',
              textTransform: 'uppercase',
              letterSpacing: '0.1em',
            }}
          >
            LLM Narrator v1.0
          </div>

          <TypewriterText text={explanation} key={activeStageId} />

          {/* Blinking cursor */}
          <span
            style={{
              display: 'inline-block',
              width: 8,
              height: 14,
              background: 'var(--cyan)',
              marginLeft: 4,
              animation: 'blink 1s step-end infinite',
              verticalAlign: 'middle',
            }}
          />
        </div>
      </div>
    </section>
  )
}

export default TrainingProgressPanel
