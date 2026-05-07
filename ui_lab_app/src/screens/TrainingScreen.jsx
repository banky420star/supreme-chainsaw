import React from "react";
import { Activity, Brain, TrendingUp, Clock, Target, BarChart3, Zap } from "lucide-react";
import { Panel, MetricTile, ProgressBar, Gauge, dollars, pct } from "../components/Common";
import { EnhancedTrainingMetrics } from "../components/TrainingMetrics";
import { TrainingAnalysisPanel, TrainingTradingConnection } from "../components/TrainingAnalysis";

export default function TrainingScreen({ data, selectedSymbol }) {
  const training = data?.training || {};
  const ppo = training.ppo || {};
  const trainingMetrics = data?.trainingMetrics || {};

  const isTraining = ppo.state === "training" || trainingMetrics.training_active;
  const symbols = training.configuredSymbols || ["BTCUSDm", "XAUUSDm"];

  return (
    <div className="stack animate-in" style={{ gap: 20 }}>
      {/* Header - Training Status */}
      <div style={{
        padding: "20px 24px",
        borderRadius: 12,
        border: "1px solid rgba(90,215,255,0.15)",
        background: "radial-gradient(400px 220px at 100% 0%, rgba(90,215,255,0.08), transparent 60%), var(--bg-surface)",
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
      }}>
        <div>
          <div className="eyebrow" style={{ marginBottom: 6 }}>Training Status</div>
          <h2 style={{ fontSize: "1.5rem", fontWeight: 700, letterSpacing: "-0.02em" }}>
            {isTraining ? "Training Active" : "Training Idle"}
          </h2>
          <p style={{ color: "var(--text-secondary)", fontSize: "0.85rem", marginTop: 4 }}>
            {isTraining
              ? `PPO training ${ppo.currentSymbol} at ${(ppo.progressPct || 0).toFixed(1)}% completion`
              : "Start training to see AI-generated insights and per-symbol metrics"}
          </p>
        </div>
        <div style={{
          display: "flex",
          gap: 12,
          alignItems: "center",
        }}>
          <div style={{
            padding: "8px 16px",
            borderRadius: 20,
            background: isTraining ? "rgba(57,217,138,0.1)" : "rgba(255,255,255,0.05)",
            border: `1px solid ${isTraining ? "rgba(57,217,138,0.3)" : "rgba(255,255,255,0.1)"}`,
            color: isTraining ? "var(--accent-green)" : "var(--text-muted)",
            fontSize: "0.8rem",
            fontWeight: 600,
          }}>
            {isTraining ? "● LIVE" : "○ IDLE"}
          </div>
        </div>
      </div>

      {/* Row 1: AI Analysis + Training Connection (side by side) */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
        <TrainingAnalysisPanel data={data} />
        <TrainingTradingConnection data={data} selectedSymbol={selectedSymbol} />
      </div>

      {/* Row 2: Enhanced Training Metrics - Full Width */}
      <Panel title="Training Performance" subtitle="Per-symbol profit, balance, drawdown, and win rates" icon={BarChart3}>
        <EnhancedTrainingMetrics data={data} />
      </Panel>

      {/* Row 3: Timeframe Optimization */}
      {trainingMetrics.timeframe_selections && Object.keys(trainingMetrics.timeframe_selections).length > 0 && (
        <Panel title="Timeframe Optimization" subtitle="Auto-selected timeframes based on Sharpe ratio × Data quality" icon={Clock}>
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <div style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))",
              gap: 12
            }}>
              {Object.entries(trainingMetrics.timeframe_selections || {}).map(([sym, tfData]) => {
                const selected = tfData.selected || "M5";
                const score = tfData.selection_score || 0;
                const allResults = tfData.all_results || {};
                const selectedResult = allResults[selected] || {};

                return (
                  <div key={sym} style={{
                    padding: 14,
                    borderRadius: 10,
                    background: "rgba(90,215,255,0.04)",
                    border: "1px solid rgba(90,215,255,0.1)",
                  }}>
                    <div style={{
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                      marginBottom: 8
                    }}>
                      <span style={{ fontWeight: 700, fontSize: "1rem" }}>{sym}</span>
                      <span style={{
                        padding: "4px 10px",
                        borderRadius: 12,
                        background: "rgba(90,215,255,0.15)",
                        color: "var(--accent-cyan)",
                        fontSize: "0.75rem",
                        fontWeight: 600,
                      }}>
                        {selected}
                      </span>
                    </div>
                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 8, fontSize: "0.75rem" }}>
                      <div>
                        <span style={{ color: "var(--text-muted)" }}>Score: </span>
                        <span style={{ fontWeight: 600 }}>{score.toFixed(2)}</span>
                      </div>
                      <div>
                        <span style={{ color: "var(--text-muted)" }}>Sharpe: </span>
                        <span style={{ fontWeight: 600, color: (selectedResult.sharpe_ratio || 0) > 1 ? "var(--accent-green)" : "var(--text-primary)" }}>
                          {(selectedResult.sharpe_ratio || 0).toFixed(2)}
                        </span>
                      </div>
                      <div>
                        <span style={{ color: "var(--text-muted)" }}>ADX: </span>
                        <span style={{ fontWeight: 600 }}>{(selectedResult.adx || 0).toFixed(1)}</span>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
            <div style={{
              padding: 10,
              background: "rgba(255,255,255,0.02)",
              borderRadius: 8,
              fontSize: "0.75rem",
              color: "var(--text-muted)",
            }}>
              <strong style={{ color: "var(--text-secondary)" }}>Selection Criteria:</strong> Sharpe ratio × Data quality × Timeframe bonus |
              Higher timeframes receive bonus weight for more reliable patterns
            </div>
          </div>
        </Panel>
      )}

      {/* Row 4: Quick Stats - Summary Cards */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12 }}>
        <div style={{
          padding: 16,
          borderRadius: 10,
          background: "rgba(57,217,138,0.05)",
          border: "1px solid rgba(57,217,138,0.1)",
          textAlign: "center",
        }}>
          <div style={{ fontSize: "0.7rem", color: "var(--text-muted)", marginBottom: 4 }}>Best Symbol</div>
          <div style={{ fontSize: "1.1rem", fontWeight: 700, color: "var(--accent-green)" }}>
            {trainingMetrics.best_symbol || "-"}
          </div>
        </div>
        <div style={{
          padding: 16,
          borderRadius: 10,
          background: "rgba(255,255,255,0.02)",
          border: "1px solid rgba(255,255,255,0.05)",
          textAlign: "center",
        }}>
          <div style={{ fontSize: "0.7rem", color: "var(--text-muted)", marginBottom: 4 }}>Avg Return</div>
          <div style={{
            fontSize: "1.1rem",
            fontWeight: 700,
            color: (trainingMetrics.average_return || 0) >= 0 ? "var(--accent-green)" : "var(--accent-red)"
          }}>
            {trainingMetrics.average_return ? `${trainingMetrics.average_return.toFixed(1)}%` : "-"}
          </div>
        </div>
        <div style={{
          padding: 16,
          borderRadius: 10,
          background: "rgba(255,255,255,0.02)",
          border: "1px solid rgba(255,255,255,0.05)",
          textAlign: "center",
        }}>
          <div style={{ fontSize: "0.7rem", color: "var(--text-muted)", marginBottom: 4 }}>Max Drawdown</div>
          <div style={{
            fontSize: "1.1rem",
            fontWeight: 700,
            color: (trainingMetrics.max_drawdown || 0) > 10 ? "var(--accent-red)" : "var(--text-primary)"
          }}>
            {trainingMetrics.max_drawdown ? `${trainingMetrics.max_drawdown.toFixed(1)}%` : "-"}
          </div>
        </div>
        <div style={{
          padding: 16,
          borderRadius: 10,
          background: "rgba(255,255,255,0.02)",
          border: "1px solid rgba(255,255,255,0.05)",
          textAlign: "center",
        }}>
          <div style={{ fontSize: "0.7rem", color: "var(--text-muted)", marginBottom: 4 }}>Symbols Tracked</div>
          <div style={{ fontSize: "1.1rem", fontWeight: 700 }}>
            {(trainingMetrics.symbols || []).length}
          </div>
        </div>
      </div>
    </div>
  );
}
