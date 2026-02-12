import streamlit as st
import pandas as pd
import yfinance as yf
import requests
from bs4 import BeautifulSoup

# --- הגדרות דף ותמיכה ב-RTL משופרת ---
st.set_page_config(page_title="סורק מניות מקצועי", layout="wide")

# CSS מתוקן: סידור RTL בלי לשבור את העיצוב
st.markdown("""
    <style>
    /* הגדרת כיוון כללי וריווחים */
    .main .block-container {
        direction: rtl;
        text-align: right;
    }
    
    /* סידור ה-Sidebar */
    [data-testid="stSidebar"] {
        direction: rtl;
        text-align: right;
    }
    
    /* החרגת הטבלה - שתמיד תהיה משמאל לימין ובמרכז */
    [data-testid="stDataFrame"], [data-testid="stTable"] {
        direction: ltr !important;
        text-align: left !important;
        margin-top: 20px;
    }
    
    /* כפתור הפעלה מעוצב */
    div.stButton > button:first-child {
        background-color: #0066cc;
        color: white;
        border-radius: 8px;
        padding: 0.5rem 2rem;
        margin-bottom: 20px;
    }

    /* תיקון טקסטים בכפתורים ובוררים */
    .stCheckbox, .stToggleButton, .stSlider {
        direction: rtl;
    }
    </style>
    """, unsafe_allow_html=True)

# כותרת עם אייקון
st.title("🛡️ סורק מניות אסטרטגי")
st.write("מערכת סינון רב-שלבית מבוססת דחיסת ATR ומגמות")

# --- תפריט צד ---
st.sidebar.title("⚙️ הגדרות סינון")
st.sidebar.markdown("---")

st.sidebar.subheader("שלב 1: דחיסה שבועית")
use_atr = st.sidebar.toggle("סינון ATR/VOL שבועי", value=True)

st.sidebar.subheader("שלב 2: מגמה ותיקון")
use_trend = st.sidebar.toggle("מגמה ראשית + תיקון (15%+)", value=False)

st.sidebar.subheader("שלב 3: אישור יומי")
use_tech = st.sidebar.toggle("אישור SMA/EMA יומי", value=False)

# --- פונקציות עזר ---
HEADERS = {"User-Agent": "Mozilla/5.0"}

def get_symbols():
    # פונקציית Finviz המקורית (מקוצרת לצורך הדוגמה)
    return ["AAPL", "NVDA", "TSLA", "ATAT", "AMD", "MSFT", "GOOGL", "AMZN"]

def compute_atr(df):
    df = df.copy()
    df["H-L"] = df["High"] - df["Low"]
    df["H-PC"] = abs(df["High"] - df["Close"].shift())
    df["L-PC"] = abs(df["Low"] - df["Close"].shift())
    df["TR"] = df[["H-L", "H-PC", "L-PC"]].max(axis=1)
    df["ATR"] = df["TR"].ewm(alpha=1/1, adjust=False).mean()
    return df

# --- ריצת הסורק ---
if st.button("🚀 הרץ סריקה עכשיו"):
    raw_symbols = get_symbols()
    results = []
    
    status_text = st.empty()
    bar = st.progress(0)
    
    for i, symbol in enumerate(raw_symbols):
        status_text.text(f"מנתח את {symbol}...")
        try:
            data = yf.Ticker(symbol).history(period="3y", interval="1d")
            if len(data) < 200: continue
            
            # לוגיקה טכנית (שלב 1, 2, 3)
            # ... (כאן נכנסת כל הלוגיקה של ה-ATR והמגמה מהקוד הקודם) ...
            
            # לצורך התצוגה נניח שמצאנו התאמה (דוגמה)
            results.append({
                "Symbol": symbol,
                "Direction": "LONG" if i%2==0 else "SHORT",
                "Price": round(data['Close'].iloc[-1], 2),
                "Move %": "-9.1%",
                "Volume Change": "+25.7%",
                "Tech": "V"
            })
        except: continue
        bar.progress((i + 1) / len(raw_symbols))
    
    status_text.empty()
    bar.empty()

    if results:
        st.subheader(f"✅ נמצאו {len(results)} מניות מתאימות")
        
        # המרת התוצאות ל-DataFrame
        df = pd.DataFrame(results)
        
        # עיצוב מותנה לטבלה (צבעים)
        def style_direction(val):
            color = '#2ecc71' if val == 'LONG' else '#e74c3c'
            return f'color: {color}; font-weight: bold'

        styled_df = df.style.applymap(style_direction, subset=['Direction'])
        
        st.dataframe(styled_df, use_container_width=True)
        
        # הורדה
        st.download_button("📥 הורד Watchlist", "\n".join(df['Symbol']), "stocks.txt")
    else:
        st.warning("אין תוצאות התואמות את הסינון.")
