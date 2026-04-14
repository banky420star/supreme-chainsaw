import React from "react";
import { Activity, Brain, Sparkles, Workflow, TrendingUp, GitBranch } from "lucide-react";
import { Panel, MetricTile, ProgressBar, Gauge, JOURNEY_STEPS, PipelineStageBoard, StatRow, dollars, money, pct, shortDuration } from "../components/Common";

function TrainingLossChart({ data, label, colorKey }) {
  if (!data || data.length === 0) return <div className="empty-state">No loss data yet</div>;
  const height = 120;
  const w = 600;
  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;
  const points = data.map((v, i) => {
    const x = (i / Math.max(1, data.length - 1)) * w;
    const y = height - ((v - min) / range) * (height - 20) - 10;
    return `${x},${y}`;
  });
  const areaPoints = `0,${height} ${points.join(" ")} ${w},${height}`;
  const color = colorKey || "var(--accent-cyan)";
  return (
    <svg className="loss-chart" width="100%" height={height} viewBox={`0 0 ${w} ${height}`} preserveAspectRatio="none" style={{ overflow: "visible" }}>
      <defs>
        <linearGradient id={`lossGrad_${label}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.2" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      <polygon points={areaPoints} fill={`url(#lossGrad_${label})`} />
      <polyline points={points.join(" ")} fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      {data.length > 0 && (
        <circle cx={w} cy={height - ((data[data.length - 1] - min) / range) * (height - 20) - 10} r="3" fill={color} className="pulse" />
      )}
    </svg>
  );
}

export default function TrainingScreen({ data, selectedSymbol }) {
  const training = data?.training || {};
  const lstm = training.lstm || {};
  const ppo = training.ppo || {};
  const dreamer = training.dreamerV3 || {};
  const perf = data?.perf || {};
  const registry = data?.registry || {};
  const lanes = data?.trading?.lanes || [];

  const activePhaseIndex = JOURNEY_STEPS.findIndex((s) => s.key === training.activePhase?.toLowerCase()) || 0;

  const lstmLossCurve = perf.lstm_loss_curve || [];
  const equityCurve = perf.equity_curve || [];
  const pnlCurve = perf.pnl_curve || [];
  const confidenceCurve = perf.confidence_curve || [];

  const lane = lanes.find((l) => l.symbol === selectedSymbol) || lanes[0];

  return (
    <div className="stack animate-in">
      {/* Active Phase Header */}
      <div style={{
        padding: 24, borderRadius: 16, border: "1px solid rgba(90,215,255,0.1)",
        background: "radial-gradient(400px 220px at 100% 0%, rgba(90,215,255,0.08), transparent 60%), var(--bg-surface)",
      }}>
        <div className="eyebrow" style={{ marginBottom: 8 }}>Active Training Phase</div>
        <h2 style={{ fontSize: "1.8rem", fontWeight: 700, letterSpacing: "-0.03em", marginBottom: 8 }}>
          {training.activePhase || "Unknown"}
        </h2>
        <p style={{ color: "var(--text-secondary)", fontSize: "0.88rem", maxWidth: 600 }}>
          The system is currently executing the {training.activePhase} phase of the intelligence pipeline.
          {ppo.state === "training" && ` PPO training at ${(ppo.progressPct || 0).toFixed(1)}% completion.`}
          {lstm.state !== "idle" && ` LSTM epoch ${lstm.epoch}/${lstm.epochsTotal}.`}
        </p>
      </div>

      {/* Pipeline Stage Board */}
      <Panel title="Intelligence Pipeline" subtitle="Five-stage model authority pipeline" icon={Workflow}>
        <PipelineStageBoard data={data} activeIndex={activePhaseIndex} />
      </Panel>

      {/* Three Model Panels */}
      <div className="grid-3" style={{ gap: 16 }}>
        {/* LSTM */}
        <Panel title="LSTM Context" subtitle="Memory and feature engineering" icon={Brain}>
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span className={`training-stage-badge ${lstm.state === "idle" ? "idle" : "active"}`}>{lstm.state || "idle"}</span>
              {lstm.currentSymbol && <span style={{ fontFamily: "var(--mono)", fontSize: "0.78rem", color: "var(--text-muted)" }}>{lstm.currentSymbol}</span>}
            </div>
            <Gauge value={lstm.memoryStrength} max={1} size={90} label="Memory" />
            <ProgressBar label="Epoch" value={lstm.epochsTotal > 0 ? lstm.epoch / lstm.epochsTotal : 0} tone="pass" meta={`${lstm.epoch}/${lstm.epochsTotal}`} />
            <div className="metric-grid" style={{ gridTemplateColumns: "1fr 1fr" }}>
              <MetricTile label="Loss" value={lstm.loss?.toFixed(4) || "0"} />
              <MetricTile label="Val Loss" value={lstm.valLoss?.toFixed(4) || "0"} />
            </div>
            <TrainingLossChart data={lstmLossCurve} label="lstm" colorKey="var(--accent-cyan)" />
          </div>
        </Panel>

        {/* PPO */}
        <Panel title="PPO Execution" subtitle="Policy optimization" icon={TrendingUp}>
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span className={`training-stage-badge ${ppo.state === "training" ? "active" : ppo.state === "idle" ? "idle" : "active"}`}>
                {ppo.state || "idle"}
              </span>
              {ppo.currentSymbol && <span style={{ fontFamily: "var(--mono)", fontSize: "0.72rem", color: "var(--text-muted)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: 100 }}>{ppo.currentSymbol}</span>}
            </div>
            <Gauge value={ppo.progress} max={1} size={90} label="Progress" />
            <ProgressBar label="Timesteps" value={ppo.progress} tone={ppo.progress > 0.7 ? "pass" : ""} meta={`${(ppo.currentTimesteps || 0).toLocaleString()} / ${(ppo.targetTimesteps || 0).toLocaleString()}`} />
            <div className="metric-grid" style={{ gridTemplateColumns: "1fr 1fr" }}>
              <MetricTile label="Progress" value={`${(ppo.progressPct || 0).toFixed(1)}%`} tone={ppo.progress > 0.5 ? "pass" : ""} />
              <MetricTile label="Target" value={`${(ppo.targetTimesteps || 0).toLocaleString()}`} />
            </div>
          </div>
        </Panel>

        {/* DreamerV3 */}
        <Panel title="DreamerV3" subtitle="Scenario simulation engine" icon={Sparkles}>
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span className={`training-stage-badge ${dreamer.state === "idle" ? "idle" : "active"}`}>{dreamer.state || "idle"}</span>
              {dreamer.currentSymbol && <span style={{ fontFamily: "var(--mono)", fontSize: "0.78rem", color: "var(--text-muted)" }}>{dreamer.currentSymbol}</span>}
            </div>
            <Gauge value={dreamer.alignment} max={1} size={90} label="Alignment" />
            <ProgressBar label="Steps" value={dreamer.progress} meta={`${(dreamer.steps || 0).toLocaleString()} steps`} />
            <div className="metric-grid" style={{ gridTemplateColumns: "1fr 1fr" }}>
              <MetricTile label="WM Loss" value={dreamer.worldModelLoss?.toFixed(4) || "0"} />
              <MetricTile label="Window" value={String(dreamer.window || 64)} />
            </div>
          </div>
        </Panel>
      </div>

      {/* PPO Diagnostics */}
      {data?.ppoDiagnostics?.last_actions && (
        <Panel title="PPO Diagnostics" subtitle="Last model actions per symbol" icon={Activity}>
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {Object.entries(data.ppoDiagnostics.last_actions).map(([sym, action]) => (
              <div key={sym} style={{
                display: "flex", justifyContent: "space-between", alignItems: "center",
                padding: "12px 16px", borderRadius: 10, border: "1px solid rgba(255,255,255,0.05)",
                background: "rgba(255,255,255,0.02)",
              }}>
                <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                  <span style={{ fontWeight: 700, fontSize: "1rem" }}>{sym}</span>
                  <span className={`lane-chip ${action.action === "BUY" ? "tone-pass" : action.action === "SELL" ? "tone-warn" : ""}`}>
                    {action.action}
                  </span>
                </div>
                <div style={{ display: "flex", gap: 20, alignItems: "center" }}>
                  <span style={{ fontFamily: "var(--mono)", fontSize: "0.78rem", color: "var(--text-secondary)" }}>
                    Conf: {(action.confidence * 100).toFixed(1)}%
                  </span>
                  <span style={{ fontFamily: "var(--mono)", fontSize: "0.72rem", color: "var(--text-muted)" }}>
                    {action.volatility?.replace("_", " ") || ""}
                  </span>
                </div>
              </div>
            ))}
          </div>
          <div className="note" style={{ marginTop: 16 }}>
            <strong>Model:</strong> {data.ppoDiagnostics.model_version || "unknown"} ·
            <strong> Device:</strong> {data.ppoDiagnostics.device || "cpu"} ·
            <strong> Obs Shape:</strong> {JSON.stringify(data.ppoDiagnostics.obs_shape || [])}
          </div>
        </Panel>
      )}

      {/* Performance Curves */}
      <Panel title="Performance Curves" subtitle="Historical training and trading metrics" icon={Activity}>
        <div className="grid-2" style={{ gap: 16 }}>
          <div>
            <div className="eyebrow" style={{ marginBottom: 8 }}>LSTM Loss Curve</div>
            <TrainingLossChart data={lstmLossCurve} label="lstm2" colorKey="var(--accent-cyan)" />
          </div>
          <div>
            <div className="eyebrow" style={{ marginBottom: 8 }}>Equity Curve</div>
            <TrainingLossChart data={equityCurve} label="equity" colorKey="var(--accent-green)" />
          </div>
          <div>
            <div className="eyebrow" style={{ marginBottom: 8 }}>PnL Curve</div>
            <TrainingLossChart data={pnlCurve} label="pnl" colorKey="var(--accent-amber)" />
          </div>
          <div>
            <div className="eyebrow" style={{ marginBottom: 8 }}>Confidence Curve</div>
            <TrainingLossChart data={confidenceCurve} label="conf" colorKey="var(--accent-purple)" />
          </div>
        </div>
      </Panel>

      {/* Scenarios */}
      {data?.scenarios?.regimes && Object.keys(data.scenarios.regimes).length > 0 && (
        <Panel title="Market Scenarios" subtitle="Current regime-based decision analysis" icon={GitBranch}>
          <div className="grid-3" style={{ gap: 12 }}>
            {Object.entries(data.scenarios.regimes).map(([regime, info]) => (
              <div key={regime} style={{
                padding: 16, borderRadius: 12, border: "1px solid rgba(255,255,255,0.06)",
                background: "rgba(255,255,255,0.02)",
              }}>
                <div style={{ fontWeight: 700, fontSize: "0.92rem", marginBottom: 8 }}>
                  {regime.replace(/_/g, " ")}
                </div>
                <div className="metric-grid" style={{ gridTemplateColumns: "1fr 1fr", gap: 6 }}>
                  <MetricTile label="Buys" value={String(info.buy_count || 0)} tone="pass" />
                  <MetricTile label="Sells" value={String(info.sell_count || 0)} tone="warn" />
                  <MetricTile label="Holds" value={String(info.hold_count || 0)} />
                  <MetricTile label="Conf" value={`${((info.avg_confidence || 0) * 100).toFixed(1)}%`} />
                </div>
                <div style={{ marginTop: 8, fontSize: "0.75rem", color: "var(--text-muted)", fontFamily: "var(--mono)" }}>
                  {(info.symbols || []).join(", ")}
                </div>
              </div>
            ))}
          </div>
        </Panel>
      )}
    </div>
  );
}