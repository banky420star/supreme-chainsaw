/** @jsxImportSource react */
import React, { useState, useEffect } from "react";
import { Brain, Activity, TrendingUp, AlertCircle, Lightbulb, Link as LinkIcon, BookOpen } from "lucide-react";

export function TrainingAnalysisPanel({ data }) {
  const analysis = data?.trainingAnalysis || {};
  const description = analysis?.description || {};
  const trajectory = analysis?.trajectory || null;
  const insights = analysis?.insights || [];

  const hasData = description?.ai_description || description?.stage_description;

  if (!hasData) {
    return (
      <div className="panel" style={{ padding: 20, border: "1px solid rgba(90,215,255,0.1)", borderRadius: 12, background: "rgba(90,215,255,0.02)" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12 }}>
          <Brain size={20} style={{ color: "var(--accent-cyan)" }} />
          <span style={{ fontWeight: 600 }}>AI Training Analysis</span>
        </div>
        <div style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>
          No active training detected. Start training to see AI-generated learning insights.
        </div>
      </div>
    );
  }

  const stageColors = {
    exploration: "var(--accent-amber)",
    pattern_recognition: "var(--accent-cyan)",
    strategy_refinement: "var(--accent-purple)",
    optimization: "var(--accent-green)",
    convergence: "var(--accent-blue)",
    unknown: "var(--text-muted)",
  };

  const stageColor = stageColors[description.learning_stage] || "var(--text-muted)";
  const progress = description.progress_pct || 0;

  return (
    <div className="panel" style={{ border: "1px solid rgba(90,215,255,0.15)", borderRadius: 12, background: "radial-gradient(400px 220px at 0% 0%, rgba(90,215,255,0.05), transparent 60%), var(--bg-surface)" }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "16px 20px", borderBottom: "1px solid rgba(255,255,255,0.05)" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <Brain size={22} style={{ color: "var(--accent-cyan)" }} />
          <span style={{ fontWeight: 700, fontSize: "1.05rem" }}>AI Training Analysis</span>
        </div>
        <div style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
          Powered by Ollama
        </div>
      </div>

      <div style={{ padding: 20 }}>
        {/* Learning Stage Badge */}
        <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 20 }}>
          <div
            style={{
              padding: "8px 16px",
              borderRadius: 20,
              background: `${stageColor}15`,
              border: `1px solid ${stageColor}40`,
              color: stageColor,
              fontWeight: 600,
              fontSize: "0.85rem",
              textTransform: "uppercase",
              letterSpacing: "0.02em",
            }}
          >
            {description.learning_stage?.replace(/_/g, " ") || "Unknown"}
          </div>
          <div style={{ flex: 1 }}>
            <div style={{ height: 6, borderRadius: 3, background: "rgba(255,255,255,0.1)", overflow: "hidden" }}>
              <div
                style={{
                  height: "100%",
                  width: `${progress}%`,
                  background: `linear-gradient(90deg, ${stageColor}, var(--accent-cyan))`,
                  borderRadius: 3,
                  transition: "width 0.3s ease",
                }}
              />
            </div>
          </div>
          <div style={{ fontFamily: "var(--mono)", fontSize: "0.85rem", color: "var(--text-secondary)" }}>
            {progress.toFixed(1)}%
          </div>
        </div>

        {/* AI Description */}
        <div style={{ marginBottom: 24 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
            <Lightbulb size={16} style={{ color: "var(--accent-amber)" }} />
            <span style={{ fontSize: "0.75rem", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.05em" }}>
              What the Model is Learning
            </span>
          </div>
          <div
            style={{
              padding: 16,
              borderRadius: 10,
              background: "rgba(90,215,255,0.03)",
              border: "1px solid rgba(90,215,255,0.1)",
              fontSize: "0.95rem",
              lineHeight: 1.6,
              color: "var(--text-primary)",
            }}
          >
            {description.ai_description || description.stage_description}
          </div>
        </div>

        {/* Metrics Grid */}
        {description.metrics_summary && (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12, marginBottom: 20 }}>
            <MetricBox label="Training Loss" value={description.metrics_summary.loss?.toFixed(4) || "N/A"} />
            <MetricBox label="Avg Reward" value={description.metrics_summary.reward?.toFixed(3) || "N/A"} color="var(--accent-green)" />
            <MetricBox label="Win Rate" value={`${description.metrics_summary.win_rate?.toFixed(1) || 0}%`} />
            <MetricBox label="Trades" value={description.metrics_summary.trades || 0} />
          </div>
        )}

        {/* Insights */}
        {insights.length > 0 && (
          <div style={{ marginBottom: 20 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
              <Activity size={16} style={{ color: "var(--accent-purple)" }} />
              <span style={{ fontSize: "0.75rem", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.05em" }}>
                Insights
              </span>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {insights.map((insight, i) => (
                <div
                  key={i}
                  style={{
                    padding: "10px 14px",
                    borderRadius: 8,
                    background: insight.includes("⚠️")
                      ? "rgba(255,123,143,0.08)"
                      : "rgba(57,217,138,0.08)",
                    border: `1px solid ${insight.includes("⚠️") ? "rgba(255,123,143,0.2)" : "rgba(57,217,138,0.2)"}`,
                    fontSize: "0.85rem",
                    color: insight.includes("⚠️") ? "var(--accent-red)" : "var(--accent-green)",
                  }}
                >
                  {insight}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Learning Trajectory */}
        {trajectory && (
          <div style={{ marginBottom: 16 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
              <TrendingUp size={16} style={{ color: "var(--accent-blue)" }} />
              <span style={{ fontSize: "0.75rem", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.05em" }}>
                Learning Trajectory ({trajectory.symbol})
              </span>
            </div>
            <div
              style={{
                padding: 14,
                borderRadius: 10,
                background: "rgba(255,255,255,0.02)",
                border: "1px solid rgba(255,255,255,0.05)",
                fontSize: "0.85rem",
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 8 }}>
                <span style={{ color: "var(--text-muted)" }}>Current Stage:</span>
                <span style={{ fontWeight: 600 }}>{trajectory.current_stage?.replace(/_/g, " ")}</span>
              </div>
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 8 }}>
                <span style={{ color: "var(--text-muted)" }}>Progressions:</span>
                <span style={{ fontWeight: 600 }}>{trajectory.stage_progressions}</span>
              </div>
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <span style={{ color: "var(--text-muted)" }}>Loss Trend:</span>
                <span
                  style={{
                    fontWeight: 600,
                    color: trajectory.loss_trend?.includes("overfitting")
                      ? "var(--accent-red)"
                      : trajectory.loss_trend?.includes("improving")
                      ? "var(--accent-green)"
                      : "var(--text-secondary)",
                  }}
                >
                  {trajectory.loss_trend}
                </span>
              </div>
            </div>
          </div>
        )}

        {/* Timestamp */}
        <div style={{ textAlign: "right", fontSize: "0.7rem", color: "var(--text-muted)" }}>
          Last updated: {description.timestamp ? new Date(description.timestamp).toLocaleTimeString() : "Never"}
        </div>
      </div>
    </div>
  );
}

function MetricBox({ label, value, color }) {
  return (
    <div
      style={{
        padding: 12,
        borderRadius: 8,
        background: "rgba(255,255,255,0.02)",
        border: "1px solid rgba(255,255,255,0.05)",
        textAlign: "center",
      }}
    >
      <div style={{ fontSize: "0.7rem", color: "var(--text-muted)", marginBottom: 4 }}>{label}</div>
      <div style={{ fontSize: "1rem", fontWeight: 700, color: color || "var(--text-primary)" }}>{value}</div>
    </div>
  );
}

export function TrainingTradingConnection({ data, selectedSymbol }) {
  const [connection, setConnection] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!selectedSymbol) return;

    const analyzeConnection = async () => {
      setLoading(true);
      try {
        const response = await fetch("/api/training/analyze", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            training_symbol: selectedSymbol,
            trading_symbol: selectedSymbol,
          }),
        });

        if (response.ok) {
          const result = await response.json();
          if (result.ok) {
            setConnection(result.analysis);
          }
        }
      } catch (err) {
        console.error("Failed to analyze training-trading connection:", err);
      } finally {
        setLoading(false);
      }
    };

    analyzeConnection();
    const interval = setInterval(analyzeConnection, 10000);
    return () => clearInterval(interval);
  }, [selectedSymbol]);

  if (!selectedSymbol) {
    return (
      <div className="panel" style={{ padding: 20 }}>
        <div style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>
          Select a symbol to see training-trading connection analysis.
        </div>
      </div>
    );
  }

  return (
    <div
      className="panel"
      style={{
        border: "1px solid rgba(57,217,138,0.15)",
        borderRadius: 12,
        background: "radial-gradient(400px 220px at 100% 100%, rgba(57,217,138,0.05), transparent 60%), var(--bg-surface)",
      }}
    >
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "16px 20px", borderBottom: "1px solid rgba(255,255,255,0.05)" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <LinkIcon size={20} style={{ color: "var(--accent-green)" }} />
          <span style={{ fontWeight: 700, fontSize: "1.05rem" }}>Training → Trading Connection</span>
        </div>
        <div style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
          {selectedSymbol}
        </div>
      </div>

      <div style={{ padding: 20 }}>
        {loading && !connection ? (
          <div style={{ textAlign: "center", padding: 20, color: "var(--text-muted)" }}>
            <Activity size={24} style={{ animation: "pulse 1.5s infinite", marginBottom: 10 }} />
            <div>Analyzing connection...</div>
          </div>
        ) : connection ? (
          <>
            {/* Alignment Score */}
            <div style={{ display: "flex", alignItems: "center", gap: 16, marginBottom: 20 }}>
              <div
                style={{
                  width: 80,
                  height: 80,
                  borderRadius: "50%",
                  background: `conic-gradient(var(--accent-green) ${connection.alignment_score * 360}deg, rgba(255,255,255,0.05) 0deg)`,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  position: "relative",
                }}
              >
                <div
                  style={{
                    width: 64,
                    height: 64,
                    borderRadius: "50%",
                    background: "var(--bg-surface)",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    fontSize: "1.1rem",
                    fontWeight: 700,
                    color: connection.alignment_score > 0.7 ? "var(--accent-green)" : connection.alignment_score > 0.4 ? "var(--accent-amber)" : "var(--accent-red)",
                  }}
                >
                  {(connection.alignment_score * 100).toFixed(0)}%
                </div>
              </div>
              <div>
                <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginBottom: 4 }}>Alignment Score</div>
                <div style={{ fontSize: "0.9rem", fontWeight: 600 }}>
                  {connection.alignment_score > 0.7
                    ? "Strong Alignment"
                    : connection.alignment_score > 0.4
                    ? "Moderate Alignment"
                    : "Weak Alignment"}
                </div>
                <div style={{ fontSize: "0.8rem", color: "var(--text-secondary)", marginTop: 4 }}>
                  How well training translates to live trading
                </div>
              </div>
            </div>

            {/* Connection Description */}
            {connection.connection_description && (
              <div style={{ marginBottom: 16 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
                  <BookOpen size={14} style={{ color: "var(--accent-cyan)" }} />
                  <span style={{ fontSize: "0.75rem", color: "var(--text-muted)", textTransform: "uppercase" }}>
                    AI Analysis
                  </span>
                </div>
                <div
                  style={{
                    padding: 14,
                    borderRadius: 10,
                    background: "rgba(90,215,255,0.03)",
                    border: "1px solid rgba(90,215,255,0.1)",
                    fontSize: "0.9rem",
                    lineHeight: 1.6,
                    color: "var(--text-primary)",
                  }}
                >
                  {connection.connection_description}
                </div>
              </div>
            )}

            {/* Metrics Comparison */}
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
              <div
                style={{
                  padding: 14,
                  borderRadius: 10,
                  background: "rgba(255,255,255,0.02)",
                  border: "1px solid rgba(255,255,255,0.05)",
                }}
              >
                <div style={{ fontSize: "0.7rem", color: "var(--text-muted)", marginBottom: 6 }}>Training Win Rate</div>
                <div style={{ fontSize: "1.1rem", fontWeight: 700 }}>
                  {connection.training_metrics?.win_rate?.toFixed(1) || 0}%
                </div>
              </div>
              <div
                style={{
                  padding: 14,
                  borderRadius: 10,
                  background: "rgba(255,255,255,0.02)",
                  border: "1px solid rgba(255,255,255,0.05)",
                }}
              >
                <div style={{ fontSize: "0.7rem", color: "var(--text-muted)", marginBottom: 6 }}>Live Win Rate</div>
                <div
                  style={{
                    fontSize: "1.1rem",
                    fontWeight: 700,
                    color: connection.trading_metrics?.live_win_rate > connection.training_metrics?.win_rate
                      ? "var(--accent-green)"
                      : "var(--text-primary)",
                  }}
                >
                  {connection.trading_metrics?.live_win_rate?.toFixed(1) || 0}%
                </div>
              </div>
            </div>
          </>
        ) : (
          <div style={{ textAlign: "center", padding: 20, color: "var(--text-muted)" }}>
            <AlertCircle size={24} style={{ marginBottom: 10 }} />
            <div>No connection data available</div>
          </div>
        )}
      </div>
    </div>
  );
}

export default TrainingAnalysisPanel;
