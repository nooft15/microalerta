"""
Unidades de medida y conversiones compartidas (backend).

El frontend guarda la preferencia del usuario; el backend la recibe en las
consultas (p. ej. /api/selfcare) para formatear los textos con esa unidad.
"""

TEMP_UNITS = ("C", "F")
WIND_UNITS = ("kmh", "ms", "mph", "kn")
CONC_UNITS = ("pml", "pl")  # part./mL | part./L

WIND_LABELS = {"kmh": "km/h", "ms": "m/s", "mph": "mph", "kn": "kt"}
CONC_LABELS = {"pml": "part./mL", "pl": "part./L"}


def normalize_units(units):
    """Devuelve dict de unidades válidas con valores por defecto."""
    u = units or {}
    return {
        "temp": u.get("temp") if u.get("temp") in TEMP_UNITS else "C",
        "wind": u.get("wind") if u.get("wind") in WIND_UNITS else "kmh",
        "conc": u.get("conc") if u.get("conc") in CONC_UNITS else "pml",
    }


def conv_temp(celsius, unit="C"):
    return float(celsius) if unit == "C" else float(celsius) * 9.0 / 5.0 + 32.0


def conv_wind(kmh, unit="kmh"):
    k = float(kmh)
    if unit == "ms":
        return k / 3.6
    if unit == "mph":
        return k / 1.609344
    if unit == "kn":
        return k / 1.852
    return k


def conv_conc(part_ml, unit="pml"):
    """part./mL -> part./L multiplica por 1000."""
    v = float(part_ml)
    return v * 1000.0 if unit == "pl" else v


def fmt_temp(celsius, unit="C"):
    v = conv_temp(celsius, unit)
    suffix = "°F" if unit == "F" else "°C"
    return f"{v:.1f} {suffix}"


def fmt_wind(kmh, unit="kmh"):
    v = conv_wind(kmh, unit)
    decimals = 1 if v < 10 else 0
    return f"{v:.{decimals}f} {WIND_LABELS.get(unit, 'km/h')}"


def fmt_conc(part_ml, unit="pml"):
    v = conv_conc(part_ml, unit)
    if unit == "pl":
        return f"{v:.0f} {CONC_LABELS['pl']}"
    return f"{v:.3f} {CONC_LABELS['pml']}"