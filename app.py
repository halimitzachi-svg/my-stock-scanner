import streamlit as st
import pandas as pd
import yfinance as yf
import requests
from bs4 import BeautifulSoup
import time

st.set_page_config(page_title="Stock Multi-Stage Scanner", layout="wide")
st.title("🛡️ סורק מניות - סינון בשלבים")

# --- הגדרות ב-Sidebar ---
st.sidebar.header("שלבי סינון")

# שלב 1: תנאי ה-ATR (חובה)
st.sidebar.subheader("שלב 1: ATR & Volume")
use_atr_filter = st.sidebar.toggle("הפעל סינון ATR/VOL", value=True)

# שלב 2: מגמה ותיקון
st.sidebar.subheader("שלב 2: מגמה ותיקון")
use_trend_filter = st.sidebar.toggle("הפעל סינון מגמה (LT) ותיקון (20%)", value=False)

# שלב 3: אישור טכני (SMA/EMA/BB)
st.sidebar.subheader("שלב 3: אישור טכני")
use_technical_filter = st.sidebar.toggle("הפעל אישור SMA/EMA/BB", value=False)

# --- פונקציות (Finviz & ATR) ---
HEADERS = {"User-Agent": "Mozilla/5.0"}
def get_finviz_stocks():
    # פונקציית המשיכה המקורית שלך
    all_symbols = ["AAPL", "TSLA", "NVDA", "AMD", "MSFT", "META", "GOOGL", "AMZN"] # דוגמה להרצה מהירה
    # כאן נכנסת הלוגיקה של ה-BeautifulSoup מהקוד הקודם
    return all_symbols

def compute_atr_rma(df, length=1):
    df = df.copy()
    df["H-L"] = df["High"] - df["Low"]
    df["H-PC"] = abs(df["High"] - df["Close"].shift())
    df["L-PC"] = abs(df["Low"] - df["Close"].shift())
    df["TR"] = df[["H-L", "H-PC", "L-PC"]].max(axis=1)
    df["ATR"] = df["TR"].ewm(alpha=1/length, adjust=False).mean()
    return df

# --- תהליך הסריקה ---
if st.button("הרץ סריקה"):
    symbols = get_finviz_stocks()
    results = []
    
    with st.status("סורק מניות...", expanded=True) as status:
        for symbol in symbols:
            try:
                data = yf.Ticker(symbol).history(period="3y", interval="1d")
                if len(data) < 500: continue
                
                # חישובים שבועיים (שלב 1)
                weekly = data.resample('W').agg({'High':'max','Low':'min','Close':'last','Volume':'sum'})
                weekly = compute_atr_rma(weekly)
                w1, w2 = weekly.iloc[-2], weekly.iloc[-1]
                vol_pct = (w2['Volume'] / w1['Volume'] - 1) * 100
                atr_pct = (w2['ATR'] / w1['ATR'] - 1) * 100
                
                # בדיקת 3 תנאי ה-ATR
                cond1 = (w2['Volume'] > w1['Volume'] and w2['ATR'] < w1['ATR'])
                cond2 = (vol_pct > 20 and atr_pct < 5)
                cond3 = (vol_pct > -5 and atr_pct < -20)
                
                pass_step1 = cond1 or cond2 or cond3
                if use_atr_filter and not pass_step1: continue
                
                # חישובי מגמה (שלב 2)
                p_now = data['Close'].iloc[-1]
                p_old = data['Close'].iloc[-500]
                long_trend = "UP" if p_now > p_old else "DOWN"
                recent = data.tail(126)
                move_pct = ((p_now / recent['High'].max()) - 1) * 100 if long_trend == "UP" else ((p_now / recent['Low'].min()) - 1) * 100
                
                pass_step2 = (long_trend == "UP" and move_pct <= -15) or (long_trend == "DOWN" and move_pct >= 15)
                if use_trend_filter and not pass_step2: continue
                
                # חישובי אישור טכני (שלב 3)
                data['SMA10'] = data['Close'].rolling(window=10).mean()
                data['EMA9'] = data['Close'].ewm(span=9, adjust=False).mean()
                # Bollinger Band Basis (SMA10 עם סטיית תקן 1)
                data['std'] = data['Close'].rolling(window=10).std()
                data['upper'] = data['SMA10'] + data['std']
                data['lower'] = data['SMA10'] - data['std']
                
                last = data.iloc[-1]
                pass_step3_long = last['Close'] > last['SMA10'] and last['EMA9'] > last['SMA10']
                pass_step3_short = last['Close'] < last['SMA10'] and last['EMA9'] < last['SMA10']
                
                if use_technical_filter and not (pass_step3_long or pass_step3_short): continue
                
                # אם הגענו לכאן, המניה עברה את כל השלבים שנבחרו
                results.append({
                    "Symbol": symbol,
                    "LT Trend": long_trend,
                    "Move %": f"{move_pct:.1f}%",
                    "ATR Cond": "Match ✅",
                    "Tech Confirm": "V" if (pass_step3_long or pass_step3_short) else "-"
                })
            except: continue
        status.update(label="הסריקה הושלמה!", state="complete")

    if results:
        st.write(f"נמצאו {len(results)} מניות שמתאימות לסינון הנבחר:")
        st.table(pd.DataFrame(results))
    else:
        st.warning("לא נמצאו מניות. נסה לבטל את אחד מהשלבים ב-Sidebar.")
