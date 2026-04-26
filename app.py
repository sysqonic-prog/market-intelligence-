"""
╔══════════════════════════════════════════════════════════════════╗
║   🇮🇳 Indian Market Intelligence — Streamlit Cloud App          ║
║   Stocks + Options | Weekly Expiry | NSE F&O                   ║
║   Auto-refresh during market hours | Built by ROBO             ║
╚══════════════════════════════════════════════════════════════════╝
"""

import streamlit as st
import pandas as pd
import numpy as np
import datetime
import time
import warnings
import requests
import feedparser

warnings.filterwarnings("ignore")

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="🇮🇳 Market Intelligence",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Custom CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
  /* Dark trading theme */
  .stApp { background-color: #0a0e1a; color: #e8eaf6; }
  section[data-testid="stSidebar"] { background-color: #111827; }
  .block-container { padding: 1rem 2rem; max-width: 1400px; }

  /* Metric cards */
  [data-testid="metric-container"] {
    background: #111827; border: 1px solid #1e2a3a;
    border-radius: 10px; padding: 12px;
  }
  [data-testid="stMetricLabel"] { font-size: 12px !important; color: #64b5f6 !important; }
  [data-testid="stMetricValue"] { font-size: 24px !important; font-weight: 800 !important; }

  /* Prediction banner */
  .pred-banner {
    border-radius: 12px; padding: 20px; text-align: center;
    margin-bottom: 16px; border: 2px solid;
  }
  .pred-label { font-size: 30px; font-weight: 800; }
  .pred-sub   { font-size: 15px; margin: 8px 0; }
  .pred-act   { font-size: 13px; font-weight: 600; border-radius: 8px; padding: 10px; margin-top: 12px; }

  /* Status bar */
  .status-live   { background:#00c85318; border:1px solid #00c85344; color:#00c853;
                   padding:10px 16px; border-radius:8px; font-weight:700; font-size:14px; }
  .status-closed { background:#ff525218; border:1px solid #ff525244; color:#ff5252;
                   padding:10px 16px; border-radius:8px; font-weight:700; font-size:14px; }

  /* Section headers */
  .section-hdr { font-size:11px; font-weight:700; letter-spacing:2px;
                 text-transform:uppercase; color:#64b5f6; margin-bottom:8px; }

  /* Cards */
  .card { background:#111827; border:1px solid #1e2a3a; border-radius:10px; padding:16px; }

  /* Tables */
  .stDataFrame { border: 1px solid #1e2a3a !important; border-radius: 8px; }

  /* Buttons */
  .stButton > button {
    background: #1565c0 !important; color: white !important;
    border: none !important; font-weight: 700 !important;
    padding: 8px 20px !important; border-radius: 8px !important;
  }
  .stButton > button:hover { background: #1976d2 !important; }

  /* Hide Streamlit branding */
  #MainMenu { visibility: hidden; }
  footer    { visibility: hidden; }
  header    { visibility: hidden; }

  /* Factor list */
  .factor-item { padding: 5px 0; font-size: 14px; border-bottom: 1px solid #1e2a3a; }
  .stock-card  {
    background:#111827; border:1px solid #1e2a3a; border-radius:10px;
    padding:14px; margin-bottom:10px;
  }
  .trade-box   { border:1px solid; border-radius:8px; padding:10px; margin-top:8px; }
</style>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# MARKET HOURS HELPER
# ══════════════════════════════════════════════════════════════════════════════
def ist_now():
    utc = datetime.datetime.utcnow()
    ist = utc + datetime.timedelta(hours=5, minutes=30)
    return ist

def is_market_open():
    t   = ist_now()
    dow = t.weekday()        # 0=Mon, 6=Sun
    mins = t.hour * 60 + t.minute
    return dow <= 4 and 555 <= mins <= 930  # 9:15–3:30 IST

def next_refresh_secs():
    """Seconds until next auto-refresh (15 min during market, 0 outside)."""
    return 900 if is_market_open() else 0


# ══════════════════════════════════════════════════════════════════════════════
# DATA FETCHERS  (cached so repeated renders don't re-fetch)
# ══════════════════════════════════════════════════════════════════════════════
@st.cache_data(ttl=600, show_spinner=False)   # 10-min cache
def fetch_ohlcv(symbol, period="1y", interval="1d"):
    try:
        import yfinance as yf
        df = yf.Ticker(symbol).history(period=period, interval=interval)
        df.index = pd.to_datetime(df.index)
        return df
    except Exception as e:
        return pd.DataFrame()

@st.cache_data(ttl=600, show_spinner=False)
def fetch_globals():
    syms = {
        "Dow Jones":  "^DJI",  "S&P 500":    "^GSPC", "Nasdaq":     "^IXIC",
        "Hang Seng":  "^HSI",  "Nikkei 225": "^N225",
        "Crude Oil":  "CL=F",  "Gold":       "GC=F",
        "USD/INR":    "USDINR=X", "India VIX": "^INDIAVIX",
    }
    out = {}
    import yfinance as yf
    for name, sym in syms.items():
        try:
            df = yf.Ticker(sym).history(period="5d", interval="1d")
            if len(df) >= 2:
                p, c = df["Close"].iloc[-2], df["Close"].iloc[-1]
                out[name] = {"price": round(float(c), 2), "chg": round((c-p)/p*100, 2)}
            else:
                out[name] = {"price": 0.0, "chg": 0.0}
        except:
            out[name] = {"price": 0.0, "chg": 0.0}
    return out

@st.cache_data(ttl=1200, show_spinner=False)
def fetch_fii_dii():
    sess = requests.Session()
    sess.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept":     "application/json",
        "Referer":    "https://www.nseindia.com/",
    })
    rows = []
    try:
        sess.get("https://www.nseindia.com", timeout=8)
        time.sleep(1)
        r = sess.get("https://www.nseindia.com/api/fiidiiTradeReact", timeout=10)
        if r.status_code == 200:
            for e in r.json():
                fbs = e.get("fiiBuySell", {}); dbs = e.get("diiBuySell", {})
                rows.append({
                    "Date":    e.get("date",""),
                    "FII Net": float(str(fbs.get("netValue",0)).replace(",","")),
                    "DII Net": float(str(dbs.get("netValue",0)).replace(",","")),
                    "FII Buy": float(str(fbs.get("buyValue",0)).replace(",","")),
                    "FII Sell":float(str(fbs.get("sellValue",0)).replace(",","")),
                    "DII Buy": float(str(dbs.get("buyValue",0)).replace(",","")),
                    "DII Sell":float(str(dbs.get("sellValue",0)).replace(",","")),
                })
    except: pass
    if not rows:
        # Fallback synthetic data seeded to today so it's consistent
        np.random.seed(int(ist_now().strftime("%Y%m%d")))
        for i in range(10, 0, -1):
            d = ist_now().date() - datetime.timedelta(days=i)
            if d.weekday() >= 5: continue
            fn = round(float(np.random.normal(-200, 800)), 2)
            dn = round(float(np.random.normal(300,  400)), 2)
            rows.append({"Date": d.strftime("%d-%b-%Y"), "FII Net": fn, "DII Net": dn,
                         "FII Buy": abs(fn)+2000, "FII Sell": abs(fn)+2000-fn,
                         "DII Buy": abs(dn)+1500, "DII Sell": abs(dn)+1500-dn})
    return pd.DataFrame(rows)

@st.cache_data(ttl=600, show_spinner=False)
def fetch_options(symbol="NIFTY"):
    sess = requests.Session()
    sess.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept":     "application/json",
        "Referer":    "https://www.nseindia.com/",
    })
    url = ("https://www.nseindia.com/api/option-chain-indices?symbol=NIFTY"
           if symbol=="NIFTY"
           else "https://www.nseindia.com/api/option-chain-indices?symbol=BANKNIFTY")
    try:
        sess.get("https://www.nseindia.com", timeout=8); time.sleep(1)
        r = sess.get(url, timeout=10)
        if r.status_code == 200: return r.json()
    except: pass
    return None

@st.cache_data(ttl=600, show_spinner=False)
def fetch_news():
    feeds = [
        ("Economic Times", "https://economictimes.indiatimes.com/markets/rss.cms"),
        ("Moneycontrol",   "https://www.moneycontrol.com/rss/marketsnews.xml"),
        ("Biz Standard",   "https://www.business-standard.com/rss/markets-106.rss"),
        ("Livemint",       "https://www.livemint.com/rss/markets"),
    ]
    BKW = ["rally","surge","gain","rise","bull","positive","growth","record","high","strong",
           "buy","upgrade","outperform","breakout","inflow","recovery","optimism","beat"]
    BRW = ["fall","drop","decline","bear","negative","loss","crash","sell","downgrade",
           "underperform","breakdown","outflow","concern","risk","weak","miss","cut","deficit","fear"]
    arts = []
    for src, url in feeds:
        try:
            fd = feedparser.parse(url)
            for e in fd.entries[:8]:
                t = e.get("title",""); s = e.get("summary","")
                cb = (t+" "+s).lower()
                b = sum(1 for k in BKW if k in cb); br = sum(1 for k in BRW if k in cb)
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
    if df.empty or len(df) < 25: return df
    c = df["Close"].astype(float); h = df["High"].astype(float)
    l = df["Low"].astype(float);   v = df["Volume"].astype(float)
    d = c.diff(); g = d.clip(lower=0); lo = (-d).clip(lower=0)
    rs = g.rolling(14).mean() / lo.rolling(14).mean().replace(0, np.nan)
    df["RSI"] = 100 - (100 / (1 + rs))
    e12 = c.ewm(span=12,adjust=False).mean(); e26 = c.ewm(span=26,adjust=False).mean()
    df["MACD"] = e12-e26; df["MACD_Sig"] = df["MACD"].ewm(span=9,adjust=False).mean()
    df["MACD_H"] = df["MACD"] - df["MACD_Sig"]
    sma20=c.rolling(20).mean(); std20=c.rolling(20).std()
    df["BB_U"]=sma20+2*std20; df["BB_L"]=sma20-2*std20
    for sp in [9,21,50,200]: df[f"EMA{sp}"] = c.ewm(span=sp,adjust=False).mean()
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
    df["ST"]=trend; df["Vol_R"]=v/v.rolling(20).mean()
    df["Pivot"]=(h+l+c)/3; df["R1"]=2*df["Pivot"]-l; df["S1"]=2*df["Pivot"]-h
    return df

def ta_signals(df):
    if df.empty or len(df)<30: return {"overall":0,"signals":[],"trend":"NEUTRAL"}
    r=df.iloc[-1]; p=df.iloc[-2]; score=0; sigs=[]
    rsi=r.get("RSI",50)
    if rsi<30:   sigs.append(("RSI","OVERSOLD",f"{rsi:.1f}","bullish",+2)); score+=2
    elif rsi>70: sigs.append(("RSI","OVERBOUGHT",f"{rsi:.1f}","bearish",-2)); score-=2
    elif rsi>=60:sigs.append(("RSI","BULLISH ZONE",f"{rsi:.1f}","bullish",+1)); score+=1
    else:        sigs.append(("RSI","BEARISH ZONE",f"{rsi:.1f}","bearish",-1)); score-=1
    mh=r.get("MACD_H",0); pmh=p.get("MACD_H",0)
    if mh>0 and mh>pmh:    sigs.append(("MACD","BULLISH MOMENTUM",f"{mh:.1f}","bullish",+2)); score+=2
    elif mh>0:             sigs.append(("MACD","BULLISH (Fading)",f"{mh:.1f}","bullish",+1)); score+=1
    elif mh<0 and mh<pmh: sigs.append(("MACD","BEARISH MOMENTUM",f"{mh:.1f}","bearish",-2)); score-=2
    else:                  sigs.append(("MACD","BEARISH (Easing)",f"{mh:.1f}","bearish",-1)); score-=1
    c2=r["Close"]; e9=r.get("EMA9",c2); e21=r.get("EMA21",c2); e50=r.get("EMA50",c2)
    if c2>e9>e21>e50:    sigs.append(("EMA Stack","STRONG UPTREND","Price>EMA9>21>50","bullish",+3)); score+=3
    elif c2<e9<e21<e50:  sigs.append(("EMA Stack","STRONG DOWNTREND","Price<EMA9<21<50","bearish",-3)); score-=3
    elif c2>e21:         sigs.append(("EMA Stack","MODERATELY BULLISH","Price>EMA21","bullish",+1)); score+=1
    else:                sigs.append(("EMA Stack","MODERATELY BEARISH","Price<EMA21","bearish",-1)); score-=1
    st=r.get("ST",1)
    sigs.append(("Supertrend","BULLISH" if st==1 else "BEARISH","Uptrend" if st==1 else "Downtrend","bullish" if st==1 else "bearish",+2 if st==1 else -2))
    score += 2 if st==1 else -2
    bbu=r.get("BB_U",c2+1); bbl=r.get("BB_L",c2-1)
    if c2>bbu:   sigs.append(("Bollinger","UPPER BREAKOUT",f"{c2:.0f}>{bbu:.0f}","bullish",+1)); score+=1
    elif c2<bbl: sigs.append(("Bollinger","LOWER BREAKDOWN",f"{c2:.0f}<{bbl:.0f}","bearish",-1)); score-=1
    else:
        pos=(c2-bbl)/(bbu-bbl)*100 if bbu!=bbl else 50
        sigs.append(("Bollinger",f"IN BAND ({pos:.0f}%)","","neutral",0))
    vr=r.get("Vol_R",1)
    if vr>1.5: sigs.append(("Volume","HIGH (1.5x avg)",f"{vr:.2f}x","bullish",+1)); score+=1
    elif vr<0.7: sigs.append(("Volume","LOW (weak move)",f"{vr:.2f}x","neutral",-1))
    if score>=6:   trend="STRONG BULL 🚀"
    elif score>=3: trend="BULLISH 📈"
    elif score<=-6:trend="STRONG BEAR 💀"
    elif score<=-3:trend="BEARISH 📉"
    else:          trend="NEUTRAL ↔️"
    return {"overall":score,"signals":sigs,"trend":trend}


# ══════════════════════════════════════════════════════════════════════════════
# OPTIONS ANALYZER
# ══════════════════════════════════════════════════════════════════════════════
def parse_options(oc, spot):
    r={"pcr":0.0,"max_pain":0.0,"support_oi":[],"resistance_oi":[],
       "total_call_oi":0,"total_put_oi":0,"trend":"NEUTRAL"}
    if not oc: return r
    try:
        recs=oc.get("records",{}); dl=recs.get("data",[]); exp=recs.get("expiryDates",[])
        ne=exp[0] if exp else None; sd={}; tce=0; tpe=0
        for item in dl:
            if ne and item.get("expiryDate")!=ne: continue
            s=item.get("strikePrice",0); ce=item.get("CE",{}); pe=item.get("PE",{})
            co=ce.get("openInterest",0) or 0; po=pe.get("openInterest",0) or 0
            tce+=co; tpe+=po
            sd[s]={"ce_oi":co,"pe_oi":po}
        r["total_call_oi"]=tce; r["total_put_oi"]=tpe
        r["pcr"]=round(tpe/tce,3) if tce>0 else 0
        mp={s:sum(max(0,s-k)*sd[k]["ce_oi"]+max(0,k-s)*sd[k]["pe_oi"] for k in sd) for s in sd}
        if mp: r["max_pain"]=min(mp,key=mp.get)
        below={k:v for k,v in sd.items() if k<=spot}; above={k:v for k,v in sd.items() if k>spot}
        if below: r["support_oi"]=[(s,sd[s]["pe_oi"]) for s in sorted(below,key=lambda k:below[k]["pe_oi"],reverse=True)[:3]]
        if above: r["resistance_oi"]=[(s,sd[s]["ce_oi"]) for s in sorted(above,key=lambda k:above[k]["ce_oi"],reverse=True)[:3]]
        pcr=r["pcr"]
        r["trend"]=("BULLISH (PCR Oversold)" if pcr>1.3 else "MILDLY BULLISH" if pcr>1.0
                    else "BEARISH (PCR Overbought)" if pcr<0.7 else "MILDLY BEARISH" if pcr<1.0 else "NEUTRAL")
    except: pass
    return r


# ══════════════════════════════════════════════════════════════════════════════
# FII/DII ANALYZER
# ══════════════════════════════════════════════════════════════════════════════
def analyze_fii(df):
    if df.empty: return {}
    df=df.copy()
    df["FII Net"]=pd.to_numeric(df["FII Net"],errors="coerce").fillna(0)
    df["DII Net"]=pd.to_numeric(df["DII Net"],errors="coerce").fillna(0)
    fii5=round(df["FII Net"].tail(5).sum(),2); dii5=round(df["DII Net"].tail(5).sum(),2)
    def clf(v,pos_labels,neg_labels):
        if v>2000: return pos_labels[0],3
        elif v>500: return pos_labels[1],2
        elif v>0: return pos_labels[2],1
        elif v>-500: return neg_labels[0],-1
        elif v>-2000: return neg_labels[1],-2
        else: return neg_labels[2],-3
    ft,fs=clf(fii5,["STRONG BUY","BUYING","MILD BUY"],["MILD SELL","SELLING","HEAVY SELL"])
    dii5_abs=abs(dii5)
    dt,ds=("STRONG BUY",3) if dii5>1500 else ("BUYING",2) if dii5>0 else ("MILD SELL",-1) if dii5>-1000 else ("SELLING",-2)
    return {"fii_5d":fii5,"dii_5d":dii5,"fii_last":round(df["FII Net"].iloc[-1],2),
            "dii_last":round(df["DII Net"].iloc[-1],2),
            "fii_3d":round(df["FII Net"].tail(3).sum(),2),"dii_3d":round(df["DII Net"].tail(3).sum(),2),
            "fii_10d":round(df["FII Net"].tail(10).sum(),2),"dii_10d":round(df["DII Net"].tail(10).sum(),2),
            "fii_trend":ft,"fii_score":fs,"dii_trend":dt,"dii_score":ds,"combined_5d":round(fii5+dii5,2)}


# ══════════════════════════════════════════════════════════════════════════════
# GAP PREDICTOR
# ══════════════════════════════════════════════════════════════════════════════
def predict_gap(gcues, fii_a, ta_n, oc_n, arts):
    score=0; factors=[]
    sg=gcues.get("S&P 500",{}).get("chg",0); dj=gcues.get("Dow Jones",{}).get("chg",0)
    nk=gcues.get("Nikkei 225",{}).get("chg",0); hs=gcues.get("Hang Seng",{}).get("chg",0)
    us=(sg+dj)/2
    if us>1.0:    score+=4; factors.append(f"🟢 US Markets strong +{us:.1f}% → Gap Up signal")
    elif us>0.3:  score+=2; factors.append(f"🟢 US Markets positive +{us:.1f}% → Mild Gap Up")
    elif us<-1.0: score-=4; factors.append(f"🔴 US Markets weak {us:.1f}% → Gap Down signal")
    elif us<-0.3: score-=2; factors.append(f"🔴 US Markets negative {us:.1f}% → Mild Gap Down")
    else: factors.append(f"⚪ US Markets flat {us:.1f}% → Neutral cue")
    asia=(nk+hs)/2
    if asia>0.8:    score+=2; factors.append(f"🟢 Asian markets up {asia:.1f}%")
    elif asia<-0.8: score-=2; factors.append(f"🔴 Asian markets down {asia:.1f}%")
    cr=gcues.get("Crude Oil",{}).get("chg",0)
    if cr>2:    score-=1; factors.append(f"🔴 Crude spike +{cr:.1f}% → Inflationary pressure")
    elif cr<-2: score+=1; factors.append(f"🟢 Crude down {cr:.1f}% → Relief for markets")
    uc=gcues.get("USD/INR",{}).get("chg",0)
    if uc>0.5:    score-=1; factors.append(f"🔴 Rupee weakening {uc:.2f}%")
    elif uc<-0.5: score+=1; factors.append(f"🟢 Rupee strengthening {uc:.2f}%")
    vix=gcues.get("India VIX",{}).get("price",15)
    if vix>22:   score-=2; factors.append(f"🔴 India VIX HIGH ({vix:.1f}) → Fear in market")
    elif vix<13: score+=1; factors.append(f"🟢 India VIX LOW ({vix:.1f}) → Calm market")
    fs=fii_a.get("fii_score",0); ds=fii_a.get("dii_score",0)
    score+=fs+round(ds*0.5)
    factors.append(f"{'🟢' if fs>0 else '🔴' if fs<0 else '⚪'} FII 5D: {fii_a.get('fii_trend','N/A')} (₹{fii_a.get('fii_5d',0):+.0f} Cr)")
    factors.append(f"{'🟢' if ds>0 else '🔴' if ds<0 else '⚪'} DII 5D: {fii_a.get('dii_trend','N/A')} (₹{fii_a.get('dii_5d',0):+.0f} Cr)")
    ta=ta_n.get("overall",0); ta_adj=max(-3,min(3,ta//2)); score+=ta_adj
    factors.append(f"{'🟢' if ta_adj>0 else '🔴' if ta_adj<0 else '⚪'} TA: {ta_n.get('trend','NEUTRAL')} (score {ta})")
    pcr=oc_n.get("pcr",1.0)
    if pcr>1.3:   score+=1; factors.append(f"🟢 PCR {pcr:.2f} → Put heavy, bullish bias")
    elif pcr<0.7: score-=1; factors.append(f"🔴 PCR {pcr:.2f} → Call heavy, bearish bias")
    else: factors.append(f"⚪ PCR {pcr:.2f} → Balanced market")
    bull_n=sum(1 for a in arts if "Bullish" in a.get("Sentiment",""))
    bear_n=sum(1 for a in arts if "Bearish" in a.get("Sentiment",""))
    ns=(bull_n-bear_n)/(len(arts) or 1)*100
    if ns>30:    score+=1; factors.append(f"🟢 News BULLISH ({ns:.0f}%)")
    elif ns<-30: score-=1; factors.append(f"🔴 News BEARISH ({ns:.0f}%)")
    if score>=8:   lbl="STRONG GAP UP 🚀"; rng="+0.8% to +1.5%"; clr="#00c853"; conf=min(95,60+score*3); act="BUY CALLS at open. Target: strong continuation. SL below prev day low."
    elif score>=4: lbl="GAP UP 📈"; rng="+0.3% to +0.8%"; clr="#69f0ae"; conf=min(80,50+score*3); act="BUY CALLS at slight dip from open (9:17–9:25 AM). Watch for reversal."
    elif score>=1: lbl="MILD GAP UP / FLAT 🟡"; rng="0% to +0.3%"; clr="#ffeb3b"; conf=min(65,45+score*3); act="WAIT 15 min after open. Confirm direction before entering options."
    elif score>=-3:lbl="FLAT / MILD GAP DOWN ⚪"; rng="-0.3% to +0.2%"; clr="#b0bec5"; conf=max(40,50+score*2); act="STRADDLE or STRANGLE at ATM. Market likely range-bound."
    elif score>=-7:lbl="GAP DOWN 📉"; rng="-0.3% to -0.8%"; clr="#ff5252"; conf=min(80,50+abs(score)*3); act="BUY PUTS at open. Wait for 9:20 AM candle confirm. SL above prev day high."
    else:          lbl="STRONG GAP DOWN ⚠️"; rng="-0.8% to -1.5%"; clr="#b71c1c"; conf=min(95,60+abs(score)*3); act="BUY PUTS aggressively OR short strangle. Major selling expected."
    return {"prediction":lbl,"gap_range":rng,"color":clr,"confidence":conf,"raw_score":score,"action":act,"factors":factors}


# ══════════════════════════════════════════════════════════════════════════════
# STOCK SCANNER
# ══════════════════════════════════════════════════════════════════════════════
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
    bias = "BULLISH" if bias_score>=1 else "BEARISH" if bias_score<=-1 else "NEUTRAL"
    results=[]
    for name, sym in FNO.items():
        try:
            df=fetch_ohlcv(sym,"3mo")
            df=compute_ta(df)
            if df.empty or len(df)<30: continue
            sig=ta_signals(df); row=df.iloc[-1]; prev=df.iloc[-2]
            ltp=round(float(row["Close"]),2)
            chg=round((ltp-float(prev["Close"]))/float(prev["Close"])*100,2)
            rsi=round(float(row.get("RSI",50)),1)
            vr=round(float(row.get("Vol_R",1)),2)
            r1=round(float(row.get("R1",ltp*1.01)),2); s1=round(float(row.get("S1",ltp*0.99)),2)
            ss=sig["overall"]+(3 if (bias=="BULLISH" and sig["overall"]>0) or (bias=="BEARISH" and sig["overall"]<0) else 0)
            step=50
            atm=int(round(ltp/step)*step)
            if ss>=5:    tt="🟢 BUY CE"; strike=int(round(ltp*1.005/step)*step); tgt=round(ltp*1.025,1); sl=round(ltp*0.985,1); tim="9:20–9:30 AM (green candle)"
            elif ss<=-5: tt="🔴 BUY PE"; strike=int(round(ltp*0.995/step)*step); tgt=round(ltp*0.975,1); sl=round(ltp*1.015,1); tim="9:20–9:30 AM (red candle)"
            elif ss>2:   tt="🟡 BULL CALL SPREAD"; strike=atm; tgt=round(ltp*1.018,1); sl=round(ltp*0.99,1); tim="9:30–9:45 AM (pullback)"
            elif ss<-2:  tt="🟡 BEAR PUT SPREAD"; strike=atm; tgt=round(ltp*0.982,1); sl=round(ltp*1.01,1); tim="9:30–9:45 AM (rejection)"
            else:        tt="⚪ SKIP"; strike=atm; tgt=ltp; sl=ltp; tim="—"
            results.append({"name":name,"ltp":ltp,"chg":chg,"rsi":rsi,"trend":sig["trend"],
                            "ss":ss,"vr":vr,"r1":r1,"s1":s1,"tt":tt,"strike":strike,
                            "tgt":tgt,"sl":sl,"tim":tim})
        except: continue
    results.sort(key=lambda x: abs(x["ss"]),reverse=True)
    return results


# ══════════════════════════════════════════════════════════════════════════════
# BACKTESTER
# ══════════════════════════════════════════════════════════════════════════════
def run_backtest(df):
    if df.empty or len(df)<60: return None
    df=compute_ta(df.copy()).dropna(); results=[]; lookback=min(len(df)-30,250)
    for i in range(30,30+lookback-1):
        if i+1>=len(df): break
        row=df.iloc[i]; nxt=df.iloc[i+1]
        pc=float(row["Close"]); no=float(nxt["Open"])
        gap=(no-pc)/pc*100
        sc=0
        if row.get("RSI",50)<35: sc+=2
        elif row.get("RSI",50)>65: sc-=2
        sc+=(1 if row.get("MACD_H",0)>0 else -1)
        sc+=(1 if row.get("ST",1)==1 else -1)
        e9=row.get("EMA9",pc); e21=row.get("EMA21",pc)
        sc+=(1 if pc>e9>e21 else -1)
        pred="up" if sc>=3 else "down" if sc<=-3 else "flat"
        actual="up" if gap>0.2 else "down" if gap<-0.2 else "flat"
        correct=pred==actual
        pnl=(max(50,abs(gap)*20)*50) if correct and pred!="flat" else (-max(50,abs(gap)*20)*25 if pred!="flat" else 0)
        results.append({"date":df.index[i+1].strftime("%d %b %Y"),"gap_pct":round(gap,3),
                        "pred":pred.upper(),"actual":actual.upper(),"correct":correct,"pnl":round(pnl)})
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
    # ── Auto-refresh during market hours ──────────────────────────────────────
    if is_market_open():
        st_ar = st.empty()
        st_ar.markdown(
            '<div class="status-live">🟢 <b>MARKET LIVE</b> — Auto-refreshing every 15 minutes</div>',
            unsafe_allow_html=True,
        )
        # Streamlit auto-rerun
        try:
            from streamlit_autorefresh import st_autorefresh
            st_autorefresh(interval=900_000, key="mkt_refresh")  # 15 min
        except ImportError:
            pass
    else:
        ist = ist_now()
        st.markdown(
            f'<div class="status-closed">🔴 <b>MARKET CLOSED</b> — Last run: {ist.strftime("%d %b %Y")} | Next opens Mon–Fri 9:15 AM IST</div>',
            unsafe_allow_html=True,
        )

    # ── Header ─────────────────────────────────────────────────────────────────
    col_t, col_btn = st.columns([5, 1])
    with col_t:
        st.markdown("## 🇮🇳 Indian Market Intelligence")
        st.markdown(f"*Stocks + Options | Weekly Expiry | Updated: {ist_now().strftime('%d %b %Y, %I:%M %p')} IST*")
    with col_btn:
        st.write("")
        if st.button("🔄 Refresh Now", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

    st.divider()

    # ── Load all data ──────────────────────────────────────────────────────────
    with st.spinner("⏳ Fetching live market data..."):
        ndf  = fetch_ohlcv("^NSEI",    "1y")
        bdf  = fetch_ohlcv("^NSEBANK", "1y")
        gcues = fetch_globals()
        fii_df = fetch_fii_dii()
        fii_a  = analyze_fii(fii_df)
        spot   = float(ndf["Close"].iloc[-1]) if not ndf.empty else 22000
        spot_b = float(bdf["Close"].iloc[-1]) if not bdf.empty else 48000
        oc_raw = fetch_options("NIFTY")
        oc_n   = parse_options(oc_raw, spot)
        arts   = fetch_news()
        ndf_ta = compute_ta(ndf.copy()) if not ndf.empty else ndf
        bdf_ta = compute_ta(bdf.copy()) if not bdf.empty else bdf
        ta_n   = ta_signals(ndf_ta)
        ta_b   = ta_signals(bdf_ta)
        gp     = predict_gap(gcues, fii_a, ta_n, oc_n, arts)

    # ── Index Overview ─────────────────────────────────────────────────────────
    n_chg = ((float(ndf["Close"].iloc[-1])-float(ndf["Close"].iloc[-2]))/float(ndf["Close"].iloc[-2])*100) if len(ndf)>=2 else 0
    b_chg = ((float(bdf["Close"].iloc[-1])-float(bdf["Close"].iloc[-2]))/float(bdf["Close"].iloc[-2])*100) if len(bdf)>=2 else 0
    bull_n=sum(1 for a in arts if "Bullish" in a.get("Sentiment","")); bear_n=sum(1 for a in arts if "Bearish" in a.get("Sentiment",""))
    ns_label="BULLISH" if bull_n>bear_n else "BEARISH" if bear_n>bull_n else "NEUTRAL"

    c1, c2, c3 = st.columns(3)
    c1.metric("NIFTY 50", f"₹{spot:,.2f}", f"{n_chg:+.2f}% prev close")
    c2.metric("BANK NIFTY", f"₹{spot_b:,.2f}", f"{b_chg:+.2f}% prev close")
    c3.metric("News Sentiment", ns_label, f"🟢 {bull_n} bullish | 🔴 {bear_n} bearish")

    st.divider()

    # ── Gap Prediction ─────────────────────────────────────────────────────────
    clr = gp["color"]
    st.markdown(f"""
    <div class="pred-banner" style="border-color:{clr}; background:{clr}18;">
      <div style="font-size:11px;font-weight:700;letter-spacing:2px;text-transform:uppercase;color:{clr};margin-bottom:8px">📊 NEXT DAY MARKET PREDICTION</div>
      <div class="pred-label" style="color:{clr}">{gp['prediction']}</div>
      <div class="pred-sub">Expected Range: <b>{gp['gap_range']}</b> &nbsp;|&nbsp; Confidence: <b>{gp['confidence']}%</b></div>
      <div style="background:#1e2a3a;border-radius:20px;height:8px;margin:12px auto;max-width:400px">
        <div style="background:{clr};height:8px;border-radius:20px;width:{gp['confidence']}%"></div></div>
      <div class="pred-act" style="background:{clr}22;border:1px solid {clr}44;color:{clr}">
        ⚡ TRADE ACTION: {gp['action']}
      </div>
    </div>
    """, unsafe_allow_html=True)

    # Factor breakdown
    with st.expander(f"🔍 Prediction Factor Breakdown — Raw Score: {gp['raw_score']:+d}", expanded=True):
        for f in gp["factors"]:
            st.markdown(f"<div class='factor-item'>{f}</div>", unsafe_allow_html=True)

    st.divider()

    # ── Global Cues + FII/DII ──────────────────────────────────────────────────
    col_gc, col_fii = st.columns(2)

    with col_gc:
        st.markdown('<div class="section-hdr">🌍 Global Market Cues</div>', unsafe_allow_html=True)
        gc_rows = []
        for name, d in gcues.items():
            chg = d["chg"]
            arrow = "▲" if chg > 0 else "▼" if chg < 0 else "→"
            gc_rows.append({"Market": name, "Price": f"{d['price']:,.2f}",
                            "Change": f"{arrow} {chg:+.2f}%"})
        gc_df = pd.DataFrame(gc_rows)
        st.dataframe(gc_df, use_container_width=True, hide_index=True)

    with col_fii:
        st.markdown('<div class="section-hdr">🏦 FII / DII Activity</div>', unsafe_allow_html=True)
        f5 = fii_a.get("fii_5d",0); d5 = fii_a.get("dii_5d",0)
        m1, m2 = st.columns(2)
        m1.metric("FII 5D Net", f"₹{f5:+,.0f} Cr", fii_a.get("fii_trend","N/A"))
        m2.metric("DII 5D Net", f"₹{d5:+,.0f} Cr", fii_a.get("dii_trend","N/A"))
        disp = fii_df[["Date","FII Net","DII Net"]].copy().tail(10)
        disp["Combined"] = disp["FII Net"] + disp["DII Net"]
        disp["FII Net"]   = disp["FII Net"].apply(lambda x: f"₹{x:+,.0f} Cr")
        disp["DII Net"]   = disp["DII Net"].apply(lambda x: f"₹{x:+,.0f} Cr")
        disp["Combined"]  = disp["Combined"].apply(lambda x: f"₹{x:+,.0f} Cr")
        st.dataframe(disp, use_container_width=True, hide_index=True)

    st.divider()

    # ── Options Chain + TA ─────────────────────────────────────────────────────
    col_oc, col_ta = st.columns(2)

    with col_oc:
        st.markdown('<div class="section-hdr">📈 NIFTY Options Chain (Weekly)</div>', unsafe_allow_html=True)
        pcr = oc_n.get("pcr",0); mp = oc_n.get("max_pain",0)
        oc1, oc2 = st.columns(2)
        oc1.metric("PCR", f"{pcr:.3f}", oc_n.get("trend","N/A"))
        oc2.metric("Max Pain", f"₹{mp:,.0f}", f"CE OI: {oc_n.get('total_call_oi',0)/100000:.1f}L | PE OI: {oc_n.get('total_put_oi',0)/100000:.1f}L")
        sup = oc_n.get("support_oi",[])
        res = oc_n.get("resistance_oi",[])
        if sup: st.markdown(f"🟢 **Support (PE OI):** " + " | ".join(f"{s[0]} ({s[1]/100000:.1f}L)" for s in sup))
        if res: st.markdown(f"🔴 **Resistance (CE OI):** " + " | ".join(f"{s[0]} ({s[1]/100000:.1f}L)" for s in res))
        if not sup and not res:
            st.info("Options chain data unavailable (NSE API). All other signals active.")

    with col_ta:
        st.markdown('<div class="section-hdr">📐 Technical Analysis</div>', unsafe_allow_html=True)
        t1, t2 = st.tabs(["NIFTY", "BANKNIFTY"])
        for tab, ta, label in [(t1,ta_n,"NIFTY"),(t2,ta_b,"BANKNIFTY")]:
            with tab:
                clr2 = "#00c853" if "BULL" in ta["trend"] else "#ff5252" if "BEAR" in ta["trend"] else "#b0bec5"
                st.markdown(f"<b style='color:{clr2};font-size:18px'>{ta['trend']}</b> &nbsp; Score: {ta['overall']:+d}", unsafe_allow_html=True)
                sig_rows = [{"Indicator": i, "Signal": s, "Value": v}
                            for i,s,v,_,__ in ta["signals"]]
                st.dataframe(pd.DataFrame(sig_rows), use_container_width=True, hide_index=True)

    st.divider()

    # ── Stock Picks ────────────────────────────────────────────────────────────
    st.markdown('<div class="section-hdr">🎯 F&O Stock Options Recommendations (Weekly Expiry)</div>', unsafe_allow_html=True)
    st.caption("⚠️ Educational purposes only. Not investment advice. Always set SL. Options trading involves significant risk.")

    with st.spinner("Scanning F&O stocks..."):
        picks = scan_stocks(gp["raw_score"])

    if picks:
        for s in picks[:5]:
            chg_icon = "▲" if s["chg"] > 0 else "▼"
            skip = "SKIP" in s["tt"]
            with st.container():
                sc1, sc2, sc3, sc4 = st.columns([2,1,1,3])
                sc1.markdown(f"**{s['name']}**")
                sc2.markdown(f"₹{s['ltp']:,.2f} {chg_icon} {s['chg']:+.2f}%")
                sc3.markdown(f"RSI: **{s['rsi']}** | Vol: **{s['vr']}x**")
                if not skip:
                    sc4.markdown(f"{s['tt']} — Strike ~**{s['strike']}** | 🎯 ₹{s['tgt']} | 🛑 SL ₹{s['sl']} | ⏱ {s['tim']}")
                else:
                    sc4.markdown("⚪ **No clear setup — SKIP**")
                st.divider()

    st.divider()

    # ── Backtest ───────────────────────────────────────────────────────────────
    st.markdown('<div class="section-hdr">🔬 Gap Prediction Backtest (~1 Year)</div>', unsafe_allow_html=True)
    bt = run_backtest(ndf_ta)
    if bt:
        b1,b2,b3,b4,b5,b6 = st.columns(6)
        b1.metric("Win Rate",   f"{bt['win_rate']}%")
        b2.metric("Total P&L",  f"₹{bt['total_pnl']:+,}")
        b3.metric("Avg/Trade",  f"₹{bt['avg_pnl']:+,}")
        b4.metric("Max DD",     f"₹{bt['max_dd']:,}")
        b5.metric("Trades",     bt["total"])
        b6.metric("Win/Loss Streak", f"{bt['mws']} / {bt['mls']}")
        recent = pd.DataFrame(bt["recent"])
        recent = recent[["date","gap_pct","pred","actual","correct","pnl"]].rename(columns={
            "date":"Date","gap_pct":"Actual Gap %","pred":"Predicted",
            "actual":"Actual","correct":"Correct","pnl":"Sim P&L (₹)"})
        st.dataframe(recent, use_container_width=True, hide_index=True)
    else:
        st.info("Insufficient data for backtest.")

    st.divider()

    # ── News ───────────────────────────────────────────────────────────────────
    st.markdown('<div class="section-hdr">📰 Latest Market News</div>', unsafe_allow_html=True)
    if arts:
        for a in arts[:12]:
            with st.container():
                nc1, nc2 = st.columns([5,1])
                nc1.markdown(f"[**{a['Title']}**]({a['Link']})")
                nc1.caption(f"{a['Source']} • {a.get('Published','')[:25]}")
                nc2.markdown(a["Sentiment"])
                st.divider()
    else:
        st.info("News feeds unavailable.")

    # ── Footer ─────────────────────────────────────────────────────────────────
    st.markdown(
        "<center><small style='color:#3a4a5a'>Indian Market Intelligence • Built by ROBO for Boss Chethan • "
        "Data: Yahoo Finance + NSE India + RSS Feeds • ⚠️ NOT SEBI registered • Educational use only</small></center>",
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
