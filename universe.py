"""
PRAGYAM — Universe Selection
══════════════════════════════════════════════════════════════════════════════

Dynamic universe definitions and fetching functions for portfolio analysis.

Supports:
- ETF Index (fixed list of 30 NSE ETFs)
- India Indices (NIFTY 50, NIFTY 500, F&O Stocks, sectoral indices)
- US Indices (S&P 500, DOW JONES, NASDAQ 100)
- Commodities (24 futures)
- Currency (24 pairs)
- Crypto (21 digital assets)

Author: @thebullishvalue
"""

import streamlit as st
import pandas as pd
import requests
import io
from typing import List, Tuple, Optional

# ══════════════════════════════════════════════════════════════════════════════
# UNIVERSE DEFINITIONS
# ══════════════════════════════════════════════════════════════════════════════

# ── ETF Universe (Fixed) ─────────────────────────────────────────────────────
ETF_UNIVERSE = [
    "CHEMICAL.NS", "NIFTYIETF.NS", "MON100.NS", "MAKEINDIA.NS", "SILVERIETF.NS",
    "HEALTHIETF.NS", "CONSUMIETF.NS", "GOLDIETF.NS", "INFRAIETF.NS", "CPSEETF.NS",
    "TNIDETF.NS", "COMMOIETF.NS", "MODEFENCE.NS", "MOREALTY.NS", "PSUBNKIETF.NS",
    "MASPTOP50.NS", "FMCGIETF.NS", "GROWWPOWER.NS", "ITIETF.NS", "EVINDIA.NS",
    "MNC.NS", "FINIETF.NS", "AUTOIETF.NS", "PVTBANIETF.NS", "MONIFTY500.NS",
    "ECAPINSURE.NS", "MIDCAPIETF.NS", "MOSMALL250.NS", "OILIETF.NS", "METALIETF.NS"
]

# ── India Index Universe ─────────────────────────────────────────────────────
INDIA_INDEX_LIST = [
    "NIFTY 50",
    "F&O Stocks",
    # Broad market
    "NIFTY NEXT 50",
    "NIFTY 100",
    "NIFTY 200",
    "NIFTY 500",
    # Midcap
    "NIFTY MIDCAP 50",
    "NIFTY MIDCAP 100",
    "NIFTY MIDCAP 150",
    "NIFTY MID SELECT",
    # Smallcap
    "NIFTY SMLCAP 50",
    "NIFTY SMLCAP 100",
    "NIFTY SMLCAP 250",
    # Sectoral
    "NIFTY BANK",
    "NIFTY PRIVATE BANK",
    "NIFTY PSU BANK",
    "NIFTY AUTO",
    "NIFTY FIN SERVICE",
    "NIFTY FMCG",
    "NIFTY IT",
    "NIFTY MEDIA",
    "NIFTY METAL",
    "NIFTY ENERGY",
    "NIFTY INFRA",
    "NIFTY PHARMA",
    "NIFTY REALTY",
]

# ── US Index Universe ────────────────────────────────────────────────────────
US_INDEX_LIST = ["S&P 500", "DOW JONES", "NASDAQ 100"]

# ── Universe Options for Dropdown ────────────────────────────────────────────
UNIVERSE_OPTIONS = [
    "ETF Index",
    "India Indexes",
    "US Indexes",
    "Commodities",
    "Currency",
    "Crypto",
    "Custom List"
]

