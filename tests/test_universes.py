from wealthsimple_agent.strategy.universes import (
    BROAD,
    NASDAQ_100,
    PRESETS,
    TSX_60,
    list_presets,
    resolve_universe,
)


def test_presets_have_content():
    p = list_presets()
    assert p["nasdaq100"] > 50
    assert p["tsx60"] > 20
    assert p["broad"] > 50


def test_resolve_universe_presets():
    out = resolve_universe(["@nasdaq100", "@tsx60", "BRK.B"])
    assert "AAPL" in out
    assert "RY.TO" in out
    assert "BRK.B" in out
    # No duplicates
    assert len(out) == len(set(out))


def test_resolve_universe_plain_tickers():
    out = resolve_universe(["aapl", "MSFT", "aapl"])
    assert out == ["AAPL", "MSFT"]


def test_tsx_uses_to_suffix():
    assert all(t.endswith(".TO") for t in TSX_60 if t)
    assert "RY.TO" in TSX_60


def test_broad_includes_both_exchanges():
    assert any(t.endswith(".TO") for t in BROAD)
    assert any(not t.endswith(".TO") and t not in ("SPY", "QQQ") for t in BROAD)


def test_no_duplicates_within_presets():
    for name, tickers in PRESETS.items():
        assert len(tickers) == len(set(tickers)), f"{name} contains duplicate tickers"
