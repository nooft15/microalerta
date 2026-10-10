"""
Datos de referencia: usuarios demo, puntos de muestreo en Atacama y reportes
de ejemplo extraídos del proyecto previo (air13) para poblar la vista comunitaria.
"""
import json, uuid
from datetime import datetime, timedelta, timezone

from . import config, db


def _now(days_ago=0):
    return (datetime.now() + timedelta(days=-days_ago)).replace(microsecond=0).isoformat()


LOCATIONS = [
    # ── Copiapó ────────────────────────────────────────────────────────────
    {"id": "cop-centro", "name": "Centro de Copiapó", "city": "Copiapó",
     "lat": -27.3700, "lon": -70.3300, "kind": "comunidad", "color": "#1E88E5"},
    {"id": "cop-liceo", "name": "Liceo de Copiapó (techo)", "city": "Copiapó",
     "lat": -27.3666, "lon": -70.3352, "kind": "escuela", "color": "#2E9E5B"},
    {"id": "cop-sala-abierta", "name": "Lab. abierto – Liceo", "city": "Copiapó",
     "lat": -27.3668, "lon": -70.3346, "kind": "escuela", "color": "#4FA8F5"},
    {"id": "cop-sala-cerrada", "name": "Lab. cerrado (blanco) – Liceo", "city": "Copiapó",
     "lat": -27.3670, "lon": -70.3341, "kind": "referencia", "color": "#8E6BD1"},
    # ── Puntos reales del proyecto (colegio y laboratorio) ────────────────
    {"id": "cop-colegio", "name": "Colegio", "city": "Copiapó",
     "lat": -27.388574, "lon": -70.311530, "kind": "escuela", "color": "#4FA8F5"},
    {"id": "cop-laboratorio", "name": "Laboratorio", "city": "Copiapó",
     "lat": -27.388328, "lon": -70.311942, "kind": "escuela", "color": "#5FBF80"},
    # ── Comunas de Atacama ─────────────────────────────────────────────────
    {"id": "tierra-amarilla", "name": "Tierra Amarilla", "city": "Tierra Amarilla",
     "lat": -27.4800, "lon": -70.2600, "kind": "comunidad", "color": "#F2711C"},
    {"id": "caldera", "name": "Caldera", "city": "Caldera",
     "lat": -27.0700, "lon": -70.8200, "kind": "comunidad", "color": "#E23B3B"},
    {"id": "bahia-inglesa", "name": "Bahía Inglesa", "city": "Caldera",
     "lat": -27.1000, "lon": -70.8700, "kind": "comunidad", "color": "#8E6BD1"},
    {"id": "chanaral", "name": "Chañaral", "city": "Chañaral",
     "lat": -26.3400, "lon": -70.6200, "kind": "comunidad", "color": "#F5C518"},
    {"id": "dalmagro", "name": "Diego de Almagro", "city": "Diego de Almagro",
     "lat": -26.3700, "lon": -70.0500, "kind": "comunidad", "color": "#5FBF80"},
    {"id": "vallenar", "name": "Vallenar", "city": "Vallenar",
     "lat": -28.5700, "lon": -70.7600, "kind": "comunidad", "color": "#4FA8F5"},
    {"id": "huasco", "name": "Huasco", "city": "Huasco",
     "lat": -28.4600, "lon": -71.2200, "kind": "comunidad", "color": "#D8D22B"},
    {"id": "scat", "name": "Aeropuerto Desierto de Atacama (SCAT)", "city": "Copiapó",
     "lat": -27.2600, "lon": -70.7800, "kind": "referencia", "color": "#94A0A8"},
]

USERS = [
    {"username": "admin", "role": "admin", "name": "Administración MicroAlerta"},
    {"username": "colegio", "role": "colegio", "name": "Prof. Cecilia Rojas", "school": "Liceo de Copiapó"},
    {"username": "ciudadano", "role": "ciudadano", "name": "Yasna Alfaro", "school": "Junta vecinal El Chimbo"},
]

