import React, { createContext, useContext, useRef, useCallback, useState, useEffect } from "react";

const DataContext = createContext(null);

const API_BASE = "/api";

function normalizeLevel(raw) {
  const v = String(raw || "info").toLowerCase();
  if (v === "warning" || v === "warn") return "warn";
  if (v === "critical" || v === "error" || v === "fail") return "fail";
  if (v === "activity" || v === "success" || v === "pass") return "pass";
  return "info";
}

async function fetchJSON(path, fallback = null) {
  try {
    const res = await fetch(`${API_BASE}${path}`, { cache: "no-store" });
    if (!res.ok) return fallback;
    return await res.json();
  } catch {
    return fallback;
  }
}

function mapStatusToState(status, trades = [], tradeReview = null, learning = null, ppoDiag = null, lstmExpl = null, scenarios = null, perf = null, strategies = null, lanes = null) {
  const visual = status?.training?.visual || {};
  const ppo = visual.ppo || {};
  const lstm = visual.lstm || {};
  const dreamer = visual.dreamer || {};
  const account = status?.account || {};
  const risk = status?.risk || {};
  const laneRows = status?.training?.symbol_lane_rows || [];

  const incidents = (status?.incidents || []).slice(0, 10).map((inc) => ({
    level: normalizeLevel(inc.severity),
    title: inc.symbol || inc.type || inc.event || "incident",
    message: inc.message || inc.summary || inc.reason || JSON.stringify(inc.payload || {}),
  }));

  const timeline = [
    ...(status?.logs?.audit || []).slice(-3).map((line) => ({ level: "info", text: line })),
    ...(status?.logs?.ppo || []).slice(-2).map((line) => ({ level: "info", text: line })),
  ].slice(0, 8);

  const mappedLanes = laneRows.length > 0
    ? laneRows.map((row) => ({
        symbol: row.symbol,
        side: String(row.side || row.position_side || "flat").toLowerCase(),
        champion: row.champion || "unknown",
        reason: row.reason || row.decision?.regime || "runtime lane",
        confidence: Number(row.confidence || row.decision?.confidence || 0),
        exposure: Number(row.exposure || 0),
        pnl: Number(row.pnl || 0),
        status: row.status || "watching",
        canTrade: row.canTrade !== false,
      }))
    : (lanes?.lanes || []).map((l) => ({
        symbol: l.symbol,
        side: String(l.action || "hold").toLowerCase(),
        champion: l.champion || "unknown",
        reason: l.reason || "",
        confidence: Number(l.confidence || 0),
        exposure: Number(l.exposure || 0),
        pnl: 0,
        status: l.can_trade ? "live" : "watching",
        canTrade: l.can_trade !== false,
      }));

  const review = tradeReview || {};
  const tradeHistory = (trades?.trades || trades || []).slice(0, 30).map((t, i) => ({
    id: String(t.ticket || `T-${i}`),
    symbol: t.symbol || "UNKNOWN",
    type: (t.action_type || t.side || "trade").toLowerCase(),
    side: (t.side || "").toLowerCase(),
    pnl: Number(t.profit || 0),
    volume: Number(t.volume || 0),
    duration: t.hold_minutes ? `${Math.floor(t.hold_minutes / 60)}h ${t.hold_minutes % 60}m` : "unknown",
    reason: t.comment || "executed by champion model",
    timestamp: t.close_time || t.open_time || "recent",
    model: t.model || "champion",
    outcome: t.outcome || (Number(t.profit || 0) >= 0 ? "win" : "loss"),
  }));

  const processes = [];
  if (status?.server?.running) processes.push({ name: "Server runtime", pid: (status.server.pids || [])[0] || "-", status: "running" });
  if (status?.training?.lstm_running) processes.push({ name: "LSTM trainer", pid: (status.training.lstm_pids || [])[0] || "-", status: "running" });
  if (status?.training?.dreamer_running) processes.push({ name: "DreamerV3 trainer", pid: (status.training.dreamer_pids || [])[0] || "-", status: "running" });
  if (status?.training?.drl_running) processes.push({ name: "PPO trainer", pid: (status.training.drl_pids || [])[0] || "-", status: "running" });
  if (status?.training?.cycle_running) processes.push({ name: "Champion cycle", pid: (status.training.cycle_pids || [])[0] || "-", status: "running" });

  const configuredSymbols = status?.training?.configured_symbols || ["BTCUSDm", "XAUUSDm", "EURUSDm", "GBPUSDm"];

  return {
    meta: {
      appName: "Money Printer",
      featureVersion: "ultimate_150",
      dreamerVersion: "DreamerV3",
      transportMode: "live",
      isDemo: false,
    },
    connection: {
      status: "connected",
      transport: "backend",
      latencyMs: 0,
      lastSyncAt: Date.now(),
      stale: false,
    },
    orchestrator: {
      loopStatus: status?.state || "live",
      owner: status?.training?.cycle_running ? "champion_cycle" : "runtime",
      currentPhase: visual.active_key || visual.active_label || "policy",
      cycleProgress: Number(((ppo.progress_pct || 0) / 100).toFixed(2)),
      nextAction: status?.training?.cycle_running ? "run_cycle" : "runtime_watch",
      queueDepth: Number(status?.training?.pipeline_summary?.training_active_symbols || 0),
      loopIteration: 0,
      cooldownSec: 0,
    },
    training: {
      featureVersion: "ultimate_150",
      activePhase: visual.active_key || visual.active_label || "policy",
      configuredSymbols,
      lstm: {
        currentSymbol: status?.training?.lstm_symbol || lstm.current_symbol || "",
        epoch: Number(status?.training?.lstm_epoch || 0),
        epochsTotal: Number(status?.training?.lstm_epochs_total || 0),
        loss: Number(lstm.loss || 0),
        valLoss: Number(lstm.val_loss || 0),
        memoryStrength: Number(lstm.memory_strength || 0),
        featuresUsed: 150,
        state: lstm.state || "idle",
        queue: configuredSymbols,
      },
      ppo: {
        currentSymbol: ppo.current_symbol || status?.training?.drl_symbol || "",
        progress: Number(((ppo.progress_pct || 0) / 100).toFixed(2)),
        currentTimesteps: Number(ppo.current_timesteps || 0),
        targetTimesteps: Number(status?.training?.drl_timesteps || ppo.target_timesteps || 100000),
        state: ppo.state || "idle",
        progressPct: Number(ppo.progress_pct || 0),
        perSymbol: status?.training?.ppo_per_symbol || {},
      },
      dreamerV3: {
        enabled: Boolean(status?.training?.dreamer_running),
        currentSymbol: dreamer.current_symbol || "",
        progress: Number(((dreamer.progress_pct || 0) / 100).toFixed(2)),
        steps: Number(dreamer.steps || 0),
        window: Number(dreamer.window || 64),
        worldModelLoss: Number(dreamer.world_model_loss || 0),
        alignment: Number(dreamer.alignment || 0),
        state: dreamer.state || "idle",
      },
      pipeline: {
        trainingActiveSymbols: Number(status?.training?.pipeline_summary?.training_active_symbols || 0),
        canaryReviewSymbols: Number(status?.training?.pipeline_summary?.canary_review_symbols || 0),
        tradingReadySymbols: Number(status?.training?.pipeline_summary?.trading_ready_symbols || 0),
        tradingActiveSymbols: Number(status?.training?.pipeline_summary?.trading_active_symbols || 0),
      },
    },
    registry: {
      champion: {
        id: status?.active_models?.champion || "none",
        symbol: mappedLanes[0]?.symbol || "",
        featureVersion: "ultimate_150",
        verdict: "champion",
      },
      canary: {
        id: status?.active_models?.canary || "none",
        symbol: "",
        featureVersion: "ultimate_150",
        verdict: status?.active_models?.canary ? "canary" : "none",
        progress: 0,
      },
      perSymbolModels: status?.registry_summary?.per_symbol_models || {},
      gate: {
        ready: Boolean(status?.canary_gate?.ready),
        reason: status?.canary_gate?.reason || "min trades not yet reached",
      },
      candidates: [],
      lineage: [],
    },
    trading: {
      mode: (status?.mode || "DRY-RUN").toLowerCase() === "live" ? "active" : "armed",
      account: {
        connected: Boolean(account.connected ?? (account.balance > 0)),
        balance: Number(account.balance || 0),
        equity: Number(account.equity || 0),
        freeMargin: Number(account.free_margin || 0),
        floatingPnl: Number(account.profit || 0),
        realizedToday: Number(account.realized_today || 0),
        openPositions: Number(account.open_positions || 0),
        positions: (account.positions || []).map((p) => ({
          ticket: p.ticket,
          symbol: p.symbol,
          type: (p.type || "").toLowerCase(),
          volume: Number(p.volume || 0),
          openPrice: Number(p.open_price || 0),
          currentPrice: Number(p.current_price || 0),
          profit: Number(p.profit || 0),
          sl: Number(p.sl || 0),
          tp: Number(p.tp || 0),
          comment: p.comment || "",
          magic: p.magic || 0,
          openTime: p.open_time || "",
        })),
      },
      risk: {
        canTrade: risk.can_trade !== false && !Boolean(risk.halt),
        drawdownPct: Number(risk.current_dd || account.drawdown_pct || 0),
        dailyLossPct: Number(risk.daily_loss_pct || 0),
        maxDailyLossPct: Number(risk.max_daily_loss || risk.max_daily_loss_pct || 3),
        sizeCap: Number(risk.size_cap || 0.64),
        killSwitchArmed: true,
      },
      lanes: mappedLanes,
      tradeHistory,
    },
    selfImprove: {
      loopHealth: status?.state === "online" ? "stable" : "degraded",
      lastImprovementAction: `Runtime: ${status?.mode || "DRY-RUN"} mode`,
    },
    tradeReview: {
      totalTrades: Number(review.total_trades || 0),
      wins: Number(review.wins || 0),
      losses: Number(review.losses || 0),
      winRate: Number(review.win_rate || 0),
      totalPnl: Number(review.total_pnl || 0),
      avgWin: Number(review.avg_win || 0),
      avgLoss: Number(review.avg_loss || 0),
      profitFactor: Number(review.profit_factor || 0),
      slHits: Number(review.sl_hits || 0),
      tpHits: Number(review.tp_hits || 0),
      slRate: Number(review.sl_rate || 0),
      tpRate: Number(review.tp_rate || 0),
      tagDistribution: review.tag_distribution || {},
      bySymbol: review.by_symbol || {},
    },
    controls: {
      runtimeStatus: status?.server?.running ? "running" : "stopped",
      processes,
      availableActions: [
        "start_lstm",
        "start_dreamer",
        "start_drl",
        "run_cycle",
        "promote_canary",
        "rollback_champion",
        "restart_server",
      ],
      blockedReasons: [],
      notifications: "telegram+ui",
    },
    incidents,
    timeline,
    economicCalendar: status?.economic_calendar || [],
    learning: learning || {},
    ppoDiagnostics: ppoDiag || {},
    lstmExplanations: lstmExpl || [],
    scenarios: scenarios || {},
    perf: perf || { equity_curve: [], pnl_curve: [], confidence_curve: [], lstm_loss_curve: [] },
    strategies: strategies || { strategies: [], patterns: [], meta: {} },
    _tick: Date.now(),
  };
}

