"""
Datos meteorológicos en cascada con consenso de modelos.

Orden de fuentes para TIEMPO REAL:
  1) Open-Meteo forecast «current» (coordenadas exactas, se actualiza ~15 min)
  2) met.no / Yr Locationforecast (respaldo en vivo, sin clave)
     · Si ambas responden se PROMEDIA (consenso): menos sesgo por modelo.
  3) METAR DGAC (aviationweather.gov, estación SCAT Copiapó) último recurso.

"""
import datetime as dt
import math

import requests

OPEN_METEO_CURRENT_URL = "https://api.open-meteo.com/v1/forecast"
OPEN_METEO_ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
METNO_URL = "https://api.met.no/weatherapi/locationforecast/2.0/compact"
METAR_URL = "https://aviationweather.gov/api/data/metar"

# met.no exige un User-Agent identificable; lo usamos en todas las llamadas.
USER_AGENT = {
    "User-Agent": "MicroAlerta/1.0 (monitoreo comunitario escolar; Chile)"
}
DEFAULT_TIMEOUT = 6

CURRENT_FIELDS = ("temperature_2m,relative_humidity_2m,wind_speed_10m,"
                  "wind_direction_10m,wind_gusts_10m,pressure_msl,precipitation")
HOURLY_FIELDS = CURRENT_FIELDS


# ── helpers ────────────────────────────────────────────────────────────────
def _avg(vals):
    vals = [float(v) for v in vals if v is not None]
    return round(sum(vals) / len(vals), 1) if vals else None


def _max(vals):
    vals = [float(v) for v in vals if v is not None]
    return round(max(vals), 1) if vals else None


def _sum(vals):
    """Total acumulado (p. ej. precipitación mm en la ventana)."""
    vals = [float(v) for v in vals if v is not None]
    return round(sum(vals), 1) if vals else None


def _circular_mean_deg(pairs):
    """Promedio circular ponderado de direcciones en grados."""
    xs = ys = total = 0.0
    for deg, weight in pairs:
        if deg is None:
            continue
        rad = math.radians(float(deg))
        xs += math.cos(rad) * float(weight)
        ys += math.sin(rad) * float(weight)
        total += float(weight)
    if total == 0:
        return None
    return round(math.degrees(math.atan2(ys / total, xs / total)) % 360, 0)


def _valid(d):
    """Una lectura es válida si trae temperatura."""
    return bool(d) and d.get("temp") is not None


def _rh_from_dew(temp_c, dewp_c):
    if temp_c is None or dewp_c is None:
        return None
    e_t = 6.112 * pow(10, (7.5 * temp_c) / (237.3 + temp_c))
    e_d = 6.112 * pow(10, (7.5 * dewp_c) / (237.3 + dewp_c))
    return round(min(100.0, max(0.0, 100.0 * e_d / e_t)), 1)


def _to_date(value):
    if value is None:
        return None
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    try:
        return dt.date.fromisoformat(str(value)[:10])
    except ValueError:
        return None

# ── proveedores ────────────────────────────────────────────────────────────
class OpenMeteoCurrent:
    """Tiempo real de Open-Meteo (modelo actualizado cada ~15 min)."""
    label = "open-meteo"

    def current(self, lat, lon):
        r = requests.get(OPEN_METEO_CURRENT_URL, params={
            "latitude": lat, "longitude": lon, "current": CURRENT_FIELDS,
            "timezone": "auto",
        }, timeout=DEFAULT_TIMEOUT, headers=USER_AGENT)
        r.raise_for_status()
        c = (r.json() or {}).get("current") or {}
        return {
            "source": self.label,
            "temp": c.get("temperature_2m"),
            "hum": c.get("relative_humidity_2m"),
            "wind": c.get("wind_speed_10m"),
            "wind_max": c.get("wind_gusts_10m") or c.get("wind_speed_10m"),
            "wind_dir": c.get("wind_direction_10m"),
            "pressure": c.get("pressure_msl"),
            "precip": c.get("precipitation"),
            "obs_time": c.get("time"),
        }


class MetNo:
    """Yr.no / met.no Locationforecast (respaldo en vivo, sin clave API)."""
    label = "met.no"

    def current(self, lat, lon):
        r = requests.get(METNO_URL, params={
            "lat": round(float(lat), 4), "lon": round(float(lon), 4),
        }, timeout=DEFAULT_TIMEOUT, headers=USER_AGENT)
        r.raise_for_status()
        data = r.json() or {}
        series = ((data.get("properties") or {}).get("timeseries") or [])
        if not series:
            return None
        first = series[0]
        det = ((first.get("data") or {}).get("instant") or {}).get("details") or {}
        wind_kmh = round(det.get("wind_speed", 0) * 3.6, 1)  # m/s -> km/h
        nxt = ((first.get("data") or {}).get("next_1_hours") or {})
        gust = (((nxt.get("details") or {}).get("wind_speed_max")))
        precip = ((nxt.get("details") or {}).get("precipitation_amount"))
        return {
            "source": self.label,
            "temp": det.get("air_temperature"),
            "hum": det.get("relative_humidity"),
            "wind": wind_kmh,
            "wind_max": round(gust * 3.6, 1) if gust else wind_kmh,
            "wind_dir": det.get("wind_from_direction"),
            "pressure": det.get("air_pressure_at_sea_level"),
            "precip": precip,
            "obs_time": first.get("time"),
        }