# ── Index Sources ────────────────────────────────────────────────────────────
BASE_URL = "https://archives.nseindia.com/content/indices/"
INDEX_URL_MAP = {
    # Broad market
    "NIFTY 50":         f"{BASE_URL}ind_nifty50list.csv",
    "NIFTY NEXT 50":    f"{BASE_URL}ind_niftynext50list.csv",
    "NIFTY 100":        f"{BASE_URL}ind_nifty100list.csv",
    "NIFTY 200":        f"{BASE_URL}ind_nifty200list.csv",
    "NIFTY 500":        f"{BASE_URL}ind_nifty500list.csv",
    # Midcap
    "NIFTY MIDCAP 50":  f"{BASE_URL}ind_niftymidcap50list.csv",
    "NIFTY MIDCAP 100": f"{BASE_URL}ind_niftymidcap100list.csv",
    "NIFTY MIDCAP 150": f"{BASE_URL}ind_niftymidcap150list.csv",
    "NIFTY MID SELECT": f"{BASE_URL}ind_niftymidcapselectlist.csv",
    # Smallcap
    "NIFTY SMLCAP 50":  f"{BASE_URL}ind_niftysmallcap50list.csv",
    "NIFTY SMLCAP 100": f"{BASE_URL}ind_niftysmallcap100list.csv",
    "NIFTY SMLCAP 250": f"{BASE_URL}ind_niftysmallcap250list.csv",
    # Sectoral
    "NIFTY BANK":         f"{BASE_URL}ind_niftybanklist.csv",
    "NIFTY PRIVATE BANK": f"{BASE_URL}ind_niftypvtbanklist.csv",
    "NIFTY PSU BANK":     f"{BASE_URL}ind_niftypsubanklist.csv",
    "NIFTY AUTO":         f"{BASE_URL}ind_niftyautolist.csv",
    "NIFTY FIN SERVICE":  f"{BASE_URL}ind_niftyfinancelist.csv",
    "NIFTY FMCG":         f"{BASE_URL}ind_niftyfmcglist.csv",
    "NIFTY IT":           f"{BASE_URL}ind_niftyitlist.csv",
    "NIFTY MEDIA":        f"{BASE_URL}ind_niftymedialist.csv",
    "NIFTY METAL":        f"{BASE_URL}ind_niftymetallist.csv",
    "NIFTY ENERGY":       f"{BASE_URL}ind_niftyenergylist.csv",
    "NIFTY INFRA":        f"{BASE_URL}ind_niftyinfrastructurelist.csv",
    "NIFTY PHARMA":       f"{BASE_URL}ind_niftypharmalist.csv",
    "NIFTY REALTY":       f"{BASE_URL}ind_niftyrealtylist.csv",
}

# ── Commodity Futures (Yahoo Finance) ─────────────────────────────────────────
COMMODITY_TICKERS = {
    "GC=F": "Gold",
    "SI=F": "Silver",
    "PL=F": "Platinum",
    "PA=F": "Palladium",
    "HG=F": "Copper",
    "CL=F": "Crude Oil WTI",
    "BZ=F": "Brent Crude",
    "NG=F": "Natural Gas",
    "RB=F": "Gasoline RBOB",
    "HO=F": "Heating Oil",
    "ZC=F": "Corn",
    "ZW=F": "Wheat",
    "ZS=F": "Soybeans",
    "ZM=F": "Soybean Meal",
    "ZL=F": "Soybean Oil",
    "CT=F": "Cotton",
    "KC=F": "Coffee",
    "SB=F": "Sugar",
    "CC=F": "Cocoa",
    "OJ=F": "Orange Juice",
    "LBS=F": "Lumber",
    "LE=F": "Live Cattle",
    "HE=F": "Lean Hogs",
    "GF=F": "Feeder Cattle",
}

# ── Currency Pairs (Yahoo Finance) ────────────────────────────────────────────
CURRENCY_TICKERS = {
    "EURUSD=X": "EUR/USD",
    "GBPUSD=X": "GBP/USD",
    "USDJPY=X": "USD/JPY",
    "USDCHF=X": "USD/CHF",
    "AUDUSD=X": "AUD/USD",
    "USDCAD=X": "USD/CAD",
    "NZDUSD=X": "NZD/USD",
    "USDINR=X": "USD/INR",
    "EURGBP=X": "EUR/GBP",
    "EURJPY=X": "EUR/JPY",
    "GBPJPY=X": "GBP/JPY",
    "AUDJPY=X": "AUD/JPY",
    "EURCHF=X": "EUR/CHF",
    "EURAUD=X": "EUR/AUD",
    "GBPCHF=X": "GBP/CHF",
    "GBPAUD=X": "GBP/AUD",
    "USDSGD=X": "USD/SGD",
    "USDHKD=X": "USD/HKD",
    "USDCNH=X": "USD/CNH",
    "USDZAR=X": "USD/ZAR",
    "USDMXN=X": "USD/MXN",
    "USDTRY=X": "USD/TRY",
    "USDBRL=X": "USD/BRL",
    "USDKRW=X": "USD/KRW",
}

