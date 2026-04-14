import React from "react";

// ── Formatters ──

export function pct(value, digits = 0) {
  return `${(Number(value || 0) * 100).toFixed(digits)}%`;
}

export function money(value) {
  const n = Number(value || 0);
  return `${n >= 0 ? "+" : ""}${n.toFixed(2)}`;
}

export function dollars(value) {
  const n = Number(value || 0);
  return `$${Math.abs(n).toFixed(2)}`;
}

export function shortDuration(seconds) {
  const total = Math.max(0, Math.floor(Number(seconds || 0)));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m ${s}s`;
  return `${s}s`;
}

export function statusTone(level) {
  const v = String(level || "info").toLowerCase();
  if (v === "pass" || v === "good" || v === "ready" || v === "running" || v === "live") return "tone-pass";
  if (v === "warn" || v === "warning" || v === "holding") return "tone-warn";
  if (v === "fail" || v === "error" || v === "critical" || v === "stopped") return "tone-fail";
  return "";
}

// ── Panel ──

export function Panel({ title, subtitle, children, icon: Icon, right, className = "" }) {
  return (
    <section className={`panel ${className}`}>
      <div className="panel-head">
        <div>
          <div className="eyebrow">
            {Icon ? <Icon size={13} /> : null}
            <span>{title}</span>
          </div>
          {subtitle && <h2 className="panel-title">{subtitle}</h2>}
        </div>
        {right || null}
      </div>
      {children}
    </section>
  );
}

// ── Metric Tile ──

export function MetricTile({ label, value, meta, tone, className = "" }) {
  return (
    <div className={`metric-tile ${statusTone(tone)} ${className}`}>
      <div className="metric-label">{label}</div>
      <div className="metric-value">{value}</div>
      {meta && <div className="metric-meta">{meta}</div>}
    </div>
  );
}

// ── KPI Card ──

export function KpiCard({ label, value, sub, tone }) {
  return (
    <div className={`kpi-card ${statusTone(tone)}`}>
      <div className="kpi-label">{label}</div>
      <div className="kpi-value">{value}</div>
      {sub && <div className="kpi-sub">{sub}</div>}
    </div>
  );
}

// ── Stat Row ──

export function StatRow({ icon: Icon, label, value, sub, tone }) {
  return (
    <div className={`stat-row ${statusTone(tone)}`}>
      <div className="stat-row-label">
        {Icon && <Icon size={13} />}
        <span>{label}</span>
      </div>
      <div>
        <span className="stat-row-value">{value}</span>
        {sub && <span className="stat-row-sub">{sub}</span>}
      </div>
    </div>
  );
}

// ── Progress Bar ──

export function ProgressBar({ label, value, tone = "", meta }) {
  const normalized = Math.max(0, Math.min(1, Number(value || 0)));
  return (
    <div className="progress-block">
      <div className="progress-row">
        <span>{label}</span>
        <span>{meta || pct(normalized)}</span>
      </div>
      <div className="progress-rail">
        <div className={`progress-fill ${statusTone(tone)}`} style={{ width: `${normalized * 100}%` }} />
      </div>
    </div>
  );
}

// ── Button ──

export function Button({ icon: Icon, children, tone = "", className = "", ...props }) {
  return (
    <button className={`btn ${tone ? `btn-${tone}` : ""} ${className}`} type="button" {...props}>
      {Icon ? <Icon size={14} /> : null}
      <span>{children}</span>
    </button>
  );
}

// ── Sparkline ──

export function Sparkline({ data = [], width = 64, height = 24 }) {
  if (!data.length) return null;
  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;
  const points = data.map((v, i) => {
    const x = (i / Math.max(1, data.length - 1)) * width;
    const y = height - ((v - min) / range) * (height - 4) - 2;
    return `${x},${y}`;
  });
  const last = data[data.length - 1];
  const lastY = height - ((last - min) / range) * (height - 4) - 2;
  const areaPoints = `0,${height} ${points.join(" ")} ${width},${height}`;
  const toneClass = last >= data[0] ? "sparkline-positive" : "sparkline-negative";
  return (
    <div style={{ flexShrink: 0 }}>
      <svg className={`sparkline-svg ${toneClass}`} width={width} height={height} viewBox={`0 0 ${width} ${height}`}>
        <polygon className="sparkline-area" points={areaPoints} />
        <polyline className="sparkline-line" points={points.join(" ")} />
        <circle className="sparkline-dot" cx={width} cy={lastY} />
      </svg>
    </div>
  );
}

// ── Large Sparkline ──

export function LargeSparkline({ data = [], height = 160, formatValue }) {
  const [hoverIdx, setHoverIdx] = React.useState(null);

  if (!data || !data.length) return <div className="empty-state">No data yet</div>;
  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;
  const w = 800;
  const pointData = data.map((v, i) => {
    const x = (i / Math.max(1, data.length - 1)) * w;
    const y = height - ((v - min) / range) * (height - 30) - 15;
    return { x, y, v };
  });
  const polyPoints = pointData.map((p) => `${p.x},${p.y}`).join(" ");
  const areaPoints = `0,${height} ${polyPoints} ${w},${height}`;
  const last = data[data.length - 1];
  const first = data[0];
  const color = last >= first ? "var(--accent-green)" : "var(--accent-red)";
  const lastY = height - ((last - min) / range) * (height - 30) - 15;

  const handleMouseMove = (e) => {
    const svg = e.currentTarget;
    const rect = svg.getBoundingClientRect();
    const relX = (e.clientX - rect.left) / rect.width;
    const idx = Math.round(relX * (data.length - 1));
    setHoverIdx(Math.max(0, Math.min(data.length - 1, idx)));
  };
  const handleMouseLeave = () => setHoverIdx(null);

  const hoverPt = hoverIdx !== null ? pointData[hoverIdx] : null;
  const fmt = formatValue || ((v) => `$${Number(v).toFixed(2)}`);

  return (
    <div style={{ position: "relative", width: "100%", height, marginTop: 12 }}>
      {hoverPt && (
        <div style={{
          position: "absolute", top: 0, left: "50%", transform: "translateX(-50%)",
          background: "rgba(13,23,38,0.92)", border: "1px solid rgba(90,215,255,0.3)",
          borderRadius: 8, padding: "6px 12px", pointerEvents: "none", zIndex: 10,
          fontFamily: "var(--mono)", fontSize: "0.82rem", color: "var(--text-primary)",
          whiteSpace: "nowrap",
        }}>
          {fmt(hoverPt.v)}
        </div>
      )}
      <svg width="100%" height="100%" viewBox={`0 0 ${w} ${height}`} preserveAspectRatio="none"
        style={{ overflow: "visible", cursor: "crosshair" }}
        onMouseMove={handleMouseMove} onMouseLeave={handleMouseLeave}>
        <defs>
          <linearGradient id="lgGlow" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity={0.25} />
            <stop offset="100%" stopColor={color} stopOpacity={0} />
          </linearGradient>
        </defs>
        <polygon points={areaPoints} fill="url(#lgGlow)" />
        <polyline points={polyPoints} fill="none" stroke={color} strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
        {hoverPt && (
          <line x1={hoverPt.x} y1={0} x2={hoverPt.x} y2={height} stroke="rgba(90,215,255,0.3)" strokeWidth="1" strokeDasharray="4,4" />
        )}
        {hoverPt && (
          <circle cx={hoverPt.x} cy={hoverPt.y} r="5" fill={color} stroke="var(--bg-base)" strokeWidth="2" />
        )}
        <circle cx={w} cy={lastY} r="4" fill={color} className="pulse" />
      </svg>
    </div>
  );
}

// ── Gauge ──

export function Gauge({ value = 0, max = 100, size = 80, strokeWidth = 6, label, color }) {
  const normalized = Math.min(1, Math.max(0, value / max));
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference * (1 - normalized);
  const displayValue = typeof value === "number" ? (value % 1 === 0 ? value : value.toFixed(1)) : value;
  const strokeColor = color || (normalized > 0.7 ? "var(--accent-green)" : normalized > 0.4 ? "var(--accent-amber)" : "var(--accent-red)");
  return (
    <div style={{ position: "relative", display: "inline-flex", flexDirection: "column", alignItems: "center" }}>
      <svg style={{ transform: "rotate(-90deg)" }} width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        <circle fill="none" stroke="rgba(255,255,255,0.06)" cx={size / 2} cy={size / 2} r={radius} strokeWidth={strokeWidth} />
        <circle fill="none" strokeLinecap="round" stroke={strokeColor} strokeDasharray={circumference} strokeDashoffset={offset}
          cx={size / 2} cy={size / 2} r={radius} strokeWidth={strokeWidth}
          style={{ transition: "stroke-dashoffset 0.6s ease" }} />
      </svg>
      <div style={{ position: "absolute", top: "50%", left: "50%", transform: "translate(-50%, -55%)", textAlign: "center" }}>
        <div style={{ fontSize: "1.2rem", fontWeight: 700, letterSpacing: "-0.03em" }}>{displayValue}</div>
        {label && <div style={{ fontSize: "0.6rem", color: "var(--text-muted)", fontFamily: "var(--mono)", textTransform: "uppercase", letterSpacing: "0.1em" }}>{label}</div>}
      </div>
    </div>
  );
}

// ── Event List ──

export function EventList({ items, empty = "Nothing to show." }) {
  if (!items || !items.length) return <div className="empty-state">{empty}</div>;
  return (
    <div className="event-list">
      {items.map((item, index) => (
        <div className={`event-card ${statusTone(item.level)}`} key={`${item.title || item.text}-${index}`}>
          <div className="event-top">
            <span className="event-title">{item.title || item.level || "event"}</span>
            <span className="event-chip">{String(item.level || "info").toUpperCase()}</span>
          </div>
          <div className="event-body">{item.message || item.text}</div>
        </div>
      ))}
    </div>
  );
}

// ── Pipeline Stage Board ──

const JOURNEY_STEPS = [
  { key: "context", label: "Context", title: "Context Engine" },
  { key: "simulation", label: "Scenario", title: "Scenario Engine" },
  { key: "policy", label: "Execution", title: "Execution Policy" },
  { key: "selection", label: "Review", title: "Live Review" },
  { key: "authority", label: "Authority", title: "Production Authority" },
];

export { JOURNEY_STEPS };

export function PipelineStageBoard({ data, activeIndex }) {
  const training = data?.training || {};
  return (
    <div className="pipeline-board">
      {JOURNEY_STEPS.map((step, index) => {
        const state = index < activeIndex ? "pass" : index === activeIndex ? "active" : "idle";
        return (
          <div className={`stage-card ${statusTone(state === "active" ? "info" : state)}`} key={step.key}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
              <span style={{ fontSize: "0.82rem", fontWeight: 600 }}>{step.label}</span>
              <span className="stage-index">0{index + 1}</span>
            </div>
            <h3>{step.title}</h3>
            {step.key === "context" && (
              <ProgressBar label="Memory" value={training.lstm?.memoryStrength || 0} tone="pass" meta={`${training.lstm?.featuresUsed || 0} feat`} />
            )}
            {step.key === "simulation" && (
              <ProgressBar label="Alignment" value={training.dreamerV3?.alignment || 0} meta={`${(training.dreamerV3?.steps || 0).toLocaleString()} steps`} />
            )}
            {step.key === "policy" && (
              <ProgressBar label="Progress" value={training.ppo?.progress || 0} meta={`${(training.ppo?.currentTimesteps || 0).toLocaleString()} ts`} />
            )}
            {step.key === "selection" && (
              <ProgressBar label="Review" value={data?.registry?.canary?.progress || 0} tone={data?.registry?.gate?.ready ? "pass" : "warn"} meta={data?.registry?.gate?.reason || ""} />
            )}
            {step.key === "authority" && (
              <ProgressBar label="Authority" value={training.ppo?.progress || 0} tone="pass" meta={data?.registry?.champion?.id || ""} />
            )}
          </div>
        );
      })}
    </div>
  );
}

// ── Log Feed ──

export function LogFeed({ items = [], maxItems = 12 }) {
  const rows = items.slice(-maxItems);
  if (!rows.length) return <div className="empty-state">No log entries</div>;
  return (
    <div className="log-feed">
      {rows.map((item, i) => (
        <div className="log-line" key={i}>
          {item.time && <span className="log-time">{item.time}</span>}
          <span className={`log-level ${item.level || "info"}`}>{item.level || "info"}</span>
          <span className="log-msg">{item.text || item.message}</span>
        </div>
      ))}
    </div>
  );
}