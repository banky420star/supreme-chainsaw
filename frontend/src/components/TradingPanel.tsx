import React from 'react'
import { StatusPayload } from '../types'
import { LaneStatus, LSTMExplanation, setTradingMode, mt5Login, resetPaperAccount } from '../services/api'

interface Props {
  status: StatusPayload
  lanes?: LaneStatus[]
  lstmExpl?: Record<string, LSTMExplanation>
  onModeChange?: () => void
}

const panelBg = 'rgba(13,23,38,0.92)'
const innerBg = '#0a111a'
const altRowBg = '#080e16'
const borderColor = '#334'
const textColor = '#eef5ff'
const mutedColor = '#889'
const accentBlue = '#4fd6ff'
const profitGreen = '#22d68a'
const profitRed = '#f5475b'

const thStyle: React.CSSProperties = {
  textAlign: 'left',
  padding: 8,
  borderBottom: '1px solid #444',
  fontWeight: 600,
  fontSize: 13,
  color: mutedColor,
  whiteSpace: 'nowrap',
}

const tdStyle: React.CSSProperties = {
  padding: 8,
  fontSize: 13,
  fontFamily: 'monospace',
}

const sectionHeading: React.CSSProperties = {
  fontSize: 16,
  fontWeight: 600,
  marginBottom: 10,
  color: textColor,
}

const cardOuter: React.CSSProperties = {
  background: panelBg,
  border: `1px solid ${borderColor}`,
  borderRadius: 8,
  padding: 16,
  marginBottom: 16,
}

const formatNum = (v: number | undefined | null, decimals = 2): string => {
  if (v == null || isNaN(v)) return '-'
  return v.toFixed(decimals)
}

const blendColors: Record<string, string> = {
  raw_target: '#6e8efb',
  ppo_target: '#a855f7',
  dreamer_target: '#f59e0b',
  agi_bias: '#ec4899',
}

const inputStyle: React.CSSProperties = {
  background: innerBg,
  border: `1px solid ${borderColor}`,
  borderRadius: 4,
  padding: '6px 10px',
  color: textColor,
  fontFamily: 'monospace',
  fontSize: 13,
  outline: 'none',
  width: '100%',
}

const btnStyle: React.CSSProperties = {
  background: 'rgba(79,214,255,0.15)',
  border: '1px solid rgba(79,214,255,0.3)',
  borderRadius: 4,
  padding: '6px 14px',
  color: accentBlue,
  fontSize: 12,
  fontWeight: 600,
  cursor: 'pointer',
}

const dangerBtnStyle: React.CSSProperties = {
  ...btnStyle,
  background: 'rgba(245,71,91,0.15)',
  border: '1px solid rgba(245,71,91,0.3)',
  color: profitRed,
}

