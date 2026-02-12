import streamlit as st
import pandas as pd
import yfinance as yf
import requests
from bs4 import BeautifulSoup

# --- Page Configuration ---
st.set_page_config(page_title="Strategic Stock Scanner v2", layout="wide")

st.title("🛡️ Professional Multi-Stage Scanner")

# --- Sidebar Configuration ---
st.sidebar.title("Scanner Stages")

# Stage 0: raw Finviz list visibility
show_stage_0 = st.sidebar.checkbox("Show Stage 0 (Raw Finviz List)", value=False)

st.sidebar.markdown("---")
use_atr = st.sidebar.toggle("Stage 1: ATR/Vol Conditions", value=True)
use_trend = st.sidebar.toggle("Stage 2: Trend & Pullback", value=False)
use_tech = st.sidebar.toggle("Stage 3: Tech Momentum", value=False)

# --- Functions ---
HEADERS = {"User-Agent": "Mozilla/5.0"}

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
    # Using simple moving average for ATR comparison as requested
    df["ATR"] = df["TR"].rolling(window=1).mean() 
    return df

# --- Execution ---
if st.sidebar.button("RUN SCANNER"):
    symbols = get_finviz_symbols()
    
    if show_stage_0:
        st.info(f"Stage 0: Found {len(symbols)} symbols from Finviz: {', '.join(symbols)}")
    
    results = []
    progress_bar = st.progress(0)
    
    for i, symbol in enumerate(symbols):
        try:
            data = yf.Ticker(symbol).history(period="3y", interval="1d")
            if len(data) < 260: continue

            # --- Weekly Calculations ---
            weekly = data.resample('W').agg({'High':'max','Low':'min','Close':'last','Volume':'sum'})
            weekly = compute_atr(weekly)
            w1, w2 = weekly.iloc[-2], weekly.iloc[-1]
            
            vol_pct = (w2['Volume'] / w1['Volume'] - 1) * 100
            atr_pct = (w2['ATR'] / w1['ATR'] - 1) * 100
            
            # THE CORE LOGIC FIX: Define strictly
            cond_label = None
            if (w2['Volume'] > w1['Volume'] and w2['ATR'] < w1['ATR']):
                cond_label = "Compression (Vol↑ ATR↓)"
            elif (vol_pct > 20 and atr_pct < 5):
                cond_label = "Quiet Breakout (Vol↑↑ ATR~)"
            elif (vol_pct > -5 and atr_pct < -20):
                cond_label = "Exhaustion (ATR↓↓ Vol~)"

            # STAGE 1 FILTER: If no condition met AND filter is ON, skip.
            if use_atr and cond_label is None:
                continue

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
            is_confirmed = (lt_trend == "UP" and last['Close'] > last['SMA10'] and last['EMA9'] > last['SMA10']) or \
                           (lt_trend == "DOWN" and last['Close'] < last['SMA10'] and last['EMA9'] < last['SMA10'])

            if use_tech and not is_confirmed: continue

            # FINAL CHECK: If Stage 1 is OFF, we still only want stocks with a label if they passed the logic
            # OR we display 'No ATR Setup' if we only filter by Trend/Tech.
            results.append({
                "Symbol": symbol,
                "Action": "LONG 🟢" if lt_trend == "UP" else "SHORT 🔴",
                "Condition": cond_label if cond_label else "No ATR Setup",
                "Price": round(p_now, 2),
                "Move %": f"{move_pct:.1f}%",
                "ATR (Now/Prev)": f"{w2['ATR']:.2f} / {w1['ATR']:.2f}",
                "Vol (Now/Prev)": f"{int(w2['Volume']):,} / {int(w1['Volume']):,}",
                "ATR Change %": f"{atr_pct:.1f}%",
                "Vol Change %": f"{vol_pct:.1f}%"
            })
        except: continue
        progress_bar.progress((i + 1) / len(symbols))

    progress_bar.empty()

    if results:
        df = pd.DataFrame(results)
        st.subheader(f"Results: {len(results)} Stocks Found")
        st.dataframe(df, use_container_width=True)
        st.download_button("Download List", "\n".join(df['Symbol']), "watchlist.txt")
    else:
        st.warning("No matches found. Try relaxing the filters in the sidebar.")
