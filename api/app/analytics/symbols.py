"""Turning broker-specific symbol names into common ones, so the same market is grouped
together however a broker spells it. The database keeps the symbol exactly as sent."""

# Only names confirmed from real data are listed. Add more here as other brokers are used.
_ALIASES = {
    "T100": "NAS100",  # IFX: Nasdaq 100
    "WS30": "US30",  # IFX: Wall Street 30 (Dow Jones)
    "XBTUSD": "BTCUSD",  # XBT is the currency code for bitcoin
}


def canonical_symbol(raw: str) -> str:
    """``T100.ifx_m`` -> ``NAS100``, ``XAUUSD.ifx`` -> ``XAUUSD``, ``EURUSD`` -> ``EURUSD``.

    Brokers add a suffix after a dot for the account type; everything from the first dot on
    is dropped, then a short alias table maps broker names to the common ones.
    """
    base = raw.strip().upper().split(".", 1)[0]
    return _ALIASES.get(base, base)
