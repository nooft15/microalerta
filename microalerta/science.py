"""
Lógica científica: métricas de concentración, índice de exposición a
 supuestos plásticos (estilo índice UV), control analítico (blancos), réplicas,
semáforo y recomendaciones de autocuidado comunitario.
"""
from . import config, units


# ── Índice de exposición a plásticos (escala tipo índice UV, 0–11+) ─────────
INDEX_BANDS = [
    (0.02, "Muy bajo"),
    (0.05, "Muy bajo"),
    (0.10, "Bajo"),
    (0.25, "Bajo"),
    (0.50, "Moderado"),
    (1.00, "Moderado"),
    (2.00, "Alto"),
    (3.00, "Alto"),
    (5.00, "Muy alto"),
    (8.00, "Muy alto"),
    (12.00, "Extremo"),
]
INDEX_MAX = len(INDEX_BANDS)  # último nivel = "11+"

INDEX_COLORS = [
    "#8FD9AE", "#5FBF80", "#2E9E5B", "#9FC63B",
    "#D8D22B", "#F5C518", "#F2A31C", "#F2711C",
    "#E85D2A", "#E23B3B", "#B71C3C", "#8E6BD1",
]


def plastic_index(conc):
    """Índice 0–11+ al estilo del índice UV solar."""
    c = max(0.0, float(conc or 0.0))
    idx = 0
    for i, (upper, _) in enumerate(INDEX_BANDS):
        if c <= upper:
            idx = i
            break
    else:
        idx = INDEX_MAX
    category = INDEX_BANDS[min(idx, len(INDEX_BANDS) - 1)][1]
    return {
        "index": idx,
        "index_label": f"{idx}+" if idx >= INDEX_MAX else str(idx),
        "label": category,
        "color": INDEX_COLORS[idx],
        "conc_p_ml": round(c, 3),
        "max_scale": INDEX_MAX,
        "scale_note": ("Escala tipo índice UV: 0-2 bajo · 3-5 moderado · "
                       "6-7 alto · 8-10 muy alto · 11+ extremo"),
    }


def compute_metrics(n_observed, volume_ml=None, area_cm2=None, exposure_hours=None):
    """Devuelve métricas clave a partir del conteo en la placa Petri.

    - conc_p_ml : partículas por mililitro de agua destilada congelada.
    - depo_p_cm2: partículas por cm² de área observada.
    - depo_p_m2day: tasa de deposición por m² y día (valora el tiempo expuesto).
    """
    n = max(0, int(n_observed or 0))
    vol = float(volume_ml or config.DEFAULT_VOLUME_ML)
    area = float(area_cm2 or config.DEFAULT_AREA_CM2)
    exp_h = float(exposure_hours) if exposure_hours else (config.EXPOSURE_MINUTES_DEFAULT / 60.0)

    area_m2 = area / 10000.0
    depo_m2 = (n / area_m2) if area_m2 else 0.0
    exp_days = exp_h / 24.0
    depo_day = (depo_m2 / exp_days) if exp_days > 0 else 0.0

    return {
        "n_observed": n,
        "volume_ml": round(vol, 2),
        "area_cm2": round(area, 2),
        "exposure_hours": round(exp_h, 2),
        "conc_p_ml": round(n / vol, 3) if vol else 0.0,
        "depo_p_cm2": round(n / area, 2) if area else 0.0,
        "depo_p_m2": round(depo_m2, 2),
        "depo_p_m2_day": round(depo_day, 2),
    }


def semaphore(conc):
    """Semáforo de calidad del aire por concentración de partículas (p/mL)."""
    c = float(conc or 0.0)
    if c < config.THRESHOLD_GREEN:
        return {"level": 0, "label": "Saludable", "color": "#2E9E5B",
                "advice": "Sin precaución especial. Aire limpio.", "range": f"< {config.THRESHOLD_GREEN}"}
    if c < config.THRESHOLD_YELLOW:
        return {"level": 1, "label": "Moderada", "color": "#F5C518",
                "advice": "Personas sensibles: use mascarilla al aire libre.", "range": f"{config.THRESHOLD_GREEN}–{config.THRESHOLD_YELLOW}"}
    if c < config.THRESHOLD_ORANGE:
        return {"level": 2, "label": "Alta", "color": "#F2711C",
                "advice": "Evite actividades al aire libre; use mascarilla.", "range": f"{config.THRESHOLD_YELLOW}–{config.THRESHOLD_ORANGE}"}
    return {"level": 3, "label": "Muy alta", "color": "#E23B3B",
            "advice": "Use mascarilla N95, permanezca en interiores.", "range": f"≥ {config.THRESHOLD_ORANGE}"}


