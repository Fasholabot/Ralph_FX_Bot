def calculate_position_size(equity: float, risk_pct: float, entry: float, sl: float) -> dict:
    risk_amount = equity * (risk_pct / 100)
    sl_distance = abs(entry - sl)
    if sl_distance == 0:
        return {"error": "Stop loss cannot equal entry price"}

    # Generic pip-based estimate (1 standard lot = 100,000 units; pip value ~= $10 on most USD-quoted pairs)
    # Determine pip size: JPY pairs have 0.01 pip size, everything else 0.0001
    pip_size = 0.01 if entry > 50 else 0.0001
    pips_risk = sl_distance / pip_size
    value_per_lot_per_pip = 10.0  # approximation for a standard lot on USD-quoted pairs

    if pips_risk == 0:
        return {"error": "Invalid stop distance"}

    lots = risk_amount / (pips_risk * value_per_lot_per_pip)

    return {
        "risk_amount": round(risk_amount, 2),
        "lots": round(lots, 2),
        "sl_pips": round(pips_risk, 1),
        "note": (
            "Estimate only based on a standard lot. Actual results depend on "
            "your broker's contract specs, spread, and slippage."
        ),
    }