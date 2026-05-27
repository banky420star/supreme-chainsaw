import React from 'react'
import { Trade, TradesResponse, TradeSummary, fetchTrades, fetchTradesSummary, fetchEquityCurve, EquityCurveResponse } from '../services/api'
import { EconomicEvent } from '../services/api'
import TruthBadge from './TruthBadge'
import LoadingBar from './LoadingBar'

function EquityChart({ data, height = 220 }: { data: EquityCurveResponse['points']; height?: number }) {
  if (!data || data.length < 2) return <div style={{ color: '#97a9c6', fontSize: 12 }}>No equity data</div>
  const w = 800
  const h = height
  const pad = { top: 10, right: 10, bottom: 30, left: 50 }
  const chartW = w - pad.left - pad.right
  const chartH = h - pad.top - pad.bottom

  const equities = data.map((d) => d.equity)
  const minE = Math.min(...equities)
  const maxE = Math.max(...equities)
  const range = maxE - minE || 1

  const toX = (i: number) => pad.left + (i / (data.length - 1)) * chartW
  const toY = (v: number) => pad.top + chartH - ((v - minE) / range) * chartH

  let path = `M ${toX(0)} ${toY(equities[0])}`
  for (let i = 1; i < data.length; i++) {
    path += ` L ${toX(i)} ${toY(equities[i])}`
  }

  const startEq = equities[0]
  const endEq = equities[equities.length - 1]
  const isUp = endEq >= startEq
  const stroke = isUp ? '#39d98a' : '#ff7b8f'
  const fill = isUp ? 'rgba(57,217,138,0.08)' : 'rgba(255,123,143,0.08)'
  const areaPath = `${path} L ${toX(data.length - 1)} ${pad.top + chartH} L ${toX(0)} ${pad.top + chartH} Z`

  const yTicks = 4
  const yTickVals = Array.from({ length: yTicks + 1 }, (_, i) => minE + (range * i) / yTicks)

  return (
    <svg viewBox={`0 0 ${w} ${h}`} style={{ width: '100%', height: 'auto' }}>
      <defs>
        <linearGradient id="eqGrad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={isUp ? '#39d98a' : '#ff7b8f'} stopOpacity="0.25" />
          <stop offset="100%" stopColor={isUp ? '#39d98a' : '#ff7b8f'} stopOpacity="0" />
        </linearGradient>
      </defs>
      {/* grid */}
      {yTickVals.map((v, i) => (
        <line key={i} x1={pad.left} y1={toY(v)} x2={pad.left + chartW} y2={toY(v)} stroke="rgba(255,255,255,0.04)" strokeDasharray="2,4" />
      ))}
      {/* area */}
      <path d={areaPath} fill="url(#eqGrad)" />
      {/* line */}
      <path d={path} fill="none" stroke={stroke} strokeWidth={2} />
      {/* start / end dots */}
      <circle cx={toX(0)} cy={toY(equities[0])} r={3} fill={stroke} />
      <circle cx={toX(data.length - 1)} cy={toY(equities[equities.length - 1])} r={3} fill={stroke} />
      {/* Y axis labels */}
      {yTickVals.map((v, i) => (
        <text key={`yl-${i}`} x={pad.left - 6} y={toY(v)} textAnchor="end" alignmentBaseline="middle" fill="#97a9c6" fontSize={10} fontFamily="monospace">
          ${v.toFixed(0)}
        </text>
      ))}
      {/* X axis label */}
      <text x={pad.left} y={h - 4} fill="#97a9c6" fontSize={10} fontFamily="monospace">{data[0].ts.slice(0, 10)}</text>
      <text x={pad.left + chartW} y={h - 4} fill="#97a9c6" fontSize={10} fontFamily="monospace" textAnchor="end">{data[data.length - 1].ts.slice(0, 10)}</text>
    </svg>
  )
}

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
}

const panelStyle: React.CSSProperties = {
  background: colors.panelBg,
  border: `1px solid ${colors.border}`,
  borderRadius: 10,
  padding: 16,
}

const thStyle: React.CSSProperties = {
  textAlign: 'left',
  padding: '8px 10px',
  borderBottom: `1px solid ${colors.border}`,
  color: colors.muted,
  fontSize: 11,
  fontWeight: 600,
  textTransform: 'uppercase',
  letterSpacing: 0.5,
}

const tdStyle: React.CSSProperties = {
  padding: '7px 10px',
  fontSize: 13,
  color: colors.text,
  borderBottom: '1px solid rgba(255,255,255,0.03)',
}

