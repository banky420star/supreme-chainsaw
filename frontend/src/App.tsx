import React from 'react'
import { StatusPayload, PatternRecord } from './types'
import {
  fetchStatus,
  fetchPatterns,
  fetchPerf,
  fetchPPODiagnostics,
  fetchLSTMExplanations,
  fetchLanes,
  fetchScenarios,
  fetchEconomicCalendar,
  createStatusWS,
  PPODiagnostics,
  LSTMExplanation,
  LaneStatus,
  RegimesResponse,
  EconomicEvent,
} from './services/api'
import DashboardPanel from './components/DashboardPanel'
import TradingPanel from './components/TradingPanel'
import TrainingPanel from './components/TrainingPanel'
import TrainingProgressPanel from './components/TrainingProgressPanel'
import ModelsPanel from './components/ModelsPanel'
import PatternLibraryPanel from './components/PatternLibraryPanel'
import SettingsPanel from './components/SettingsPanel'
import TradeHistoryPanel from './components/TradeHistoryPanel'
import PPODiagPanel from './components/PPODiagPanel'
import HFTHealthPanel from './components/HFTHealthPanel'
import PerpetualPanel from './components/PerpetualPanel'
import LRTimeline from './components/LRTimeline'
import ScenarioMemoryPanel from './components/ScenarioMemoryPanel'
import PipelinePanel from './components/PipelinePanel'
import AgentTeamPanel from './components/AgentTeamPanel'

type TabId =
  | 'home' | 'trading' | 'training' | 'progress' | 'models'
  | 'patterns' | 'settings' | 'trades' | 'ppo'
  | 'hft' | 'perpetual' | 'lr-timeline' | 'scenarios' | 'agents'
  | 'pipeline'

const TABS: { id: TabId; label: string }[] = [
  { id: 'home',        label: 'Dashboard'  },
  { id: 'pipeline',    label: 'Pipeline'   },
  { id: 'trading',     label: 'Trading'    },
  { id: 'trades',      label: 'History'    },
  { id: 'training',    label: 'Training'   },
  { id: 'progress',    label: 'Progress'   },
  { id: 'models',      label: 'Models'     },
  { id: 'ppo',         label: 'PPO Brain'  },
  { id: 'hft',         label: 'HFT Health' },
  { id: 'scenarios',   label: 'Scenarios'  },
  { id: 'perpetual',   label: 'Perpetual'  },
  { id: 'lr-timeline', label: 'LR Timeline'},
  { id: 'patterns',    label: 'Patterns'   },
  { id: 'agents',      label: 'Agents'     },
  { id: 'settings',    label: 'Settings'   },
]

const LOAD_STEPS = [
  'CONNECTING BROKER...',
  'LOADING MODELS...',
  'CALIBRATING RISK...',
  'ARMING SIGNALS...',
  'STACK ONLINE',
]

function LoadingScreen() {
  const [step, setStep] = React.useState(0)
  const [progress, setProgress] = React.useState(0)

  React.useEffect(() => {
    const targets = [18, 42, 65, 85, 100]
    let i = 0
    const advance = () => {
      if (i >= targets.length) return
      setProgress(targets[i])
      setStep(i)
      i++
    }
    advance()
    const id = setInterval(advance, 480)
    return () => clearInterval(id)
  }, [])

  return (
    <div className="agit-loading">
      {/* Sparks */}
      <div className="agit-loading-sparks" aria-hidden="true">
        {Array.from({ length: 12 }).map((_, i) => (
          <span
            key={i}
            style={{
              '--x': `${10 + Math.random() * 80}%`,
              '--y': `${20 + Math.random() * 60}%`,
              '--d': `${3 + Math.random() * 3}s`,
              '--delay': `${Math.random() * 2}s`,
            } as React.CSSProperties}
          />
        ))}
      </div>

      {/* Spinning ring */}
      <div className="agit-loading-core">
        <div className="agit-loading-dot" />
      </div>

      {/* Text content */}
      <div className="agit-loading-content">
        <div className="agit-loading-title">CHAIN GAMBLER</div>
        <div className="agit-loading-sub">AUTONOMOUS TRADING STACK</div>

        {/* Progress bar */}
        <div
          className="agit-loading-progress"
          style={{ position: 'relative' }}
        >
          <div
            style={{
              position: 'absolute',
              inset: 0,
              background: 'linear-gradient(90deg, #009db0, #00f0ff, #ff00a0)',
              boxShadow: '0 0 8px rgba(0,240,255,0.4)',
              width: `${progress}%`,
              transition: 'width 0.45s cubic-bezier(0.4,0,0.2,1)',
              borderRadius: 1,
            }}
          />
        </div>

        {/* Status sequence */}
        <div className="agit-loading-status">
          <span
            style={{
              fontFamily: 'var(--mono)',
              fontSize: '0.65rem',
              color: 'var(--dim)',
              letterSpacing: '0.1em',
            }}
          >
            {LOAD_STEPS[step] ?? LOAD_STEPS[LOAD_STEPS.length - 1]}
          </span>
        </div>
      </div>
    </div>
  )
}

