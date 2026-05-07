/**
 * Training Metrics Dashboard Component
 *
 * Shows per-symbol profit, balance, drawdown, and timeframe optimization results
 * during and after training.
 */

import React, { useState, useEffect } from "react";
import { Activity, TrendingUp, TrendingDown, BarChart3, Clock, Target, Award, AlertTriangle } from "lucide-react";
import { Panel, MetricTile, ProgressBar, dollars, pct } from "../components/Common";

function useTrainingData() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const fetchTrainingMetrics = async () => {
      try {
        // Fetch from the training status endpoint
        const response = await fetch("/api/training/metrics");
        if (!response.ok) throw new Error("Failed to fetch training metrics");
        const json = await response.json();
        setData(json);
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };

    fetchTrainingMetrics();
    const interval = setInterval(fetchTrainingMetrics, 5000); // Poll every 5 seconds
    return () => clearInterval(interval);
  }, []);

  return { data, loading, error };
}

function TimeframeComparison({ results }) {
  if (!results || Object.keys(results).length === 0) return null;

  const timeframes = Object.entries(results).sort(
    (a, b) => (b[1].sharpe_ratio || 0) - (a[1].sharpe_ratio || 0)
  );

  const bestTf = timeframes[0];

  return (
    <div style={{ marginTop: 16 }}>
      <div className="eyebrow" style={{ marginBottom: 12 }}>
        <Clock size={13} /> Timeframe Optimization Results
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {timeframes.map(([tf, result]) => (
          <div
            key={tf}
            style={{
              padding: "10px 12px",
              borderRadius: 8,
              border: `1px solid ${tf === bestTf[0] ? "var(--accent-green)" : "var(--border)"}`,
              background: tf === bestTf[0] ? "rgba(57,217,138,0.06)" : "rgba(255,255,255,0.02)",
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <span
                style={{
                  fontFamily: "var(--mono)",
                  fontWeight: 700,
                  fontSize: "0.9rem",
                  color: tf === bestTf[0] ? "var(--accent-green)" : "var(--text-primary)",
                }}
              >
                {tf}
              </span>
              {tf === bestTf[0] && (
                <span
                  className="lane-chip tone-pass"
                  style={{ fontSize: "0.65rem" }}
                >
                  BEST
                </span>
              )}
            </div>
            <div style={{ display: "flex", gap: 16, fontSize: "0.78rem" }}>
              <span>
                Bars: <strong>{result.bars?.toLocaleString()}</strong>
              </span>
              <span>
                Sharpe: <strong style={{ color: result.sharpe_ratio > 0 ? "var(--accent-green)" : "var(--accent-red)" }}>
                  {result.sharpe_ratio?.toFixed(2)}
                </strong>
              </span>
              <span>
                ADX: <strong>{result.adx?.toFixed(1)}</strong>
              </span>
              <span>
                Quality: <strong>{pct(result.quality_score, 0)}</strong>
              </span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function SymbolMetricsCard({ symbol, metrics }) {
  if (!metrics) return null;

  const {
    initial_balance,
    current_balance,
    net_profit,
    return_pct,
    total_trades,
    win_rate,
    profit_factor,
    max_drawdown,
    max_drawdown_pct,
    volatility_regime,
  } = metrics;

  const isProfit = net_profit >= 0;
  const tone = isProfit ? "pass" : "fail";

  return (
    <div
      style={{
        padding: 16,
        borderRadius: 12,
        border: `1px solid ${isProfit ? "rgba(57,217,138,0.15)" : "rgba(255,123,143,0.15)"}`,
        background: "rgba(255,255,255,0.02)",
      }}
    >
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: 12,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <span style={{ fontWeight: 700, fontSize: "1.1rem" }}>{symbol}</span>
          <span
            className={`lane-chip ${volatility_regime === "HIGH_VOLATILITY" ? "tone-warn" : "tone-pass"}`}
            style={{ fontSize: "0.7rem" }}
          >
            {volatility_regime}
          </span>
        </div>
        <div
          style={{
            fontSize: "1.2rem",
            fontWeight: 700,
            color: isProfit ? "var(--accent-green)" : "var(--accent-red)",
          }}
        >
          {isProfit ? "+" : ""}
          {dollars(net_profit)}
        </div>
      </div>

      <div className="metric-grid" style={{ gridTemplateColumns: "repeat(2, 1fr)", gap: 8 }}>
        <MetricTile
          label="Initial Balance"
          value={dollars(initial_balance)}
        />
        <MetricTile
          label="Current Balance"
          value={dollars(current_balance)}
          tone={tone}
        />
        <MetricTile
          label="Return %"
          value={pct(return_pct / 100, 1)}
          tone={tone}
        />
        <MetricTile
          label="Total Trades"
          value={String(total_trades)}
        />
        <MetricTile
          label="Win Rate"
          value={pct(win_rate / 100, 1)}
          tone={win_rate >= 50 ? "pass" : "warn"}
        />
        <MetricTile
          label="Profit Factor"
          value={profit_factor?.toFixed(2) || "N/A"}
          tone={profit_factor >= 1.5 ? "pass" : profit_factor < 1 ? "fail" : "warn"}
        />
        <MetricTile
          label="Max Drawdown"
          value={dollars(max_drawdown)}
          tone={max_drawdown_pct > 20 ? "fail" : max_drawdown_pct > 10 ? "warn" : ""}
        />
        <MetricTile
          label="Drawdown %"
          value={pct(max_drawdown_pct / 100, 1)}
          tone={max_drawdown_pct > 20 ? "fail" : max_drawdown_pct > 10 ? "warn" : ""}
        />
      </div>

      {/* Equity curve mini chart */}
      {metrics.equity_curve && metrics.equity_curve.length > 1 && (
        <div style={{ marginTop: 12 }}>
          <div style={{ fontSize: "0.7rem", color: "var(--text-muted)", marginBottom: 4 }}>
            Equity Curve
          </div>
          <EquityCurveMini data={metrics.equity_curve} />
        </div>
      )}
    </div>
  );
}

function EquityCurveMini({ data }) {
  if (!data || data.length < 2) return null;

  const balances = data.map((d) => d.balance);
  const min = Math.min(...balances);
  const max = Math.max(...balances);
  const range = max - min || 1;

  const points = balances.map((b, i) => {
    const x = (i / (balances.length - 1)) * 100;
    const y = 30 - ((b - min) / range) * 25;
    return `${x},${y}`;
  });

  const isPositive = balances[balances.length - 1] >= balances[0];
  const color = isPositive ? "var(--accent-green)" : "var(--accent-red)";

  return (
    <svg width="100%" height="35" viewBox="0 0 100 30" style={{ overflow: "visible" }}>
      <polyline
        fill="none"
        stroke={color}
        strokeWidth="2"
        points={points.join(" ")}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function TrainingMetricsPanel({ symbols }) {
  const { data, loading, error } = useTrainingData();
  const [selectedSymbol, setSelectedSymbol] = useState(symbols?.[0] || null);

  if (loading) {
    return (
      <Panel title="Training Metrics" icon={Activity}>
        <div className="empty-state">Loading training metrics...</div>
      </Panel>
    );
  }

  if (error) {
    return (
      <Panel title="Training Metrics" icon={AlertTriangle}>
        <div className="empty-state" style={{ color: "var(--accent-red)" }}>
          Error loading metrics: {error}
        </div>
      </Panel>
    );
  }

  if (!data || !data.symbols || data.symbols.length === 0) {
    return (
      <Panel title="Training Metrics" icon={Activity}>
        <div className="empty-state">No training data available. Start training to see metrics.</div>
      </Panel>
    );
  }

  return (
    <div className="stack">
      {/* Summary Panel */}
      <Panel title="Training Performance Summary" subtitle="Per-symbol results" icon={BarChart3}>
        <div className="kpi-strip">
          <MetricTile
            label="Symbols Trained"
            value={String(data.symbols.length)}
          />
          <MetricTile
            label="Avg Return"
            value={pct(data.average_return / 100, 1)}
            tone={data.average_return >= 0 ? "pass" : "fail"}
          />
          <MetricTile
            label="Best Symbol"
            value={data.best_symbol || "N/A"}
            tone="pass"
          />
          <MetricTile
            label="Worst Drawdown"
            value={pct(data.max_drawdown / 100, 1)}
            tone={data.max_drawdown > 20 ? "fail" : data.max_drawdown > 10 ? "warn" : ""}
          />
        </div>
      </Panel>

      {/* Symbol Selector */}
      {symbols.length > 1 && (
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          {symbols.map((sym) => (
            <button
              key={sym}
              className={`btn btn-sm ${selectedSymbol === sym ? "btn-primary" : ""}`}
              onClick={() => setSelectedSymbol(sym)}
            >
              {sym}
            </button>
          ))}
        </div>
      )}

      {/* Per-Symbol Metrics */}
      {selectedSymbol && data.per_symbol_metrics?.[selectedSymbol] && (
        <Panel
          title={`${selectedSymbol} Metrics`}
          subtitle="Profit, balance, and drawdown tracking"
          icon={TrendingUp}
        >
          <SymbolMetricsCard
            symbol={selectedSymbol}
            metrics={data.per_symbol_metrics[selectedSymbol]}
          />
        </Panel>
      )}

      {/* Timeframe Optimization */}
      {selectedSymbol && data.timeframe_selections?.[selectedSymbol] && (
        <Panel
          title="Timeframe Optimization"
          subtitle="Multi-timeframe analysis results"
          icon={Clock}
        >
          <TimeframeComparison results={data.timeframe_selections[selectedSymbol].all_results} />
          <div style={{ marginTop: 16, padding: 12, background: "rgba(90,215,255,0.04)", borderRadius: 8 }}>
            <div style={{ fontSize: "0.78rem", color: "var(--text-secondary)", lineHeight: 1.5 }}>
              <strong>Selected Timeframe:</strong>{" "}
              {data.timeframe_selections[selectedSymbol].selected}
              <br />
              <strong>Selection Score:</strong>{" "}
              {data.timeframe_selections[selectedSymbol].selection_score?.toFixed(2)}
              <br />
              <em style={{ color: "var(--text-muted)", fontSize: "0.72rem" }}>
                Based on Sharpe ratio, data quality, ADX, and bar count
              </em>
            </div>
          </div>
        </Panel>
      )}

      {/* Training History */}
      {selectedSymbol && data.per_symbol_metrics?.[selectedSymbol]?.trade_history?.length > 0 && (
        <Panel title="Recent Trades" subtitle="Last 10 simulated trades" icon={Target}>
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {data.per_symbol_metrics[selectedSymbol].trade_history
              .slice(-10)
              .reverse()
              .map((trade, i) => (
                <div
                  key={i}
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    padding: "8px 12px",
                    borderRadius: 6,
                    background: "rgba(255,255,255,0.02)",
                    borderLeft: `3px solid ${trade.profit >= 0 ? "var(--accent-green)" : "var(--accent-red)"}`,
                  }}
                >
                  <div style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>
                    {new Date(trade.timestamp).toLocaleTimeString()}
                  </div>
                  <div
                    style={{
                      fontWeight: 600,
                      color: trade.profit >= 0 ? "var(--accent-green)" : "var(--accent-red)",
                    }}
                  >
                    {trade.profit >= 0 ? "+" : ""}
                    {dollars(trade.profit)}
                  </div>
                </div>
              ))}
          </div>
        </Panel>
      )}
    </div>
  );
}

// Standalone component for integration into TrainingScreen
export function EnhancedTrainingMetrics({ data }) {
  const trainingData = data?.training || {};
  const symbols = trainingData.configured_symbols || [];

  return (
    <div className="stack">
      <div className="eyebrow" style={{ marginBottom: 8 }}>
        <Award size={13} /> Enhanced Training Metrics
      </div>

      {symbols.length === 0 ? (
        <div className="empty-state">No training configured</div>
      ) : (
        <div className="grid-2" style={{ gap: 12 }}>
          {symbols.map((symbol) => (
            <div
              key={symbol}
              style={{
                padding: 14,
                borderRadius: 10,
                border: "1px solid var(--border)",
                background: "rgba(255,255,255,0.02)",
              }}
            >
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  marginBottom: 8,
                }}
              >
                <span style={{ fontWeight: 700 }}>{symbol}</span>
                <span className="lane-chip">
                  {trainingData.per_symbol_timeframe?.[symbol] || "M5"}
                </span>
              </div>

              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                <div
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    fontSize: "0.8rem",
                  }}
                >
                  <span style={{ color: "var(--text-muted)" }}>P&L:</span>
                  <span
                    style={{
                      color:
                        (trainingData.per_symbol_pnl?.[symbol] || 0) >= 0
                          ? "var(--accent-green)"
                          : "var(--accent-red)",
                    }}
                  >
                    {dollars(trainingData.per_symbol_pnl?.[symbol] || 0)}
                  </span>
                </div>
                <div
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    fontSize: "0.8rem",
                  }}
                >
                  <span style={{ color: "var(--text-muted)" }}>Drawdown:</span>
                  <span>
                    {pct((trainingData.per_symbol_drawdown?.[symbol] || 0) / 100, 1)}
                  </span>
                </div>
                <div
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    fontSize: "0.8rem",
                  }}
                >
                  <span style={{ color: "var(--text-muted)" }}>Trades:</span>
                  <span>{trainingData.per_symbol_trades?.[symbol] || 0}</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default TrainingMetricsPanel;
