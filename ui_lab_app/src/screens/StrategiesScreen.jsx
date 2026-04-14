import React, { useEffect, useState } from "react";
import { Brain, Lightbulb, TrendingUp, BarChart3, Clock, ArrowUpDown } from "lucide-react";
import { Panel, MetricTile, pct } from "../components/common";

function useMoney(v) {
  if (v == null) return "$0.00";
  const n = Number(v);
  const sign = n >= 0 ? "+" : "";
  return `${sign}$${Math.abs(n).toFixed(2)}`;
}

function toneForPnl(v) {
  return v > 0 ? "pass" : v < 0 ? "fail" : "info";
}

function ScoreBar({ value, max }) {
  const pctWidth = max > 0 ? Math.min(100, Math.max(0, (value / max) * 100)) : 0;
  const color = value > 0 ? "var(--green)" : value < 0 ? "var(--red)" : "var(--muted)";
  return (
    <div style={{ height: 6, background: "rgba(255,255,255,0.06)", borderRadius: 3, overflow: "hidden", width: "100%" }}>
      <div style={{ height: "100%", width: `${Math.abs(pctWidth)}%`, background: color, borderRadius: 3, transition: "width 0.3s ease" }} />
    </div>
  );
}

function SessionBadge({ session }) {
  const colors = { asian: "#a78bfa", london: "#62d6ff", new_york: "#34d399", unknown: "#888" };
  const bg = colors[session] || colors.unknown;
  return (
    <span style={{ padding: "3px 8px", background: `${bg}22`, color: bg, borderRadius: 4, fontSize: "0.7rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.05em" }}>
      {session.replace("_", " ")}
    </span>
  );
}

function SideBadge({ side }) {
  const isBuy = side === "BUY";
  return (
    <span style={{ padding: "3px 8px", background: isBuy ? "rgba(52,211,153,0.12)" : "rgba(255,107,107,0.12)", color: isBuy ? "var(--green)" : "var(--red)", borderRadius: 4, fontSize: "0.7rem", fontWeight: 700 }}>
      {side}
    </span>
  );
}

