import React from 'react'
import { StatusPayload } from '../types'

interface Props {
  status: StatusPayload
}

const panelBg = 'rgba(13,23,38,0.92)'
const innerBg = '#0a111a'
const borderColor = '#334'
const textColor = '#eef5ff'
const mutedColor = '#889'
const accentBlue = '#4fd6ff'
const profitGreen = '#22d68a'
const profitRed = '#f5475b'
const amber = '#f59e0b'

const cardOuter: React.CSSProperties = {
  background: panelBg,
  border: `1px solid ${borderColor}`,
  borderRadius: 8,
  padding: 16,
  marginBottom: 16,
}

const sectionHeading: React.CSSProperties = {
  fontSize: 16,
  fontWeight: 600,
  marginBottom: 10,
  color: textColor,
}

const stageBox = (active: boolean, color: string): React.CSSProperties => ({
  background: active ? `${color}15` : innerBg,
  border: `1px solid ${active ? color : borderColor}`,
  borderRadius: 6,
  padding: 12,
  position: 'relative' as const,
})

const stageTitle = (active: boolean, color: string): React.CSSProperties => ({
  fontSize: 13,
  fontWeight: 700,
  color: active ? color : mutedColor,
  marginBottom: 6,
  display: 'flex',
  alignItems: 'center',
  gap: 6,
})

const arrowDown: React.CSSProperties = {
  display: 'flex',
  justifyContent: 'center',
  alignItems: 'center',
  height: 24,
  color: mutedColor,
  fontSize: 16,
}

const codeBlock: React.CSSProperties = {
  background: '#050a10',
  borderRadius: 4,
  padding: '8px 10px',
  fontFamily: 'monospace',
  fontSize: 11,
  color: mutedColor,
  overflowX: 'auto' as const,
  lineHeight: 1.5,
}

