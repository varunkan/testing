from __future__ import annotations

"""
Curated liquid universes for NASDAQ and Toronto Stock Exchange (TSX).

Why curated and not "all tickers":
- NASDAQ lists ~3,000+ and TSX ~1,500+ symbols. Pulling live data for all of them
  every day hits provider rate limits and is mostly illiquid noise.
- These presets focus on large, liquid, tradeable names that actually move on news.

TSX tickers use the yfinance ".TO" suffix (e.g. RY.TO = Royal Bank of Canada).
"""

NASDAQ_100: list[str] = [
    "AAPL", "MSFT", "AMZN", "NVDA", "META", "GOOGL", "GOOG", "TSLA", "AVGO", "PEP",
    "COST", "ADBE", "NFLX", "AMD", "INTC", "CSCO", "TMUS", "COMS", "TXN", "QCOM",
    "AMGN", "HON", "ISRG", "BKNG", "AMAT", "INTU", "ADP", "CME", "CSX", "GILD",
    "MU", "MDLZ", "ADSK", "REGN", "PANW", "KLAC", "SNPS", "ORLY", "VRTX", "LRCX",
    "ADI", "MRVL", "CDNS", "ASML", "ABNB", "MELI", "PYPL", "CRWD", "MAR", "MRNA",
    "CHTR", "MNST", "NXPI", "FTNT", "PCAR", "KDP", "WDAY", "LULU", "ROST", "CTAS",
    "ODFL", "KDP", "DLTR", "CPRT", "MCHP", "AEP", "AZN", "TTWO", "FAST", "BIIB",
    "EXC", "XEL", "SBUX", "EA", "CTSH", "VRSK", "WBD", "DLTR", "CEG", "BKR",
    "FANG", "DXCM", "ZS", "GFS", "ILMN", "DDOG", "IDXX", "ANET", "TEAM", "MRVL",
    "SIRI", "MIDD", "MDB", "NET", "SPLK", "SNPS", "CDW", "GEN", "VXUS", "WST",
    "SOFI", "ARM", "DASH", "SHOP", "O",
]

# S&P/TSX 60 (Canada's largest companies), yfinance uses .TO suffix
TSX_60: list[str] = [
    "RY.TO", "TD.TO", "BNS.TO", "BMO.TO", "CM.TO", "NA.TO",
    "ENB.TO", "TRP.TO", "CNQ.TO", "SU.TO", "IMO.TO", "CVE.TO",
    "CNR.TO", "CP.TO", "L.TO", "MFC.TO", "SLF.TO", "POW.TO",
    "BCE.TO", "T.TO", "RCI-B.TO", "ABX.TO", "AEM.TO", "K.TO",
    "FNV.TO", "NTR.TO", "POT.TO", "WCN.TO", "WCN.TO",
    "SHOP.TO", "CSU.TO", "DOL.TO", "ATD.TO", "MG.TO",
    "CNR.TO", "CP.TO", "FTS.TO", "EMA.TO", "H.TO",
    "BHC.TO", "TSCO.TO", "GIB.A.TO", "OTEX.TO", "SAP.TO",
    "DHI.TO", "TFII.TO", "TIH.TO", "CTC.A.TO",
    "CCL-B.TO", "MRU.TO", "EMP-A.TO", "L.TO",
    "QSR.TO", "WN.TO", "DOL.TO", "RS.TO", "LB.TO",
    "TGZ.TO", "HVL.TO", "ECN.TO", "BAM.TO",
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
