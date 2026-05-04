import React, { useState } from "react";
import { Play, RefreshCcw, Shield, Wrench, Activity, Database, HeartPulse, Download, RotateCcw } from "lucide-react";
import { Panel, MetricTile, Button } from "../components/Common";
import { useData } from "../data/DataContext";

export default function ControlScreen({ data }) {
  const { dispatch, actionResult } = useData();
  const [busyAction, setBusyAction] = useState(null);
  const [symbol, setSymbol] = useState("BTCUSDm");
  const [backupBusy, setBackupBusy] = useState(false);
  const [backupResult, setBackupResult] = useState(null);

  const controls = data?.controls || {};
  const processes = controls.processes || [];
  const availableActions = controls.availableActions || [];
  const registry = data?.registry || {};
  const health = data?.health || {};
  const backup = data?.backup || {};

  async function runAction(action) {
    setBusyAction(action);
    try {
      await dispatch(action, { symbol });
    } finally {
      setBusyAction(null);
    }
  }

  async function createBackup() {
    setBackupBusy(true);
    setBackupResult(null);
    try {
      const res = await fetch("/api/backup/create", { method: "POST" });
      const result = await res.json();
      setBackupResult({ ok: res.ok, ...result });
    } catch (e) {
      setBackupResult({ ok: false, error: e.message });
    } finally {
      setBackupBusy(false);
    }
  }

  return (
    <div className="stack animate-in">
      {/* Action Result Banner */}
      {actionResult && (
        <div className={`event-card ${actionResult.ok ? "tone-pass" : "tone-fail"}`} style={{ marginBottom: 8 }}>
          <div className="event-top">
            <span className="event-title">{actionResult.action}</span>
            <span className="event-chip">{actionResult.ok ? "SUCCESS" : "FAILED"}</span>
          </div>
          <div className="event-body">{actionResult.message}</div>
        </div>
      )}

      <div className="grid-2" style={{ gap: 16 }}>
        {/* Runtime Processes */}
        <Panel title="Runtime Processes" subtitle="Active system processes" icon={Wrench}>
          {processes.length === 0 ? (
            <div className="empty-state">No processes detected</div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {processes.map((process) => (
                <div className="process-row" key={`${process.name}-${process.pid}`}>
                  <div>
                    <div style={{ fontWeight: 600, fontSize: "0.88rem" }}>{process.name}</div>
                    <div style={{ color: "var(--text-muted)", fontSize: "0.72rem", fontFamily: "var(--mono)" }}>PID {process.pid}</div>
                  </div>
                  <span className={`process-chip ${process.status}`}>{process.status}</span>
                </div>
              ))}
            </div>
          )}
        </Panel>

        {/* Control Actions */}
        <Panel title="Control Actions" subtitle="Operator commands" icon={RefreshCcw}>
          <div style={{ marginBottom: 12 }}>
            <label style={{ display: "block", fontSize: "0.78rem", color: "var(--text-muted)", marginBottom: 6, fontFamily: "var(--mono)", textTransform: "uppercase", letterSpacing: "0.1em" }}>
              Target Symbol
            </label>
            <input
              id="symbol"
              value={symbol}
              onChange={(e) => setSymbol(e.target.value)}
              style={{
                padding: "10px 12px", borderRadius: 8, border: "1px solid var(--border)",
                background: "rgba(255,255,255,0.02)", color: "var(--text-primary)",
                width: "100%", fontFamily: "var(--mono)", fontSize: "0.88rem",
              }}
            />
          </div>
          <div className="action-grid">
            {availableActions.map((action) => (
              <button
                key={action}
                className={`action-btn ${busyAction === action ? "busy" : ""}`}
                onClick={() => runAction(action)}
                disabled={busyAction !== null}
              >
                <span>{action}</span>
                <span style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>
                  {busyAction === action ? "running..." : "ready"}
                </span>
              </button>
            ))}
          </div>
        </Panel>
      </div>

      <div className="grid-2" style={{ gap: 16 }}>
        {/* Registry */}
        <Panel title="Registry Authority" subtitle="Model promotion and gate status" icon={Shield}>
          <div className="metric-grid" style={{ gridTemplateColumns: "repeat(2, 1fr)" }}>
            <MetricTile label="Champion" value={registry.champion?.id || "unknown"} tone="pass" />
            <MetricTile label="Canary" value={registry.canary?.id || "none"} tone={registry.canary?.id && registry.canary.id !== "none" ? "warn" : ""} />
            <MetricTile label="Gate Ready" value={registry.gate?.ready ? "yes" : "no"} tone={registry.gate?.ready ? "pass" : "warn"} />
            <MetricTile label="Reason" value={registry.gate?.reason || "N/A"} />
          </div>
          {(registry.lineage || []).length > 0 && (
            <div style={{ marginTop: 16, display: "flex", flexDirection: "column", gap: 8 }}>
              <div className="eyebrow" style={{ marginBottom: 4 }}>Lineage</div>
              {registry.lineage.map((entry, i) => (
                <div className="lineage-row" key={`${entry.id}-${i}`}>
                  <div>
                    <div style={{ fontWeight: 600, fontSize: "0.88rem" }}>{entry.id}</div>
                    <div style={{ color: "var(--text-muted)", fontSize: "0.72rem" }}>from {entry.from}</div>
                  </div>
                  <div style={{ textAlign: "right" }}>
                    <div style={{ fontSize: "0.82rem" }}>{entry.when}</div>
                    <div style={{ color: "var(--text-muted)", fontSize: "0.72rem" }}>{entry.reason}</div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </Panel>

        {/* Guardrails */}
        <Panel title="Guardrails" subtitle="System safety boundaries" icon={Activity}>
          <div className="metric-grid" style={{ gridTemplateColumns: "repeat(2, 1fr)" }}>
            <MetricTile label="Runtime Status" value={controls.runtimeStatus || "unknown"} tone={controls.runtimeStatus === "running" ? "pass" : "warn"} />
            <MetricTile label="Notifications" value={controls.notifications || "N/A"} />
            <MetricTile label="Feature Version" value={data?.meta?.featureVersion || "N/A"} />
            <MetricTile label="Dreamer Stack" value={data?.meta?.dreamerVersion || "N/A"} />
          </div>
          <div className="note" style={{ marginTop: 16 }}>
            This screen is the operator surface for process control, promotion actions, and guarded mutation paths.
            Keep this screen isolated from the guided journey.
          </div>
        </Panel>
      </div>

      {/* System Health & Backup */}
      <div className="grid-2" style={{ gap: 16 }}>
        <Panel title="System Health" subtitle="Component status checks" icon={HeartPulse}>
          <div className="metric-grid" style={{ gridTemplateColumns: "repeat(2, 1fr)" }}>
            <MetricTile label="Status" value={health?.status === "ok" ? "ONLINE" : health?.status || "Unknown"} tone={health?.status === "ok" ? "pass" : "warn"} />
            <MetricTile label="Uptime" value={`${Math.floor((health?.uptime_seconds || 0) / 3600)}h ${Math.floor(((health?.uptime_seconds || 0) % 3600) / 60)}m`} />
            <MetricTile label="Server" value={health?.checks?.server_running ? "OK" : "FAIL"} tone={health?.checks?.server_running ? "pass" : "fail"} />
            <MetricTile label="Risk Engine" value={health?.checks?.risk_engine ? "OK" : "FAIL"} tone={health?.checks?.risk_engine ? "pass" : "fail"} />
            <MetricTile label="Brain" value={health?.checks?.brain_initialized ? "OK" : "FAIL"} tone={health?.checks?.brain_initialized ? "pass" : "fail"} />
            <MetricTile label="Registry" value={health?.checks?.model_registry ? "OK" : "FAIL"} tone={health?.checks?.model_registry ? "pass" : "fail"} />
          </div>
        </Panel>

        <Panel title="Backup Manager" subtitle="Data protection and recovery" icon={Database}>
          <div className="metric-grid" style={{ gridTemplateColumns: "repeat(2, 1fr)" }}>
            <MetricTile label="Backups" value={String(backup?.count || 0)} />
            <MetricTile label="Latest" value={backup?.latest ? new Date(backup.latest).toLocaleDateString() : "None"} />
            <MetricTile label="Retention" value={`${backup?.max_backups || 7} days`} />
            <MetricTile label="Auto" value={backup?.auto_enabled ? "ENABLED" : "DISABLED"} tone={backup?.auto_enabled ? "pass" : "warn"} />
          </div>
          {backupResult && (
            <div className={`event-card ${backupResult.ok ? "tone-pass" : "tone-fail"}`} style={{ marginTop: 12 }}>
              <div className="event-top">
                <span className="event-title">Backup {backupResult.ok ? "Created" : "Failed"}</span>
                <span className="event-chip">{backupResult.ok ? "SUCCESS" : "FAILED"}</span>
              </div>
              <div className="event-body">{backupResult.path || backupResult.error || "Backup operation completed"}</div>
            </div>
          )}
          <div style={{ marginTop: 12 }}>
            <Button icon={backupBusy ? RotateCcw : Download} onClick={createBackup} disabled={backupBusy}>
              {backupBusy ? "Creating..." : "Create Backup Now"}
            </Button>
          </div>
        </Panel>
      </div>
    </div>
  );
}