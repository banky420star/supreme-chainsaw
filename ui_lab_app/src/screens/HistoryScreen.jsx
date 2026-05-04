import React from "react";
import { ArrowRightLeft, BarChart3, Clock, TrendingDown, TrendingUp, Brain, FileText } from "lucide-react";
import { Panel, KpiCard, MetricTile, dollars, money, pct } from "../components/Common";

export default function HistoryScreen({ data }) {
  const tradeHistory = data?.trading?.tradeHistory || [];
  const review = data?.tradeReview || {};
  const learning = data?.learning || {};
  const log = learning?.learning_log || {};
  const health = data?.health || {};
  const backup = data?.backup || {};

  const bySymbol = review.bySymbol || review.by_symbol || log.by_symbol || {};
  const isLiveData = review.totalTrades > 0;
  const dataSourceLabel = isLiveData ? "LIVE" : "BACKTEST";
  const byHour = log.by_hour_utc || [];

  return (
    <div className="stack animate-in">
      {/* Data source indicator */}
      <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "8px 14px", borderRadius: 8, border: `1px solid ${isLiveData ? "rgba(57,217,138,0.2)" : "rgba(243,187,74,0.2)"}`, background: isLiveData ? "rgba(57,217,138,0.04)" : "rgba(243,187,74,0.04)", marginBottom: 8 }}>
        <div style={{ width: 8, height: 8, borderRadius: "50%", background: isLiveData ? "var(--accent-green)" : "var(--accent-amber)", boxShadow: `0 0 6px ${isLiveData ? "var(--accent-green)" : "var(--accent-amber)"}` }} />
        <span style={{ fontFamily: "var(--mono)", fontSize: "0.72rem", textTransform: "uppercase", letterSpacing: "0.1em", color: isLiveData ? "var(--accent-green)" : "var(--accent-amber)", fontWeight: 600 }}>
          {dataSourceLabel} DATA
        </span>
        <span style={{ color: "var(--text-muted)", fontSize: "0.78rem" }}>
          {isLiveData ? `${review.totalTrades} live trades from MT5` : "Simulated backtest data — not from live trading"}
        </span>
      </div>

      {/* System Status Overview */}
      <div className="grid-3" style={{ gap: 16 }}>
        <Panel title="System Health" subtitle="Component status" icon={Brain}>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span style={{ fontSize: "0.85rem" }}>Status</span>
              <span className={`lane-chip ${health?.status === "ok" ? "tone-pass" : ""}`}>
                {health?.status === "ok" ? "ONLINE" : health?.status || "Unknown"}
              </span>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span style={{ fontSize: "0.85rem" }}>Uptime</span>
              <span style={{ fontFamily: "var(--mono)", fontSize: "0.85rem" }}>
                {Math.floor((health?.uptime_seconds || 0) / 3600)}h {Math.floor(((health?.uptime_seconds || 0) % 3600) / 60)}m
              </span>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span style={{ fontSize: "0.85rem" }}>PID</span>
              <span style={{ fontFamily: "var(--mono)", fontSize: "0.85rem" }}>{health?.pid || "-"}</span>
            </div>
          </div>
        </Panel>

        <Panel title="Backup Status" subtitle="Data protection" icon={FileText}>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span style={{ fontSize: "0.85rem" }}>Backups</span>
              <span style={{ fontFamily: "var(--mono)", fontSize: "0.85rem" }}>{backup?.count || 0}</span>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span style={{ fontSize: "0.85rem" }}>Latest</span>
              <span style={{ fontFamily: "var(--mono)", fontSize: "0.75rem" }}>
                {backup?.latest ? new Date(backup.latest).toLocaleDateString() : "None"}
              </span>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span style={{ fontSize: "0.85rem" }}>Retention</span>
              <span style={{ fontFamily: "var(--mono)", fontSize: "0.85rem" }}>{backup?.max_backups || 7} days</span>
            </div>
          </div>        </Panel>

        <Panel title="Trade Log" subtitle="Decision tracking" icon={Clock}>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span style={{ fontSize: "0.85rem" }}>Total Trades</span>
              <span style={{ fontFamily: "var(--mono)", fontSize: "0.85rem" }}>{review.totalTrades || log.trades || 0}</span>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span style={{ fontSize: "0.85rem" }}>Decision Log</span>
              <span className="lane-chip tone-pass" style={{ fontSize: "0.7rem" }}>JSONL</span>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span style={{ fontSize: "0.85rem" }}>Outcomes Tagged</span>
              <span style={{ fontFamily: "var(--mono)", fontSize: "0.85rem" }}>{Object.keys(review.tagDistribution || {}).length} types</span>
            </div>
          </div>        </Panel>
      </div>

      {/* Trade Review KPIs */}
      <Panel title="Live Trade Review" subtitle={`${review.totalTrades || log.trades || 0} live trades analyzed`} icon={BarChart3}>
        <div className="kpi-strip">
          <KpiCard label="Total PnL" value={dollars(review.totalPnl || log.total_pnl || 0)} tone={(review.totalPnl || log.total_pnl || 0) >= 0 ? "pass" : "fail"} />
          <KpiCard label="Win Rate" value={`${(review.winRate || log.win_rate || 0).toFixed(1)}%`} sub={`${review.wins || log.wins || 0}W / ${review.losses || log.losses || 0}L`} tone={(review.winRate || log.win_rate || 0) >= 50 ? "pass" : "warn"} />
          <KpiCard label="Profit Factor" value={String((review.profitFactor || log.profit_factor || 0).toFixed(2))} tone={(review.profitFactor || log.profit_factor || 0) >= 1 ? "pass" : "fail"} />
          <KpiCard label="Avg Win" value={dollars(review.avgWin || log.avg_win || 0)} tone="pass" />
          <KpiCard label="Avg Loss" value={dollars(review.avgLoss || log.avg_loss || 0)} tone="fail" />
          <KpiCard label="Expectancy" value={dollars(review.totalPnl || 0)} sub={`per: ${dollars(log.expectancy || 0)}`} tone={(log.expectancy || 0) >= 0 ? "pass" : "fail"} />
        </div>
      </Panel>

      {/* SL/TP Breakdown */}
      <div className="grid-2" style={{ gap: 16 }}>
        <Panel title="Outcome Tags" subtitle="How trades are classified" icon={TrendingDown}>
          {Object.keys(review.tagDistribution || {}).length === 0 ? (
            <div className="empty-state">No tag data</div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              {Object.entries(review.tagDistribution).sort((a, b) => b[1] - a[1]).map(([tag, count]) => (
                <div key={tag} style={{
                  display: "flex", justifyContent: "space-between", alignItems: "center",
                  padding: "8px 12px", borderRadius: 8, border: "1px solid rgba(255,255,255,0.06)",
                  background: "rgba(255,255,255,0.02)",
                }}>
                  <span style={{ fontSize: "0.85rem" }}>{tag.replace(/_/g, " ")}</span>
                  <span style={{ fontFamily: "var(--mono)", fontSize: "0.82rem", fontWeight: 600 }}>{count}</span>
                </div>
              ))}
            </div>
          )}
        </Panel>

        <Panel title="Per-Symbol" subtitle="Performance by symbol" icon={TrendingUp}>
          {Object.keys(bySymbol).length === 0 ? (
            <div className="empty-state">No symbol data</div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {Object.entries(bySymbol).map(([sym, d]) => (
                <div key={sym} className={`lane-card ${d.pnl >= 0 ? "live" : "watching"}`}>
                  <div className="lane-top">
                    <div>
                      <div className="lane-symbol">{sym}</div>
                      <div style={{ color: "var(--text-muted)", fontSize: "0.78rem" }}>{d.trades} trades · WR: {d.win_rate?.toFixed(1) || d.winRate}%</div>
                    </div>
                    <div style={{ textAlign: "right" }}>
                      <div style={{ color: d.pnl >= 0 ? "var(--accent-green)" : "var(--accent-red)", fontWeight: 700, fontSize: "1.1rem" }}>
                        {dollars(d.pnl)}
                      </div>
                      <div style={{ color: "var(--text-muted)", fontSize: "0.72rem" }}>
                        {(d.profit_factor || d.profitFactor || 0).toFixed(2)} PF
                      </div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </Panel>
      </div>

      {/* Hourly Breakdown */}
      {byHour.length > 0 && (
        <Panel title="Hourly Performance" subtitle="Performance by UTC hour" icon={Clock}>
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            {byHour.sort((a, b) => (a.hour_utc || 0) - (b.hour_utc || 0)).map((h, i) => (
              <div key={i} style={{
                display: "flex", justifyContent: "space-between", alignItems: "center",
                padding: "8px 12px", borderRadius: 6,
                borderLeft: `3px solid ${h.total_pnl >= 0 ? "var(--accent-green)" : "var(--accent-red)"}`,
                background: "rgba(255,255,255,0.02)",
              }}>
                <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                  <span style={{ fontFamily: "var(--mono)", fontSize: "0.85rem", fontWeight: 600, minWidth: 40 }}>
                    {String(h.hour_utc).padStart(2, "0")}:00
                  </span>
                  <span style={{ fontSize: "0.82rem", color: "var(--text-secondary)" }}>{h.trades} trades</span>
                  <span style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>{(h.win_rate || 0).toFixed(1)}% WR</span>
                </div>
                <span style={{ fontWeight: 600, fontSize: "0.92rem", color: h.total_pnl >= 0 ? "var(--accent-green)" : "var(--accent-red)" }}>
                  {dollars(h.total_pnl)}
                </span>
              </div>
            ))}
          </div>
        </Panel>
      )}

      {/* Recent Trades */}
      <Panel title="Recent Trades" subtitle={`${tradeHistory.length} most recent`} icon={ArrowRightLeft}>
        {tradeHistory.length === 0 ? (
          <div className="empty-state">No trades recorded yet</div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {tradeHistory.slice(0, 20).map((trade) => {
              const isWin = trade.pnl >= 0;
              return (
                <div key={trade.id} style={{
                  display: "flex", justifyContent: "space-between", alignItems: "center",
                  padding: "10px 14px", borderRadius: 8,
                  borderLeft: `3px solid ${isWin ? "var(--accent-green)" : "var(--accent-red)"}`,
                  background: "rgba(255,255,255,0.02)",
                }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                    <span className={`lane-chip ${isWin ? "tone-pass" : "tone-fail"}`}>
                      {trade.outcome || trade.type}
                    </span>
                    <strong style={{ fontSize: "0.95rem" }}>{trade.symbol}</strong>
                    <span style={{ color: "var(--text-muted)", fontSize: "0.72rem", fontFamily: "var(--mono)" }}>{trade.timestamp}</span>
                  </div>
                  <div style={{ textAlign: "right" }}>
                    <span style={{ color: isWin ? "var(--accent-green)" : "var(--accent-red)", fontWeight: 700, fontSize: "0.95rem" }}>
                      {dollars(trade.pnl)}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </Panel>

      {/* Worst Symbols from Learning */}
      {log.worst_symbols && log.worst_symbols.length > 0 && (
        <Panel title="Problem Areas" subtitle="Symbols with worst performance" icon={TrendingDown}>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {log.worst_symbols.map((sym, i) => (
              <div key={i} style={{
                padding: 16, borderRadius: 10, border: "1px solid rgba(255,123,143,0.1)",
                background: "rgba(255,123,143,0.03)",
              }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <div>
                    <strong style={{ fontSize: "1rem" }}>{sym.symbol}</strong>
                    <div style={{ color: "var(--text-muted)", fontSize: "0.78rem" }}>
                      {sym.trades} trades · {(sym.win_rate || 0).toFixed(1)}% WR
                    </div>
                  </div>
                  <div style={{ textAlign: "right" }}>
                    <div style={{ color: "var(--accent-red)", fontWeight: 700, fontSize: "1.1rem" }}>{dollars(sym.total_pnl)}</div>
                    <div style={{ color: "var(--text-muted)", fontSize: "0.72rem" }}>PF: {(sym.profit_factor || 0).toFixed(2)}</div>
                  </div>
                </div>
                <div style={{ marginTop: 8, fontSize: "0.78rem", color: "var(--text-secondary)" }}>
                  Max loss streak: {sym.max_loss_streak} · Recent streak: {sym.recent_loss_streak}
                </div>
              </div>
            ))}
          </div>
        </Panel>
      )}
    </div>
  );
}