class OpenMeteoArchive:
    """Archivo histórico de Open-Meteo para ventanas pasadas."""
    label = "open-meteo-archivo"

    def window(self, lat, lon, start_date, end_date):
        r = requests.get(OPEN_METEO_ARCHIVE_URL, params={
            "latitude": lat, "longitude": lon,
            "start_date": start_date, "end_date": end_date,
            "hourly": HOURLY_FIELDS, "timezone": "auto",
        }, timeout=DEFAULT_TIMEOUT, headers=USER_AGENT)
        r.raise_for_status()
        h = (r.json() or {}).get("hourly") or {}
        return {
            "source": self.label,
            "temp": _avg(h.get("temperature_2m")),
            "hum": _avg(h.get("relative_humidity_2m")),
            "wind": _avg(h.get("wind_speed_10m")),
            "wind_max": _max(h.get("wind_gusts_10m") or h.get("wind_speed_10m")),
            "wind_dir": _avg(h.get("wind_direction_10m")),
            "pressure": _avg(h.get("pressure_msl")),
            "precip": _sum(h.get("precipitation")),
        }


class MetarDGAC:
    """METAR de la DGAC (vía aviationweather.gov; estación SCAT Copiapó)."""
    label = "DGAC/METAR"

    def current(self, station="SCAT"):
        r = requests.get(METAR_URL, params={"ids": station, "format": "json"},
                         timeout=DEFAULT_TIMEOUT, headers=USER_AGENT)
        r.raise_for_status()
        rows = r.json() or []
        if not rows:
            return None
        m = rows[0]
        w = (m.get("wspd") or 0) * 1.852  # kt -> km/h
        return {
            "source": self.label,
            "temp": m.get("temp"),
            "hum": _rh_from_dew(m.get("temp"), m.get("dewp")),
            "wind": round(w, 1),
            "wind_max": round(w, 1),
            "wind_dir": m.get("wdir"),
            "pressure": m.get("altim"),
            "obs_time": m.get("reportTime"),
            "raw": (m.get("raw") or "")[:120],
        }

class WeatherService:
    """Cascada de fuentes + consenso para tiempo real."""

    def _live_consensus(self, lat, lon):
        readings = []
        for provider in (OpenMeteoCurrent(), MetNo()):
            try:
                d = provider.current(lat, lon)
                if _valid(d):
                    readings.append(d)
            except Exception:
                pass

        if not readings:
            return None
        if len(readings) == 1:
            return readings[0]

        # Consenso: promediar modelos reduce el sesgo individual.
        dir_pairs = [(r.get("wind_dir"), 1) for r in readings]
        return {
            "source": " + ".join(r["source"] for r in readings),
            "temp": _avg([r.get("temp") for r in readings]),
            "hum": _avg([r.get("hum") for r in readings]),
            "wind": _avg([r.get("wind") for r in readings]),
            "wind_max": _max([r.get("wind_max") for r in readings]),
            "wind_dir": _circular_mean_deg(dir_pairs),
            "pressure": _avg([r.get("pressure") for r in readings]),
            "precip": _avg([r.get("precip") for r in readings]),
            "obs_time": max((r.get("obs_time") or "" for r in readings), default=None),
            "consensus": True,
        }

    def get_current(self, lat, lon):
        """Tiempo real: consenso Open-Meteo + met.no; METAR como último recurso."""
        d = self._live_consensus(lat, lon)
        if _valid(d):
            return d
        try:
            m = MetarDGAC().current()
            if m:
                return m
        except Exception:
            pass
        return d or None

    def report_weather(self, lat, lon, start_dt=None, end_dt=None):
        """Clima para una ventana: histórico si es pasado; en vivo si incluye hoy."""
        today = dt.date.today()
        end_d = _to_date(end_dt)
        start_d = _to_date(start_dt)

        if end_d is None or end_d >= today - dt.timedelta(days=1):
            # Ventana actual/reciente: medición en vivo (lo más fresco posible).
            return self.get_current(lat, lon)

        # Ventana histórica: archivo de Open-Meteo primero.
        if start_d is not None and end_d is not None:
            try:
                arch = OpenMeteoArchive().window(
                    lat, lon, start_d.isoformat(), end_d.isoformat())
                if _valid(arch):
                    return arch
            except Exception:
                pass
        return self.get_current(lat, lon)


