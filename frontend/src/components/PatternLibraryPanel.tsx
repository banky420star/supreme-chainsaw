import React from 'react'
import { PatternRecord } from '../types'
import { LSTMExplanation, RainforestResponse, RainforestSymbolData, fetchRainforest } from '../services/api'
import LoadingBar from './LoadingBar'

interface Props {
  patterns: PatternRecord[]
  status: any
  lstmExpl?: Record<string, LSTMExplanation>
}

const REGIME_COLORS: Record<string, string> = {
  bull_trend:     '#22d68a',
  bear_trend:     '#f5475b',
  ranging:        '#4fd6ff',
  breakout_up:    '#39d98a',
  breakout_down:  '#ff7b8f',
  reversal_up:    '#a855f7',
  reversal_down:  '#f59e0b',
}

const REGIME_LABEL: Record<string, string> = {
  bull_trend:     'BULL TREND',
  bear_trend:     'BEAR TREND',
  ranging:        'RANGING',
  breakout_up:    'BREAKOUT UP',
  breakout_down:  'BREAKOUT DOWN',
  reversal_up:    'REVERSAL UP',
  reversal_down:  'REVERSAL DOWN',
}

function regimeColor(regime: string): string {
  return REGIME_COLORS[regime] ?? '#889'
}

/* ─── Spider/Radar chart (SVG) for feature importances ─── */
function RadarChart({ importances, size = 200 }: { importances: Record<string, number>; size?: number }) {
  const entries = Object.entries(importances)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 8)

  if (entries.length === 0) return <div style={{ color: '#889', fontSize: 12, padding: 8 }}>No feature data</div>

  const cx = size / 2
  const cy = size / 2
  const maxR = size / 2 - 28
  const n = entries.length
  const levels = 4

  const angleOf = (i: number) => (i / n) * 2 * Math.PI - Math.PI / 2

  const gridPolygons = Array.from({ length: levels }, (_, lvl) => {
    const r = (maxR * (lvl + 1)) / levels
    return Array.from({ length: n }, (_, i) => {
      const a = angleOf(i)
      return `${cx + r * Math.cos(a)},${cy + r * Math.sin(a)}`
    }).join(' ')
  })

  const maxVal = Math.max(...entries.map(([, v]) => v), 0.001)
  const dataPoints = entries.map(([, v], i) => {
    const a = angleOf(i)
    const r = (v / maxVal) * maxR
    return `${cx + r * Math.cos(a)},${cy + r * Math.sin(a)}`
  })

  return (
    <svg width={size} height={size} style={{ overflow: 'visible' }}>
      {/* Grid rings */}
      {gridPolygons.map((pts, i) => (
        <polygon key={i} points={pts} fill="none" stroke="rgba(79,214,255,0.12)" strokeWidth={1} />
      ))}
      {/* Spokes */}
      {entries.map((_, i) => {
        const a = angleOf(i)
        return (
          <line key={i}
            x1={cx} y1={cy}
            x2={cx + maxR * Math.cos(a)}
            y2={cy + maxR * Math.sin(a)}
            stroke="rgba(79,214,255,0.15)" strokeWidth={1}
          />
        )
      })}
      {/* Data fill */}
      <polygon points={dataPoints.join(' ')} fill="rgba(79,214,255,0.15)" stroke="#4fd6ff" strokeWidth={1.5} />
      {/* Data dots */}
      {entries.map(([, v], i) => {
        const a = angleOf(i)
        const r = (v / maxVal) * maxR
        return <circle key={i} cx={cx + r * Math.cos(a)} cy={cy + r * Math.sin(a)} r={3} fill="#4fd6ff" />
      })}
      {/* Labels */}
      {entries.map(([key], i) => {
        const a = angleOf(i)
        const labelR = maxR + 18
        const lx = cx + labelR * Math.cos(a)
        const ly = cy + labelR * Math.sin(a)
        return (
          <text key={i} x={lx} y={ly} textAnchor="middle" dominantBaseline="middle"
            fontSize={9} fill="#889" fontFamily="monospace">
            {key.replace(/_/g, ' ')}
          </text>
        )
      })}
    </svg>
  )
}

