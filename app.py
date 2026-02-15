import streamlit as st
import pandas as pd
import yfinance as yf
import requests
from bs4 import BeautifulSoup
import time

st.set_page_config(page_title="Strategic Scanner FIX", layout="wide")
st.title("🛡️ Strategic Scanner (Anti-Hang Version)")

# מנגנון הגנה: הגבלת כמות המניות לניתוח אם האתר קורס
MAX_SYMBOLS = 100 

HEADERS = {"User-Agent": "Mozilla/5.0"}

def get_symbols_safe():
    symbols = []
    # הוספת מגבלת עמודים קשיחה למניעת לולאה אינסופית
    urls = [
        "https://finviz.com/screener.ashx?v=111&f=ind_stocksonly,sh_avgvol_o1000,sh_price_50to100,ta_averagetruerange_o2.5&r=",
        "https://finviz.com/screener.ashx?v=111&f=ind_stocksonly,sh_avgvol_o1000,sh_price_10to50,ta_averagetruerange_o1.5&r="
    ]
    for base in urls:
        for i in range(1, 101, 20): # מקסימום 5 עמודים לכל פילטר לביטחון
            try:
                r = requests.get(f"{base}{i}", headers=HEADERS, timeout=5)
                soup = BeautifulSoup(r.text, "html.parser")
                rows = soup.find_all("tr", valign="top")
                if not rows: break
                symbols.extend([row.find_all("td")[1].text.strip() for row in rows if len(row.find_all("td")) > 1])
                time.sleep(0.5)
            except: break
    return list(set(symbols))

if st.sidebar.button("🚀 Run Analysis"):
    with st.spinner("Step 1: Getting Symbols..."):
        all_symbols = get_symbols_safe()
        # צמצום הרשימה אם היא גדולה מדי לביצועי ענן
        all_symbols = all_symbols[:MAX_SYMBOLS]
        st.write(f"Analyzing top {len(all_symbols)} symbols to prevent server hang.")

    results = []
    progress = st.progress(0)
    
    for idx, sym in enumerate(all_symbols):
        try:
            # הוספת timeout קצר ל-yfinance
            data = yf.Ticker(sym).history(period="1y", timeout=3)
            if data.empty: continue
            
            # לוגיקה טכנית בקצרה... (ATR, SMA וכו')
            # ...
            
            results.append({"Symbol": sym, "Price": data['Close'].iloc[-1]})
        except: continue
        progress.progress((idx + 1) / len(all_symbols))
    
    if results:
        st.table(pd.DataFrame(results))
