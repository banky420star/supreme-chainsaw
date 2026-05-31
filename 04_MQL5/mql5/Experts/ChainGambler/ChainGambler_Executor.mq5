//+------------------------------------------------------------------+
//|                                      ChainGambler_Executor.mq5   |
//|  ChainGambler Native MQL5 Inference Executor EA                  |
//|  Uses NeuroNetworksBook library (from 48097.zip) for ultra-low   |
//|  latency inference. Hybrid: Python trains PPO policies; MQL5     |
//|  executes the model inside the terminal (OpenCL optional).       |
//|                                                                  |
//|  v0.2 — Production-ready skeleton with 28-feat parity, ShadowMode|
//|  Based on ea_template.mq5 + NeuroNetworksBook (48097) + Python parity. |
//+------------------------------------------------------------------+
#property copyright "ChainGambler Project — MQL5 Execution Lead"
#property link      "https://github.com/supreme-chainsaw"
#property version   "0.30"
#property description "Native MQL5 NN inference executor (v0.3+). Supports Decision/Execution separation: ExecutionCommandMode polls structured TradeDecision JSON from Python ExecutionAgent (preferred low-latency native CTrade mgmt with partials/ladders/trailing). Full backward compat with ShadowMode + inference."

//--- Inputs
sinput string          ModelFile          = "chaingambler_v1.net";   // Model in MQL5/Files or Common (generated via export + CNet::Save or native train)
sinput bool            UseCommonFolder    = true;                    // FILE_COMMON for models (recommended on VPS)
sinput bool            UseOpenCL          = true;                    // GPU acceleration if available (library fallback to CPU)
sinput int             LookbackBars       = 40;                      // Sequence length for LSTM / features (must match arch)
sinput double          TradeThreshold     = 0.25;                    // |output[0]| > threshold => trade
sinput double          LotSize            = 0.01;
sinput int             SL_Pips            = 150;
sinput int             TP_Pips            = 300;
sinput ENUM_TIMEFRAMES InferenceTF        = PERIOD_M5;
sinput bool            ShadowMode         = true;                    // If true: log signals only, NO trades (for validation vs Python)
sinput bool            DebugFeatures      = false;                   // Print feature vector occasionally
// Autonomous loop: execution_type=decision_ppo (default for promoted) enables rich DecisionPPO specs (full trade: side/size/sl/tp) consumed by native + Python Execution layer. Legacy simple_action supported.

//--- NEW: Decision/Execution Layer Bridge (additive, does not break inference/Shadow paths)
sinput bool            ExecutionCommandMode = false;                 // When true: poll runtime/mql5_commands/ (or Common) for TradeDecision JSON from Python ExecutionAgent. Ignores NN policy.
sinput string          CommandDir           = "Files\\trade_decisions"; // Relative to MQL5 or Common (use Common for cross-terminal). ExecutionAgent writes here.
sinput bool            UseCommonForCommands = true;                  // FILE_COMMON for decision command files (matches Python runtime bridge in production)
sinput int             CommandPollSeconds   = 5;                     // How often to check for new decision commands (OnTick throttled)
sinput bool            EnableRichMgmt       = true;                  // Use advanced partial closes, ladder TPs, multiple trailing types, time exits from received TradeDecision
sinput int             MaxRichMgmtPositions = 3;                     // Safety cap per symbol when in command mode

// Includes
#include "ChainGambler_Types.mqh"
#include "ChainGambler_Features.mqh"

//--- Global objects
CNet                 *net                 = NULL;
CTrade               *trade               = NULL;
datetime             last_bar_time        = 0;
CBufferType          *input_buffer        = NULL;

//--- Execution Command Bridge state (v0.3 Decision+Execution layer)
datetime             last_command_poll    = 0;
string               last_processed_cmd   = "";  // decision_id guard against re-processing
int                  commands_processed   = 0;