/* ─── Hero card for a single symbol ─── */
function RainforestSymbolCard({ symbol, data }: { symbol: string; data: RainforestSymbolData }) {
  const color = regimeColor(data.regime)
  const label = REGIME_LABEL[data.regime] ?? data.regime.toUpperCase()
  const confPct = Math.round((data.confidence ?? 0) * 100)

  const topFeatures = Object.entries(data.feature_importances ?? {})
    .sort((a, b) => b[1] - a[1])
    .slice(0, 6)

  const maxFeat = topFeatures[0]?.[1] ?? 1

  return (
    <div style={{
      background: 'rgba(13,23,38,0.92)',
      border: `1px solid rgba(255,255,255,0.08)`,
      borderRadius: 10,
      padding: 16,
      display: 'flex',
      flexDirection: 'column',
      gap: 12,
    }}>
      {/* Hero: symbol + regime */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <div style={{ fontSize: 13, color: '#889', marginBottom: 2 }}>Rainforest says:</div>
          <div style={{ fontFamily: 'monospace', fontWeight: 700, fontSize: 20, color }}>
            {label}
          </div>
          <div style={{ fontSize: 12, color: '#889', marginTop: 2 }}>{symbol}</div>
        </div>
        {/* Confidence ring */}
        <div style={{ textAlign: 'center' }}>
          <svg width={60} height={60}>
            <circle cx={30} cy={30} r={24} fill="none" stroke="rgba(255,255,255,0.08)" strokeWidth={4} />
            <circle cx={30} cy={30} r={24} fill="none" stroke={color} strokeWidth={4}
              strokeDasharray={`${(confPct / 100) * 150.8} 150.8`}
              strokeLinecap="round"
              style={{ transform: 'rotate(-90deg)', transformOrigin: '30px 30px' }}
            />
            <text x={30} y={34} textAnchor="middle" fontSize={13} fontWeight={700} fill={color} fontFamily="monospace">
              {confPct}%
            </text>
          </svg>
          <div style={{ fontSize: 10, color: '#889', marginTop: -2 }}>confidence</div>
        </div>
      </div>

      {/* Radar chart */}
      {Object.keys(data.feature_importances ?? {}).length > 0 && (
        <div style={{ display: 'flex', justifyContent: 'center' }}>
          <RadarChart importances={data.feature_importances} size={180} />
        </div>
      )}

      {/* Feature importance bars */}
      {topFeatures.length > 0 && (
        <div>
          <div style={{ fontSize: 11, color: '#889', marginBottom: 6, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
            Top Features
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
            {topFeatures.map(([feat, val]) => (
              <div key={feat}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, marginBottom: 2 }}>
                  <span style={{ fontFamily: 'monospace', color: '#eef5ff' }}>{feat.replace(/_/g, ' ')}</span>
                  <span style={{ fontFamily: 'monospace', color }}>{(val * 100).toFixed(1)}%</span>
                </div>
                <div style={{ height: 4, background: 'rgba(255,255,255,0.06)', borderRadius: 2, overflow: 'hidden' }}>
                  <div style={{
                    height: '100%',
                    width: `${(val / maxFeat) * 100}%`,
                    background: color,
                    borderRadius: 2,
                    transition: 'width 0.4s ease',
                  }} />
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Top patterns */}
      {data.top_patterns && data.top_patterns.length > 0 && (
        <div>
          <div style={{ fontSize: 11, color: '#889', marginBottom: 6, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
            Top Patterns
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
            {data.top_patterns.slice(0, 4).map((p) => (
              <span key={p.pattern} style={{
                fontSize: 10,
                padding: '3px 8px',
                borderRadius: 12,
                background: `${color}20`,
                border: `1px solid ${color}40`,
                color,
                fontFamily: 'monospace',
              }}>
                {p.pattern.replace(/_/g, ' ')} {Math.round(p.freq * 100)}%
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

/* ─── Regime overview bar (all symbols in one row) ─── */
function RainforestOverviewBar({ data }: { data: Record<string, RainforestSymbolData> }) {
  const symbols = Object.entries(data)
  if (symbols.length === 0) return null

  return (
    <div style={{
      display: 'flex',
      flexWrap: 'wrap',
      gap: 8,
      padding: '10px 12px',
      background: 'rgba(10,17,26,0.8)',
      borderRadius: 8,
      marginBottom: 12,
      border: '1px solid rgba(255,255,255,0.06)',
    }}>
      {symbols.map(([sym, d]) => {
        const color = regimeColor(d.regime)
        const label = REGIME_LABEL[d.regime] ?? d.regime
        const conf = Math.round((d.confidence ?? 0) * 100)
        return (
          <div key={sym} style={{
            display: 'flex', alignItems: 'center', gap: 6,
            padding: '4px 10px',
            borderRadius: 6,
            background: `${color}12`,
            border: `1px solid ${color}30`,
          }}>
            <span style={{ width: 6, height: 6, borderRadius: '50%', background: color, display: 'inline-block' }} />
            <span style={{ fontSize: 12, fontWeight: 700, fontFamily: 'monospace', color: '#eef5ff' }}>{sym}</span>
            <span style={{ fontSize: 11, color }}>{label}</span>
            <span style={{ fontSize: 11, color: '#889' }}>{conf}%</span>
          </div>
        )
      })}
    </div>
  )
}

/* ─── Main component ─── */
const PatternLibraryPanel: React.FC<Props> = ({ patterns, status, lstmExpl: _lstmExpl }) => {
  const [query, setQuery] = React.useState('')
  const [selected, setSelected] = React.useState<PatternRecord | null>(null)
  const [activeTab, setActiveTab] = React.useState<'library' | 'rainforest'>('rainforest')
  const [rfData, setRfData] = React.useState<RainforestResponse | null>(null)
  const [rfLoading, setRfLoading] = React.useState(false)

  // Pull Rainforest data from status if available
  const rfFromStatus: any = status?.rainforest ?? null

  React.useEffect(() => {
    let cancelled = false
    const load = async () => {
      setRfLoading(true)
      try {
        const d = await fetchRainforest()
        if (!cancelled) setRfData(d)
      } catch {
        // ignore — status fallback used
      } finally {
        if (!cancelled) setRfLoading(false)
      }
    }
    load()
    const id = setInterval(load, 30000)
    return () => { cancelled = true; clearInterval(id) }
  }, [])

  const filtered = patterns.filter((p) => {
    const s = (p.pattern_name || '') + ' ' + (p.symbol || '')
    return s.toLowerCase().includes(query.toLowerCase())
  })

  const perSymbol = rfData?.per_symbol ?? {}
  const hasRfData = Object.keys(perSymbol).length > 0

  return (
    <section style={{ padding: 16, marginBottom: 16 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
        <h2 style={{ margin: 0 }}>Pattern Intelligence</h2>
        <div style={{ display: 'flex', gap: 6 }}>
          {(['rainforest', 'library'] as const).map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              style={{
                padding: '5px 14px',
                borderRadius: 6,
                border: `1px solid ${activeTab === tab ? '#4fd6ff' : 'rgba(255,255,255,0.1)'}`,
                background: activeTab === tab ? 'rgba(79,214,255,0.12)' : 'transparent',
                color: activeTab === tab ? '#4fd6ff' : '#889',
                fontSize: 12,
                fontWeight: 600,
                cursor: 'pointer',
                textTransform: 'capitalize',
              }}
            >
              {tab === 'rainforest' ? '🌲 Rainforest' : `📚 Library (${patterns.length})`}
            </button>
          ))}
        </div>
      </div>

      {/* ── Rainforest Tab ── */}
      {activeTab === 'rainforest' && (
        <div>
          {/* Status bar from /api/status */}
          {rfFromStatus && (
            <div style={{
              display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap',
              padding: '8px 12px', marginBottom: 12,
              background: 'rgba(10,17,26,0.6)', borderRadius: 6,
              border: '1px solid rgba(255,255,255,0.06)',
              fontSize: 12, color: '#889',
            }}>
              <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                <span style={{
                  width: 7, height: 7, borderRadius: '50%',
                  background: rfFromStatus.loaded ? '#22d68a' : '#f5475b',
                  display: 'inline-block'
                }} />
                {rfFromStatus.loaded ? 'Rainforest loaded' : 'Not trained yet'}
              </span>
              {rfFromStatus.regime && (
                <span>
                  Regime: <span style={{ color: regimeColor(rfFromStatus.regime), fontWeight: 600 }}>
                    {REGIME_LABEL[rfFromStatus.regime] ?? rfFromStatus.regime}
                  </span>
                </span>
              )}
              {rfFromStatus.confidence != null && (
                <span>Confidence: <span style={{ fontFamily: 'monospace', color: '#4fd6ff' }}>
                  {Math.round(rfFromStatus.confidence * 100)}%
                </span></span>
              )}
              {rfFromStatus.top_feature && (
                <span>Top feature: <span style={{ fontFamily: 'monospace', color: '#eef5ff' }}>{rfFromStatus.top_feature}</span></span>
              )}
              {rfData?.trained_at && (
                <span style={{ marginLeft: 'auto' }}>
                  Trained: {new Date(rfData.trained_at).toLocaleString()}
                </span>
              )}
            </div>
          )}

          {rfLoading && !hasRfData && <LoadingBar label="Loading Rainforest data..." />}

          {!rfLoading && !hasRfData && (
            <div style={{
              textAlign: 'center', padding: 40, color: '#889',
              background: 'rgba(13,23,38,0.6)', borderRadius: 10,
              border: '1px dashed rgba(255,255,255,0.08)',
            }}>
              <div style={{ fontSize: 40, marginBottom: 12 }}>🌲</div>
              <div style={{ fontSize: 14, fontWeight: 600, color: '#eef5ff', marginBottom: 6 }}>
                Rainforest not yet trained
              </div>
              <div style={{ fontSize: 12 }}>
                The RandomForest detector trains automatically when market data is available.
                Start the training cycle to grow the forest.
              </div>
            </div>
          )}

          {hasRfData && (
            <>
              <RainforestOverviewBar data={perSymbol} />
              <div style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))',
                gap: 14,
              }}>
                {Object.entries(perSymbol).map(([sym, d]) => (
                  <RainforestSymbolCard key={sym} symbol={sym} data={d} />
                ))}
              </div>
            </>
          )}
        </div>
      )}

      {/* ── Pattern Library Tab ── */}
      {activeTab === 'library' && (
        <div>
          <input
            type="text"
            placeholder="Search patterns..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            style={{ padding: '8px 10px', borderRadius: 6, border: '1px solid #334', width: '100%', marginBottom: 8, background: '#0a111a', color: '#eef5ff' }}
          />
          <div style={{
            border: '1px solid #334',
            borderRadius: 8,
            padding: 12,
            maxHeight: 400,
            overflowY: 'auto',
            background: '#0a111a'
          }}>
            {filtered.length === 0 ? (
              <div style={{ color: '#888', textAlign: 'center', padding: 20 }}>
                No patterns discovered yet
              </div>
            ) : (
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                  <thead>
                    <tr>
                      <th style={{ textAlign: 'left', padding: 8, borderBottom: '1px solid #444' }}>Symbol</th>
                      <th style={{ textAlign: 'left', padding: 8, borderBottom: '1px solid #444' }}>Pattern</th>
                      <th style={{ textAlign: 'left', padding: 8, borderBottom: '1px solid #444' }}>Regime</th>
                      <th style={{ textAlign: 'left', padding: 8, borderBottom: '1px solid #444' }}>Discovered</th>
                      <th style={{ textAlign: 'left', padding: 8, borderBottom: '1px solid #444' }}>Count</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filtered.map((p, idx) => (
                      <tr key={idx} style={{ background: idx % 2 === 0 ? '#0a111a' : '#080e16', cursor: 'pointer' }} onClick={() => setSelected(p)}>
                        <td style={{ padding: 8 }}>{p.symbol ?? '-'}</td>
                        <td style={{ padding: 8 }}>{p.pattern_name ?? '-'}</td>
                        <td style={{ padding: 8, color: regimeColor(p.regime ?? '') }}>{p.regime ?? '-'}</td>
                        <td style={{ padding: 8 }}>{new Date(p.discovered_at || 0).toLocaleString()}</td>
                        <td style={{ padding: 8 }}>{p.count ?? 0}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>

                {/* Right column: detail of selected pattern */}
                <div style={{ padding: 6, borderLeft: '1px solid #334' }}>
                  <h4 style={{ margin: '0 0 8px', color: '#4fd6ff' }}>Pattern Details</h4>
                  {selected ? (
                    <pre style={{ whiteSpace: 'pre-wrap', maxHeight: 300, overflow: 'auto', fontSize: 12 }}>
                      {JSON.stringify(selected, null, 2)}
                    </pre>
                  ) : (
                    <div style={{ color: '#888' }}>Select a pattern to view details</div>
                  )}
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </section>
  )
}

export default PatternLibraryPanel
