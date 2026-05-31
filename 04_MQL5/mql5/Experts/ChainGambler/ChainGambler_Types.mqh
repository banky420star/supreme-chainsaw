//+------------------------------------------------------------------+
//|                                        ChainGambler_Types.mqh     |
//|  Common types, constants, and includes for ChainGambler MQL5     |
//|  executor. Part of native inference layer using NeuroNetworksBook|
//|  from 48097.zip.                                                 |
//+------------------------------------------------------------------+
#property copyright "ChainGambler MQL5 Execution Layer"
#property link      "https://github.com/supreme-chainsaw"

// Standard includes (assumes NeuroNetworksBook deployed to MT5 Include)
#ifndef CHAIN_GAMBLER_TYPES
#define CHAIN_GAMBLER_TYPES

#include <NeuroNetworksBook\realization\neuronnet.mqh>
#include <Trade\Trade.mqh>
#include <Arrays\ArrayObj.mqh>

//--- ChainGambler specific constants
#define CG_MODEL_FILE_NAME          "chaingambler_v1.net"
#define CG_DEFAULT_LOOKBACK_BARS    40
#define CG_FEATURES_PER_BAR         28     // Start conservative (subset of ultimate_150)
#define CG_OUTPUT_DIM               3      // [direction, size, target] stub
#define CG_TRADE_LEVEL              0.25
#define CG_LOT                      0.01
#define CG_SL_PIPS                  150
#define CG_TP_PIPS                  300

//--- Feature indices (28 total - explicit parity subset of Python ULTIMATE_150 / ENGINEERED_V2)
// Must stay in sync with Python/feature_pipeline.py core computable feats + export_for_mql5.py feature_names
// and ChainGambler_Features.mqh GetBarFeatures implementation.
enum CG_FEATURE_INDEX
  {
   // Core returns / price action (0-4)
   CG_F_RET_1          = 0,
   CG_F_RET_5          = 1,
   CG_F_BODY_RATIO     = 2,
   CG_F_UPPER_WICK     = 3,
   CG_F_LOWER_WICK     = 4,
   // Momentum / oscillators (5-10)
   CG_F_RSI_7_NORM     = 5,
   CG_F_RSI_14_NORM    = 6,
   CG_F_RSI_21_NORM    = 7,
   CG_F_MACD_MAIN      = 8,
   CG_F_MACD_SIG       = 9,
   CG_F_ATR_14_REL     = 10,
   // Volatility / bands / volume (11-16)
   CG_F_BB_WIDTH_20    = 11,
   CG_F_VOL_REL_20     = 12,
   CG_F_REALIZED_VOL_8 = 13,
   CG_F_RANGE_RATIO    = 14,
   CG_F_LOG_VOL        = 15,
   CG_F_SPREAD_EST     = 16,
   // Time encodings (17-22)
   CG_F_HOUR_SIN       = 17,
   CG_F_HOUR_COS       = 18,
   CG_F_DOW_SIN        = 19,
   CG_F_DOW_COS        = 20,
   CG_F_MONTH_SIN      = 21,
   CG_F_MONTH_COS      = 22,
   // HTF / momentum extensions + z (23-27)
   CG_F_HTF_H1_TREND   = 23,
   CG_F_MOMENTUM_21    = 24,
   CG_F_CLOSE_Z_13     = 25,
   CG_F_SLOPE_21       = 26,
   CG_F_BREAKOUT_21    = 27
  };

//--- Simple struct for observation building
struct SChainGamblerObs
  {
   double            values[];   // flat or will be reshaped in buffer
   int               bars;
   int               feat_dim;
  };

#endif
//+------------------------------------------------------------------+
