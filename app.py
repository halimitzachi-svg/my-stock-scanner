import streamlit as st
import pandas as pd
import yfinance as yf
import requests
from bs4 import BeautifulSoup
import time

# --- Page Configuration ---
st.set_page_config(page_title="ATR/VOL Pro Scanner", layout="wide")

st.title("🛡️ ATR & Volume Strategic Scanner")
st.markdown("Full market scan with interactive sorting. Click on any column header to sort.")

# --- Sidebar: Legend & Controls ---
st.sidebar.title("📖 Legend")
st.sidebar.info("""
**1. Compression:** Vol↑ ATR↓ (Coiling Spring)
**2. Quiet Breakout:** Vol↑↑ ATR~ (Early Move)
**3. Exhaustion:** ATR↓↓ Vol~ (Stabilizing)
""")

st.sidebar.markdown("---")
st.sidebar.subheader("Scanner Settings")
s1_filter = st.sidebar.toggle("Filter: Only Stage 1 matches", value=True)

# --- Core Functions ---
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

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
    if not vol_prev or not atr_prev: return None
    v_pct = (vol_now / vol_prev - 1) * 100
    a_pct = (atr_now / atr_prev - 1) * 100
    if vol_now > vol_prev and atr_now < atr_prev: return "Compression"
    if v_pct > 20 and a_pct < 5: return "Quiet Breakout"
    if v_pct > -5 and a_pct < -20: return "Exhaustion"
    return None

# --- Execution ---
if st.sidebar.button("🚀 RUN SCANNER"):
    symbols = get_all_symbols()
    st.info(f"Found {len(symbols)} symbols. Starting deep analysis...")
    
    results = []
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    for i, symbol in enumerate(symbols):
        status_text.text(f"Analyzing {symbol} ({i+1}/{len(symbols)})")
        try:
            data = yf.Ticker(symbol).history(period="1y", interval="1d", timeout=10)
            if len(data) < 100: continue

            # --- Technicals ---
            data['SMA10'] = data['Close'].rolling(window=10).mean()
            data['EMA9'] = data['Close'].ewm(span=9, adjust=False).mean()
            
            p_now = data['Close'].iloc[-1]
            p_old = data['Close'].iloc[0]
            lt_trend = "UP" if p_now > p_old else "DOWN"

            # Momentum Days
            mom_days = 0
            recent_data = data.tail(12)
            for j in range(len(recent_data)-1, -1, -1):
                row = recent_data.iloc[j]
                if lt_trend == "UP":
                    if row['EMA9'] > row['SMA10']: mom_days += 1
                    else: break
                else:
                    if row['EMA9'] < row['SMA10']: mom_days += 1
                    else: break

            # --- Weekly History ---
            weekly = data.resample('W').agg({'High':'max','Low':'min','Close':'last','Volume':'sum'})
            weekly['TR'] = weekly[['High', 'Low', 'Close']].max(axis=1)
            weekly['ATR'] = weekly['TR'].rolling(window=1).mean()
            
            if len(weekly) < 4: continue
            w0, w1, w2, w3 = weekly.iloc[-1], weekly.iloc[-2], weekly.iloc[-3], weekly.iloc[-4]

            c0 = check_atr_logic(w0['Volume'], w1['Volume'], w0['ATR'], w1['ATR'])
            c1 = check_atr_logic(w1['Volume'], w2['Volume'], w1['ATR'], w2['ATR'])
            c2 = check_atr_logic(w2['Volume'], w3['Volume'], w2['ATR'], w3['ATR'])

            streak_num = 0
            if c0:
                streak_num = 1
                if c1:
                    streak_num = 2
                    if c2: streak_num = 3

            if s1_filter and not c0: continue

            results.append({
                "Symbol": symbol,
                "Setup": "LONG 🟢" if lt_trend == "UP" else "SHORT 🔴",
                "Mom_Days": mom_days,
                "Streak": "🔥" * streak_num if streak_num > 1 else ("V" if streak_num == 1 else ""),
                "Streak_Score": streak_num, # Hidden helper for sorting
                "Condition": c0 if c0 else "-",
                "Price": round(p_now, 2),
                "ATR Chg %": round((w0['ATR']/w1['ATR']-1)*100, 1),
                "Vol Chg %": round((w0['Volume']/w1['Volume']-1)*100, 1),
                "W1 Setup": c1 if c1 else "-",
                "W2 Setup": c2 if c2 else "-"
            })
        except: continue
        progress_bar.progress((i + 1) / len(symbols))

    status_text.empty()
    progress_bar.empty()

    if results:
        df = pd.DataFrame(results)
        # Sort by Momentum Days descending by default
        df = df.sort_values(by="Mom_Days", ascending=False)
        
        st.subheader(f"Matches: {len(df)}")
        # We display Streak and hide Streak_Score to keep it clean
        st.dataframe(
            df[['Symbol', 'Setup', 'Mom_Days', 'Streak', 'Condition', 'Price', 'ATR Chg %', 'Vol Chg %']], 
            use_container_width=True
        )
        
        st.download_button("📥 Download Watchlist", "\n".join(df['Symbol']), "watchlist.txt")
    else:
        st.warning("No matches found.")
