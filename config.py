import sys
import json
import time
import threading
from pathlib import Path

# ── CHECK DEPENDENCIES ────────────────────────────────────────────────────────
try:    from PIL import Image;          HAS_PIL        = True
except: HAS_PIL        = False

try:    import img2pdf;                 HAS_IMG2PDF    = True
except: HAS_IMG2PDF    = False

try:    import pdfplumber;              HAS_PDFPLUMBER = True
except: HAS_PDFPLUMBER = False

try:    from docx import Document;      HAS_DOCX       = True
except: HAS_DOCX       = False

try:    from pdf2docx import Converter; HAS_PDF2DOCX   = True
except: HAS_PDF2DOCX   = False

try:    import openpyxl;                HAS_OPENPYXL   = True
except: HAS_OPENPYXL   = False

try:
    import win32com.client
    HAS_OFFICE = True
except:
    HAS_OFFICE = False

import shutil
HAS_FFMPEG = shutil.which("ffmpeg") is not None
HAS_LIBREOFFICE = shutil.which("soffice") is not None or shutil.which("libreoffice") is not None

# ── COLORS & FONTS ─────────────────────────────────────────────────────────────
BG      = "#0B0D15"; SURFACE = "#10131C"; CARD = "#161B27"; CARD2 = "#1C2133"
BORDER  = "#252D3F"; ACCENT = "#6C63FF"; ACCENT2 = "#4F8EF7"
GREEN   = "#22C55E"; RED = "#EF4444"; ORANGE = "#F97316"; YELLOW = "#EAB308"
TEXT    = "#E8ECF5"; TEXT2 = "#8892A4"; TEXT3 = "#3D4A60"
HOVER   = "#1E2436"; BTN = "#252D3F"; BTN_H = "#2E3854"

F_H1  = ("Segoe UI", 22, "bold"); F_H2 = ("Segoe UI", 15, "bold")
F_H3  = ("Segoe UI", 13, "bold"); F_B = ("Segoe UI", 12)
F_S   = ("Segoe UI", 11); F_XS = ("Segoe UI", 10); F_MONO = ("Consolas", 11)

# ── UNIT DATA ───────────────────────────────────────────────────────────────────
UNIT_CATS = {
    "📏  Length": {
        "meter":1,"kilometer":1e3,"centimeter":0.01,"millimeter":0.001,
        "micrometer":1e-6,"nanometer":1e-9,"mile":1609.344,
        "yard":0.9144,"foot":0.3048,"inch":0.0254,"nautical mile":1852,
    },
    "⚖️  Weight": {
        "kilogram":1,"gram":0.001,"milligram":1e-6,"pound":0.453592,
        "ounce":0.0283495,"metric ton":1000,"stone":6.35029,"carat":0.0002,
    },
    "🌡️  Temperature": {"__temp__": True, "units": ["Celsius","Fahrenheit","Kelvin","Rankine"]},
    "🧪  Volume": {
        "liter":1,"milliliter":0.001,"cubic meter":1000,
        "gallon (US)":3.78541,"quart":0.946353,"pint":0.473176,
        "cup":0.236588,"fluid ounce":0.0295735,"tablespoon":0.0147868,"teaspoon":0.00492892,
    },
    "⬛  Area": {
        "square meter":1,"square kilometer":1e6,"square centimeter":0.0001,
        "square mile":2589988,"acre":4046.86,"hectare":10000,
        "square foot":0.092903,"square inch":0.00064516,"square yard":0.836127,
    },
    "💨  Speed": {
        "m/s":1,"km/h":0.277778,"mph":0.44704,"knot":0.514444,"ft/s":0.3048,"mach":340.29,
    },
    "⏱️  Time": {
        "second":1,"millisecond":0.001,"microsecond":1e-6,"nanosecond":1e-9,
        "minute":60,"hour":3600,"day":86400,"week":604800,
        "month":2592000,"year":31536000,"decade":315360000,
    },
    "💾  Data": {
        "byte":1,"kilobyte":1024,"megabyte":1048576,"gigabyte":1073741824,
        "terabyte":1099511627776,"bit":0.125,"kilobit":128,"megabit":131072,"gigabit":134217728,
    },
    "🔵  Pressure": {
        "pascal":1,"kilopascal":1000,"megapascal":1e6,
        "bar":100000,"psi":6894.76,"atm":101325,"mmHg":133.322,
    },
    "⚡  Energy": {
        "joule":1,"kilojoule":1000,"megajoule":1e6,
        "calorie":4.184,"kilocalorie":4184,"watt-hour":3600,"kilowatt-hour":3600000,"BTU":1055.06,
    },
    "💡  Power": {
        "watt":1,"kilowatt":1000,"megawatt":1e6,"gigawatt":1e9,"horsepower":745.7,
    },
    "📐  Angle": {
        "degree":1,"radian":57.2958,"gradian":0.9,"arcminute":1/60,"arcsecond":1/3600,
    },
    "📡  Frequency": {
        "hertz":1,"kilohertz":1000,"megahertz":1e6,"gigahertz":1e9,
    },
}

