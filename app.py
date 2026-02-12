import streamlit as st
import pandas as pd
import yfinance as yf
import requests
from bs4 import BeautifulSoup
import time
from datetime import datetime

# --- Page Configuration ---
st.set_page_config(page_title="Strategic Scanner PRO", layout="wide")

st.title("🛡️ Strategic Stock Scanner (Stable Version)")

# --- Functions ---
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

def get_all_finviz_symbols():
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

def compute_atr(df):
    temp = df.copy()
    temp["H-L"] = temp["High"] - temp["Low"]
    temp["H-PC"] = abs(temp["High"] - temp["Close"].shift())
    temp["L-PC"] = abs(temp["Low"] - temp["Close"].shift())
    temp["TR"] = temp[["H-L", "H-PC", "L-PC"]].max(axis=1)
    temp["ATR"] = temp["TR"].rolling(window=1).mean()
    return temp

# --- The Core Cache (Saves Raw Tech Data) ---
@st.cache_data(ttl=3600, show_spinner=False)
def get_analysis_database(symbols):
    results = []
    total = len(symbols)
    # שימוש ב-st.empty כדי להראות התקדמות מחוץ ל-Cache
    for i, symbol in enumerate(symbols):
        try:
            ticker = yf.Ticker(symbol)
            data = ticker.history(period="2y", interval="1d")
            if len(data) < 260: continue

            # Weekly calculations for Stage 1
            weekly = data.resample('W').agg({'High':'max','Low':'min','Close':'last','Volume':'sum'})
            weekly = compute_atr(weekly)
            if len(weekly) < 2: continue
            w1, w2 = weekly.iloc[-2], weekly.iloc[-1]

            # Daily calculations for Stage 3
            data['SMA10'] = data['Close'].rolling(window=10).mean()
            data['EMA9'] = data['Close'].ewm(span=9, adjust=False).mean()
            last_d = data.iloc[-1]

            # Trend for Stage 2
            p_now = data['Close'].iloc[-1]
            p_old = data['Close'].iloc[-500] if len(data) >= 500 else data['Close'].iloc[0]
            r_max = data.tail(126)['High'].max()
            r_min = data.tail(126)['Low'].min()

            results.append({
                "Symbol": symbol,
                "Price": p_now,
                "LT_Trend": "UP" if p_now > p_old else "DOWN",
                "Move_Pct": ((p_now / r_max) - 1) * 100 if p_now > p_old else ((p_now / r_min) - 1) * 100,
                "W2_Vol": w2['Volume'], "W1_Vol": w1['Volume'],
                "W2_ATR": w2['ATR'], "W1_ATR": w1['ATR'],
                "Last_Close": last_d['Close'], "SMA10": last_d['SMA10'], "EMA9": last_d['EMA9']
            })
        except: continue
    return pd.DataFrame(results)

# --- Sidebar & UI ---
st.sidebar.title("Controls")
if st.sidebar.button("♻️ Force Refresh All Data"):
    st.cache_data.clear()
    st.rerun()

st.sidebar.markdown("---")
st.sidebar.subheader("Filter Stages")
s1_on = st.sidebar.toggle("Stage 1: ATR/Vol Conditions", value=True)
s2_on = st.sidebar.toggle("Stage 2: Trend & Pullback", value=False)
s3_on = st.sidebar.toggle("Stage 3: Tech Confirm", value=False)

# --- App Logic ---
symbols_list = get_all_finviz_symbols()

with st.spinner(f"Analyzing {len(symbols_list)} stocks (Cached for 1 hour)..."):
    db = get_analysis_database(symbols_list)

if db.empty:
    st.warning("No data found. Click Refresh.")
else:
    # Always start with a fresh copy of the database for filtering
    filtered = db.copy()

    # Calculation of conditions (always run, so we can display them)
    def get_cond(row):
        v_pct = (row['W2_Vol'] / row['W1_Vol'] - 1) * 100
        a_pct = (row['W2_ATR'] / row['W1_ATR'] - 1) * 100
        if (row['W2_Vol'] > row['W1_Vol'] and row['W2_ATR'] < row['W1_ATR']): return "Compression"
        if (v_pct > 20 and a_pct < 5): return "Quiet Breakout"
        if (v_pct > -5 and a_pct < -20): return "Exhaustion"
        return None

    filtered['Condition'] = filtered.apply(get_cond, axis=1)

    # --- APPLY FILTERS ---
    if s1_on:
        filtered = filtered[filtered['Condition'].notnull()]
    
    if s2_on:
        filtered = filtered[
            ((filtered['LT_Trend'] == "UP") & (filtered['Move_Pct'] <= -15)) |
            ((filtered['LT_Trend'] == "DOWN") & (filtered['Move_Pct'] >= 15))
        ]
    
    if s3_on:
        long_ok = (filtered['LT_Trend'] == "UP") & (filtered['Last_Close'] > filtered['SMA10']) & (filtered['EMA9'] > filtered['SMA10'])
        short_ok = (filtered['LT_Trend'] == "DOWN") & (filtered['Last_Close'] < filtered['SMA10']) & (filtered['EMA9'] < filtered['SMA10'])
        filtered = filtered[long_ok | short_ok]

    # --- Display ---
    st.write(f"**Last Full Scan Time:** {datetime.now().strftime('%H:%M:%S')} (Using Cached Data)")
    st.subheader(f"Results: {len(filtered)} matches")
    
    display_cols = ['Symbol', 'LT_Trend', 'Condition', 'Price', 'Move_Pct']
    st.dataframe(filtered[display_cols], use_container_width=True)
    
    st.download_button("📥 Download Watchlist", "\n".join(filtered['Symbol']), "watchlist.txt")