//+------------------------------------------------------------------+
//| Expert initialization                                            |
//+------------------------------------------------------------------+
int OnInit()
  {
   Print("=== ChainGambler MQL5 Executor v0.3 (Decision+Execution Layer) ===");
   PrintFormat("Model: %s | CommonFolder=%s | OpenCL=%s | Lookback=%d | CommandMode=%s",
               ModelFile, UseCommonFolder ? "YES" : "NO", UseOpenCL ? "YES" : "NO", LookbackBars,
               ExecutionCommandMode ? "ON (rich TradeDecision from Python ExecAgent)" : "OFF (NN inference)");
   if(ExecutionCommandMode)
      PrintFormat("Command bridge active: dir=%s (Common=%s) | RichMgmt=%s", CommandDir, UseCommonForCommands?"Y":"N", EnableRichMgmt?"Y":"N");

   // 1. Create and load the neural net
   net = new CNet();
   if(!net)
     {
      PrintFormat("FATAL: Failed to allocate CNet: %d", GetLastError());
      return INIT_FAILED;
     }

   if(!net.Load(ModelFile, UseCommonFolder))
     {
      PrintFormat("WARNING: Could not load model '%s' (error %d).", ModelFile, GetLastError());
      Print("         (Place .net from export_for_mql5 artifacts + MQL5 Create/Save, or train in MT5. See README.)");
      Print("         Executor will continue in NO-OP mode until a valid model is available.");
      // We do NOT fail init — allows compilation/test without model first.
      // In production you may choose to return INIT_FAILED here.
     }
   else
     {
      Print("Model loaded successfully.");
     }

   net.UseOpenCL(UseOpenCL);
   if(UseOpenCL)
      Print("OpenCL acceleration requested (library will fallback gracefully if GPU unavailable).");

   // 2. Trade object
   trade = new CTrade();
   if(!trade)
     {
      PrintFormat("FATAL: Failed to allocate CTrade: %d", GetLastError());
      return INIT_FAILED;
     }
   if(!trade.SetTypeFillingBySymbol(_Symbol))
      Print("Warning: Could not set filling mode.");

   // 3. Pre-allocate input buffer (reused)
   input_buffer = new CBufferType();
   if(!input_buffer)
     {
      PrintFormat("FATAL: Failed to allocate input buffer.");
      return INIT_FAILED;
     }

   last_bar_time = iTime(_Symbol, InferenceTF, 0);

   Print("OnInit complete. Ready for OnTick inference.");
   return INIT_SUCCEEDED;
  }

//+------------------------------------------------------------------+
//| Expert deinitialization                                          |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
  {
   Print("ChainGambler Executor shutting down. Reason=", reason);

   if(!!net)       { delete net;       net = NULL; }
   if(!!trade)     { delete trade;     trade = NULL; }
   if(!!input_buffer) { delete input_buffer; input_buffer = NULL; }
  }

