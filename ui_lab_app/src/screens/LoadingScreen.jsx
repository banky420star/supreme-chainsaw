import React, { useEffect, useState, useRef } from "react";
import {
  CheckCircle2, XCircle, Loader2, AlertTriangle,
  Activity, Shield, Cpu, Brain, Database,
  GitBranch, Rocket, TrendingUp, Radio, Server,
} from "lucide-react";

const API_BASE = "/api";

async function fetchJSON(path, fallback = null) {
  try {
    const res = await fetch(`${API_BASE}${path}`, { cache: "no-store" });
    if (!res.ok) return fallback;
    return await res.json();
  } catch {
    return fallback;
  }
}

const CHECKS = [
  {
    id: "api",
    label: "API Server",
    icon: Server,
    check: async () => {
      const data = await fetchJSON("/health", null);
      const ok = !!data;
      return { ok, detail: ok ? "Online" : "No response" };
    },
  },
  {
    id: "data",
    label: "Data Feed",
    icon: Database,
    check: async () => {
      const data = await fetchJSON("/status", null);
      const mode = data?.account?.mode;
      const isDemo = mode === "demo" || mode === "mt5_demo";
      const ok = data?.account?.connected || mode === "paper" || mode === "live" || isDemo;
      return { ok, detail: mode === "paper" ? "Paper mode" : (isDemo ? "Demo feed" : (mode === "live" ? "Live feed" : (ok ? "Connected" : "No data"))) };
    },
  },
  {
    id: "brain",
    label: "AGI Brain",
    icon: Brain,
    check: async () => {
      const data = await fetchJSON("/status", null);
      const ok = data?.server?.running === true;
      return { ok, detail: ok ? "Loaded" : "Not loaded" };
    },
  },
  {
    id: "models",
    label: "Models",
    icon: Cpu,
    check: async () => {
      const data = await fetchJSON("/status", null);
      const champ = data?.active_models?.champion;
      const visual = data?.training?.visual || {};
      const hasDreamer = !!visual.dreamer;
      const hasPPO = !!visual.ppo;
      const hasLSTM = !!visual.lstm;
      const ok = champ !== "none" && champ !== null || hasDreamer || hasPPO || hasLSTM;
      return { ok, detail: ok ? "Ready" : "Loading" };
    },
  },
  {
    id: "training",
    label: "Training",
    icon: Activity,
    check: async () => {
      const data = await fetchJSON("/status", null);
      const symbols = data?.training?.configured_symbols || [];
      const ok = symbols.length > 0;
      return { ok, detail: ok ? `${symbols.length} symbols` : "No symbols" };
    },
  },
  {
    id: "risk",
    label: "Risk Engine",
    icon: Shield,
    check: async () => {
      const data = await fetchJSON("/status", null);
      const risk = data?.risk || {};
      // Halted = fail, can_trade = ok, neither = warn (active but waiting)
      if (risk.halt) return { ok: false, detail: "Halted" };
      if (risk.can_trade) return { ok: true, detail: "Armed" };
      return { ok: false, detail: "Waiting" };
    },
  },
  {
    id: "pipeline",
    label: "Pipeline",
    icon: GitBranch,
    check: async () => {
      const data = await fetchJSON("/status", null);
      const summary = data?.training?.pipeline_summary || {};
      const total = summary.symbols_total || 0;
      const ok = total > 0;
      return { ok, detail: ok ? `${total} symbols` : "Initializing" };
    },
  },
  {
    id: "ready",
    label: "Ready to Trade",
    icon: Rocket,
    check: async () => {
      const data = await fetchJSON("/status", null);
      const risk = data?.risk || {};
      const hasSymbols = (data?.training?.configured_symbols || []).length > 0;
      const serverOk = data?.server?.running === true;
      const ok = serverOk && hasSymbols && !risk.halt;
      return { ok, detail: ok ? "GO" : "Waiting" };
    },
  },
];

function StatusIcon({ status }) {
  if (status === "ok") return <CheckCircle2 size={13} style={{ color: "var(--accent-green)" }} />;
  if (status === "fail") return <XCircle size={13} style={{ color: "var(--accent-red)" }} />;
  if (status === "warn") return <AlertTriangle size={13} style={{ color: "var(--accent-amber)" }} />;
  return <Loader2 size={13} style={{ color: "var(--accent-cyan)", animation: "spin 1s linear infinite" }} />;
}

