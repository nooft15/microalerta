"""
Excel de datos de MicroAlerta (.xlsx) con gráficas listas para usar.

El archivo se regenera automáticamente cada vez que se registra, aprueba,
edita o elimina una muestra, así Excel siempre refleja los datos actuales.
Incluye hojas de datos y gráficos (líneas, barras y torta) que se actualizan
con los valores del archivo.
"""
import os
from datetime import datetime

from openpyxl import Workbook
from openpyxl.chart import BarChart, LineChart, PieChart, Reference
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from . import config, science

SHEET_MUESTRAS = "Muestras"
SHEET_SERIE = "Serie temporal"
SHEET_PUNTOS = "Resumen por punto"
SHEET_MORFO = "Morfologías"
SHEET_AYUDA = "Cómo usar"

_HEAD_FILL = PatternFill("solid", fgColor="1E88E5")
_HEAD_FONT = Font(bold=True, color="FFFFFF", size=10)
_TITLE_FONT = Font(bold=True, size=13, color="1E88E5")

# (encabezado, ancho de columna)
COLUMNS = [
    ("Reporte", 34), ("Fecha registro", 17), ("Hora aprox.", 11), ("Estado", 11),
    ("Punto", 22), ("Comuna", 14), ("Latitud", 11), ("Longitud", 11),
    ("Tipo de plato", 15), ("Grupo réplicas", 13), ("N° placa", 10), ("Medio", 22),
    ("Volumen (mL)", 11), ("Área (cm²)", 10),
    ("Exposición inicio", 17), ("Exposición fin", 17), ("Horas exposición", 11),
    ("Partículas (N)", 12), ("Fibras", 9), ("Fragmentos", 11), ("Films", 8),
    ("Minerales", 10), ("Inciertas", 10),
    ("Concentración (p/mL)", 15), ("Deposición (p/cm²)", 15), ("Deposición (p/m²·d)", 16),
    ("Índice", 8), ("Categoría índice", 15), ("Semáforo", 12),
    ("Tinción", 16), ("Aumento", 9),
    ("Temp (°C)", 9), ("Humedad (%)", 11), ("Viento (km/h)", 12), ("Ráfaga (km/h)", 12),
    ("Dir. viento (°)", 12), ("Presión (hPa)", 12), ("Precipitación (mm)", 13),
    ("Fuente clima", 16),
    ("Reportado por", 20), ("Institución", 22), ("Comentario admin", 26), ("Imagen", 22),
]

_QUERY = """
SELECT o.id AS obs_id, o.created_at AS registrado, o.obs_time, o.status, o.stain,
       o.microscope_mag, o.n_observed, o.morph_fiber, o.morph_fragment, o.morph_film,
       o.morph_mineral, o.n_uncertain, o.admin_comment, o.image_path,
       s.dish_id, s.sample_type, s.replicate_group, s.volume_ml, s.area_cm2, s.medium,
       s.exposure_start, s.exposure_end, s.exposure_hours,
       l.name AS punto, l.city AS comuna, l.lat, l.lon,
       u.name AS usuario, u.school AS institucion,
       w.source AS wx_fuente, w.temp_avg, w.hum_avg, w.wind_avg, w.wind_max,
       w.wind_dir_avg, w.pressure_avg, w.precip_mm
FROM observations o
JOIN samples s   ON o.sample_id  = s.id
JOIN locations l ON s.location_id = l.id
JOIN users u     ON o.user_id    = u.id
LEFT JOIN weather_snapshots w ON w.id = (
    SELECT id FROM weather_snapshots WHERE sample_id = s.id
    ORDER BY created_at DESC LIMIT 1)
ORDER BY o.created_at ASC
"""


def fetch_rows(conn):
    """Todas las observaciones con su muestra, punto y clima asociado."""
    return conn.execute(_QUERY).fetchall()


def _dt(value):
    """ISO -> datetime local (Excel no admite zonas horarias)."""
    if not value:
        return None
    try:
        d = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if d.tzinfo is not None:
        d = d.astimezone().replace(tzinfo=None)
    return d


def _num(value):
    return None if value is None else float(value)