# ── Crypto (Yahoo Finance) ────────────────────────────────────────────────────
CRYPTO_TICKERS = {
    "BTC-USD": "Bitcoin",
    "ETH-USD": "Ethereum",
    "SOL-USD": "Solana",
    "BNB-USD": "Binance Coin",
    "XRP-USD": "Ripple (XRP)",
    "ADA-USD": "Cardano",
    "DOGE-USD": "Dogecoin",
    "TRX-USD": "Tron",
    "LINK-USD": "Chainlink",
    "DOT-USD": "Polkadot",
    "POL-USD": "Polygon (POL)",
    "LTC-USD": "Litecoin",
    "BCH-USD": "Bitcoin Cash",
    "SHIB-USD": "Shiba Inu",
    "AVAX-USD": "Avalanche",
    "NEAR-USD": "Near Protocol",
    "UNI-USD": "Uniswap",
    "XLM-USD": "Stellar",
    "ETC-USD": "Ethereum Classic",
    "XMR-USD": "Monero",
    "ATOM-USD": "Cosmos"
}

# ── Hardcoded Dow Jones 30 components ─────────────────────────────────────────
DOW_JONES_TICKERS = [
    "AMZN", "AMGN", "AAPL", "BA", "CAT", "CSCO", "CVX", "GS", "HD", "HON",
    "IBM", "JNJ", "JPM", "KO", "MCD", "MMM", "MRK", "MSFT", "NKE", "PG",
    "CRM", "SHW", "TRV", "UNH", "V", "VZ", "WMT", "DIS", "DOW", "NVDA"
]

# ── Wikipedia URLs for India Index fallback ───────────────────────────────────
INDIA_INDEX_WIKI_MAP = {
    "NIFTY 50": "https://en.wikipedia.org/wiki/NIFTY_50",
    "NIFTY NEXT 50": "https://en.wikipedia.org/wiki/NIFTY_Next_50",
    "NIFTY 500": "https://en.wikipedia.org/wiki/NIFTY_500",
}


# ══════════════════════════════════════════════════════════════════════════════
# UNIVERSE FETCHING FUNCTIONS
# ══════════════════════════════════════════════════════════════════════════════

def get_etf_universe() -> Tuple[List[str], str]:
    """Return the fixed ETF universe for analysis"""
    return ETF_UNIVERSE, f"✓ Loaded {len(ETF_UNIVERSE)} ETFs"


