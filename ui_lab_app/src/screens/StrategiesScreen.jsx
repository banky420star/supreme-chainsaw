import React, { useEffect, useState } from "react";
import { Brain, BarChart3, Clock, TrendingUp, ArrowUpDown, Lightbulb, Zap, TrendingUpDown } from "lucide-react";
import { Panel, MetricTile, pct, dollars } from "../components/Common";

function useMoney(v) {
  if (v == null) return "$0.00";
  const n = Number(v);
  const sign = n >= 0 ? "+" : "";
  return `${sign}$${Math.abs(n).toFixed(2)}`;
}

function toneForPnl(v) { return v > 0 ? "pass" : v < 0 ? "fail" : ""; }

function ScoreBar({ value, max }) {
  const pctWidth = max > 0 ? Math.min(100, Math.max(0, (Math.abs(value) / max) * 100)) : 0;
  const color = value > 0 ? "var(--accent-green)" : value < 0 ? "var(--accent-red)" : "var(--text-muted)";
  return (
    <div style={{ height: 6, background: "rgba(255,255,255,0.06)", borderRadius: 3, overflow: "hidden", width: "100%" }}>
      <div style={{ height: "100%", width: `${Math.abs(pctWidth)}%`, background: color, borderRadius: 3, transition: "width 0.3s ease" }} />
    </div>
  );
}

function SessionBadge({ session }) {
  const colors = { asian: "#b78aff", london: "#5ad7ff", new_york: "#39d98a", unknown: "#888" };
  const bg = colors[session] || colors.unknown;
  return (
    <span style={{ padding: "3px 8px", background: `${bg}22`, color: bg, borderRadius: 4, fontSize: "0.7rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.05em" }}>
      {(session || "").replace("_", " ")}
    </span>
  );
}

function SideBadge({ side }) {
  const isBuy = side === "BUY";
  return (
    <span style={{ padding: "3px 8px", background: isBuy ? "rgba(57,217,138,0.12)" : "rgba(255,123,143,0.12)", color: isBuy ? "var(--accent-green)" : "var(--accent-red)", borderRadius: 4, fontSize: "0.7rem", fontWeight: 700 }}>
      {side}
    </span>
  );
}

