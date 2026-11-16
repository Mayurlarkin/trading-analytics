//+------------------------------------------------------------------+
//| TradeReporter.mqh                                                |
//| Sends closed positions to the Trading Analytics API              |
//| (POST /ingest/trades).                                           |
//|                                                                  |
//| How it works: every few seconds (and whenever a deal is added)   |
//| it looks at the account history since the last position it       |
//| reported, builds one record per fully closed position and posts  |
//| them. The API ignores duplicates, so sending a trade twice is    |
//| harmless. If the API is down, nothing is lost: the next sync     |
//| starts from the last successful one, even after a restart.       |
//|                                                                  |
//| NOTE: the NY-close time conversion below mirrors                 |
//| api/app/timezones.py. api/tests/test_mql5_time_rule.py checks    |
//| the algorithm; keep the two in step if you change either.        |
//+------------------------------------------------------------------+
#ifndef TRADE_REPORTER_MQH
#define TRADE_REPORTER_MQH

enum ENUM_TR_TIME_MODE
  {
   TR_TIME_NY_CLOSE     = 0,  // New York + 7h, follows US daylight saving (typical for IFX)
   TR_TIME_FIXED_OFFSET = 1   // Fixed hours ahead of UTC, no daylight saving
  };

class CTradeReporter
  {
private:
   bool     m_enabled;
   bool     m_busy;
   string   m_endpoint;
   string   m_apiKey;
   string   m_tag;
   long     m_magic;
   int      m_timeMode;
   int      m_fixedOffsetSec;
   int      m_backfillDays;
   int      m_batchSize;
   int      m_timeoutMs;
   string   m_gvName;
   datetime m_tieTime;     // the close time that m_tieIds belong to
   ulong    m_tieIds[];    // already-sent positions that closed exactly at m_tieTime

   //--- time ----------------------------------------------------------
   datetime          NthSunday(const int year,const int month,const int n)
     {
      MqlDateTime d;
      ZeroMemory(d);
      d.year = year;
      d.mon  = month;
      d.day  = 1;
      TimeToStruct(StructToTime(d),d);              // fills day_of_week (0 = Sunday)
      int day = 1+(7-d.day_of_week)%7+7*(n-1);
      ZeroMemory(d);
      d.year = year;
      d.mon  = month;
      d.day  = day;
      return(StructToTime(d));
     }

   bool              IsUsDaylightTime(const datetime nyWall)
     {
      MqlDateTime d;
      TimeToStruct(nyWall,d);
      // Clocks jump 02:00 -> 03:00 on the 2nd Sunday of March and fall back 02:00 -> 01:00
      // on the 1st Sunday of November. Wall times in the skipped hour count as standard time,
      // wall times in the repeated hour as daylight time (same as Python's zoneinfo).
      datetime start = NthSunday(d.year,3,2)+3*3600;
      datetime end   = NthSunday(d.year,11,1)+2*3600;
      return(nyWall>=start && nyWall<end);
     }

   datetime          ToUtc(const datetime serverTime)
     {
      if(m_timeMode==TR_TIME_FIXED_OFFSET)
         return(serverTime-m_fixedOffsetSec);
      datetime nyWall = serverTime-7*3600;           // the broker clock is New York + 7h
      return(nyWall+(IsUsDaylightTime(nyWall) ? 4 : 5)*3600);
     }

   string            IsoUtc(const datetime serverTime)
     {
      MqlDateTime d;
      TimeToStruct(ToUtc(serverTime),d);
      return(StringFormat("%04d-%02d-%02dT%02d:%02d:%02d+00:00",d.year,d.mon,d.day,d.hour,d.min,d.sec));
     }

   //--- small helpers -------------------------------------------------
   string            JsonString(string s)
     {
      StringReplace(s,"\\","\\\\");
      StringReplace(s,"\"","\\\"");
      return("\""+s+"\"");
     }

   int               IndexOf(ulong &arr[],const ulong value)
     {
      for(int i=0;i<ArraySize(arr);i++)
         if(arr[i]==value)
            return(i);
      return(-1);
     }

   bool              IsPositionOpen(const ulong id)
     {
      for(int i=PositionsTotal()-1;i>=0;i--)
        {
         ulong ticket = PositionGetTicket(i);
         if(ticket==0)
            continue;
         if((ulong)PositionGetInteger(POSITION_IDENTIFIER)==id)
            return(true);
        }
      return(false);
     }

   void              SortByTime(ulong &ids[],datetime &times[])
     {
      for(int i=1;i<ArraySize(ids);i++)
        {
         ulong    id = ids[i];
         datetime t  = times[i];
         int      j  = i-1;
         while(j>=0 && times[j]>t)
           {
            ids[j+1]   = ids[j];
            times[j+1] = times[j];
            j--;
           }
         ids[j+1]   = id;
         times[j+1] = t;
        }
     }

   //--- state kept between runs ---------------------------------------
   datetime          LoadLastClose(const datetime now)
     {
      if(GlobalVariableCheck(m_gvName))
         return((datetime)(long)GlobalVariableGet(m_gvName));
      return(now-(datetime)m_backfillDays*86400);
     }

   //--- history -> trade records --------------------------------------
   // Finds positions that have an exit deal in the selected history that we have not sent yet.
   void              CollectClosedPositions(const datetime lastClose,ulong &ids[],datetime &closes[])
     {
      ArrayResize(ids,0);
      ArrayResize(closes,0);
      int total = HistoryDealsTotal();
      for(int i=0;i<total;i++)
        {
         ulong deal = HistoryDealGetTicket(i);
         if(deal==0)
            continue;
         long entry = HistoryDealGetInteger(deal,DEAL_ENTRY);
         if(entry!=DEAL_ENTRY_OUT && entry!=DEAL_ENTRY_OUT_BY && entry!=DEAL_ENTRY_INOUT)
            continue;
         long type = HistoryDealGetInteger(deal,DEAL_TYPE);
         if(type!=DEAL_TYPE_BUY && type!=DEAL_TYPE_SELL)
            continue;
         ulong    pid = (ulong)HistoryDealGetInteger(deal,DEAL_POSITION_ID);
         datetime t   = (datetime)HistoryDealGetInteger(deal,DEAL_TIME);
         int      at  = IndexOf(ids,pid);
         if(at>=0)
           {
            if(t>closes[at])
               closes[at] = t;
            continue;
           }
         int size = ArraySize(ids);
         ArrayResize(ids,size+1);
         ArrayResize(closes,size+1);
         ids[size]    = pid;
         closes[size] = t;
        }
      // Drop what an earlier sync already delivered.
      int keep = 0;
      for(int i=0;i<ArraySize(ids);i++)
        {
         bool done = (closes[i]<lastClose) ||
                     (closes[i]==lastClose && m_tieTime==lastClose && IndexOf(m_tieIds,ids[i])>=0);
         if(done)
            continue;
         ids[keep]    = ids[i];
         closes[keep] = closes[i];
         keep++;
        }
      ArrayResize(ids,keep);
      ArrayResize(closes,keep);
     }

   // Returns 1 and the JSON for one trade, or 0 if this position should be skipped.
   int               BuildTradeJson(const ulong id,string &json)
     {
      json = "";
      if(!HistorySelectByPosition(id))
        {
         Print("TradeReporter: cannot read history of position ",id,", skipping it");
         return(0);
        }
      int      total = HistoryDealsTotal();
      string   symbol = "";
      long     magic = 0;
      bool     haveIn = false;
      long     dirType = -1;
      datetime openTime = 0, closeTime = 0;
      double   inVol = 0, inValue = 0, outVol = 0, outValue = 0;
      double   commission = 0, swap = 0, profit = 0, sl = 0, tp = 0;

      for(int i=0;i<total;i++)
        {
         ulong deal = HistoryDealGetTicket(i);
         if(deal==0)
            continue;
         long type = HistoryDealGetInteger(deal,DEAL_TYPE);
         if(type!=DEAL_TYPE_BUY && type!=DEAL_TYPE_SELL)
            continue;                                   // balance operations, credit, etc.
         long     entry = HistoryDealGetInteger(deal,DEAL_ENTRY);
         datetime t     = (datetime)HistoryDealGetInteger(deal,DEAL_TIME);
         double   vol   = HistoryDealGetDouble(deal,DEAL_VOLUME);
         double   price = HistoryDealGetDouble(deal,DEAL_PRICE);

         commission += HistoryDealGetDouble(deal,DEAL_COMMISSION)+HistoryDealGetDouble(deal,DEAL_FEE);
         swap       += HistoryDealGetDouble(deal,DEAL_SWAP);
         profit     += HistoryDealGetDouble(deal,DEAL_PROFIT);

         if(entry==DEAL_ENTRY_IN)
           {
            if(!haveIn)
              {
               haveIn   = true;
               dirType  = type;
               openTime = t;
               symbol   = HistoryDealGetString(deal,DEAL_SYMBOL);
               magic    = HistoryDealGetInteger(deal,DEAL_MAGIC);
              }
            inVol   += vol;
            inValue += vol*price;
           }
         else
            if(entry==DEAL_ENTRY_OUT || entry==DEAL_ENTRY_OUT_BY || entry==DEAL_ENTRY_INOUT)
              {
               if(t>=closeTime)
                 {
                  closeTime = t;
                  sl = HistoryDealGetDouble(deal,DEAL_SL);
                  tp = HistoryDealGetDouble(deal,DEAL_TP);
                 }
               outVol   += vol;
               outValue += vol*price;
              }
        }

      if(!haveIn || inVol<=0 || outVol<=0 || symbol=="")
        {
         Print("TradeReporter: position ",id," has no complete entry/exit in the history, skipping it");
         return(0);
        }
      if(m_magic>=0 && magic!=m_magic)
         return(0);                                      // not one of ours

      string tag = m_tag;
      if(tag=="" && magic!=0)
         tag = "magic-"+(string)magic;
      tag = StringSubstr(tag,0,64);

      // Prices use 5 decimals and money 2, the most the API accepts. Values are strings so
      // no precision is lost on the way.
      json = "{\"ticket\":"+(string)id+
             ",\"symbol\":"+JsonString(symbol)+
             ",\"direction\":\""+(dirType==DEAL_TYPE_BUY ? "buy" : "sell")+"\""+
             ",\"volume\":\""+DoubleToString(inVol,4)+"\""+
             ",\"open_time\":\""+IsoUtc(openTime)+"\""+
             ",\"close_time\":\""+IsoUtc(closeTime)+"\""+
             ",\"open_price\":\""+DoubleToString(inValue/inVol,5)+"\""+
             ",\"close_price\":\""+DoubleToString(outValue/outVol,5)+"\""+
             ",\"sl\":\""+DoubleToString(sl,5)+"\""+
             ",\"tp\":\""+DoubleToString(tp,5)+"\""+
             ",\"commission\":\""+DoubleToString(commission,2)+"\""+
             ",\"swap\":\""+DoubleToString(swap,2)+"\""+
             ",\"profit\":\""+DoubleToString(profit,2)+"\""+
             ",\"strategy_tag\":"+(tag=="" ? "null" : JsonString(tag))+"}";
      return(1);
     }

   //--- http -----------------------------------------------------------
   int               Post(const string body,string &response)
     {
      char   data[];
      char   result[];
      string resultHeaders;
      int    n = StringToCharArray(body,data,0,WHOLE_ARRAY,CP_UTF8);
      ArrayResize(data,n-1);                           // drop the terminating zero
      string headers = "Content-Type: application/json\r\nX-API-Key: "+m_apiKey+"\r\n";
      ResetLastError();
      int code = WebRequest("POST",m_endpoint,headers,m_timeoutMs,data,result,resultHeaders);
      response = CharArrayToString(result,0,WHOLE_ARRAY,CP_UTF8);
      if(code==-1)
        {
         int err = GetLastError();
         if(err==4014)
            Print("TradeReporter: MT5 blocked the request. Add ",m_endpoint," under Tools > Options > ",
                  "Expert Advisors > Allow WebRequest for listed URL (use the address only, e.g. http://127.0.0.1:8000).");
         else
            Print("TradeReporter: could not reach ",m_endpoint," (error ",err,"). Is the API running?");
        }
      return(code);
     }

   // 400/422 mean the server read the request but refused its content.
   bool              IsRejection(const int code)
     {
      return(code==400 || code==422);
     }

   // Posts one batch. Returns false if the sync should stop and be retried later.
   bool              Flush(string &items[],ulong &itemIds[],const int count)
     {
      string body = "";
      int    sendable = 0;
      for(int i=0;i<count;i++)
        {
         if(items[i]=="")
            continue;
         body += (sendable>0 ? "," : "")+items[i];
         sendable++;
        }
      if(sendable==0)
         return(true);

      string response;
      int    code = Post("{\"trades\":["+body+"]}",response);
      if(code==200)
        {
         Print("TradeReporter: sent ",sendable," trade(s): ",response);
         return(true);
        }
      if(!IsRejection(code))
        {
         if(code==401 || code==403)
            Print("TradeReporter: the API key was refused (HTTP ",code,"). Check InpApiKey.");
         else
            if(code!=-1)
               Print("TradeReporter: server answered HTTP ",code,", will retry: ",response);
         return(false);
        }
      // One bad trade rejects the whole batch, so retry them one by one and skip only the bad ones.
      for(int i=0;i<count;i++)
        {
         if(items[i]=="")
            continue;
         string single;
         int    c = Post("{\"trades\":["+items[i]+"]}",single);
         if(c==200)
            continue;
         if(IsRejection(c))
           {
            Print("TradeReporter: position ",itemIds[i]," was rejected (HTTP ",c,") and is skipped: ",single);
            continue;
           }
         return(false);
        }
      return(true);
     }

   void              Run()
     {
      datetime now       = TimeCurrent();
      datetime lastClose = LoadLastClose(now);
      if(!GlobalVariableCheck(m_gvName))
         GlobalVariableSet(m_gvName,(double)lastClose);   // pin the first-run start point
      if(!HistorySelect(lastClose,now+86400))
        {
         Print("TradeReporter: HistorySelect failed");
         return;
        }
      ulong    ids[];
      datetime closes[];
      CollectClosedPositions(lastClose,ids,closes);
      int n = ArraySize(ids);
      if(n==0)
         return;
      SortByTime(ids,closes);

      string   items[];
      ulong    itemIds[];
      datetime itemClose[];
      ulong    sentIds[];
      datetime sentClose[];
      datetime advanceTo  = lastClose;
      datetime holdBefore = 0;             // earliest close time we must not move past
      int      count = 0;
      bool     failed = false;

      ArrayResize(items,m_batchSize);
      ArrayResize(itemIds,m_batchSize);
      ArrayResize(itemClose,m_batchSize);

      for(int i=0;i<=n && !failed;i++)
        {
         bool flushNow = (i==n) || (count>=m_batchSize);
         if(flushNow && count>0)
           {
            if(Flush(items,itemIds,count))
              {
               advanceTo = itemClose[count-1];
               for(int k=0;k<count;k++)
                  if(items[k]!="")
                    {
                     int s = ArraySize(sentIds);
                     ArrayResize(sentIds,s+1);
                     ArrayResize(sentClose,s+1);
                     sentIds[s]   = itemIds[k];
                     sentClose[s] = itemClose[k];
                    }
               count = 0;
              }
            else
              {
               failed = true;
               break;
              }
           }
         if(i==n)
            break;

         // A position that still looks open may just be a partial close, or the platform has not
         // caught up yet. Do not move past it, so it is picked up again.
         if(IsPositionOpen(ids[i]))
           {
            if(holdBefore==0 || closes[i]<holdBefore)
               holdBefore = closes[i];
            continue;
           }
         string json;
         BuildTradeJson(ids[i],json);                 // json stays "" when the position is skipped
         items[count]     = json;
         itemIds[count]   = ids[i];
         itemClose[count] = closes[i];
         count++;
        }

      if(holdBefore!=0 && holdBefore-1<advanceTo)
        {
         advanceTo = holdBefore-1;
         if(advanceTo<lastClose)
            advanceTo = lastClose;
        }
      if(advanceTo<=0)
         return;

      // Remember what was sent at the final second so a later sync does not repeat it.
      if(advanceTo!=m_tieTime)
        {
         ArrayResize(m_tieIds,0);
         m_tieTime = advanceTo;
        }
      for(int k=0;k<ArraySize(sentIds);k++)
         if(sentClose[k]==advanceTo && IndexOf(m_tieIds,sentIds[k])<0)
           {
            int s = ArraySize(m_tieIds);
            ArrayResize(m_tieIds,s+1);
            m_tieIds[s] = sentIds[k];
           }
      if(advanceTo>lastClose)
         GlobalVariableSet(m_gvName,(double)advanceTo);
     }

public:
                     CTradeReporter(void)
     {
      m_enabled        = false;
      m_busy           = false;
      m_magic          = -1;
      m_timeMode       = TR_TIME_NY_CLOSE;
      m_fixedOffsetSec = 0;
      m_backfillDays   = 7;
      m_batchSize      = 100;
      m_timeoutMs      = 5000;
      m_tieTime        = 0;
     }

   // baseUrl: address of the API, e.g. http://127.0.0.1:8000
   // magic: only report positions with this magic number (-1 = all)
   bool              Init(const string baseUrl,const string apiKey,const string strategyTag,
                          const long magic,const int timeMode,const int fixedOffsetHours,
                          const int backfillDays)
     {
      m_enabled = false;
      if(MQLInfoInteger(MQL_TESTER)!=0)
        {
         Print("TradeReporter: running in the strategy tester, nothing will be reported.");
         return(true);
        }
      string url = baseUrl;
      StringTrimLeft(url);
      StringTrimRight(url);
      while(StringLen(url)>0 && StringSubstr(url,StringLen(url)-1,1)=="/")
         url = StringSubstr(url,0,StringLen(url)-1);
      if(StringFind(url,"http://")!=0 && StringFind(url,"https://")!=0)
        {
         Print("TradeReporter: the API address must start with http:// or https://");
         return(false);
        }
      if(StringFind(apiKey,"ta_")!=0 || StringLen(apiKey)<20)
        {
         Print("TradeReporter: paste the full API key (it starts with ta_) into InpApiKey.");
         return(false);
        }
      if(fixedOffsetHours<-12 || fixedOffsetHours>14)
        {
         Print("TradeReporter: the fixed UTC offset must be between -12 and 14 hours.");
         return(false);
        }
      if((ENUM_ACCOUNT_MARGIN_MODE)AccountInfoInteger(ACCOUNT_MARGIN_MODE)!=ACCOUNT_MARGIN_MODE_RETAIL_HEDGING)
         Print("TradeReporter: warning: this is not a hedging account. Netting accounts merge and reverse ",
               "positions, so reported results may not match the broker's report.");

      m_endpoint       = url+"/ingest/trades";
      m_apiKey         = apiKey;
      m_tag            = strategyTag;
      m_magic          = magic;
      m_timeMode       = timeMode;
      m_fixedOffsetSec = fixedOffsetHours*3600;
      m_backfillDays   = MathMax(0,backfillDays);
      m_gvName         = "TA_LAST_CLOSE_"+(string)AccountInfoInteger(ACCOUNT_LOGIN);
      m_enabled        = true;
      Print("TradeReporter: ready, reporting to ",m_endpoint);
      return(true);
     }

   // Call from OnTimer and from OnTradeTransaction (on TRADE_TRANSACTION_DEAL_ADD).
   void              Sync(void)
     {
      if(!m_enabled || m_busy)
         return;
      m_busy = true;
      Run();
      m_busy = false;
     }

   // Prints the JSON for the most recent closed positions without sending anything,
   // so the values can be checked against the MT5 report first.
   void              Preview(const int maxTrades=3)
     {
      if(!m_enabled)
         return;
      datetime now = TimeCurrent();
      if(!HistorySelect(now-(datetime)MathMax(1,m_backfillDays)*86400,now+86400))
        {
         Print("TradeReporter: HistorySelect failed");
         return;
        }
      ulong    ids[];
      datetime closes[];
      CollectClosedPositions(0,ids,closes);
      SortByTime(ids,closes);
      Print("TradeReporter preview: ",ArraySize(ids)," closed position(s) in the last ",
            MathMax(1,m_backfillDays)," day(s). Showing the newest ",maxTrades,". Nothing is sent.");
      int shown = 0;
      for(int i=ArraySize(ids)-1;i>=0 && shown<maxTrades;i--)
        {
         if(IsPositionOpen(ids[i]))
            continue;
         string json;
         if(BuildTradeJson(ids[i],json)==1)
           {
            Print(json);
            shown++;
           }
         HistorySelect(now-(datetime)MathMax(1,m_backfillDays)*86400,now+86400);
        }
     }
  };

#endif
