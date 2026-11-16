//+------------------------------------------------------------------+
//| TradeReporterEA.mq5                                              |
//| Standalone Expert Advisor: attach it to any chart and it reports |
//| every closed position of the account to the Trading Analytics    |
//| API. It never places or changes orders, so it can run next to    |
//| your trading EA without touching it.                             |
//+------------------------------------------------------------------+
#property copyright "trading-analytics"
#property version   "1.00"
#property description "Reports closed positions to the Trading Analytics API. Does not trade."

#include "TradeReporter.mqh"

input string            InpApiUrl           = "http://127.0.0.1:8000"; // API address (no path)
input string            InpApiKey           = "";                      // API key (starts with ta_)
input string            InpStrategyTag      = "";                      // Tag for all trades (empty = magic number)
input long              InpMagicFilter      = -1;                      // Only this magic number (-1 = all trades)
input ENUM_TR_TIME_MODE InpTimeMode         = TR_TIME_NY_CLOSE;        // How to read the broker's clock
input int               InpFixedOffsetHours = 2;                       // Hours ahead of UTC (fixed-offset mode only)
input int               InpBackfillDays     = 7;                       // On the very first run, send this many days back
input int               InpSyncSeconds      = 15;                      // How often to check for closed trades
input bool              InpPreviewOnly      = false;                   // Only print the newest trades, send nothing

CTradeReporter reporter;

int OnInit()
  {
   if(!reporter.Init(InpApiUrl,InpApiKey,InpStrategyTag,InpMagicFilter,InpTimeMode,
                     InpFixedOffsetHours,InpBackfillDays))
      return(INIT_PARAMETERS_INCORRECT);
   if(InpPreviewOnly)
     {
      reporter.Preview();
      return(INIT_SUCCEEDED);
     }
   EventSetTimer(MathMax(5,InpSyncSeconds));
   reporter.Sync();
   return(INIT_SUCCEEDED);
  }

void OnDeinit(const int reason)
  {
   EventKillTimer();
  }

void OnTimer()
  {
   reporter.Sync();
  }

void OnTradeTransaction(const MqlTradeTransaction &trans,
                        const MqlTradeRequest &request,
                        const MqlTradeResult &result)
  {
   if(!InpPreviewOnly && trans.type==TRADE_TRANSACTION_DEAL_ADD)
      reporter.Sync();
  }

void OnTick()
  {
  }