@st.cache_data(ttl=3600, show_spinner=False)
def get_fno_stock_list() -> Tuple[Optional[List[str]], str]:
    """Fetch F&O stock list from NSE with institutional-grade fallbacks."""
    # ── Primary: NSE JSON API ──
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Referer': 'https://www.nseindia.com/market-data/live-equity-market',
        }
        session = requests.Session()
        session.headers.update(headers)
        session.get("https://www.nseindia.com/", timeout=10)
        session.get("https://www.nseindia.com/market-data/live-equity-market", timeout=10)

        url = "https://www.nseindia.com/api/equity-stockIndices?index=SECURITIES%20IN%20F%26O"
        response = session.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data.get('data'):
                symbols = [item.get('symbol', '') for item in data['data'] if item.get('symbol')]
                symbols = [s for s in symbols if s and not s.startswith('NIFTY')]
                symbols_ns = [s + ".NS" for s in symbols if s.strip()]
                if symbols_ns:
                    return symbols_ns, f"✓ Fetched {len(symbols_ns)} F&O securities from NSE"
    except Exception:
        pass

    # ── Fallback 1: nsepython (if installed) ──
    try:
        from nsepython import nse_get_advances_declines
        stock_data = nse_get_advances_declines()
        if isinstance(stock_data, pd.DataFrame):
            symbols = None
            if 'SYMBOL' in stock_data.columns:
                symbols = stock_data['SYMBOL'].tolist()
            elif 'symbol' in stock_data.columns:
                symbols = stock_data['symbol'].tolist()
            if symbols:
                symbols_ns = [str(s) + ".NS" for s in symbols if s and str(s).strip()]
                return symbols_ns, f"⚠ NSE API failed → Loaded {len(symbols_ns)} F&O securities via nsepython"
    except ImportError:
        pass
    except Exception:
        pass

    # ── Fallback 2: NSE Archives (NIFTY 500 as proxy for depth) ──
    try:
        url = f"{BASE_URL}ind_nifty500list.csv"
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        # TLS verification ON by default; only relax on a genuine SSL failure
        # (see AUDIT_DIRECTIVES.md B2 — this endpoint feeds symbols that later
        # flow into real broker orders via Broker Sync).
        try:
            response = requests.get(url, headers=headers, timeout=10)
        except requests.exceptions.SSLError:
            import warnings as _warnings
            try:
                from logger_config import console
                console.warning("NSE archives TLS verification failed for F&O fallback — retrying unverified")
            except Exception:
                pass
            with _warnings.catch_warnings():
                _warnings.simplefilter("ignore")
                response = requests.get(url, headers=headers, verify=False, timeout=10)
        if response.status_code == 200:
            csv_file = io.StringIO(response.text)
            stock_df = pd.read_csv(csv_file)
            symbol_col = next((c for c in stock_df.columns if c.lower() == 'symbol'), None)
            if symbol_col:
                symbols = stock_df[symbol_col].tolist()
                symbols_ns = [str(s) + ".NS" for s in symbols if s and str(s).strip()]
                return symbols_ns, f"⚠ NSE API failed → Loaded {len(symbols_ns)} stocks from NIFTY 500 Archive"
    except Exception:
        pass

    return None, "All F&O fetch sources failed (NSE API, nsepython, Archives)"


