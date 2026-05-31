# MQL5 Native Execution Layer Design
## Hybrid Python Training + MQL5 Inference for Maximum Profitability

**Date:** 2026-05-27 (updated 2026-05-28 Execution Path Finalization)  
**Author:** Grok (as autonomous lead on profitability)  
**Status:** Strategic decision — highest leverage path for live profitability on real MT5.  
**2026-05-28 Update (Execution Path Finalization Agent):** On Windows + running MT5 terminal, pure Python (OrderManager+MT5Executor, mql5_bridge_enabled=False via MQL5_BRIDGE_ENABLED=0) is now the **recommended primary** for the full stack. Direct interaction is simpler/reliable with full rich TradeDecision + telemetry. MQL5 bridge/EA remains fully supported as **optional high-performance alternative** (MQL5_BRIDGE_ENABLED=1). Paper harness/supervisor/watcher default to primary pure. See DECISION_EXECUTION_ARCHITECTURE.md for details + one-command switch.

---

## 1. Strategic Rationale (Why This Is Best for Profitability)

Pure Python execution (current path) has fundamental limitations for live retail trading:

- Latency from Python ↔ MT5 COM bridge (especially on VPS)
- Process fragility (Python crashes, memory leaks, dependency issues)
- Harder to run 24/7 reliably with minimal supervision
- Slippage and reaction time disadvantages on fast instruments (BTC, XAU)

**Winning pattern for profitable MT5 bots:**

- **Python** = World-class training, complex reward engineering, hyperparameter search, backtesting, per-symbol optimization, champion selection.
- **MQL5 Native** = Ultra-low latency inference + execution inside the terminal, OpenCL acceleration, no external dependencies, maximum robustness.

The `48097.zip` (NeuroNetworksBook library) gives us a **ready, production-oriented** MQL5 neural network engine with:
- LSTM, Multi-Head Attention, GPT-style blocks
- Full backprop + training support (we can even do light online learning later)
- Proper binary model format (`.net` files)
- Built-in OpenCL support
- Working EA template pattern

This is a massive shortcut toward a real-money viable system.

---

## 2. Target Architecture (Hybrid)

```
Python Training Pipeline (current stack + improvements)
    ├── Real MT5 data ingestion
    ├── Hardened reward (TradingReward + slippage + strong DD)
    ├── Real per-symbol backtest metrics
    ├── OOS splits + proper validation
    └── PPO (SB3) with LSTM / future attention policies

         ↓  (Best models exported / distilled)

MQL5 Execution Layer (new track from 48097.zip)
    ├── CNet + CNeuronLSTM / Attention / etc.
    ├── Feature pipeline mirrored from Python (or close enough)
    ├── OnTick inference at M5/H1
    ├── Risk management + trade execution in native MQL5
    └── Optional: OpenCL acceleration
```

**Phased rollout for safety:**
1. Phase A: Python training + Python execution (current) — for paper trading validation.
2. Phase B: Python training + MQL5 inference shadow (compare signals).
3. Phase C: Full MQL5 execution for live champion/canary (primary path).

---

## 3. Technical Analysis of the MQL5 NN Library (from 48097.zip)

### 3.1 Model Format
- Binary files (`.net` extension in the template).
- Saved via `CNet::Save()` / loaded via `CNet::Load(file, common)`.
- Supports `FILE_COMMON` folder.
- The library serializes the entire network structure + weights.

### 3.2 Network Construction
From `neuronnet.mqh`:
- `CNet::Create(CArrayObj *descriptions)` — primary way to build networks.
- `CLayerDescription` objects define each layer (type, activation, size, etc.).
- Supports position encoding (useful for attention/transformer style).

### 3.3 Supported Components (very rich)
- `CNeuronLSTM` — full LSTM with forget/input/output gates + OpenCL kernel.
- `CNeuronMHAttention` / `CNeuronAttention` — multi-head attention.
- `CNeuronGPT` — transformer-style blocks.
- Convolution, BatchNorm, Dropout, etc.
- Multiple activations (in `activations.mqh` / `.py`).

