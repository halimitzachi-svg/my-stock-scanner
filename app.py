import streamlit as st
import pandas as pd
import yfinance as yf
import requests
from bs4 import BeautifulSoup
import time
from datetime import datetime

st.set_page_config(page_title="Strategic Scanner v4", layout="wide")
st.title("🛡️ Advanced Strategic Stock Scanner")

# --- Functions ---
HEADERS = {"User-Agent": "Mozilla/5.0"}

def get_all_symbols():
    URLS = [
        "https://finviz.com/screener.ashx?v=111&f=ind_stocksonly,sh_avgvol_o1000,sh_price_50to100,ta_averagetruerange_o2.5&r=",
        "https://finviz.com/screener.ashx?v=111&f=ind_stocksonly,sh_avgvol_o1000,sh_price_10to50,ta_averagetruerange_o1.5&r="
    ]
    all_symbols = []
    for base_url in URLS:
        start_index = 1
        while True:
            try:
                res = requests.get(f"{base_url}{start_index}", headers=HEADERS, timeout=10)
                soup = BeautifulSoup(res.text, "html.parser")
                rows = soup.find("table", class_="styled-table-new").find_all("tr", valign="top")
                page_symbols = [r.find_all("td")[1].text.strip() for r in rows]
                all_symbols.extend(page_symbols)
                if len(page_symbols) < 20: break
                start_index += 20
            except: break
    return list(set(all_symbols))

def check_atr_logic(vol_now, vol_prev, atr_now, atr_prev):
    v_pct = (vol_now / vol_prev - 1) * 100
    a_pct = (atr_now / atr_prev - 1) * 100
    if vol_now > vol_prev and atr_now < atr_prev: return "Compression"
    if v_pct > 20 and a_pct < 5: return "Quiet Breakout"
    if v_pct > -5 and a_pct < -20: return "Exhaustion"
    return None

@st.cache_data(ttl=3600)
def get_full_analysis(symbols):
    results = []
    for symbol in symbols:
        try:
            data = yf.Ticker(symbol).history(period="2y", interval="1d")
            if len(data) < 260: continue
            
            # --- Technicals for Momentum Column ---
            data['SMA10'] = data['Close'].rolling(window=10).mean()
            data['EMA9'] = data['Close'].ewm(span=9, adjust=False).mean()
            
            # LT Trend
            p_now = data['Close'].iloc[-1]
            p_old = data['Close'].iloc[-500] if len(data) >= 500 else data['Close'].iloc[0]
            trend = "UP" if p_now > p_old else "DOWN"

            # Momentum Counter (Last 12 days)
            momentum_count = 0
            recent_data = data.tail(12).copy()
            for i in range(len(recent_data)):
                row = recent_data.iloc[i]
                if trend == "UP":
                    if row['EMA9'] > row['SMA10']: momentum_count += 1
                    else: momentum_count = 0 # Reset on cross-under
                else:
                    if row['EMA9'] < row['SMA10']: momentum_count += 1
                    else: momentum_count = 0 # Reset on cross-over

            # --- Weekly History (Current, -1W, -2W) ---
            weekly = data.resample('W').agg({'High':'max','Low':'min','Close':'last','Volume':'sum'})
            weekly['TR'] = weekly[['High', 'Low', 'Close']].max(axis=1) # Simplified
            weekly['ATR'] = weekly['TR'].rolling(window=1).mean()
            
            w_now = weekly.iloc[-1]
            w_prev1 = weekly.iloc[-2]
            w_prev2 = weekly.iloc[-3]
            w_prev3 = weekly.iloc[-4]

            cond_now = check_atr_logic(w_now['Volume'], w_prev1['Volume'], w_now['ATR'], w_prev1['ATR'])
            cond_w1 = check_atr_logic(w_prev1['Volume'], w_prev2['Volume'], w_prev1['ATR'], w_prev2['ATR'])
            cond_w2 = check_atr_logic(w_prev2['Volume'], w_prev3['Volume'], w_prev2['ATR'], w_prev3['ATR'])

            # Streak Calculation
            streak = 1 if cond_now else 0
            if cond_now and cond_w1: streak = 2
            if cond_now and cond_w1 and cond_w2: streak = 3

            results.append({
                "Symbol": symbol, "Price": p_now, "Trend": trend,
                "Mom_Days": momentum_count,
                "Cond_Now": cond_now, "Cond_W1": cond_w1, "Cond_W2": cond_w2,
                "Streak": streak,
                "Last_Close": p_now, "SMA10": last_val(data, 'SMA10'), "EMA9": last_val(data, 'EMA9'),
                "Move_Pct": ((p_now / data.tail(126)['High'].max()) - 1) * 100 if trend == "UP" else ((p_now / data.tail(126)['Low'].min()) - 1) * 100
            })
        except: continue
    return pd.DataFrame(results)

def last_val(df, col): return df[col].iloc[-1]

# --- UI ---
st.sidebar.button("♻️ Refresh Cache", on_click=lambda: st.cache_data.clear())
s1 = st.sidebar.toggle("Stage 1: ATR/Vol", value=True)
s2 = st.sidebar.toggle("Stage 2: Trend Pullback", value=False)
s3 = st.sidebar.toggle("Stage 3: Tech Confirm", value=False)

db = get_full_analysis(get_all_symbols())

tab1, tab2 = st.tabs(["🎯 Current Scanner", "⏳ History Analysis"])

with tab1:
    f = db.copy()
    if s1: f = f[f['Cond_Now'].notnull()]
    if s2: f = f[((f['Trend']=="UP") & (f['Move_Pct']<=-15)) | ((f['Trend']=="DOWN") & (f['Move_Pct']>=15))]
    if s3: 
        c = (f['Trend']=="UP") & (f['Last_Close']>f['SMA10']) & (f['EMA9']>f['SMA10'])
        c_s = (f['Trend']=="DOWN") & (f['Last_Close']<f['SMA10']) & (f['EMA9']<f['SMA10'])
        f = f[c | c_s]
    
    # Add Streak Icon
    f['Streak_Icon'] = f['Streak'].apply(lambda x: "🔥" * x if x > 1 else "")
    st.dataframe(f[['Symbol', 'Trend', 'Cond_Now', 'Mom_Days', 'Streak_Icon', 'Price']])

with tab2:
    st.subheader("Stocks with ATR/VOL setups in previous weeks")
    hist = db[(db['Cond_W1'].notnull()) | (db['Cond_W2'].notnull())].copy()
    st.dataframe(hist[['Symbol', 'Cond_Now', 'Cond_W1', 'Cond_W2', 'Streak']])