def _parse_wiki_table(url: str, min_count: int = 10) -> Optional[List[str]]:
    """Parse a Wikipedia page and extract NSE symbols from the constituent table"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        tables = pd.read_html(io.StringIO(response.text))
        for tbl in tables:
            # Flexible scanner: search for symbol/ticker/code columns
            cols_lower = [c.lower() for c in tbl.columns]
            sym_col = None
            for candidate in ('symbol', 'ticker', 'nse code', 'code', 'ticker symbol'):
                if candidate in cols_lower:
                    sym_col = tbl.columns[cols_lower.index(candidate)]
                    break
            
            if sym_col:
                symbols = tbl[sym_col].dropna().astype(str).str.strip().tolist()
                symbols = [s for s in symbols if s and len(s) <= 20 and s.lower() != 'nan']
                if len(symbols) >= min_count:
                    return symbols
        return None
    except Exception:
        return None


def _fetch_india_index_from_wikipedia(index: str) -> Tuple[Optional[List[str]], str]:
    """Fallback: Fetch Indian index constituents from Wikipedia when niftyindices.com is unreachable"""
    try:
        # NIFTY 100 is constructed from NIFTY 50 + NIFTY NEXT 50
        if index == "NIFTY 100":
            n50 = _parse_wiki_table(INDIA_INDEX_WIKI_MAP["NIFTY 50"], min_count=40)
            nn50 = _parse_wiki_table(INDIA_INDEX_WIKI_MAP["NIFTY NEXT 50"], min_count=40)
            if n50 and nn50:
                combined = list(dict.fromkeys(n50 + nn50))  # deduplicate preserving order
                symbols_ns = [s + ".NS" for s in combined]
                return symbols_ns, f"⚠ niftyindices.com unavailable → Loaded {len(symbols_ns)} NIFTY 100 constituents from Wikipedia (NIFTY 50 + Next 50)"
            return None, "Wikipedia fallback failed for NIFTY 100"

        # NIFTY 200: NO Wikipedia fallback. The NIFTY 500 Wikipedia
        # constituent table is not ordered by market cap or index weight
        # (typically alphabetical), so slicing its first 200 rows produces a
        # systematically wrong universe (an A-M alphabetical tilt), not an
        # approximation of the real NIFTY 200 — silently fabricating an index
        # is worse than an honest failure (see AUDIT_DIRECTIVES.md B3).
        if index == "NIFTY 200":
            return None, "No reliable Wikipedia fallback for NIFTY 200 (constituent order is not market-cap-ranked) — retry later or select NIFTY 100"

        # Direct Wikipedia lookup for NIFTY 50, NIFTY NEXT 50, NIFTY 500
        wiki_url = INDIA_INDEX_WIKI_MAP.get(index)
        if wiki_url:
            min_expected = {"NIFTY 50": 40, "NIFTY NEXT 50": 40, "NIFTY 500": 400}.get(index, 10)
            symbols = _parse_wiki_table(wiki_url, min_count=min_expected)
            if symbols:
                symbols_ns = [s + ".NS" for s in symbols]
                return symbols_ns, f"⚠ niftyindices.com unavailable → Loaded {len(symbols_ns)} {index} constituents from Wikipedia"
            return None, f"Wikipedia fallback: could not parse {index} table"

        # No Wikipedia fallback available for this index (sectoral/midcap)
        return None, "No Wikipedia fallback available for this index"

    except Exception as e:
        return None, f"Wikipedia fallback error: {e}"


def get_index_stock_list(index: str) -> Tuple[Optional[List[str]], str]:
    """Fetch India index constituents with three-source fallback chain.

    Non-cached wrapper so transient failures aren't pinned for the cache TTL
    — only successful fetches are memoised (mirrors get_us_index_stock_list).
    Previously this whole function was uncached, so it fired 2-4 NSE HTTP
    requests (each with 10-15s timeouts) on EVERY sidebar rerun — including
    the "show current universe info" block that calls resolve_universe on
    every widget interaction, not just on Run Analysis (see
    AUDIT_DIRECTIVES.md B1).
    """
    if index in US_INDEX_LIST:
        return get_us_index_stock_list(index)

    if index == "F&O Stocks":
        return get_fno_stock_list()

    try:
        return _get_india_index_stock_list_cached(index)
    except Exception as e:
        return None, f"Error fetching {index}: {e}"


@st.cache_data(ttl=3600, show_spinner=False)
def _get_india_index_stock_list_cached(index: str) -> Tuple[Optional[List[str]], str]:
    """Inner cached fetcher. Raises on failure so Streamlit does not memoise
    the failure — st.cache_data only caches successful return values."""
    import urllib.parse

    nse_headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'application/json',
        'Accept-Language': 'en-US,en;q=0.9',
        'Referer': 'https://www.nseindia.com/market-data/live-equity-market',
    }

    # ── Source 1: NSE JSON API (most reliable for sectoral indexes) ──
    try:
        api_url = f"https://www.nseindia.com/api/equity-stockIndices?index={urllib.parse.quote(index)}"
        session = requests.Session()
        session.get("https://www.nseindia.com", headers=nse_headers, timeout=10)
        response = session.get(api_url, headers=nse_headers, timeout=15)
        if response.status_code == 200:
            data = response.json()
            if data.get('data'):
                # First item is always the index itself, not a constituent
                symbols = [item['symbol'] for item in data['data'][1:] if item.get('symbol')]
                symbols = [s for s in symbols if s and str(s).strip()]
                if symbols:
                    symbols_ns = [str(s) + ".NS" for s in symbols]
                    return symbols_ns, f"✓ Fetched {len(symbols_ns)} constituents from {index}"
    except Exception:
        pass

    # ── Source 2: NSE Archives CSV (session-warmed) ──
    url = INDEX_URL_MAP.get(index)
    if url:
        try:
            arch_headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate, br',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
                'Cache-Control': 'max-age=0',
            }
            session = requests.Session()
            # TLS verification ON by default (was verify=False unconditionally
            # — disabling certificate validation exposes the machine that
            # later places real orders via Broker Sync to MITM tampering of
            # the fetched constituent list; see AUDIT_DIRECTIVES.md B2). Only
            # relax it as a last-resort retry on a genuine SSL failure, and
            # say so loudly.
            try:
                session.get("https://archives.nseindia.com", headers=arch_headers, timeout=10)
                response = session.get(url, headers=arch_headers, timeout=15)
            except requests.exceptions.SSLError:
                import warnings as _warnings
                try:
                    from logger_config import console
                    console.warning(f"NSE archives TLS verification failed for {index} — retrying unverified")
                except Exception:
                    pass
                with _warnings.catch_warnings():
                    _warnings.simplefilter("ignore")
                    session.get("https://archives.nseindia.com", headers=arch_headers, verify=False, timeout=10)
                    response = session.get(url, headers=arch_headers, verify=False, timeout=15)
            response.raise_for_status()
            stock_df = pd.read_csv(io.StringIO(response.text))
            symbol_col = next((c for c in stock_df.columns if c.strip().lower() in ('symbol', 'ticker', 'code')), None)
            if symbol_col:
                symbols = stock_df[symbol_col].tolist()
                symbols_ns = [str(s) + ".NS" for s in symbols if s and str(s).strip()]
                if symbols_ns:
                    return symbols_ns, f"✓ Fetched {len(symbols_ns)} constituents from {index} (NSE archive)"
        except Exception:
            pass

    # ── Source 3: Wikipedia fallback ──
    wiki_result, wiki_msg = _fetch_india_index_from_wikipedia(index)
    if wiki_result:
        return wiki_result, wiki_msg

    fallback_note = ""
    if wiki_msg is None:
        fallback_note = " (no Wikipedia fallback for this index — retry later)"
    elif wiki_msg:
        fallback_note = f" | {wiki_msg}"

    raise RuntimeError(f"all sources failed for {index}{fallback_note}")


def get_us_index_stock_list(index: str) -> Tuple[Optional[List[str]], str]:
    """Fetch US index constituents. Non-cached wrapper so transient failures
    aren't pinned for the cache TTL — only successful fetches are memoised."""
    try:
        return _get_us_index_stock_list_cached(index)
    except Exception as e:
        return None, f"Error fetching {index}: {e}"


