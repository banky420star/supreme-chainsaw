import React from "react";
import { Brain, GitBranch, Shield, Sparkles } from "lucide-react";
import { Panel, MetricTile, ProgressBar, Gauge, StatRow, dollars, pct } from "../components/Common";

export default function ModelsScreen({ data }) {
  const registry = data?.registry || {};
  const learning = data?.learning || {};
  const ppoDiag = data?.ppoDiagnostics || {};
  const training = data?.training || {};
  const lstm = training.lstm || {};
  const ppo = training.ppo || {};
  const dreamer = training.dreamerV3 || {};

  const champion = learning?.champion || {};
  const canary = learning?.canary || {};
  const candidates = learning?.candidates || [];

  const lstmCandidates = candidates.filter((c) => c.type === "lstm").sort((a, b) => (a.loss || 0) - (b.loss || 0));
  const bestLstm = lstmCandidates[0] || {};

  // Per-symbol model information from the registry
  const perSymbolModels = registry.perSymbolModels || {};
  const configuredSymbols = training.configuredSymbols || ["BTCUSDm", "XAUUSDm", "EURUSDm", "GBPUSDm"];

  return (
    <div className="stack animate-in">
      {/* Per-Symbol Model Status */}
      {Object.keys(perSymbolModels).length > 0 && (
        <Panel title="Per-Symbol Models" subtitle="Active champion/canary per trading symbol" icon={Shield}>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))", gap: 12 }}>
            {configuredSymbols.map((sym) => {
              const symInfo = perSymbolModels[sym] || {};
              return (
                <div key={sym} style={{
                  padding: 16, borderRadius: 12, border: "1px solid rgba(255,255,255,0.06)",
                  background: symInfo.has_per_symbol_champion ? "rgba(57,217,138,0.04)" : "rgba(255,255,255,0.02)",
                }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <span style={{ fontSize: "1.1rem", fontWeight: 700 }}>{sym}</span>
                      {symInfo.has_per_symbol_champion && (
                        <span className="lane-chip tone-pass" style={{ fontSize: "0.7rem" }}>DEDICATED</span>
                      )}
                    </div>
                  </div>
                  <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                    <div style={{ display: "flex", justifyContent: "space-between" }}>
                      <span style={{ color: "var(--text-muted)", fontSize: "0.78rem" }}>Champion</span>
                      <span style={{ fontFamily: "var(--mono)", fontSize: "0.78rem" }}>
                        {symInfo.champion || <span style={{ color: "var(--text-muted)" }}>global</span>}
                      </span>
                    </div>
                    <div style={{ display: "flex", justifyContent: "space-between" }}>
                      <span style={{ color: "var(--text-muted)", fontSize: "0.78rem" }}>Canary</span>
                      <span style={{ fontFamily: "var(--mono)", fontSize: "0.78rem" }}>
                        {symInfo.canary || <span style={{ color: "var(--text-muted)" }}>none</span>}
                      </span>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </Panel>
      )}

      {/* Champion Model */}
      <Panel title="Champion Model" subtitle="Current production model" icon={Shield}>
        <div style={{ display: "flex", gap: 20, flexWrap: "wrap" }}>
          <div style={{ flex: "1 1 200px" }}>
            <div className="metric-grid" style={{ gridTemplateColumns: "repeat(2, 1fr)" }}>
              <MetricTile label="Version" value={champion.version || registry.champion?.id || "unknown"} tone="pass" />
              <MetricTile label="Type" value={champion.scorecard?.type || "ppo"} />
              <MetricTile label="Symbols" value={Array.isArray(champion.scorecard?.symbols) ? champion.scorecard.symbols.join(", ") : String(champion.scorecard?.symbols || "")} />
              <MetricTile label="Source" value={champion.scorecard?.source ? "Manual promotion" : "trained"} />
            </div>
          </div>
          <div style={{ flex: "1 1 200px" }}>
            <Gauge value={champion.scorecard?.win_rate ? champion.scorecard.win_rate / 100 : 0.5} max={1} size={100} label="Win Rate" />
          </div>
        </div>
        <div className="note" style={{ marginTop: 16 }}>
          <strong>Path:</strong> {champion.path || "N/A"}
        </div>
      </Panel>

      {/* Canary Model */}
      <Panel title="Canary Model" subtitle="Candidate under evaluation" icon={GitBranch}>
        {canary.active ? (
          <div className="metric-grid" style={{ gridTemplateColumns: "repeat(2, 1fr)" }}>
            <MetricTile label="Version" value={canary.version || "none"} tone={canary.version ? "warn" : ""} />
            <MetricTile label="Score" value={canary.scorecard ? `${(canary.scorecard.win_rate || 0).toFixed(1)}%` : "N/A"} />
          </div>
        ) : (
          <div className="empty-state">No canary model active. The system will promote a canary when a candidate outperforms the champion.</div>
        )}
      </Panel>

      {/* PPO Model Details */}
      <Panel title="PPO Model" subtitle="Current policy network details" icon={Brain}>
        <div className="metric-grid" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(130px, 1fr))" }}>
          <MetricTile label="State" value={ppo.state || "idle"} tone={ppo.state === "training" ? "pass" : ""} />
          <MetricTile label="Progress" value={`${(ppo.progressPct || 0).toFixed(1)}%`} tone={ppo.progress > 0.5 ? "pass" : ""} />
          <MetricTile label="Timesteps" value={`${(ppo.currentTimesteps || 0).toLocaleString()}`} />
          <MetricTile label="Target" value={`${(ppo.targetTimesteps || 0).toLocaleString()}`} />
          <MetricTile label="Symbol" value={ppo.currentSymbol?.split(",")[0] || "N/A"} />
          <MetricTile label="Device" value={ppoDiag.device || "cpu"} />
        </div>
        <div style={{ marginTop: 16 }}>
          <ProgressBar label="Training Progress" value={ppo.progress} tone={ppo.progress > 0.7 ? "pass" : ""} meta={`${(ppo.currentTimesteps || 0).toLocaleString()} / ${(ppo.targetTimesteps || 0).toLocaleString()}`} />
        </div>

        {/* PPO Actions per Symbol */}
        {ppoDiag.last_actions && (
          <div style={{ marginTop: 20 }}>
            <div className="eyebrow" style={{ marginBottom: 10 }}>Latest Actions</div>
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {Object.entries(ppoDiag.last_actions).map(([sym, action]) => (
                <div key={sym} style={{
                  display: "flex", justifyContent: "space-between", alignItems: "center",
                  padding: "10px 14px", borderRadius: 8, border: "1px solid rgba(255,255,255,0.06)",
                  background: "rgba(255,255,255,0.02)",
                }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <strong>{sym}</strong>
                    <span className={`lane-chip ${action.action === "BUY" ? "tone-pass" : action.action === "SELL" ? "tone-warn" : ""}`}>
                      {action.action}
                    </span>
                  </div>
                  <div style={{ fontFamily: "var(--mono)", fontSize: "0.78rem", color: "var(--text-secondary)" }}>
                    conf {(action.confidence * 100).toFixed(1)}% · exp {(action.exposure * 100).toFixed(2)}% · {action.volatility?.replace("_", " ") || ""}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </Panel>

      {/* LSTM Candidates Table */}
      <Panel title="LSTM Model Candidates" subtitle={`${lstmCandidates.length} saved models`} icon={Sparkles}>
        {lstmCandidates.length === 0 ? (
          <div className="empty-state">No LSTM candidates recorded yet.</div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {lstmCandidates.slice(0, 10).map((c, i) => (
              <div key={c.version || i} style={{
                display: "flex", justifyContent: "space-between", alignItems: "center",
                padding: "10px 14px", borderRadius: 8, border: "1px solid rgba(255,255,255,0.06)",
                background: i === 0 ? "rgba(57,217,138,0.04)" : "rgba(255,255,255,0.02)",
              }}>
                <div>
                  <strong style={{ fontSize: "0.88rem" }}>{c.version}</strong>
                  <div style={{ color: "var(--text-muted)", fontSize: "0.72rem", fontFamily: "var(--mono)" }}>
                    {c.saved_at ? new Date(c.saved_at).toLocaleString() : "N/A"}
                  </div>
                </div>
                <div style={{ display: "flex", gap: 16, alignItems: "center" }}>
                  <div style={{ textAlign: "right" }}>
                    <div style={{ fontWeight: 600, color: c.win_rate > 50 ? "var(--accent-green)" : "var(--accent-red)", fontSize: "0.92rem" }}>
                      {(c.win_rate || 0).toFixed(1)}% WR
                    </div>
                  </div>
                  <div style={{ textAlign: "right" }}>
                    <div style={{ fontWeight: 600, fontSize: "0.88rem" }}>
                      Loss: {(c.loss || 0).toFixed(4)}
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </Panel>

      {/* Learning Summary */}
      {learning?.learning_log && (
        <Panel title="Learning Summary" subtitle="Overall trading and learning performance" icon={Brain}>
          {(() => {
            const log = learning.learning_log;
            return (
              <div className="grid-2" style={{ gap: 16 }}>
                <div className="stack" style={{ gap: 10 }}>
                  <StatRow label="Total Trades" value={String(log.trades || 0)} />
                  <StatRow label="Win Rate" value={`${(log.win_rate || 0).toFixed(1)}%`} tone={(log.win_rate || 0) >= 50 ? "pass" : "warn"} />
                  <StatRow label="Profit Factor" value={String((log.profit_factor || 0).toFixed(2))} tone={(log.profit_factor || 0) >= 1 ? "pass" : "fail"} />
                  <StatRow label="Total PnL" value={dollars(log.total_pnl || 0)} tone={(log.total_pnl || 0) >= 0 ? "pass" : "fail"} />
                  <StatRow label="Expectancy" value={dollars(log.expectancy || 0)} tone={(log.expectancy || 0) >= 0 ? "pass" : "fail"} />
                  <StatRow label="Max Loss Streak" value={String(log.max_loss_streak || 0)} tone="warn" />
                </div>
                <div className="stack" style={{ gap: 10 }}>
                  <StatRow label="Avg Win" value={dollars(log.avg_win || 0)} tone="pass" />
                  <StatRow label="Avg Loss" value={dollars(log.avg_loss || 0)} tone="fail" />
                  <StatRow label="Recent Loss Streak" value={String(log.recent_loss_streak || 0)} tone={(log.recent_loss_streak || 0) > 5 ? "warn" : ""} />
                  <StatRow label="Lookback" value={`${log.lookback_days || 30} days`} />
                </div>
              </div>
            );
          })()}
        </Panel>
      )}
    </div>
  );
}