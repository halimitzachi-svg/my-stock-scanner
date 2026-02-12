import streamlit as st
import pandas as pd
import yfinance as yf
import requests
from bs4 import BeautifulSoup
import time

# --- הגדרות דף ותמיכה ב-RTL ---
st.set_page_config(page_title="סורק מניות רב-שלבי", layout="wide")

# הזרקת CSS ליישור לימין
st.markdown("""
    <style>
    /* הגדרת כיוון טקסט כללי לימין */
    .main, .sidebar-content, .stMarkdown, .stButton, .stToggle, .stHeader, p, h1, h2, h3 {
        direction: rtl;
        text-align: right;
    }
    
    /* החרגת הטבלאות - שיישארו משמאל לימין */
    .stDataFrame, .stTable, table {
        direction: ltr !important;
        text-align: left !important;
    }
    
    /* תיקון ל-Sidebar שייצמד לימין (במידה והוא לא) */
    [data-testid="stSidebar"] {
        direction: rtl;
    }
    
    /* סידור הכפתורים */
    div.stButton > button:first-child {
        display: block;
        margin-right: 0;
        margin-left: auto;
    }
    </style>
    """, unsafe_allow_html=True)

st.title("🛡️ סורק מניות - סינון בשלבים")

# --- הגדרות ב-Sidebar (תפריט צד) ---
st.sidebar.header("הגדרות סינון")

# שלב 1: תנאי ה-ATR (חובה)
st.sidebar.subheader("שלב 1: ATR ו-Volume")
use_atr_filter = st.sidebar.toggle("הפעל סינון ATR/VOL שבועי", value=True)

# שלב 2: מגמה ותיקון
st.sidebar.subheader("שלב 2: מגמה ותיקון מחיר")
use_trend_filter = st.sidebar.toggle("סינון מגמה ראשית ותיקון (15%+)", value=False)

# שלב 3: אישור טכני (SMA/EMA/BB)
st.sidebar.subheader("שלב 3: אישור ומומנטום")
use_technical_filter = st.sidebar.toggle("הפעל אישור SMA/EMA (יומי)", value=False)

# --- פונקציות (Finviz & ATR) ---
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36"}

def get_finviz_symbols():
    # פונקציית המשיכה המלאה מ-Finviz כפי שהופיעה בקוד הקודם שלך
    URLS = [
        "https://finviz.com/screener.ashx?v=111&f=ind_stocksonly,sh_avgvol_o1000,sh_price_50to100,ta_averagetruerange_o2.5&r=",
        "https://finviz.com/screener.ashx?v=111&f=ind_stocksonly,sh_avgvol_o1000,sh_price_10to50,ta_averagetruerange_o1.5&r="
    ]
    all_symbols = []
    for url in URLS:
        try:
            res = requests.get(url + "1", headers=HEADERS, timeout=10)
            soup = BeautifulSoup(res.text, "html.parser")
            table = soup.find("table", class_="styled-table-new")
            if table:
                rows = table.find_all("tr", valign="top")
                for row in rows[:25]: # הגבלה למהירות
                    cols = row.find_all("td")
                    if len(cols) > 1: all_symbols.append(cols[1].text.strip())
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
if st.button("הפעל סריקה עכשיו"):
    symbols = get_finviz_symbols()
    if not symbols:
        st.error("לא הצלחתי למשוך מניות מ-Finviz. נסה שוב מאוחר יותר.")
    else:
        results = []
        st.write(f"מתחיל ניתוח עומק עבור {len(symbols)} מניות...")
        
        progress_bar = st.progress(0)
        
        for i, symbol in enumerate(symbols):
            try:
                data = yf.Ticker(symbol).history(period="3y", interval="1d")
                if len(data) < 500: continue
                
                # --- שלב 1: ATR/VOL שבועי ---
                weekly = data.resample('W').agg({'High':'max','Low':'min','Close':'last','Volume':'sum'})
                weekly = compute_atr_rma(weekly)
                w1, w2 = weekly.iloc[-2], weekly.iloc[-1]
                
                vol_pct = (w2['Volume'] / w1['Volume'] - 1) * 100
                atr_pct = (w2['ATR'] / w1['ATR'] - 1) * 100
                
                # 3 הקריטריונים שלך
                cond1 = (w2['Volume'] > w1['Volume'] and w2['ATR'] < w1['ATR'])
                cond2 = (vol_pct > 20 and atr_pct < 5)
                cond3 = (vol_pct > -5 and atr_pct < -20)
                
                pass_step1 = cond1 or cond2 or cond3
                if use_atr_filter and not pass_step1: continue
                
                # --- שלב 2: מגמה ותיקון ---
                p_now = data['Close'].iloc[-1]
                p_old = data['Close'].iloc[-500]
                long_trend = "UP" if p_now > p_old else "DOWN"
                
                recent = data.tail(126)
                move_pct = ((p_now / recent['High'].max()) - 1) * 100 if long_trend == "UP" else ((p_now / recent['Low'].min()) - 1) * 100
                
                # תנאי תיקון של 15% (ניתן לשינוי)
                pass_step2 = (long_trend == "UP" and move_pct <= -15) or (long_trend == "DOWN" and move_pct >= 15)
                if use_trend_filter and not pass_step2: continue
                
                # --- שלב 3: אישור טכני (SMA/EMA) ---
                data['SMA10'] = data['Close'].rolling(window=10).mean()
                data['EMA9'] = data['Close'].ewm(span=9, adjust=False).mean()
                last = data.iloc[-1]
                
                is_long = last['Close'] > last['SMA10'] and last['EMA9'] > last['SMA10']
                is_short = last['Close'] < last['SMA10'] and last['EMA9'] < last['SMA10']
                
                if use_technical_filter and not (is_long or is_short): continue
                
                # שמירת תוצאה
                results.append({
                    "Symbol": symbol,
                    "Direction": "LONG 🟢" if long_trend == "UP" else "SHORT 🔴",
                    "Price": round(p_now, 2),
                    "Move_from_Peak": f"{move_pct:.1f}%",
                    "Weekly_Vol_Change": f"{vol_pct:.1f}%",
                    "Tech_Confirm": "V" if (is_long or is_short) else "-"
                })
            except: continue
            progress_bar.progress((i + 1) / len(symbols))

        if results:
            st.success(f"נמצאו {len(results)} מניות העונות על הדרישות!")
            st.table(pd.DataFrame(results))
            
            # ייצוא רשימה
            symbols_text = "\n".join([r['Symbol'] for r in results])
            st.download_button("הורד רשימה ל-TradingView", symbols_text, file_name="watchlist.txt")
        else:
            st.warning("לא נמצאו מניות העונות על שילוב הסינונים שנבחר.")
