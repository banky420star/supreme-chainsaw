/**
 * DashboardPanel Component - IMPROVED VERSION
 *
 * The main dashboard showing system overview, account status, and signal lanes.
 * Includes extensive inline documentation and tooltips to explain concepts.
 *
 * KEY CONCEPTS:
 * - System Truth: Real-time status of all components
 * - Signal Lanes: Per-symbol trading decisions
 * - Champion/Canary: Model evolution system
 * - Risk Status: Safety controls
 */
import React from 'react'
import { StatusPayload } from '../types'
import { Trade, TradeSummary, fetchTrades, fetchTradesSummary, fetchEquityCurve, EquityCurveResponse } from '../services/api'
import EquityChart from './EquityChart'
import LoadingBar from './LoadingBar'
import HelpTooltip from './HelpTooltip'
import TruthBadge from './TruthBadge'

interface Props {
  status: StatusPayload
}

const colors = {
  bg: '#0d1726',
  panelBg: 'rgba(13,23,38,0.92)',
  border: 'rgba(255,255,255,0.08)',
  text: '#eef5ff',
  muted: '#97a9c6',
  green: '#39d98a',
  amber: '#f3bb4a',
  red: '#ff7b8f',
  cyan: '#5ad7ff',
}

const panelStyle: React.CSSProperties = {
  background: colors.panelBg,
  border: `1px solid ${colors.border}`,
  borderRadius: 10,
  padding: 16,
}

const kpiStyle: React.CSSProperties = {
  ...panelStyle,
  display: 'flex',
  flexDirection: 'column',
  alignItems: 'flex-start',
  gap: 4,
}

const labelStyle: React.CSSProperties = {
  fontSize: 11,
  fontWeight: 500,
  color: colors.muted,
  textTransform: 'uppercase',
  letterSpacing: '0.06em',
}

const valueStyle: React.CSSProperties = {
  fontSize: 22,
  fontWeight: 700,
  color: colors.text,
}

function fmtMoney(v: number | undefined | null): string {
  if (v == null || isNaN(v)) return '--'
  return v.toFixed(2)
}

function fmtSignal(v: number | undefined | null): string {
  if (v == null || isNaN(v)) return '--'
  return v.toFixed(4)
}

function statusBadge(
  active: boolean | undefined | null,
  onLabel: string,
  offLabel: string,
): { label: string; color: string } {
  if (active == null) return { label: '--', color: colors.muted }
  return active
    ? { label: onLabel, color: colors.green }
    : { label: offLabel, color: colors.red }
}

function truthColor(value?: string): string {
  if (!value) return colors.muted
  const v = value.toLowerCase()
  const good = new Set([
    'clean', 'audited', 'valid', 'trained', 'validated', 'champion',
    'active', 'running', 'passing', 'unlocked', 'hold',
  ])
  const warn = new Set([
    'stale', 'unaudited', 'leakage-risk', 'validating', 'informational-only',
    'training', 'candidate', 'demo_canary', 'degraded', 'locked', 'failed',
    'failing', 'invalid', 'undertrained', 'rejected', 'idle',
  ])
  if (good.has(v)) return colors.green
  if (warn.has(v)) return colors.amber
  return colors.red
}

// Help text for dashboard elements
const HELP_TEXTS = {
  accountBalance: "Current funds available in your account. This is the cash you can use to open new positions.",
  accountEquity: "Total account value including open positions. Equity = Balance + Floating PnL of open trades.",
  openPositions: "Number of trades currently open. Each symbol can have up to 2 positions (buy + sell allowed).",
  serverStatus: "Whether the API server is running. If stopped, the dashboard cannot communicate with the trading bot.",
  trainingCycle: "Active training status. Shows if LSTM/PPO/Dreamer models are being trained on new data.",
  canaryGate: "The canary model promotion gate. 'Ready' means a trained canary is waiting for live testing.",
  systemTruth: "Real-time health status of all system components. Green = Good, Amber = Warning, Red = Error.",
  championLive: "Number of symbols with a 'champion' model making live trading decisions.",
  tradingReady: "Symbols ready to trade but waiting for confidence threshold.",
  blockedSymbols: "Symbols temporarily blocked by risk controls or manual intervention.",
  signalLanes: "Per-symbol trading signals from the Hybrid Brain. Shows what the AI is thinking for each symbol.",
  regime: "Market condition detected by the AI: HOLD (no trade), BUY (long), SELL (short).",
  confidence: "AI certainty level (0-1). Higher = more confident. Trades only execute above threshold (~0.6).",
  finalTarget: "The blended signal from all three AI brains (-1 to +1). Closer to ±1 = stronger signal.",
  lstmState: "The LSTM model's current prediction state for this symbol.",
}

