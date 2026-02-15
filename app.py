import streamlit as st
import pandas as pd
import yfinance as yf
import requests
from bs4 import BeautifulSoup
import time

# --- Page Configuration ---
st.set_page_config(page_title="Strategic Full Scanner", layout="wide")

st.title("🛡️ Strategic Full-Market Scanner")
st.markdown("Direct scan from Finviz & Yahoo Finance (No Cache).")

# --- Sidebar Controls ---
st.sidebar.title("Scanner Settings")
s1_on = st.sidebar.toggle("Stage 1: ATR/Vol Conditions", value=True)
s2_on = st.sidebar.toggle("Stage 2: Trend & Pullback", value=False)
s3_on = st.sidebar.toggle("Stage 3: Tech Momentum", value=False)

# --- Core Functions ---
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

def get_all_symbols():
    """Scrapes all pages from Finviz filters."""
    URLS = [
        "https://finviz.com/screener.ashx?v=111&f=ind_stocksonly,sh_avgvol_o1000,sh_price_50to100,ta_averagetruerange_o2.5&r=",
        "https://finviz.com/screener.ashx?v=111&f=ind_stocksonly,sh_avgvol_o1000,sh_price_10to50,ta_averagetruerange_o1.5&r="
    ]
    all_symbols = []
    for base_url in URLS:
        start_index = 1
        while True:
            try:
                res = requests.get(f"{base_url}{start_index}", headers=HEADERS, timeout=15)
                soup = BeautifulSoup(res.text, "html.parser")
                table = soup.find("table", class_="styled-table-new")
                if not table: break
                rows = table.find_all("tr", valign="top")
                if not rows: break
                
                page_symbols = [r.find_all("td")[1].text.strip() for r in rows if len(r.find_all("td")) > 1]
                all_symbols.extend(page_symbols)
                
                if len(page_symbols) < 20: break
                start_index += 20
                time.sleep(0.2)
            except: break
    return list(set(all_symbols))

def check_atr_logic(vol_now, vol_prev, atr_now, atr_prev):
    """3 ATR/VOL Conditions."""
    if vol_prev == 0 or atr_prev == 0: return None
    v_pct = (vol_now / vol_prev - 1) * 100
    a_pct = (atr_now / atr_prev - 1) * 100
    if vol_now > vol_prev and atr_now < atr_prev: return "Compression"
    if v_pct > 20 and a_pct < 5: return "Quiet Breakout"
    if v_pct > -5 and a_pct < -20: return "Exhaustion"
    return None

# --- Execution Logic ---
if st.sidebar.button("🚀 RUN FULL SCAN"):
    symbols = get_all_symbols()
    st.info(f"Found {len(symbols)} symbols. Starting deep analysis...")
    
    results = []
    progress_bar = st.progress(0)
    
    for i, symbol in enumerate(symbols):
        try:
            # Download 2 years of daily data
            data = yf.Ticker(symbol).history(period="2y", interval="1d", timeout=10)
            if len(data) < 260: continue

            # --- Technical Indicators ---
            data['SMA10'] = data['Close'].rolling(window=10).mean()
            data['EMA9'] = data['Close'].ewm(span=9, adjust=False).mean()
            
            p_now = data['Close'].iloc[-1]
            p_old = data['Close'].iloc[-500] if len(data) >= 500 else data['Close'].iloc[0]
            lt_trend = "UP" if p_now > p_old else "DOWN"

            # --- Momentum Counter (Reverse sampling from today) ---
            mom_days = 0
            recent_12 = data.tail(12)
            for j in range(len(recent_12)-1, -1, -1):
                row = recent_12.iloc[j]
                if lt_trend == "UP":
                    if row['EMA9'] > row['SMA10']: mom_days += 1
                    else: break
                else:
                    if row['EMA9'] < row['SMA10']: mom_days += 1
                    else: break

            # --- Weekly Logic (Current + History) ---
            weekly = data.resample('W').agg({'High':'max','Low':'min','Close':'last','Volume':'sum'})
            weekly['TR'] = weekly[['High', 'Low', 'Close']].max(axis=1)
            weekly['ATR'] = weekly['TR'].rolling(window=1).mean()
            
            if len(weekly) < 4: continue
            w0, w1, w2, w3 = weekly.iloc[-1], weekly.iloc[-2], weekly.iloc[-3], weekly.iloc[-4]

            c0 = check_atr_logic(w0['Volume'], w1['Volume'], w0['ATR'], w1['ATR'])
            c1 = check_atr_logic(w1['Volume'], w2['Volume'], w1['ATR'], w2['ATR'])
            c2 = check_atr_logic(w2['Volume'], w3['Volume'], w2['ATR'], w3['ATR'])

            # Streak check
            streak = 0
            if c0:
                streak = 1
                if c1:
                    streak = 2
                    if c2: streak = 3

            # --- Apply Filters ---
            # Stage 1
            if s1_on and not c0: continue
            
            # Stage 2
            r_max = data.tail(126)['High'].max()
            r_min = data.tail(126)['Low'].min()
            move_pct = ((p_now / r_max) - 1) * 100 if lt_trend == "UP" else ((p_now / r_min) - 1) * 100
            
            if s2_on:
                pass_s2 = (lt_trend == "UP" and move_pct <= -15) or (lt_trend == "DOWN" and move_pct >= 15)
                if not pass_s2: continue
            
            # Stage 3
            last_d = data.iloc[-1]
            is_conf = (lt_trend == "UP" and last_d['Close'] > last_d['SMA10'] and last_d['EMA9'] > last_d['SMA10']) or \
                      (lt_trend == "DOWN" and last_d['Close'] < last_d['SMA10'] and last_d['EMA9'] < last_d['SMA10'])
            
            if s3_on and not is_conf: continue

            results.append({
                "Symbol": symbol,
                "Setup": "LONG 🟢" if lt_trend == "UP" else "SHORT 🔴",
                "Mom_Days": mom_days,
                "Streak": "🔥" * streak if streak > 1 else ("V" if streak == 1 else ""),
                "Condition": c0,
                "Price": round(p_now, 2),
                "Move %": f"{move_pct:.1f}%",
                "W1 Setup": c1 if c1 else "-",
                "W2 Setup": c2 if c2 else "-"
            })
        except: continue
        progress_bar.progress((i + 1) / len(symbols))

    if results:
        df = pd.DataFrame(results)
        tab1, tab2 = st.tabs(["Active Scanner", "Full Details"])
        
        with tab1:
            st.dataframe(df[['Symbol', 'Setup', 'Mom_Days', 'Streak', 'Condition', 'Price']], use_container_width=True)
            st.download_button("Download TV List", "\n".join(df['Symbol']), "watchlist.txt")
        
        with tab2:
            st.dataframe(df, use_container_width=True)
    else:
        st.warning("No matches found. Try relaxing the filter stages.")
