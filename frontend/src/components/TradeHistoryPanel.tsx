import React from 'react'
import { Trade, TradesResponse, TradeSummary, EconomicEvent, fetchTrades, fetchTradesSummary } from '../services/api'

const colors = {
  bg: '#0d1726',
  panelBg: 'rgba(13,23,38,0.92)',
  border: 'rgba(255,255,255,0.08)',
  text: '#eef5ff',
  muted: '#97a9c6',
  green: '#39d98a',
  red: '#ff7b8f',
  cyan: '#5ad7ff',
  amber: '#f3bb4a',
}

const panelStyle: React.CSSProperties = {
  background: colors.panelBg,
  border: `1px solid ${colors.border}`,
  borderRadius: 10,
  padding: 16,
  marginBottom: 16,
}

const kpiStyle: React.CSSProperties = {
  background: colors.bg,
  borderRadius: 8,
  padding: '12px 14px',
  border: `1px solid ${colors.border}`,
  textAlign: 'center',
}

const labelStyle: React.CSSProperties = {
  fontSize: 11,
  fontWeight: 500,
  color: colors.muted,
  textTransform: 'uppercase',
  letterSpacing: '0.06em',
  marginBottom: 4,
}

const selectStyle: React.CSSProperties = {
  padding: '6px 10px',
  borderRadius: 6,
  border: `1px solid ${colors.border}`,
  background: colors.bg,
  color: colors.text,
  fontSize: 13,
  outline: 'none',
  cursor: 'pointer',
  minWidth: 110,
}

const thStyle: React.CSSProperties = {
  textAlign: 'left',
  padding: '8px 10px',
  borderBottom: `1px solid ${colors.border}`,
  fontWeight: 600,
  fontSize: 12,
  color: colors.muted,
  whiteSpace: 'nowrap',
  position: 'sticky',
  top: 0,
  background: '#0a111a',
  zIndex: 1,
}

const tdStyle: React.CSSProperties = {
  padding: '7px 10px',
  fontSize: 13,
  fontFamily: 'monospace',
  whiteSpace: 'nowrap',
}

const btnStyle: React.CSSProperties = {
  padding: '6px 16px',
  borderRadius: 6,
  border: `1px solid ${colors.border}`,
  background: colors.bg,
  color: colors.text,
  fontSize: 13,
  cursor: 'pointer',
  fontWeight: 500,
}

function fmtNum(v: number | undefined | null, decimals = 2): string {
  if (v == null || isNaN(v)) return '--'
  return v.toFixed(decimals)
}

function fmtPnl(v: number): string {
  const s = v.toFixed(2)
  return v >= 0 ? `+${s}` : s
}

function outcomeColor(outcome: string): string {
  if (outcome === 'win') return colors.green
  if (outcome === 'loss') return colors.red
  return colors.amber
}

function pnlColor(v: number): string {
  if (v > 0) return colors.green
  if (v < 0) return colors.red
  return colors.text
}

const PAGE_SIZE = 50

const IMPORTANCE_COLOR: Record<string, string> = {
  high:   colors.red,
  medium: colors.amber,
  low:    colors.muted,
}

const IMPORTANCE_DOT: Record<string, string> = {
  high:   '⬛',  // replaced by colored dot in JSX
  medium: '⬛',
  low:    '⬛',
}

function fmtCalTime(iso: string): string {
  try {
    const d = new Date(iso)
    return d.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
  } catch {
    return iso
  }
}

