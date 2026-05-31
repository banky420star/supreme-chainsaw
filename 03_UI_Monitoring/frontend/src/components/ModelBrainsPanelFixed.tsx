/**
 * ModelBrainsPanel Component - FIXED VERSION
 *
 * Displays the status and diagnostics of the four AI "brains" (models):
 * - LSTM: Sequence pattern recognition
 * - Rainforest: Regime detection and classification
 * - Dreamer: World model for scenario planning
 * - PPO: Policy gradient optimization
 *
 * IMPROVEMENTS:
 * - Better error handling
 * - Visual feedback for empty states
 * - Explanations for each model type
 * - Help tooltips for metrics
 */
import React from 'react'
import { ModelBrains, fetchModelBrains } from '../services/api'
import TruthBadge from './TruthBadge'
import LoadingBar from './LoadingBar'
import HelpTooltip from './HelpTooltip'

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
  purple: '#a78bfa',
}

const panelStyle: React.CSSProperties = {
  background: colors.panelBg,
  border: `1px solid ${colors.border}`,
  borderRadius: 10,
  padding: 16,
  marginBottom: 16,
}

const cardStyle: React.CSSProperties = {
  background: colors.bg,
  border: `1px solid ${colors.border}`,
  borderRadius: 8,
  padding: 14,
  flex: 1,
  minWidth: 280,
}

const labelStyle: React.CSSProperties = {
  fontSize: 11,
  color: colors.muted,
  textTransform: 'uppercase',
  letterSpacing: 0.5,
  marginBottom: 4,
  fontWeight: 600,
}

const mono: React.CSSProperties = {
  fontFamily: 'monospace',
  fontSize: 12,
  color: colors.text,
}

function brainTone(status?: string): any {
  if (!status) return 'gray'
  const s = status.toLowerCase()
  if (s === 'trained' || s === 'online' || s === 'champion' || s === 'active') return 'green'
  if (s === 'training' || s === 'candidate' || s === 'validating') return 'blue'
  if (s === 'stub_disabled' || s === 'undertrained' || s === 'stale' || s === 'unaudited' || s === 'informational-only') return 'yellow'
  if (s === 'failed' || s === 'error' || s === 'offline' || s === 'blocked') return 'red'
  if (s === 'unknown') return 'gray'
  return 'gray'
}

function fmtNum(v: number | null | undefined, digits = 4): string {
  if (v == null || isNaN(v)) return '--'
  return v.toFixed(digits)
}

function fmtPct(v: number | null | undefined): string {
  if (v == null || isNaN(v)) return '--'
  return `${(v * 100).toFixed(1)}%`
}

// Help text for model concepts
const HELP_TEXTS = {
  lstm: "LSTM (Long Short-Term Memory) analyzes price sequences to detect patterns and trends. It predicts whether prices will go up, down, or stay flat.",
  rainforest: "Rainforest is a Random Forest classifier that detects market regimes (bull trend, bear trend, ranging). It helps the system adapt to different market conditions.",
  dreamer: "Dreamer is a world model that simulates future scenarios. Currently stubbed/disabled in this version. When enabled, it predicts future market states for better planning.",
  ppo: "PPO (Proximal Policy Optimization) is a reinforcement learning agent. It learns optimal trading strategies through trial and error, continuously improving from experience.",
  p_up: "Probability that price will go up",
  p_down: "Probability that price will go down",
  p_flat: "Probability that price will stay flat",
  confidence: "Model's confidence in its prediction (0-1)",
  expectedReturn: "Expected return from the predicted move",
  regime: "Current market condition detected by Rainforest",
}

