import React, { useEffect, useState, useRef, useCallback } from "react";
import { Activity, Shield, Cpu, Network, Zap, Brain, CandlestickChart, GitBranch, Rocket, Eye, Lock, Sparkles, TrendingUp, Gauge, Database, HeartPulse } from "lucide-react";

const BOOT_SEQUENCE = [
  { label: "Initializing neural pathways...", icon: Brain, duration: 1200, quip: "Synapses firing up" },
  { label: "Connecting to market data feed...", icon: Network, duration: 900, quip: "Riding the wire" },
  { label: "Loading LSTM context memory...", icon: Cpu, duration: 1100, quip: "150 features, zero excuses" },
  { label: "Warming up PPO champion model...", icon: Activity, duration: 1000, quip: "Policy mode: engaged" },
  { label: "Scanning symbol lanes...", icon: CandlestickChart, duration: 800, quip: "4 symbols, 1 brain" },
  { label: "Initializing reversal detector...", icon: TrendingUp, duration: 700, quip: "5 methods, zero mercy" },
  { label: "Calibrating speed simulator...", icon: Gauge, duration: 600, quip: "Latency profiles loaded" },
  { label: "Mounting backup manager...", icon: Database, duration: 500, quip: "7-day retention active" },
  { label: "Starting health check endpoint...", icon: HeartPulse, duration: 400, quip: "/api/health ready" },
  { label: "Verifying risk authority...", icon: Shield, duration: 700, quip: "Drawdown check: passed" },
  { label: "Arming trailing stop manager...", icon: Zap, duration: 600, quip: "Profits, protected" },
  { label: "Calibrating deadzone threshold...", icon: Eye, duration: 500, quip: "LOW_VOL = hold tight" },
  { label: "Locking canary gate...", icon: Lock, duration: 400, quip: "Canary not yet ready" },
  { label: "Syncing evolutionary pipeline...", icon: GitBranch, duration: 600, quip: "Always improving" },
  { label: "Running final sanity check...", icon: Sparkles, duration: 500, quip: "All systems nominal" },
  { label: "Going live.", icon: Rocket, duration: 300, quip: "" },
];