function CalendarPanel({ events }: { events: EconomicEvent[] }) {
  const [showAll, setShowAll] = React.useState(false)
  const highOnly = events.filter(e => e.importance >= 1)
  const visible = showAll ? events : highOnly.slice(0, 20)

  return (
    <div style={{ ...panelStyle, minWidth: 260, maxWidth: 320, flexShrink: 0 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
        <h3 style={{ margin: 0, fontSize: 14, fontWeight: 700, color: colors.cyan }}>
          Economic Calendar
        </h3>
        <span style={{ fontSize: 11, color: colors.muted }}>MT5 · 7d</span>
      </div>
      <div style={{ display: 'flex', gap: 6, marginBottom: 10 }}>
        <button
          onClick={() => setShowAll(false)}
          style={{ ...btnStyle, fontSize: 11, padding: '3px 10px', background: !showAll ? 'rgba(90,215,255,0.12)' : colors.bg, color: !showAll ? colors.cyan : colors.muted, border: `1px solid ${!showAll ? colors.cyan : colors.border}` }}
        >
          High/Med
        </button>
        <button
          onClick={() => setShowAll(true)}
          style={{ ...btnStyle, fontSize: 11, padding: '3px 10px', background: showAll ? 'rgba(90,215,255,0.12)' : colors.bg, color: showAll ? colors.cyan : colors.muted, border: `1px solid ${showAll ? colors.cyan : colors.border}` }}
        >
          All
        </button>
      </div>
      {visible.length === 0 ? (
        <div style={{ color: colors.muted, fontSize: 12, padding: '12px 0' }}>
          No upcoming events
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8, maxHeight: 520, overflowY: 'auto' }}>
          {visible.map((ev, i) => {
            const dotColor = IMPORTANCE_COLOR[ev.importance_label] ?? colors.muted
            return (
              <div key={ev.event_id || i} style={{
                padding: '8px 10px',
                borderRadius: 6,
                background: 'rgba(10,17,26,0.6)',
                border: `1px solid ${ev.importance === 2 ? 'rgba(255,123,143,0.25)' : colors.border}`,
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 3 }}>
                  <span style={{
                    width: 7, height: 7, borderRadius: '50%', flexShrink: 0,
                    background: dotColor,
                    boxShadow: ev.importance === 2 ? `0 0 6px ${dotColor}` : 'none',
                    display: 'inline-block',
                  }} />
                  <span style={{ fontSize: 12, fontWeight: 600, color: colors.text, lineHeight: 1.3 }}>
                    {ev.name}
                  </span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: colors.muted }}>
                  <span style={{ fontFamily: 'monospace', color: dotColor === colors.muted ? colors.muted : dotColor }}>
                    {ev.currency || ev.country}
                  </span>
                  <span>{fmtCalTime(ev.time)}</span>
                </div>
                {(ev.forecast != null || ev.previous != null) && (
                  <div style={{ fontSize: 10, color: colors.muted, marginTop: 3, fontFamily: 'monospace' }}>
                    {ev.forecast != null && <span>Fcst: {ev.forecast}  </span>}
                    {ev.previous != null && <span>Prev: {ev.previous}</span>}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

interface TradeHistoryPanelProps {
  calendar?: EconomicEvent[]
}

const TradeHistoryPanel: React.FC<TradeHistoryPanelProps> = ({ calendar = [] }) => {
  const [trades, setTrades] = React.useState<Trade[]>([])
  const [total, setTotal] = React.useState(0)
  const [offset, setOffset] = React.useState(0)
  const [summary, setSummary] = React.useState<TradeSummary | null>(null)

  // Filters
  const [filterSymbol, setFilterSymbol] = React.useState('')
  const [filterSide, setFilterSide] = React.useState('')
  const [filterOutcome, setFilterOutcome] = React.useState('')
  const [filterLane, setFilterLane] = React.useState('')

  const buildParams = React.useCallback((extraOffset?: number): Record<string, string> => {
    const p: Record<string, string> = {
      limit: String(PAGE_SIZE),
      offset: String(extraOffset ?? offset),
    }
    if (filterSymbol) p.symbol = filterSymbol
    if (filterSide) p.side = filterSide
    if (filterOutcome) p.outcome = filterOutcome
    if (filterLane) p.bot_lane = filterLane
    return p
  }, [offset, filterSymbol, filterSide, filterOutcome, filterLane])

  const loadData = React.useCallback(async (resetOffset = false) => {
    const currentOffset = resetOffset ? 0 : offset
    const params = buildParams(currentOffset)
    if (resetOffset) {
      params.offset = '0'
      setOffset(0)
    }

    // Build summary params (without limit/offset)
    const summaryParams: Record<string, string> = {}
    if (filterSymbol) summaryParams.symbol = filterSymbol
    if (filterSide) summaryParams.side = filterSide
    if (filterOutcome) summaryParams.outcome = filterOutcome
    if (filterLane) summaryParams.bot_lane = filterLane

    const [tradesRes, summaryRes] = await Promise.all([
      fetchTrades(params).catch((): TradesResponse => ({ trades: [], total: 0, limit: PAGE_SIZE, offset: 0 })),
      fetchTradesSummary(summaryParams).catch((): TradeSummary => ({ overall: {} as any, by_symbol: {} })),
    ])

    setTrades(tradesRes.trades)
    setTotal(tradesRes.total)
    setSummary(summaryRes)
  }, [buildParams, offset, filterSymbol, filterSide, filterOutcome, filterLane])

  // Initial load + auto-refresh every 15s
  React.useEffect(() => {
    loadData(true)
  }, [filterSymbol, filterSide, filterOutcome, filterLane])

  React.useEffect(() => {
    const interval = setInterval(() => loadData(), 15_000)
    return () => clearInterval(interval)
  }, [loadData])

  // Pagination when offset changes (but not on filter change which resets)
  React.useEffect(() => {
    loadData()
  }, [offset])

  const overall = summary?.overall
  const endIndex = Math.min(offset + PAGE_SIZE, total)
  const hasPrev = offset > 0
  const hasNext = offset + PAGE_SIZE < total

  // Collect unique symbols from current trades for filter dropdown
  const uniqueSymbols = React.useMemo(() => {
    const syms = new Set<string>()
    trades.forEach(t => { if (t.symbol) syms.add(t.symbol) })
    return Array.from(syms).sort()
  }, [trades])

  return (
    <div style={{ background: colors.bg, color: colors.text, padding: 20 }}>
      <h2 style={{ margin: '0 0 16px', fontSize: 18, color: colors.cyan, fontWeight: 700 }}>
        Trade History — MT5
      </h2>
      <div style={{ display: 'flex', gap: 16, alignItems: 'flex-start' }}>
      <div style={{ flex: 1, minWidth: 0 }}>

      {/* Filters */}
      <div style={{ ...panelStyle, display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'center' }}>
        <div>
          <div style={labelStyle}>Symbol</div>
          <select
            style={selectStyle}
            value={filterSymbol}
            onChange={e => setFilterSymbol(e.target.value)}
          >
            <option value="">All</option>
            {uniqueSymbols.map(s => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>
        <div>
          <div style={labelStyle}>Side</div>
          <select
            style={selectStyle}
            value={filterSide}
            onChange={e => setFilterSide(e.target.value)}
          >
            <option value="">All</option>
            <option value="BUY">BUY</option>
            <option value="SELL">SELL</option>
          </select>
        </div>
        <div>
          <div style={labelStyle}>Outcome</div>
          <select
            style={selectStyle}
            value={filterOutcome}
            onChange={e => setFilterOutcome(e.target.value)}
          >
            <option value="">All</option>
            <option value="win">Win</option>
            <option value="loss">Loss</option>
            <option value="breakeven">Breakeven</option>
          </select>
        </div>
        <div>
          <div style={labelStyle}>Bot Lane</div>
          <select
            style={selectStyle}
            value={filterLane}
            onChange={e => setFilterLane(e.target.value)}
          >
            <option value="">All</option>
            <option value="standard">Standard</option>
            <option value="hft">HFT</option>
          </select>
        </div>
      </div>

      {/* Summary Stats Bar */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))',
          gap: 12,
          marginBottom: 16,
        }}
      >
        <div style={kpiStyle}>
          <div style={labelStyle}>Total Trades</div>
          <div style={{ fontSize: 20, fontWeight: 700, color: colors.cyan }}>
            {overall?.total_trades ?? '--'}
          </div>
        </div>
        <div style={kpiStyle}>
          <div style={labelStyle}>Win Rate</div>
          <div style={{ fontSize: 20, fontWeight: 700, color: colors.green }}>
            {overall?.win_rate != null ? `${(overall.win_rate * 100).toFixed(1)}%` : '--'}
          </div>
        </div>
        <div style={kpiStyle}>
          <div style={labelStyle}>Total PnL</div>
          <div style={{
            fontSize: 20,
            fontWeight: 700,
            color: overall?.total_pnl != null ? pnlColor(overall.total_pnl) : colors.text,
          }}>
            {overall?.total_pnl != null ? fmtPnl(overall.total_pnl) : '--'}
          </div>
        </div>
        <div style={kpiStyle}>
          <div style={labelStyle}>Profit Factor</div>
          <div style={{ fontSize: 20, fontWeight: 700, color: colors.amber }}>
            {overall?.profit_factor != null ? String(typeof overall.profit_factor === 'number' ? overall.profit_factor.toFixed(2) : overall.profit_factor) : '--'}
          </div>
        </div>
        <div style={kpiStyle}>
          <div style={labelStyle}>Avg Hold (min)</div>
          <div style={{ fontSize: 20, fontWeight: 700, color: colors.text }}>
            {fmtNum(overall?.avg_hold_minutes, 1)}
          </div>
        </div>
      </div>

      {/* Trades Table */}
      <div style={{ ...panelStyle, padding: 0 }}>
        <div style={{ maxHeight: 520, overflowY: 'auto', overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 900 }}>
            <thead>
              <tr>
                {['Close Time', 'Symbol', 'Side', 'Lane', 'Volume', 'Open Price', 'Close Price', 'PnL', 'Hold (min)', 'Outcome'].map(h => (
                  <th key={h} style={thStyle}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {trades.length === 0 ? (
                <tr>
                  <td colSpan={10} style={{ ...tdStyle, textAlign: 'center', color: colors.muted, padding: 32 }}>
                    No trades found
                  </td>
                </tr>
              ) : (
                trades.map((t, idx) => (
                  <tr
                    key={t.ticket}
                    style={{
                      background: idx % 2 === 0 ? 'transparent' : 'rgba(90,215,255,0.02)',
                      transition: 'background 0.1s',
                    }}
                    onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = 'rgba(90,215,255,0.06)' }}
                    onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = idx % 2 === 0 ? 'transparent' : 'rgba(90,215,255,0.02)' }}
                  >
                    <td style={tdStyle}>{t.close_time ?? '--'}</td>
                    <td style={{ ...tdStyle, color: colors.cyan, fontWeight: 600 }}>{t.symbol}</td>
                    <td style={{
                      ...tdStyle,
                      color: t.side === 'BUY' ? colors.green : colors.red,
                      fontWeight: 600,
                    }}>
                      {t.side}
                    </td>
                    <td style={tdStyle}>{t.bot_lane}</td>
                    <td style={tdStyle}>{fmtNum(t.volume, 2)}</td>
                    <td style={tdStyle}>{fmtNum(t.open_price, 5)}</td>
                    <td style={tdStyle}>{fmtNum(t.close_price, 5)}</td>
                    <td style={{ ...tdStyle, color: pnlColor(t.profit), fontWeight: 700 }}>
                      {fmtPnl(t.profit)}
                    </td>
                    <td style={tdStyle}>{t.hold_minutes != null ? fmtNum(t.hold_minutes, 1) : '--'}</td>
                    <td style={tdStyle}>
                      <span style={{
                        padding: '2px 8px',
                        borderRadius: 4,
                        fontSize: 11,
                        fontWeight: 700,
                        textTransform: 'uppercase',
                        background: `${outcomeColor(t.outcome)}20`,
                        color: outcomeColor(t.outcome),
                      }}>
                        {t.outcome}
                      </span>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        {total > 0 && (
          <div style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            padding: '10px 16px',
            borderTop: `1px solid ${colors.border}`,
          }}>
            <span style={{ fontSize: 13, color: colors.muted }}>
              {offset + 1}--{endIndex} of {total}
            </span>
            <div style={{ display: 'flex', gap: 8 }}>
              <button
                style={{ ...btnStyle, opacity: hasPrev ? 1 : 0.4, cursor: hasPrev ? 'pointer' : 'default' }}
                disabled={!hasPrev}
                onClick={() => hasPrev && setOffset(Math.max(0, offset - PAGE_SIZE))}
              >
                Prev
              </button>
              <button
                style={{ ...btnStyle, opacity: hasNext ? 1 : 0.4, cursor: hasNext ? 'pointer' : 'default' }}
                disabled={!hasNext}
                onClick={() => hasNext && setOffset(offset + PAGE_SIZE)}
              >
                Next
              </button>
            </div>
          </div>
        )}
      </div>
      </div>{/* flex left col */}
      <CalendarPanel events={calendar} />
      </div>{/* flex row */}
    </div>
  )
}

export default TradeHistoryPanel