const PipelinePanel: React.FC<Props> = ({ status }) => {
  const symbols = status?.training?.configured_symbols ?? []
  const lstmRunning = status?.training?.lstm_running
  const ppoRunning = status?.training?.drl_running
  const dreamerRunning = status?.training?.dreamer_running
  const cycleRunning = status?.training?.cycle_running
  const modelCount = status?.active_models ? Object.keys(status.active_models).length : 0

  const stages = [
    {
      id: 'ingest',
      title: '1. Data Ingestion',
      color: accentBlue,
      active: true,
      desc: 'Pulls OHLCV from MT5 via Wine/RPyC bridge',
      details: [
        `Source: MT5 terminal (Wine on macOS)`,
        `Symbols: ${symbols.join(', ') || '—'}`,
        `Timeframe: M5`,
        `Bars: up to 100,000 per symbol`,
        `Fallback: Dukascopy if MT5 unavailable`,
      ],
      files: ['Python/data_feed.py'],
      funcs: ['fetch_training_data()', '_fetch_mt5_data()', '_fetch_rates_any()'],
    },
    {
      id: 'features',
      title: '2. Feature Engineering',
      color: '#a855f7',
      active: true,
      desc: 'Transforms raw OHLCV into 150+ engineered features',
      details: [
        `Version: ultimate_150 (150 features)`,
        `Core: returns, RSI, ATR, MACD, BB width, stochastics`,
        `Fibonacci windows: 3,5,8,13,21,34,55 bars`,
        `Multi-timeframe: M15, H1, H4, D1 resampled`,
        `Cross-features: h1_trend - h4_trend, etc.`,
        `Temporal: hour_sin/cos, dow_sin/cos, month_sin/cos`,
      ],
      files: ['Python/feature_pipeline.py'],
      funcs: ['_build_ultimate_feature_frame()', 'build_env_feature_matrix()'],
    },
    {
      id: 'lstm',
      title: '3. LSTM Training',
      color: amber,
      active: lstmRunning,
      desc: 'Sequence model learns price patterns and regime classification',
      details: [
        `Status: ${lstmRunning ? 'TRAINING' : 'Idle'}`,
        `Input: 21 engineered features per timestep`,
        `Window: configurable (default 100 bars)`,
        `Output: regime probabilities (bull/bear/ranging/breakout/reversal)`,
        `Loss: categorical cross-entropy`,
      ],
      files: ['Python/agi_brain.py', 'Python/lstm_trainer.py'],
      funcs: ['_train_lstm_for_symbol()', 'build_lstm_feature_frame()'],
    },
    {
      id: 'ppo',
      title: '4. PPO Training',
      color: profitGreen,
      active: ppoRunning,
      desc: 'Policy Gradient learns when to BUY/SELL/HOLD',
      details: [
        `Status: ${ppoRunning ? 'TRAINING' : 'Idle'}`,
        `Algorithm: PPO (Proximal Policy Optimization)`,
        `Environment: custom trading env with 21-dim observation`,
        `Action space: continuous position sizing (-1 to +1)`,
        `Reward: v2_risk_adjusted (growth, sharpe, drawdown, cost)`,
        `VecNormalize: running mean/std normalization`,
        `EvalCallback: saves best model during training`,
      ],
      files: ['Python/ppo_trainer.py', 'Python/trading_env.py'],
      funcs: ['_train_ppo_for_symbol()', 'run_ppo_backtest()'],
    },
    {
      id: 'dreamer',
      title: '5. Dreamer Training',
      color: '#ec4899',
      active: dreamerRunning,
      desc: 'World model learns to imagine future states for planning',
      details: [
        `Status: ${dreamerRunning ? 'TRAINING' : 'Idle'}`,
        `Architecture: RSSM (Recurrent State-Space Model)`,
        `Learns: latent dynamics model from observations`,
        `Imagines: future trajectories for value estimation`,
        `Planning: model-predictive control for trade decisions`,
      ],
      files: ['Python/dreamer_policy.py'],
      funcs: ['_train_dreamer_for_symbol()'],
    },
    {
      id: 'backtest',
      title: '6. Backtesting & Validation',
      color: '#6366f1',
      active: cycleRunning,
      desc: 'Champion gates: forward windows, drawdown, sharpe, return checks',
      details: [
        `Status: ${cycleRunning ? 'RUNNING' : 'Idle'}`,
        `Method: vectorized backtest with loaded PPO model`,
        `Gates: max_drawdown ≤ 10%, min_sharpe ≥ 0.30, min_return ≥ 1.5%`,
        `Forward windows: 60d, 90d, 120d out-of-sample`,
        `Per-symbol: steps, drawdown, sharpe, return checks`,
        `Pass rate: 80% of symbols must pass gates`,
      ],
      files: ['Python/backtester.py', 'Python/model_evaluator.py'],
      funcs: ['run_multi()', 'evaluate_candidate_vs_champion()'],
    },
    {
      id: 'rainforest',
      title: '7. Pattern Recognition (Rainforest)',
      color: '#14b8a6',
      active: true,
      desc: 'RandomForest ensemble classifies market regime from 14 features',
      details: [
        `Model: RandomForest (200 trees, max_depth=12)`,
        `Features: returns, volatility, ATR, RSI, MACD, BB width`,
        `Regimes: bull_trend, bear_trend, ranging, breakout_up, breakout_down, reversal_up, reversal_down`,
        `Ensemble weight: 10% of final signal`,
        `Retrain: every 24 hours`,
      ],
      files: ['Python/rainforest_detector.py'],
      funcs: ['fit()', 'predict_regime()', 'extract_features()'],
    },
    {
      id: 'ensemble',
      title: '8. Signal Ensemble',
      color: '#f97316',
      active: true,
      desc: 'Blends LSTM + PPO + Dreamer + Rainforest into final decision',
      details: [
        `LSTM: regime confidence (direction bias)`,
        `PPO: policy target (position sizing)`,
        `Dreamer: imagined future value`,
        `Rainforest: regime classification (10% weight)`,
        `Final: weighted blend with confidence threshold gating`,
      ],
      files: ['Python/agi_brain.py'],
      funcs: ['_blend_predictions()', '_ensemble_decision()'],
    },
    {
      id: 'execute',
      title: '9. Live Execution',
      color: profitRed,
      active: (status?.account?.open_positions ?? 0) > 0,
      desc: 'MT5 order routing with dynamic SL/TP and trailing stops',
      details: [
        `Mode: ${status?.account?.mode === 'paper' ? 'PAPER (simulated)' : 'LIVE (real money)'}`,
        `Positions open: ${status?.account?.open_positions ?? 0}`,
        `Dynamic SL/TP: ATR-based adaptive stops`,
        `Trailing: activates after profit trigger`,
        `Breakeven: promotes SL to entry + buffer`,
        `Risk: max 1% per trade, 8% max drawdown halt`,
      ],
      files: ['Python/mt5_executor.py', 'Python/order_manager.py'],
      funcs: ['open_position()', 'manage_open_positions()', 'reconcile_exposure()'],
    },
    {
      id: 'registry',
      title: '10. Model Registry & Canary',
      color: '#8b5cf6',
      active: modelCount > 0,
      desc: 'Champion promotion with canary gate validation',
      details: [
        `Models registered: ${modelCount}`,
        `Champion: current live production model`,
        `Canary: shadow mode validation (30+ trades, 45min runtime)`,
        `Promotion: candidate must beat champion on forward windows`,
        `Rollback: automatic if canary exceeds drawdown limits`,
      ],
      files: ['Python/model_registry.py'],
      funcs: ['register_candidate()', 'promote_canary()', 'evaluate_canary()'],
    },
  ]

  return (
    <section style={{ color: textColor }}>
      <div style={cardOuter}>
        <h3 style={sectionHeading}>Chain Gambler Pipeline</h3>
        <div style={{ fontSize: 12, color: mutedColor, marginBottom: 12 }}>
          Full data flow from MT5 ingestion to live trade execution. Click any stage for details.
        </div>

        {stages.map((stage, idx) => (
          <React.Fragment key={stage.id}>
            <div style={stageBox(stage.active, stage.color)}>
              <div style={stageTitle(stage.active, stage.color)}>
                <span style={{
                  width: 8, height: 8, borderRadius: '50%',
                  background: stage.color,
                  boxShadow: stage.active ? `0 0 8px ${stage.color}` : 'none',
                  display: 'inline-block',
                }} />
                {stage.title}
                {stage.active && (
                  <span style={{
                    fontSize: 10,
                    padding: '1px 6px',
                    borderRadius: 3,
                    background: `${stage.color}25`,
                    color: stage.color,
                    fontWeight: 700,
                    marginLeft: 'auto',
                  }}>
                    ACTIVE
                  </span>
                )}
              </div>
              <div style={{ fontSize: 12, color: mutedColor, marginBottom: 8 }}>
                {stage.desc}
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginBottom: 8 }}>
                <div>
                  <div style={{ fontSize: 10, color: mutedColor, marginBottom: 4, textTransform: 'uppercase', letterSpacing: 1 }}>Files</div>
                  <div style={codeBlock}>
                    {stage.files.map(f => (
                      <div key={f} style={{ color: accentBlue }}>{f}</div>
                    ))}
                  </div>
                </div>
                <div>
                  <div style={{ fontSize: 10, color: mutedColor, marginBottom: 4, textTransform: 'uppercase', letterSpacing: 1 }}>Key Functions</div>
                  <div style={codeBlock}>
                    {stage.funcs.map(f => (
                      <div key={f} style={{ color: '#a5b4fc' }}>{f}</div>
                    ))}
                  </div>
                </div>
              </div>

              <div style={{ fontSize: 11, color: mutedColor, lineHeight: 1.6 }}>
                {stage.details.map((d, i) => (
                  <div key={i} style={{ display: 'flex', gap: 6 }}>
                    <span style={{ color: stage.color, flexShrink: 0 }}>•</span>
                    <span>{d}</span>
                  </div>
                ))}
              </div>
            </div>
            {idx < stages.length - 1 && (
              <div style={arrowDown}>▼</div>
            )}
          </React.Fragment>
        ))}
      </div>
    </section>
  )
}

export default PipelinePanel