export default function StrategiesScreen() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [sortKey, setSortKey] = useState("score");

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const res = await fetch("/api/strategies", { cache: "no-store" });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const json = await res.json();
        if (!cancelled) {
          setData(json);
          setLoading(false);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err.message);
          setLoading(false);
        }
      }
    }
    load();
    const interval = setInterval(load, 30000);
    return () => { cancelled = true; clearInterval(interval); };
  }, []);

  if (loading) {
    return (
      <div className="stack">
        <Panel title="Strategies Engine" subtitle="Loading trade analysis..." icon={Brain}>
          <div className="empty-state">Fetching strategy data from backend...</div>
        </Panel>
      </div>
    );
  }

  if (error) {
    return (
      <div className="stack">
        <Panel title="Strategies Engine" subtitle="Connection issue" icon={Brain}>
          <div className="empty-state" style={{ color: "var(--red)" }}>Failed to load strategies: {error}</div>
        </Panel>
      </div>
    );
  }

  const strategies = data?.strategies || [];
  const patterns = data?.patterns || [];
  const meta = data?.meta || {};
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
    <div className="stack">
      {/* Overview metrics */}
      <Panel title="Strategies Engine" subtitle={`Analyzing ${meta.total_trades || 0} trades over ${meta.analysis_window || "30d"}`} icon={Brain}>
        <div className="card-grid three-up">
          <MetricTile label="Total Strategies" value={String(strategies.length)} />
          <MetricTile label="Profitable" value={String(strategies.filter((s) => s.total_pnl > 0).length)} tone="pass" />
          <MetricTile label="Unprofitable" value={String(strategies.filter((s) => s.total_pnl < 0).length)} tone={strategies.some((s) => s.total_pnl < 0) ? "fail" : "info"} />
        </div>
      </Panel>

      {/* Strategy table */}
      <Panel title="Strategy Buckets" subtitle="Symbol × Session × Side — ranked by weighted score" icon={BarChart3}>
        <div style={{ display: "flex", gap: 8, marginBottom: 16, flexWrap: "wrap" }}>
          {["score", "pnl", "win_rate", "trades"].map((key) => (
            <button
              key={key}
              onClick={() => setSortKey(key)}
              style={{
                padding: "5px 12px",
                background: sortKey === key ? "rgba(98,214,255,0.15)" : "rgba(255,255,255,0.04)",
                border: sortKey === key ? "1px solid var(--cyan)" : "1px solid rgba(255,255,255,0.08)",
                borderRadius: 4,
                color: sortKey === key ? "var(--cyan)" : "var(--muted)",
                fontSize: "0.75rem",
                fontWeight: 600,
                cursor: "pointer",
                textTransform: "uppercase",
              }}
            >
              {key.replace("_", " ")}
            </button>
          ))}
        </div>

        {sorted.length === 0 ? (
          <div className="empty-state">No trades recorded yet. Strategies will appear once the system executes trades.</div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {sorted.map((s) => (
              <div
                key={s.id}
                style={{
                  padding: "16px 20px",
                  background: "rgba(255,255,255,0.02)",
                  borderRadius: 10,
                  border: `1px solid ${s.score > 0 ? "rgba(52,211,153,0.15)" : s.score < 0 ? "rgba(255,107,107,0.15)" : "rgba(255,255,255,0.05)"}`,
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                    <span style={{ fontWeight: 700, fontSize: "1.05rem" }}>{s.symbol}</span>
                    <SessionBadge session={s.session} />
                    <SideBadge side={s.side} />
                  </div>
                  <div style={{ textAlign: "right" }}>
                    <div style={{ fontSize: "1.15rem", fontWeight: 700, color: s.total_pnl >= 0 ? "var(--green)" : "var(--red)" }}>
                      {useMoney(s.total_pnl)}
                    </div>
                    <div style={{ fontSize: "0.7rem", color: "var(--muted)" }}>{s.trades} trades</div>
                  </div>
                </div>

                <div className="card-grid" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(100px, 1fr))", gap: 8, marginBottom: 10 }}>
                  <MetricTile label="Win Rate" value={pct(s.win_rate)} tone={s.win_rate >= 0.55 ? "pass" : s.win_rate < 0.4 ? "fail" : "warn"} />
                  <MetricTile label="Expectancy" value={useMoney(s.expectancy)} tone={toneForPnl(s.expectancy)} />
                  <MetricTile label="Profit Factor" value={s.profit_factor >= 999 ? "∞" : s.profit_factor.toFixed(2)} tone={s.profit_factor >= 1.5 ? "pass" : s.profit_factor < 1 ? "fail" : "warn"} />
                  <MetricTile label="Sharpe" value={s.sharpe.toFixed(2)} tone={s.sharpe > 0.5 ? "pass" : s.sharpe < 0 ? "fail" : "info"} />
                  <MetricTile label="Confidence" value={pct(s.confidence)} tone={s.confidence >= 0.7 ? "pass" : "info"} />
                  <MetricTile label="Score" value={s.score.toFixed(1)} tone={toneForPnl(s.score)} />
                </div>

                <ScoreBar value={s.score} max={maxScore} />
              </div>
            ))}
          </div>
        )}
      </Panel>

      {/* Pattern Recognition */}
      <Panel title="Pattern Recognition" subtitle="Profitability patterns weighted by win rate and volume" icon={Lightbulb}>
        <div className="card-grid three-up" style={{ gap: 16 }}>
          {/* Symbol patterns */}
          <div style={{ padding: 16, background: "rgba(255,255,255,0.02)", borderRadius: 10, border: "1px solid rgba(255,255,255,0.05)" }}>
            <div className="eyebrow" style={{ marginBottom: 12, display: "flex", alignItems: "center", gap: 6 }}>
              <TrendingUp size={14} /> By Symbol
            </div>
            {symbolPatterns.length === 0 ? (
              <div style={{ color: "var(--muted)", fontSize: "0.8rem" }}>No data</div>
            ) : (
              symbolPatterns.map((p) => (
                <div key={p.name} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "8px 0", borderBottom: "1px solid rgba(255,255,255,0.04)" }}>
                  <div>
                    <div style={{ fontWeight: 600, fontSize: "0.9rem" }}>{p.name}</div>
                    <div style={{ fontSize: "0.7rem", color: "var(--muted)" }}>{p.trades} trades · {pct(p.win_rate)} WR</div>
                  </div>
                  <div style={{ textAlign: "right" }}>
                    <div style={{ fontWeight: 700, color: p.pnl >= 0 ? "var(--green)" : "var(--red)", fontSize: "0.95rem" }}>{useMoney(p.pnl)}</div>
                    <div style={{ fontSize: "0.65rem", color: "var(--dim)" }}>wt: {p.weight.toFixed(2)}</div>
                  </div>
                </div>
              ))
            )}
          </div>

          {/* Session patterns */}
          <div style={{ padding: 16, background: "rgba(255,255,255,0.02)", borderRadius: 10, border: "1px solid rgba(255,255,255,0.05)" }}>
            <div className="eyebrow" style={{ marginBottom: 12, display: "flex", alignItems: "center", gap: 6 }}>
              <Clock size={14} /> By Session
            </div>
            {sessionPatterns.length === 0 ? (
              <div style={{ color: "var(--muted)", fontSize: "0.8rem" }}>No data</div>
            ) : (
              sessionPatterns.map((p) => (
                <div key={p.name} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "8px 0", borderBottom: "1px solid rgba(255,255,255,0.04)" }}>
                  <div>
                    <SessionBadge session={p.name} />
                    <div style={{ fontSize: "0.7rem", color: "var(--muted)", marginTop: 4 }}>{p.trades} trades · {pct(p.win_rate)} WR</div>
                  </div>
                  <div style={{ textAlign: "right" }}>
                    <div style={{ fontWeight: 700, color: p.pnl >= 0 ? "var(--green)" : "var(--red)", fontSize: "0.95rem" }}>{useMoney(p.pnl)}</div>
                    <div style={{ fontSize: "0.65rem", color: "var(--dim)" }}>wt: {p.weight.toFixed(2)}</div>
                  </div>
                </div>
              ))
            )}
          </div>

          {/* Side patterns */}
          <div style={{ padding: 16, background: "rgba(255,255,255,0.02)", borderRadius: 10, border: "1px solid rgba(255,255,255,0.05)" }}>
            <div className="eyebrow" style={{ marginBottom: 12, display: "flex", alignItems: "center", gap: 6 }}>
              <ArrowUpDown size={14} /> By Side
            </div>
            {sidePatterns.length === 0 ? (
              <div style={{ color: "var(--muted)", fontSize: "0.8rem" }}>No data</div>
            ) : (
              sidePatterns.map((p) => (
                <div key={p.name} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "8px 0", borderBottom: "1px solid rgba(255,255,255,0.04)" }}>
                  <div>
                    <SideBadge side={p.name} />
                    <div style={{ fontSize: "0.7rem", color: "var(--muted)", marginTop: 4 }}>{p.trades} trades · {pct(p.win_rate)} WR</div>
                  </div>
                  <div style={{ textAlign: "right" }}>
                    <div style={{ fontWeight: 700, color: p.pnl >= 0 ? "var(--green)" : "var(--red)", fontSize: "0.95rem" }}>{useMoney(p.pnl)}</div>
                    <div style={{ fontSize: "0.65rem", color: "var(--dim)" }}>wt: {p.weight.toFixed(2)}</div>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </Panel>
    </div>
  );
}