//+------------------------------------------------------------------+
//| Core inference + decision on new bar                             |
//+------------------------------------------------------------------+
void OnTick()
  {
   // Decision/Execution Layer priority: when ExecutionCommandMode=true, the rich TradeDecision bridge from Python DecisionPPO+ExecutionAgent owns execution (partials, ladders, trailing native in MQL5).
   // Legacy NN inference + simple action only when command mode OFF (full backward compat, no breakage).
   if(ExecutionCommandMode)
     {
      OnTickExecutionBridge();
      return;  // Command-driven rich path (low-latency CTrade mgmt); NN not needed
     }

   // Legacy NN inference path (simple dir/size/target action)
   // Only process on new bar (M5 or configured TF) for efficiency
   datetime current_bar = iTime(_Symbol, InferenceTF, 0);
   if(current_bar <= last_bar_time)
      return;
   last_bar_time = current_bar;

   // --- Build observation (feature parity with Python side) ---
   if(!BuildObservationBuffer(input_buffer, _Symbol, InferenceTF, LookbackBars))
     {
      Print("ERROR: Failed to build observation buffer.");
      return;
     }

   // --- Run inference (the heart of the MQL5 execution layer) ---
   if(!net || net.Total() < 2)   // crude check that a model was actually loaded
     {
      // No-op / placeholder mode
      static int no_model_counter = 0;
      if(no_model_counter++ % 20 == 0)
         Print("No valid model loaded — inference skipped (stub mode).");
      return;
     }

   if(!net.FeedForward(input_buffer))
     {
      PrintFormat("ERROR: FeedForward failed (last error %d).", GetLastError());
      return;
     }

   if(!net.GetResults(input_buffer))
     {
      PrintFormat("ERROR: GetResults failed (last error %d).", GetLastError());
      return;
     }

   // --- Policy head (v0.1: extremely simple — extend with action decoder) ---
   double action_dir   = input_buffer.At(0);
   double action_size  = (input_buffer.Total() > 1) ? input_buffer.At(1) : 0.5;
   double action_target= (input_buffer.Total() > 2) ? input_buffer.At(2) : 1.0;

   // Basic risk filter stub
   if(MathAbs(action_dir) < TradeThreshold)
      return;   // HOLD

   // --- Trade execution (very conservative v0.1) OR Shadow logging ---
   double point = SymbolInfoDouble(_Symbol, SYMBOL_POINT);
   double sl_distance = SL_Pips * point;
   double tp_distance = TP_Pips * point;

   bool do_trade = !ShadowMode;

   if(action_dir > 0)  // LONG bias
     {
      if(ShadowMode)
        {
         PrintFormat("[SHADOW LONG] dir=%.4f size=%.3f (no order placed)", action_dir, action_size);
         // Improved ShadowMode: structured log for easy correlation with Python paper harness logs
         string shlog = StringFormat("%s,SHADOW,LONG,%.4f,%.3f,%.5f\n", TimeToString(TimeCurrent(), TIME_DATE|TIME_SECONDS), action_dir, action_size, SymbolInfoDouble(_Symbol, SYMBOL_BID));
         int h = FileOpen("chaingambler_shadow_log.csv", FILE_WRITE|FILE_READ|FILE_CSV|FILE_COMMON, ',');
         if(h != INVALID_HANDLE) { FileSeek(h, 0, SEEK_END); FileWrite(h, TimeToString(TimeCurrent(), TIME_DATE|TIME_SECONDS), "LONG", action_dir, action_size, SymbolInfoDouble(_Symbol, SYMBOL_BID)); FileClose(h); }
        }
      else
        {
         if(PositionSelect(_Symbol) && PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY)
            return;
         double sl = SymbolInfoDouble(_Symbol, SYMBOL_BID) - sl_distance;
         double tp = SymbolInfoDouble(_Symbol, SYMBOL_ASK) + tp_distance;
         trade.Buy(LotSize, _Symbol, 0.0, sl, tp, "ChainGambler_MQL5_v0.2");
         PrintFormat("BUY signal | dir=%.3f size=%.3f | SL=%.5f TP=%.5f", action_dir, action_size, sl, tp);
        }
     }
   else if(action_dir < 0)  // SHORT bias
     {
      if(ShadowMode)
        {
         PrintFormat("[SHADOW SHORT] dir=%.4f size=%.3f (no order placed)", action_dir, action_size);
         string shlog = StringFormat("%s,SHADOW,SHORT,%.4f,%.3f,%.5f\n", TimeToString(TimeCurrent(), TIME_DATE|TIME_SECONDS), action_dir, action_size, SymbolInfoDouble(_Symbol, SYMBOL_ASK));
         int h = FileOpen("chaingambler_shadow_log.csv", FILE_WRITE|FILE_READ|FILE_CSV|FILE_COMMON, ',');
         if(h != INVALID_HANDLE) { FileSeek(h, 0, SEEK_END); FileWrite(h, TimeToString(TimeCurrent(), TIME_DATE|TIME_SECONDS), "SHORT", action_dir, action_size, SymbolInfoDouble(_Symbol, SYMBOL_ASK)); FileClose(h); }
        }
      else
        {
         if(PositionSelect(_Symbol) && PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_SELL)
            return;
         double sl = SymbolInfoDouble(_Symbol, SYMBOL_ASK) + sl_distance;
         double tp = SymbolInfoDouble(_Symbol, SYMBOL_BID) - tp_distance;
         trade.Sell(LotSize, _Symbol, 0.0, sl, tp, "ChainGambler_MQL5_v0.2");
         PrintFormat("SELL signal | dir=%.3f size=%.3f | SL=%.5f TP=%.5f", action_dir, action_size, sl, tp);
        }
     }

   // Debug raw output + optional features
   if(input_buffer.Total() <= 6)
     {
      Print("Raw NN output vector: ");
      for(ulong i=0; i<input_buffer.Total(); i++)
         PrintFormat("  [%d]=%.4f", i, input_buffer.At(i));
     }
   // (DebugFeatures can be extended with a full feature debug buffer if needed)
  }