@st.cache_data(ttl=3600, show_spinner=False)
def _get_us_index_stock_list_cached(index: str) -> Tuple[Optional[List[str]], str]:
    """Inner cached fetcher. Raises on failure so Streamlit does not memoise
    the failure — st.cache_data only caches successful return values."""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }

    if index == "S&P 500":
        url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        tables = pd.read_html(io.StringIO(response.text))
        # Scan tables for the constituents table — column name/order on Wikipedia
        # has shifted historically ('Symbol' vs 'Ticker symbol'), so don't trust tables[0]
        for tbl in tables:
            cols = list(tbl.columns)
            sym_col = next((c for c in cols if c.strip().lower() in ('symbol', 'ticker', 'ticker symbol')), None)
            if not sym_col:
                continue
            symbols = tbl[sym_col].dropna().astype(str).str.strip().tolist()
            # Yahoo uses '-' in place of '.' for class-share tickers (BRK.B → BRK-B)
            symbols = [s.replace('.', '-') for s in symbols if s and s.lower() != 'nan']
            if len(symbols) >= 400:
                return symbols, f"✓ Fetched {len(symbols)} S&P 500 constituents from Wikipedia"
        raise RuntimeError("Could not parse S&P 500 table from Wikipedia")

    elif index == "NASDAQ 100":
        url = "https://en.wikipedia.org/wiki/NASDAQ-100"
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        tables = pd.read_html(io.StringIO(response.text))
        for tbl in tables:
            if 'Symbol' in tbl.columns or 'Ticker' in tbl.columns:
                col = 'Symbol' if 'Symbol' in tbl.columns else 'Ticker'
                symbols = tbl[col].dropna().astype(str).tolist()
                symbols = [s.replace('.', '-') for s in symbols if s.strip()]
                if len(symbols) > 50:
                    return symbols, f"✓ Fetched {len(symbols)} NASDAQ 100 constituents from Wikipedia"
        raise RuntimeError("Could not parse NASDAQ 100 table")

    elif index == "DOW JONES":
        return DOW_JONES_TICKERS, f"✓ Loaded {len(DOW_JONES_TICKERS)} Dow Jones components"

    raise ValueError(f"Unknown US index: {index}")


