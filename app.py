import streamlit as st
import pandas as pd
import yfinance as yf
import requests
from bs4 import BeautifulSoup
import time
from datetime import datetime, timedelta

# הגדרות כותרת
st.set_page_config(page_title="Gemini Pro Stock Scanner", layout="wide")
st.title("🔍 סורק מניות אסטרטגי: ATR Convergence & Mean Reversion")

# --- פונקציות עזר (Scraping & Data) ---

HEADERS = {"User-Agent": "Mozilla/5.0"}
URLS = [
    "https://finviz.com/screener.ashx?v=111&f=ind_stocksonly,sh_avgvol_o1000,sh_price_50to100,ta_averagetruerange_o2.5&r=",
    "https://finviz.com/screener.ashx?v=111&f=ind_stocksonly,sh_avgvol_o1000,sh_price_10to50,ta_averagetruerange_o1.5&r="
]

def get_finviz_stocks():
    all_symbols = []
    for base_url in URLS:
        start_index = 1
        while start_index < 100: # מגבלה ל-100 מניות ראשונות לכל פילטר למהירות
            url = base_url + str(start_index)
            res = requests.get(url, headers=HEADERS)
            soup = BeautifulSoup(res.text, "html.parser")
            table = soup.find("table", class_="styled-table-new")
            if not table: break
            
            rows = table.find_all("tr", valign="top")
            if not rows: break
            
            for row in rows:
                cols = row.find_all("td")
                if len(cols) > 1:
                    all_symbols.append(cols[1].text.strip())
            start_index += 20
            time.sleep(0.5)
    return list(set(all_symbols))

def compute_atr_rma(df, length=1):
    df = df.copy()
    df["H-L"] = df["High"] - df["Low"]
    df["H-PC"] = abs(df["High"] - df["Close"].shift())
    df["L-PC"] = abs(df["Low"] - df["Close"].shift())
    df["TR"] = df[["H-L", "H-PC", "L-PC"]].max(axis=1)
    df["ATR"] = df["TR"].ewm(alpha=1/length, adjust=False).mean()
    return df

# --- ממשק משתמש ---

if st.button("התחל סריקה"):
    with st.spinner("מושך מניות מ-Finviz..."):
        symbols = get_finviz_stocks()
        st.write(f"נמצאו {len(symbols)} מניות ראשוניות. מתחיל ניתוח עומק...")

    results = []
    progress_bar = st.progress(0)
    
    for i, symbol in enumerate(symbols):
        try:
            # הורדת נתונים ל-3 שנים
            data = yf.Ticker(symbol).history(period="3y", interval="1d")
            if len(data) < 500: continue
            
            # 1. מגמה ארוכת טווח (שנתיים אחורה)
            price_now = data['Close'].iloc[-1]
            price_2y_ago = data['Close'].iloc[-500]
            long_term_trend = "UP" if price_now > price_2y_ago else "DOWN"
            
            # 2. תיקון של 20% בטווח הקצר/בינוני (חצי שנה אחרונה)
            recent_data = data.tail(126) # חצי שנה
            max_recent = recent_data['High'].max()
            min_recent = recent_data['Low'].min()
            drop_from_high = (price_now / max_recent - 1) * 100
            jump_from_low = (price_now / min_recent - 1) * 100
            
            # 3. חישובי ATR ו-Volume שבועיים
            weekly = data.resample('W').agg({'Open':'first','High':'max','Low':'min','Close':'last','Volume':'sum'})
            weekly = compute_atr_rma(weekly)
            w1, w2 = weekly.iloc[-2], weekly.iloc[-1]
            atr_pct = (w2['ATR'] / w1['ATR'] - 1) * 100
            vol_pct = (w2['Volume'] / w1['Volume'] - 1) * 100
            
            # 4. אישור יומי (SMA10, EMA9, Bollinger Basis)
            data['SMA10'] = data['Close'].rolling(window=10).mean()
            data['EMA9'] = data['Close'].ewm(span=9, adjust=False).mean()
            last_day = data.iloc[-1]
            
            # לוגיקת החלטה
            action = "Hold"
            
            # תנאי לונג
            if long_term_trend == "UP" and drop_from_high <= -20:
                if last_day['Close'] > last_day['SMA10'] and last_day['EMA9'] > last_day['SMA10']:
                    if (w2['Volume'] > w1['Volume'] and w2['ATR'] < w1['ATR']) or (vol_pct > 20 and atr_pct < 5):
                        action = "LONG 🟢"

            # תנאי שורט
            elif long_term_trend == "DOWN" and jump_from_low >= 20:
                if last_day['Close'] < last_day['SMA10'] and last_day['EMA9'] < last_day['SMA10']:
                    if (w2['Volume'] > w1['Volume'] and w2['ATR'] < w1['ATR']) or (vol_pct > 20 and atr_pct < 5):
                        action = "SHORT 🔴"

            if action != "Hold":
                results.append({
                    "Symbol": symbol,
                    "Action": action,
                    "LT Trend": long_term_trend,
                    "Move %": f"{drop_from_high:.1f}%" if action == "LONG 🟢" else f"{jump_from_low:.1f}%",
                    "ATR Change": f"{atr_pct:.1f}%",
                    "Vol Change": f"{vol_pct:.1f}%"
                })

        except Exception as e:
            continue
        
        progress_bar.progress((i + 1) / len(symbols))

    if results:
        df_res = pd.DataFrame(results)
        st.table(df_res)
        
        # יצירת Watchlist ל-TradingView
        tv_list = "\n".join([r['Symbol'] for r in results])
        st.download_button("הורד Watchlist ל-TradingView", tv_list, file_name="watchlist.txt")
    else:
        st.write("לא נמצאו מניות העונות על כל הקריטריונים כרגע.")