import React, { useState } from "react";
import { Activity, Brain, Shield, Zap, TrendingUp, Calendar, GitBranch, CandlestickChart, Play, Square, HeartPulse, Database, Gauge, TrendingDown, AlertTriangle } from "lucide-react";
import { Panel, KpiCard, MetricTile, ProgressBar, LargeSparkline, Button, EventList, dollars, money } from "../components/Common";
import { useData } from "../data/DataContext";

export default function DashboardScreen({ data, selectedSymbol }) {
  const { dispatch } = useData();
  const [botBusy, setBotBusy] = useState(false);
  const account = data?.trading?.account || {};
  const risk = data?.trading?.risk || {};
  const lanes = data?.trading?.lanes || [];
  const positions = account.positions || [];
  const training = data?.training || {};
  const review = data?.tradeReview || {};
  const economicCalendar = data?.economicCalendar || [];
  const incidents = data?.incidents || [];
  const timeline = data?.timeline || [];
  const equityHistory = data?._history?.equity || [];
  const controls = data?.controls || {};
  const health = data?.health || {};
  const backup = data?.backup || {};
  const reversal = data?.reversal || {};
  const speed = data?.speed || {};
  const botRunning = controls.runtimeStatus === "running" || controls.botPid;
  const botPid = controls.botPid;

  async function handleBotToggle() {
    setBotBusy(true);
    try {
      const action = botRunning ? "stop_bot" : "start_bot";
      await dispatch(action);
    } finally {
      setBotBusy(false);
    }
  }

  return (
    <div className="stack animate-in">
      {/* Hero Monitor */}
      <section className="hero-monitor">
        <div>
          <div className="hero-monitor-label">Total Account Equity</div>
          <div className="hero-monitor-value">{dollars(account.equity)}</div>
          <div className="status-lamps">
            <div className="status-lamp"><div className={`lamp-dot ${botRunning ? "active" : ""}`} /><span>{botRunning ? "Bot Live" : "Bot Stopped"}</span></div>
            <div className="status-lamp"><div className="lamp-dot pass" /><span>Data Stream</span></div>
            <div className="status-lamp"><div className="lamp-dot" /><span>Risk Shields</span></div>
            <div className="status-lamp"><div className={`lamp-dot ${health?.status === "ok" ? "pass" : ""}`} /><span>{health?.status === "ok" ? "System Healthy" : "Health Check"}</span></div>
          </div>
          <div style={{ marginTop: 12, display: "flex", gap: 8, alignItems: "center" }}>
            <Button
              icon={botRunning ? Square : Play}
              tone={botRunning ? "danger" : "primary"}
              onClick={handleBotToggle}
              disabled={botBusy}
            >
              {botBusy ? (botRunning ? "Stopping..." : "Starting...") : (botRunning ? "Stop Bot" : "Start Bot")}
            </Button>
            {botPid && <span style={{ fontFamily: "var(--mono)", fontSize: "0.72rem", color: "var(--text-muted)" }}>PID {botPid}</span>}
          </div>
        </div>
        <div className="hero-monitor-side">
          <div>
            <div className="secondary-label">Balance</div>
            <div className="secondary-value">{dollars(account.balance)}</div>
          </div>
          <div>
            <div className="secondary-label">Floating PnL</div>
            <div className={`secondary-value ${account.floatingPnl >= 0 ? "text-pass" : "text-fail"}`}>
              {money(account.floatingPnl)}
            </div>
          </div>
          <div>
            <div className="secondary-label">Realized Today</div>
            <div className={`secondary-value ${account.realizedToday >= 0 ? "text-pass" : "text-fail"}`}>{money(account.realizedToday)}</div>
          </div>
          <div>
            <div className="secondary-label">Positions</div>
            <div className="secondary-value">{account.openPositions}</div>
          </div>
        </div>
      </section>

      {/* KPI Strip */}
      <div className="kpi-strip">
        <KpiCard label="Equity" value={dollars(account.equity)} sub={`Float: ${money(account.floatingPnl)}`} tone={account.floatingPnl >= 0 ? "pass" : "fail"} />
        <KpiCard label="Balance" value={dollars(account.balance)} sub={`Free: ${dollars(account.freeMargin)}`} />
        <KpiCard label="Positions" value={String(account.openPositions)} sub={`Today: ${money(account.realizedToday)}`} />
        <KpiCard label="Risk" value={risk.canTrade ? "ACTIVE" : "BLOCKED"} sub={`DD: ${(risk.drawdownPct || 0).toFixed(1)}%`} tone={risk.canTrade ? "pass" : "warn"} />
        <KpiCard label="Win Rate" value={`${review.winRate || 0}%`} sub={`${review.wins || 0}W / ${review.losses || 0}L`} tone={(review.winRate || 0) >= 50 ? "pass" : "warn"} />
        <KpiCard label="Profit Factor" value={String(review.profitFactor || 0)} sub={`PnL: ${dollars(review.totalPnl || 0)}`} tone={(review.profitFactor || 0) >= 1 ? "pass" : "fail"} />
      </div>

      <div className="grid-wide">
        {/* Left column */}
        <div className="stack">
          {/* Equity Curve */}
          <Panel title="Equity Curve" subtitle="Real-time account value" icon={Activity}>
            <LargeSparkline data={equityHistory} height={180} />
          </Panel>

          {/* Symbol Lanes */}
          <Panel title="Symbol Lanes" subtitle="Active trading lanes" icon={TrendingUp}>
            {lanes.length === 0 ? (
              <div className="empty-state">No active lanes</div>
            ) : (
              <div className="lane-grid" style={{ gap: 12 }}>
                {lanes.map((lane) => (
                  <div className={`lane-card ${lane.status === "live" ? "live" : "watching"}`} key={lane.symbol}>
                    <div className="lane-top">
                      <div>
                        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                          <span className="lane-symbol">{lane.symbol}</span>
                          <span className={`lane-chip ${lane.side === "buy" ? "tone-pass" : lane.side === "sell" ? "tone-warn" : ""}`}>
                            {lane.side} {(Math.abs(lane.exposure) * 100).toFixed(0)}%
                          </span>
                        </div>
                        <div style={{ color: "var(--text-muted)", fontSize: "0.78rem", marginTop: 4 }}>
                          {lane.champion} · conf {(lane.confidence * 100).toFixed(1)}%
                        </div>
                      </div>
                      <div style={{ textAlign: "right" }}>
                        <div style={{ fontWeight: 700, fontSize: "1.1rem" }}>
                          {String(lane.status || "watching").toUpperCase()}
                        </div>
                      </div>
                    </div>
                    {lane.reason && <div className="lane-reason">{lane.reason}</div>}
                  </div>
                ))}
              </div>
            )}
          </Panel>

          {/* Open Positions */}
          <Panel title="Open Positions" subtitle={`${account.openPositions} active`} icon={CandlestickChart}>
            {positions.length === 0 ? (
              <div className="empty-state">No open positions</div>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {positions.map((pos) => (
                  <div key={pos.ticket} style={{
                    padding: 12, borderRadius: 10, border: "1px solid rgba(255,255,255,0.06)",
                    background: "rgba(255,255,255,0.02)", display: "flex",
                    justifyContent: "space-between", alignItems: "center",
                  }}>
                    <div>
                      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                        <span className="lane-symbol">{pos.symbol}</span>
                        <span className={`lane-chip ${pos.type === "buy" ? "tone-pass" : "tone-warn"}`}>
                          {pos.type.toUpperCase()}
                        </span>
                        <span style={{ color: "var(--text-muted)", fontFamily: "var(--mono)", fontSize: "0.75rem" }}>
                          {pos.volume} lots
                        </span>
                      </div>
                      <div style={{ color: "var(--text-muted)", fontSize: "0.75rem", marginTop: 2, fontFamily: "var(--mono)" }}>
                        #{pos.ticket} @ {dollars(pos.openPrice)}
                      </div>
                    </div>
                    <div style={{ textAlign: "right" }}>
                      <div style={{
                        color: pos.profit >= 0 ? "var(--accent-green)" : "var(--accent-red)",
                        fontWeight: 700, fontSize: "1.05rem",
                      }}>
                        {money(pos.profit)}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Panel>
        </div>

        {/* Right column */}
        <div className="stack">
          {/* Training Status */}
          <Panel title="Training Engine" subtitle="Neural model status" icon={Brain}>
            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              <div>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
                  <span style={{ fontSize: "0.85rem", fontWeight: 600 }}>LSTM Context</span>
                  <span className={`training-stage-badge ${training.lstm?.state === "idle" ? "idle" : "active"}`}>
                    {training.lstm?.state || "idle"}
                  </span>
                </div>
                <ProgressBar label="Memory" value={training.lstm?.memoryStrength || 0} tone="pass" meta={`${training.lstm?.featuresUsed || 0} feat`} />
              </div>
              <div>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
                  <span style={{ fontSize: "0.85rem", fontWeight: 600 }}>PPO Execution</span>
                  <span className={`training-stage-badge ${training.ppo?.state === "training" ? "active" : training.ppo?.state === "idle" ? "idle" : ""}`}>
                    {training.ppo?.state || "idle"}
                  </span>
                </div>
                <ProgressBar label="Progress" value={training.ppo?.progress || 0} meta={`${(training.ppo?.currentTimesteps || 0).toLocaleString()} ts`} />
              </div>
              <div>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
                  <span style={{ fontSize: "0.85rem", fontWeight: 600 }}>DreamerV3</span>
                  <span className={`training-stage-badge ${training.dreamerV3?.state === "idle" ? "idle" : "active"}`}>
                    {training.dreamerV3?.state || "idle"}
                  </span>
                </div>
                <ProgressBar label="Alignment" value={training.dreamerV3?.alignment || 0} meta={`${(training.dreamerV3?.steps || 0).toLocaleString()} steps`} />
              </div>
            </div>
          </Panel>

          {/* Safety & Guardrails */}
          <Panel title="Safety & Guardrails" subtitle="Risk mitigation status" icon={Shield}>
            <div className="metric-grid" style={{ gridTemplateColumns: "repeat(2, 1fr)" }}>
              <MetricTile label="Drawdown" value={`${(risk.drawdownPct || 0).toFixed(1)}%`} tone={(risk.drawdownPct || 0) > 5 ? "warn" : "pass"} />
              <MetricTile label="Daily Cap" value={`${risk.maxDailyLossPct || 3}%`} />
              <MetricTile label="Kill Switch" value={risk.killSwitchArmed ? "ARMED" : "Safe"} tone={risk.killSwitchArmed ? "warn" : "pass"} />
              <MetricTile label="Size Cap" value={`${((risk.sizeCap || 0) * 100).toFixed(0)}%`} />
            </div>
          </Panel>

          {/* System Health */}
          <Panel title="System Health" subtitle="Component status & uptime" icon={HeartPulse}>
            <div className="metric-grid" style={{ gridTemplateColumns: "repeat(2, 1fr)" }}>
              <MetricTile label="Status" value={health?.status === "ok" ? "ONLINE" : health?.status || "Unknown"} tone={health?.status === "ok" ? "pass" : "warn"} />
              <MetricTile label="Uptime" value={`${Math.floor((health?.uptime_seconds || 0) / 3600)}h ${Math.floor(((health?.uptime_seconds || 0) % 3600) / 60)}m`} />
              <MetricTile label="Risk Engine" value={health?.checks?.risk_engine ? "OK" : "FAIL"} tone={health?.checks?.risk_engine ? "pass" : "fail"} />
              <MetricTile label="Brain" value={health?.checks?.brain_initialized ? "OK" : "FAIL"} tone={health?.checks?.brain_initialized ? "pass" : "fail"} />
            </div>
            {(health?.checks?.server_running || health?.checks?.model_registry || health?.checks?.config_loaded) > (
              <div style={{ marginTop: 12, display: "flex", gap: 8, flexWrap: "wrap" }}>
                {health?.checks?.server_running && <span className="lane-chip tone-pass">Server OK</span>}
                {health?.checks?.model_registry && <span className="lane-chip tone-pass">Registry OK</span>}
                {health?.checks?.config_loaded && <span className="lane-chip tone-pass">Config OK</span>}
              </div>
            )}
          </Panel>

          {/* Backup Status */}
          <Panel title="Backup Manager" subtitle="Automated backup status" icon={Database}>
            <div className="metric-grid" style={{ gridTemplateColumns: "repeat(2, 1fr)" }}>
              <MetricTile label="Backups" value={String(backup?.count || 0)} />
              <MetricTile label="Latest" value={backup?.latest ? new Date(backup.latest).toLocaleDateString() : "None"} />
              <MetricTile label="Auto-Backup" value={backup?.auto_enabled ? "ENABLED" : "DISABLED"} tone={backup?.auto_enabled ? "pass" : "warn"} />
              <MetricTile label="Retention" value={`${backup?.max_backups || 7} days`} />
            </div>
            {backup?.latest_size_mb && (
              <div style={{ marginTop: 8, fontSize: "0.75rem", color: "var(--text-muted)" }}>
                Latest backup size: {backup.latest_size_mb} MB
              </div>
            )}
          </Panel>

          {/* Reversal Detection & Speed Simulator */}
          <Panel title="Advanced Systems" subtitle="Reversal detection & execution speed" icon={Gauge}>
            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <TrendingDown size={16} style={{ color: "var(--accent-purple)" }} />
                  <span style={{ fontSize: "0.85rem", fontWeight: 600 }}>Reversal Detector</span>
                </div>
                <span className={`lane-chip ${reversal?.enabled ? "tone-pass" : ""}`}>
                  {reversal?.enabled ? "ACTIVE" : "STANDBY"}
                </span>
              </div>
              {reversal?.enabled && (
                <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", paddingLeft: 24 }}>
                  5-method confirmation • Auto-flip enabled • Divergence + Exhaustion + S/R breaks
                </div>
              )}
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginTop: 4 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <Gauge size={16} style={{ color: "var(--accent-cyan)" }} />
                  <span style={{ fontSize: "0.85rem", fontWeight: 600 }}>Speed Simulator</span>
                </div>
                <span className={`lane-chip ${speed?.enabled ? "tone-pass" : ""}`}>
                  {speed?.enabled ? "ACTIVE" : "STANDBY"}
                </span>
              </div>
              {speed?.enabled && (
                <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", paddingLeft: 24 }}>
                  Profile: {speed?.network_profile || "excellent"} • Latency: {speed?.avg_latency_ms || "~50"}ms • Slippage sim active
                </div>
              )}
            </div>
          </Panel>

          {/* Incidents */}
          <Panel title="Incidents" subtitle="Recent activity and warnings" icon={Zap}>
            <EventList items={incidents} empty="No active incidents." />
          </Panel>

          {/* Economic Calendar Preview */}
          {economicCalendar.length > 0 && (
            <Panel title="Upcoming Events" subtitle="High-impact market events" icon={Calendar}>
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                {economicCalendar.filter(e => e.importance >= 2).slice(0, 4).map((event, i) => {
                  const formattedTime = event.time
                    ? new Date(event.time).toLocaleDateString([], { month: "short", day: "numeric" }) + " " + new Date(event.time).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
                    : "";
                  return (
                    <div key={i} style={{
                      display: "flex", alignItems: "center", justifyContent: "space-between",
                      padding: "8px 12px", borderRadius: 8, border: "1px solid rgba(255,123,143,0.1)",
                      background: "rgba(255,255,255,0.02)",
                    }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                        <span style={{ fontFamily: "var(--mono)", fontSize: "0.7rem", fontWeight: 700, color: "var(--text-muted)", width: 30 }}>
                          {event.currency || "?"}
                        </span>
                        <span style={{ fontSize: "0.85rem", fontWeight: 500 }}>{event.name}</span>
                      </div>
                      <span style={{ fontFamily: "var(--mono)", fontSize: "0.72rem", color: "var(--text-muted)" }}>
                        {formattedTime}
                      </span>
                    </div>
                  );
                })}
              </div>
            </Panel>
          )}
        </div>
      </div>
    </div>
  );
}