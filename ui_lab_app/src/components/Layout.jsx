import React from "react";
import {
  LayoutDashboard, TrendingUp, GraduationCap, Brain, Clock, Settings, Shield, Info,
} from "lucide-react";
import { useData } from "../data/DataContext";

const NAV_ITEMS = [
  { key: "dashboard", label: "Dashboard", icon: LayoutDashboard },
  { key: "trading", label: "Trading", icon: TrendingUp },
  { key: "training", label: "Training", icon: GraduationCap },
  { key: "models", label: "Models", icon: Brain },
  { key: "history", label: "History", icon: Clock },
  { key: "strategies", label: "Strategies", icon: Shield },
  { key: "control", label: "Control", icon: Settings },
  { key: "about", label: "About", icon: Info },
];

const MOBILE_TABS = ["dashboard", "trading", "training", "models", "control"];

function dollars(v) { const n = Number(v || 0); return `$${Math.abs(n).toFixed(2)}`; }

export default function Layout({ screen, onNavigate, selectedSymbol, onSelectSymbol, data, children }) {
  const { error } = useData();
  const account = data?.trading?.account || {};
  const lanes = data?.trading?.lanes || [];

  return (
    <div className="app-layout">
      {/* ── Sidebar (desktop) ── */}
      <aside className="sidebar">
        <div className="sidebar-brand">
          <img src="/app_icon.ico" alt="CG" />
          <span className="sidebar-brand-text">Money Printer</span>
        </div>

        <nav className="sidebar-nav">
          {NAV_ITEMS.map((item) => {
            const Icon = item.icon;
            return (
              <button
                key={item.key}
                className={`nav-item ${screen === item.key ? "active" : ""}`}
                onClick={() => onNavigate(item.key)}
              >
                <Icon size={16} />
                <span>{item.label}</span>
              </button>
            );
          })}
        </nav>

        <div className="sidebar-section">
          <div className="sidebar-section-title">Symbol Lanes</div>
          <div className="symbol-pills">
            {lanes.map((lane) => (
              <button
                key={lane.symbol}
                className={`symbol-pill ${selectedSymbol === lane.symbol ? "active" : ""}`}
                onClick={() => onSelectSymbol(lane.symbol)}
              >
                <span>{lane.symbol}</span>
                <span style={{ fontFamily: "var(--mono)", fontSize: "0.7rem", color: "var(--text-muted)" }}>
                  {String(lane.status || "watching").toUpperCase()}
                </span>
              </button>
            ))}
          </div>
        </div>

        <div className="sidebar-section">
          <div className="sidebar-section-title">Quick Stats</div>
          <div className="sidebar-quick-stats">
            <div className="stat-row">
              <span className="stat-row-label">Equity</span>
              <span className="stat-row-value text-pass">{dollars(account.equity)}</span>
            </div>
            <div className="stat-row">
              <span className="stat-row-label">PnL</span>
              <span className={`stat-row-value ${account.floatingPnl >= 0 ? "text-pass" : "text-fail"}`}>
                {account.floatingPnl >= 0 ? "+" : ""}{dollars(account.floatingPnl)}
              </span>
            </div>
            <div className="stat-row">
              <span className="stat-row-label">Positions</span>
              <span className="stat-row-value">{account.openPositions}</span>
            </div>
          </div>
        </div>

        {error && (
          <div className="note" style={{ borderColor: "rgba(255,123,143,0.3)", color: "var(--accent-red)" }}>
            Connection issue: {error}
          </div>
        )}
      </aside>

      {/* ── Main Content ── */}
      <main className="main-content">
        {children}
      </main>

      {/* ── Bottom Tab Bar (mobile) ── */}
      <div className="bottom-tab-bar">
        {MOBILE_TABS.map((key) => {
          const item = NAV_ITEMS.find((n) => n.key === key);
          const Icon = item.icon;
          return (
            <button
              key={key}
              className={`tab-btn ${screen === key ? "active" : ""}`}
              onClick={() => onNavigate(key)}
            >
              <Icon size={20} />
              <span>{item.label}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}