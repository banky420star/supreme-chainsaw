import React from 'react'
import { PipelineStage } from '../types'
import TruthBadge from './TruthBadge'
import LoadingBar from './LoadingBar'

const colors = {
  bg: '#0d1726', panelBg: 'rgba(13,23,38,0.92)', border: 'rgba(255,255,255,0.08)',
  text: '#eef5ff', muted: '#97a9c6', cyan: '#5ad7ff',
}

const STAGE_ORDER = [
  'mt5_data', 'validation', 'features', 'labels', 'lstm', 'rainforest',
  'dreamer', 'ppo', 'meta_controller', 'bundle', 'backtest',
  'walk_forward', 'baseline', 'demo_canary', 'champion_rejected',
  'trade_journal', 'trade_coroner', 'replay_dataset', 'retraining_trigger',
]

const STAGE_NAMES: Record<string, string> = {
  mt5_data: 'MT5 Data',
  validation: 'Validation',
  features: 'Features',
  labels: 'Labels',
  lstm: 'LSTM',
  rainforest: 'Rainforest',
  dreamer: 'Dreamer',
  ppo: 'PPO',
  meta_controller: 'Meta Controller',
  bundle: 'Bundle',
  backtest: 'Backtest',
  walk_forward: 'Walk-Forward',
  baseline: 'Baseline',
  demo_canary: 'Demo Canary',
  champion_rejected: 'Champion/Rejected',
  trade_journal: 'Trade Journal',
  trade_coroner: 'Trade Coroner',
  replay_dataset: 'Replay Dataset',
  retraining_trigger: 'Retraining Trigger',
}

function toneFromStatus(status?: string): any {
  if (!status) return 'gray'
  const s = status.toLowerCase()
  if (s === 'passed' || s === 'online') return 'green'
  if (s === 'running' || s === 'active') return 'blue'
  if (s === 'warning' || s === 'degraded') return 'yellow'
  if (s === 'failed' || s === 'blocked' || s === 'error') return 'red'
  return 'gray'
}

const PipelinePanel: React.FC = () => {
  const [stages, setStages] = React.useState<PipelineStage[]>([])
  const [loading, setLoading] = React.useState(true)

  React.useEffect(() => {
    let cancelled = false
    const load = async () => {
      setLoading(true)
      try {
        const r = await fetch(`${''}/api/pipeline/stages`, { cache: 'no-store' })
        const data = r.ok ? await r.json() : []
        if (!cancelled) setStages(Array.isArray(data) ? data : [])
      } catch {
        if (!cancelled) setStages([])
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    const id = setInterval(load, 15_000)
    return () => { cancelled = true; clearInterval(id) }
  }, [])

  const byId = React.useMemo(() => {
    const map: Record<string, PipelineStage> = {}
    for (const s of stages) map[s.id] = s
    return map
  }, [stages])

  return (
    <div style={{ background: colors.bg, color: colors.text, padding: 20 }}>
      <h2 style={{ margin: '0 0 16px', fontSize: 18, color: colors.cyan, fontWeight: 700 }}>Pipeline</h2>

      {loading && stages.length === 0 && <LoadingBar label="Loading pipeline stages..." />}

      {!loading && stages.length === 0 && (
        <div style={{ color: colors.muted, padding: 20 }}>No pipeline stage data available.</div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: 12 }}>
        {STAGE_ORDER.map((id) => {
          const s = byId[id]
          const name = STAGE_NAMES[id] ?? id
          const status = s?.status ?? 'unknown'
          const tone = toneFromStatus(status)
          return (
            <div
              key={id}
              style={{
                background: colors.panelBg,
                border: `1px solid ${colors.border}`,
                borderRadius: 10,
                padding: 14,
                borderLeft: `3px solid ${
                  tone === 'green' ? '#00ff88' : tone === 'blue' ? '#00f0ff' : tone === 'yellow' ? '#ffd700' : tone === 'red' ? '#ff3366' : '#4a6078'
                }`,
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                <span style={{ fontSize: 13, fontWeight: 700 }}>{name}</span>
                <TruthBadge tone={tone} label={status} dot={false} />
              </div>
              <div style={{ fontSize: 11, color: colors.muted, fontFamily: 'monospace', marginBottom: 4 }}>
                Last: {s?.last_run ?? 'never'}
              </div>
              <div style={{ fontSize: 11, color: colors.muted, fontFamily: 'monospace', marginBottom: 4 }}>
                Artifact: {s?.artifact_id ?? 'none'}
              </div>
              {s?.blockers && s.blockers.length > 0 && (
                <div style={{ fontSize: 11, color: '#ff7b8f', marginTop: 4 }}>
                  Blockers: {s.blockers.join(', ')}
                </div>
              )}
              {s?.metrics && Object.keys(s.metrics).length > 0 && (
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 6 }}>
                  {Object.entries(s.metrics).map(([k, v]) => (
                    <span key={k} style={{ fontSize: 10, color: colors.muted, fontFamily: 'monospace' }}>
                      {k}: {v != null ? String(v) : '--'}
                    </span>
                  ))}
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

export default PipelinePanel
