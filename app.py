import streamlit as st
import pandas as pd
import yfinance as yf
import requests
from bs4 import BeautifulSoup
import time

# --- Page Configuration ---
st.set_page_config(page_title="Strategic Full Scanner", layout="wide")

st.title("🛡️ Strategic Full-Market Scanner")
st.markdown("Full pagination scan of Finviz symbols followed by multi-stage technical analysis.")

# --- Sidebar Configuration ---
st.sidebar.title("Scanner Controls")
show_stage_0 = st.sidebar.checkbox("Show Stage 0 (Full Finviz List)", value=False)
st.sidebar.markdown("---")
use_atr = st.sidebar.toggle("Stage 1: ATR/Vol Conditions", value=True)
use_trend = st.sidebar.toggle("Stage 2: Trend & Pullback", value=False)
use_tech = st.sidebar.toggle("Stage 3: Tech Momentum", value=False)

# --- Core Logic Functions ---
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
                url = f"{base_url}{start_index}"
                res = requests.get(url, headers=HEADERS, timeout=15)
                soup = BeautifulSoup(res.text, "html.parser")
                table = soup.find("table", class_="styled-table-new")
                
                if not table: break
                
                rows = table.find_all("tr", valign="top")
                if not rows: break
                
                page_symbols = [row.find_all("td")[1].text.strip() for row in rows if len(row.find_all("td")) > 1]
                all_symbols.extend(page_symbols)
                
                if len(page_symbols) < 20: break # Last page reached
                
                start_index += 20
                time.sleep(0.3) # Faster but safe
            except:
                break
    return list(set(all_symbols))

def compute_atr(df):
    df = df.copy()
    df["H-L"] = df["High"] - df["Low"]
    df["H-PC"] = abs(df["High"] - df["Close"].shift())
    df["L-PC"] = abs(df["Low"] - df["Close"].shift())
    df["TR"] = df[["H-L", "H-PC", "L-PC"]].max(axis=1)
    df["ATR"] = df["TR"].rolling(window=1).mean() 
    return df

# --- Execution Engine ---
if st.sidebar.button("🚀 START FULL SCAN"):
    with st.spinner("Step 0: Scraping all pages from Finviz..."):
        symbols = get_all_finviz_symbols()
    
    if show_stage_0:
        st.info(f"Stage 0 Complete: Found {len(symbols)} unique symbols.")
        st.write(", ".join(sorted(symbols)))
    
    results = []
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    # Large scale analysis
    for i, symbol in enumerate(symbols):
        status_text.text(f"Deep Analysis: {symbol} ({i+1}/{len(symbols)})")
        try:
            # Period of 2y is sufficient for 500-day trend check
            data = yf.Ticker(symbol).history(period="2y", interval="1d")
            if len(data) < 260: continue

            # --- Stage 1: Weekly ATR/VOL Check ---
            weekly = data.resample('W').agg({'High':'max','Low':'min','Close':'last','Volume':'sum'})
            weekly = compute_atr(weekly)
            if len(weekly) < 2: continue
            
            w1, w2 = weekly.iloc[-2], weekly.iloc[-1]
            vol_pct = (w2['Volume'] / w1['Volume'] - 1) * 100
            atr_pct = (w2['ATR'] / w1['ATR'] - 1) * 100
            
            cond_label = None
            if (w2['Volume'] > w1['Volume'] and w2['ATR'] < w1['ATR']):
                cond_label = "Compression (Vol↑ ATR↓)"
            elif (vol_pct > 20 and atr_pct < 5):
                cond_label = "Quiet Breakout (Vol↑↑ ATR~)"
            elif (vol_pct > -5 and atr_pct < -20):
                cond_label = "Exhaustion (ATR↓↓ Vol~)"

            if use_atr and cond_label is None:
                continue

            # --- Stage 2: Trend & Pullback ---
            p_now = data['Close'].iloc[-1]
            # Use oldest available data for trend if 500 days aren't available
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

            results.append({
                "Symbol": symbol,
                "Action": "LONG 🟢" if lt_trend == "UP" else "SHORT 🔴",
                "Condition": cond_label if cond_label else "Pass (Stage 1 Off)",
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
        st.subheader(f"✅ Final Selection: {len(results)} Stocks Passed All Criteria")
        
        def color_action(val):
            color = '#00ff00' if 'LONG' in val else '#ff4b4b'
            return f'color: {color}; font-weight: bold'

        st.dataframe(df.style.applymap(color_action, subset=['Action']), use_container_width=True)
        
        csv = df.to_csv(index=False).encode('utf-8')
        st.download_button("📥 Export Full Results (CSV)", csv, "scan_results.csv", "text/csv")
        st.download_button("📥 Export Symbols (TradingView)", "\n".join(df['Symbol']), "watchlist.txt")
    else:
        st.warning("Scan complete. No stocks matched your strict criteria today.")
