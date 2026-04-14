import React, { useEffect, useState, useRef } from "react";
import { Activity, Shield, Cpu, Network, Zap } from "lucide-react";

export default function LoadingScreen({ onComplete }) {
  const [progress, setProgress] = useState(0);
  const apiReadyRef = useRef(false);
  const doneRef = useRef(false);
  const timerRef = useRef(null);

  const onCompleteRef = useRef(onComplete);
  useEffect(() => {
    onCompleteRef.current = onComplete;
  }, [onComplete]);

  const steps = [
    { label: "Establishing secure connection to core...", icon: Network },
    { label: "Loading initial context memory...", icon: Cpu },
    { label: "Warming up PPO and Dreamer models...", icon: Activity },
    { label: "Verifying risk authority...", icon: Shield },
    { label: "Connecting to live symbol lanes...", icon: Zap }
  ];

  // Poll backend until /api/status responds OK
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
        } catch (_) {
          // backend not up yet
        }
        await new Promise((r) => setTimeout(r, 1500));
      }
    }
    checkApi();
    return () => { cancelled = true; };
  }, []);

  // Animate progress bar — single stable interval
  useEffect(() => {
    const intervalMs = 50;
    let elapsed = 0;

    timerRef.current = setInterval(() => {
      if (!apiReadyRef.current) elapsed += intervalMs;

      setProgress((prev) => {
        let target;
        if (apiReadyRef.current) {
          target = Math.min(100, prev + 4);
        } else {
          const t = elapsed / 5000;
          target = Math.min(80, (1 - (1 - t) * (1 - t)) * 80);
        }

        if (target >= 100 && !doneRef.current) {
          doneRef.current = true;
          clearInterval(timerRef.current);
          setTimeout(() => {
            if (onCompleteRef.current) onCompleteRef.current();
          }, 400);
        }

        return target;
      });
    }, intervalMs);

    return () => clearInterval(timerRef.current);
  }, []);

  const step = progress > 85 ? 4 : progress > 65 ? 3 : progress > 40 ? 2 : progress > 15 ? 1 : 0;
  const CurrentIcon = steps[step].icon;

  return (
    <div className="loading-screen">
      <div className="loading-content">
        <div className="logo-container">
          <div className="logo-pulse"></div>
          <div className="logo-core">
            <svg viewBox="0 0 100 100" className="brand-logo">
              {/* Outer hexagon */}
              <path d="M50 5 L88.97 27.5 L88.97 72.5 L50 95 L11.03 72.5 L11.03 27.5 Z" fill="none" stroke="var(--cyan)" strokeWidth="2.5" strokeDasharray="30 10" className="logo-path-slow" />
              {/* Inner shape */}
              <path d="M50 20 L75 35 L75 65 L50 80 L25 65 L25 35 Z" fill="none" stroke="var(--purple)" strokeWidth="1.5" strokeDasharray="4 6" className="logo-path-fast" />
              {/* Center core */}
              <circle cx="50" cy="50" r="10" fill="var(--cyan)" className="logo-dot" />
            </svg>
          </div>
        </div>

        <h1 className="brand-title">CAUTIOUS GIGGLE</h1>
        <div className="brand-subtitle">AUTONOMOUS TRADING PIPELINE</div>

        <div className="loading-status-area">
          <div className="loading-step-row" key={step}>
            <CurrentIcon size={16} className="loading-step-icon" />
            <span className="loading-step-text">{steps[step].label}</span>
          </div>

          <div className="global-progress-bar">
            <div className="global-progress-fill" style={{ width: `${progress}%` }}>
              <div className="global-progress-glow"></div>
            </div>
          </div>
          <div className="loading-percentage">{Math.floor(progress)}%</div>
        </div>
      </div>
    </div>
  );
}
