import React, { useState, useEffect } from "react";
import { useData } from "./data/DataContext";
import Layout from "./components/Layout";
import LoadingScreen from "./screens/LoadingScreen";
import DashboardScreen from "./screens/DashboardScreen";
import TradingScreen from "./screens/TradingScreen";
import TrainingScreen from "./screens/TrainingScreen";
import ModelsScreen from "./screens/ModelsScreen";
import HistoryScreen from "./screens/HistoryScreen";
import StrategiesScreen from "./screens/StrategiesScreen";
import ControlScreen from "./screens/ControlScreen";
import AboutScreen from "./screens/AboutScreen";

class ErrorBoundary extends React.Component {
  constructor(props) { super(props); this.state = { error: null }; }
  static getDerivedStateFromError(error) { return { error }; }
  render() {
    if (this.state.error) {
      return (
        <div style={{ padding: 40, color: "#ff7b8f", background: "var(--bg-base)", minHeight: "100vh", fontFamily: "monospace" }}>
          <h2>UI Error</h2>
          <pre style={{ whiteSpace: "pre-wrap", color: "#eef5ff" }}>{this.state.error.message}</pre>
          <button onClick={() => { this.setState({ error: null }); window.location.reload(); }}
            style={{ marginTop: 20, padding: "8px 16px", background: "var(--accent-cyan)", color: "#000", border: "none", cursor: "pointer", borderRadius: 8 }}>
            Reload
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

const SCREENS = {
  dashboard: DashboardScreen,
  trading: TradingScreen,
  training: TrainingScreen,
  models: ModelsScreen,
  history: HistoryScreen,
  strategies: StrategiesScreen,
  control: ControlScreen,
  about: AboutScreen,
};

const MIN_SPLASH_MS = 10000; // Loading screen shows for at least 10 seconds

export default function App() {
  const { data, loading, error } = useData();
  const [screen, setScreen] = useState("dashboard");
  const [selectedSymbol, setSelectedSymbol] = useState("BTCUSDm");
  const [splashDone, setSplashDone] = useState(false);

  // Enforce minimum splash screen duration
  useEffect(() => {
    const timer = setTimeout(() => setSplashDone(true), MIN_SPLASH_MS);
    return () => clearTimeout(timer);
  }, []);

  useEffect(() => {
    if (data?.trading?.lanes?.length) {
      const symbols = data.trading.lanes.map((l) => l.symbol);
      if (!symbols.includes(selectedSymbol)) setSelectedSymbol(symbols[0]);
    }
  }, [data, selectedSymbol]);

  if (loading || !splashDone) return <LoadingScreen />;

  if (error && !data) {
    return (
      <div style={{ padding: 40, color: "var(--accent-red)", background: "var(--bg-base)", minHeight: "100vh" }}>
        <h2>Cannot connect to backend</h2>
        <p style={{ color: "var(--text-secondary)" }}>Make sure the backend is running at http://localhost:5000</p>
        <p style={{ color: "var(--text-muted)", fontFamily: "monospace", fontSize: 12 }}>{error}</p>
        <button onClick={() => window.location.reload()}
          style={{ marginTop: 20, padding: "8px 16px", background: "var(--accent-cyan)", color: "#000", border: "none", cursor: "pointer", borderRadius: 8 }}>
          Retry
        </button>
      </div>
    );
  }

  // If we have data (even partial), show the dashboard
  // Error banner will appear in the UI if needed

  const ScreenComponent = SCREENS[screen] || DashboardScreen;

  return (
    <ErrorBoundary>
      <Layout
        screen={screen}
        onNavigate={setScreen}
        selectedSymbol={selectedSymbol}
        onSelectSymbol={setSelectedSymbol}
        data={data}
      >
        <ScreenComponent data={data} selectedSymbol={selectedSymbol} onSelectSymbol={setSelectedSymbol} />
      </Layout>
    </ErrorBoundary>
  );
}