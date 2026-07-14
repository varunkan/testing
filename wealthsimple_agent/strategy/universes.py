from __future__ import annotations

"""
Curated liquid universes for NASDAQ and Toronto Stock Exchange (TSX).

Why curated and not "all tickers":
- NASDAQ lists ~3,000+ and TSX ~1,500+ symbols. Pulling live data for all of them
  every day hits provider rate limits and is mostly illiquid noise.
- These presets focus on large, liquid, tradeable names that actually move on news.
- Users can still pass their own tickers (e.g. ["AAPL", "TSLA", "SHOP.TO"]) to override.

TSX tickers use the yfinance ".TO" suffix (e.g. RY.TO = Royal Bank of Canada).
Tickers are current as of mid-2024; index constituents change over time and may be
updated by the user through the `universe` configuration.
"""

# NASDAQ-100 / large liquid NASDAQ-listed names (no duplicates)
NASDAQ_100: list[str] = [
    "AAPL", "ABNB", "ADBE", "ADI", "ADP", "ADSK", "AEP", "AMAT", "AMD", "AMGN",
    "AMZN", "ANSS", "APP", "ARM", "ASML", "AVGO", "AZN", "BIIB", "BKNG", "BKR",
    "CCEP", "CDNS", "CDW", "CEG", "CHTR", "CMCSA", "COST", "CPRT", "CRWD", "CSCO",
    "CSGP", "CSX", "CTAS", "CTSH", "DASH", "DDOG", "DXCM", "EA", "EXC", "FAST",
    "FISV", "FTNT", "GEHC", "GFS", "GILD", "GOOG", "GOOGL", "HON", "IDXX", "ILMN",
    "INTC", "INTU", "ISRG", "KDP", "KLAC", "LIN", "LRCX", "LULU", "MAR", "MCHP",
    "MDB", "MDLZ", "MELI", "META", "MIDD", "MNST", "MRNA", "MRVL", "MSFT", "MU",
    "NFLX", "NVDA", "NXPI", "ODFL", "ORLY", "PANW", "PAYX", "PCAR", "PEP", "PYPL",
    "QCOM", "REGN", "ROP", "ROST", "SBUX", "SIRI", "SNPS", "SOFI", "SPLK", "TEAM",
    "TMUS", "TSLA", "TTWO", "TXN", "VRSK", "VRSN", "VRTX", "WBD", "WDC", "WDAY",
    "WST", "XEL", "ZS",
]

# S&P/TSX 60 (Canada's largest companies), yfinance uses .TO suffix
# List cleaned to remove duplicates and non-TSX symbols.
TSX_60: list[str] = [
    "RY.TO", "TD.TO", "BNS.TO", "BMO.TO", "CM.TO", "NA.TO",
    "ENB.TO", "TRP.TO", "CNQ.TO", "SU.TO", "IMO.TO", "CVE.TO", "TOU.TO", "PPL.TO",
    "CNR.TO", "CP.TO", "WCN.TO", "WSP.TO", "TFII.TO", "TIH.TO", "CCL-B.TO",
    "MFC.TO", "SLF.TO", "POW.TO", "GWO.TO", "IAG.TO", "IFC.TO",
    "BCE.TO", "T.TO", "RCI-B.TO", "QBR-B.TO",
    "ABX.TO", "AEM.TO", "K.TO", "FNV.TO", "WPM.TO", "NTR.TO", "LUN.TO",
    "SHOP.TO", "CSU.TO", "DOL.TO", "ATD.TO", "MG.TO", "GIB.A.TO", "OTEX.TO", "KXS.TO", "DOO.TO",
    "FTS.TO", "EMA.TO", "H.TO", "CU.TO",
    "BAM-A.TO", "BIP-UN.TO",
    "L.TO", "MRU.TO", "EMP-A.TO", "CTC.A.TO", "BBD-B.TO",
    "QSR.TO", "WN.TO", "SAP.TO",
    "REI-UN.TO", "HR-UN.TO",
    "ECN.TO",
]

# Broad liquid universe spanning both exchanges (used by default "broad" preset)
BROAD: list[str] = NASDAQ_100[:60] + TSX_60[:30] + [
    "SPY", "QQQ", "IWM", "GLD", "TLT", "XLF", "XLE", "XLK", "XLI", "XLV",
    "EWC",  # Canada ETF
    "VOO", "VEA", "VWO", "AGG", "HYG", "LQD",
]

PRESETS: dict[str, list[str]] = {
    "nasdaq100": NASDAQ_100,
    "tsx60": TSX_60,
    "broad": BROAD,
    "tsx": TSX_60,
    "nasdaq": NASDAQ_100,
}


def resolve_universe(universe: list[str]) -> list[str]:
    """
    Resolve a universe list that may contain preset names prefixed with '@'.
    Example: ["@nasdaq100", "@tsx60", "BRK.B"] -> expanded tickers + BRK.B
    Duplicates are removed and tickers are upper-cased.
    """
    out: list[str] = []
    seen: set[str] = set()
    for item in universe:
        s = item.strip()
        if not s:
            continue
        if s.startswith("@"):
            preset = s[1:].strip().lower()
            for t in PRESETS.get(preset, []):
                tt = t.strip().upper()
                if tt and tt not in seen:
                    seen.add(tt)
                    out.append(tt)
        else:
            tt = s.upper()
            if tt not in seen:
                seen.add(tt)
                out.append(tt)
    return out


def list_presets() -> dict[str, int]:
    return {name: len(tickers) for name, tickers in PRESETS.items()}