const TradingPanel: React.FC<Props> = ({ status, lanes: _propLanes, lstmExpl: _lstmExpl, onModeChange }) => {
  const positions = status?.account?.positions ?? []
  const laneRows = status?.training?.symbol_lane_rows ?? []
  const account = status?.account

  const balance = account?.balance ?? 0
  const equity = account?.equity ?? 0
  const freeMargin = account?.free_margin ?? 0
  const floatingPnl = equity - balance
  const login = account?.login
  const server = account?.server
  const accName = account?.name
  const currency = account?.currency
  const mode = account?.mode ?? 'live'
  const isPaper = mode === 'paper'
  const isReal = !isPaper && server?.toLowerCase().includes('real')

  const [loginForm, setLoginForm] = React.useState({ login: '', password: '', server: '' })
  const [loginMsg, setLoginMsg] = React.useState('')
  const [modeLoading, setModeLoading] = React.useState(false)

  const handleSetMode = async (newMode: 'paper' | 'live') => {
    setModeLoading(true)
    const res = await setTradingMode(newMode)
    setModeLoading(false)
    if (res.success) {
      setLoginMsg(`Switched to ${newMode.toUpperCase()} mode`)
      onModeChange?.()
      setTimeout(() => setLoginMsg(''), 2000)
    } else {
      setLoginMsg(res.error || 'Mode switch failed')
    }
  }

  const handleMT5Login = async () => {
    setLoginMsg('Logging in...')
    const res = await mt5Login(Number(loginForm.login), loginForm.password, loginForm.server)
    if (res.success) {
      setLoginMsg(`Logged in: ${res.name || res.login} @ ${res.server}`)
      onModeChange?.()
      setLoginForm({ login: '', password: '', server: '' })
    } else {
      setLoginMsg(res.error || 'Login failed')
    }
  }

  const handlePaperReset = async () => {
    const res = await resetPaperAccount(100_000)
    if (res.success) {
      setLoginMsg('Paper account reset to $100,000')
      onModeChange?.()
    } else {
      setLoginMsg(res.error || 'Reset failed')
    }
  }

  return (
    <section style={{ color: textColor }}>
      {/* Paper Banner */}
      {isPaper && (
        <div style={{
          ...cardOuter,
          border: '1px solid rgba(245,158,11,0.4)',
          background: 'rgba(245,158,11,0.08)',
        }}>
          <div style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: 10,
            fontSize: 14,
            fontWeight: 700,
            color: '#f59e0b',
            letterSpacing: 2,
            textTransform: 'uppercase',
          }}>
            <span style={{
              width: 10, height: 10, borderRadius: '50%',
              background: '#f59e0b',
              boxShadow: '0 0 10px #f59e0b',
              animation: 'markPulse 2s ease-in-out infinite',
            }} />
            PAPER TRADING — NO REAL MONEY AT RISK
          </div>
        </div>
      )}

      {/* Mode & Account Controls */}
      <div style={cardOuter}>
        <div style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexWrap: 'wrap',
          gap: 12,
          marginBottom: 12,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <span style={{ fontWeight: 700, fontSize: 14 }}>Trading Mode</span>
            <div style={{
              display: 'flex',
              borderRadius: 4,
              overflow: 'hidden',
              border: `1px solid ${borderColor}`,
            }}>
              {(['paper', 'live'] as const).map((m) => (
                <button
                  key={m}
                  disabled={modeLoading}
                  onClick={() => handleSetMode(m)}
                  style={{
                    border: 'none',
                    padding: '4px 12px',
                    fontSize: 11,
                    fontWeight: 700,
                    textTransform: 'uppercase',
                    cursor: modeLoading ? 'not-allowed' : 'pointer',
                    background: mode === m
                      ? (m === 'paper' ? 'rgba(245,158,11,0.25)' : 'rgba(34,214,138,0.25)')
                      : innerBg,
                    color: mode === m
                      ? (m === 'paper' ? '#f59e0b' : profitGreen)
                      : mutedColor,
                  }}
                >
                  {m}
                </button>
              ))}
            </div>
          </div>

          {isPaper && (
            <button onClick={handlePaperReset} style={dangerBtnStyle}>
              Reset $100k
            </button>
          )}
        </div>

        {/* Account Identity */}
        <div style={{
          display: 'flex',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: 8,
          fontSize: 12,
          fontFamily: 'monospace',
          marginBottom: 12,
        }}>
          <span style={{
            padding: '2px 8px',
            borderRadius: 4,
            background: isPaper ? 'rgba(245,158,11,0.15)' : isReal ? 'rgba(245,71,91,0.15)' : 'rgba(34,214,138,0.15)',
            color: isPaper ? '#f59e0b' : isReal ? profitRed : profitGreen,
            fontWeight: 700,
            textTransform: 'uppercase',
            fontSize: 11,
          }}>
            {isPaper ? 'PAPER' : isReal ? 'LIVE' : 'DEMO'}
          </span>
          {login && <span style={{ color: mutedColor }}>Login: <span style={{ color: textColor }}>{login}</span></span>}
          {server && <span style={{ color: mutedColor }}>Server: <span style={{ color: textColor }}>{server}</span></span>}
          {currency && <span style={{ color: mutedColor }}>Currency: <span style={{ color: textColor }}>{currency}</span></span>}
          {accName && <span style={{ color: mutedColor, fontSize: 11 }}>{accName}</span>}
        </div>

        {/* MT5 Login Form */}
        {!isPaper && (
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))',
            gap: 8,
            alignItems: 'end',
          }}>
            <input
              type="number"
              placeholder="Login ID"
              value={loginForm.login}
              onChange={(e) => setLoginForm((f) => ({ ...f, login: e.target.value }))}
              style={inputStyle}
            />
            <input
              type="password"
              placeholder="Password"
              value={loginForm.password}
              onChange={(e) => setLoginForm((f) => ({ ...f, password: e.target.value }))}
              style={inputStyle}
            />
            <input
              type="text"
              placeholder="Server (e.g. Exness-MT5Trial9)"
              value={loginForm.server}
              onChange={(e) => setLoginForm((f) => ({ ...f, server: e.target.value }))}
              style={inputStyle}
            />
            <button onClick={handleMT5Login} style={btnStyle}>Connect MT5</button>
          </div>
        )}

        {loginMsg && (
          <div style={{
            marginTop: 10,
            fontSize: 12,
            color: loginMsg.includes('failed') || loginMsg.includes('error') ? profitRed : profitGreen,
            fontFamily: 'monospace',
          }}>
            {loginMsg}
          </div>
        )}
      </div>

      {/* Account Summary */}
      <div style={cardOuter}>
        <h3 style={sectionHeading}>Account Summary</h3>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 12 }}>
          {[
            { label: 'Balance', value: formatNum(balance) },
            { label: 'Equity', value: formatNum(equity) },
            { label: 'Free Margin', value: formatNum(freeMargin) },
            {
              label: 'Floating P&L',
              value: formatNum(floatingPnl),
              color: floatingPnl > 0 ? profitGreen : floatingPnl < 0 ? profitRed : textColor,
            },
          ].map((item, i) => (
            <div
              key={i}
              style={{
                background: innerBg,
                borderRadius: 6,
                padding: 12,
                textAlign: 'center',
              }}
            >
              <div style={{ fontSize: 11, color: mutedColor, marginBottom: 4 }}>{item.label}</div>
              <div
                style={{
                  fontSize: 18,
                  fontWeight: 700,
                  fontFamily: 'monospace',
                  color: item.color ?? accentBlue,
                }}
              >
                {item.value}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Lane Summary */}
    <div style={cardOuter}>
      <h3 style={sectionHeading}>Lane Summary</h3>
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))',
          gap: 12,
          marginBottom: 12,
        }}
      >
        {[
          { label: 'Actionable', value: status?.training?.lane_summary?.actionable_symbols },
          { label: 'Executed', value: status?.training?.lane_summary?.executed_symbols },
          { label: 'Blocked', value: status?.training?.lane_summary?.blocked_symbols },
          { label: 'Neutral', value: status?.training?.lane_summary?.neutral_symbols },
          { label: 'Open Positions', value: status?.training?.lane_summary?.open_positions },
        ].map((item) => (
          <div
            key={item.label}
            style={{
              background: innerBg,
              borderRadius: 6,
              padding: 10,
              textAlign: 'center',
            }}
          >
            <div style={{ fontSize: 11, color: mutedColor, marginBottom: 4 }}>{item.label}</div>
            <div style={{ fontSize: 16, fontWeight: 700, color: accentBlue }}>
              {item.value ?? '--'}
            </div>
          </div>
        ))}
      </div>
      {laneRows && laneRows.length > 0 && (
        <div style={{ fontSize: 12, color: mutedColor }}>
          Last block:{' '}
          <span style={{ color: profitRed }}>
            {laneRows.find((row) => row.execution?.block_reason)?.execution?.block_reason ?? 'none'}
          </span>
        </div>
      )}
    </div>

    {/* Active Positions */}
    <div style={cardOuter}>
        <h3 style={sectionHeading}>Active Positions</h3>
        {positions.length === 0 ? (
          <div style={{ color: mutedColor, textAlign: 'center', padding: 20 }}>
            No open positions
          </div>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr>
                  {['Symbol', 'Side', 'Volume', 'Entry', 'SL', 'TP', 'Profit'].map((h) => (
                    <th key={h} style={thStyle}>
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {positions.map((pos: any, idx: number) => {
                  const profit = pos.profit ?? 0
                  const profitColor =
                    profit > 0 ? profitGreen : profit < 0 ? profitRed : textColor
                  return (
                    <tr
                      key={pos.ticket ?? idx}
                      style={{ background: idx % 2 === 0 ? innerBg : altRowBg }}
                    >
                      <td style={tdStyle}>{pos.symbol ?? '-'}</td>
                      <td
                        style={{
                          ...tdStyle,
                          color: (pos.type ?? '')
                            .toString()
                            .toLowerCase()
                            .includes('buy')
                            ? profitGreen
                            : profitRed,
                        }}
                      >
                        {pos.type ?? '-'}
                      </td>
                      <td style={tdStyle}>{formatNum(pos.volume, 2)}</td>
                      <td style={tdStyle}>{formatNum(pos.open_price, 5)}</td>
                      <td style={tdStyle}>{formatNum(pos.sl, 5)}</td>
                      <td style={tdStyle}>{formatNum(pos.tp, 5)}</td>
                      <td style={{ ...tdStyle, color: profitColor, fontWeight: 600 }}>
                        {formatNum(profit)}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Per-Symbol Decision Blend */}
      <div style={cardOuter}>
        <h3 style={sectionHeading}>Per-Symbol Decision Blend</h3>
        {laneRows.length === 0 ? (
          <div style={{ color: mutedColor, textAlign: 'center', padding: 20 }}>
            No symbol lane data
          </div>
        ) : (
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fill, minmax(340px, 1fr))',
              gap: 12,
            }}
          >
            {laneRows.map((row: any, idx: number) => {
              const d = row.decision ?? {}
              const confidence = d.confidence ?? 0

              const components = [
                { key: 'raw_target', value: d.raw_target ?? 0 },
                { key: 'ppo_target', value: d.ppo_target ?? 0 },
                { key: 'dreamer_target', value: d.dreamer_target ?? 0 },
                { key: 'agi_bias', value: d.agi_bias ?? 0 },
              ]
              const absSum =
                components.reduce((s, c) => s + Math.abs(c.value), 0) || 1

              return (
                <div
                  key={row.symbol ?? idx}
                  style={{
                    background: innerBg,
                    border: `1px solid ${borderColor}`,
                    borderRadius: 6,
                    padding: 12,
                  }}
                >
                  {/* Card header */}
                  <div
                    style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                      marginBottom: 8,
                    }}
                  >
                    <span style={{ fontWeight: 700, fontSize: 14 }}>
                      {row.symbol ?? '-'}
                    </span>
                    <span
                      style={{
                        fontSize: 11,
                        padding: '2px 8px',
                        borderRadius: 4,
                        background: 'rgba(79,214,255,0.12)',
                        color: accentBlue,
                      }}
                    >
                      {d.regime ?? '-'}
                    </span>
                  </div>

                  {/* Metrics grid */}
                  <div
                    style={{
                      display: 'grid',
                      gridTemplateColumns: '1fr 1fr',
                      gap: 4,
                      fontSize: 12,
                      marginBottom: 8,
                    }}
                  >
                    <div>
                      <span style={{ color: mutedColor }}>Final: </span>
                      <span style={{ fontFamily: 'monospace', fontWeight: 600 }}>
                        {formatNum(d.final_target, 4)}
                      </span>
                    </div>
                    <div>
                      <span style={{ color: mutedColor }}>Confidence: </span>
                      <span
                        style={{
                          fontFamily: 'monospace',
                          fontWeight: 600,
                          color:
                            confidence > 0.7
                              ? profitGreen
                              : confidence > 0.4
                                ? '#f59e0b'
                                : profitRed,
                        }}
                      >
                        {formatNum(confidence, 3)}
                      </span>
                    </div>
                    <div>
                      <span style={{ color: mutedColor }}>Raw: </span>
                      <span style={{ fontFamily: 'monospace' }}>
                        {formatNum(d.raw_target, 4)}
                      </span>
                    </div>
                    <div>
                      <span style={{ color: mutedColor }}>PPO: </span>
                      <span style={{ fontFamily: 'monospace' }}>
                        {formatNum(d.ppo_target, 4)}
                      </span>
                    </div>
                    <div>
                      <span style={{ color: mutedColor }}>Dreamer: </span>
                      <span style={{ fontFamily: 'monospace' }}>
                        {formatNum(d.dreamer_target, 4)}
                      </span>
                    </div>
                    <div>
                      <span style={{ color: mutedColor }}>AGI Bias: </span>
                      <span style={{ fontFamily: 'monospace' }}>
                        {formatNum(d.agi_bias, 4)}
                      </span>
                    </div>
                  </div>

                  {/* Horizontal blend bar */}
                  <div
                    style={{
                      height: 8,
                      borderRadius: 4,
                      overflow: 'hidden',
                      display: 'flex',
                      background: '#1a2234',
                    }}
                  >
                    {components.map((c) => {
                      const pct = (Math.abs(c.value) / absSum) * 100
                      return (
                        <div
                          key={c.key}
                          title={`${c.key}: ${c.value.toFixed(4)}`}
                          style={{
                            width: `${pct}%`,
                            background: blendColors[c.key],
                            transition: 'width 0.3s ease',
                          }}
                        />
                      )
                    })}
                  </div>

                  {/* Blend legend */}
                  <div
                    style={{
                      display: 'flex',
                      gap: 10,
                      marginTop: 6,
                      flexWrap: 'wrap',
                    }}
                  >
                    {components.map((c) => (
                      <div
                        key={c.key}
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: 4,
                          fontSize: 10,
                          color: mutedColor,
                        }}
                      >
                        <span
                          style={{
                            width: 8,
                            height: 8,
                            borderRadius: 2,
                            background: blendColors[c.key],
                            display: 'inline-block',
                          }}
                        />
                        {c.key.replace('_target', '').replace('_', ' ')}
                      </div>
                    ))}
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>
    </section>
  )
}

export default TradingPanel
