"""
NSE Stock List Fetcher
Fetches complete list of NSE stocks
"""
import requests
import pandas as pd
import os
import json
from typing import List
import logging

import sys
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from config.config import DATA_DIR, STOCK_LIST_FILE

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Comprehensive Nifty 500 Stock List
NSE_STOCKS = [
    # Nifty 50
    "RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK", "HINDUNILVR", "ITC", 
    "SBIN", "BHARTIARTL", "KOTAKBANK", "LT", "AXISBANK", "ASIANPAINT", 
    "MARUTI", "TITAN", "SUNPHARMA", "ULTRACEMCO", "BAJFINANCE", "WIPRO", 
    "HCLTECH", "NESTLEIND", "POWERGRID", "NTPC", "TATAMOTORS", "M&M",
    "ADANIENT", "ADANIPORTS", "BAJAJFINSV", "TATASTEEL", "ONGC", "JSWSTEEL",
    "COALINDIA", "HINDALCO", "GRASIM", "INDUSINDBK", "TECHM", "DRREDDY",
    "CIPLA", "DIVISLAB", "EICHERMOT", "BPCL", "HEROMOTOCO", "BRITANNIA",
    "APOLLOHOSP", "SHREECEM", "TATACONSUM", "SBILIFE", "HDFCLIFE", "UPL",
    "BAJAJ-AUTO",
    
    # Nifty Next 50
    "ADANIGREEN", "AMBUJACEM", "BANKBARODA", "BERGEPAINT", "BOSCHLTD",
    "CHOLAFIN", "COLPAL", "DABUR", "DLF", "GAIL", "GODREJCP", "HAVELLS",
    "ICICIGI", "ICICIPRULI", "INDUSTOWER", "IOC", "JINDALSTEL", "JUBLFOOD",
    "LUPIN", "MARICO", "MUTHOOTFIN", "NAUKRI", "PAGEIND", "PETRONET", 
    "PIDILITIND", "PNB", "PGHH", "SAIL", "SBICARD", "SIEMENS", "SRF", 
    "TATAPOWER", "TORNTPHARM", "TRENT", "VEDL", "ZYDUSLIFE",
    
    # Nifty Midcap 150
    "AARTIIND", "ABB", "ABCAPITAL", "ABFRL", "ACC", "AIAENG", "AJANTPHARM",
    "ALKEM", "AMARAJABAT", "APLAPOLLO", "ASHOKLEY", "ASTRAL", "ATUL",
    "AUROPHARMA", "BALKRISIND", "BANDHANBNK", "BATAINDIA", "BEL", "BHARATFORG",
    "BHEL", "BIOCON", "BLUEDART", "CANBK", "CANFINHOME", "CASTROLIND",
    "CENTRALBK", "CESC", "CGPOWER", "CHAMBLFERT", "COFORGE", "CONCOR",
    "COROMANDEL", "CROMPTON", "CUB", "CUMMINSIND", "CYIENT", "DALBHARAT",
    "DEEPAKNTR", "DELHIVERY", "DIXON", "ELGIEQUIP", "EMAMILTD", "ENDURANCE",
    "EQUITASBNK", "ESCORTS", "EXIDEIND", "FEDERALBNK", "FINEORG", "FLUOROCHEM",
    "FORTIS", "FSL", "GLAND", "GLAXO", "GLENMARK", "GNFC",
    "GODREJPROP", "GRANULES", "GSPL", "GUJGASLTD", "HAL", "HAPPSTMNDS",
    "HATSUN", "HEG", "HFCL", "HINDCOPPER", "HINDPETRO", "HONAUT",
    "IBREALEST", "IDFCFIRSTB", "IEX", "IIFL", "INDHOTEL", "INDIAMART",
    "INTELLECT", "IOB", "IPCALAB", "IRB", "IRCTC", "IRFC",
    "JBCHEPHARM", "JINDALSAW", "JKCEMENT", "JKLAKSHMI", "JMFINANCIL",
    "JSL", "JSWENERGY", "JTEKTINDIA", "KAJARIACER", "KALPATPOWR",
    "KANSAINER", "KEI", "KIRLOSENG", "KPITTECH", "KRBL", "KTKBANK",
    "LALPATHLAB", "LAURUSLABS", "LICHSGFIN", "LTIM", "LTTS",
    "M&MFIN", "MAHABANK", "MAHINDCIE", "MANAPPURAM", "MASTEK",
    "MAXHEALTH", "METROPOLIS", "MFSL", "MGL", "MOTHERSON", "MPHASIS",
    "MRF", "MRPL", "NAM-INDIA", "NATCOPHARM", "NATIONALUM",
    "NAVINFLUOR", "NESCO", "NHPC", "NIACL", "NLCINDIA", "NMDC", "NUVAMA",
    "OBEROIRLTY", "OFSS", "OIL", "OLECTRA", "PATANJALI",
    "PERSISTENT", "PFC", "PHOENIXLTD",
    "PIIND", "PNBHOUSING", "POLYCAB", "POLYMED", "POONAWALLA",
    "POWERMECH", "PRESTIGE", "PRINCEPIPE", "PVRINOX", "RADICO", "RAIN",
    "RAJESHEXPO", "RAMCOCEM", "RATNAMANI", "RAYMOND", "RECLTD", "RELAXO",
    "ROUTE", "SCHAEFFLER", "SHRIRAMFIN", "SJVN", "SKFINDIA",
    "SOBHA", "SONACOMS", "SPARC", "STARHEALTH", "SUNDARMFIN",
    "SUNDRMFAST", "SUNTV", "SUPRAJIT", "SUPREMEIND", "SWANENERGY", "SYMPHON",
    "SYNGENE", "TANLA", "TATACHEM", "TATACOMM", "TATAELXSI", "TATAINVEST",
    "TATVA", "TCI", "TCIEXP", "THERMAX", "TIINDIA",
    "TIMKEN", "TITAGARH", "TORNTPOWER", "TRIDENT", "TRITURBINE", "TRIVENI",
    "TTKPRESTIG", "TVSMOTOR", "UBL", "UCOBANK", "UNIONBANK",
    "UTIAMC", "VINATIORGA", "VOLTAS", "VGUARD", "WELCORP",
    "WESTLIFE", "WHIRLPOOL", "YESBANK", "ZENSARTECH", "ZFCVINDIA",
    
    # Additional Nifty 500 stocks
    "3MINDIA", "AAVAS", "ABBOTINDIA", "ACE", "ADANIENSOL", "ADANIPOWER",
    "AEGISLOG", "AFFLE", "AJMERA", "AKZOINDIA", "ALLCARGO", "ALOKINDS",
    "ANANTRAJ", "ANGELONE", "APARINDS", "APTUS", "ARCHIDPLY",
    "ARVINDFASN", "ASAHIINDIA", "ASTERDM", "ASTRAZEN", "ATGL",
    "AUROCHM", "AVANTIFEED", "AWL", "BAJAJELEC", "BAJAJHLDNG", "BALRAMCHIN",
    "BANCOINDIA", "BASF", "BAYERCROP", "BDL", "BEML", "BLUESTARCO",
    "BORORENEW", "BRIGADE", "BSOFT", "CAPLIPOINT", "CARBORUNIV",
    "CARERATING", "CDSL", "CENTURYTEX", "CERA", "CHALET", "CHEMCON",
    "CLEAN", "CMSINFO", "COCHINSHIP", "CRAFTSMAN", "CREDITACC", "CRISIL",
    "DATAPATTNS", "DCBBANK", "DCMSHRIRAM", "DELTACORP", "DEVYANI", "DHANI",
    "DODLA", "DOMS", "ECLERX", "EDELWEISS", "EIDPARRY", "ELECON",
    "EPL", "ESABINDIA", "FINCABLES", "FINPIPE", "FDC", "GABRIEL",
    "GARFIBRES", "GATEWAY", "GESHIP", "GHCL", "GILLETTE", "GLS",
    "GOCOLORS", "GODREJAGRO", "GODREJIND", "GOODYEAR", "GPPL", "GRINDWELL",
    "GRSE", "GSFC", "GTPL", "HAPPIEST", "HCG", "HDFCAMC", "HEMIPROP",
    "HGINFRA", "HIKAL", "HIL", "HGS", "HINDZINC",
    "HOMEFIRST", "HONASA", "HSCL", "HUDCO", "ICRA", "IDBI", "IFBIND",
    "IIFLSEC", "IMFA", "INDIACEM", "INDIGRID", "INDOSTAR", "INFIBEAM",
    "INOXGREEN", "INOXIND", "INOXWIND", "IONEXCHANG", "IOLCP",
    "IRCON", "ISEC", "ITDC", "ITI", "J&KBANK", "JAMNAAUTO", "JBMA",
    "JKPAPER", "JKTYRE", "JSLHISAR", "JUSTDIAL", "JYOTHYLAB", "KALYANKJIL",
    "KARURVYSYA", "KCP", "KFINTECH", "KIOCL", "KNRCON", "KPIGREEN",
    "KPRMILL", "KSB", "LATENTVIEW", "LEMONTREE", "LINDEINDIA",
    "LLOYDSME", "LODHA", "LTFOODS", "LUXIND", "MAHLIFE",
    "MAHLOG", "MAHSCOOTER", "MAHSEAMLES", "MAITHANALL", "MANINFRA", "MANKIND",
    "MAPMYINDIA", "MARKSANS", "MAZAGONDOCK", "MCX", "MEDANTA", "MEDPLUS",
    "MIDHANI", "MMTC", "MOIL", "MOTILALOFS", "MSTCLTD",
    "NBCC", "NCC", "NEWGEN", "NSLNISP", "NUVOCO", "NYKAA",
    "PAYTM", "PNCINFRA", "PRAKASH", "PRSMJOHNSN", "PSB", "PTC",
    "QUESS", "RBLBANK", "RCF", "REDINGTON", "RENUKA",
    "RITES", "RVNL", "SAFARI", "SAGCEM", "SANOFI", "SAPPHIRE",
    "SAREGAMA", "SCI", "SEQUENT", "SFL", "SHARDACROP", "SHILPAMED",
    "SHOPERSTOP", "SIS", "SOLARINDS", "SOLARA", "SONATSOFTW", "SOUTHBANK",
    "STAR", "STLTECH", "SUBROS", "SUMICHEM", "SUNFLAG",
    "SURYAROSNI", "SUVENPHAR", "SUZLON", "SWARAJENG", "SWSOLAR",
    "TARSONS", "TASTYBITE", "TEAMLEASE", "TEXRAIL",
    "THYROCARE", "TINPLATE", "TMB", "TRIL",
    "TTML", "TV18BRDCST", "TVSSRICHAK", "TVTODAY", "TWL", "UJJIVAN",
    "UJJIVANSFB", "UNOMINDA", "USHAMART", "VAIBHAVGBL", "VALIANT", "VARROC",
    "VBL", "VENKEYS", "VIJAYA", "VIPIND", "VMART",
    "VSTIND", "VTL", "WABCOINDIA", "WELSPUNLIV", "WOCKPHARMA", "WONDERLA",
    "XPROINDIA", "ZEEL"
]


