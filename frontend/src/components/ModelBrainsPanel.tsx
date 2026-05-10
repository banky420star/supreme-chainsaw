import React from 'react'
import { ModelBrains, fetchModelBrains } from '../services/api'
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
  minWidth: 240,
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
  if (s === 'stub_disabled' || s === 'undertrained' || s === 'stale' || s === 'unaudited') return 'yellow'
  if (s === 'failed' || s === 'error' || s === 'offline' || s === 'blocked') return 'red'
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

const ModelBrainsPanel: React.FC = () => {
  const [brains, setBrains] = React.useState<ModelBrains | null>(null)
  const [loading, setLoading] = React.useState(true)

  React.useEffect(() => {
    let cancelled = false
    const load = async () => {
      setLoading(true)
      try {
        const data = await fetchModelBrains()
        if (!cancelled) setBrains(data)
      } catch {
        if (!cancelled) setBrains(null)
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

  return (
    <div style={{ background: colors.bg, color: colors.text, padding: 20 }}>
      <h2 style={{ margin: '0 0 16px', fontSize: 18, color: colors.cyan, fontWeight: 700 }}>
        Model Brains
      </h2>

      {loading && !brains && (
        <div style={{ ...panelStyle, color: colors.muted }}>Loading model brains...</div>
      )}
      {!loading && !brains && (
        <div style={{ ...panelStyle, color: colors.muted }}>
          No model brain data available. The endpoint returned empty.
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: 14 }}>
        {/* LSTM */}
        <div style={cardStyle}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
            <span style={{ fontSize: 13, fontWeight: 700, color: colors.cyan }}>LSTM</span>
            <TruthBadge tone={brainTone(lstm?.status)} label={lstm?.status ?? 'unknown'} dot={false} />
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            <div><span style={labelStyle}>Model ID</span><div style={mono}>{lstm?.model_id ?? 'none'}</div></div>
            <div><span style={labelStyle}>Lookback</span><div style={mono}>{lstm?.lookback ?? '--'}</div></div>
            <div><span style={labelStyle}>Feature Set</span><div style={mono}>{lstm?.feature_set ?? '--'}</div></div>
            <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
              <div><span style={labelStyle}>p_up</span><div style={mono}>{fmtNum(lstm?.p_up, 3)}</div></div>
              <div><span style={labelStyle}>p_down</span><div style={mono}>{fmtNum(lstm?.p_down, 3)}</div></div>
              <div><span style={labelStyle}>p_flat</span><div style={mono}>{fmtNum(lstm?.p_flat, 3)}</div></div>
            </div>
            <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
              <div><span style={labelStyle}>Expected Return</span><div style={mono}>{fmtNum(lstm?.expected_return, 4)}</div></div>
              <div><span style={labelStyle}>Confidence</span><div style={mono}>{fmtPct(lstm?.confidence)}</div></div>
              <div><span style={labelStyle}>Calib Error</span><div style={mono}>{fmtNum(lstm?.calibration_error, 4)}</div></div>
            </div>
            <div>
              <span style={labelStyle}>Influence</span>
              <TruthBadge tone={lstm?.influence_enabled ? 'green' : 'gray'} label={lstm?.influence_enabled ? 'ENABLED' : 'DISABLED'} dot={false} />
            </div>
          </div>
        </div>

        {/* Rainforest */}
        <div style={cardStyle}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
            <span style={{ fontSize: 13, fontWeight: 700, color: colors.green }}>Rainforest</span>
            <TruthBadge tone={brainTone(rf?.status)} label={rf?.status ?? 'unknown'} dot={false} />
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            <div><span style={labelStyle}>Regime</span><div style={mono}>{rf?.regime ?? '--'}</div></div>
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

        {/* Dreamer */}
        <div style={cardStyle}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
            <span style={{ fontSize: 13, fontWeight: 700, color: colors.purple }}>Dreamer</span>
            <TruthBadge tone={brainTone(dreamer?.status)} label={dreamer?.status ?? 'unknown'} dot={false} />
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {dreamer?.stub_disabled && (
              <div style={{ padding: '6px 8px', background: 'rgba(243,187,74,0.10)', borderRadius: 4, fontSize: 12, color: colors.amber, border: `1px solid rgba(243,187,74,0.20)` }}>
                Stub disabled — no artifact found.
              </div>
            )}
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
        </div>

        {/* PPO */}
        <div style={cardStyle}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
            <span style={{ fontSize: 13, fontWeight: 700, color: colors.amber }}>PPO</span>
            <TruthBadge tone={brainTone(ppo?.status)} label={ppo?.status ?? 'unknown'} dot={false} />
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            <div><span style={labelStyle}>Training Status</span><div style={mono}>{ppo?.training_status ?? '--'}</div></div>
            <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
              <div><span style={labelStyle}>Actual Timesteps</span><div style={mono}>{ppo?.actual_timesteps ?? '--'}</div></div>
              <div><span style={labelStyle}>Configured</span><div style={mono}>{ppo?.configured_timesteps ?? '--'}</div></div>
            </div>
            <div><span style={labelStyle}>Reward Version</span><div style={mono}>{ppo?.reward_version ?? '--'}</div></div>
            <div><span style={labelStyle}>Action Bias</span><div style={mono}>{fmtNum(ppo?.action_bias, 4)}</div></div>
            <div><span style={labelStyle}>Promotion Status</span><div style={mono}>{ppo?.promotion_status ?? '--'}</div></div>
          </div>
        </div>
      </div>
    </div>
  )
}

export default ModelBrainsPanel