function LiveClock() {
  const [time, setTime] = React.useState(new Date())
  React.useEffect(() => {
    const id = setInterval(() => setTime(new Date()), 1000)
    return () => clearInterval(id)
  }, [])
  const h = String(time.getUTCHours()).padStart(2, '0')
  const m = String(time.getUTCMinutes()).padStart(2, '0')
  const s = String(time.getUTCSeconds()).padStart(2, '0')
  return (
    <div className="agit-clock">
      <span className="agit-clock-label">UTC</span>
      <span>{h}</span>
      <span style={{ animation: 'blink 1s step-end infinite' }}>:</span>
      <span>{m}</span>
      <span style={{ animation: 'blink 1s step-end infinite' }}>:</span>
      <span>{s}</span>
    </div>
  )
}

/* ─── Full pipeline state ─── */
interface PipelineState {
  status: StatusPayload | null
  patterns: PatternRecord[]
  perf: any
  ppoDiag: PPODiagnostics | null
  lstmExpl: Record<string, LSTMExplanation>
  lanes: LaneStatus[]
  scenarios: RegimesResponse
  calendar: EconomicEvent[]
}

const EMPTY_PIPELINE: PipelineState = {
  status: null,
  patterns: [],
  perf: null,
  ppoDiag: null,
  lstmExpl: {},
  lanes: [],
  scenarios: { regimes: {} },
  calendar: [],
}