export function DataProvider({ children, pollMs = 3000 }) {
  const [state, setState] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [actionResult, setActionResult] = useState(null);
  const historyRef = useRef({ equity: [], pnl: [], confidence: [] });
  const cancelledRef = useRef(false);

  const poll = useCallback(async () => {
    try {
      const [status, trades, tradeReview, learning, ppoDiag, lstmExpl, scenarios, perf, strategies, lanes] = await Promise.all([
        fetchJSON("/status"),
        fetchJSON("/trades?limit=30"),
        fetchJSON("/trade_review"),
        fetchJSON("/learning"),
        fetchJSON("/ppo_diagnostics"),
        fetchJSON("/lstm_explanations"),
        fetchJSON("/scenarios"),
        fetchJSON("/perf"),
        fetchJSON("/strategies"),
        fetchJSON("/lanes"),
      ]);

      if (cancelledRef.current) return;

      // Core status must succeed — other endpoints are optional
      if (!status) {
        setError("Backend unreachable");
        setLoading(false);
        return;
      }

      let mapped;
      try {
        mapped = mapStatusToState(status, trades, tradeReview, learning, ppoDiag, lstmExpl, scenarios, perf, strategies, lanes);
      } catch (mapErr) {
        console.error("mapStatusToState error:", mapErr);
        // Build minimal state so the dashboard still renders
        const account = status?.account || {};
        const risk = status?.risk || {};
        mapped = {
          meta: { appName: "Money Printer", featureVersion: "ultimate_150" },
          connection: { status: "connected", transport: "backend" },
          trading: {
            mode: "active",
            account: {
              balance: Number(account.balance || 0), equity: Number(account.equity || 0),
              freeMargin: Number(account.free_margin || 0), floatingPnl: Number(account.profit || 0),
              realizedToday: Number(account.realized_today || 0), openPositions: Number(account.open_positions || 0),
              positions: (account.positions || []).map(p => ({
                ticket: p.ticket, symbol: p.symbol, type: (p.type || "").toLowerCase(),
                volume: Number(p.volume || 0), openPrice: Number(p.open_price || 0),
                currentPrice: Number(p.current_price || 0), profit: Number(p.profit || 0),
                sl: Number(p.sl || 0), tp: Number(p.tp || 0), comment: p.comment || "",
              })),
            },
            risk: {
              canTrade: risk.can_trade !== false && !risk.halt,
              drawdownPct: Number(risk.current_dd || 0), maxDailyLossPct: 3,
              dailyLossPct: 0, sizeCap: 0.64, killSwitchArmed: true,
            },
            lanes: [], tradeHistory: [],
          },
          tradeReview: { totalTrades: 0, wins: 0, losses: 0, winRate: 0, totalPnl: 0, profitFactor: 0, slHits: 0, tpHits: 0, slRate: 0, tpRate: 0, tagDistribution: {}, bySymbol: {} },
          training: { activePhase: "idle", configuredSymbols: [], lstm: { state: "idle" }, ppo: { state: "idle" }, dreamerV3: { state: "idle" } },
          registry: { champion: { id: "none" }, canary: { id: "none" }, gate: { ready: false, reason: "" } },
          incidents: [], timeline: [], controls: { runtimeStatus: "running", processes: [], availableActions: [] },
          _tick: Date.now(),
        };
      }

      const equity = Number(status?.account?.equity || 0);
      const pnl = Number(status?.account?.profit || 0);
      const laneConfs = (mapped.trading?.lanes || []).map((l) => l.confidence).filter(Boolean);
      const topConf = laneConfs.length > 0 ? Math.max(...laneConfs) : 0;

      const h = historyRef.current;
      h.equity.push(equity);
      h.pnl.push(pnl);
      h.confidence.push(topConf);
      if (h.equity.length > 300) { h.equity.shift(); h.pnl.shift(); h.confidence.shift(); }

      mapped._history = { equity: [...h.equity], pnl: [...h.pnl], confidence: [...h.confidence] };

      setState(mapped);
      setLoading(false);
      setError(null);
    } catch (err) {
      if (!cancelledRef.current) {
        setError(err.message || "Connection failed");
        setLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    cancelledRef.current = false;
    poll();
    const id = setInterval(poll, pollMs);
    return () => { cancelledRef.current = true; clearInterval(id); };
  }, [poll, pollMs]);

  const dispatch = useCallback(async (action, payload = {}) => {
    try {
      const res = await fetch(`${API_BASE}/control`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action, ...payload }),
      });
      const result = res.ok ? await res.json().catch(() => ({})) : {};
      setActionResult({ ok: res.ok, action, message: result.message || (res.ok ? "ok" : `failed: ${res.status}`), at: Date.now() });
      return result;
    } catch (err) {
      setActionResult({ ok: false, action, message: err.message, at: Date.now() });
      return { ok: false, message: err.message };
    }
  }, []);

  const refreshTradeReview = useCallback(async () => {
    try {
      await fetch(`${API_BASE}/trade_review/refresh`, { method: "POST", cache: "no-store" });
    } catch {}
  }, []);

  return (
    <DataContext.Provider value={{ data: state, loading, error, actionResult, dispatch, refreshTradeReview }}>
      {children}
    </DataContext.Provider>
  );
}

export function useData() {
  const ctx = useContext(DataContext);
  if (!ctx) throw new Error("useData must be used within DataProvider");
  return ctx;
}