export default function LoadingScreen({ onReady }) {
  const [checks, setChecks] = useState(
    CHECKS.map((c) => ({ id: c.id, label: c.label, status: "pending", detail: "...", icon: c.icon }))
  );
  const [done, setDone] = useState(false);
  const doneRef = useRef(false);
  const minSplashOver = useRef(false);

  const okCount = checks.filter((r) => r.status === "ok").length;
  const total = checks.length;
  const progress = done ? 100 : Math.min(90, (okCount / total) * 90);

  useEffect(() => {
    let cancelled = false;
    async function run() {
      for (let i = 0; i < CHECKS.length; i++) {
        if (cancelled) return;
        const def = CHECKS[i];
        setChecks((prev) => prev.map((r, idx) => (idx === i ? { ...r, status: "running", detail: "Checking..." } : r)));
        try {
          const result = await def.check();
          if (cancelled) return;
          setChecks((prev) => prev.map((r, idx) => (idx === i ? { ...r, status: result.ok ? "ok" : "fail", detail: result.detail } : r)));
        } catch (e) {
          setChecks((prev) => prev.map((r, idx) => (idx === i ? { ...r, status: "fail", detail: "Error" } : r)));
        }
        await new Promise((r) => setTimeout(r, 300));
      }
      setDone(true);
    }
    run();
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    const t = setTimeout(() => { minSplashOver.current = true; }, 2000);
    return () => clearTimeout(t);
  }, []);

  useEffect(() => {
    if (done && minSplashOver.current && !doneRef.current) {
      doneRef.current = true;
      const t = setTimeout(() => { if (onReady) onReady(); }, 600);
      return () => clearTimeout(t);
    }
  }, [done, onReady]);

  return (
    <div style={{
      position: "fixed", inset: 0, background: "var(--bg-base)",
      display: "flex", alignItems: "center", justifyContent: "center",
      fontFamily: "var(--display)", color: "var(--text-primary)", zIndex: 9999
    }}>
      <div style={{
        width: "100%", maxWidth: 360, padding: "0 24px", textAlign: "center"
      }}>
        <div style={{ marginBottom: 20 }}>
          <h1 style={{
            fontSize: "1rem", fontWeight: 700, letterSpacing: 2,
            textTransform: "uppercase", margin: 0
          }}>
            Chain Gambler
          </h1>
          <div style={{
            fontSize: "0.65rem", color: "var(--text-muted)", marginTop: 4,
            letterSpacing: 1, textTransform: "uppercase"
          }}>
            {done ? "System Online" : "Initializing..."}
          </div>
        </div>

        <div style={{
          background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.06)",
          borderRadius: 10, padding: "12px 16px", marginBottom: 16, textAlign: "left"
        }}>
          <div style={{
            display: "flex", justifyContent: "space-between", alignItems: "center",
            marginBottom: 8, fontSize: "0.6rem", fontWeight: 600,
            textTransform: "uppercase", letterSpacing: 1, color: "var(--text-muted)"
          }}>
            <span>Diagnostics</span>
            <span style={{ color: "var(--accent-cyan)" }}>{okCount}/{total}</span>
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: 1 }}>
            {checks.map((check) => {
              const Icon = check.icon;
              return (
                <div key={check.id} style={{
                  display: "flex", alignItems: "center", gap: 8,
                  padding: "4px 0", opacity: check.status === "pending" ? 0.4 : 1,
                  transition: "opacity 0.2s"
                }}>
                  <Icon size={12} style={{ color: "var(--text-muted)", minWidth: 14 }} />
                  <span style={{ flex: 1, fontSize: "0.75rem", color: "var(--text-secondary)" }}>
                    {check.label}
                  </span>
                  <span style={{ fontSize: "0.6rem", color: "var(--text-muted)", marginRight: 6 }}>
                    {check.detail}
                  </span>
                  <StatusIcon status={check.status} />
                </div>
              );
            })}
          </div>
        </div>

        <div style={{
          height: 3, borderRadius: 2, background: "rgba(255,255,255,0.05)", overflow: "hidden"
        }}>
          <div style={{
            height: "100%", borderRadius: 2,
            background: done ? "var(--accent-green)" : "var(--accent-cyan)",
            width: `${progress}%`, transition: "width 0.4s ease"
          }} />
        </div>
        <div style={{
          display: "flex", justifyContent: "space-between",
          marginTop: 6, fontSize: "0.6rem", color: "var(--text-muted)"
        }}>
          <span>{done ? "Ready" : "Checking..."}</span>
          <span>{Math.floor(progress)}%</span>
        </div>
      </div>
    </div>
  );
}