const DashboardPanelImproved: React.FC<Props> = ({ status }) => {
  const [tradeSummary, setTradeSummary] = React.useState<TradeSummary | null>(null)
  const [recentTrades, setRecentTrades] = React.useState<Trade[]>([])
  const [equityCurve, setEquityCurve] = React.useState<EquityCurveResponse | null>(null)
  const [equityWindow, setEquityWindow] = React.useState<'30d' | '90d' | 'all'>('all')
  const [loading, setLoading] = React.useState(true)

  React.useEffect(() => {
    const loadTradeData = async () => {
      setLoading(true)
      const [summaryRes, tradesRes] = await Promise.all([
        fetchTradesSummary().catch((): TradeSummary => ({ overall: {} as any, by_symbol: {} })),
        fetchTrades({ limit: '5' }).catch(() => ({ trades: [] as Trade[], total: 0, limit: 5, offset: 0 })),
      ])
      setTradeSummary(summaryRes)
      setRecentTrades(tradesRes.trades)
      setLoading(false)
    }
    loadTradeData()
    const interval = setInterval(loadTradeData, 15_000)
    return () => clearInterval(interval)
  }, [])

  React.useEffect(() => {
    fetchEquityCurve(equityWindow).then(setEquityCurve).catch(() => {})
  }, [equityWindow])

  const account = status.account
  const server = status.server
  const training = status.training
  const canary = status.canary_gate
  const lanes = training?.symbol_lane_rows ?? []
  const incidents = (status.incidents ?? []).slice(0, 8)
  const tradeOverall = tradeSummary?.overall

  const serverBadge = statusBadge(server?.running, 'running', 'stopped')
  const trainingBadge = statusBadge(training?.cycle_running, 'active', 'idle')
  const canaryBadge = statusBadge(canary?.ready, 'ready', 'hold')
  const pipelineSummary = training?.pipeline_summary
  const laneSummary = training?.lane_summary
  const activeStageLabel = training?.visual?.active_label ?? 'Idle'

  return (
    <div style={{ background: colors.bg, color: colors.text, padding: 20 }}>
      {loading && <LoadingBar label="Loading dashboard..." />}

      {/* KPI Grid */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 14, marginBottom: 24 }}>
        {/* Row 1 */}
        <div style={kpiStyle}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={labelStyle}>Account Balance</span>
            <HelpTooltip text={HELP_TEXTS.accountBalance} />
          </div>
          <span style={valueStyle}>${fmtMoney(account?.balance)}</span>
        </div>
        <div style={kpiStyle}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={labelStyle}>Account Equity</span>
            <HelpTooltip text={HELP_TEXTS.accountEquity} />
          </div>
          <span style={valueStyle}>${fmtMoney(account?.equity)}</span>
        </div>
        <div style={kpiStyle}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={labelStyle}>Open Positions</span>
            <HelpTooltip text={HELP_TEXTS.openPositions} />
          </div>
          <span style={valueStyle}>{account?.open_positions ?? '--'}</span>
        </div>

        {/* Row 2 */}
        <div style={kpiStyle}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={labelStyle}>Server Status</span>
            <HelpTooltip text={HELP_TEXTS.serverStatus} />
          </div>
          <span style={{ ...valueStyle, color: serverBadge.color }}>{serverBadge.label}</span>
        </div>
        <div style={kpiStyle}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={labelStyle}>Training Cycle</span>
            <HelpTooltip text={HELP_TEXTS.trainingCycle} />
          </div>
          <span style={{ ...valueStyle, color: trainingBadge.color }}>{trainingBadge.label}</span>
        </div>
        <div style={kpiStyle}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={labelStyle}>Canary Gate</span>
            <HelpTooltip text={HELP_TEXTS.canaryGate} />
          </div>
          <span style={{ ...valueStyle, color: canaryBadge.color }}>{canaryBadge.label}</span>
        </div>
      </div>

      {/* System Truth */}
      <div style={{ ...panelStyle, marginBottom: 24 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 14 }}>
          <h3 style={{ margin: 0, fontSize: 14, color: colors.cyan, fontWeight: 600 }}>System Truth</h3>
          <HelpTooltip
            title="System Health Dashboard"
            text={HELP_TEXTS.systemTruth}
          />
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))', gap: 10 }}>
          {[
            { label: 'Mode', value: status.system?.system_mode ?? 'unknown' },
            { label: 'Data', value: status.data?.status ?? 'unknown' },
            { label: 'Features', value: 'unaudited' },
            { label: 'Labels', value: 'unknown' },
            { label: 'LSTM', value: status.models?.lstm_status ?? 'unknown' },
            { label: 'Rainforest', value: status.models?.rainforest_status ?? 'unknown' },
            { label: 'Dreamer', value: status.models?.dreamer_status ?? 'unknown' },
            { label: 'PPO', value: status.models?.ppo_status ?? 'unknown' },
            { label: 'Ensemble', value: status.models?.ensemble_status ?? 'unknown' },
            { label: 'Paper', value: status.system?.system_mode === 'paper_sim' ? 'running' : 'idle' },
            { label: 'Demo-live', value: status.system?.system_mode === 'demo_live' ? 'active' : 'idle' },
            { label: 'Real-live', value: status.system?.real_money_locked ? 'locked' : 'unlocked' },
            { label: 'Tests', value: status.tests?.status ?? 'unknown' },
            { label: 'Telemetry', value: status.account?.telemetry_valid ? 'valid' : 'invalid' },
          ].map((item) => (
            <div
              key={item.label}
              style={{
                ...panelStyle,
                padding: '8px 10px',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
              }}
            >
              <span style={{ fontSize: 11, color: colors.muted, textTransform: 'uppercase', letterSpacing: 0.5 }}>
                {item.label}
              </span>
              <span
                style={{
                  fontSize: 12,
                  fontWeight: 700,
                  color: truthColor(item.value),
                  textTransform: 'uppercase',
                }}
              >
                {item.value}
              </span>
            </div>
          ))}
        </div>
        {/* Conditional truth messages */}
        <div style={{ marginTop: 12, display: 'flex', flexWrap: 'wrap', gap: 8 }}>
          {(!status.data?.status || status.data?.status === 'unknown') && (
            <span style={{ fontSize: 11, color: colors.amber }}>No verified data yet</span>
          )}
          {(!training?.cycle_running && !training?.lstm_running && !training?.drl_running && !training?.dreamer_running) && (
            <span style={{ fontSize: 11, color: colors.amber }}>Training not running (models already trained)</span>
          )}
          {status.models?.dreamer_status === 'stub_disabled' && (
            <span style={{ fontSize: 11, color: colors.amber }}>Dreamer disabled/stub (using LSTM + PPO only)</span>
          )}
          {(status.models?.ppo_status === 'undertrained' || status.models?.lstm_status === 'disabled') && (
            <span style={{ fontSize: 11, color: colors.amber }}>Model not validated (using fresh weights)</span>
          )}
          {status.system?.system_mode === 'demo_live' && tradeOverall?.total_trades == null && (
            <span style={{ fontSize: 11, color: colors.amber }}>Waiting for demo trades (normal on startup)</span>
          )}
          {status.tests?.status === 'failing' && (
            <span style={{ fontSize: 11, color: colors.red }}>Tests failing - check logs</span>
          )}
          {status.account?.telemetry_valid === false && (
            <span style={{ fontSize: 11, color: colors.red }}>Telemetry invalid - account data may be stale</span>
          )}
          {status.system?.real_money_locked && (
            <span style={{ fontSize: 11, color: colors.red }}>Real money locked (safety feature)</span>
          )}
        </div>
      </div>

      {/* Equity Curve */}
      <div style={{ ...panelStyle, marginBottom: 24 }}>
        <EquityChart
          data={equityCurve?.points ?? []}
          height={200}
          window={equityWindow}
          onWindowChange={setEquityWindow}
        />
      </div>

      <div style={{ ...panelStyle, marginBottom: 24 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
          <h3 style={{ margin: 0, fontSize: 14, color: colors.cyan, fontWeight: 600 }}>Pipeline Snapshot</h3>
          <HelpTooltip text="Overview of the training pipeline and symbol readiness." />
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 12 }}>
          <div style={{ ...panelStyle, padding: '10px 12px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <div style={labelStyle}>Active training symbols</div>
              <HelpTooltip text="Symbols currently being trained on new data." />
            </div>
            <div style={valueStyle}>{pipelineSummary?.training_active_symbols ?? '--'}</div>
          </div>
          <div style={{ ...panelStyle, padding: '10px 12px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <div style={labelStyle}>Champion live</div>
              <HelpTooltip text={HELP_TEXTS.championLive} />
            </div>
            <div style={valueStyle}>{pipelineSummary?.champion_live_symbols ?? '--'}</div>
          </div>
          <div style={{ ...panelStyle, padding: '10px 12px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <div style={labelStyle}>Trading ready symbols</div>
              <HelpTooltip text={HELP_TEXTS.tradingReady} />
            </div>
            <div style={valueStyle}>{pipelineSummary?.trading_ready_symbols ?? '--'}</div>
          </div>
          <div style={{ ...panelStyle, padding: '10px 12px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <div style={labelStyle}>Blocked symbols</div>
              <HelpTooltip text={HELP_TEXTS.blockedSymbols} />
            </div>
            <div style={valueStyle}>{laneSummary?.blocked_symbols ?? '--'}</div>
          </div>
        </div>
        <div style={{ marginTop: 12, fontSize: 12, color: colors.muted }}>
          Active stage: <span style={{ color: colors.cyan }}>{activeStageLabel}</span>
        </div>
      </div>

      {/* Signal Lanes */}
      <div style={{ ...panelStyle, marginBottom: 24 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 14 }}>
          <h3 style={{ margin: 0, fontSize: 15, fontWeight: 600, color: colors.cyan }}>
            Signal Lanes
          </h3>
          <HelpTooltip
            title="Per-Symbol Trading Signals"
            text={HELP_TEXTS.signalLanes}
          />
        </div>
        {lanes.length === 0 ? (
          <div style={{ color: colors.muted, fontSize: 13 }}>
            No symbol lanes available.
          </div>
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 12 }}>
            {lanes.map((lane: any, idx: number) => {
              const decision = lane.decision ?? {}
              const pipeline = lane.pipeline ?? {}
              const lstmState = pipeline.lstm?.state ?? '--'
              return (
                <div
                  key={lane.symbol ?? idx}
                  style={{
                    ...panelStyle,
                    background: 'rgba(20,32,52,0.85)',
                    padding: 14,
                  }}
                >
                  <div style={{ fontSize: 14, fontWeight: 700, color: colors.cyan, marginBottom: 8 }}>
                    {lane.symbol ?? 'UNKNOWN'}
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 13 }}>
                    <div>
                      <span style={{ color: colors.muted }}>Regime: </span>
                      <span style={{ color: truthColor(decision.regime) }}>{decision.regime ?? '--'}</span>
                      <HelpTooltip text={HELP_TEXTS.regime} />
                    </div>
                    <div>
                      <span style={{ color: colors.muted }}>Final Target: </span>
                      <span style={{ color: colors.amber }}>{fmtSignal(decision.final_target)}</span>
                      <HelpTooltip text={HELP_TEXTS.finalTarget} />
                    </div>
                    <div>
                      <span style={{ color: colors.muted }}>PPO Target: </span>
                      <span style={{ color: colors.text }}>{fmtSignal(decision.ppo_target)}</span>
                    </div>
                    <div>
                      <span style={{ color: colors.muted }}>Dreamer Target: </span>
                      <span style={{ color: colors.text }}>{fmtSignal(decision.dreamer_target)}</span>
                    </div>
                    <div>
                      <span style={{ color: colors.muted }}>Confidence: </span>
                      <span style={{ color: colors.green }}>{fmtSignal(decision.confidence)}</span>
                      <HelpTooltip text={HELP_TEXTS.confidence} />
                    </div>
                    <div>
                      <span style={{ color: colors.muted }}>LSTM State: </span>
                      <span style={{ color: colors.text }}>{lstmState}</span>
                      <HelpTooltip text={HELP_TEXTS.lstmState} />
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>

      {/* Recent Incidents */}
      <div style={panelStyle}>
        <h3 style={{ margin: '0 0 14px 0', fontSize: 15, fontWeight: 600, color: colors.amber }}>
          Recent Incidents
        </h3>
        {incidents.length === 0 ? (
          <div style={{ color: colors.muted, fontSize: 13 }}>No recent incidents.</div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {incidents.map((inc: any, idx: number) => {
              const sevColor =
                inc.severity === 'critical'
                  ? colors.red
                  : inc.severity === 'warning'
                    ? colors.amber
                    : colors.muted
              return (
                <div
                  key={idx}
                  style={{
                    display: 'flex',
                    alignItems: 'flex-start',
                    gap: 10,
                    padding: '8px 10px',
                    background: 'rgba(20,32,52,0.6)',
                    borderRadius: 6,
                    borderLeft: `3px solid ${sevColor}`,
                    fontSize: 13,
                  }}
                >
                  <div style={{ flex: 1 }}>
                    <div style={{ fontWeight: 600, color: colors.text }}>{inc.event ?? '--'}</div>
                    <div style={{ color: colors.muted, marginTop: 2 }}>{inc.summary ?? ''}</div>
                  </div>
                  <div style={{ fontSize: 11, color: colors.muted, whiteSpace: 'nowrap', flexShrink: 0 }}>
                    {inc.ts ?? ''}
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>

      {/* Trade Performance */}
      <div style={{ ...panelStyle, marginTop: 24 }}>
        <h3 style={{ margin: '0 0 12px 0', fontSize: 14, color: colors.cyan, fontWeight: 600 }}>
          Trade Performance
        </h3>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: 12 }}>
          <div style={{ ...panelStyle, padding: '10px 12px' }}>
            <div style={labelStyle}>Total Trades</div>
            <div style={valueStyle}>{tradeOverall?.total_trades ?? '--'}</div>
          </div>
          <div style={{ ...panelStyle, padding: '10px 12px' }}>
            <div style={labelStyle}>Win Rate</div>
            <div style={{ ...valueStyle, color: colors.green }}>
              {tradeOverall?.win_rate != null ? `${(tradeOverall.win_rate * 100).toFixed(1)}%` : '--'}
            </div>
          </div>
          <div style={{ ...panelStyle, padding: '10px 12px' }}>
            <div style={labelStyle}>Total PnL</div>
            <div style={{
              ...valueStyle,
              color: tradeOverall?.total_pnl != null
                ? (tradeOverall.total_pnl > 0 ? colors.green : tradeOverall.total_pnl < 0 ? colors.red : colors.text)
                : colors.text,
            }}>
              {tradeOverall?.total_pnl != null ? fmtMoney(tradeOverall.total_pnl) : '--'}
            </div>
          </div>
          <div style={{ ...panelStyle, padding: '10px 12px' }}>
            <div style={labelStyle}>Profit Factor</div>
            <div style={{ ...valueStyle, color: colors.amber }}>
              {tradeOverall?.profit_factor != null
                ? String(typeof tradeOverall.profit_factor === 'number' ? tradeOverall.profit_factor.toFixed(2) : tradeOverall.profit_factor)
                : '--'}
            </div>
          </div>
        </div>
      </div>

      {/* Recent Trades */}
      <div style={panelStyle}>
        <h3 style={{ margin: '0 0 12px 0', fontSize: 14, color: colors.cyan, fontWeight: 600 }}>
          Recent Trades
        </h3>
        {recentTrades.length === 0 ? (
          <div style={{ color: colors.muted, fontSize: 13 }}>No recent trades.</div>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
              <thead>
                <tr>
                  {['Time', 'Symbol', 'Side', 'PnL', 'Outcome'].map(h => (
                    <th
                      key={h}
                      style={{
                        textAlign: 'left',
                        padding: '6px 10px',
                        borderBottom: `1px solid ${colors.border}`,
                        color: colors.muted,
                        fontWeight: 600,
                        fontSize: 11,
                        whiteSpace: 'nowrap',
                      }}
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {recentTrades.map((t, idx) => {
                  const profitColor = t.profit > 0 ? colors.green : t.profit < 0 ? colors.red : colors.text
                  const outcomeCol = t.outcome === 'win' ? colors.green : t.outcome === 'loss' ? colors.red : colors.amber
                  return (
                    <tr key={t.ticket} style={{ background: idx % 2 === 0 ? 'transparent' : 'rgba(90,215,255,0.02)' }}>
                      <td style={{ padding: '6px 10px', fontFamily: 'monospace', whiteSpace: 'nowrap' }}>{t.close_time ?? '--'}</td>
                      <td style={{ padding: '6px 10px', color: colors.cyan, fontWeight: 600 }}>{t.symbol}</td>
                      <td style={{ padding: '6px 10px', color: t.side === 'BUY' ? colors.green : colors.red, fontWeight: 600 }}>{t.side}</td>
                      <td style={{ padding: '6px 10px', fontFamily: 'monospace', color: profitColor, fontWeight: 700 }}>
                        {t.profit >= 0 ? `+${fmtMoney(t.profit)}` : fmtMoney(t.profit)}
                      </td>
                      <td style={{ padding: '6px 10px' }}>
                        <span style={{
                          padding: '2px 8px',
                          borderRadius: 4,
                          fontSize: 11,
                          fontWeight: 700,
                          textTransform: 'uppercase',
                          background: `${outcomeCol}20`,
                          color: outcomeCol,
                        }}>
                          {t.outcome}
                        </span>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}

export default DashboardPanelImproved