const ModelBrainsPanelFixed: React.FC = () => {
  const [brains, setBrains] = React.useState<ModelBrains | null>(null)
  const [loading, setLoading] = React.useState(true)
  const [error, setError] = React.useState<string | null>(null)

  React.useEffect(() => {
    let cancelled = false
    const load = async () => {
      setLoading(true)
      setError(null)
      try {
        const data = await fetchModelBrains()
        if (!cancelled) {
          setBrains(data)
          if (!data) {
            setError('No model brain data returned from API')
          }
        }
      } catch (err: any) {
        console.error('ModelBrainsPanel load error:', err)
        if (!cancelled) {
          setError(err?.message || 'Failed to load model brain data')
          setBrains(null)
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    const id = setInterval(load, 15_000)
    return () => { cancelled = true; clearInterval(id) }
  }, [])

  const lstm = brains?.lstm
  const rf = brains?.rainforest
  const dreamer = brains?.dreamer
  const ppo = brains?.ppo

  // Debug info
  console.log('ModelBrainsPanel render:', { loading, error, hasData: !!brains, lstm, rf, dreamer, ppo })

  return (
    <div style={{ background: colors.bg, color: colors.text, padding: 20 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 16 }}>
        <h2 style={{ margin: 0, fontSize: 18, color: colors.cyan, fontWeight: 700 }}>
          Model Brains
        </h2>
        <HelpTooltip
          title="AI Model Diagnostics"
          text="This panel shows the status of the four AI 'brains' that make trading decisions. Each model provides different insights into market conditions."
        />
      </div>

      {loading && !brains && <LoadingBar label="Loading model brains..." />}

      {error && (
        <div style={{ ...panelStyle, border: `1px solid ${colors.red}`, background: 'rgba(255,123,143,0.08)' }}>
          <div style={{ color: colors.red, fontWeight: 600, marginBottom: 8 }}>Error Loading Models</div>
          <div style={{ color: colors.muted, fontSize: 13 }}>{error}</div>
        </div>
      )}

      {!loading && !error && !brains && (
        <div style={panelStyle}>
          <div style={{ color: colors.muted, marginBottom: 8 }}>No model brain data available.</div>
          <div style={{ fontSize: 12, color: colors.amber }}>
            This is normal when the system has just started. Models will appear after training completes.
          </div>
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: 14 }}>
        {/* LSTM Card */}
        <div style={cardStyle}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span style={{ fontSize: 14, fontWeight: 700, color: colors.cyan }}>LSTM</span>
              <HelpTooltip text={HELP_TEXTS.lstm} />
            </div>
            <TruthBadge tone={brainTone(lstm?.status)} label={lstm?.status ?? 'unknown'} dot={false} />
          </div>

          {lstm?.status === 'unknown' ? (
            <div style={{ padding: '10px', background: 'rgba(74,96,120,0.12)', borderRadius: 6, fontSize: 12, color: colors.muted }}>
              No LSTM model loaded yet. Train a model to see results here.
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              <div><span style={labelStyle}>Model ID</span><div style={mono}>{lstm?.model_id ?? 'none'}</div></div>
              <div><span style={labelStyle}>Lookback</span><div style={mono}>{lstm?.lookback ?? '--'} bars</div></div>
              <div><span style={labelStyle}>Feature Set</span><div style={mono}>{lstm?.feature_set ?? '--'}</div></div>

              <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
                <div>
                  <span style={labelStyle}>p_up <HelpTooltip text={HELP_TEXTS.p_up} size="sm" /></span>
                  <div style={mono}>{fmtNum(lstm?.p_up, 3)}</div>
                </div>
                <div>
                  <span style={labelStyle}>p_down <HelpTooltip text={HELP_TEXTS.p_down} size="sm" /></span>
                  <div style={mono}>{fmtNum(lstm?.p_down, 3)}</div>
                </div>
                <div>
                  <span style={labelStyle}>p_flat <HelpTooltip text={HELP_TEXTS.p_flat} size="sm" /></span>
                  <div style={mono}>{fmtNum(lstm?.p_flat, 3)}</div>
                </div>
              </div>

              <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
                <div>
                  <span style={labelStyle}>Expected Return <HelpTooltip text={HELP_TEXTS.expectedReturn} size="sm" /></span>
                  <div style={mono}>{fmtNum(lstm?.expected_return, 4)}</div>
                </div>
                <div>
                  <span style={labelStyle}>Confidence <HelpTooltip text={HELP_TEXTS.confidence} size="sm" /></span>
                  <div style={mono}>{fmtPct(lstm?.confidence)}</div>
                </div>
                <div>
                  <span style={labelStyle}>Calib Error</span>
                  <div style={mono}>{fmtNum(lstm?.calibration_error, 4)}</div>
                </div>
              </div>

              <div>
                <span style={labelStyle}>Influence</span>
                <TruthBadge tone={lstm?.influence_enabled ? 'green' : 'gray'} label={lstm?.influence_enabled ? 'ENABLED' : 'DISABLED'} dot={false} />
              </div>
            </div>
          )}
        </div>

        {/* Rainforest Card */}
        <div style={cardStyle}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span style={{ fontSize: 14, fontWeight: 700, color: colors.green }}>Rainforest</span>
              <HelpTooltip text={HELP_TEXTS.rainforest} />
            </div>
            <TruthBadge tone={brainTone(rf?.status)} label={rf?.status ?? 'unknown'} dot={false} />
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            <div>
              <span style={labelStyle}>Regime <HelpTooltip text={HELP_TEXTS.regime} size="sm" /></span>
              <div style={{ ...mono, color: rf?.regime === 'bull_trend' ? colors.green : rf?.regime === 'bear_trend' ? colors.red : colors.text }}>
                {rf?.regime ?? '--'}
              </div>
            </div>
            <div><span style={labelStyle}>Confidence</span><div style={mono}>{fmtPct(rf?.confidence)}</div></div>
            <div><span style={labelStyle}>Lift vs No-Rainforest</span><div style={mono}>{fmtNum(rf?.lift_vs_no_rainforest, 4)}</div></div>

            <div>
              <span style={labelStyle}>Allowed Modes</span>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginTop: 4 }}>
                {(rf?.allowed_modes ?? []).length === 0 ? (
                  <span style={{ fontSize: 11, color: colors.muted }}>none</span>
                ) : (
                  rf?.allowed_modes.map((m) => (
                    <span key={m} style={{ fontSize: 10, padding: '2px 6px', borderRadius: 4, background: 'rgba(57,217,138,0.12)', color: colors.green }}>{m}</span>
                  ))
                )}
              </div>
            </div>

            <div>
              <span style={labelStyle}>Blocked Modes</span>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginTop: 4 }}>
                {(rf?.blocked_modes ?? []).length === 0 ? (
                  <span style={{ fontSize: 11, color: colors.muted }}>none</span>
                ) : (
                  rf?.blocked_modes.map((m) => (
                    <span key={m} style={{ fontSize: 10, padding: '2px 6px', borderRadius: 4, background: 'rgba(255,123,143,0.12)', color: colors.red }}>{m}</span>
                  ))
                )}
              </div>
            </div>

            {rf?.feature_importance && Object.keys(rf.feature_importance).length > 0 && (
              <div>
                <span style={labelStyle}>Feature Importance</span>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 3, marginTop: 4 }}>
                  {Object.entries(rf.feature_importance)
                    .sort(([, a], [, b]) => (b as number) - (a as number))
                    .slice(0, 6)
                    .map(([k, v]) => (
                      <div key={k} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, fontFamily: 'monospace' }}>
                        <span style={{ color: colors.muted }}>{k}</span>
                        <span style={{ color: colors.text }}>{fmtNum(v as number, 4)}</span>
                      </div>
                    ))}
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Dreamer Card */}
        <div style={cardStyle}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span style={{ fontSize: 14, fontWeight: 700, color: colors.purple }}>Dreamer</span>
              <HelpTooltip text={HELP_TEXTS.dreamer} />
            </div>
            <TruthBadge tone={brainTone(dreamer?.status)} label={dreamer?.status ?? 'unknown'} dot={false} />
          </div>

          {dreamer?.stub_disabled ? (
            <div style={{ padding: '10px', background: 'rgba(243,187,74,0.10)', borderRadius: 6, fontSize: 12, color: colors.amber, border: `1px solid rgba(243,187,74,0.20)` }}>
              <strong>Stub Disabled</strong><br />
              Dreamer world model is not available in this version. The system uses LSTM + PPO for trading decisions.
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              <div><span style={labelStyle}>Rollouts</span><div style={mono}>{dreamer?.rollouts ?? '--'}</div></div>
              <div><span style={labelStyle}>Horizon</span><div style={mono}>{dreamer?.horizon ?? '--'}</div></div>
              <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
                <div><span style={labelStyle}>Expected Reward</span><div style={mono}>{fmtNum(dreamer?.expected_reward, 4)}</div></div>
                <div><span style={labelStyle}>Expected Drawdown</span><div style={mono}>{fmtNum(dreamer?.expected_drawdown, 4)}</div></div>
                <div><span style={labelStyle}>Ruin Probability</span><div style={mono}>{fmtPct(dreamer?.ruin_probability)}</div></div>
              </div>
              <div>
                <span style={labelStyle}>Used For Decisions</span>
                <TruthBadge tone={dreamer?.used_for_decisions ? 'green' : 'gray'} label={dreamer?.used_for_decisions ? 'YES' : 'NO'} dot={false} />
              </div>
            </div>
          )}
        </div>

        {/* PPO Card */}
        <div style={cardStyle}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span style={{ fontSize: 14, fontWeight: 700, color: colors.amber }}>PPO</span>
              <HelpTooltip text={HELP_TEXTS.ppo} />
            </div>
            <TruthBadge tone={brainTone(ppo?.status)} label={ppo?.status ?? 'unknown'} dot={false} />
          </div>

          {ppo?.status === 'undertrained' || ppo?.status === 'unknown' ? (
            <div style={{ padding: '10px', background: 'rgba(243,187,74,0.10)', borderRadius: 6, fontSize: 12, color: colors.amber }}>
              <strong>Undertrained</strong><br />
              PPO model needs more training to be effective. Current: {ppo?.actual_timesteps ?? 0} / {ppo?.configured_timesteps ?? 500000} timesteps.
            </div>
          ) : null}

          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            <div><span style={labelStyle}>Training Status</span><div style={mono}>{ppo?.training_status ?? '--'}</div></div>
            <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
              <div><span style={labelStyle}>Actual Timesteps</span><div style={mono}>{ppo?.actual_timesteps?.toLocaleString() ?? '--'}</div></div>
              <div><span style={labelStyle}>Configured</span><div style={mono}>{ppo?.configured_timesteps?.toLocaleString() ?? '--'}</div></div>
            </div>
            <div><span style={labelStyle}>Reward Version</span><div style={mono}>{ppo?.reward_version ?? '--'}</div></div>
            <div><span style={labelStyle}>Action Bias</span><div style={mono}>{fmtNum(ppo?.action_bias, 4)}</div></div>
            <div><span style={labelStyle}>Promotion Status</span><div style={mono}>{ppo?.promotion_status ?? '--'}</div></div>
          </div>
        </div>
      </div>

      {/* Legend */}
      <div style={{ ...panelStyle, marginTop: 16 }}>
        <div style={{ fontSize: 12, color: colors.muted, marginBottom: 8 }}>
          <strong style={{ color: colors.text }}>Status Legend:</strong>
        </div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
          <TruthBadge tone="green" label="Trained/Active" dot={false} />
          <TruthBadge tone="blue" label="Training" dot={false} />
          <TruthBadge tone="yellow" label="Undertrained/Stubbed" dot={false} />
          <TruthBadge tone="red" label="Failed/Error" dot={false} />
          <TruthBadge tone="gray" label="Unknown" dot={false} />
        </div>
      </div>
    </div>
  )
}

export default ModelBrainsPanelFixed