def dataset_rows(conn):
    """Filas del dataset plano (mismo contenido de la hoja «Muestras»).
    Devuelve (filas_valores, encabezados) para reutilizar en CSV."""
    headers = [name for name, _w in COLUMNS]
    return [[_x(v) for v in _values(r)] for r in fetch_rows(conn)], headers


def _x(value):
    if isinstance(value, datetime):
        return value.replace(tzinfo=None) if value.tzinfo else value
    return value


def _values(r):
    """Fila de datos con las métricas y el índice ya calculados."""
    m = science.compute_metrics(r["n_observed"], r["volume_ml"], r["area_cm2"],
                                r["exposure_hours"])
    idx = science.plastic_index(m["conc_p_ml"])
    sem = science.semaphore(m["conc_p_ml"])
    return [
        r["obs_id"], _dt(r["registrado"]), r["obs_time"] or "", r["status"],
        r["punto"], r["comuna"], r["lat"], r["lon"],
        r["sample_type"], r["replicate_group"] or "", r["dish_id"] or "", r["medium"] or "",
        _num(r["volume_ml"]), _num(r["area_cm2"]),
        _dt(r["exposure_start"]), _dt(r["exposure_end"]), m["exposure_hours"],
        r["n_observed"], r["morph_fiber"], r["morph_fragment"], r["morph_film"],
        r["morph_mineral"], r["n_uncertain"],
        m["conc_p_ml"], m["depo_p_cm2"], m["depo_p_m2_day"],
        idx["index"], idx["label"], sem["label"],
        r["stain"], r["microscope_mag"],
        _num(r["temp_avg"]), _num(r["hum_avg"]), _num(r["wind_avg"]),
        _num(r["wind_max"]), _num(r["wind_dir_avg"]), _num(r["pressure_avg"]),
        _num(r["precip_mm"]), r["wx_fuente"] or "",
        r["usuario"], r["institucion"] or "", r["admin_comment"] or "",
        r["image_path"] or "",
    ]


def _header(ws, headers, widths=None):
    ws.append(list(headers))
    for i, cell in enumerate(ws[1], start=1):
        cell.fill = _HEAD_FILL
        cell.font = _HEAD_FONT
        cell.alignment = Alignment(vertical="center", wrap_text=True)
        if widths:
            ws.column_dimensions[get_column_letter(i)].width = widths[i - 1]
    ws.freeze_panes = "A2"
    ws.row_dimensions[1].height = 28


def _sheet_muestras(ws, rows):
    _header(ws, [c[0] for c in COLUMNS], [c[1] for c in COLUMNS])
    for r in rows:
        ws.append(_values(r))
    # Formatos de fecha y números
    for row in ws.iter_rows(min_row=2):
        for col in (2, 15, 16):
            row[col - 1].number_format = "DD/MM/YYYY HH:MM"
        for col in (13, 14, 17, 24, 25, 26, 32, 33, 34, 35, 36, 37, 38):
            row[col - 1].number_format = "0.00"
    if len(rows):
        ws.auto_filter.ref = f"A1:{get_column_letter(len(COLUMNS))}{len(rows) + 1}"
    return ws


def _group_by_date(rows):
    """Serie temporal (solo aprobados): n, concentración promedio y máxima."""
    acc = {}
    for r in rows:
        if r["status"] != "aprobado":
            continue
        d = _dt(r["registrado"])
        if d is None:
            continue
        key = d.date()
        m = science.compute_metrics(r["n_observed"], r["volume_ml"], r["area_cm2"],
                                    r["exposure_hours"])
        idx = science.plastic_index(m["conc_p_ml"])
        a = acc.setdefault(key, {"n": 0, "sum": 0.0, "max": 0.0, "isum": 0.0})
        a["n"] += 1
        a["sum"] += m["conc_p_ml"]
        a["max"] = max(a["max"], m["conc_p_ml"])
        a["isum"] += idx["index"]
    out = []
    for key in sorted(acc):
        a = acc[key]
        out.append([key, a["n"], round(a["sum"] / a["n"], 3), round(a["max"], 3),
                    round(a["isum"] / a["n"], 1)])
    return out


