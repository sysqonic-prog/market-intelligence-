"""
╔══════════════════════════════════════════════════════════════════╗
║   🇮🇳 Indian Market Intelligence v2 — Streamlit Cloud App       ║
║   Stocks + Options | Weekly Expiry | NSE F&O                   ║
║   UPGRADED: GIFT Nifty • Live Futures • Sector Indices         ║
║   Real FII/DII • Accurate Strike Steps • Better Prediction     ║
╚══════════════════════════════════════════════════════════════════╝
"""

import streamlit as st
import pandas as pd
import numpy as np
import datetime, time, warnings, requests, feedparser
warnings.filterwarnings("ignore")

st.set_page_config(
    page_title="🇮🇳 Market Intelligence",
    page_icon="📈", layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
  .stApp{background-color:#0a0e1a;color:#e8eaf6}
  section[data-testid="stSidebar"]{background-color:#111827}
  .block-container{padding:1rem 2rem;max-width:1400px}
  [data-testid="metric-container"]{background:#111827;border:1px solid #1e2a3a;border-radius:10px;padding:12px}
  [data-testid="stMetricLabel"]{font-size:12px!important;color:#64b5f6!important}
  [data-testid="stMetricValue"]{font-size:22px!important;font-weight:800!important}
  .pred-banner{border-radius:12px;padding:20px;text-align:center;margin-bottom:16px;border:2px solid}
  .pred-label{font-size:30px;font-weight:800}
  .status-live{background:#00c85318;border:1px solid #00c85344;color:#00c853;padding:10px 16px;border-radius:8px;font-weight:700;font-size:14px}
  .status-closed{background:#ff525218;border:1px solid #ff525244;color:#ff5252;padding:10px 16px;border-radius:8px;font-weight:700;font-size:14px}
  .section-hdr{font-size:11px;font-weight:700;letter-spacing:2px;text-transform:uppercase;color:#64b5f6;margin-bottom:8px}
  .factor-item{padding:5px 0;font-size:14px;border-bottom:1px solid #1e2a3a}
  .warn-box{background:#ff980018;border:1px solid #ff980044;color:#ff9800;padding:8px 12px;border-radius:6px;font-size:12px;margin:4px 0}
  #MainMenu{visibility:hidden}footer{visibility:hidden}header{visibility:hidden}
  .stButton>button{background:#1565c0!important;color:white!important;border:none!important;font-weight:700!important;padding:8px 20px!important;border-radius:8px!important}
</style>
""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# TIME HELPERS
# ══════════════════════════════════════════════════════════════════════════════
def ist_now():
    return datetime.datetime.utcnow() + datetime.timedelta(hours=5, minutes=30)

def is_market_open():
    t = ist_now(); mins = t.hour*60+t.minute
    return t.weekday()<=4 and 555<=mins<=930  # 9:15–3:30

def is_pre_market():
    t = ist_now(); mins = t.hour*60+t.minute
    return t.weekday()<=4 and 480<=mins<555   # 8:00–9:15

# ══════════════════════════════════════════════════════════════════════════════
# DATA FETCHERS
# ══════════════════════════════════════════════════════════════════════════════
@st.cache_data(ttl=300, show_spinner=False)
def fetch_ohlcv(symbol, period="1y", interval="1d"):
    try:
        import yfinance as yf
        df = yf.Ticker(symbol).history(period=period, interval=interval)
        df.index = pd.to_datetime(df.index)
        return df
    except:
        return pd.DataFrame()

@st.cache_data(ttl=300, show_spinner=False)
def fetch_globals():
    """
    Fetch global indices. During pre-market/market hours, also fetch
    US FUTURES (ES=F, NQ=F) which are more relevant than spot indices.
    GIFT Nifty proxy: NF=F (Nifty Futures) vs previous Nifty close.
    """
    import yfinance as yf

    syms = {
        "S&P 500":     "^GSPC",
        "S&P Futures": "ES=F",       # ← LIVE US futures (pre-market signal)
        "Nasdaq":      "^IXIC",
        "Nq Futures":  "NQ=F",       # ← LIVE Nasdaq futures
        "Dow Jones":   "^DJI",
        "Nikkei 225":  "^N225",
        "Hang Seng":   "^HSI",
        "Crude Oil":   "CL=F",
        "Gold":        "GC=F",
        "USD/INR":     "USDINR=X",
        "India VIX":   "^INDIAVIX",
        "GIFT Nifty":  "NKD=F",      # ← Nifty Dollar Futures (GIFT Nifty proxy)
    }
    out = {}
    for name, sym in syms.items():
        try:
            # Use 5d/1d for overnight change; 1d/5m for intraday live price
            df_d = yf.Ticker(sym).history(period="5d", interval="1d")
            df_i = yf.Ticker(sym).history(period="1d", interval="5m")
            if len(df_d) >= 2:
                prev_close = float(df_d["Close"].iloc[-2])
                # Use latest intraday price if available
                live_price = float(df_i["Close"].iloc[-1]) if not df_i.empty else float(df_d["Close"].iloc[-1])
                chg = round((live_price - prev_close) / prev_close * 100, 2)
                out[name] = {"price": round(live_price, 2), "chg": chg, "prev_close": round(prev_close, 2)}
            elif len(df_d) == 1:
                out[name] = {"price": round(float(df_d["Close"].iloc[-1]), 2), "chg": 0.0, "prev_close": 0.0}
        except:
            out[name] = {"price": 0.0, "chg": 0.0, "prev_close": 0.0}
    return out

@st.cache_data(ttl=300, show_spinner=False)
def fetch_sector_indices():
    """Sector indices for rotation analysis."""
    import yfinance as yf
    sectors = {
        "NIFTY IT":     "^CNXIT",
        "NIFTY AUTO":   "^CNXAUTO",
        "NIFTY PHARMA": "^CNXPHARMA",
        "NIFTY METAL":  "^CNXMETAL",
        "NIFTY FMCG":   "^CNXFMCG",
        "NIFTY REALTY": "^CNXREALTY",
    }
    out = {}
    for name, sym in sectors.items():
        try:
            df = yf.Ticker(sym).history(period="5d", interval="1d")
            if len(df) >= 2:
                p, c = float(df["Close"].iloc[-2]), float(df["Close"].iloc[-1])
                out[name] = {"price": round(c, 2), "chg": round((c-p)/p*100, 2)}
        except:
            out[name] = {"price": 0.0, "chg": 0.0}
    return out

@st.cache_data(ttl=900, show_spinner=False)
def fetch_fii_dii():
    """
    Fetch FII/DII from NSE. If NSE blocks, return empty DataFrame with
    a clear warning — NO synthetic random fallback (that was misleading).
    """
    sess = requests.Session()
    sess.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.nseindia.com/",
        "Connection": "keep-alive",
    })
    rows = []
    source = "NSE Live"
    try:
        sess.get("https://www.nseindia.com", timeout=10)
        time.sleep(1.5)
        r = sess.get("https://www.nseindia.com/api/fiidiiTradeReact", timeout=12)
        if r.status_code == 200:
            data = r.json()
            for e in data:
                fbs = e.get("fiiBuySell", {}); dbs = e.get("diiBuySell", {})
                try:
                    rows.append({
                        "Date":     e.get("date", ""),
                        "FII Net":  float(str(fbs.get("netValue",  0)).replace(",", "")),
                        "DII Net":  float(str(dbs.get("netValue",  0)).replace(",", "")),
                        "FII Buy":  float(str(fbs.get("buyValue",  0)).replace(",", "")),
                        "FII Sell": float(str(fbs.get("sellValue", 0)).replace(",", "")),
                        "DII Buy":  float(str(dbs.get("buyValue",  0)).replace(",", "")),
                        "DII Sell": float(str(dbs.get("sellValue", 0)).replace(",", "")),
                    })
                except: continue
    except: pass

    if not rows:
        source = "UNAVAILABLE"

    df = pd.DataFrame(rows) if rows else pd.DataFrame(
        columns=["Date","FII Net","DII Net","FII Buy","FII Sell","DII Buy","DII Sell"]
    )
    return df, source

@st.cache_data(ttl=600, show_spinner=False)
def fetch_options(symbol="NIFTY"):
    sess = requests.Session()
    sess.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://www.nseindia.com/",
    })
    url = ("https://www.nseindia.com/api/option-chain-indices?symbol=NIFTY"
           if symbol == "NIFTY"
           else "https://www.nseindia.com/api/option-chain-indices?symbol=BANKNIFTY")
    try:
        sess.get("https://www.nseindia.com", timeout=10)
        time.sleep(1.5)
        r = sess.get(url, timeout=12)
        if r.status_code == 200: return r.json(), True
    except: pass
    return None, False

@st.cache_data(ttl=600, show_spinner=False)
def fetch_news():
    feeds = [
        ("Economic Times", "https://economictimes.indiatimes.com/markets/rss.cms"),
        ("Moneycontrol",   "https://www.moneycontrol.com/rss/marketsnews.xml"),
        ("Biz Standard",   "https://www.business-standard.com/rss/markets-106.rss"),
        ("Livemint",       "https://www.livemint.com/rss/markets"),
    ]
    # Context-aware keywords — avoid naive single-word matching
    BULL_PHRASES = ["rally","surge","soar","gain","rise sharply","bull run","strong buy",
                    "positive outlook","growth","record high","52-week high","strong earnings",
                    "beats estimate","inflow","recovery","outperform","upgrade","breakout",
                    "buy rating","optimism","upside","accumulate"]
    BEAR_PHRASES = ["fall sharply","drop","decline","bear market","sell-off","crash","tumble",
                    "negative outlook","loss","52-week low","miss estimate","outflow","concern",
                    "downgrade","breakdown","sell rating","risk","deficit","recession",
                    "inflation spike","weak earnings","underperform","cut rating","fear","panic"]
    arts = []
    for src, url in feeds:
        try:
            fd = feedparser.parse(url)
            for e in fd.entries[:8]:
                t = e.get("title",""); s = e.get("summary","")
                cb = (t+" "+s).lower()
                b  = sum(1 for k in BULL_PHRASES if k in cb)
                br = sum(1 for k in BEAR_PHRASES if k in cb)
                arts.append({
                    "Source": src, "Title": t, "Summary": s[:200],
                    "Link": e.get("link","#"), "Published": e.get("published",""),
                    "Sentiment": "🟢 Bullish" if b>br else "🔴 Bearish" if br>b else "⚪ Neutral",
                    "_bull": b, "_bear": br,
                })
        except: pass
    return arts

# ══════════════════════════════════════════════════════════════════════════════
# TECHNICAL ANALYSIS
# ══════════════════════════════════════════════════════════════════════════════
def compute_ta(df):
    if df.empty or len(df) < 26: return df
    c=df["Close"].astype(float); h=df["High"].astype(float)
    l=df["Low"].astype(float);   v=df["Volume"].astype(float)

    # RSI-14
    d=c.diff(); g=d.clip(lower=0); lo=(-d).clip(lower=0)
    rs=g.rolling(14).mean()/lo.rolling(14).mean().replace(0,np.nan)
    df["RSI"]=100-(100/(1+rs))

    # MACD (12,26,9)
    e12=c.ewm(span=12,adjust=False).mean(); e26=c.ewm(span=26,adjust=False).mean()
    df["MACD"]=e12-e26; df["MACD_Sig"]=df["MACD"].ewm(span=9,adjust=False).mean()
    df["MACD_H"]=df["MACD"]-df["MACD_Sig"]

    # Bollinger Bands (20,2)
    sma20=c.rolling(20).mean(); std20=c.rolling(20).std()
    df["BB_U"]=sma20+2*std20; df["BB_L"]=sma20-2*std20; df["BB_M"]=sma20

    # EMAs
    for sp in [9,21,50,200]: df[f"EMA{sp}"]=c.ewm(span=sp,adjust=False).mean()

    # Supertrend (7, 3)
    tr=pd.concat([h-l,(h-c.shift()).abs(),(l-c.shift()).abs()],axis=1).max(axis=1)
    atr=tr.rolling(7).mean()
    bub=(h+l)/2+3*atr; blb=(h+l)/2-3*atr
    sub=bub.copy(); slb=blb.copy(); trend=pd.Series(1,index=df.index)
    for i in range(1,len(df)):
        sub.iloc[i]=bub.iloc[i] if bub.iloc[i]<sub.iloc[i-1] or c.iloc[i-1]>sub.iloc[i-1] else sub.iloc[i-1]
        slb.iloc[i]=blb.iloc[i] if blb.iloc[i]>slb.iloc[i-1] or c.iloc[i-1]<slb.iloc[i-1] else slb.iloc[i-1]
        if trend.iloc[i-1]==-1 and c.iloc[i]>sub.iloc[i]: trend.iloc[i]=1
        elif trend.iloc[i-1]==1 and c.iloc[i]<slb.iloc[i]: trend.iloc[i]=-1
        else: trend.iloc[i]=trend.iloc[i-1]
    df["ST"]=trend

    # Volume ratio and ADX
    df["Vol_R"]=v/v.rolling(20).mean()

    # ADX (14) — trend strength
    up_move=h-h.shift(); down_move=l.shift()-l
    plus_dm=np.where((up_move>down_move)&(up_move>0),up_move,0)
    minus_dm=np.where((down_move>up_move)&(down_move>0),down_move,0)
    smooth_tr=tr.rolling(14).sum()
    plus_di=100*pd.Series(plus_dm,index=df.index).rolling(14).sum()/smooth_tr.replace(0,np.nan)
    minus_di=100*pd.Series(minus_dm,index=df.index).rolling(14).sum()/smooth_tr.replace(0,np.nan)
    dx=(plus_di-minus_di).abs()/(plus_di+minus_di)*100
    df["ADX"]=dx.rolling(14).mean()
    df["Plus_DI"]=plus_di; df["Minus_DI"]=minus_di

    # Pivot, S/R
    df["Pivot"]=(h+l+c)/3
    df["R1"]=2*df["Pivot"]-l; df["S1"]=2*df["Pivot"]-h
    df["R2"]=df["Pivot"]+(h-l); df["S2"]=df["Pivot"]-(h-l)

    # 52-week high/low
    df["52W_H"]=c.rolling(252).max(); df["52W_L"]=c.rolling(252).min()

    return df

def ta_signals(df):
    if df.empty or len(df)<30: return {"overall":0,"signals":[],"trend":"NEUTRAL"}
    r=df.iloc[-1]; p=df.iloc[-2]; score=0; sigs=[]
    c2=float(r["Close"])

    # RSI
    rsi=float(r.get("RSI",50))
    if rsi<30:    sigs.append(("RSI","OVERSOLD ⚠️",f"{rsi:.1f}","bullish",+2)); score+=2
    elif rsi>75:  sigs.append(("RSI","EXTREMELY OB",f"{rsi:.1f}","bearish",-2)); score-=2
    elif rsi>65:  sigs.append(("RSI","OVERBOUGHT",f"{rsi:.1f}","bearish",-1)); score-=1
    elif rsi>=55: sigs.append(("RSI","BULLISH ZONE",f"{rsi:.1f}","bullish",+1)); score+=1
    elif rsi>=45: sigs.append(("RSI","NEUTRAL",f"{rsi:.1f}","neutral",0))
    else:         sigs.append(("RSI","BEARISH ZONE",f"{rsi:.1f}","bearish",-1)); score-=1

    # MACD
    mh=float(r.get("MACD_H",0)); pmh=float(p.get("MACD_H",0))
    if mh>0 and mh>pmh:    sigs.append(("MACD","BULLISH MOMENTUM",f"{mh:.2f}","bullish",+2)); score+=2
    elif mh>0:             sigs.append(("MACD","BULLISH (Fading)",f"{mh:.2f}","bullish",+1)); score+=1
    elif mh<0 and mh<pmh: sigs.append(("MACD","BEARISH MOMENTUM",f"{mh:.2f}","bearish",-2)); score-=2
    else:                  sigs.append(("MACD","BEARISH (Easing)",f"{mh:.2f}","bearish",-1)); score-=1

    # EMA Stack
    e9=float(r.get("EMA9",c2)); e21=float(r.get("EMA21",c2))
    e50=float(r.get("EMA50",c2)); e200=float(r.get("EMA200",c2))
    if c2>e9>e21>e50>e200:  sigs.append(("EMA Stack","PERFECT UPTREND","Price>9>21>50>200","bullish",+4)); score+=4
    elif c2>e9>e21>e50:     sigs.append(("EMA Stack","STRONG UPTREND","Price>EMA9>21>50","bullish",+3)); score+=3
    elif c2<e9<e21<e50<e200:sigs.append(("EMA Stack","PERFECT DOWNTREND","Price<9<21<50<200","bearish",-4)); score-=4
    elif c2<e9<e21<e50:     sigs.append(("EMA Stack","STRONG DOWNTREND","Price<EMA9<21<50","bearish",-3)); score-=3
    elif c2>e21:            sigs.append(("EMA Stack","MODERATELY BULLISH","Price>EMA21","bullish",+1)); score+=1
    else:                   sigs.append(("EMA Stack","MODERATELY BEARISH","Price<EMA21","bearish",-1)); score-=1

    # Supertrend
    st=int(r.get("ST",1))
    sigs.append(("Supertrend","BULLISH ▲" if st==1 else "BEARISH ▼",
                 "Above support" if st==1 else "Below resistance",
                 "bullish" if st==1 else "bearish",+2 if st==1 else -2))
    score+=2 if st==1 else -2

    # ADX — trend strength filter
    adx=float(r.get("ADX",20))
    pdi=float(r.get("Plus_DI",0)); mdi=float(r.get("Minus_DI",0))
    if adx>25:
        if pdi>mdi: sigs.append(("ADX","STRONG TREND BULL",f"ADX={adx:.0f}, +DI>{mdi:.0f}","bullish",+2)); score+=2
        else:       sigs.append(("ADX","STRONG TREND BEAR",f"ADX={adx:.0f}, -DI>{pdi:.0f}","bearish",-2)); score-=2
    elif adx>20:
        sigs.append(("ADX","MODERATE TREND",f"ADX={adx:.0f}","neutral",0))
    else:
        sigs.append(("ADX","WEAK/RANGING",f"ADX={adx:.0f}","neutral",-1))

    # Bollinger
    bbu=float(r.get("BB_U",c2+1)); bbl=float(r.get("BB_L",c2-1))
    bb_m=float(r.get("BB_M",c2))
    if c2>bbu:   sigs.append(("Bollinger","UPPER BREAKOUT",f"₹{c2:.0f}>₹{bbu:.0f}","bullish",+1)); score+=1
    elif c2<bbl: sigs.append(("Bollinger","LOWER BREAKDOWN",f"₹{c2:.0f}<₹{bbl:.0f}","bearish",-1)); score-=1
    else:
        pos=(c2-bbl)/(bbu-bbl)*100 if bbu!=bbl else 50
        bw=(bbu-bbl)/bb_m*100
        sigs.append(("Bollinger",f"IN BAND @{pos:.0f}%",f"BW={bw:.1f}%","neutral",0))

    # Volume
    vr=float(r.get("Vol_R",1))
    if vr>2.0:   sigs.append(("Volume","VERY HIGH (2x avg)",f"{vr:.2f}x","bullish",+2)); score+=2
    elif vr>1.5: sigs.append(("Volume","HIGH (1.5x avg)",f"{vr:.2f}x","bullish",+1)); score+=1
    elif vr<0.6: sigs.append(("Volume","LOW (weak move)",f"{vr:.2f}x","neutral",-1))
    else:        sigs.append(("Volume","AVERAGE",f"{vr:.2f}x","neutral",0))

    # 52W position
    h52=float(r.get("52W_H",c2*1.2)); l52=float(r.get("52W_L",c2*0.8))
    pos52=(c2-l52)/(h52-l52)*100 if h52!=l52 else 50
    if pos52>90:  sigs.append(("52W Range","NEAR 52W HIGH",f"{pos52:.0f}%ile","bullish",+1)); score+=1
    elif pos52<10:sigs.append(("52W Range","NEAR 52W LOW",f"{pos52:.0f}%ile","bearish",-1)); score-=1
    else:         sigs.append(("52W Range",f"MID RANGE",f"{pos52:.0f}%ile","neutral",0))

    if score>=8:    trend="STRONG BULL 🚀"
    elif score>=4:  trend="BULLISH 📈"
    elif score<=-8: trend="STRONG BEAR 💀"
    elif score<=-4: trend="BEARISH 📉"
    else:           trend="NEUTRAL ↔️"
    return {"overall":score,"signals":sigs,"trend":trend}

# ══════════════════════════════════════════════════════════════════════════════
# OPTIONS ANALYZER
# ══════════════════════════════════════════════════════════════════════════════
def parse_options(oc, spot):
    r={"pcr":0.0,"max_pain":0.0,"support_oi":[],"resistance_oi":[],
       "total_call_oi":0,"total_put_oi":0,"trend":"NEUTRAL","available":False}
    if not oc: return r
    try:
        recs=oc.get("records",{}); dl=recs.get("data",[]); exp=recs.get("expiryDates",[])
        ne=exp[0] if exp else None; sd={}; tce=0; tpe=0
        for item in dl:
            if ne and item.get("expiryDate")!=ne: continue
            s=item.get("strikePrice",0); ce=item.get("CE",{}); pe=item.get("PE",{})
            co=ce.get("openInterest",0) or 0; po=pe.get("openInterest",0) or 0
            tce+=co; tpe+=po
            sd[s]={"ce_oi":co,"pe_oi":po,
                   "ce_chg":ce.get("changeinOpenInterest",0) or 0,
                   "pe_chg":pe.get("changeinOpenInterest",0) or 0}
        r["total_call_oi"]=tce; r["total_put_oi"]=tpe
        r["pcr"]=round(tpe/tce,3) if tce>0 else 0
        r["available"]=tce>0
        # Max Pain
        mp={s:sum(max(0,s-k)*sd[k]["ce_oi"]+max(0,k-s)*sd[k]["pe_oi"] for k in sd) for s in sd}
        if mp: r["max_pain"]=min(mp,key=mp.get)
        below={k:v for k,v in sd.items() if k<=spot}; above={k:v for k,v in sd.items() if k>spot}
        if below: r["support_oi"]=[(s,sd[s]["pe_oi"],sd[s]["pe_chg"]) for s in sorted(below,key=lambda k:below[k]["pe_oi"],reverse=True)[:3]]
        if above: r["resistance_oi"]=[(s,sd[s]["ce_oi"],sd[s]["ce_chg"]) for s in sorted(above,key=lambda k:above[k]["ce_oi"],reverse=True)[:3]]
        # OI change analysis (fresh money vs unwinding)
        total_ce_add=sum(v["ce_chg"] for v in sd.values())
        total_pe_add=sum(v["pe_chg"] for v in sd.values())
        r["ce_oi_change"]=total_ce_add; r["pe_oi_change"]=total_pe_add
        pcr=r["pcr"]
        r["trend"]=("BULLISH (PCR Oversold)" if pcr>1.3 else "MILDLY BULLISH" if pcr>1.0
                    else "BEARISH (PCR Overbought)" if pcr<0.7 else "MILDLY BEARISH" if pcr<1.0 else "NEUTRAL")
    except: pass
    return r

# ══════════════════════════════════════════════════════════════════════════════
# FII/DII ANALYZER
# ══════════════════════════════════════════════════════════════════════════════
def analyze_fii(df):
    if df.empty: return {"available":False}
    df=df.copy()
    df["FII Net"]=pd.to_numeric(df["FII Net"],errors="coerce").fillna(0)
    df["DII Net"]=pd.to_numeric(df["DII Net"],errors="coerce").fillna(0)
    fii5=round(df["FII Net"].tail(5).sum(),2); dii5=round(df["DII Net"].tail(5).sum(),2)
    fii10=round(df["FII Net"].tail(10).sum(),2); dii10=round(df["DII Net"].tail(10).sum(),2)
    # Consecutive buy/sell streak
    streak=0
    for val in df["FII Net"].tail(10).values[::-1]:
        if val>0 and (streak>=0): streak+=1
        elif val<0 and (streak<=0): streak-=1
        else: break
    def classify_fii(v):
        if v>3000: return "HEAVY BUYING",4
        elif v>1500: return "STRONG BUY",3
        elif v>500:  return "BUYING",2
        elif v>0:    return "MILD BUY",1
        elif v>-500: return "MILD SELL",-1
        elif v>-1500:return "SELLING",-2
        elif v>-3000:return "STRONG SELL",-3
        else:        return "HEAVY SELLING",-4
    ft,fs=classify_fii(fii5)
    def classify_dii(v):
        if v>2000: return "STRONG BUY",3
        elif v>500: return "BUYING",2
        elif v>0:   return "MILD BUY",1
        elif v>-500:return "MILD SELL",-1
        else:       return "SELLING",-2
    dt,ds=classify_dii(dii5)
    return {"available":True,
            "fii_5d":fii5,"dii_5d":dii5,"fii_10d":fii10,"dii_10d":dii10,
            "fii_last":round(df["FII Net"].iloc[-1],2),
            "dii_last":round(df["DII Net"].iloc[-1],2),
            "fii_3d":round(df["FII Net"].tail(3).sum(),2),
            "dii_3d":round(df["DII Net"].tail(3).sum(),2),
            "fii_trend":ft,"fii_score":fs,"dii_trend":dt,"dii_score":ds,
            "combined_5d":round(fii5+dii5,2),
            "fii_streak":streak}

# ══════════════════════════════════════════════════════════════════════════════
# GAP PREDICTOR  v2 — more accurate weighting
# ══════════════════════════════════════════════════════════════════════════════
def predict_gap(gcues, fii_a, ta_n, oc_n, arts, sectors):
    score=0; factors=[]

    # ── 1. GIFT Nifty / US Futures (MOST IMPORTANT — 40% weight) ──────────────
    gift = gcues.get("GIFT Nifty", {}).get("chg", 0)
    es_f = gcues.get("S&P Futures", {}).get("chg", 0)
    nq_f = gcues.get("Nq Futures", {}).get("chg", 0)

    if gift != 0:
        # GIFT Nifty is the most direct signal
        if gift > 0.8:   score+=5; factors.append(f"🚀 GIFT Nifty +{gift:.2f}% → Strong Gap Up expected")
        elif gift > 0.3: score+=3; factors.append(f"🟢 GIFT Nifty +{gift:.2f}% → Mild Gap Up expected")
        elif gift > 0:   score+=1; factors.append(f"🟢 GIFT Nifty +{gift:.2f}% → Slight positive open")
        elif gift < -0.8:score-=5; factors.append(f"💀 GIFT Nifty {gift:.2f}% → Strong Gap Down expected")
        elif gift < -0.3:score-=3; factors.append(f"🔴 GIFT Nifty {gift:.2f}% → Mild Gap Down expected")
        else:             score-=1; factors.append(f"🔴 GIFT Nifty {gift:.2f}% → Slight negative open")
    else:
        # Fall back to US futures as proxy
        us_fut = (es_f + nq_f) / 2 if (es_f and nq_f) else es_f or nq_f
        sg  = gcues.get("S&P 500",   {}).get("chg", 0)
        dj  = gcues.get("Dow Jones", {}).get("chg", 0)
        us_spot = (sg + dj) / 2
        us  = us_fut if abs(us_fut) > 0.05 else us_spot  # prefer futures

        if us > 1.0:    score+=4; factors.append(f"🟢 US Markets (Futures) strong +{us:.1f}% → Gap Up signal")
        elif us > 0.3:  score+=2; factors.append(f"🟢 US Markets positive +{us:.1f}% → Mild Gap Up")
        elif us < -1.0: score-=4; factors.append(f"🔴 US Markets (Futures) weak {us:.1f}% → Gap Down signal")
        elif us < -0.3: score-=2; factors.append(f"🔴 US Markets negative {us:.1f}% → Mild Gap Down")
        else: factors.append(f"⚪ US Markets flat {us:.1f}% → Neutral pre-market cue")

    # ── 2. Asian Markets ────────────────────────────────────────────────────────
    nk = gcues.get("Nikkei 225", {}).get("chg", 0)
    hs = gcues.get("Hang Seng",  {}).get("chg", 0)
    asia = (nk + hs) / 2 if (nk and hs) else nk or hs
    if asia > 1.0:    score+=2; factors.append(f"🟢 Asia strong ({nk:+.1f}% NK / {hs:+.1f}% HS)")
    elif asia > 0.3:  score+=1; factors.append(f"🟢 Asia positive ({asia:+.1f}% avg)")
    elif asia < -1.0: score-=2; factors.append(f"🔴 Asia weak ({nk:+.1f}% NK / {hs:+.1f}% HS)")
    elif asia < -0.3: score-=1; factors.append(f"🔴 Asia negative ({asia:+.1f}% avg)")

    # ── 3. Crude Oil (India is net importer — crude up = bad) ──────────────────
    cr = gcues.get("Crude Oil", {}).get("chg", 0)
    if cr > 3:    score-=2; factors.append(f"🔴 Crude spike +{cr:.1f}% → Significant inflation risk")
    elif cr > 1.5:score-=1; factors.append(f"🔴 Crude +{cr:.1f}% → Mild inflation pressure")
    elif cr < -3: score+=2; factors.append(f"🟢 Crude crash {cr:.1f}% → Strong relief for India")
    elif cr < -1.5:score+=1;factors.append(f"🟢 Crude down {cr:.1f}% → Mild relief")

    # ── 4. USD/INR ──────────────────────────────────────────────────────────────
    uc = gcues.get("USD/INR", {}).get("chg", 0)
    if uc > 0.5:    score-=1; factors.append(f"🔴 Rupee weakening {uc:+.2f}% → FII outflow pressure")
    elif uc < -0.5: score+=1; factors.append(f"🟢 Rupee strengthening {uc:+.2f}% → FII inflow friendly")

    # ── 5. India VIX (level + change) ──────────────────────────────────────────
    vix     = gcues.get("India VIX", {}).get("price", 15)
    vix_chg = gcues.get("India VIX", {}).get("chg", 0)
    if vix > 22:      score-=3; factors.append(f"🔴 India VIX HIGH {vix:.1f} (+{vix_chg:+.1f}%) → FEAR — avoid naked options")
    elif vix > 18:    score-=1; factors.append(f"🟡 India VIX ELEVATED {vix:.1f} → Caution")
    elif vix < 12:    score+=2; factors.append(f"🟢 India VIX VERY LOW {vix:.1f} → Calm, bullish bias")
    elif vix < 15:    score+=1; factors.append(f"🟢 India VIX low {vix:.1f} → Stable conditions")
    if vix_chg > 5:   score-=1; factors.append(f"⚠️ VIX jumped {vix_chg:+.1f}% — sudden fear spike")
    elif vix_chg < -5:score+=1; factors.append(f"🟢 VIX fell {vix_chg:+.1f}% — fear easing")

    # ── 6. FII/DII (30% weight) ─────────────────────────────────────────────────
    if fii_a.get("available"):
        fs = fii_a.get("fii_score", 0); ds = fii_a.get("dii_score", 0)
        streak = fii_a.get("fii_streak", 0)
        score += fs + round(ds * 0.4)
        factors.append(f"{'🟢' if fs>0 else '🔴' if fs<0 else '⚪'} FII 5D: {fii_a.get('fii_trend','N/A')} (₹{fii_a.get('fii_5d',0):+.0f} Cr)")
        factors.append(f"{'🟢' if ds>0 else '🔴' if ds<0 else '⚪'} DII 5D: {fii_a.get('dii_trend','N/A')} (₹{fii_a.get('dii_5d',0):+.0f} Cr)")
        if abs(streak) >= 3:
            streak_score = 1 if streak > 0 else -1
            score += streak_score
            factors.append(f"{'🟢' if streak>0 else '🔴'} FII on {abs(streak)}-day {'buying' if streak>0 else 'selling'} streak → momentum {'bullish' if streak>0 else 'bearish'}")
    else:
        factors.append("⚪ FII/DII: NSE API unavailable — not factored into prediction")

    # ── 7. Technical Analysis (15% weight) ──────────────────────────────────────
    ta = ta_n.get("overall", 0); ta_adj = max(-3, min(3, ta // 2)); score += ta_adj
    factors.append(f"{'🟢' if ta_adj>0 else '🔴' if ta_adj<0 else '⚪'} TA Signals: {ta_n.get('trend','NEUTRAL')} (score {ta:+d})")

    # ── 8. Options Chain — PCR + OI Change ──────────────────────────────────────
    if oc_n.get("available"):
        pcr = oc_n.get("pcr", 1.0)
        ce_chg = oc_n.get("ce_oi_change", 0); pe_chg = oc_n.get("pe_oi_change", 0)
        if pcr > 1.5:   score+=2; factors.append(f"🟢 PCR {pcr:.2f} → VERY bearish options, strong reversal up likely")
        elif pcr > 1.2: score+=1; factors.append(f"🟢 PCR {pcr:.2f} → Put heavy, bullish bias")
        elif pcr < 0.6: score-=2; factors.append(f"🔴 PCR {pcr:.2f} → VERY bullish options, reversal down likely")
        elif pcr < 0.8: score-=1; factors.append(f"🔴 PCR {pcr:.2f} → Call heavy, bearish bias")
        else: factors.append(f"⚪ PCR {pcr:.2f} → Balanced options market")
        # OI buildup direction
        if pe_chg > ce_chg and pe_chg > 0:
            score+=1; factors.append(f"🟢 Fresh PE OI buildup ({pe_chg/1000:.0f}K) → Support forming")
        elif ce_chg > pe_chg and ce_chg > 0:
            score-=1; factors.append(f"🔴 Fresh CE OI buildup ({ce_chg/1000:.0f}K) → Resistance forming")
    else:
        factors.append("⚪ Options Chain: NSE API unavailable — PCR not factored")

    # ── 9. Sector Rotation ───────────────────────────────────────────────────────
    if sectors:
        advancing = sum(1 for s in sectors.values() if s.get("chg",0)>0)
        total_sec = len(sectors)
        breadth = advancing / total_sec * 100
        if breadth >= 80:   score+=1; factors.append(f"🟢 Sector breadth {breadth:.0f}% advancing → Broad rally")
        elif breadth <= 20: score-=1; factors.append(f"🔴 Sector breadth {breadth:.0f}% advancing → Broad selloff")
        # Bank sector weight (heavy in Nifty)
        bank_chg = sectors.get("NIFTY AUTO",{}).get("chg",0)  # proxy if BankNifty already counted

    # ── 10. News Sentiment ───────────────────────────────────────────────────────
    bull_n = sum(1 for a in arts if "Bullish" in a.get("Sentiment",""))
    bear_n = sum(1 for a in arts if "Bearish" in a.get("Sentiment",""))
    ns = (bull_n - bear_n) / (len(arts) or 1) * 100
    if ns > 40:    score+=1; factors.append(f"🟢 News strongly BULLISH ({bull_n} bull / {bear_n} bear)")
    elif ns > 20:  factors.append(f"🟢 News mildly bullish")
    elif ns < -40: score-=1; factors.append(f"🔴 News strongly BEARISH ({bear_n} bear / {bull_n} bull)")
    elif ns < -20: factors.append(f"🔴 News mildly bearish")

    # ── Final verdict ────────────────────────────────────────────────────────────
    if score>=10:   lbl="STRONG GAP UP 🚀";     rng="+0.8% to +1.5%"; clr="#00c853"; conf=min(95,65+score*2); act="BUY CALLS at open. Strong follow-through likely. SL below opening candle low."
    elif score>=5:  lbl="GAP UP 📈";             rng="+0.3% to +0.8%"; clr="#69f0ae"; conf=min(82,55+score*2); act="BUY CALLS at slight dip from open (9:17–9:25 AM). Watch for 9:20 AM reversal."
    elif score>=2:  lbl="MILD GAP UP / FLAT 🟡"; rng="0% to +0.3%";    clr="#ffeb3b"; conf=min(65,48+score*2); act="WAIT 15 min after open. Confirm direction. Consider strangle if unclear."
    elif score>=-2: lbl="FLAT ↔️";               rng="-0.2% to +0.2%"; clr="#b0bec5"; conf=max(40,50+score); act="STRADDLE/STRANGLE at ATM. Sell premium if VIX <15. Market range-bound."
    elif score>=-5: lbl="MILD GAP DOWN 🔴";      rng="-0.3% to -0.6%"; clr="#ff7043"; conf=min(70,52+abs(score)*2); act="BUY PUTS. Wait for 9:20 AM confirm candle. SL above opening candle high."
    elif score>=-9: lbl="GAP DOWN 📉";            rng="-0.6% to -1.2%"; clr="#ff5252"; conf=min(85,58+abs(score)*2); act="BUY PUTS aggressively at open. Strong selling likely. SL above prev day high."
    else:           lbl="STRONG GAP DOWN ⚠️";    rng="-1.2% to -2%";   clr="#b71c1c"; conf=min(95,65+abs(score)*2); act="SHORT STRANGLE or BUY PUTS. Major event-driven selloff expected."

    return {"prediction":lbl,"gap_range":rng,"color":clr,"confidence":conf,
            "raw_score":score,"action":act,"factors":factors}

# ══════════════════════════════════════════════════════════════════════════════
# STOCK SCANNER  v2 — proper strike steps
# ══════════════════════════════════════════════════════════════════════════════
# Strike step sizes per stock (NSE standard lot sizes)
STRIKE_STEPS = {
    "RELIANCE":100,"TCS":100,"HDFCBANK":50,"INFY":50,"ICICIBANK":20,
    "KOTAKBANK":20,"AXISBANK":20,"SBIN":20,"LT":50,"WIPRO":20,
    "BAJFINANCE":100,"MARUTI":200,"TATAMOTORS":20,"SUNPHARMA":50,
    "BHARTIARTL":20,"TITAN":50,"ITC":10,"HINDALCO":20,"TATASTEEL":20,"ADANIENT":50,
}
FNO = {
    "RELIANCE":"RELIANCE.NS","TCS":"TCS.NS","HDFCBANK":"HDFCBANK.NS","INFY":"INFY.NS",
    "ICICIBANK":"ICICIBANK.NS","KOTAKBANK":"KOTAKBANK.NS","AXISBANK":"AXISBANK.NS",
    "SBIN":"SBIN.NS","LT":"LT.NS","WIPRO":"WIPRO.NS","BAJFINANCE":"BAJFINANCE.NS",
    "MARUTI":"MARUTI.NS","TATAMOTORS":"TATAMOTORS.NS","SUNPHARMA":"SUNPHARMA.NS",
    "BHARTIARTL":"BHARTIARTL.NS","TITAN":"TITAN.NS","ITC":"ITC.NS",
    "HINDALCO":"HINDALCO.NS","TATASTEEL":"TATASTEEL.NS","ADANIENT":"ADANIENT.NS",
}

@st.cache_data(ttl=600, show_spinner=False)
def scan_stocks(bias_score):
    bias = "BULLISH" if bias_score>=2 else "BEARISH" if bias_score<=-2 else "NEUTRAL"
    results=[]
    for name, sym in FNO.items():
        try:
            df=fetch_ohlcv(sym,"6mo")
            df=compute_ta(df)
            if df.empty or len(df)<30: continue
            sig=ta_signals(df); row=df.iloc[-1]; prev=df.iloc[-2]
            ltp=round(float(row["Close"]),2)
            chg=round((ltp-float(prev["Close"]))/float(prev["Close"])*100,2)
            rsi=round(float(row.get("RSI",50)),1)
            vr=round(float(row.get("Vol_R",1)),2)
            r1=round(float(row.get("R1",ltp*1.01)),2); s1=round(float(row.get("S1",ltp*0.99)),2)
            r2=round(float(row.get("R2",ltp*1.02)),2); s2=round(float(row.get("S2",ltp*0.98)),2)
            adx=round(float(row.get("ADX",15)),1)
            h52=round(float(row.get("52W_H",ltp*1.2)),2)
            l52=round(float(row.get("52W_L",ltp*0.8)),2)

            # Setup score — bias alignment
            ss=sig["overall"]
            if bias=="BULLISH" and sig["overall"]>0: ss+=3
            elif bias=="BEARISH" and sig["overall"]<0: ss+=3
            # ADX filter — only trade strong trends
            if adx<18: ss=ss//2  # halve score if trend is weak

            step=STRIKE_STEPS.get(name,50)
            atm=int(round(ltp/step)*step)

            if ss>=6:
                tt="🟢 BUY CE"; strike=int(round((ltp*1.005)/step)*step)
                tgt=round(ltp*1.03,1); sl=round(ltp*0.985,1)
                tim="9:20–9:30 AM (green candle + volume confirm)"
            elif ss<=-6:
                tt="🔴 BUY PE"; strike=int(round((ltp*0.995)/step)*step)
                tgt=round(ltp*0.97,1); sl=round(ltp*1.015,1)
                tim="9:20–9:30 AM (red candle + volume confirm)"
            elif ss>=3:
                tt="🟡 BULL CALL SPREAD"; strike=atm
                tgt=round(ltp*1.02,1); sl=round(ltp*0.99,1)
                tim="9:30–9:45 AM (pullback to support)"
            elif ss<=-3:
                tt="🟡 BEAR PUT SPREAD"; strike=atm
                tgt=round(ltp*0.98,1); sl=round(ltp*1.01,1)
                tim="9:30–9:45 AM (bounce rejection)"
            else:
                tt="⚪ SKIP / NEUTRAL"; strike=atm; tgt=ltp; sl=ltp; tim="—"

            results.append({
                "name":name,"ltp":ltp,"chg":chg,"rsi":rsi,"trend":sig["trend"],
                "ss":ss,"vr":vr,"adx":adx,"r1":r1,"s1":s1,"r2":r2,"s2":s2,
                "h52":h52,"l52":l52,"tt":tt,"strike":strike,
                "tgt":tgt,"sl":sl,"tim":tim,
            })
        except: continue
    results.sort(key=lambda x: abs(x["ss"]),reverse=True)
    return results

# ══════════════════════════════════════════════════════════════════════════════
# BACKTESTER
# ══════════════════════════════════════════════════════════════════════════════
def run_backtest(df):
    if df.empty or len(df)<60: return None
    df=compute_ta(df.copy()).dropna(); results=[]; lookback=min(len(df)-30,252)
    for i in range(30,30+lookback-1):
        if i+1>=len(df): break
        row=df.iloc[i]; nxt=df.iloc[i+1]
        pc=float(row["Close"]); no=float(nxt["Open"])
        gap=(no-pc)/pc*100
        # Use the same multi-factor logic as the prediction engine (simplified)
        sc=0
        rsi=float(row.get("RSI",50))
        if rsi<35: sc+=2
        elif rsi>65: sc-=2
        sc+=(2 if float(row.get("MACD_H",0))>0 else -2)
        sc+=(2 if int(row.get("ST",1))==1 else -2)
        adx=float(row.get("ADX",15))
        if adx>25:
            sc+=(1 if float(row.get("Plus_DI",0))>float(row.get("Minus_DI",0)) else -1)
        e21=float(row.get("EMA21",pc)); e50=float(row.get("EMA50",pc))
        if pc>e21>e50: sc+=2
        elif pc<e21<e50: sc-=2
        vr=float(row.get("Vol_R",1))
        if vr>1.5: sc+=1 if sc>0 else -1  # volume confirms direction

        pred="up" if sc>=4 else "down" if sc<=-4 else "flat"
        actual="up" if gap>0.25 else "down" if gap<-0.25 else "flat"
        correct=pred==actual
        pnl=(max(80,abs(gap)*25)*50) if correct and pred!="flat" else (-max(80,abs(gap)*25)*25 if pred!="flat" else 0)
        results.append({"date":df.index[i+1].strftime("%d %b %Y"),
                        "gap_pct":round(gap,3),"pred":pred.upper(),
                        "actual":actual.upper(),"correct":correct,"pnl":round(pnl)})
    if not results: return None
    total=len(results); correct_n=sum(1 for r in results if r["correct"])
    wr=round(correct_n/total*100,1); tpnl=sum(r["pnl"] for r in results)
    run=peak=mdd=cw=cl=mws=mls=0
    for r in results:
        run+=r["pnl"]; peak=max(peak,run); mdd=max(mdd,peak-run)
        if r["correct"]: cw+=1; cl=0; mws=max(mws,cw)
        else: cl+=1; cw=0; mls=max(mls,cl)
    return {"total":total,"correct":correct_n,"win_rate":wr,"total_pnl":round(tpnl),
            "avg_pnl":round(tpnl/total),"max_dd":round(mdd),
            "mws":mws,"mls":mls,"recent":results[-15:]}

# ══════════════════════════════════════════════════════════════════════════════
# MAIN APP
# ══════════════════════════════════════════════════════════════════════════════
def main():
    # Auto-refresh
    try:
        from streamlit_autorefresh import st_autorefresh
        if is_market_open():
            st_autorefresh(interval=900_000, key="mkt_refresh")  # 15 min during market
        elif is_pre_market():
            st_autorefresh(interval=300_000, key="pre_refresh")   # 5 min pre-market
    except: pass

    # Status bar
    if is_market_open():
        st.markdown('<div class="status-live">🟢 <b>MARKET LIVE</b> — Auto-refreshing every 15 minutes. Data current as of latest fetch.</div>', unsafe_allow_html=True)
    elif is_pre_market():
        st.markdown('<div class="status-live">🟡 <b>PRE-MARKET</b> — Refreshing every 5 min. GIFT Nifty and US Futures live.</div>', unsafe_allow_html=True)
    else:
        st.markdown(f'<div class="status-closed">🔴 <b>MARKET CLOSED</b> — Showing last data. Next session: Mon–Fri 9:15 AM IST</div>', unsafe_allow_html=True)

    # Header
    col_t, col_btn = st.columns([5,1])
    with col_t:
        st.markdown("## 🇮🇳 Indian Market Intelligence")
        st.markdown(f"*Stocks + Options | Weekly Expiry | v2.0 | {ist_now().strftime('%d %b %Y, %I:%M %p')} IST*")
    with col_btn:
        st.write("")
        if st.button("🔄 Refresh Now", use_container_width=True):
            st.cache_data.clear(); st.rerun()

    st.divider()

    # Load data
    with st.spinner("⏳ Fetching live market data..."):
        ndf   = fetch_ohlcv("^NSEI",    "1y")
        bdf   = fetch_ohlcv("^NSEBANK", "1y")
        gcues = fetch_globals()
        sectors = fetch_sector_indices()
        fii_df, fii_source = fetch_fii_dii()
        fii_a  = analyze_fii(fii_df)
        spot   = float(ndf["Close"].iloc[-1]) if not ndf.empty else 22000
        spot_b = float(bdf["Close"].iloc[-1]) if not bdf.empty else 48000
        oc_raw, oc_ok = fetch_options("NIFTY")
        oc_n   = parse_options(oc_raw, spot)
        arts   = fetch_news()
        ndf_ta = compute_ta(ndf.copy()) if not ndf.empty else ndf
        bdf_ta = compute_ta(bdf.copy()) if not bdf.empty else bdf
        ta_n   = ta_signals(ndf_ta)
        ta_b   = ta_signals(bdf_ta)
        gp     = predict_gap(gcues, fii_a, ta_n, oc_n, arts, sectors)

    # Index overview
    n_chg = ((float(ndf["Close"].iloc[-1])-float(ndf["Close"].iloc[-2]))/float(ndf["Close"].iloc[-2])*100) if len(ndf)>=2 else 0
    b_chg = ((float(bdf["Close"].iloc[-1])-float(bdf["Close"].iloc[-2]))/float(bdf["Close"].iloc[-2])*100) if len(bdf)>=2 else 0
    gift_p = gcues.get("GIFT Nifty",{}).get("price",0)
    gift_c = gcues.get("GIFT Nifty",{}).get("chg",0)
    vix_p  = gcues.get("India VIX",{}).get("price",0)
    vix_c  = gcues.get("India VIX",{}).get("chg",0)
    bull_n = sum(1 for a in arts if "Bullish" in a.get("Sentiment",""))
    bear_n = sum(1 for a in arts if "Bearish" in a.get("Sentiment",""))

    c1,c2,c3,c4,c5 = st.columns(5)
    c1.metric("NIFTY 50",    f"₹{spot:,.2f}",   f"{n_chg:+.2f}%")
    c2.metric("BANK NIFTY",  f"₹{spot_b:,.2f}", f"{b_chg:+.2f}%")
    c3.metric("GIFT Nifty",  f"{gift_p:,.2f}" if gift_p else "N/A", f"{gift_c:+.2f}%" if gift_p else "Unavailable")
    c4.metric("India VIX",   f"{vix_p:.2f}" if vix_p else "N/A",   f"{vix_c:+.2f}%" if vix_p else "")
    c5.metric("News Mood",   "🟢 BULLISH" if bull_n>bear_n else "🔴 BEARISH" if bear_n>bull_n else "⚪ NEUTRAL",
              f"{bull_n} bull / {bear_n} bear")

    st.divider()

    # Gap Prediction
    clr = gp["color"]
    st.markdown(f"""
    <div class="pred-banner" style="border-color:{clr};background:{clr}18;">
      <div style="font-size:11px;font-weight:700;letter-spacing:2px;text-transform:uppercase;color:{clr};margin-bottom:8px">📊 NEXT DAY MARKET PREDICTION — v2.0</div>
      <div class="pred-label" style="color:{clr}">{gp['prediction']}</div>
      <div style="font-size:16px;color:#90caf9;margin:8px 0">Expected Range: <b>{gp['gap_range']}</b> &nbsp;|&nbsp; Confidence: <b>{gp['confidence']}%</b> &nbsp;|&nbsp; Score: <b>{gp['raw_score']:+d}</b></div>
      <div style="background:#1e2a3a;border-radius:20px;height:8px;margin:12px auto;max-width:400px">
        <div style="background:{clr};height:8px;border-radius:20px;width:{gp['confidence']}%"></div></div>
      <div style="background:{clr}22;border:1px solid {clr}44;border-radius:8px;padding:12px;margin-top:12px;font-size:13px;font-weight:600;color:{clr}">
        ⚡ TRADE ACTION: {gp['action']}
      </div>
    </div>
    """, unsafe_allow_html=True)

    with st.expander(f"🔍 Full Factor Breakdown — Score: {gp['raw_score']:+d} / Confidence: {gp['confidence']}%", expanded=True):
        for f in gp["factors"]:
            st.markdown(f"<div class='factor-item'>{f}</div>", unsafe_allow_html=True)

    st.divider()

    # Global Cues + FII/DII
    col_gc, col_fii = st.columns(2)
    with col_gc:
        st.markdown('<div class="section-hdr">🌍 Global Market Cues (Live)</div>', unsafe_allow_html=True)
        gc_rows=[]
        for name,d in gcues.items():
            chg=d["chg"]; arrow="▲" if chg>0 else "▼" if chg<0 else "→"
            clr2="#00c853" if chg>0 else "#ff5252" if chg<0 else "#b0bec5"
            is_futures="Futures" in name or name=="GIFT Nifty"
            gc_rows.append({"Market":f"{'⚡ ' if is_futures else ''}{name}","Price":f"{d['price']:,.2f}","Change":f"{arrow} {chg:+.2f}%"})
        st.dataframe(pd.DataFrame(gc_rows), use_container_width=True, hide_index=True)
        st.caption("⚡ = Live futures price (most relevant for next-day gap)")

    with col_fii:
        st.markdown(f'<div class="section-hdr">🏦 FII / DII — Source: {fii_source}</div>', unsafe_allow_html=True)
        if not fii_a.get("available"):
            st.markdown('<div class="warn-box">⚠️ NSE API blocked this session. FII/DII data unavailable. Prediction uses other factors only. Check nseindia.com directly for FII/DII figures.</div>', unsafe_allow_html=True)
        else:
            m1,m2,m3 = st.columns(3)
            f5=fii_a["fii_5d"]; d5=fii_a["dii_5d"]
            m1.metric("FII 5D Net",  f"₹{f5:+,.0f} Cr", fii_a["fii_trend"])
            m2.metric("DII 5D Net",  f"₹{d5:+,.0f} Cr", fii_a["dii_trend"])
            m3.metric("Combined 5D", f"₹{fii_a['combined_5d']:+,.0f} Cr",
                      f"FII {abs(fii_a['fii_streak'])}d {'buy' if fii_a['fii_streak']>0 else 'sell'} streak")
            disp=fii_df[["Date","FII Net","DII Net"]].copy().tail(10)
            disp["Combined"]=disp["FII Net"]+disp["DII Net"]
            for col in ["FII Net","DII Net","Combined"]:
                disp[col]=disp[col].apply(lambda x: f"₹{x:+,.0f} Cr")
            st.dataframe(disp, use_container_width=True, hide_index=True)

    st.divider()

    # Sector Indices
    st.markdown('<div class="section-hdr">🏭 Sector Performance</div>', unsafe_allow_html=True)
    s_cols = st.columns(len(sectors))
    for col, (name, d) in zip(s_cols, sectors.items()):
        chg=d["chg"]; col.metric(name.replace("NIFTY ",""), f"{d['price']:,.0f}", f"{chg:+.2f}%")

    st.divider()

    # Options Chain + TA
    col_oc, col_ta = st.columns(2)
    with col_oc:
        st.markdown('<div class="section-hdr">📈 NIFTY Options Chain (Weekly)</div>', unsafe_allow_html=True)
        if not oc_n.get("available"):
            st.markdown('<div class="warn-box">⚠️ NSE options API unavailable. PCR not shown. Visit nseindia.com/option-chain for live data.</div>', unsafe_allow_html=True)
        else:
            pcr=oc_n["pcr"]; mp=oc_n["max_pain"]
            o1,o2,o3 = st.columns(3)
            o1.metric("PCR",      f"{pcr:.3f}", oc_n["trend"])
            o2.metric("Max Pain", f"₹{mp:,.0f}")
            o3.metric("OI Bias",  f"CE +{oc_n.get('ce_oi_change',0)/1000:.0f}K / PE +{oc_n.get('pe_oi_change',0)/1000:.0f}K")
            sup=oc_n.get("support_oi",[]); res=oc_n.get("resistance_oi",[])
            if sup: st.markdown("🟢 **Support:** " + " | ".join(f"**{s[0]}** ({s[1]/100000:.1f}L, chg {s[2]/1000:+.0f}K)" for s in sup))
            if res: st.markdown("🔴 **Resistance:** " + " | ".join(f"**{s[0]}** ({s[1]/100000:.1f}L, chg {s[2]/1000:+.0f}K)" for s in res))

    with col_ta:
        st.markdown('<div class="section-hdr">📐 Technical Analysis</div>', unsafe_allow_html=True)
        t1,t2 = st.tabs(["NIFTY","BANKNIFTY"])
        for tab,ta in [(t1,ta_n),(t2,ta_b)]:
            with tab:
                tc="#00c853" if "BULL" in ta["trend"] else "#ff5252" if "BEAR" in ta["trend"] else "#b0bec5"
                st.markdown(f"<b style='color:{tc};font-size:18px'>{ta['trend']}</b> &nbsp; Score: {ta['overall']:+d}", unsafe_allow_html=True)
                st.dataframe(pd.DataFrame([{"Indicator":i,"Signal":s,"Value":v} for i,s,v,_,__ in ta["signals"]]),
                             use_container_width=True, hide_index=True)

    st.divider()

    # Stock Picks
    st.markdown('<div class="section-hdr">🎯 F&O Stock Picks — Weekly Options (Correct Strike Steps)</div>', unsafe_allow_html=True)
    st.caption("⚠️ Not SEBI registered. Educational only. Always set SL. Options carry full risk of premium loss.")
    with st.spinner("Scanning F&O stocks..."):
        picks = scan_stocks(gp["raw_score"])
    for s in picks[:5]:
        skip="SKIP" in s["tt"]
        c1,c2,c3,c4 = st.columns([2,1,1,4])
        icon="▲" if s["chg"]>0 else "▼"
        c1.markdown(f"**{s['name']}** &nbsp; <small style='color:#7a8598'>ADX:{s['adx']}</small>", unsafe_allow_html=True)
        c2.markdown(f"₹{s['ltp']:,.2f} {icon}{s['chg']:+.2f}%")
        c3.markdown(f"RSI:**{s['rsi']}** Vol:**{s['vr']}x**")
        if not skip:
            tc="#00c853" if "CE" in s["tt"] else "#ff5252" if "PE" in s["tt"] else "#ffeb3b"
            c4.markdown(f"<span style='color:{tc};font-weight:700'>{s['tt']}</span> Strike ~**{s['strike']}** | 🎯₹{s['tgt']} | 🛑₹{s['sl']} | R1:₹{s['r1']} S1:₹{s['s1']} | ⏱{s['tim']}", unsafe_allow_html=True)
            c4.caption(f"52W: ₹{s['l52']:,.0f} ↔ ₹{s['h52']:,.0f}")
        else:
            c4.markdown("⚪ **No clear setup** — ADX weak or conflicting signals")
        st.divider()

    # Backtest
    st.markdown('<div class="section-hdr">🔬 Gap Prediction Backtest (~1 Year, upgraded signals)</div>', unsafe_allow_html=True)
    bt=run_backtest(ndf_ta)
    if bt:
        b1,b2,b3,b4,b5,b6=st.columns(6)
        wr_color="#00c853" if bt["win_rate"]>=58 else "#ffeb3b" if bt["win_rate"]>=48 else "#ff5252"
        b1.metric("Win Rate",  f"{bt['win_rate']}%")
        b2.metric("Total P&L", f"₹{bt['total_pnl']:+,}")
        b3.metric("Avg/Trade", f"₹{bt['avg_pnl']:+,}")
        b4.metric("Max DD",    f"₹{bt['max_dd']:,}")
        b5.metric("Trades",    bt["total"])
        b6.metric("Win/Loss",  f"{bt['mws']}/{bt['mls']}")
        recent=pd.DataFrame(bt["recent"])
        recent=recent[["date","gap_pct","pred","actual","correct","pnl"]].rename(columns={
            "date":"Date","gap_pct":"Gap %","pred":"Predicted","actual":"Actual","correct":"✓","pnl":"Sim P&L ₹"})
        st.dataframe(recent, use_container_width=True, hide_index=True)

    st.divider()

    # News
    st.markdown('<div class="section-hdr">📰 Market News — Context-Aware Sentiment</div>', unsafe_allow_html=True)
    if arts:
        for a in arts[:12]:
            nc1,nc2=st.columns([5,1])
            nc1.markdown(f"[**{a['Title']}**]({a['Link']})")
            nc1.caption(f"{a['Source']} • {a.get('Published','')[:25]}")
            nc2.markdown(a["Sentiment"])
            st.divider()

    st.markdown("<center><small style='color:#3a4a5a'>Indian Market Intelligence v2 • ROBO for Boss Chethan • Yahoo Finance + NSE India + RSS • ⚠️ NOT SEBI registered</small></center>", unsafe_allow_html=True)

if __name__=="__main__":
    main()