const App: React.FC = () => {
  const [pipe, setPipe] = React.useState<PipelineState>(EMPTY_PIPELINE)
  const [activeTab, setActiveTab] = React.useState<TabId>('home')
  const wsConnectedRef = React.useRef(false)
  const [wsConnected, setWsConnected] = React.useState(false)

  /* ─── Full pipeline refresh (non-status endpoints) ─── */
  const refreshSideData = React.useCallback(async () => {
    const [patterns, perf, ppoDiag, lstmExpl, lanesRes, scenarios, calendar] =
      await Promise.allSettled([
        fetchPatterns(),
        fetchPerf(),
        fetchPPODiagnostics(),
        fetchLSTMExplanations(),
        fetchLanes(),
        fetchScenarios(),
        fetchEconomicCalendar(7),
      ])

    setPipe((prev) => {
      const next = { ...prev }

      if (patterns.status === 'fulfilled')
        next.patterns = patterns.value ?? []

      if (perf.status === 'fulfilled' && perf.value)
        next.perf = perf.value

      if (ppoDiag.status === 'fulfilled')
        next.ppoDiag = ppoDiag.value

      if (lstmExpl.status === 'fulfilled')
        next.lstmExpl = lstmExpl.value ?? {}

      if (lanesRes.status === 'fulfilled')
        next.lanes = lanesRes.value?.lanes ?? []

      if (scenarios.status === 'fulfilled')
        next.scenarios = scenarios.value ?? { regimes: {} }

      if (calendar.status === 'fulfilled')
        next.calendar = calendar.value ?? []

      return next
    })
  }, [])

  /* ─── WebSocket + polling setup ─── */
  React.useEffect(() => {
    // Full refresh on load (status + side data)
    const initialRefresh = async () => {
      const statusResult = await fetchStatus().catch(() => null)
      if (statusResult) {
        setPipe((prev) => ({ ...prev, status: statusResult }))
      }
      await refreshSideData()
    }
    initialRefresh()

    // WebSocket — receives /api/status payloads every ~2s from backend
    const destroyWS = createStatusWS(
      (data) => {
        setPipe((prev) => ({ ...prev, status: data }))
      },
      (connected) => {
        wsConnectedRef.current = connected
        setWsConnected(connected)
      }
    )

    // Polling fallback:
    //   • When WS is connected — poll side data every 30s (WS handles status)
    //   • When WS is disconnected — poll status + side data every 10s
    const poll = async () => {
      if (!wsConnectedRef.current) {
        const statusResult = await fetchStatus().catch(() => null)
        if (statusResult) {
          setPipe((prev) => ({ ...prev, status: statusResult }))
        }
      }
      await refreshSideData()
    }

    const interval = setInterval(poll, 10_000)

    return () => {
      destroyWS()
      clearInterval(interval)
    }
  }, [refreshSideData]) // eslint-disable-line react-hooks/exhaustive-deps

  /* Sync pattern library from live status */
  React.useEffect(() => {
    const lib = pipe.status?.training?.pattern_library
    if (!lib) return
    const records: PatternRecord[] = Object.entries(lib)
      .map(([pattern_name, payload]) => ({ pattern_name, ...(payload || {}) }))
      .sort((a, b) => new Date(b.discovered_at || 0).getTime() - new Date(a.discovered_at || 0).getTime())
    setPipe((prev) => ({ ...prev, patterns: records.length > 0 ? records : prev.patterns }))
  }, [pipe.status])

  if (!pipe.status) return <LoadingScreen />

  const { status, patterns, perf, ppoDiag, lstmExpl, lanes, scenarios, calendar } = pipe
  const halted = status?.risk?.halt

  const refreshAll = React.useCallback(async () => {
    const statusResult = await fetchStatus().catch(() => null)
    if (statusResult) {
      setPipe((prev) => ({ ...prev, status: statusResult }))
    }
    await refreshSideData()
  }, [refreshSideData])

  const renderContent = () => {
    switch (activeTab) {
      case 'home':        return <DashboardPanel status={status!} />
      case 'pipeline':    return <PipelinePanel status={status!} />
      case 'trading':     return <TradingPanel status={status!} lanes={lanes} lstmExpl={lstmExpl} onModeChange={refreshAll} />
      case 'trades':      return <TradeHistoryPanel calendar={calendar} />
      case 'training':    return <TrainingPanel status={status!} />
      case 'progress':    return <TrainingProgressPanel status={status!} />
      case 'models':      return <ModelsPanel status={status!} />
      case 'ppo':         return <PPODiagPanel status={status!} ppoDiag={ppoDiag} />
      case 'hft':         return <HFTHealthPanel status={status!} />
      case 'scenarios':   return <ScenarioMemoryPanel scenarios={scenarios} />
      case 'perpetual':   return <PerpetualPanel perf={perf} />
      case 'lr-timeline': return <LRTimeline data={perf?.adaptation_history ?? null} height={200} />
      case 'patterns':    return <PatternLibraryPanel patterns={patterns} status={status!} lstmExpl={lstmExpl} />
      case 'agents':      return <AgentTeamPanel status={status!} />
      case 'settings':    return <SettingsPanel status={status!} />
      default: return null
    }
  }

  return (
    <div className="agit-shell">
      <div className="scanlines" />

      <nav className="agit-nav">
        <div className="agit-nav-brand">
          <div className="agit-nav-mark" />
          <div>
            <div className="agit-nav-title">CHAIN GAMBLER</div>
            <div className="agit-nav-subtitle">Autonomous Trading Stack</div>
          </div>
        </div>

        <div className="agit-nav-tabs">
          {TABS.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`agit-nav-tab${activeTab === tab.id ? ' active' : ''}`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        <div className="agit-nav-status">
          <LiveClock />
          {halted ? (
            <span className="agit-pill agit-pill-halt">HALTED</span>
          ) : (
            <span className="agit-pill agit-pill-live">LIVE</span>
          )}
          {/* Truth pills */}
          {pipe.status?.system?.real_money_locked && (
            <span className="agit-pill" style={{ background: 'var(--red)', color: '#fff', marginLeft: 6 }}>
              LOCKED
            </span>
          )}
          {pipe.status?.tests?.status === 'failing' && (
            <span className="agit-pill" style={{ background: 'var(--amber)', color: '#000', marginLeft: 6 }}>
              TESTS FAIL
            </span>
          )}
          {pipe.status?.account?.telemetry_valid === false && (
            <span className="agit-pill" style={{ background: 'var(--amber)', color: '#000', marginLeft: 6 }}>
              TELEMETRY INVALID
            </span>
          )}
          <span style={{
            display: 'inline-flex', alignItems: 'center', gap: 4,
            fontSize: 11, color: wsConnected ? 'var(--green)' : 'var(--amber)',
            marginLeft: 6,
          }}>
            <span style={{
              width: 6, height: 6, borderRadius: '50%',
              background: wsConnected ? 'var(--green)' : 'var(--amber)',
              boxShadow: wsConnected ? '0 0 6px var(--green)' : 'none',
              flexShrink: 0,
            }} />
            {wsConnected ? 'WS' : 'POLL'}
          </span>
        </div>
      </nav>

      <main className="agit-main animate-in">
        {renderContent()}
      </main>
    </div>
  )
}

export default App
