//+------------------------------------------------------------------+
//|                                     ChainGambler_Features.mqh    |
//|  Native MQL5 implementation of core feature engineering.         |
//|  Mirrors a strong, computable subset of Python's ULTIMATE_150    |
//|  (feature_pipeline.py) for hybrid training/execution parity.     |
//|  Uses standard indicators + manual calculations for speed.       |
//+------------------------------------------------------------------+
#property copyright "ChainGambler MQL5 Execution Layer"
#property link      "https://github.com/supreme-chainsaw"

#include "ChainGambler_Types.mqh"

//+------------------------------------------------------------------+
//| Build a single bar's feature vector - 28 features with good      |
//| overlap to Python ULTIMATE_150 / ENGINEERED_V2 (see feature_pipeline.py)
//| Uses native i* indicators + manual for parity & low latency.     |
//| Keep indices + formulas in sync with Types.mqh enum + export JSON|
//+------------------------------------------------------------------+
void GetBarFeatures(const string symbol,
                    ENUM_TIMEFRAMES tf,
                    int shift,
                    double &feat[])
  {
   ArrayResize(feat, CG_FEATURES_PER_BAR);
   ArrayInitialize(feat, 0.0);

   double close = iClose(symbol, tf, shift);
   double open_ = iOpen(symbol, tf, shift);
   double high  = iHigh(symbol, tf, shift);
   double low   = iLow(symbol, tf, shift);
   double prev_close = iClose(symbol, tf, shift+1);
   if(close <= 0) return;

   double eps = 1e-12;
   double range = MathMax(high - low, eps);

   // 0. ret_1
   feat[CG_F_RET_1] = (prev_close > 0) ? (close - prev_close) / (prev_close + eps) : 0;

   // 1. ret_5
   double close_5 = iClose(symbol, tf, shift+5);
   feat[CG_F_RET_5] = (close_5 > 0) ? (close - close_5) / (close_5 + eps) : 0;

   // 2-4. Body / wicks (Python parity)
   feat[CG_F_BODY_RATIO] = (range > 0) ? (close - open_) / range : 0;
   feat[CG_F_UPPER_WICK] = (range > 0) ? (high - MathMax(open_, close)) / range : 0;
   feat[CG_F_LOWER_WICK] = (range > 0) ? (MathMin(open_, close) - low) / range : 0;

   // 5-7. RSI normalized [-1,1] on multiple windows (Python does /100*2-1)
   int hRSI7 = iRSI(symbol, tf, 7, PRICE_CLOSE);
   double rsi7[]; if(CopyBuffer(hRSI7, 0, shift, 1, rsi7) > 0) feat[CG_F_RSI_7_NORM] = (rsi7[0]/100.0)*2.0 - 1.0;
   IndicatorRelease(hRSI7);

   int hRSI14 = iRSI(symbol, tf, 14, PRICE_CLOSE);
   double rsi14[]; if(CopyBuffer(hRSI14, 0, shift, 1, rsi14) > 0) feat[CG_F_RSI_14_NORM] = (rsi14[0]/100.0)*2.0 - 1.0;
   IndicatorRelease(hRSI14);

   int hRSI21 = iRSI(symbol, tf, 21, PRICE_CLOSE);
   double rsi21[]; if(CopyBuffer(hRSI21, 0, shift, 1, rsi21) > 0) feat[CG_F_RSI_21_NORM] = (rsi21[0]/100.0)*2.0 - 1.0;
   IndicatorRelease(hRSI21);

   // 8-9. MACD (12,26,9) main/signal (scaled to price)
   int hMACD = iMACD(symbol, tf, 12, 26, 9, PRICE_CLOSE);
   double macd_main[], macd_sig[];
   if(CopyBuffer(hMACD, 0, shift, 1, macd_main) > 0 && CopyBuffer(hMACD, 1, shift, 1, macd_sig) > 0)
     {
      feat[CG_F_MACD_MAIN] = macd_main[0] / (close * 0.005 + eps);
      feat[CG_F_MACD_SIG]  = macd_sig[0]  / (close * 0.005 + eps);
     }
   IndicatorRelease(hMACD);

   // 10. ATR(14) / close
   int hATR = iATR(symbol, tf, 14);
   double atr[];
   if(CopyBuffer(hATR, 0, shift, 1, atr) > 0)
      feat[CG_F_ATR_14_REL] = atr[0] / (close + eps);
   IndicatorRelease(hATR);

   // 11. BB width (20,2) like Python bb_width
   int hBB = iBands(symbol, tf, 20, 0, 2.0, PRICE_CLOSE);
   double bb_upper[], bb_lower[];
   if(CopyBuffer(hBB, 1, shift, 1, bb_upper) > 0 && CopyBuffer(hBB, 2, shift, 1, bb_lower) > 0)
     {
      double bb_mid = (bb_upper[0] + bb_lower[0]) * 0.5;
      feat[CG_F_BB_WIDTH_20] = (bb_upper[0] - bb_lower[0]) / (MathAbs(bb_mid) + eps);
     }
   IndicatorRelease(hBB);

   // 12. Vol rel (volume / 20-period avg) - use iVolume
   long vol = iVolume(symbol, tf, shift);
   long vol_sum = 0;
   for(int k=0; k<20; k++) vol_sum += iVolume(symbol, tf, shift + k);
   double vol_ma = (vol_sum / 20.0) + eps;
   feat[CG_F_VOL_REL_20] = (vol > 0) ? (vol / vol_ma) : 1.0;

   // 13. Realized vol approx (std of recent rets) - simple 8-bar
   double rets[8];
   double sumr=0, sumr2=0;
   for(int k=0; k<8; k++)
     {
      double c1 = iClose(symbol, tf, shift+k);
      double c0 = iClose(symbol, tf, shift+k+1);
      rets[k] = (c0>0) ? (c1-c0)/(c0+eps) : 0;
      sumr += rets[k]; sumr2 += rets[k]*rets[k];
     }
   double meanr = sumr/8.0;
   feat[CG_F_REALIZED_VOL_8] = MathSqrt(MathMax(sumr2/8.0 - meanr*meanr, 0));

   // 14-15. Range + log vol
   feat[CG_F_RANGE_RATIO] = range / (close + eps);
   feat[CG_F_LOG_VOL] = MathLog(MathMax(vol, 1) + 1.0);

   // 16. Spread est (high-low in bps)
   feat[CG_F_SPREAD_EST] = (range / (close + eps)) * 10000.0;

   // 17-22. Time encodings (sin/cos) - full Python parity
   MqlDateTime dt;
   datetime bar_time = iTime(symbol, tf, shift);
   TimeToStruct(bar_time, dt);
   feat[CG_F_HOUR_SIN]  = MathSin(2.0 * M_PI * dt.hour / 24.0);
   feat[CG_F_HOUR_COS]  = MathCos(2.0 * M_PI * dt.hour / 24.0);
   feat[CG_F_DOW_SIN]   = MathSin(2.0 * M_PI * dt.day_of_week / 7.0);
   feat[CG_F_DOW_COS]   = MathCos(2.0 * M_PI * dt.day_of_week / 7.0);
   feat[CG_F_MONTH_SIN] = MathSin(2.0 * M_PI * (dt.mon) / 12.0);
   feat[CG_F_MONTH_COS] = MathCos(2.0 * M_PI * (dt.mon) / 12.0);

   // 23. Simple HTF trend proxy (close / MA50 -1 ) using MQL iMA
   int hMA = iMA(symbol, tf, 50, 0, MODE_SMA, PRICE_CLOSE);
   double ma50[];
   if(CopyBuffer(hMA, 0, shift, 1, ma50) > 0 && ma50[0] > 0)
      feat[CG_F_HTF_H1_TREND] = (close / ma50[0]) - 1.0;
   IndicatorRelease(hMA);

   // 24. Momentum 21
   double close_21 = iClose(symbol, tf, shift+21);
   feat[CG_F_MOMENTUM_21] = (close_21 > 0) ? (close - close_21) / (close_21 + eps) : 0;

   // 25-26. Z-score / slope proxies (13/21 win)
   // Close z approx using recent MA+std rough (use iStdDev)
   int hStd = iStdDev(symbol, tf, 13, 0, MODE_SMA, PRICE_CLOSE);
   double std13[];
   if(CopyBuffer(hStd, 0, shift, 1, std13) > 0 && std13[0] > eps)
     {
      int hMA13 = iMA(symbol, tf, 13, 0, MODE_SMA, PRICE_CLOSE);
      double ma13buf[];
      if(CopyBuffer(hMA13, 0, shift, 1, ma13buf) > 0)
         feat[CG_F_CLOSE_Z_13] = (close - ma13buf[0]) / std13[0];
      IndicatorRelease(hMA13);
     }
   IndicatorRelease(hStd);

   // Slope proxy (MA diff / lag)
   int hMA21 = iMA(symbol, tf, 21, 0, MODE_SMA, PRICE_CLOSE);
   double ma21[], ma21_lag[];
   if(CopyBuffer(hMA21, 0, shift, 1, ma21) > 0 && CopyBuffer(hMA21, 0, shift+21, 1, ma21_lag) > 0 && MathAbs(ma21_lag[0]) > eps)
      feat[CG_F_SLOPE_21] = (ma21[0] - ma21_lag[0]) / MathAbs(ma21_lag[0]);
   IndicatorRelease(hMA21);

   // 27. Breakout 21 (close / highest21 -1)
   double highest21 = high;
   for(int k=1; k<=21; k++)
     {
      double hk = iHigh(symbol, tf, shift+k);
      if(hk > highest21) highest21 = hk;
     }
   feat[CG_F_BREAKOUT_21] = (highest21 > 0) ? (close / highest21) - 1.0 : 0;

   // Final sanitize
   for(int i=0; i<CG_FEATURES_PER_BAR; i++)
      if(!MathIsValidNumber(feat[i]) || MathAbs(feat[i]) > 1e6)
         feat[i] = 0.0;
  }

