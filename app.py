import streamlit as st
import pandas as pd
import yfinance as yf
import requests
from bs4 import BeautifulSoup
import time

# הגדרות דף
st.set_page_config(page_title="Gemini Stock Pro Scanner", layout="wide")
st.title("📊 סורק מניות אסטרטגי - מודל ציונים")

# --- פרמטרים שניתן לשנות בממשק ---
st.sidebar.header("הגדרות סינון")
min_drop = st.sidebar.slider("מינימום נפילה ללונג (%)", 5, 30, 15)
min_jump = st.sidebar.slider("מינימום עלייה לשורט (%)", 5, 30, 15)
atr_flex = st.sidebar.checkbox("הגמשת תנאי ATR (ווליום עולה בלבד)", True)

# --- פונקציות Scraping ---
HEADERS = {"User-Agent": "Mozilla/5.0"}
URLS = [
    "https://finviz.com/screener.ashx?v=111&f=ind_stocksonly,sh_avgvol_o1000,sh_price_50to100,ta_averagetruerange_o2.5&r=",
    "https://finviz.com/screener.ashx?v=111&f=ind_stocksonly,sh_avgvol_o1000,sh_price_10to50,ta_averagetruerange_o1.5&r="
]

def get_finviz_stocks():
    all_symbols = []
    for base_url in URLS:
        try:
            res = requests.get(base_url + "1", headers=HEADERS, timeout=10)
            soup = BeautifulSoup(res.text, "html.parser")
            table = soup.find("table", class_="styled-table-new")
            if not table: continue
            rows = table.find_all("tr", valign="top")
            for row in rows[:30]: # לוקח 30 ראשונות מכל פילטר למהירות
                cols = row.find_all("td")
                if len(cols) > 1:
                    all_symbols.append(cols[1].text.strip())
        except: continue
    return list(set(all_symbols))

def compute_atr_rma(df, length=1):
    df = df.copy()
    df["H-L"] = df["High"] - df["Low"]
    df["H-PC"] = abs(df["High"] - df["Close"].shift())
    df["L-PC"] = abs(df["Low"] - df["Close"].shift())
    df["TR"] = df[["H-L", "H-PC", "L-PC"]].max(axis=1)
    df["ATR"] = df["TR"].ewm(alpha=1/length, adjust=False).mean()
    return df

# --- תהליך הסריקה ---
if st.button("הפעל סורק"):
    symbols = get_finviz_stocks()
    st.write(f"בודק {len(symbols)} מניות פוטנציאליות...")
    
    results = []
    progress_bar = st.progress(0)

    for i, symbol in enumerate(symbols):
        try:
            data = yf.Ticker(symbol).history(period="3y", interval="1d")
            if len(data) < 500: continue

            # 1. מגמה ארוכה (Price 2Y ago)
            p_now = data['Close'].iloc[-1]
            p_old = data['Close'].iloc[-500]
            trend = "UP" if p_now > p_old else "DOWN"

            # 2. תנועה קיצונית (חצי שנה)
            recent = data.tail(126)
            move_pct = ((p_now / recent['High'].max()) - 1) * 100 if trend == "UP" else ((p_now / recent['Low'].min()) - 1) * 100
            
            # 3. ATR & Vol (Weekly)
            weekly = data.resample('W').agg({'High':'max','Low':'min','Close':'last','Volume':'sum'})
            weekly = compute_atr_rma(weekly)
            w1, w2 = weekly.iloc[-2], weekly.iloc[-1]
            
            # 4. Indicators (Daily)
            data['SMA10'] = data['Close'].rolling(window=10).mean()
            data['EMA9'] = data['Close'].ewm(span=9, adjust=False).mean()
            last = data.iloc[-1]

            # --- מודל הציונים ---
            points = 0
            reasons = []

            # נקודה 1: תנועה חריגה (Mean Reversion)
            if trend == "UP" and move_pct <= -min_drop:
                points += 1
                reasons.append(f"נפילה חדה ({move_pct:.1f}%)")
            elif trend == "DOWN" and move_pct >= min_jump:
                points += 1
                reasons.append(f"עלייה חדה ({move_pct:.1f}%)")

            # נקודה 2: דחיסת ATR/VOL
            if (w2['Volume'] > w1['Volume'] and w2['ATR'] < w1['ATR']):
                points += 1
                reasons.append("דחיסת ATR (ווליום עולה/תנודתיות יורדת)")
            elif atr_flex and (w2['Volume'] > w1['Volume'] * 1.2):
                points += 1
                reasons.append("זינוק בווליום שבועי")

            # נקודה 3: אישור מומנטום (SMA/EMA)
            if trend == "UP" and last['Close'] > last['SMA10'] and last['EMA9'] > last['SMA10']:
                points += 1
                reasons.append("אישור מומנטום (EMA9 > SMA10)")
            elif trend == "DOWN" and last['Close'] < last['SMA10'] and last['EMA9'] < last['SMA10']:
                points += 1
                reasons.append("אישור מומנטום שורט")

            if points >= 2:
                results.append({
                    "Symbol": symbol,
                    "Score": "⭐" * points,
                    "Direction": "LONG" if trend == "UP" else "SHORT",
                    "Reasoning": " + ".join(reasons),
                    "LT Trend": trend,
                    "Move %": f"{move_pct:.1f}%"
                })
        except: continue
        progress_bar.progress((i + 1) / len(symbols))

    if results:
        df = pd.DataFrame(results).sort_values(by="Score", ascending=False)
        st.dataframe(df, use_container_width=True)
        
        # Watchlist Export
        st.download_button("Export Symbols", "\n".join(df['Symbol']), "watchlist.txt")
    else:
        st.warning("לא נמצאו מניות עם ציון 2 ומעלה. נסה להגמיש את הפרמטרים בסרגל הצד.")