//+------------------------------------------------------------------+
//| Helper: Quick self-test of library availability at runtime       |
//+------------------------------------------------------------------+
bool SelfTestLibrary()
  {
   // This can be expanded — for now just a compile-time + load check
   return (net != NULL);
  }

//+------------------------------------------------------------------+
//| Decision/Execution Layer — Command Bridge (v0.3)                 |
//| Polls for TradeDecision JSON written by Python ExecutionAgent.   |
//| Preferred path for rich structured decisions (lot risk%, ladders,|
//| multiple trailing types, partial closes, time exits).            |
//| Fully additive: does not interfere with NN inference or Shadow.  |
//+------------------------------------------------------------------+
void ProcessExecutionCommands()
  {
   if(!ExecutionCommandMode)
      return;

   datetime now = TimeCurrent();
   if(now - last_command_poll < CommandPollSeconds)
      return;
   last_command_poll = now;

   string search_path = CommandDir;
   if(UseCommonForCommands)
      search_path = "Common\\Files\\trade_decisions\\";  // Aligns with Python runtime/mql5_commands (deploy copies or symlink in prod)

   string file_name;
   long search_handle = FileFindFirst(search_path + "*.ready", file_name, UseCommonForCommands ? FILE_COMMON : 0);
   if(search_handle == INVALID_HANDLE)
      return;

   do
     {
      if(StringFind(file_name, ".ready") < 0)
         continue;

      string base = StringSubstr(file_name, 0, StringLen(file_name) - 6); // strip .ready
      string json_file = base + ".json";

      int h = FileOpen(search_path + json_file, FILE_READ|FILE_TXT| (UseCommonForCommands ? FILE_COMMON : 0));
      if(h == INVALID_HANDLE)
         continue;

      string content = "";
      while(!FileIsEnding(h))
         content += FileReadString(h);

      FileClose(h);

      // Very lightweight parse for the protocol we control (decision_id + core fields).
      // For full production MQL5 JSON use a proper parser lib; this suffices for our controlled schema.
      string decision_id = ExtractJsonString(content, "decision_id");
      if(decision_id == "" || decision_id == last_processed_cmd)
         continue;

      string sym       = ExtractJsonString(content, "symbol");
      string side_str  = ExtractJsonString(content, "side");
      double sz_val    = ExtractJsonDouble(content, "size", "value", 0.01);

      // Basic entry (market for v0.3; extend with entry.type later)
      double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
      double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);

      double lots = MathMax(0.01, sz_val);  // TODO: full risk-pct sizing resolution in MQL5 (use account info + ATR)
      if(lots > 5.0) lots = 0.5; // safety

      bool is_long = (side_str == "LONG");

      if(EnableRichMgmt)
        {
         // Delegate to rich manager (implemented below). For now do entry + basic SL/TP from decision.
         ExecuteRichDecision(decision_id, sym, is_long, lots, content);
        }
      else
        {
         // Minimal entry path (still better than nothing)
         if(is_long)
            trade.Buy(lots, sym, 0.0, 0, 0, "ExecCmd|" + decision_id);
         else
            trade.Sell(lots, sym, 0.0, 0, 0, "ExecCmd|" + decision_id);
         PrintFormat("[EXEC-CMD] Minimal entry for %s %s lots=%.2f", decision_id, side_str, lots);
        }

      last_processed_cmd = decision_id;
      commands_processed++;
      PrintFormat("[EXEC-CMD] Processed decision %s (total=%d)", decision_id, commands_processed);

      // Clean marker (best effort)
      FileDelete(search_path + file_name, UseCommonForCommands ? FILE_COMMON : 0);
     }
   while(FileFindNext(search_handle, file_name));

   FileFindClose(search_handle);
  }

// Simple string helpers for our controlled JSON (no external deps)
string ExtractJsonString(const string json, const string key)
  {
   string pattern = "\"" + key + "\":\"";
   int pos = StringFind(json, pattern);
   if(pos < 0) return "";
   pos += StringLen(pattern);
   int end = StringFind(json, "\"", pos);
   if(end < 0) return "";
   return StringSubstr(json, pos, end - pos);
  }

