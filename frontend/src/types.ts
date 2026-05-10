export interface PatternRecord {
  symbol?: string
  pattern_name?: string
  pattern?: string
  type?: string
  regime?: string
  discovered_at?: string
  count?: number
  details?: any
}

export interface PerpetualImprovementSnapshot {
  last_improvement_action?: any
  adaptation_history?: any[]
  learning_rates?: { [model: string]: { [param: string]: number } }
}

export interface AccountInfo {
  balance?: number
  equity?: number
  free_margin?: number
  profit?: number
  open_positions?: number
  positions?: any[]
  realized_today?: number
  drawdown_pct?: number
  connected?: boolean
  login?: number | string
  server?: string
  name?: string
  currency?: string
  leverage?: number
}

export interface TrainingVisual {
  state?: string
  current_symbol?: string
  progress_pct?: number
  queue?: any[]
  fail_reason?: string
  /* ── Progress-panel extensions ── */
  current_epoch?: number
  total_epochs?: number
  loss?: number
  val_loss?: number
  current_timestep?: number
  target_timesteps?: number
  current_step?: number
  target_steps?: number
  eta_seconds?: number | null
}

export interface TrainingPipelineSummary {
  symbols_total?: number
  training_active_symbols?: number
  canary_review_symbols?: number
  champion_live_symbols?: number
  trading_ready_symbols?: number
  trading_active_symbols?: number
}

export interface TrainingLaneSummary {
  actionable_symbols?: number
  executed_symbols?: number
  blocked_symbols?: number
  neutral_symbols?: number
  open_positions?: number
}

export interface TrainingState {
  cycle_running?: boolean
  lstm_running?: boolean
  drl_running?: boolean
  dreamer_running?: boolean
  configured_symbols?: string[]
  visual?: {
    lstm?: TrainingVisual
    ppo?: TrainingVisual
    dreamer?: TrainingVisual
    active_label?: string
  }
  pattern_library?: { [pattern_name: string]: PatternRecord }
  symbol_stage_rows?: any[]
  symbol_lane_rows?: any[]
  pipeline_summary?: TrainingPipelineSummary
  cycle_heartbeat?: any
  lane_summary?: TrainingLaneSummary
}

export interface ServerInfo {
  running?: boolean
  pids?: number[]
}

export interface CanaryGate {
  ready?: boolean
  reason?: string
}

export interface SystemTruth {
  system_mode?: string
  execution_transport?: string
  real_money_locked?: boolean
  live_lock_reason?: string
}

export interface DataTruth {
  source?: string
  status?: string
  latest_dataset_id?: string
}

export interface ModelsTruth {
  bundle_id?: string
  lstm_status?: string
  rainforest_status?: string
  dreamer_status?: string
  ppo_status?: string
  ensemble_status?: string
}

export interface ValidationTruth {
  backtest_status?: string
  walk_forward_status?: string
  promotion_status?: string
  champion_status?: string
}

export interface TestsTruth {
  status?: string
  open_failures?: number
  open_errors?: number
}

export interface StatusPayload {
  state?: string
  server?: ServerInfo
  account?: AccountInfo
  training?: TrainingState
  canary_gate?: CanaryGate
  active_models?: any
  incidents?: any[]
  logs?: { [key: string]: string }
  registry_summary?: any
  telegram?: any
  repo_root?: string
  risk?: {
    halt?: boolean
    haltReason?: string
    drawdownPct?: number
    canTrade?: boolean
    maxPositionsPerSymbol?: number
    riskPerTradePct?: number
  }
  models?: any
  system?: SystemTruth
  data?: DataTruth
  validation?: ValidationTruth
  tests?: TestsTruth
}

export interface AgentStatus {
  id: string
  name: string
  role: string
  status: 'Online' | 'Training' | 'Idle' | 'Error'
  lastActivity: string
  metric: string
  logs: string
}
