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

/* ═══════════════════════════════════════════════════════════════
   NEW MISSION CONTROL TYPES
   ═══════════════════════════════════════════════════════════════ */

export interface SystemHeaderState {
  system_mode: 'paper_sim' | 'demo_live' | 'real_live_locked' | 'real_live' | 'unknown'
  execution_transport: 'sim' | 'mt5' | 'unknown'
  real_money_locked: boolean
  live_lock_reason: string
  api_status: 'online' | 'degraded' | 'offline'
  mt5_bridge_status: 'online' | 'degraded' | 'offline'
  account_type: 'demo' | 'real' | 'unknown'
  account_type_verified: boolean
  account_telemetry_valid: boolean
  tests_status: 'passing' | 'failing' | 'unknown'
  open_test_failures: number
  open_test_errors: number
  active_bundle_id: string | null
  champion_status: 'champion' | 'candidate' | 'rejected' | 'none'
}

export interface PipelineStage {
  id: string
  name: string
  status: 'passed' | 'running' | 'warning' | 'failed' | 'blocked' | 'unknown' | 'idle'
  last_run: string | null
  artifact_id: string | null
  blockers: string[]
  metrics: Record<string, number | string | null>
}

export interface ModelBrainLSTM {
  status: string
  model_id: string | null
  lookback: number | null
  feature_set: string | null
  p_up: number | null
  p_down: number | null
  p_flat: number | null
  expected_return: number | null
  confidence: number | null
  calibration_error: number | null
  influence_enabled: boolean
}

export interface ModelBrainRainforest {
  status: string
  regime: string | null
  confidence: number | null
  allowed_modes: string[]
  blocked_modes: string[]
  feature_importance: Record<string, number>
  lift_vs_no_rainforest: number | null
}

export interface ModelBrainDreamer {
  status: string
  stub_disabled: boolean
  rollouts: number | null
  horizon: number | null
  expected_reward: number | null
  expected_drawdown: number | null
  ruin_probability: number | null
  used_for_decisions: boolean
}

export interface ModelBrainPPO {
  status: string
  training_status: string
  actual_timesteps: number | null
  configured_timesteps: number | null
  reward_version: string | null
  action_bias: number | null
  promotion_status: string | null
}

export interface ModelBrains {
  lstm: ModelBrainLSTM
  rainforest: ModelBrainRainforest
  dreamer: ModelBrainDreamer
  ppo: ModelBrainPPO
}

export interface TrainingLaneCard {
  lane_id: string
  lane_name: string
  status: string
  progress_pct: number | null
  model_id: string | null
  timesteps: number | null
  validation_summary: string | null
  failure_reason: string | null
}

export interface ModelBundle {
  bundle_id: string
  symbol: string
  timeframe: string
  status: string
  data_source: string | null
  feature_set: string | null
  lstm: string | null
  rainforest: string | null
  dreamer: string | null
  ppo: string | null
  backtest_return: number | null
  walk_forward: number | null
  canary: number | null
  promotion_decision: string | null
  promotion_reason: string | null
}

export interface PromotionGateItem {
  gate: string
  required: number | string | boolean
  actual: number | string | boolean | null
  passed: boolean
  pending: boolean
}

export interface DemoCanaryMetrics {
  trades: number
  days: number
  pnl: number
  drawdown: number
  profit_factor: number | null
  win_rate: number | null
}

export interface DemoCanaryTimelineEvent {
  step: string
  ts: string
  status: string
  detail: string
}

export interface DemoCanaryState {
  account_type: 'demo'
  real_money_locked: true
  metrics: DemoCanaryMetrics
  timeline: DemoCanaryTimelineEvent[]
}

export interface TradeCoronerCluster {
  cluster_id: string
  count: number
  root_cause: string
  affected_symbols: string[]
  recommended_experiment: string
  retraining_eligible: boolean
}

export interface TradeCoronerState {
  clusters: TradeCoronerCluster[]
  total_mistakes: number
  total_reviewed: number
}

export interface PatternVerification {
  pattern_id: string
  pattern_name: string
  confidence: number
  regime: string
  outcome: string
  verified: boolean
  fallback_incidents: number
}

export interface PerpetualImprovementState {
  loop_status: string
  learning_events: Array<{
    ts: string
    event: string
    symbol: string
    model: string
  }>
  candidate_experiments: string[]
}

/* ═══════════════════════════════════════════════════════════════
   Decision PPO + Execution Rich Telemetry (Observability Completion)
   Full TradeDecision specs + execution reports + feedback for panels.
   ═══════════════════════════════════════════════════════════════ */
export interface TradeDecisionSize { mode: string; value: number; max_lots_cap?: number | null; min_lots_floor?: number }
export interface TradeDecisionExit { type: string; value: number; price?: number | null }
export interface TradeDecisionTrailing { type: string; trigger: number; distance: number; step?: number; atr_period?: number }
export interface TradeDecisionLadderLevel { level: number; close_pct: number; type: string }
export interface TradeDecisionSpec {
  decision_id: string
  timestamp: string
  source: string
  symbol: string
  side: 'LONG' | 'SHORT' | 'FLAT'
  size: TradeDecisionSize
  sl: TradeDecisionExit
  tp: TradeDecisionExit
  trailing: TradeDecisionTrailing
  tp_ladder?: { levels: TradeDecisionLadderLevel[]; of_original_size?: boolean } | null
  confidence?: number
  tags?: Record<string, any>
}

export interface ExecutionReport {
  decision_id: string
  ts: string
  status: string
  fills: any[]
  partials: any[]
  trailing_updates: any[]
  current_sl?: number | null
  current_tp?: number | null
  realized_pnl: number
  open_volume: number
  error?: string | null
  backend: string
  mql5_command_written?: boolean
  decision?: TradeDecisionSpec  // full rich spec when emitted
  extra?: Record<string, any>
}

export interface DecisionExecutionState {
  decisions: ExecutionReport[]
  count: number
  live?: any
  feedback?: any[]
}

export interface AgentOperationalStatus {
  agent_id: string
  agent_name: string
  status: string
  heartbeat: string | null
  current_task: string | null
  last_artifact: string | null
  error_count: number
}

export interface SafetyGate {
  name: string
  passed: boolean
  required: boolean | string | number
  actual: boolean | string | number | null
  reason: string | null
}

export interface SafetyState {
  real_money_locked: boolean
  lock_reasons: string[]
  gates: SafetyGate[]
}

export interface EvidenceArtifact {
  name: string
  created_at: string
  status: string
  linked_model: string | null
  path: string
}