def _demo_reports():
    """Reportes demostrativos alineados al protocolo del proyecto previo (air13)."""
    return [
        {"dish": "PL-001", "loc": "cop-liceo", "type": "muestra", "group": "RG-COP-01",
         "stain": "lugol", "n": 63, "fiber": 27, "frag": 16, "film": 13, "mineral": 7, "unc": 2,
         "mag": 400, "status": "aprobado", "user": "colegio", "days": 2},
        {"dish": "PL-001R1", "loc": "cop-liceo", "type": "replica", "group": "RG-COP-01",
         "stain": "lugol", "n": 58, "fiber": 25, "frag": 15, "film": 12, "mineral": 6, "unc": 1,
         "mag": 400, "status": "aprobado", "user": "colegio", "days": 2},
        {"dish": "PL-BLK", "loc": "cop-sala-cerrada", "type": "blanco", "group": "RG-COP-01",
         "stain": "ninguna", "n": 0, "fiber": 0, "frag": 0, "film": 0, "mineral": 0, "unc": 0,
         "mag": 400, "status": "aprobado", "user": "colegio", "days": 2},
        {"dish": "PL-002", "loc": "cop-centro", "type": "muestra", "group": "RG-COP-02",
         "stain": "azul_metileno", "n": 72, "fiber": 24, "frag": 31, "film": 12, "mineral": 5, "unc": 3,
         "mag": 200, "status": "pendiente", "user": "ciudadano", "days": 1},
        {"dish": "PL-003", "loc": "cop-sala-abierta", "type": "muestra", "group": "RG-COP-03",
         "stain": "lugol", "n": 26, "fiber": 8, "frag": 9, "film": 5, "mineral": 4, "unc": 1,
         "mag": 400, "status": "aprobado", "user": "colegio", "days": 1},
        {"dish": "PL-004", "loc": "caldera", "type": "replica", "group": "RG-COP-04",
         "stain": "azul_metileno", "n": 19, "fiber": 5, "frag": 8, "film": 3, "mineral": 3, "unc": 2,
         "mag": 100, "status": "pendiente", "user": "ciudadano", "days": 0},
    ]


def seed_db(app, force=False):
    """Siembra idempotente. Con `force` restablece reportes demostrativos."""
    from datetime import datetime
    conn = db.get_db(app)
    try:
        for u in USERS:
            db._seed_user(conn, u["username"], u["role"], u["name"], u.get("school"))

        # Puntos base del proyecto: se agregan si faltan (no borra los del usuario)
        for loc in LOCATIONS:
            conn.execute(
                "INSERT OR IGNORE INTO locations"
                " (id,name,city,region,lat,lon,kind,active,color,created_at)"
                " VALUES (?,?,?,?,?,?,?,1,?,?)",
                (loc["id"], loc["name"], loc["city"], "Atacama", loc["lat"], loc["lon"],
                 loc["kind"], loc["color"], _now()))

        cur = conn.execute("SELECT value FROM configs WHERE key='allowed_stains'")
        if cur.fetchone() is None:
            conn.execute("INSERT INTO configs (key,value) VALUES ('allowed_stains',?)",
                         (json.dumps(config.STAIN_DEFAULTS, ensure_ascii=False),))

        # Confirmar altas de usuarios, puntos y configuración (independiente de
        # si hay o no reportes demostrativos por sembrar).
        conn.commit()

        n_obs = conn.execute("SELECT COUNT(*) AS c FROM observations").fetchone()["c"]
        if n_obs == 0 or force:
            if force:
                conn.execute("DELETE FROM weather_snapshots")
                conn.execute("DELETE FROM observations")
                conn.execute("DELETE FROM samples")
            ids_users = dict((row["username"], row["id"]) for row in
                             conn.execute("SELECT id,username FROM users"))
            loc_ids = set(r["id"] for r in conn.execute("SELECT id FROM locations"))
            now = datetime.now(timezone.utc).replace(microsecond=0)
            for rep in _demo_reports():
                loc = rep["loc"] if rep["loc"] in loc_ids else "cop-liceo"
                sid = str(uuid.uuid4())
                end = now + timedelta(days=-rep["days"])
                start = end + timedelta(hours=-24)
                conn.execute(
                    "INSERT INTO samples (id,location_id,user_id,dish_id,volume_ml,area_cm2,medium,"
                    "sample_type,replicate_group,exposure_start,exposure_end,exposure_hours,notes,created_at)"
                    " VALUES (?,?,?,?,?,?,?,?,?,?,?,24,?,?)",
                    (sid, loc, ids_users[rep["user"]], rep["dish"], config.DEFAULT_VOLUME_ML,
                     config.DEFAULT_AREA_CM2, config.DEFAULT_MEDIUM, rep["type"],
                     rep["group"], start.isoformat(), end.isoformat(),
                     "Reporte de demostración", _now(rep["days"])))
                conn.execute(
                    "INSERT INTO observations (id,sample_id,user_id,stain,image_path,microscope_mag,"
                    "n_observed,morph_fiber,morph_fragment,morph_film,morph_mineral,n_uncertain,"
                    "status,admin_comment,reviewed_by,reviewed_at,created_at)"
                    " VALUES (?,?,?,?,NULL,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (str(uuid.uuid4()), sid, ids_users[rep["user"]], rep["stain"], rep["mag"],
                     rep["n"], rep["fiber"], rep["frag"], rep["film"], rep["mineral"], rep["unc"],
                     rep["status"], "Revisión automática de siembra" if rep["status"] == "aprobado" else None,
                     ids_users["admin"] if rep["status"] == "aprobado" else None,
                     _now() if rep["status"] == "aprobado" else None, _now(rep["days"])))
            conn.commit()
    finally:
        conn.close()