**Full extracted library inventory (C:\Users\Administrator\Downloads\48097_extracted\mql5\Include\NeuroNetworksBook\):**
- `realization/neuronnet.mqh`, `layerdescription.mqh`, `neuronlstm.mqh`, `neuronmhattention.mqh`, `neurongpt.mqh`, `neuronbase.mqh`, `buffer.mqh`, `defines.mqh`, `opencl.mqh`, `activations.mqh`, etc.
- EA template: `Experts/NeuroNetworksBook/ea_template.mq5`
- Test scripts: perceptron, lstm, attention, gpt, convolution, rnn/ under Scripts/NeuroNetworksBook/
- OpenCL kernels: `mult_vect_ocl.cl`, `opencl_program.cl`

### 3.4 EA Usage Pattern (from ea_template.mq5)
```mql5
CNet *net = new CNet();
net.Load("model.net", true);
net.UseOpenCL(true);

// On each bar
CBufferType *input_data = new CBufferType();
... populate from indicators (RSI, MACD, etc.) ...
net.FeedForward(input_data);
net.GetResults(input_data);

// Simple policy head
if (input_data.At(0) > 0) Buy...
else if (input_data.At(0) < 0) Sell...
```

This is **exactly** the lightweight executor we want.

### 3.5 Python ↔ MQL5 Gap
- Python side in the zip uses TensorFlow/Keras for prototyping.
- No automatic weight converter exists.
- We will need either:
  a) A custom converter (Python → MQL5 binary format), or
  b) Re-implement the policy architecture in MQL5 using the same layer descriptions, then train lightweight versions natively or transfer weights manually.

---

## 3.6 MQL5 Agent Analysis Artifact: Current Python Policy Mapping (Delivered 2026-05-27)

**Source:** `tools/analyze_for_mql5_port.py` (first concrete MQL5 track deliverable)

**Current Chain Gambler Policy (post-alignment fixes):**
- Algorithm: PPO (Stable-Baselines3)
- Feature extractor: Adaptive LSTM (on ~150 engineered features from `ultimate_150` pipeline)
- Input: Windowed market features (recent bars) — MACD/RSI/ATR/BB style + custom vol/regime
- Output: Continuous action vector (direction, size, target levels)
- Training objective (hardened): Composite reward blending growth, payoff, sharpe bonus + strong DD tail penalty (weight 8.0, quadratic), cost/slippage (slippage_bps default 2.5 now modeled), commission, churn. See `drl/trading_env.py` + `Python/rewards/reward_function.py`.
- Data source for recent run: Real MT5 historical (BTCUSDm 1h best TF selected via optimization).

**Direct MQL5 Mapping Opportunities:**
- `CNeuronLSTM` (defNeuronLSTM): **Excellent primary match** for adaptive LSTM extractor.
- `CLayerDescription`: Configure type=defNeuronLSTM, count, window (lookback), activation (AF_TANH etc.), optimization.
- Inference flow matches EA template exactly (FeedForward + GetResults on tick/bar).
- Future: `CNeuronMHAttention` for richer policies; OpenCL for <5ms inference.

**Recommended Porting Path (from artifact):**
1. Replicate small LSTM policy head in MQL5 (CNeuronLSTM + dense output head).
2. Mirror core feature set (or close subset) inside MQL5 indicators (or buffer from Python export).
3. Either: (a) Train lightweight native MQL5 version on labeled data, or (b) Implement weight transfer / description exporter from SB3 policy.
4. Executor EA skeleton based on ea_template.mq5 + our risk rules (native MQL5 execution for speed/robustness).

**Evidence Location:** `tools/analyze_for_mql5_port.py` (full console-ready report); 48097_extracted/ tree.

**Before/After for this track:**
- **Before pivot:** Sole reliance on Python ↔ MT5 bridge (latency, fragility).
- **After:** Python = best-in-class training/research engine. MQL5 = production execution layer (low latency, no external deps, OpenCL-ready, 24/7 robust inside terminal).

