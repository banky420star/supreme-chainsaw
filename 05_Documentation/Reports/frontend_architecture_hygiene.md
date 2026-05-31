# Frontend Architecture & State Hygiene Report — React Trading Monitor UI

**Date**: 2026-05-28  
**Specialist Role**: UI Architecture & State Hygiene Specialist (hygiene team)  
**Scope**: `C:\supreme-chainsaw\frontend\` (React 18 + Vite + TypeScript SPA)  
**Focus Areas** (per assignment):  
- State management (StatusPayload, pipeline stages, equity, training data, agent status)  
- Component composition & reusability (DashboardPanel, OverviewPanel, 20+ specialized panels)  
- Data fetching (api.ts + WebSocket `createStatusWS`)  
- Routing / tab system (App.tsx)  
- Performance (re-renders, memoization, large lists e.g. trades/patterns)  
- Separation of concerns (UI vs data layer)  

**Priority**: Issues affecting long-term maintainability, reliability, and operational safety for a **production trading monitor**. Trading UIs demand consistent real-time data, low cognitive load for operators, and zero-tolerance for desync/staleness bugs.

---

## Executive Summary

The React frontend is a visually polished, feature-rich SPA (multiple mission-control style tabs for trades, brains, pipeline, training, agents, safety, etc.) that successfully surfaces a complex autonomous trading stack. It demonstrates strong domain understanding (StatusPayload shape, risk halts, champion registry, lanes, etc.).

**However, the architecture exhibits classic "panel sprawl" anti-patterns** typical of rapidly evolved internal tools:

- **Fragmented state & fetching**: Central WS-driven status coexists with ~15 independent per-panel polling loops (mostly 15s). No single source of truth.
- **Massive duplication**: Boilerplate polling, color/panel style objects, tone mappers, error fallbacks repeated across components.
- **Poor separation**: Most "panels" are smart components that own both data fetching *and* rendering. api.ts is a thin fetch bag, not a service layer.
- **Dead code & tech debt**: Multiple unused panels (TradeHistoryPanel, HFTHealthPanel, etc.), dead imports in App.tsx, two EquityChart implementations.
- **Performance & scalability risks**: No memoization on panels, no virtualization for tables, full re-renders on every status push.

**Cross-reference to existing hygiene work**:  
The broader project has invested heavily in **TUI / swarm visibility hygiene** (see `runtime/TUI_HYGIENE_RETRY_REPORT.md`, `logs/SUPERVISOR_AUDIT_REPORT.md`, `logs/TUI_SWARM_VISIBILITY_UPDATE.md`, `runtime/agent_status/*.json`, `PIPELINE_DECISIONS.jsonl`). These efforts emphasize reliable, no-kill data-layer persistence for 50+ agents and v5 training observability.  

The **React frontend has not benefited from equivalent hygiene**. It consumes the same backend but through ad-hoc, uncoordinated HTTP + limited WS paths. The robust runtime/ JSON + swarm sync story for the Python TUI is invisible or duplicated in the web UI. This creates a two-tier observability gap: TUI/swarm data is "hygiened," React panels are not. A production trading monitor cannot tolerate this divergence.

**Overall Hygiene Grade**: C- (functional today; high risk for production scaling/maintenance).

---

## 1. State Management Analysis

### 1.1 Central "Pipe" State (App.tsx)
**File**: `C:\supreme-chainsaw\frontend\src\App.tsx` (lines 192-214, 216-317)

```ts
interface PipelineState {
  status: StatusPayload | null
  patterns: PatternRecord[]
  perf: any
  ppoDiag: PPODiagnostics | null
  lstmExpl: Record<string, LSTMExplanation>
  lanes: LaneStatus[]
  scenarios: RegimesResponse
  calendar: EconomicEvent[]
  systemHeader: SystemHeaderState | null
}

const [pipe, setPipe] = React.useState<PipelineState>(EMPTY_PIPELINE)
```

- **Single useState blob** updated from:
  - Initial `fetchStatus` + `refreshSideData` (Promise.allSettled)
  - WebSocket `createStatusWS` callback (full replacement)
  - 10s fallback poll (when !wsConnected)
  - Dedicated sync effect for `status.training?.pattern_library` → `patterns` (lines 298-305)
- **Problems**:
  - No granularity: any status tick causes full App re-render and prop cascade to active panel.
  - `any` for perf (line 195). No derived selectors.
  - Pattern sync effect can race with `refreshSideData` patterns fetch.
  - Equity snapshot lives only in `status.account` (types.ts:20); full curves are side-loaded independently.

### 1.2 StatusPayload Shape
**File**: `C:\supreme-chainsaw\frontend\src\types.ts:135-160`

Big discriminated bag with nested `training`, `account`, `risk`, `system`, `data`, `validation`, etc. Some fields duplicated (e.g. drawdown in multiple places). Training data (lanes, visual progress, pattern_library) mixed with live trading state.

**Pipeline stages** (`PipelineStage`): Defined in types + fetched only by `PipelinePanel` (never via App's central refresh).

**Equity**: Snapshot (cheap) vs curve (heavy, only in Trades + legacy Dashboard).

**Training data**: Primarily via prop-drilled `status.training` to `TrainingPanel`. Other training views (if any) fetch separately.

**Agent status**: Two completely divergent paths:
  1. `extractAgentStatus(status)` in `api.ts:34-163` — derives 11 synthetic `AgentStatus[]` from status fields (fake metrics, pattern counts, etc.). Used by unused `AgentTeamPanel`.
  2. Dedicated `fetchAgentsOperational()` → `/api/agents/status` returning `AgentOperationalStatus[]`. Used by live `AgentsPanel`.
  Result: Inconsistent "agents" views depending on tab.

### 1.3 Cross-Panel Desynchronization Risks (Production Critical)
- User viewing **Pipeline** tab sees `/api/pipeline/stages` (15s poll).
- User viewing **Training** sees `status.training` (WS + 10s).
- User viewing **Model Brains** sees `/api/model_brains` (15s).
- No guarantee these are consistent at the same instant. For a trading monitor making promotion/halt decisions, this is unacceptable.

---

## 2. Component Composition & Reusability

### 2.1 Tab / Panel Architecture
**File**: `C:\supreme-chainsaw\frontend\src\App.tsx:320-340` (renderContent switch)

- 15+ specialized panels, each ~150-500 LOC.
- Only a handful receive props from central state:
  - `TrainingPanel`, `PatternsPanel`, `OverviewPanel`, `SettingsPanel`, `TradesPanel` (partial), `DashboardPanel` (legacy).
- Majority are **completely autonomous** (`PipelinePanel`, `ModelBrainsPanel`, `RegistryPanel`, `PromotionGatesPanel`, `DemoCanaryPanel`, `TradeCoronerPanel`, `PerpetualPanel`, `AgentsPanel`, `SafetyPanel`, `EvidenceLockerPanel`).

### 2.2 Reusability Score: Low
**Good**:
- `TruthBadge.tsx` — excellent, used everywhere.
- `LoadingBar.tsx`
- `EquityChart.tsx` (sophisticated, ResizeObserver + heavy useMemo + hover).
- `TrainingLaneCard.tsx`

**Problems**:
- Every panel duplicates:
  - `const colors = { bg, panelBg, border, text, muted, cyan, green, amber, red }`
  - `panelStyle`, `thStyle`, `tdStyle` objects
  - `toneFromStatus` / `brainTone` / `agentTone` functions (nearly identical logic)
- No shared theme file, no CSS modules / styled-components / Tailwind.
- Inline styles dominate in specialized panels (vs CSS classes used in Overview/System bar).
- **Two EquityChart implementations**:
  - Sophisticated: `C:\supreme-chainsaw\frontend\src\components\EquityChart.tsx`
  - Crude inline duplicate: `C:\supreme-chainsaw\frontend\src\components\TradesPanel.tsx:7-68`

### 2.3 Dead / Orphaned Components (Significant Bloat)
Confirmed unused (no imports in App.tsx or elsewhere in src):
- `TradeHistoryPanel.tsx`
- `HFTHealthPanel.tsx`
- `PatternLibraryPanel.tsx`
- `ScenarioMemoryPanel.tsx`
- `TrainingProgressPanel.tsx`
- `ModelsPanel.tsx`
- `AgentTeamPanel.tsx`
- `TradingPanel.tsx`
- `LRTimeline.tsx`

These contain their own polling + complex UI. They represent abandoned experiments and increase maintenance surface.

**Dead imports in App.tsx** (lines 13-24): `fetchPipelineStages`, `fetchModelBrains`, `fetchTrainingLanes`, `fetchRegistry`, etc. — imported but never called (panels bypass them).

---

## 3. Data Fetching Strategy

**File**: `C:\supreme-chainsaw\frontend\src\services\api.ts` (600+ LOC of thin wrappers)

### 3.1 WebSocket (createStatusWS)
**File**: `C:\supreme-chainsaw\frontend\src\services\api.ts:193-244`

- Basic reconnect with exponential backoff (capped at 30s, hard stop after 3 failures).
- Only for `/ws/status` → full `StatusPayload`.
- No message validation, no heartbeat/ping, no partial updates.
- Consumer in App sets entire `status` on every message.

### 3.2 HTTP Fetching
- ~25 `fetch*` functions, all using `cache: 'no-store'`.
- Inconsistent usage: some panels call the helper (`fetchModelBrains`), others raw `fetch` (PipelinePanel:59 does `${''}/api/...`).
- Every autonomous panel implements identical pattern:
  ```ts
  const [data, setData] = useState(...)
  useEffect(() => {
    let cancelled = false
    const load = async () => { ... fetch ... }
    load()
    const id = setInterval(load, 15_000)
    return () => { cancelled=true; clearInterval(id) }
  }, [])
  ```
- App central poll: 10s for side data + conditional status.
- **Result**: When all tabs conceptually "active" (user switching), easily 1 + 12+ concurrent polling timers.

### 3.3 Other Issues
- No React Query / SWR / RTK Query → no deduping, caching, background refetch, optimistic updates, or stale-while-revalidate.
- No request deduplication across panels.
- Error handling is swallow-to-[] / {}.
- No loading vs error distinction in many places.
- `fetchStatus` aliased as `fetchTrainingStatus` (unnecessary).

---

## 4. Routing / Tab System (App.tsx)

**File**: `C:\supreme-chainsaw\frontend\src\App.tsx:52-74, 218, 320-340`

- Pure client state: `const [activeTab, setActiveTab] = useState<TabId>('trades')`
- Large `switch` in `renderContent`.
- **No React Router**, no URL sync, no deep linking.
- Tab buttons in nav; `legacy_dashboard` has no nav entry (only switch case).
- On full page reload or WS reconnect: tab resets to default.
- No persisted preference.

**Production impact**: Operator cannot share "look at the Trade Coroner for BTC right now" via link. History navigation broken for tab changes. Poor for incident post-mortems.

---

## 5. Performance Analysis

### 5.1 Memoization & Re-renders
**Grep results across src**: Only 6 uses of `useMemo` total (mostly inside EquityChart and one table in TradeHistoryPanel).
- **Zero** `React.memo` on any panel component.
- App re-renders on every WS tick → re-creates tab buttons, calls `renderContent()` (new element each time).
- Prop drilling of fresh `status` object (new ref) to panels that receive it causes unnecessary subtree work.

### 5.2 Large Lists (Trades / Patterns)
- **TradesPanel** (`C:\supreme-chainsaw\frontend\src\components\TradesPanel.tsx:246-264`): Renders full `<table>` of all loaded rows (limit 50) with no virtualization. Pagination exists but is offset-based refetch (not client-side).
- Patterns lists similar.
- For production with months of trade history or hundreds of discovered patterns → DOM bloat + slow re-renders on every update.
- No `useMemo` on derived lists (win rate calcs, filtering) in most places.

### 5.3 Other
- LoadingScreen has inline spark animation with randoms (minor).
- No code splitting / lazy panels (all imported eagerly at top of App).

---

## 6. Separation of Concerns

**Current State**: Weak.

- **Data layer** (`services/api.ts`): Mix of pure transport + domain derivation (`extractAgentStatus` builds UI-facing agents from raw payload). No API client class, no interceptors, no typed error handling.
- **UI layer**: Panels own fetching, state, polling, transformation, and JSX. Many contain business logic (e.g. deriving "online" from multiple fields).
- No custom hooks (`useStatus`, `usePipeline`, `useEquityCurve`).
- No Context providers for shared concerns (auth mode, global halt, theme).
- Types split awkwardly between `types.ts` (core domain) and inline interfaces in `api.ts`.
- Styling concerns scattered (inline + global css + duplicate color maps).

**Consequence for trading monitor**: A change to the status payload shape or a new endpoint requires hunting through 15+ files. Hard to add features (e.g. "add alerts on any panel") without duplication.

---

## 7. Additional Observations (Production Readiness)

- **Reliability**: WS failure after 3 attempts silently degrades to 10s polling forever. No user-visible "data may be stale" stronger than a small "POLL" pill.
- **Observability**: No frontend logging of fetch errors, WS reconnects, or data age. Contrast with excellent backend `PIPELINE_DECISIONS.jsonl`.
- **Testing**: No test files visible. Component isolation impossible without heavy mocking.
- **Build / Deploy**: Vite proxy only for dev. Production requires static build + correct nginx/ingress rules (see root `PRODUCTION.md`).
- **Accessibility / Ops**: Good UTC clock and halt pills. Limited keyboard nav in tables.

---

## Prioritized Recommendations (Long-Term Maintainability)

### P0 — Critical for Production Safety & Maintainability
1. **Introduce centralized data layer** (React Query or lightweight Zustand + custom hooks). One `useStatusWS()`, `usePipelineStages()`, etc. Kill per-panel polling.
2. **Unify agent status** — deprecate `extractAgentStatus` or make AgentsPanel consume central status where possible. Document the two sources.
3. **Make all critical data flow through WS or a single coordinated poller** in App (or a provider). Panels become purely presentational or use hooks.
4. **Add data staleness / last-updated indicators** globally (especially when on POLL fallback).

### P1 — High
5. **Extract shared UI primitives**:
   - `theme.ts` or CSS custom properties for all colors/panels.
   - Reusable `Panel`, `DataTable`, `KpiCard` components.
   - Single `useTone(status)` hook.
6. **Delete or archive dead components** and clean dead imports in App.tsx.
7. **Replace duplicate EquityChart** in TradesPanel with the real one (or make the inline one use shared logic).
8. **Add virtualization** (react-window / @tanstack/react-virtual) for Trades, Patterns, Registry tables.
9. **Sync activeTab to URL hash** (or adopt react-router for future deep links/filters).

### P2 — Important for Scale
10. **Adopt React.memo + useMemo** on all expensive panels and list rows. Memoize renderContent or split into tab routes.
11. **Error boundaries + consistent retry UI**.
12. **Request batching / smarter refreshSideData** — only fetch data for the *currently visible* tab + global status.
13. **Type the entire StatusPayload more strictly** (remove `any`); generate types from backend if possible.
14. **Add frontend telemetry** (last fetch times, error counts) surfaced in Settings or a hidden diagnostics tab.

### Quick Wins (Low Effort)
- Standardize every panel to use api.ts helpers (remove raw `fetch`).
- Extract polling hook: `usePolling<T>(fetcher, interval, deps)`.
- Move repeated style objects to a `styles.ts` constants file.
- Add `key` prop discipline and stable references for lists.

---

## Strengths (For Balance)
- Sophisticated EquityChart with interaction, smoothing, drawdown viz.
- TruthBadge is a high-quality reusable primitive.
- Good initial loading experience and visual "trading terminal" aesthetic.
- WS + poll fallback is better than pure polling.
- Some panels (Training, Overview) correctly consume central state.
- Pagination and summary KPIs in Trades are useful.

---

## Conclusion

The current React frontend works for internal monitoring of the v5 autonomous wave but is **architecturally unsustainable** for a production trading system. The hygiene gap versus the carefully-managed TUI/swarm data layer is striking.

Immediate investment in a proper data layer (hooks/query client) + ruthless deduplication of polling/UI primitives will pay for itself the first time an operator needs to trust the monitor during a live incident or promotion decision.

**Recommended next hygiene step**: Create a `useDataLayer` spike (or adopt TanStack Query) that makes every panel dumb and guarantees a single source of truth for StatusPayload + derived entities. Re-run this hygiene review after the spike.

**Files of Primary Concern** (must touch in any refactor):
- `C:\supreme-chainsaw\frontend\src\App.tsx`
- `C:\supreme-chainsaw\frontend\src\services\api.ts`
- All `C:\supreme-chainsaw\frontend\src\components\*Panel.tsx` (especially autonomous ones)
- `C:\supreme-chainsaw\frontend\src\types.ts`
- `C:\supreme-chainsaw\frontend\src\components\TradesPanel.tsx` (duplicate chart)
- `C:\supreme-chainsaw\frontend\src\components\EquityChart.tsx`

---

*Report generated via direct static analysis of source (no runtime execution). All paths absolute per workspace.*