export default function LoadingScreen() {
  const [progress, setProgress] = useState(0);
  const [currentStep, setCurrentStep] = useState(0);
  const [completedSteps, setCompletedSteps] = useState([]);
  const [showQuip, setShowQuip] = useState(false);
  const [matrixChars, setMatrixChars] = useState([]);
  const apiReadyRef = useRef(false);
  const doneRef = useRef(false);

  // Poll API until it responds
  useEffect(() => {
    let cancelled = false;
    async function checkApi() {
      while (!cancelled) {
        try {
          const res = await fetch("/api/status", { cache: "no-store" });
          if (res.ok) {
            apiReadyRef.current = true;
            return;
          }
        } catch {}
        await new Promise((r) => setTimeout(r, 1500));
      }
    }
    checkApi();
    return () => { cancelled = true; };
  }, []);

  // Progress and step animation
  useEffect(() => {
    const totalDuration = BOOT_SEQUENCE.reduce((a, s) => a + s.duration, 0);
    let elapsed = 0;
    let stepIdx = 0;
    let stepElapsed = 0;

    const interval = setInterval(() => {
      if (stepIdx < BOOT_SEQUENCE.length) {
        const step = BOOT_SEQUENCE[stepIdx];
        stepElapsed += 50;

        setCurrentStep(stepIdx);
        setShowQuip(true);

        if (stepElapsed >= step.duration) {
          setCompletedSteps((prev) => [...prev, stepIdx]);
          stepIdx++;
          stepElapsed = 0;
          setShowQuip(false);
        }
      }

      elapsed += 50;
      setProgress((prev) => {
        let target;
        if (apiReadyRef.current) {
          target = Math.min(100, prev + 3);
        } else {
          const t = Math.min(1, elapsed / totalDuration);
          target = Math.min(90, (1 - (1 - t) * (1 - t)) * 90);
        }
        if (target >= 99.5 && !doneRef.current) {
          doneRef.current = true;
        }
        return target;
      });
    }, 50);

    return () => clearInterval(interval);
  }, []);

  // Matrix rain effect
  useEffect(() => {
    const chars = "01ACGT$%@#&<>{}[]";
    const interval = setInterval(() => {
      setMatrixChars((prev) => {
        const next = [...prev];
        if (next.length < 25) {
          next.push({
            char: chars[Math.floor(Math.random() * chars.length)],
            x: Math.random() * 100,
            y: -5,
            speed: 0.5 + Math.random() * 2,
            opacity: 0.05 + Math.random() * 0.1,
            id: Date.now() + Math.random(),
          });
        }
        return next
          .map((c) => ({ ...c, y: c.y + c.speed }))
          .filter((c) => c.y < 105);
      });
    }, 100);
    return () => clearInterval(interval);
  }, []);

  const step = BOOT_SEQUENCE[currentStep] || BOOT_SEQUENCE[BOOT_SEQUENCE.length - 1];
  const CurrentIcon = step.icon;
  const isComplete = progress >= 99.5;

  return (
    <div className="loading-screen">
      {/* Matrix rain background */}
      <div className="loading-matrix-bg">
        {matrixChars.map((c) => (
          <span
            key={c.id}
            className="matrix-char"
            style={{
              left: `${c.x}%`,
              top: `${c.y}%`,
              opacity: c.opacity,
            }}
          >
            {c.char}
          </span>
        ))}
      </div>

      <div className="loading-content">
        {/* Animated hex logo */}
        <div className="logo-container">
          <div className="logo-pulse"></div>
          <div className="logo-pulse" style={{ animationDelay: "0.7s" }}></div>
          <div className="logo-core">
            <svg viewBox="0 0 100 100" className="brand-logo">
              <path d="M50 5 L88.97 27.5 L88.97 72.5 L50 95 L11.03 72.5 L11.03 27.5 Z" fill="none" stroke="var(--accent-cyan)" strokeWidth="2" strokeDasharray="30 10" style={{ animation: "sweep 8s linear infinite" }} />
              <path d="M50 20 L75 35 L75 65 L50 80 L25 65 L25 35 Z" fill="none" stroke="var(--accent-purple)" strokeWidth="1.5" strokeDasharray="4 6" style={{ animation: "sweep 4s linear infinite reverse" }} />
              <path d="M50 30 L65 38.75 L65 61.25 L50 70 L35 61.25 L35 38.75 Z" fill="none" stroke="var(--accent-green)" strokeWidth="1" strokeDasharray="2 4" style={{ animation: "sweep 2.5s linear infinite" }} />
              <circle cx="50" cy="50" r="8" fill="var(--accent-cyan)" style={{ animation: "pulse 1.5s infinite" }} />
              <circle cx="50" cy="50" r="4" fill="#fff" style={{ animation: "pulse 1.5s infinite 0.3s" }} />
            </svg>
          </div>
          {/* Orbiting dots */}
          <div className="orbit-dot orbit-1" />
          <div className="orbit-dot orbit-2" />
          <div className="orbit-dot orbit-3" />
        </div>

        {/* Brand */}
        <h1 className={`brand-title ${isComplete ? "brand-ready" : ""}`}>
          CHAIN GAMBLER
        </h1>
        <div className="brand-subtitle" style={{ fontSize: "0.85rem", opacity: 0.7, marginTop: -8, marginBottom: 8 }}>
          Money Printer Edition
        </div>
        <div className="brand-subtitle">
          {isComplete ? "SYSTEM ONLINE" : "AUTONOMOUS TRADING PIPELINE"}
        </div>

        {/* Boot sequence log */}
        <div className="boot-log">
          {completedSteps.map((idx) => {
            const s = BOOT_SEQUENCE[idx];
            if (!s || !s.icon) return null;
            const SIcon = s.icon;
            return (
              <div className="boot-line done" key={idx}>
                <SIcon size={12} className="boot-line-icon done" />
                <span className="boot-line-text">{s.label}</span>
                <span className="boot-line-check">&#10003;</span>
              </div>
            );
          })}
          {!isComplete && (
            <div className="boot-line active" key={currentStep}>
              <CurrentIcon size={12} className="boot-line-icon active" />
              <span className="boot-line-text">{step.label}</span>
              <span className="boot-line-spinner" />
            </div>
          )}
        </div>

        {/* Quip */}
        {showQuip && step.quip && (
          <div className="boot-quip" key={currentStep}>
            {step.quip}
          </div>
        )}

        {/* Progress bar with segments */}
        <div className="progress-section">
          <div className="global-progress-bar">
            <div className="global-progress-fill" style={{ width: `${progress}%` }}>
              <div className="global-progress-glow" />
            </div>
          </div>
          <div className="progress-info">
            <span className="progress-pct">{Math.floor(progress)}%</span>
            <span className="progress-detail">
              {isComplete
                ? "Dashboard loading..."
                : `Step ${currentStep + 1}/${BOOT_SEQUENCE.length}`}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}