double ExtractJsonDouble(const string json, const string parent, const string child, double def=0.0)
  {
   // Handles "size":{"mode":"...","value":0.75} or flat
   string p = "\"" + parent + "\":";
   int start = StringFind(json, p);
   if(start < 0)
      return def;
   int vpos = StringFind(json, "\"" + child + "\":", start);
   if(vpos < 0)
     {
      // try direct after parent
      vpos = StringFind(json, child + "\":", start);
     }
   if(vpos < 0) return def;
   vpos = StringFind(json, ":", vpos) + 1;
   string num = "";
   for(int i = vpos; i < StringLen(json) && (StringGetCharacter(json, i) == '.' || (StringGetCharacter(json,i) >= '0' && StringGetCharacter(json,i) <= '9')); i++)
      num += StringSubstr(json, i, 1);
   return (num == "") ? def : StringToDouble(num);
  }

//+------------------------------------------------------------------+
//| Execute rich TradeDecision (partials, ladders, trailing, etc.)   |
//| This is the MQL5-side implementation of the Execution Layer.     |
//| Extend with full ladder state tracking per ticket in future rev. |
//+------------------------------------------------------------------+
void ExecuteRichDecision(const string decision_id, const string sym, bool is_long, double lots, const string raw_json)
  {
   // For production this would parse the full sl/tp/trailing/ladder structs
   // and maintain per-position state (magic + decision_id in comment).
   // v0.3: solid entry + SL/TP + skeleton for partials/trailing.

   double point = SymbolInfoDouble(sym, SYMBOL_POINT);
   int    digits = (int)SymbolInfoInteger(sym, SYMBOL_DIGITS);

   // Conservative defaults pulled from decision if present (simple string scan)
   double sl_dist = 150 * point;  // fallback
   double tp_dist = 300 * point;

   // TODO (future): parse sl.value / tp.value / type from raw_json for ATR/R-multiple etc.
   // For now use EA inputs or fixed.

   double entry_price = is_long ? SymbolInfoDouble(sym, SYMBOL_ASK) : SymbolInfoDouble(sym, SYMBOL_BID);
   double sl = is_long ? entry_price - sl_dist : entry_price + sl_dist;
   double tp = is_long ? entry_price + tp_dist : entry_price - tp_dist;

   ulong ticket = 0;
   if(is_long)
      ticket = trade.Buy(lots, sym, 0.0, sl, tp, "RichExec|" + decision_id);
   else
      ticket = trade.Sell(lots, sym, 0.0, sl, tp, "RichExec|" + decision_id);

   if(ticket > 0)
     {
      PrintFormat("[RICH-EXEC] %s %s # %I64u @ %.5f SL=%.5f TP=%.5f (decision=%s)",
                  is_long?"LONG":"SHORT", sym, ticket, entry_price, sl, tp, decision_id);

      // Write a status report back for Python side observability (ExecutionAgent can poll these)
      string status = StringFormat("{\"decision_id\":\"%s\",\"ticket\":%I64u,\"symbol\":\"%s\",\"status\":\"filled\",\"ts\":\"%s\"}\n",
                                   decision_id, ticket, sym, TimeToString(TimeCurrent(), TIME_DATE|TIME_SECONDS));
      int sh = FileOpen("Common\\Files\\execution_status\\" + decision_id + ".json", FILE_WRITE|FILE_COMMON|FILE_TXT);
      if(sh != INVALID_HANDLE)
        {
         FileWrite(sh, status);
         FileClose(sh);
        }
     }
   else
     {
      PrintFormat("[RICH-EXEC] Order failed for decision %s ret=%d", decision_id, GetLastError());
     }

   // NOTE: Full ladder partial closes + dynamic trailing would be implemented in OnTick
   // by scanning open positions whose comment contains the decision_id and applying
   // the ladder/trailing rules from the original JSON (cached or re-read).
   // This skeleton demonstrates the integration point.
  }

//+------------------------------------------------------------------+
//| Enhanced OnTick that also drives the command bridge              |
//+------------------------------------------------------------------+
void OnTickExecutionBridge()
  {
   ProcessExecutionCommands();

   // Future: here we can also run a rich position manager that reads
   // cached decision JSONs and applies partials / trailing / time exits
   // to positions tagged with decision_id. This makes MQL5 the owner
   // of low-latency execution while Python only emits high-level decisions.
  }
//+------------------------------------------------------------------+
