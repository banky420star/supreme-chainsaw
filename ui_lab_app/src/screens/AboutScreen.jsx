import React from "react";
import { BrainCircuit, Database, GitMerge, Rocket, ShieldAlert, Workflow } from "lucide-react";
import { Panel } from "../components/Common";

const steps = [
  {
    title: "Granular Data & Feature Engineering",
    technical: "Data Pipeline",
    icon: Database,
    tone: "info",
    purpose: "The entire system feeds on live price, volume, and depth data before mathematically expanding it into hundreds of features.",
    description: "Data is retrieved natively in pure Python via a specialized MetaTrader5 HFT pipeline running at granular minute resolutions. Raw ticks are aggressively engineered into 150+ advanced mathematical features before touching any neural network.",
  },
  {
    title: "Latent Context Engine",
    technical: "LSTM Time-Series",
    icon: BrainCircuit,
    tone: "pass",
    purpose: "Long Short-Term Memory parses complex arrays of past price action to intuitively feel the market regime.",
    description: "It summarizes a sequence of up to 60-depth inputs into a highly compressed Latent Context representing the immediate physical scenario (chopping, trending, expanding mathematically).",
  },
  {
    title: "Execution & Imagination",
    technical: "DreamerV3 + PPO Policy",
    icon: Rocket,
    tone: "warn",
    purpose: "Two separate neural networks evaluate the situation simultaneously; one simulates disaster while the other hunts for profit.",
    description: "DreamerV3 simulates thousands of potential future ticks before execution, issuing direct alerts if a trajectory leads to a highly probable disaster. PPO precisely merges the LSTM context with Dreamer warnings to map optimal pathways.",
  },
  {
    title: "Risk Overlord Interception",
    technical: "Hard Cutoff Hierarchy",
    icon: ShieldAlert,
    tone: "fail",
    purpose: "Absolute mathematical preservation of capital supersedes any AI model confidence.",
    description: "Risk calculation is completely decoupled from the autonomous AI brains. The risk_supervisor module strictly audits incoming PPO execution decisions. Rigid cutoff constraints physically intercept and kill trade pipelines if daily limits or maximum drawdowns are threatened.",
  },
  {
    title: "The Evolutionary Loop",
    technical: "Continuous Learning",
    icon: GitMerge,
    tone: "pass",
    purpose: "A continuous survival-of-the-fittest architecture constantly replaces underperforming neural models with hyper-tuned mutations.",
    description: "When trades result in stop-losses, setup boundaries are mathematically isolated and specific neural action-weights are physically shifted. Mutated canary models trade continuously in the background; once they mathematically outperform the live champion, they instantly take control.",
  },
];

function ArchitectureStage({ step, index, total }) {
  const Icon = step.icon;
  return (
    <div className="authority-stage" style={{ animationDelay: `${index * 150}ms`, width: "100%", maxWidth: 900, margin: "0 auto" }}>
      <div className="authority-marker">
        <div className="authority-number">0{index + 1}</div>
        {index < total - 1 ? <div className="authority-line" /> : null}
      </div>
      <div className="authority-card">
        <div className="authority-card-top">
          <div>
            <div className="eyebrow" style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <Icon size={14} />
              <span>{step.technical}</span>
            </div>
            <h3>{step.title}</h3>
          </div>
        </div>
        <p className="authority-purpose">{step.purpose}</p>
        {step.description && (
          <div style={{ marginTop: 12, borderTop: "1px solid var(--border)", paddingTop: 12, color: "var(--text-secondary)", fontSize: "0.9rem", lineHeight: 1.6 }}>
            {step.description}
          </div>
        )}
      </div>
    </div>
  );
}

export default function AboutScreen() {
  return (
    <div className="stack animate-in" style={{ maxWidth: 960, margin: "0 auto" }}>
      <div style={{ textAlign: "center", marginBottom: 30, marginTop: 10 }}>
        <h1 style={{ fontSize: "2.2rem", letterSpacing: "-0.04em", color: "var(--accent-cyan)", margin: "0 0 10px 0", textTransform: "uppercase" }}>
          Pipeline Architecture
        </h1>
        <p style={{ color: "var(--text-secondary)", maxWidth: 600, margin: "0 auto", lineHeight: 1.6, fontSize: "1.05rem" }}>
          The autonomous trading pipeline is a massive, self-improving sequence of AI operations. The explicit workflow below details the pipeline from raw data to live execution.
        </p>
      </div>

      <Panel title="The Machine Workflow" subtitle="Detailed breakdown of the continuous intelligence pipeline" icon={Workflow}>
        <div className="authority-timeline" style={{ padding: "20px 10px 0" }}>
          {steps.map((step, idx) => (
            <ArchitectureStage key={idx} step={step} index={idx} total={steps.length} />
          ))}
        </div>
      </Panel>
    </div>
  );
}