def get_commodity_list() -> Tuple[List[str], str]:
    """Return all commodity futures tickers for analysis"""
    tickers = list(COMMODITY_TICKERS.keys())
    return tickers, f"✓ Loaded {len(tickers)} commodity futures"


def get_currency_list() -> Tuple[List[str], str]:
    """Return all currency pair tickers for analysis"""
    tickers = list(CURRENCY_TICKERS.keys())
    return tickers, f"✓ Loaded {len(tickers)} currency pairs"


def get_crypto_list() -> Tuple[List[str], str]:
    """Return all crypto digital asset tickers for analysis"""
    tickers = list(CRYPTO_TICKERS.keys())
    return tickers, f"✓ Loaded {len(tickers)} digital assets"


# ══════════════════════════════════════════════════════════════════════════════
# MAIN RESOLVE FUNCTION
# ══════════════════════════════════════════════════════════════════════════════

def resolve_universe(
    universe: str,
    index: Optional[str] = None
) -> Tuple[Optional[List[str]], str]:
    """
    Resolve a universe selection to a list of symbols.

    Args:
        universe: One of UNIVERSE_OPTIONS ("ETF Universe", "India Indexes", etc.)
        index: Sub-selection (e.g., "NIFTY 50", "S&P 500") — required for India/US Indexes

    Returns:
        Tuple of (symbol_list, status_message)

    Raises:
        ValueError: If universe is unknown or index is missing when required
    """
    if universe == "ETF Index":
        return get_etf_universe()

    elif universe == "India Indexes":
        if not index:
            raise ValueError("Index selection is required for India Indexes universe")
        return get_index_stock_list(index)

    elif universe == "US Indexes":
        if not index:
            raise ValueError("Index selection is required for US Indexes universe")
        return get_us_index_stock_list(index)

    elif universe == "Commodities":
        return get_commodity_list()

    elif universe == "Currency":
        return get_currency_list()

    elif universe == "Crypto":
        return get_crypto_list()

    elif universe == "Custom List":
        symbols = st.session_state.get("custom_universe_symbols", [])
        status = st.session_state.get("custom_universe_status", "No symbols loaded")
        if not symbols:
            return [], "Error: Please upload a file with a 'Symbol' column first."
        return symbols, status

    else:
        raise ValueError(f"Unknown universe: {universe}. Choose from: {UNIVERSE_OPTIONS}")


def get_index_options(universe: str) -> List[str]:
    """Return the list of index options for a given universe"""
    if universe == "India Indexes":
        return INDIA_INDEX_LIST
    elif universe == "US Indexes":
        return US_INDEX_LIST
    return []


def get_default_index(universe: str) -> Optional[str]:
    """Return the default index for a given universe"""
    if universe == "India Indexes":
        return "NIFTY 50"
    elif universe == "US Indexes":
        return "DOW JONES"
    return None


# ══════════════════════════════════════════════════════════════════════════════
# UI RENDERER
# ══════════════════════════════════════════════════════════════════════════════