---

## 4. Phased Implementation Plan

### Phase 0 (Immediate — This Session) — **COMPLETE**
- [x] Deep analysis of library (done via 48097.zip review).
- [x] Create this design document (and live maintenance by Evidence Curator).
- [x] Inventory all layer types and `CLayerDescription` usage (detailed in 3.3 + extracted tree).
- [x] Check current Python policy architecture (LSTM extractor in our code) against what the MQL5 lib supports.
- [x] **Delivered:** `tools/analyze_for_mql5_port.py` — explicit mapping of post-alignment PPO + adaptive LSTM + hardened reward + 150 features. Full library extraction at Downloads/48097_extracted/.

### Phase 1 (Next 1-3 days)
- Build a minimal "feature parity" MQL5 EA skeleton based on `ea_template.mq5`.
- Mirror our current input features (or a strong subset) inside MQL5.
- Create a simple dense or LSTM policy head (CNeuronLSTM primary) that we can train/test natively in MQL5 for baseline comparison.
- Document the exact `CLayerDescription` format needed + first weight description exporter utility.
- **Owner:** MQL5 Execution specialist (parallel to training cycles).

### Phase 2 (Parallel to next training runs)
- Implement or script a weight transfer / distillation path:
  - Option A: Export policy weights from our SB3 model and load into equivalent MQL5 architecture.
  - Option B: Use the MQL5 library's training capability to fine-tune a student model on data labeled by the Python teacher.
- Add OpenCL toggle and performance benchmarking (target <5ms inference).

### Phase 3 (Paper Trading Gate)
- Run the current Python champion **and** the new MQL5 version in parallel during paper trading (shadow mode first).
- Compare realized P&L, slippage, reaction time, robustness, uptime.
- Promote the MQL5 version as primary executor if it wins on reliability + speed.

### Phase 4 (Production)
- Full live champion uses MQL5 executor (hybrid training remains Python).
- Python training continues for research and periodic retraining.
- Possible future: light online learning inside the MQL5 EA using the library's backprop support.

---

## 8. Deep Technical Analysis Findings (48097.zip Library — 2026-05-27 Session)

### 8.1 Core API Summary (from neuronnet.mqh, layerdescription.mqh, defines.mqh, buffer.mqh)

**CNet (main inference engine):**
- `CNet *net = new CNet();`
- Creation: `net.Create(CArrayObj *descriptions)` OR overloads with lr/beta/loss params.
- `net.Load(string file_name, bool common=false)` — binary .net / .nns? (uses FILE_BIN). Supports `FILE_COMMON` folder for shared storage.
- `net.Save(...)` symmetric.
- `net.UseOpenCL(bool)` / `net.UseOpenCL()` — enables GPU kernels (43 kernels registered in InitOpenCL).
- `net.FeedForward(const CBufferType *inputs)` — primary inference call. Expects input layer to be defNeuronBase.
- `net.GetResults(CBufferType *&result)` — retrieves output (often reuse input buffer after reshape or new).
- `net.TrainMode(bool)`, Backpropagation, UpdateWeights for training path (we can ignore for pure inference initially).
- Loss, position encoder, learning rates configurable but secondary for executor.

**CLayerDescription (layer spec):**
```mql5
CLayerDescription *d = new CLayerDescription();
d.type = defNeuronBase | defNeuronLSTM | defNeuronMHAttention | defNeuronGPT | ...;
d.count = neurons/units;
d.window = input_window_size;  // critical for recurrent/attention
d.window_out = ...;            // e.g. keys size or LSTM depth
d.step = heads (for MHAttention/GPT);
d.layers = stacked blocks (GPT);
d.activation = AF_TANH | AF_SIGMOID | AF_SWISH | AF_LINEAR | AF_NONE | ...;
d.optimization = Adam | None | ...;
d.activation_params = VECTOR::Ones(2); // [a,b] for some acts
d.batch = 100;
layers.Add(d);  // CArrayObj
```
**First layer MUST be defNeuronBase with window=0.**

