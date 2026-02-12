import streamlit as st
import pandas as pd
import yfinance as yf
import requests
from bs4 import BeautifulSoup

# --- Page Configuration ---
st.set_page_config(page_title="Multi-Stage Stock Scanner", layout="wide")

st.markdown("""
    <style>
    div.stButton > button:first-child {
        background-color: #007bff;
        color: white;
        width: 100%;
        font-weight: bold;
    }
    .stDataFrame { border: 1px solid #30363d; }
    </style>
    """, unsafe_allow_html=True)

st.title("🛡️ Strategic Stock Scanner")

# --- Sidebar ---
st.sidebar.title("Filter Stages")
use_atr = st.sidebar.toggle("Stage 1: ATR/Vol Conditions", value=True)
use_trend = st.sidebar.toggle("Stage 2: Trend & Pullback", value=False)
use_tech = st.sidebar.toggle("Stage 3: Tech Momentum", value=False)

# --- Functions ---
HEADERS = {"User-Agent": "Mozilla/5.0"}

def get_symbols():
    # Scraping symbols from Finviz (Top 50 results for speed)
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
                for row in rows[:25]:
                    cols = row.find_all("td")
                    if len(cols) > 1: symbols.append(cols[1].text.strip())
        except: continue
    return list(set(symbols))

def compute_atr(df):
    df = df.copy()
    df["H-L"] = df["High"] - df["Low"]
    df["H-PC"] = abs(df["High"] - df["Close"].shift())
    df["L-PC"] = abs(df["Low"] - df["Close"].shift())
    df["TR"] = df[["H-L", "H-PC", "L-PC"]].max(axis=1)
    df["ATR"] = df["TR"].ewm(alpha=1, adjust=False).mean()
    return df

# --- Execution ---
if st.sidebar.button("RUN SCANNER"):
    symbols = get_symbols()
    results = []
    
    progress_bar = st.progress(0)
    status_text = st.empty()

    for i, symbol in enumerate(symbols):
        status_text.text(f"Processing {symbol}...")
        try:
            data = yf.Ticker(symbol).history(period="3y", interval="1d")
            if len(data) < 260: continue

            # --- Weekly Calculations ---
            weekly = data.resample('W').agg({'High':'max','Low':'min','Close':'last','Volume':'sum'})
            weekly = compute_atr(weekly)
            w1, w2 = weekly.iloc[-2], weekly.iloc[-1]
            
            vol_pct = (w2['Volume'] / w1['Volume'] - 1) * 100
            atr_pct = (w2['ATR'] / w1['ATR'] - 1) * 100
            
            # Identifying which ATR condition met
            cond_label = None
            if (w2['Volume'] > w1['Volume'] and w2['ATR'] < w1['ATR']):
                cond_label = "Compression (Vol↑ ATR↓)"
            elif (vol_pct > 20 and atr_pct < 5):
                cond_label = "Quiet Breakout (Vol↑↑ ATR~)"
            elif (vol_pct > -5 and atr_pct < -20):
                cond_label = "Exhaustion (ATR↓↓ Vol~)"

            if use_atr and not cond_label: continue

            # --- Trend & Pullback ---
            p_now = data['Close'].iloc[-1]
            p_old = data['Close'].iloc[-500] if len(data) >= 500 else data['Close'].iloc[0]
            lt_trend = "UP" if p_now > p_old else "DOWN"
            
            recent_max = data.tail(126)['High'].max()
            recent_min = data.tail(126)['Low'].min()
            move_pct = ((p_now / recent_max) - 1) * 100 if lt_trend == "UP" else ((p_now / recent_min) - 1) * 100
            
            if use_trend:
                pass_trend = (lt_trend == "UP" and move_pct <= -15) or (lt_trend == "DOWN" and move_pct >= 15)
                if not pass_trend: continue

            # --- Technical Confirm ---
            data['SMA10'] = data['Close'].rolling(window=10).mean()
            data['EMA9'] = data['Close'].ewm(span=9, adjust=False).mean()
            last = data.iloc[-1]
            is_confirmed = (lt_trend == "UP" and last['Close'] > last['SMA10'] and last['EMA9'] > last['SMA10']) or \
                           (lt_trend == "DOWN" and last['Close'] < last['SMA10'] and last['EMA9'] < last['SMA10'])

            if use_tech and not is_confirmed: continue

            results.append({
                "Symbol": symbol,
                "Action": "LONG 🟢" if lt_trend == "UP" else "SHORT 🔴",
                "Condition": cond_label,
                "Price": round(p_now, 2),
                "Move %": f"{move_pct:.1f}%",
                "ATR (Now/Prev)": f"{w2['ATR']:.2f} / {w1['ATR']:.2f}",
                "Vol (Now/Prev)": f"{int(w2['Volume']):,} / {int(w1['Volume']):,}",
                "ATR Change %": f"{atr_pct:.1f}%",
                "Vol Change %": f"{vol_pct:.1f}%"
            })
        except: continue
        progress_bar.progress((i + 1) / len(symbols))

    status_text.empty()
    progress_bar.empty()

    if results:
        df = pd.DataFrame(results)
        st.subheader(f"Results: {len(results)} Stocks Found")
        
        # Color coding for Action column
        def style_action(val):
            color = '#00ff00' if 'LONG' in val else '#ff4b4b'
            return f'color: {color}; font-weight: bold'

        st.dataframe(df.style.applymap(style_action, subset=['Action']), use_container_width=True)
        st.download_button("Download List", "\n".join(df['Symbol']), "watchlist.txt")
    else:
        st.warning("No matches found.")