# ── Escala completa del semáforo (colores, rangos y recomendaciones) ────────
# Fuente única de verdad para la leyenda informativa (icono "i") de la app:
# cada nivel trae su color de plástico, rango de concentración (part./mL),
# la recomendación principal y una lista de acciones de autocuidado.
SEMAPHORE_LEVELS = [
    {"level": 0, "label": "Saludable", "color": "#2E9E5B", "range": "< 0.5",
     "advice": "Sin precaución especial. Aire limpio.",
     "recommendations": [
         "Aire limpio: sin mascarilla ni restricciones para la población general.",
         "Buen momento para la actividad al aire libre, la escuela y el deporte.",
         "Mantén las placas de muestreo activas para seguir construyendo la serie.",
     ]},
    {"level": 1, "label": "Moderada", "color": "#F5C518", "range": "0.5 – 2.0",
     "advice": "Personas sensibles: use mascarilla al aire libre.",
     "recommendations": [
         "Personas sensibles (asma, alergias, adultos mayores, niñez): use mascarilla al aire libre.",
         "Ventila tu casa a primera hora, cuando el aire suele estar más limpio.",
         "Limita el ejercicio intenso y prolongado en exteriores.",
     ]},
    {"level": 2, "label": "Alta", "color": "#F2711C", "range": "2.0 – 5.0",
     "advice": "Evite actividades al aire libre; use mascarilla.",
     "recommendations": [
         "Use mascarilla (ideal N95/KN95) al salir a la calle.",
         "Evite la actividad física al aire libre.",
         "Mantén ventanas cerradas en horas de viento y limpia superficies con paño húmedo.",
     ]},
    {"level": 3, "label": "Muy alta", "color": "#E23B3B", "range": "≥ 5.0",
     "advice": "Use mascarilla N95, permanezca en interiores.",
     "recommendations": [
         "Permanece en interiores con puertas y ventanas cerradas.",
         "Si debes salir, use mascarilla N95/KN95 bien ajustada.",
         "Hidrátate y acude al médico si presentas tos, ardor de ojos o dificultad para respirar.",
     ]},
]


def semaphore_scale():
    """Devuelve la escala completa del semáforo (para leyendas e información).

    Cada elemento incluye: level, label, color, range (part./mL), advice y
    recommendations (lista de acciones de autocuidado para ese nivel).
    """
    return SEMAPHORE_LEVELS


def blank_qc(blank_n):
    """Control de calidad del blanco analítico (plato de control cerrado)."""
    n = int(blank_n or 0)
    if n > config.BLANK_TOLERANCE:
        return {
            "ok": False,
            "level": "warn",
            "label": f"Blanco con {n} partículas",
            "detail": "El plato de control superó la tolerancia de partículas; "
                      "sospeche de contaminación cruzada en el procedimiento.",
        }
    if blank_n is not None:
        return {"ok": True, "level": "ok", "label": f"Blanco válido ({n} partículas)",
                "detail": "El control cerrado confirma ausencia de contaminación cruzada."}
    return None


def replicates_qc(samples):
    """Revisa un grupo de réplicas: conteo mínimo y existencia de blanco.

    `samples`: lista de dicts con clave `sample_type` y `n_observed`.
    Devuelve lista de avisos (advertencias) según el protocolo de control cerrado.
    """
    notes = []
    n_total = len(samples)
    n_blanco = sum(1 for s in samples if s.get("sample_type") == "blanco")
    n_muestra = sum(1 for s in samples if s.get("sample_type") in ("muestra", "replica"))

    if n_total < config.MIN_REPLICATES:
        notes.append(f"Grupo con solo {n_total} platos; el protocolo recomienda ≥ {config.MIN_REPLICATES} réplicas.")
    if n_blanco == 0:
        notes.append("No se registró plato de control (blanco analítico) en este grupo.")
    elif n_blanco > 0:
        blanco_n = next((s.get("n_observed") for s in samples if s.get("sample_type") == "blanco"), None)
        qc = blank_qc(blanco_n)
        if qc and not qc["ok"]:
            notes.append(qc["detail"])
    if n_muestra < 1:
        notes.append("No hay muestra de campo (solo blancos) en este grupo.")
    return notes


def self_care(conc=None, hum=None, wind_kmh=None, temp=None, units_pref=None):
    """Recomendaciones de autocuidado (concentración + clima).

    `units_pref` permite formatear viento/temperatura con las unidades
    preferidas del usuario; los umbrales se evalúan siempre en SI.
    """
    u = units.normalize_units(units_pref)
    s = semaphore(conc)
    pidx = plastic_index(conc)

    out = [{
        "title": f"Nivel {s['label']} - indice {pidx['index_label']} ({pidx['label']})",
        "detail": s["advice"],
        "priority": s["level"],
    }]

    # Ventilación del hogar según el nivel
    if s["level"] == 1:
        out.append({"title": "Ventilación recomendada",
                    "detail": "Ventila tu casa a primera hora, cuando el aire suele estar más limpio "
                              "y antes de que suba el viento.",
                    "priority": 1})
    elif s["level"] >= 2:
        out.append({"title": "Ventanas cerradas",
                    "detail": "Mantén ventanas cerradas durante los picos de viento o si ves polvo "
                              "levantarse; limpia superficies con paño húmedo.",
                    "priority": max(s["level"], 2)})

    # Modificadores ambientales del Desierto de Atacama
    if wind_kmh is not None and wind_kmh >= 40:
        out.append({"title": "Viento intenso / re-suspensión",
                    "detail": f"Ráfagas altas (> {units.fmt_wind(40, u['wind'])}) pueden re-suspender polvo "
                              "y partículas desde el suelo desértico. Cierre ventanas al salir y "
                              "priorice mascarilla.",
                    "priority": max(s["level"], 1)})
    if hum is not None and hum < 20:
        out.append({"title": "Aire muy seco",
                    "detail": "Humedad < 20 % favorece la dispersión de partículas y el malestar en "
                              "vías respiratorias. Hidrátese a menudo.",
                    "priority": max(s["level"], 0)})
    if temp is not None and temp >= 30:
        out.append({"title": "Calor extremo",
                    "detail": f"Temperatura sobre {units.fmt_temp(30, u['temp'])}: reduzca la actividad "
                              "física al aire libre y refúgiese a la sombra en las horas de mayor sol.",
                    "priority": max(s["level"], 0)})
    if temp is not None and temp <= 5:
        out.append({"title": "Frío",
                    "detail": "Temperaturas bajas pueden agravar molestias respiratorias; abrige vías "
                              "aéreas y evite cambios bruscos.",
                    "priority": max(s["level"], 0)})

    out.sort(key=lambda r: r["priority"], reverse=True)
    return out