def _sheet_serie(ws, rows):
    _header(ws, ["Fecha", "Muestras aprobadas", "Concentración promedio (p/mL)",
                 "Concentración máxima (p/mL)", "Índice promedio"], [13, 18, 26, 26, 16])
    data = _group_by_date(rows)
    for row in data:
        ws.append(row)
    for row in ws.iter_rows(min_row=2):
        row[0].number_format = "DD/MM/YYYY"
    if not data:
        return ws
    n = len(data) + 1
    line = LineChart()
    line.title = "Evolución de la concentración (p/mL)"
    line.y_axis.title = "p/mL"
    line.x_axis.title = "Fecha"
    line.height, line.width = 9, 20
    line.add_data(Reference(ws, min_col=3, max_col=4, min_row=1, max_row=n),
                  titles_from_data=True)
    line.set_categories(Reference(ws, min_col=1, min_row=2, max_row=n))
    ws.add_chart(line, "G2")

    bar = BarChart()
    bar.title = "Muestras aprobadas por fecha"
    bar.y_axis.title = "N° de muestras"
    bar.height, bar.width = 9, 20
    bar.add_data(Reference(ws, min_col=2, min_row=1, max_row=n), titles_from_data=True)
    bar.set_categories(Reference(ws, min_col=1, min_row=2, max_row=n))
    ws.add_chart(bar, "G22")
    return ws


def _group_by_point(rows):
    """Resumen por punto de muestreo (solo aprobados)."""
    acc = {}
    for r in rows:
        if r["status"] != "aprobado":
            continue
        key = r["punto"]
        m = science.compute_metrics(r["n_observed"], r["volume_ml"], r["area_cm2"],
                                    r["exposure_hours"])
        idx = science.plastic_index(m["conc_p_ml"])
        a = acc.setdefault(key, {"comuna": r["comuna"], "n": 0, "sum": 0.0,
                                 "imax": 0, "isum": 0.0, "blancos": 0, "replicas": 0})
        a["n"] += 1
        a["sum"] += m["conc_p_ml"]
        a["isum"] += idx["index"]
        a["imax"] = max(a["imax"], idx["index"])
        if r["sample_type"] == "blanco":
            a["blancos"] += 1
        elif r["sample_type"] == "replica":
            a["replicas"] += 1
    out = []
    for key in sorted(acc, key=lambda k: -acc[k]["n"]):
        a = acc[key]
        out.append([key, a["comuna"], a["n"], round(a["sum"] / a["n"], 3),
                    round(a["isum"] / a["n"], 1), a["imax"], a["blancos"], a["replicas"]])
    return out


def _sheet_puntos(ws, rows):
    _header(ws, ["Punto", "Comuna", "Muestras aprobadas", "Concentración promedio (p/mL)",
                 "Índice promedio", "Índice máx.", "Blancos", "Réplicas"],
            [24, 14, 18, 26, 16, 12, 10, 10])
    data = _group_by_point(rows)
    for row in data:
        ws.append(row)
    if not data:
        return ws
    n = len(data) + 1
    bar = BarChart()
    bar.type = "col"
    bar.title = "Concentración promedio por punto (p/mL)"
    bar.y_axis.title = "p/mL"
    bar.height, bar.width = 10, 22
    bar.add_data(Reference(ws, min_col=4, min_row=1, max_row=n), titles_from_data=True)
    bar.set_categories(Reference(ws, min_col=1, min_row=2, max_row=n))
    ws.add_chart(bar, "J2")

    bar2 = BarChart()
    bar2.type = "col"
    bar2.title = "Muestras aprobadas por punto"
    bar2.y_axis.title = "N° de muestras"
    bar2.height, bar2.width = 10, 22
    bar2.add_data(Reference(ws, min_col=3, min_row=1, max_row=n), titles_from_data=True)
    bar2.set_categories(Reference(ws, min_col=1, min_row=2, max_row=n))
    ws.add_chart(bar2, "J23")
    return ws