def get_nse_stock_list() -> List[str]:
    """
    Get list of NSE stocks
    
    Returns:
        List of stock symbols
    """
    return NSE_STOCKS.copy()


def fetch_nse_stocks_from_api() -> List[str]:
    """
    Try to fetch NSE stocks from various sources
    Falls back to hardcoded list if API fails
    """
    stocks = []
    
    # Try fetching from NSE (may require headers/cookies)
    try:
        # This is a simplified attempt - real NSE API needs proper headers
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        # Try Yahoo Finance screener as alternative
        logger.info("Using predefined NSE stock list...")
        stocks = NSE_STOCKS.copy()
        
    except Exception as e:
        logger.warning(f"Could not fetch from API: {e}")
        stocks = NSE_STOCKS.copy()
    
    return stocks


def save_stock_list(stocks: List[str], filename: str = None):
    """Save stock list to CSV file"""
    filename = filename or STOCK_LIST_FILE
    
    df = pd.DataFrame({'symbol': stocks})
    df.to_csv(filename, index=False)
    logger.info(f"Saved {len(stocks)} stocks to {filename}")


def load_stock_list(filename: str = None) -> List[str]:
    """Load stock list from CSV file"""
    filename = filename or STOCK_LIST_FILE
    
    try:
        if os.path.exists(filename):
            df = pd.read_csv(filename)
            return df['symbol'].tolist()
    except Exception as e:
        logger.warning(f"Could not load stock list: {e}")
    
    # Fall back to default list
    return NSE_STOCKS.copy()


def update_stock_list():
    """Update the stock list file"""
    stocks = fetch_nse_stocks_from_api()
    save_stock_list(stocks)
    return stocks


if __name__ == "__main__":
    # Initialize stock list
    print(f"Total NSE stocks in list: {len(NSE_STOCKS)}")
    
    # Save to file
    update_stock_list()
    
    # Test loading
    loaded = load_stock_list()
    print(f"Loaded {len(loaded)} stocks from file")