**CBufferType (I/O):**
- Wraps MQL5 `matrix<TYPE>` (double) + optional OpenCL buffer.
- `BufferInit(rows, cols, 0.0)`
- `Update(row, col, val)` or `Update(flat_index, val)`
- `Reshape(1, N)` often used to flatten for dense input.
- `At(i)`, `Total()`, `Row()`, operator[]
- `BufferCreate/OpenCL` methods for GPU path.
- Save/Load per buffer.

**Save/Load Format:**
- Pure binary (FILE_BIN). Header: opencl flag, loss stats, encoder flag, lr, betas, lambdas, loss fn.
- Then position encoder (if used) + full recursive layer serialization via CArrayLayers.
- Models are portable between CPU/OpenCL if rebuilt.

### 8.2 Neuron Types Deep Dive (Production Ready)

- **defNeuronBase** (CNeuronBase): Standard dense/FC + activation. Foundation for gates.
- **defNeuronLSTM** (CNeuronLSTM): Full 4-gate LSTM (forget/input/output/newcontent) using internal Base neurons + recurrent memory/hidden arrays (depth = window_out). Excellent match for our AdaptiveLSTMFeatureExtractor (2-layer 160 hidden). Uses custom OpenCL kernel `def_k_LSTMFeedForward`. State carried across bars via internal buffers.
  - Init: window = prev.count, count=hidden, window_out=depth (min 2).
- **defNeuronAttention / MHAttention**: Query/Key/Value attention. MH has `step`=num_heads, window_out=key_size.
- **defNeuronGPT**: Full decoder-style transformer blocks (multi-layer, FF sub-blocks, layer-norm via internal). Advanced (m_iLayers, m_iUnits, m_iHeads). Overkill for v1 executor.
- Others: Conv, BatchNorm, Dropout, Proof (pooling) — available for richer models.

OpenCL: Automatic when UseOpenCL(true) and Init succeeds. Kernels for all major paths including LSTM/Attention/GPT. Very mature.

### 8.3 EA Pattern (Exact from ea_template.mq5 + lstm_test.mq5)
(See full template in extracted. Key flow reproduced in our ChainGambler_Executor.mq5.)

Typical:
1. OnInit: new CNet(), Load(model.net, true), UseOpenCL(input).
2. Precompute indicators (iRSI, iMACD, iATR, iMA, CopyBuffer for multi-bar window).
3. On new bar: Build CBufferType flat or (bars, feats) matrix from features + history.
4. FeedForward + GetResults.
5. Policy head: simple threshold on output[0] (or multi-dim for size/TP).
6. Trade logic via CTrade, risk checks.
7. Delete buffers each tick.

**Input shaping critical:** Many examples flatten to (1, total_features) for input layer.

### 8.4 Python Policy ↔ MQL5 Mapping (Current State)

**Python (from drl/adaptive_feature_extractor.py + training/train_drl.py + feature_pipeline.py):**
- Obs: window=100 bars × ~150 ultimate engineered feats (OHLC ratios, multi-win RSI/ATR/BB/ret/z-score/momentum/volume + time sin/cos + HTF resamples) + small portfolio state (~6-20).
- Extractor: 2-layer LSTM (input=feat_dim, hidden=160, batch_first) → take last timestep → Linear proj to 256 + concat portfolio → MLP net_arch [512,256] (ReLU) → action head (SB3 MlpPolicy, 6-dim continuous action Box(-1,1)).
- Training: PPO with hardened rewards (growth+DD+slippage costs).
- Persistence: .zip (SB3) + vec_normalize.pkl.

