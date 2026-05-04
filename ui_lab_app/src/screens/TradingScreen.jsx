import React, { useState } from "react";
import { Activity, ArrowRightLeft, BarChart3, Brain, Calendar, CandlestickChart, GitBranch, Shield, Sparkles, Target, TrendingDown, TrendingUp, Zap, Gauge, TrendingUpDown } from "lucide-react";
import { Panel, KpiCard, MetricTile, LargeSparkline, Button, dollars, money, pct } from "../components/Common";

export default function TradingScreen({ data, selectedSymbol }) {
  const account = data?.trading?.account || {};
  const risk = data?.trading?.risk || {};
  const lanes = data?.trading?.lanes || [];
  const positions = account.positions || [];
  const tradeHistory = data?.trading?.tradeHistory || [];
  const review = data?.tradeReview || {};
  const economicCalendar = data?.economicCalendar || [];
  const equityHistory = data?._history?.equity || [];
  const pnlHistory = data?._history?.pnl || [];
  const reversal = data?.reversal || {};
  const speed = data?.speed || {};

  const openTrades = lanes.filter((l) => l.status === "live");
  const [timeframe, setTimeframe] = useState("1d");

  // Filter equity history by timeframe
  // _history.equity stores up to 300 points polled every 3s (15 min of data)
  // For different timeframes, we slice the array or show all
  const totalPoints = equityHistory.length;
  const filteredEquity = (() => {
    if (timeframe === "all") return equityHistory;
    if (timeframe === "30d") return equityHistory; // same dataset for now
    if (timeframe === "7d") return equityHistory.slice(-200);
    return equityHistory.slice(-100); // 1d: last ~5 min of 3s polls
  })();

  return (
    <div className="stack animate-in">
      {/* Account KPIs */}
      <div className="kpi-strip" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(150px, 1fr))" }}>
        <KpiCard label="Equity" value={dollars(account.equity)} sub={`Float: ${money(account.floatingPnl)}`} tone={account.floatingPnl >= 0 ? "pass" : "fail"} />
        <KpiCard label="Balance" value={dollars(account.balance)} sub={`Free: ${dollars(account.freeMargin)}`} />
        <KpiCard label="Positions" value={String(account.openPositions)} sub={`Today: ${money(account.realizedToday)}`} />
        <KpiCard label="Risk" value={risk.canTrade ? "ACTIVE" : "BLOCKED"} sub={`DD: ${(risk.drawdownPct || 0).toFixed(1)}%`} tone={risk.canTrade ? "pass" : "warn"} />
      </div>

      {/* Equity Curve */}
      <Panel title="Live Equity Curve" subtitle="Real-time account value" icon={Activity}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 16, flexWrap: "wrap", gap: 16 }}>
          <div>
            <div style={{ fontSize: "2.5rem", fontWeight: 700, letterSpacing: "-0.04em", lineHeight: 1 }}>{dollars(account.equity)}</div>
            <div style={{ color: account.floatingPnl >= 0 ? "var(--accent-green)" : "var(--accent-red)", fontFamily: "var(--mono)", fontSize: "0.82rem", marginTop: 8 }}>
              Floating: {money(account.floatingPnl)}
            </div>
          </div>
          <div className="btn-row">
            {["1d", "7d", "30d", "all"].map((tf) => (
              <button key={tf} className={`btn btn-sm ${timeframe === tf ? "btn-primary" : ""}`} onClick={() => setTimeframe(tf)}>
                {tf === "1d" ? "1 Day" : tf === "7d" ? "7 Days" : tf === "30d" ? "30 Days" : "All Time"}
              </button>
            ))}
          </div>
        </div>
        <LargeSparkline data={filteredEquity} height={200} formatValue={(v) => `$${Number(v).toFixed(2)}`} />
      </Panel>

      {/* Open Trades */}
      <Panel title="Open Trades" subtitle={`${account.openPositions} active position${account.openPositions !== 1 ? "s" : ""}`} icon={CandlestickChart}>
        {positions.length === 0 && openTrades.length === 0 ? (
          <div className="empty-state">No active trades. System is standing down.</div>
        ) : (
          <>
            {positions.length > 0 && (
              <div style={{ display: "flex", flexDirection: "column", gap: 10, marginBottom: openTrades.length > 0 ? 16 : 0 }}>
                {positions.map((pos) => (
                  <div className={`lane-card ${pos.profit >= 0 ? "live" : "watching"}`} key={pos.ticket}>
                    <div className="lane-top">
                      <div>
                        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                          <span className="lane-symbol" style={{ fontSize: "1.3rem" }}>{pos.symbol}</span>
                          <span className={`lane-chip ${pos.type === "buy" ? "tone-pass" : "tone-warn"}`}>
                            {pos.type.toUpperCase()}
                          </span>
                          <span style={{ color: "var(--text-muted)", fontFamily: "var(--mono)", fontSize: "0.8rem" }}>
                            {pos.volume} lots
                          </span>
                        </div>
                        <div style={{ color: "var(--text-muted)", fontSize: "0.78rem", marginTop: 4, fontFamily: "var(--mono)" }}>
                          #{pos.ticket} @ {dollars(pos.openPrice)} &rarr; {dollars(pos.currentPrice)}
                        </div>
                        {pos.sl > 0 && pos.tp > 0 && (
                          <div style={{ display: "flex", alignItems: "center", gap: 6, color: "var(--text-muted)", fontSize: "0.72rem", marginTop: 2, fontFamily: "var(--mono)" }}>
                            <Shield size={10} />
                            <span style={{ color: "var(--accent-red)" }}>SL: {dollars(pos.sl)}</span>
                            <span style={{ color: "var(--accent-green)" }}>TP: {dollars(pos.tp)}</span>
                            <span style={{ color: "var(--text-muted)", fontSize: "0.65rem" }}>
                              ({pos.type === "buy"
                                ? `SL -${(pos.openPrice - pos.sl).toFixed(2)} / TP +${(pos.tp - pos.openPrice).toFixed(2)}`
                                : `SL +${(pos.sl - pos.openPrice).toFixed(2)} / TP -${(pos.openPrice - pos.tp).toFixed(2)}`})
                            </span>
                          </div>
                        )}
                      </div>
                      <div style={{ textAlign: "right" }}>
                        <div style={{ color: pos.profit >= 0 ? "var(--accent-green)" : "var(--accent-red)", fontWeight: 700, fontSize: "1.3rem" }}>
                          {money(pos.profit)}
                        </div>
                      </div>
                    </div>
                    {pos.comment && (
                      <div style={{ marginTop: 12, padding: 12, background: "rgba(255,255,255,0.02)", borderRadius: 8, border: "1px solid rgba(255,255,255,0.05)" }}>
                        <div className="eyebrow" style={{ marginBottom: 6 }}><Sparkles size={12} /> Comment</div>
                        <p style={{ color: "rgba(255,255,255,0.85)", fontSize: "0.9rem", lineHeight: 1.5 }}>{pos.comment}</p>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
            {openTrades.length > 0 && positions.length === 0 && (
              <div className="lane-grid">
                {openTrades.map((lane) => (
                  <div className={`lane-card ${lane.pnl >= 0 ? "live" : "watching"}`} key={lane.symbol}>
                    <div className="lane-top">
                      <div>
                        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                          <span className="lane-symbol" style={{ fontSize: "1.3rem" }}>{lane.symbol}</span>
                          <span className={`lane-chip ${lane.side === "buy" ? "tone-pass" : "tone-warn"}`}>
                            {lane.side} {(Math.abs(lane.exposure) * 100).toFixed(0)}%
                          </span>
                        </div>
                        <div style={{ color: "var(--text-muted)", fontSize: "0.78rem", marginTop: 4 }}>Controlled by {lane.champion}</div>
                      </div>
                      <div style={{ textAlign: "right" }}>
                        <div style={{ color: lane.pnl >= 0 ? "var(--accent-green)" : "var(--accent-red)", fontWeight: 700, fontSize: "1.3rem" }}>
                          {money(lane.pnl)}
                        </div>
                      </div>
                    </div>
                    {lane.reason && (
                      <div style={{ marginTop: 12, padding: 12, background: "rgba(255,255,255,0.02)", borderRadius: 8, border: "1px solid rgba(255,255,255,0.05)" }}>
                        <div className="eyebrow" style={{ marginBottom: 6 }}><Brain size={12} /> Decision Reasoning</div>
                        <p style={{ color: "rgba(255,255,255,0.85)", fontSize: "0.85rem", lineHeight: 1.5, fontFamily: "var(--mono)" }}>{lane.reason}</p>
                        {lane.confidence > 0 && (
                          <div style={{ marginTop: 8, display: "flex", gap: 8, flexWrap: "wrap" }}>
                            <span className="lane-chip" style={{ fontSize: "0.65rem" }}>Conf: {(lane.confidence * 100).toFixed(1)}%</span>
                            {lane.is_canary && <span className="lane-chip tone-warn" style={{ fontSize: "0.65rem" }}>CANARY</span>}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </>
        )}
      </Panel>

      {/* Trade History */}
      <Panel title="Trade History" subtitle="Closed trades and post-trade analysis" icon={ArrowRightLeft}>
        {tradeHistory.length === 0 ? (
          <div className="empty-state">No recent trades</div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            {tradeHistory.slice(0, 15).map((trade) => {
              const isWin = trade.pnl >= 0;
              return (
                <div key={trade.id} style={{
                  padding: 16, borderRadius: 12, border: "1px solid rgba(255,255,255,0.05)",
                  background: "rgba(255,255,255,0.02)",
                }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                    <div>
                      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 4 }}>
                        <span className={`lane-chip ${isWin ? "tone-pass" : "tone-fail"}`} style={{ textTransform: "uppercase" }}>
                          {trade.outcome || trade.type}
                        </span>
                        <strong style={{ fontSize: "1.1rem" }}>{trade.symbol}</strong>
                        <span style={{ color: "var(--text-muted)", fontFamily: "var(--mono)", fontSize: "0.75rem" }}>{trade.timestamp}</span>
                      </div>
                      <div style={{ color: "var(--text-muted)", fontFamily: "var(--mono)", fontSize: "0.72rem" }}>
                        Model: {trade.model} · Side: {trade.side || trade.type}
                      </div>
                    </div>
                    <div style={{ textAlign: "right" }}>
                      <div style={{ color: isWin ? "var(--accent-green)" : "var(--accent-red)", fontWeight: 700, fontSize: "1.2rem" }}>
                        {isWin ? "+" : ""}{dollars(trade.pnl)}
                      </div>
                    </div>
                  </div>
                  {trade.reason && (
                    <div style={{ marginTop: 8, padding: "8px 10px", background: "rgba(255,255,255,0.02)", borderRadius: 6, borderLeft: `2px solid ${isWin ? "var(--accent-green)" : "var(--accent-red)"}` }}>
                      <div className="eyebrow" style={{ marginBottom: 4, fontSize: "0.62rem" }}><Sparkles size={11} /> Comment</div>
                      <div style={{ color: "rgba(255,255,255,0.75)", fontSize: "0.82rem", lineHeight: 1.4 }}>{trade.reason}</div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </Panel>

      {/* Trade Review */}
      {review.totalTrades > 0 && (
        <Panel title="Trade Review" subtitle={`${review.totalTrades} trades | Win rate ${review.winRate}% | PF ${review.profitFactor}`} icon={BarChart3}>
          <div className="kpi-strip" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(110px, 1fr))" }}>
            <KpiCard label="Total PnL" value={dollars(review.totalPnl)} sub={`${review.totalTrades} trades`} tone={review.totalPnl >= 0 ? "pass" : "fail"} />
            <KpiCard label="Win Rate" value={`${review.winRate}%`} sub={`${review.wins}W / ${review.losses}L`} tone={review.winRate >= 50 ? "pass" : "warn"} />
            <KpiCard label="Profit Factor" value={String(review.profitFactor)} sub={`Avg W: ${dollars(review.avgWin)}`} tone={review.profitFactor >= 1 ? "pass" : "fail"} />
            <KpiCard label="SL Hits" value={String(review.slHits)} sub={`${review.slRate}%`} />
            <KpiCard label="TP Hits" value={String(review.tpHits)} sub={`${review.tpRate}%`} tone="pass" />
          </div>

          {Object.keys(review.bySymbol || {}).length > 0 && (
            <div style={{ marginTop: 16 }}>
              <div className="eyebrow" style={{ marginBottom: 10 }}><Target size={13} /> Per-Symbol Breakdown</div>
              <div className="grid-2" style={{ gap: 10 }}>
                {Object.entries(review.bySymbol).map(([sym, d]) => (
                  <div className={`lane-card ${d.pnl >= 0 ? "live" : "watching"}`} key={sym}>
                    <div className="lane-top">
                      <div>
                        <div className="lane-symbol">{sym}</div>
                        <div style={{ color: "var(--text-muted)", fontSize: "0.78rem" }}>{d.trades} trades | WR: {d.winRate}%</div>
                      </div>
                      <div style={{ textAlign: "right" }}>
                        <div style={{ color: d.pnl >= 0 ? "var(--accent-green)" : "var(--accent-red)", fontWeight: 700, fontSize: "1.1rem" }}>{dollars(d.pnl)}</div>
                        <div style={{ color: "var(--text-muted)", fontSize: "0.72rem" }}>{d.slHits} SL / {d.tpHits} TP</div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {Object.keys(review.tagDistribution || {}).length > 0 && (
            <div style={{ marginTop: 16 }}>
              <div className="eyebrow" style={{ marginBottom: 10 }}><TrendingDown size={13} /> Outcome Tags</div>
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                {Object.entries(review.tagDistribution).sort((a, b) => b[1] - a[1]).map(([tag, count]) => (
                  <span key={tag} className={`lane-chip ${tag.includes("correct") || tag.includes("tp") ? "tone-pass" : tag.includes("wrong") || tag.includes("tight") ? "tone-warn" : ""}`}>
                    {tag.replace(/_/g, " ")}: {count}
                  </span>
                ))}
              </div>
            </div>
          )}
        </Panel>
      )}

      {/* Advanced Systems Status */}
      <div className="grid-2" style={{ gap: 16 }}>
        <Panel title="Reversal Detection" subtitle="Trend exhaustion monitoring" icon={TrendingUpDown}>
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <Zap size={16} style={{ color: reversal?.enabled ? "var(--accent-green)" : "var(--text-muted)" }} />
                <span style={{ fontWeight: 600 }}>Status</span>
              </div>
              <span className={`lane-chip ${reversal?.enabled ? "tone-pass" : ""}`}>
                {reversal?.enabled ? "ACTIVE" : "STANDBY"}
              </span>
            </div>
            {reversal?.enabled && (
              <>
                <div className="metric-grid" style={{ gridTemplateColumns: "repeat(2, 1fr)" }}>
                  <MetricTile label="Methods" value="5" />
                  <MetricTile label="Auto-Flip" value={reversal?.auto_flip ? "ON" : "OFF"} tone={reversal?.auto_flip ? "pass" : ""} />
                  <MetricTile label="Divergence" value="RSI/MACD" />
                  <MetricTile label="S/R Breaks" value="Enabled" tone="pass" />
                </div>
                <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", padding: "8px 0" }}>
                  Detection: Trend exhaustion · Candlestick patterns · Volume confirmation
                </div>
              </>
            )}
          </div>
        </Panel>

        <Panel title="Execution Simulation" subtitle="Realistic fill modeling" icon={Gauge}>
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <Gauge size={16} style={{ color: speed?.enabled ? "var(--accent-cyan)" : "var(--text-muted)" }} />
                <span style={{ fontWeight: 600 }}>Status</span>
              </div>
              <span className={`lane-chip ${speed?.enabled ? "tone-pass" : ""}`}>
                {speed?.enabled ? "ACTIVE" : "STANDBY"}
              </span>
            </div>
            {speed?.enabled && (
              <>
                <div className="metric-grid" style={{ gridTemplateColumns: "repeat(2, 1fr)" }}>
                  <MetricTile label="Network" value={speed?.network_profile || "good"} />
                  <MetricTile label="Broker" value={speed?.mode === "paper_trading_simulation" ? "Paper" : "Live"} />
                  <MetricTile label="Latency" value={`${speed?.avg_latency_ms || "~50"}ms`} />
                  <MetricTile label="Slippage" value="Simulated" tone="pass" />
                </div>
                <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", padding: "8px 0" }}>
                  Fill probability · Slippage modeling · Network latency simulation
                </div>
              </>
            )}
          </div>
        </Panel>
      </div>

      {/* Economic Calendar */}
      <Panel title="Economic Calendar" subtitle="Upcoming market-moving events" icon={Calendar}>
        {economicCalendar.length === 0 ? (
          <div className="empty-state">No upcoming economic events</div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {economicCalendar.map((event, i) => {
              const importanceColors = { 0: "var(--accent-green)", 1: "var(--accent-amber)", 2: "var(--accent-red)" };
              const dotColor = importanceColors[event.importance] || importanceColors[0];
              const importanceLabels = { 0: "Low", 1: "Medium", 2: "High" };
              const label = event.importance_label || importanceLabels[event.importance] || "Low";
              const formattedTime = event.time
                ? new Date(event.time).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
                : "";

              return (
                <div key={i} style={{
                  display: "flex", alignItems: "center", justifyContent: "space-between",
                  padding: "12px 16px", border: "1px solid rgba(255,255,255,0.05)",
                  borderRadius: 8, background: "rgba(255,255,255,0.02)", gap: 16,
                }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                    <div style={{
                      width: 36, height: 36, borderRadius: 6, flexShrink: 0,
                      display: "flex", alignItems: "center", justifyContent: "center",
                      background: "rgba(255,255,255,0.06)", fontFamily: "var(--mono)",
                      fontSize: "0.7rem", fontWeight: 700, color: "var(--text-muted)",
                    }}>
                      {event.currency || event.country}
                    </div>
                    <div>
                      <div style={{ fontWeight: 600, fontSize: "0.92rem" }}>{event.name}</div>
                      {formattedTime && (
                        <div style={{ color: "var(--text-muted)", fontFamily: "var(--mono)", fontSize: "0.72rem", marginTop: 2 }}>
                          {formattedTime}
                        </div>
                      )}
                    </div>
                  </div>
                  <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                    <span style={{
                      fontFamily: "var(--mono)", fontSize: "0.68rem", textTransform: "uppercase",
                      letterSpacing: "0.06em", color: "var(--text-muted)",
                    }}>
                      {label}
                    </span>
                    <div style={{
                      width: 10, height: 10, borderRadius: "50%", flexShrink: 0,
                      background: dotColor,
                      boxShadow: `0 0 6px ${dotColor}`,
                    }} />
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </Panel>

      {/* Evolutionary Loop */}
      <Panel title="Continuous Evolutionary Loop" subtitle="How Money Printer improves itself" icon={GitBranch}>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))", gap: 24, paddingTop: 8 }}>
          <div>
            <div className="eyebrow" style={{ marginBottom: 10 }}><Brain size={14} /> 1. Context & Pressure</div>
            <p style={{ color: "var(--text-secondary)", fontSize: "0.9rem", lineHeight: 1.55 }}>
              LSTM networks establish deep market context from 150+ engineered features. DreamerV3 then applies simulation pressure to find edge case failures before they manifest as real drawdowns.
            </p>
          </div>
          <div>
            <div className="eyebrow" style={{ marginBottom: 10 }}><Activity size={14} /> 2. Hyper-Tuning & Execution</div>
            <p style={{ color: "var(--text-secondary)", fontSize: "0.9rem", lineHeight: 1.55 }}>
              PPO translates pressured scenarios into adaptive execution policies. The bot dynamically adjusts parameters based on market regimes, tightening stops and adjusting bundle sensitivity.
            </p>
          </div>
          <div>
            <div className="eyebrow" style={{ marginBottom: 10 }}><GitBranch size={14} /> 3. The Canary Pipeline</div>
            <p style={{ color: "var(--text-secondary)", fontSize: "0.9rem", lineHeight: 1.55 }}>
              Models spawn as Canaries and ghost-trade alongside the Champion. If a Canary mathematically outperforms the Champion, authority is seamlessly hot-swapped.
            </p>
          </div>
        </div>
      </Panel>
    </div>
  );
}