export default function StrategiesScreen({ data }) {
  const [sortKey, setSortKey] = useState("score");
  const strategiesData = data?.strategies || {};
  const strategies = strategiesData.strategies || [];
  const patterns = strategiesData.patterns || [];
  const meta = strategiesData.meta || {};

  const maxScore = strategies.length ? Math.max(...strategies.map((s) => Math.abs(s.score))) : 1;

  const sorted = [...strategies].sort((a, b) => {
    if (sortKey === "score") return b.score - a.score;
    if (sortKey === "pnl") return b.total_pnl - a.total_pnl;
    if (sortKey === "win_rate") return b.win_rate - a.win_rate;
    if (sortKey === "trades") return b.trades - a.trades;
    return 0;
  });

  const symbolPatterns = patterns.filter((p) => p.type === "symbol");
  const sessionPatterns = patterns.filter((p) => p.type === "session");
  const sidePatterns = patterns.filter((p) => p.type === "side");

  return (
    <div className="stack animate-in">
      <Panel title="Strategies Engine" subtitle={`Analyzing ${meta.total_trades || 0} trades over ${meta.analysis_window || "30d"}`} icon={Brain}>
        <div className="grid-3">
          <MetricTile label="Total Strategies" value={String(strategies.length)} />
          <MetricTile label="Profitable" value={String(strategies.filter((s) => s.total_pnl > 0).length)} tone="pass" />
          <MetricTile label="Unprofitable" value={String(strategies.filter((s) => s.total_pnl < 0).length)} tone={strategies.some((s) => s.total_pnl < 0) ? "fail" : ""} />
        </div>
      </Panel>

      {/* Strategy table */}
      <Panel title="Strategy Buckets" subtitle="Symbol x Session x Side -- ranked by score" icon={BarChart3}>
        <div style={{ display: "flex", gap: 8, marginBottom: 16, flexWrap: "wrap" }}>
          {["score", "pnl", "win_rate", "trades"].map((key) => (
            <button key={key} className={`btn btn-sm ${sortKey === key ? "btn-primary" : ""}`}
              onClick={() => setSortKey(key)}>
              {key.replace("_", " ")}
            </button>
          ))}
        </div>

        {sorted.length === 0 ? (
          <div className="empty-state">No trades recorded yet. Strategies will appear once the system executes trades.</div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {sorted.map((s) => (
              <div key={s.id} style={{
                padding: 16, borderRadius: 10,
                border: `1px solid ${s.score > 0 ? "rgba(57,217,138,0.15)" : s.score < 0 ? "rgba(255,123,143,0.15)" : "rgba(255,255,255,0.05)"}`,
                background: "rgba(255,255,255,0.02)",
              }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                    <span style={{ fontWeight: 700, fontSize: "1rem" }}>{s.symbol}</span>
                    <SessionBadge session={s.session} />
                    <SideBadge side={s.side} />
                  </div>
                  <div style={{ textAlign: "right" }}>
                    <div style={{ fontSize: "1.15rem", fontWeight: 700, color: s.total_pnl >= 0 ? "var(--accent-green)" : "var(--accent-red)" }}>
                      {useMoney(s.total_pnl)}
                    </div>
                    <div style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>{s.trades} trades</div>
                  </div>
                </div>
                <div className="metric-grid" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(90px, 1fr))", gap: 8, marginBottom: 10 }}>
                  <MetricTile label="Win Rate" value={pct(s.win_rate)} tone={s.win_rate >= 0.55 ? "pass" : s.win_rate < 0.4 ? "fail" : "warn"} />
                  <MetricTile label="Expectancy" value={useMoney(s.expectancy)} tone={toneForPnl(s.expectancy)} />
                  <MetricTile label="Profit Factor" value={s.profit_factor >= 999 ? "Inf" : s.profit_factor.toFixed(2)} tone={s.profit_factor >= 1.5 ? "pass" : s.profit_factor < 1 ? "fail" : "warn"} />
                  <MetricTile label="Sharpe" value={s.sharpe.toFixed(2)} tone={s.sharpe > 0.5 ? "pass" : s.sharpe < 0 ? "fail" : ""} />
                  <MetricTile label="Confidence" value={pct(s.confidence)} tone={s.confidence >= 0.7 ? "pass" : ""} />
                  <MetricTile label="Score" value={s.score.toFixed(1)} tone={toneForPnl(s.score)} />
                </div>
                <ScoreBar value={s.score} max={maxScore} />
              </div>
            ))}
          </div>
        )}
      </Panel>

      {/* Pattern Recognition */}
      <Panel title="Pattern Recognition" subtitle="Profitability patterns by category" icon={Lightbulb}>
        <div className="grid-3" style={{ gap: 16 }}>
          {[
            { title: "By Symbol", items: symbolPatterns, icon: TrendingUp },
            { title: "By Session", items: sessionPatterns, icon: Clock },
            { title: "By Side", items: sidePatterns, icon: ArrowUpDown },
          ].map(({ title, items }) => (
            <div key={title} style={{ padding: 16, background: "rgba(255,255,255,0.02)", borderRadius: 10, border: "1px solid rgba(255,255,255,0.05)" }}>
              <div className="eyebrow" style={{ marginBottom: 12 }}>{title}</div>
              {items.length === 0 ? (
                <div style={{ color: "var(--text-muted)", fontSize: "0.8rem" }}>No data</div>
              ) : (
                items.map((p) => (
                  <div key={p.name} style={{
                    display: "flex", justifyContent: "space-between", alignItems: "center",
                    padding: "8px 0", borderBottom: "1px solid rgba(255,255,255,0.04)",
                  }}>
                    <div>
                      <div style={{ fontWeight: 600, fontSize: "0.9rem" }}>{p.name}</div>
                      <div style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>{p.trades} trades · {pct(p.win_rate)} WR</div>
                    </div>
                    <div style={{ textAlign: "right" }}>
                      <div style={{ fontWeight: 700, color: p.pnl >= 0 ? "var(--accent-green)" : "var(--accent-red)", fontSize: "0.92rem" }}>
                        {useMoney(p.pnl)}
                      </div>
                      {p.weight !== undefined && (
                        <div style={{ fontSize: "0.65rem", color: "var(--text-muted)" }}>wt: {p.weight.toFixed(2)}</div>
                      )}
                    </div>
                  </div>
                ))
              )}
            </div>
          ))}
        </div>
      </Panel>

      {/* Signal Optimization & Kelly Criterion */}
      <div className="grid-2" style={{ gap: 16 }}>
        <Panel title="Signal Quality Filters" subtitle="Multi-dimensional signal validation" icon={TrendingUpDown}>
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {[
              { name: "Trend Alignment", desc: "Price action aligns with signal direction" },
              { name: "Volatility Regime", desc: "Appropriate for current LSTM regime" },
              { name: "Volume Confirmation", desc: "Sufficient volume for execution" },
              { name: "S/R Distance", desc: "Adequate distance from support/resistance" },
              { name: "Momentum Strength", desc: "ADX and momentum indicators confirm" },
            ].map((filter, i) => (
              <div key={i} style={{ display: "flex", alignItems: "center", gap: 10, padding: "8px 12px", background: "rgba(255,255,255,0.02)", borderRadius: 6 }}>
                <div style={{ width: 6, height: 6, borderRadius: "50%", background: "var(--accent-cyan)" }} />
                <div>
                  <div style={{ fontSize: "0.85rem", fontWeight: 600 }}>{filter.name}</div>
                  <div style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>{filter.desc}</div>
                </div>
              </div>
            ))}
          </div>          <div style={{ marginTop: 12, padding: 12, background: "rgba(90,215,255,0.04)", borderRadius: 8, border: "1px solid rgba(90,215,255,0.1)" }}>
            <div style={{ fontSize: "0.78rem", color: "var(--text-secondary)" }}>
              <strong>Quality Score Threshold:</strong> 0.40 minimum to pass. Blocked signals prevent low-confidence trades.
            </div>
          </div>        </Panel>

        <Panel title="Kelly Criterion Sizing" subtitle="Mathematically optimal position sizing" icon={Zap}>
          <div style={{ padding: 16, background: "rgba(255,255,255,0.02)", borderRadius: 10, marginBottom: 12 }}>
            <div style={{ fontFamily: "var(--mono)", fontSize: "1.1rem", textAlign: "center", marginBottom: 12, color: "var(--accent-cyan)" }}>
              f* = (p·b - q) / b
            </div>
            <div style={{ fontSize: "0.78rem", color: "var(--text-secondary)", lineHeight: 1.5 }}>
              <strong>f*</strong> = Kelly fraction · <strong>p</strong> = win rate · <strong>q</strong> = loss rate (1-p) · <strong>b</strong> = avg win/avg loss ratio
            </div>
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            <div style={{ display: "flex", justifyContent: "space-between", padding: "8px 0", borderBottom: "1px solid rgba(255,255,255,0.04)" }}>
              <span style={{ fontSize: "0.85rem" }}>Full Kelly</span>
              <span style={{ fontFamily: "var(--mono)", fontSize: "0.85rem", color: "var(--accent-green)" }}>100% of f*</span>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", padding: "8px 0", borderBottom: "1px solid rgba(255,255,255,0.04)" }}>
              <span style={{ fontSize: "0.85rem" }}>Half Kelly (default)</span>
              <span style={{ fontFamily: "var(--mono)", fontSize: "0.85rem", color: "var(--accent-amber)" }}>50% of f*</span>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", padding: "8px 0" }}>
              <span style={{ fontSize: "0.85rem" }}>Quarter Kelly</span>
              <span style={{ fontFamily: "var(--mono)", fontSize: "0.85rem", color: "var(--text-muted)" }}>25% of f* (conservative)</span>
            </div>
          </div>

          <div style={{ marginTop: 12, padding: 12, background: "rgba(243,187,74,0.04)", borderRadius: 8, border: "1px solid rgba(243,187,74,0.1)" }}>
            <div style={{ fontSize: "0.78rem", color: "var(--text-secondary)" }}>
              Kelly sizing applied when win rate > 50% and sufficient trade history (30+ trades) for statistical significance.
            </div>
          </div>        </Panel>
      </div>
    </div>
  );
}