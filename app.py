import streamlit as st
import pandas as pd
import yfinance as yf
import requests
from bs4 import BeautifulSoup
import time

# --- Page Configuration ---
st.set_page_config(page_title="Multi-Stage Stock Scanner", layout="wide")

# Custom CSS for a clean professional look
st.markdown("""
    <style>
    .main {
        background-color: #0e1117;
    }
    div.stButton > button:first-child {
        background-color: #007bff;
        color: white;
        border-radius: 5px;
        width: 100%;
        height: 3em;
        font-weight: bold;
    }
    .stDataFrame {
        border: 1px solid #30363d;
        border-radius: 5px;
    }
    </style>
    """, unsafe_allow_html=True)

st.title("🛡️ Strategic Stock Scanner")
st.markdown("Multi-stage filtering based on ATR compression, Trend, and Technical Momentum.")

# --- Sidebar Configuration ---
st.sidebar.title("Settings")
st.sidebar.markdown("---")

st.sidebar.subheader("Stage 1: ATR & Volume")
use_atr = st.sidebar.toggle("Weekly Compression Filter", value=True)

st.sidebar.subheader("Stage 2: Trend & Pullback")
use_trend = st.sidebar.toggle("LT Trend + 15% Pullback", value=False)

st.sidebar.subheader("Stage 3: Tech Confirm")
use_tech = st.sidebar.toggle("Daily SMA/EMA Confirm", value=False)

# --- Core Functions ---
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

def get_finviz_symbols():
    URLS = [
        "https://finviz.com/screener.ashx?v=111&f=ind_stocksonly,sh_avgvol_o1000,sh_price_50to100,ta_averagetruerange_o2.5&r=",
        "https://finviz.com/screener.ashx?v=111&f=ind_stocksonly,sh_avgvol_o1000,sh_price_10to50,ta_averagetruerange_o1.5&r="
    ]
    symbols = []
    for url in URLS:
        try:
            res = requests.get(url + "1", headers=HEADERS, timeout=10)
            soup = BeautifulSoup(res.text, "html.parser")
            table = soup.find("table", class_="styled-table-new")
            if table:
                rows = table.find_all("tr", valign="top")
                for row in rows[:25]: # Speed optimization
                    cols = row.find_all("td")
                    if len(cols) > 1: symbols.append(cols[1].text.strip())
        except: continue
    return list(set(symbols))

def compute_atr(df, length=1):
    df = df.copy()
    df["H-L"] = df["High"] - df["Low"]
    df["H-PC"] = abs(df["High"] - df["Close"].shift())
    df["L-PC"] = abs(df["Low"] - df["Close"].shift())
    df["TR"] = df[["H-L", "H-PC", "L-PC"]].max(axis=1)
    df["ATR"] = df["TR"].ewm(alpha=1/length, adjust=False).mean()
    return df

# --- Execution ---
if st.sidebar.button("RUN SCANNER"):
    symbols = get_finviz_symbols()
    if not symbols:
        st.error("Could not fetch symbols from Finviz.")
    else:
        results = []
        progress_text = st.empty()
        progress_bar = st.progress(0)
        
        for i, symbol in enumerate(symbols):
            progress_text.text(f"Analyzing {symbol} ({i+1}/{len(symbols)})...")
            try:
                # Download 3 years of daily data
                data = yf.Ticker(symbol).history(period="3y", interval="1d")
                if len(data) < 260: continue
                
                # --- Stage 1: Weekly ATR/VOL ---
                weekly = data.resample('W').agg({'High':'max','Low':'min','Close':'last','Volume':'sum'})
                weekly = compute_atr(weekly)
                w1, w2 = weekly.iloc[-2], weekly.iloc[-1]
                
                vol_pct = (w2['Volume'] / w1['Volume'] - 1) * 100
                atr_pct = (w2['ATR'] / w1['ATR'] - 1) * 100
                
                cond1 = (w2['Volume'] > w1['Volume'] and w2['ATR'] < w1['ATR'])
                cond2 = (vol_pct > 20 and atr_pct < 5)
                cond3 = (vol_pct > -5 and atr_pct < -20)
                
                if use_atr and not (cond1 or cond2 or cond3): continue
                
                # --- Stage 2: Trend & Move ---
                p_now = data['Close'].iloc[-1]
                p_old = data['Close'].iloc[-500] if len(data) >= 500 else data['Close'].iloc[0]
                lt_trend = "UP" if p_now > p_old else "DOWN"
                
                recent_max = data.tail(126)['High'].max()
                recent_min = data.tail(126)['Low'].min()
                move_pct = ((p_now / recent_max) - 1) * 100 if lt_trend == "UP" else ((p_now / recent_min) - 1) * 100
                
                if use_trend:
                    pass_trend = (lt_trend == "UP" and move_pct <= -15) or (lt_trend == "DOWN" and move_pct >= 15)
                    if not pass_trend: continue
                
                # --- Stage 3: Technical Confirm ---
                data['SMA10'] = data['Close'].rolling(window=10).mean()
                data['EMA9'] = data['Close'].ewm(span=9, adjust=False).mean()
                last = data.iloc[-1]
                
                is_long = last['Close'] > last['SMA10'] and last['EMA9'] > last['SMA10']
                is_short = last['Close'] < last['SMA10'] and last['EMA9'] < last['SMA10']
                
                if use_tech and not (is_long or is_short): continue
                
                # Collect result
                results.append({
                    "Symbol": symbol,
                    "Setup": "LONG 🟢" if lt_trend == "UP" else "SHORT 🔴",
                    "Price": round(p_now, 2),
                    "Move %": f"{move_pct:.1f}%",
                    "Weekly Vol": f"{vol_pct:.1f}%",
                    "Tech": "Confirmed" if (is_long or is_short) else "Pending"
                })
            except: continue
            progress_bar.progress((i + 1) / len(symbols))
        
        progress_text.empty()
        progress_bar.empty()

        if results:
            st.subheader(f"Found {len(results)} Stocks")
            df = pd.DataFrame(results)
            
            # Styling
            def color_setup(val):
                color = '#00ff00' if 'LONG' in val else '#ff4b4b'
                return f'color: {color}; font-weight: bold'

            st.dataframe(df.style.applymap(color_setup, subset=['Setup']), use_container_width=True)
            
            # Download
            csv = df.to_csv(index=False)
            st.download_button("Download CSV", csv, "results.csv", "text/csv")
            
            tv_list = "\n".join(df['Symbol'])
            st.download_button("TradingView List", tv_list, "watchlist.txt")
        else:
            st.warning("No stocks found with the current filter settings.")