**Mapping to MQL5:**
- **v1 Target (immediate):** Replicate core ~20-30 features (price rel, RSI/MACD/ATR on several windows, volume, time-of-day) using native i* indicators + manual calc. Use 20-40 bar window.
- Architecture for first model:
  - Input: defNeuronBase (window=0, count= flattened_size, activation=AF_NONE)
  - LSTM: defNeuronLSTM (count=64 or 128, window=flattened_per_bar, window_out=2 or 4)
  - Dense: defNeuronBase (count=128, AF_SWISH or TANH, Adam)
  - Output: defNeuronBase (count=3 or 6, AF_LINEAR) for action vector.
- Train equivalent lightweight model **natively in MQL5** using library training (Backprop/Update) on exported MT5 bar data, or.
- **Distillation path:** Python labels actions on historical data → train MQL5 net as student (regression on actions or policy mimic). Or manual weight copy for small dense layers (matrix inspection via Python torch → write binary? complex).
- Gap: No auto converter yet. Python obs ~150 feats vs MQL5 easy ~25-40. Start with feature subset parity (core technicals + returns).

**First model file target:** `models/mql5/chaingambler_lstm_v1.net` (binary, loadable by CNet::Load).

### 8.5 Concrete Next Code Artifacts Produced This Session
- Updated this design doc.
- New project structure: `mql5/Experts/ChainGambler/`
  - `ChainGambler_Executor.mq5` (v0.1 skeleton — loads model, computes basic features, runs FeedForward/GetResults, stub policy + trade).
  - Supporting `ChainGambler_Features.mqh` (mirror of key Python engineered feats using MQL5 indicators).
  - `ChainGambler_Types.mqh` (common defs).
- Deployment note: Copy `48097_extracted/mql5/Include/NeuroNetworksBook/` → MT5 `MQL5/Include/NeuroNetworksBook/`.
- Conversion planning started (see Section 9).
- No full header duplication in repo (to keep lean); references extracted sources.

**Risk/Notes from Analysis:**
- LSTM state persistence across bars: library handles via internal arrays; careful with bar skip / history.
- Matrix sizes must match exactly at Create/FeedForward time.
- OpenCL: Great perf but requires GPU context init; graceful fallback in template.
- File paths: Use `FILE_COMMON` for models in VPS/shared.
- Compilation: Needs `#include <NeuroNetworksBook\realization\neuronnet.mqh>` (after deploy).