def _sheet_morfo(ws, rows):
    _header(ws, ["Morfología", "Partículas (aprobadas)", "% del total"], [20, 22, 14])
    labels = [("Fibras", "morph_fiber"), ("Fragmentos", "morph_fragment"),
              ("Films (láminas)", "morph_film"), ("Minerales / polvo", "morph_mineral")]
    totals = [(name, sum(int(r[key] or 0) for r in rows if r["status"] == "aprobado"))
              for name, key in labels]
    gran = sum(t[1] for t in totals) or 1
    for name, value in totals:
        ws.append([name, value, round(100.0 * value / gran, 1)])
    for row in ws.iter_rows(min_row=2):
        row[2].number_format = "0.0"
    n = len(totals) + 1
    pie = PieChart()
    pie.title = "Distribución por morfología"
    pie.height, pie.width = 10, 14
    pie.add_data(Reference(ws, min_col=2, min_row=1, max_row=n), titles_from_data=True)
    pie.set_categories(Reference(ws, min_col=1, min_row=2, max_row=n))
    ws.add_chart(pie, "E2")
    return ws


def _sheet_ayuda(ws):
    ws.column_dimensions["A"].width = 4
    ws.column_dimensions["B"].width = 110
    ws["B1"] = "Cómo usar este Excel"
    ws["B1"].font = _TITLE_FONT
    lineas = [
        "",
        "• El archivo se actualiza SOLO: cada vez que alguien registra, aprueba, edita o",
        "  elimina una muestra en la app, este Excel se regenera con los datos del momento.",
        "  Si lo tienes abierto en Excel, ciérralo y vuelve a abrirlo para ver los cambios.",
        "",
        "• Hoja «Muestras»: una fila por muestra registrada, con métricas calculadas",
        "  (concentración, deposición, índice, semáforo) y el clima de la ventana de exposición.",
        "  Usa los filtros de la fila 1 para ver solo un punto, una fecha o un estado.",
        "",
        "• Hoja «Serie temporal»: concentración promedio y máxima por fecha, con dos gráficas",
        "  listas (líneas y barras). Añade más fechas y las gráficas se actualizan solas.",
        "",
        "• Hoja «Resumen por punto»: comparación entre puntos de muestreo (barras).",
        "",
        "• Hoja «Morfologías»: reparto de fibras, fragmentos, films y minerales (torta).",
        "",
        "• Para tus propias gráficas: selecciona cualquier columna numérica de «Muestras» y usa",
        "  Insertar ▸ Gráfico. Los encabezados ya están listos como títulos de serie.",
        "",
        "• Datos abiertos: puedes compartir este archivo con el colegio o la comunidad.",
    ]
    for i, texto in enumerate(lineas, start=2):
        ws[f"B{i}"] = texto
    return ws


def build_workbook(conn):
    """Construye el libro completo con datos y gráficas."""
    rows = fetch_rows(conn)
    wb = Workbook()
    ws = wb.active
    ws.title = SHEET_MUESTRAS
    _sheet_muestras(ws, rows)
    _sheet_serie(wb.create_sheet(SHEET_SERIE), rows)
    _sheet_puntos(wb.create_sheet(SHEET_PUNTOS), rows)
    _sheet_morfo(wb.create_sheet(SHEET_MORFO), rows)
    _sheet_ayuda(wb.create_sheet(SHEET_AYUDA))
    return wb, len(rows)



def open_in_excel(path):
    """Abre el archivo en la app Excel del equipo (Windows/macOS/Linux).

    No bloquea: devuelve True si se lanzó la apertura, False si no se pudo
    (p. ej. servidor sin entorno gráfico). Nunca lanza excepciones.
    """
    import subprocess
    import sys
    try:
        if not path or not os.path.exists(path):
            return False
        if sys.platform.startswith("win"):
            os.startfile(os.path.abspath(path))  # noqa: S606 - ruta local propia
            return True
        opener = "open" if sys.platform == "darwin" else "xdg-open"
        subprocess.Popen([opener, os.path.abspath(path)],
                         stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)
        return True
    except Exception:
        return False


def sync(app):
    """Regenera el Excel en disco. Silencioso: nunca rompe el flujo de la app."""
    path = app.config.get("EXCEL_PATH") or config.EXCEL_PATH
    try:
        from . import db
        os.makedirs(os.path.dirname(path), exist_ok=True)
        conn = db.get_db(app)
        try:
            wb, n = build_workbook(conn)
        finally:
            conn.close()
        wb.save(path)
        return path
    except Exception:
        return None