//+------------------------------------------------------------------+
//| Build full observation buffer for the model (window x feats)     |
//| Flattens or keeps 2D then caller can reshape.                    |
//| Returns total elements prepared in the CBufferType.              |
//+------------------------------------------------------------------+
bool BuildObservationBuffer(CBufferType *&buf,
                            const string symbol,
                            ENUM_TIMEFRAMES tf,
                            int lookback = CG_DEFAULT_LOOKBACK_BARS)
  {
   if(!buf)
      buf = new CBufferType();
   if(!buf)
      return false;

   int feat_dim = CG_FEATURES_PER_BAR;
   int rows = lookback;
   int total_elems = rows * feat_dim;

   if(!buf.BufferInit(rows, feat_dim, 0.0))
      return false;

   double per_bar[];
   for(int b = 0; b < lookback; b++)
     {
      GetBarFeatures(symbol, tf, b+1, per_bar);  // +1 to avoid current forming bar
      for(int f=0; f<feat_dim && f<ArraySize(per_bar); f++)
        {
         buf.Update(b, f, (TYPE)per_bar[f]);
        }
     }

   // Flatten for typical dense/LSTM input layer expectation (many examples use 1xN)
   buf.Reshape(1, total_elems);

   return true;
  }

//+------------------------------------------------------------------+
//| Simple helper: print feature vector for debugging                |
//+------------------------------------------------------------------+
void DebugPrintFeatures(const double &feat[])
  {
   Print("CG Features sample: ");
   for(int i=0; i<fmin(8, ArraySize(feat)); i++)
      PrintFormat("  [%d]=%.4f", i, feat[i]);
  }
//+------------------------------------------------------------------+