This analysis is exhaustive from direct source inspection of all core realization/*.mqh + examples + Python side. Ready for implementation.

---

## 9. Model Conversion / Distillation Path (Python PPO → MQL5)

**High-level plan:**
1. **Feature Parity Layer (MQL5 side):** Implement `ChainGambler_Features.mqh` exporting `GetChainGamblerObservation()` returning CBufferType or double[] matching a documented 30-feature subset of ULTIMATE_150 (document exact formulas).
2. **Architecture Definition:** Hardcode equivalent CLayerDescription stack in a `CreateChainGamblerModel()` helper or load from JSON sidecar + builder.
3. **Weight Transfer (Option A — fast prototype):**
   - Python: export small student net weights (torch.save or numpy matrices for LSTM gates + linears).
   - MQL5: Extend CNet or write a loader that populates internal buffers/weights of created layers (using GetWeights/Set from introspection in lib).
   - Manual for first 1-2 layers.
4. **Distillation / Behavioral Cloning (Option B — robust):**
   - Use Python to run champion PPO over large MT5 history → record (obs_window, teacher_action).
   - Export CSV/Parquet of labeled sequences.
   - In MQL5: Use library's training loop (FeedForward + Backprop + UpdateWeights with MSE on action targets) to train student net on same data.
   - Or hybrid: pre-train in Python with matching arch (use MQL5 neuron definitions in a PyTorch custom module? ambitious), then fine-tune.
5. **Native MQL5 Training Path:** Library fully supports training (see lstm_test.mq5, perceptron examples). We can build "MQL5-only" lightweight policies directly on terminal (good for online adaptation later).
6. **Validation:** Shadow mode — MQL5 and Python predict on identical bars, measure action correlation + downstream P&L delta.
7. **Tooling to build:** Add Python script `tools/export_for_mql5.py` (future) that generates .net or description + weight CSVs.

**Immediate Action:** v0.1 executor uses a hard-coded simple architecture + placeholder model (train one in MQL5 script first).

**Success Gate:** MQL5 executor produces non-crashing inference + sensible (even if not yet optimal) signals on real symbols.

This track is now fully actionable with concrete library knowledge.

---

## 5. Risk Mitigation

- **Model quality risk**: We will not switch live execution until the MQL5 version has proven itself in paper trading with real fills.
- **Feature mismatch risk**: We will maintain a "core feature set" that both Python and MQL5 can compute identically.
- **Complexity risk**: Start with LSTM or simple dense policy heads before attempting attention/GPT blocks.
- **Maintenance**: The MQL5 library becomes a first-class part of the repo (we will copy relevant headers + document them).

---

## 6. Next Immediate Actions (Owner: MQL5 Execution + Evidence Curator)

1. [COMPLETE] Analyze our current Python model architecture (from `training/enhanced_train_drl.py` + policy extractor) and map it to MQL5 layer descriptions. → `tools/analyze_for_mql5_port.py` delivered.
2. Create a small Python utility to help inspect/export policy weights / layer descriptions in a format friendly to MQL5 (CLayerDescription generator).
3. Write the first version of the MQL5 executor EA (skeleton + feature ingestion) in `MQL5/Experts/` (or equivalent) based on ea_template.
4. [COMPLETE] Update the main Go/No-Go document with this new strategic track + cross-links (see Phase 1.5 + Parallel Workstreams section).
5. Continue monitoring the current post-fix validation runs as Validation Run Controller (8k diagnostic ~10:28 stalled post-init, zero candidate/artifacts produced; 50k prepared/ready via updated run_postfix_validation.bat for detached launch — target first usable post-fix model with real backtest metrics + alignment_fix_applied for MQL5 porting/shadow testing). Full eval vs improved scorecard (PromotionGates defaults + model_evaluator) documented in WINDOWS_PRODUCTION_GO_NO_GO_ASSESSMENT.md.
6. Expand this design doc live as MQL5 agent produces further scaffolding / benchmarks.

---

## 7. Success Metrics (for this track)

- MQL5 executor can load a model and run inference on every tick/bar without crashing.
- Inference latency < 5ms on CPU (much better on OpenCL).
- During paper trading, MQL5 version shows equal or better net expectancy than Python version after slippage.
- We can retrain in Python and deploy an updated MQL5 model in < 30 minutes.
- End-to-end: Python champion trained on real MT5 data → exported/described → loads/runs natively in MQL5 EA during live conditions.

---

## 8. Decision Record & Evidence Log (Maintained by Documentation Curator)

| Date | Decision / Milestone | Evidence / Artifact | Notes |
|------|----------------------|---------------------|-------|
| 2026-05-27 | Strategic Pivot to Hybrid (Python Train + MQL5 Exec) | Decision logged in `WINDOWS_PRODUCTION_GO_NO_GO_ASSESSMENT.md`; design doc created | Highest-ROI for real MT5 profitability |
| 2026-05-27 | MQL5 Agent Phase 0 Complete | `tools/analyze_for_mql5_port.py` (policy mapping: PPO+adaptive LSTM → CNeuronLSTM); full 48097_extracted/ library | First concrete deliverable |
| 2026-05-27 | Library Inventory | `C:\Users\Administrator\Downloads\48097_extracted\` (neuronlstm.mqh, ea_template.mq5, OpenCL, tests) | Ready for EA scaffolding |

**This is the path that gives the bot the best chance of being sustainably profitable in real conditions.**

We keep the excellent Python training work we've done (alignment fixes, real metrics, etc.) and add the missing execution robustness piece.

The Evidence Curator will keep both this doc and the master Go/No-Go continuously updated as the MQL5 agent (and parallel streams) deliver further findings, code, and benchmarks.

Next actions: weight exporter utility + first MQL5 EA skeleton.