# ── CURRENCY DATA ───────────────────────────────────────────────────────────────
# ── CURRENCY RATES (Live fetch with embedded fallback) ─────────────────────────
_CACHE_FILE = Path(__file__).parent / "rates_cache.json"
_CACHE_MAX_AGE_HOURS = 6  # refresh every 6 hours

# Your existing hardcoded rates become the fallback
_FALLBACK_RATES = {
    # Major currencies
    "USD": 1.000,  "EUR": 0.920,  "GBP": 0.790,  "JPY": 149.50, "CAD": 1.360,
    "AUD": 1.530,  "CHF": 0.880,  "CNY": 7.240,  "INR": 83.10,  "MXN": 17.10,
    
    # Asia-Pacific
    "HKD": 7.820,  "SGD": 1.340,  "KRW": 1325.0, "THB": 35.10,  "MYR": 4.720,
    "IDR": 15700,  "PHP": 56.20,  "VND": 24500,  "TWD": 31.80,  "NZD": 1.630,
    "PKR": 278.0,  "BDT": 109.5,  "LKR": 304.0,  "NPR": 132.8,  "MMK": 2098,
    "KHR": 4085,   "LAK": 21500,  "MNT": 3415,   "BND": 1.340,  "FJD": 2.220,
    
    # Middle East
    "AED": 3.670,  "SAR": 3.750,  "QAR": 3.640,  "KWD": 0.307,  "OMR": 0.385,
    "BHD": 0.376,  "JOD": 0.709,  "ILS": 3.710,  "IQD": 1310,   "LBP": 89500,
    "SYP": 13000,  "YER": 250.3,
    
    # Europe
    "NOK": 10.50,  "SEK": 10.40,  "DKK": 6.890,  "PLN": 3.970,  "CZK": 22.80,
    "HUF": 357.0,  "RON": 4.600,  "BGN": 1.800,  "HRK": 6.930,  "RSD": 108.0,
    "ISK": 137.2,  "TRY": 30.50,  "RUB": 90.20,  "UAH": 37.50,  "BYN": 3.270,
    "MDL": 18.20,  "GEL": 2.680,  "AMD": 386.5,  "AZN": 1.700,  "KZT": 452.0,
    "UZS": 12700,  "TJS": 10.65,  "KGS": 84.50,  "TMT": 3.500,
    
    # Africa
    "ZAR": 18.60,  "EGP": 30.90,  "NGN": 1580,   "KES": 153.0,  "GHS": 15.20,
    "TZS": 2525,   "UGX": 3720,   "RWF": 1330,   "ETB": 120.5,  "MAD": 10.15,
    "TND": 3.100,  "DZD": 134.2,  "AOA": 829.0,  "MZN": 63.80,  "ZMW": 26.50,
    "BWP": 13.45,  "NAD": 18.60,  "SZL": 18.60,  "LSL": 18.60,  "MWK": 1735,
    "MGA": 4520,   "MUR": 45.80,  "SCR": 14.20,  "GMD": 67.50,  "SLL": 19750,
    "LRD": 193.5,  "GNF": 8620,   "XOF": 603.5,  "XAF": 603.5,
    
    # Americas
    "BRL": 4.970,  "ARS": 354.0,  "CLP": 897.0,  "COP": 3950,   "PEN": 3.720,
    "VES": 36.20,  "BOB": 6.910,  "PYG": 7350,   "UYU": 39.15,  "CRC": 509.0,
    "GTQ": 7.730,  "HNL": 24.85,  "NIO": 36.75,  "PAB": 1.000,  "DOP": 58.50,
    "HTG": 131.5,  "JMD": 155.0,  "TTD": 6.790,  "BBD": 2.020,  "BSD": 1.000,
    "BZD": 2.020,  "XCD": 2.700,  "GYD": 209.5,  "SRD": 36.50,  "AWG": 1.790,
    "ANG": 1.790,  "CUP": 24.00,  "BMD": 1.000,  "KYD": 0.833,
    
    # Additional regions
    "ALL": 93.80,  "MKD": 56.70,  "BAM": 1.800,  "AFN": 70.50,  "IRR": 42000,
    "IMP": 0.790,  "GGP": 0.790,  "JEP": 0.790,  "FOK": 6.890,  "GIP": 0.790,
    "FKP": 0.790,  "SHP": 0.790,  "TVD": 1.530,  "SBD": 8.520,  "TOP": 2.340,
    "WST": 2.720,  "VUV": 119.5,  "PGK": 3.950,  "ZWL": 322.0,  "STN": 22.55,
    "CVE": 101.5,  "CDF": 2785,   "BIF": 2890,   "DJF": 177.7,  "KMF": 453.0,
    "SOS": 571.5,  "SSP": 130.2,  "SDG": 601.5,  "ERN": 15.00,
}
def _load_cache():
    """Load rates from local cache file if it's fresh enough."""
    try:
        if _CACHE_FILE.exists():
            data = json.loads(_CACHE_FILE.read_text())
            age_hours = (time.time() - data.get("timestamp", 0)) / 3600
            if age_hours < _CACHE_MAX_AGE_HOURS:
                return data["rates"]
    except Exception:
        pass
    return None

