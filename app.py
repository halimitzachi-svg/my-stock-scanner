import streamlit as st
import pandas as pd
import yfinance as yf
import requests
from bs4 import BeautifulSoup
import time

# --- Page Configuration ---
st.set_page_config(page_title="Strategic Scanner (Cached)", layout="wide")

st.title("🛡️ Strategic Scanner with Instant Filtering")
st.markdown("Full scan is cached for 1 hour. Changing filters will now be instant.")

# --- Functions ---
HEADERS = {"User-Agent": "Mozilla/5.0"}

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
                rows = soup.find("table", class_="styled-table-new").find_all("tr", valign="top")
                page_symbols = [r.find_all("td")[1].text.strip() for r in rows if len(r.find_all("td")) > 1]
                all_symbols.extend(page_symbols)
                if len(page_symbols) < 20: break
                start_index += 20
                time.sleep(0.2)
            except: break
    return list(set(all_symbols))

def compute_atr(df):
    df = df.copy()
    df["TR"] = df[["High", "Low", "Close"]].max(axis=1) # Simplified for cache speed
    df["ATR"] = df["TR"].rolling(window=1).mean() 
    return df

# --- THE CACHE MAGIC ---
# This function runs only once per hour OR if symbols change.
@st.cache_data(ttl=3600)
def perform_full_technical_analysis(symbols):
    processed_data = []
    progress_bar = st.progress(0)
    
    for i, symbol in enumerate(symbols):
        try:
            data = yf.Ticker(symbol).history(period="2y", interval="1d")
            if len(data) < 260: continue

            # Weekly data
            weekly = data.resample('W').agg({'High':'max','Low':'min','Close':'last','Volume':'sum'})
            weekly = compute_atr(weekly)
            w1, w2 = weekly.iloc[-2], weekly.iloc[-1]
            
            # Daily Technicals
            data['SMA10'] = data['Close'].rolling(window=10).mean()
            data['EMA9'] = data['Close'].ewm(span=9, adjust=False).mean()
            last_day = data.iloc[-1]
            
            # LT Trend & Move
            p_now = data['Close'].iloc[-1]
            p_old = data['Close'].iloc[-500] if len(data) >= 500 else data['Close'].iloc[0]
            recent_max = data.tail(126)['High'].max()
            recent_min = data.tail(126)['Low'].min()

            processed_data.append({
                "Symbol": symbol,
                "Price": p_now,
                "LT_Trend": "UP" if p_now > p_old else "DOWN",
                "Move_Pct": ((p_now / recent_max) - 1) * 100 if p_now > p_old else ((p_now / recent_min) - 1) * 100,
                "W2_Vol": w2['Volume'], "W1_Vol": w1['Volume'],
                "W2_ATR": w2['ATR'], "W1_ATR": w1['ATR'],
                "Close_Daily": last_day['Close'],
                "SMA10_Daily": last_day['SMA10'],
                "EMA9_Daily": last_day['EMA9']
            })
        except: continue
        progress_bar.progress((i + 1) / len(symbols))
    progress_bar.empty()
    return pd.DataFrame(processed_data)

# --- UI Controls ---
st.sidebar.title("Controls")
if st.sidebar.button("Force Fresh Scan"):
    st.cache_data.clear()

st.sidebar.markdown("---")
use_atr = st.sidebar.toggle("Stage 1: ATR/Vol", value=True)
use_trend = st.sidebar.toggle("Stage 2: Trend/Pullback", value=False)
use_tech = st.sidebar.toggle("Stage 3: Tech Confirm", value=False)

# --- Main Logic ---
all_symbols = get_all_finviz_symbols()
raw_data_df = perform_full_technical_analysis(all_symbols)

if not raw_data_df.empty:
    # INSTANT FILTERING LOGIC
    filtered_df = raw_data_df.copy()

    # Stage 1 Filter
    def check_atr(row):
        v_pct = (row['W2_Vol'] / row['W1_Vol'] - 1) * 100
        a_pct = (row['W2_ATR'] / row['W1_ATR'] - 1) * 100
        if (row['W2_Vol'] > row['W1_Vol'] and row['W2_ATR'] < row['W1_ATR']): return "Compression"
        if (v_pct > 20 and a_pct < 5): return "Quiet Breakout"
        if (v_pct > -5 and a_pct < -20): return "Exhaustion"
        return None

    filtered_df['Condition'] = filtered_df.apply(check_atr, axis=1)
    if use_atr:
        filtered_df = filtered_df[filtered_df['Condition'].notnull()]

    # Stage 2 Filter
    if use_trend:
        filtered_df = filtered_df[((filtered_df['LT_Trend'] == "UP") & (filtered_df['Move_Pct'] <= -15)) | 
                                  ((filtered_df['LT_Trend'] == "DOWN") & (filtered_df['Move_Pct'] >= 15))]

    # Stage 3 Filter
    if use_tech:
        long_c = (filtered_df['LT_Trend'] == "UP") & (filtered_df['Close_Daily'] > filtered_df['SMA10_Daily']) & (filtered_df['EMA9_Daily'] > filtered_df['SMA10_Daily'])
        short_c = (filtered_df['LT_Trend'] == "DOWN") & (filtered_df['Close_Daily'] < filtered_df['SMA10_Daily']) & (filtered_df['EMA9_Daily'] < filtered_df['SMA10_Daily'])
        filtered_df = filtered_df[long_c | short_c]

    st.subheader(f"Results: {len(filtered_df)} Matches")
    st.dataframe(filtered_df[['Symbol', 'LT_Trend', 'Condition', 'Price', 'Move_Pct']])
    st.download_button("Get TV List", "\n".join(filtered_df['Symbol']), "watchlist.txt")