def render_universe_selector() -> Tuple[str, Optional[str]]:
    """
    Render the universe selection UI inputs in the sidebar (title rendered externally).

    Returns:
        Tuple of (universe, selected_index) where selected_index may be None
    """
    universe = st.selectbox(
        "Asset Class",
        UNIVERSE_OPTIONS,
        help="Choose the universe of securities to analyze",
        label_visibility="visible"
    )

    if universe == "Currency":
        # Curation is covariance-based and needs only a return series, so FX's
        # missing volume does not disable it. What it does affect is the regime
        # detector, whose oscillator, extremes and acceptance factors are all
        # volume-derived — the regime read on this universe is therefore much
        # thinner than on equities.
        st.warning(
            "Currency pairs report no volume on Yahoo Finance. Portfolio curation is "
            "unaffected (it needs only returns), but the market-regime read relies on "
            "volume-derived factors and will be far less reliable here.",
            icon="⚠️",
        )

    selected_index = None

    # Show index dropdown only for India/US Indexes
    if universe in ("India Indexes", "US Indexes"):
        index_options = get_index_options(universe)
        default_index = get_default_index(universe)
        default_idx = index_options.index(str(default_index)) if default_index in index_options else 0

        selected_index = st.selectbox(
            "Market Index",
            index_options,
            index=default_idx,
            help="Select the specific index for constituent analysis",
            label_visibility="visible"
        )

    # ── Custom List Handler ──────────────────────────────────────────────
    if universe == "Custom List":
        st.markdown('<div class="sidebar-title" style="margin-top:10px;">Custom Config</div>', unsafe_allow_html=True)
        market_type = st.selectbox(
            "Market Type",
            ["India", "Global"],
            index=0,
            help="India adds .NS suffix; Global uses symbols as-is"
        )
        
        uploaded_file = st.file_uploader(
            "Upload Symbol List",
            type=["csv", "xlsx"],
            help="File must have a 'Symbol' or 'symbol' column"
        )

        if uploaded_file:
            try:
                if uploaded_file.name.endswith(".csv"):
                    df = pd.read_csv(uploaded_file)
                else:
                    try:
                        df = pd.read_excel(uploaded_file)
                    except ImportError:
                        st.error("Error: 'openpyxl' is required for Excel files. Please install it.")
                        return universe, "ERROR:NO_OPENPYXL"
                
                # Find symbol column
                col = next((c for c in df.columns if c.strip().lower() == "symbol"), None)
                if col:
                    raw_symbols = df[col].dropna().astype(str).str.strip().tolist()
                    clean_symbols = []
                    for s in raw_symbols:
                        if not s: continue
                        # Apply suffix logic
                        if market_type == "India":
                            if "=F" not in s and not s.endswith(".NS"):
                                s = f"{s.upper()}.NS"
                            else:
                                s = s.upper()
                        else:
                            s = s.upper()
                        clean_symbols.append(s)
                    
                    # Store in session state
                    import hashlib
                    list_str = ",".join(sorted(clean_symbols))
                    list_hash = hashlib.md5((list_str + market_type).encode()).hexdigest()[:8]
                    
                    st.session_state.custom_universe_symbols = clean_symbols
                    st.session_state.custom_universe_status = f"✓ Loaded {len(clean_symbols)} custom symbols ({market_type})"
                    
                    # Return hash as selected_index to ensure cache uniqueness
                    selected_index = list_hash
                    st.success(f"Loaded {len(clean_symbols)} symbols")
                else:
                    st.error("Error: No 'Symbol' column found in file.")
                    st.session_state.custom_universe_symbols = []
                    st.session_state.custom_universe_status = "Error: Column 'Symbol' missing"
            except Exception as e:
                st.error(f"Error parsing file: {e}")
                st.session_state.custom_universe_symbols = []
                st.session_state.custom_universe_status = f"Error: {e}"

    return universe, selected_index


# ══════════════════════════════════════════════════════════════════════════════
# EXPORTS
# ══════════════════════════════════════════════════════════════════════════════

__all__ = [
    # Universe definitions
    'ETF_UNIVERSE',
    'INDIA_INDEX_LIST',
    'US_INDEX_LIST',
    'UNIVERSE_OPTIONS',
    'COMMODITY_TICKERS',
    'CURRENCY_TICKERS',
    'CRYPTO_TICKERS',
    'DOW_JONES_TICKERS',
    'INDEX_URL_MAP',
    # Fetching functions
    'get_etf_universe',
    'get_fno_stock_list',
    'get_index_stock_list',
    'get_us_index_stock_list',
    'get_commodity_list',
    'get_currency_list',
    'get_crypto_list',
    # Resolver
    'resolve_universe',
    'get_index_options',
    'get_default_index',
    # UI
    'render_universe_selector',
]