def _fetch_live_rates():
    """
    Fetches from open.er-api.com — free, no key, 160+ currencies.
    Falls back to cache, then to hardcoded rates. Never crashes the app.
    """
    try:
        import urllib.request
        url = "https://open.er-api.com/v6/latest/USD"
        req = urllib.request.Request(url, headers={"User-Agent": "UniversalConverter/2.1"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
        if data.get("result") == "success":
            rates = data["rates"]   # already USD-based, 160+ currencies
            rates["USD"] = 1.0
            # Save to cache
            _CACHE_FILE.write_text(json.dumps({"timestamp": time.time(), "rates": rates}))
            return rates
    except Exception as e:
        print(f"[Currency] Live fetch failed: {e}")
    return None

def _init_rates():
    """Returns rates dict: live > cache > hardcoded fallback."""
    cached = _load_cache()
    if cached:
        print(f"[Currency] Loaded {len(cached)} rates from cache.")
        return cached
    live = _fetch_live_rates()
    if live:
        print(f"[Currency] Loaded {len(live)} live rates.")
        return live
    print("[Currency] Using embedded fallback rates.")
    return _FALLBACK_RATES

# This is what the rest of the app uses — populated once at startup
CURRENCY_RATES = _init_rates()

# Background refresh: fetch silently after app loads without blocking startup
def _background_refresh():
    live = _fetch_live_rates()
    if live:
        CURRENCY_RATES.clear()
        CURRENCY_RATES.update(live)
        print(f"[Currency] Background refresh complete: {len(live)} rates.")

threading.Thread(target=_background_refresh, daemon=True).start()

# ── FORMATS ────────────────────────────────────────────────────────────────────
AUDIO_FMTS  = ["mp3","wav","flac","aac","ogg","m4a","wma","opus","aiff","ac3"]
VIDEO_FMTS  = ["mp4","avi","mov","mkv","webm","flv","wmv","m4v","ts","3gp"]
IMG_IN      = ["jpg","jpeg","png","webp","gif","bmp","tiff","tif","ico"]
IMG_OUT     = ["jpg","png","webp","gif","bmp","tiff","pdf"]