function fmtMoney(v: number | undefined | null): string {
  if (v == null || isNaN(v)) return '--'
  return v.toFixed(2)
}

interface Props {
  calendar: import('../services/api').EconomicEvent[]
}

const TradesPanel: React.FC<Props> = ({ calendar }) => {
  const [tradesRes, setTradesRes] = React.useState<TradesResponse | null>(null)
  const [summary, setSummary] = React.useState<TradeSummary | null>(null)
  const [equity, setEquity] = React.useState<EquityCurveResponse | null>(null)
  const [loading, setLoading] = React.useState(true)
  const [offset, setOffset] = React.useState(0)
  const limit = 50

  React.useEffect(() => {
    let cancelled = false
    const load = async () => {
      setLoading(true)
      try {
        const [t, s, e] = await Promise.all([
          fetchTrades({ limit: String(limit), offset: String(offset) }).catch(() => ({ trades: [], total: 0, limit, offset })),
          fetchTradesSummary().catch((): TradeSummary => ({ overall: {} as any, by_symbol: {} })),
          fetchEquityCurve('all').catch((): EquityCurveResponse => ({ points: [], summary: { start_equity: 0, current_equity: 0, peak_equity: 0, max_drawdown_pct: 0, total_trades: 0 } })),
        ])
        if (!cancelled) {
          setTradesRes(t)
          setSummary(s)
          setEquity(e)
        }
      } catch {
        if (!cancelled) {
          setTradesRes(null)
          setSummary(null)
          setEquity(null)
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    const id = setInterval(load, 15_000)
    return () => { cancelled = true; clearInterval(id) }
  }, [offset])

  const trades = tradesRes?.trades ?? []
  const total = tradesRes?.total ?? 0
  const ov = summary?.overall

  return (
    <div style={{ background: colors.bg, color: colors.text, padding: 20 }}>
      <h2 style={{ margin: '0 0 16px', fontSize: 18, color: colors.cyan, fontWeight: 700 }}>
        Trades
      </h2>

      {/* KPIs */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(140px, 1fr))', gap: 12, marginBottom: 16 }}>
        {[
          { label: 'Total', value: ov?.total_trades ?? '--' },
          { label: 'Wins', value: ov?.wins ?? '--' },
          { label: 'Losses', value: ov?.losses ?? '--' },
          { label: 'Win Rate', value: ov?.win_rate != null ? `${(ov.win_rate * 100).toFixed(1)}%` : '--' },
          { label: 'PnL', value: ov?.total_pnl != null ? `$${fmtMoney(ov.total_pnl)}` : '--' },
          { label: 'Profit Factor', value: ov?.profit_factor != null ? String(typeof ov.profit_factor === 'number' ? ov.profit_factor.toFixed(2) : ov.profit_factor) : '--' },
        ].map((kpi) => (
          <div key={kpi.label} style={{ ...panelStyle, textAlign: 'center' }}>
            <div style={{ fontSize: 11, color: colors.muted, textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 4 }}>
              {kpi.label}
            </div>
            <div style={{ fontSize: 18, fontWeight: 700, color: colors.text }}>{kpi.value}</div>
          </div>
        ))}
      </div>

      {/* Equity Curve */}
      {equity && equity.points.length > 0 && (
        <div style={{ ...panelStyle, marginBottom: 16 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
            <h3 style={{ margin: 0, fontSize: 13, color: colors.cyan, fontWeight: 700 }}>Equity Curve</h3>
            <div style={{ display: 'flex', gap: 12, fontSize: 11, fontFamily: 'monospace' }}>
              <span style={{ color: colors.muted }}>Start: <span style={{ color: colors.text }}>${equity.summary.start_equity.toFixed(2)}</span></span>
              <span style={{ color: colors.muted }}>Current: <span style={{ color: equity.summary.current_equity >= equity.summary.start_equity ? colors.green : colors.red }}>${equity.summary.current_equity.toFixed(2)}</span></span>
              <span style={{ color: colors.muted }}>Peak: <span style={{ color: colors.text }}>${equity.summary.peak_equity.toFixed(2)}</span></span>
              <span style={{ color: colors.muted }}>Max DD: <span style={{ color: colors.red }}>{equity.summary.max_drawdown_pct.toFixed(2)}%</span></span>
            </div>
          </div>
          <EquityChart data={equity.points} />
        </div>
      )}

      {/* Calendar banner */}
      {calendar.length > 0 && (
        <div style={{ ...panelStyle, marginBottom: 16 }}>
          <h3 style={{ margin: '0 0 8px', fontSize: 12, color: colors.muted, fontWeight: 600 }}>Economic Calendar (next 7 days)</h3>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
            {calendar.slice(0, 6).map((ev) => (
              <span
                key={ev.event_id}
                style={{
                  fontSize: 10,
                  padding: '3px 8px',
                  borderRadius: 4,
                  background: ev.importance >= 2 ? 'rgba(255,123,143,0.12)' : 'rgba(90,215,255,0.08)',
                  color: ev.importance >= 2 ? colors.red : colors.cyan,
                  border: `1px solid ${ev.importance >= 2 ? 'rgba(255,123,143,0.25)' : 'rgba(90,215,255,0.15)'}`,
                }}
              >
                {ev.currency} {ev.name} ({ev.importance_label})
              </span>
            ))}
          </div>
        </div>
      )}

      {loading && trades.length === 0 && <LoadingBar label="Loading trades..." />}
      {!loading && trades.length === 0 && (
        <div style={{ ...panelStyle, color: colors.muted }}>No trades found.</div>
      )}

      {trades.length > 0 && (
        <>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
              <thead>
                <tr>
                  <th style={thStyle}>Ticket</th>
                  <th style={thStyle}>Symbol</th>
                  <th style={thStyle}>Side</th>
                  <th style={thStyle}>Volume</th>
                  <th style={thStyle}>Open</th>
                  <th style={thStyle}>Close</th>
                  <th style={thStyle}>PnL</th>
                  <th style={thStyle}>Outcome</th>
                  <th style={thStyle}>Model</th>
                </tr>
              </thead>
              <tbody>
                {trades.map((t, idx) => {
                  const profitColor = t.profit > 0 ? colors.green : t.profit < 0 ? colors.red : colors.text
                  const outcomeTone = t.outcome === 'win' ? 'green' : t.outcome === 'loss' ? 'red' : 'yellow'
                  return (
                    <tr key={t.ticket} style={{ background: idx % 2 === 0 ? 'transparent' : 'rgba(90,215,255,0.02)' }}>
                      <td style={{ ...tdStyle, fontFamily: 'monospace', fontSize: 11 }}>{t.ticket}</td>
                      <td style={{ ...tdStyle, color: colors.cyan, fontWeight: 600 }}>{t.symbol}</td>
                      <td style={{ ...tdStyle, color: t.side === 'BUY' ? colors.green : colors.red, fontWeight: 600 }}>{t.side}</td>
                      <td style={tdStyle}>{t.volume}</td>
                      <td style={{ ...tdStyle, fontFamily: 'monospace' }}>{t.open_price.toFixed(5)}</td>
                      <td style={{ ...tdStyle, fontFamily: 'monospace' }}>{t.close_price.toFixed(5)}</td>
                      <td style={{ ...tdStyle, fontFamily: 'monospace', color: profitColor, fontWeight: 700 }}>
                        {t.profit >= 0 ? `+${fmtMoney(t.profit)}` : fmtMoney(t.profit)}
                      </td>
                      <td style={tdStyle}><TruthBadge tone={outcomeTone} label={t.outcome} dot={false} /></td>
                      <td style={{ ...tdStyle, fontSize: 11 }}>{t.model ?? '--'}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginTop: 12 }}>
            <button
              style={{ padding: '6px 12px', borderRadius: 4, border: `1px solid ${colors.border}`, background: colors.panelBg, color: colors.text, cursor: offset > 0 ? 'pointer' : 'not-allowed', opacity: offset > 0 ? 1 : 0.5 }}
              disabled={offset <= 0}
              onClick={() => setOffset((o) => Math.max(0, o - limit))}
            >
              Prev
            </button>
            <span style={{ fontSize: 12, color: colors.muted }}>
              {offset + 1} – {Math.min(offset + trades.length, total)} of {total}
            </span>
            <button
              style={{ padding: '6px 12px', borderRadius: 4, border: `1px solid ${colors.border}`, background: colors.panelBg, color: colors.text, cursor: offset + limit < total ? 'pointer' : 'not-allowed', opacity: offset + limit < total ? 1 : 0.5 }}
              disabled={offset + limit >= total}
              onClick={() => setOffset((o) => o + limit)}
            >
              Next
            </button>
          </div>
        </>
      )}
    </div>
  )
}

export default TradesPanel
