"""
Capa de persistencia (SQLite por defecto, PostgreSQL opcional vía DATABASE_URL).

Modelos de datos (tablas):
  User (users) ................. cuentas: admin / colegio / ciudadano
  Point (locations) ............ puntos de muestreo (colegio, laboratorio, comunidad)
  Sample (samples) ............. placa Petri: ventana de exposición, medio, réplicas
  Observation (observations) ... conteo + tinción + foto + revisión admin
  Settings (configs) ........... tinciones permitidas, video tutorial, ajustes app
  WeatherHistory ................ snapshots climáticos por muestra (ver abajo)
  UserPrefs (user_prefs) ....... unidades preferidas por cuenta

Historial meteorológico: tabla weather_snapshots (alias WeatherHistory) con
promedios de la ventana de exposición de cada muestra
(temp/humedad/viento/ráfaga/dirección/presión/precipitación + fuente).
Se guarda al crear el reporte y se RE-asocia al aprobar (revisión admin),
para correlacionar deposición con meteorología.

Motores:
- SQLite (stdlib): cero dependencias, persistente en microalerta.db. WAL activado.
- PostgreSQL (psycopg, ver requirements [postgres]): se usa cuando
  DATABASE_URL=postgresql://... está definido (despliegue multiproceso).
"""
import sqlite3
import uuid

try:
    import psycopg as _pg  # type: ignore
    from psycopg.rows import dict_row as _pg_dict_row  # type: ignore
except Exception:  # pragma: no cover - psycopg es opcional
    _pg = None
    _pg_dict_row = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            TEXT PRIMARY KEY,
    username      TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL CHECK(role IN ('admin','colegio','ciudadano')),
    name          TEXT,
    school        TEXT,
    created_at    TEXT
);

CREATE TABLE IF NOT EXISTS locations (
    id         TEXT PRIMARY KEY,
    name       TEXT NOT NULL,
    city       TEXT,
    region     TEXT DEFAULT 'Atacama',
    lat        REAL NOT NULL,
    lon        REAL NOT NULL,
    kind       TEXT DEFAULT 'comunidad' CHECK(kind IN ('escuela','comunidad','referencia')),
    active     INTEGER DEFAULT 1,
    color      TEXT DEFAULT '#1E88E5',
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS samples (
    id              TEXT PRIMARY KEY,
    location_id     TEXT NOT NULL REFERENCES locations(id),
    user_id         TEXT NOT NULL REFERENCES users(id),
    dish_id         TEXT,
    volume_ml       REAL DEFAULT 40.0,
    area_cm2        REAL DEFAULT 4.0,
    medium          TEXT DEFAULT 'Agua destilada congelada',
    sample_type     TEXT NOT NULL CHECK(sample_type IN ('muestra','blanco','replica')),
    replicate_group TEXT,
    exposure_start  TEXT,
    exposure_end    TEXT,
    exposure_hours  REAL,
    notes           TEXT,
    created_at      TEXT
);

CREATE TABLE IF NOT EXISTS observations (
    id            TEXT PRIMARY KEY,
    sample_id     TEXT NOT NULL REFERENCES samples(id),
    user_id       TEXT NOT NULL REFERENCES users(id),
    stain         TEXT NOT NULL,
    image_path    TEXT,
    microscope_mag INTEGER,
    n_observed    INTEGER DEFAULT 0,
    morph_fiber   INTEGER DEFAULT 0,
    morph_fragment INTEGER DEFAULT 0,
    morph_film    INTEGER DEFAULT 0,
    morph_mineral INTEGER DEFAULT 0,
    n_uncertain   INTEGER DEFAULT 0,
    obs_time      TEXT,
    status        TEXT DEFAULT 'pendiente' CHECK(status IN ('pendiente','aprobado','rechazado')),
    admin_comment TEXT,
    reviewed_by   TEXT,
    reviewed_at   TEXT,
    created_at    TEXT
);

CREATE TABLE IF NOT EXISTS weather_snapshots (
    id          TEXT PRIMARY KEY,
    sample_id   TEXT,
    location_id TEXT,
    source      TEXT,
    ts_start    TEXT,
    ts_end      TEXT,
    temp_avg    REAL,
    hum_avg     REAL,
    wind_avg    REAL,
    wind_max    REAL,
    wind_dir_avg REAL,
    pressure_avg REAL,
    raw         TEXT,
    created_at  TEXT
);

CREATE TABLE IF NOT EXISTS configs (
    key   TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS user_prefs (
    user_id TEXT NOT NULL REFERENCES users(id),
    key     TEXT NOT NULL,
    value   TEXT,
    PRIMARY KEY (user_id, key)
);
"""


def engine():
    """Motor activo: 'postgres' si hay DATABASE_URL, si no 'sqlite'."""
    from . import config
    url = (getattr(config, "DATABASE_URL", "") or "").strip()
    if url and _pg is not None:
        return "postgres"
    return "sqlite"


def _pg_conn(url):
    conn = _pg.connect(url, row_factory=_pg_dict_row)
    conn.autocommit = False
    return conn


def get_db(app=None):
    """Abre conexión (SQLite con Row + WAL, o PostgreSQL con filas dict)."""
    if app:
        url = (app.config.get("DATABASE_URL") or "").strip() if app.config.get("DATABASE_URL") else ""
        db_path = app.config["DATABASE"]
    else:
        from . import config
        url = (getattr(config, "DATABASE_URL", "") or "").strip()
        db_path = config.DATABASE
    if url and _pg is not None:
        return _pg_conn(url)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode = WAL")
    except Exception:
        pass
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _migrate(db):
    """Migraciones ligeras para bases creadas con versiones anteriores."""
    if engine() == "postgres":
        # PostgreSQL: columnas idempotentes (IF NOT EXISTS donde aplica).
        try:
            db.execute("ALTER TABLE weather_snapshots ADD COLUMN IF NOT EXISTS precip_mm DOUBLE PRECISION")
        except Exception:
            pass
        try:
            db.execute("ALTER TABLE observations ADD COLUMN IF NOT EXISTS obs_time TEXT")
        except Exception:
            pass
        return
    cols = [r[1] for r in db.execute("PRAGMA table_info(weather_snapshots)").fetchall()]
    if "precip_mm" not in cols:
        db.execute("ALTER TABLE weather_snapshots ADD COLUMN precip_mm REAL")
    ocols = [r[1] for r in db.execute("PRAGMA table_info(observations)").fetchall()]
    if "obs_time" not in ocols:
        db.execute("ALTER TABLE observations ADD COLUMN obs_time TEXT")


def init_db(app):
    from contextlib import closing
    with closing(get_db(app)) as db:
        if engine() == "postgres":
            _pg_schema(db)
        else:
            db.executescript(SCHEMA)
        _migrate(db)
        db.commit()


def _pg_schema(db):
    """Esquema PostgreSQL (equivalente al SQLite, con UUIDs y SERIAL)."""
    db.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY, username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL CHECK(role IN ('admin','colegio','ciudadano')),
        name TEXT, school TEXT, created_at TIMESTAMPTZ);""")
    db.execute("""
    CREATE TABLE IF NOT EXISTS locations (
        id TEXT PRIMARY KEY, name TEXT NOT NULL, city TEXT,
        region TEXT DEFAULT 'Atacama', lat DOUBLE PRECISION NOT NULL,
        lon DOUBLE PRECISION NOT NULL,
        kind TEXT DEFAULT 'comunidad'
          CHECK(kind IN ('escuela','comunidad','referencia')),
        active INTEGER DEFAULT 1, color TEXT DEFAULT '#1E88E5',
        created_at TIMESTAMPTZ);""")
    db.execute("""
    CREATE TABLE IF NOT EXISTS samples (
        id TEXT PRIMARY KEY, location_id TEXT NOT NULL REFERENCES locations(id),
        user_id TEXT NOT NULL REFERENCES users(id), dish_id TEXT,
        volume_ml DOUBLE PRECISION DEFAULT 40.0, area_cm2 DOUBLE PRECISION DEFAULT 4.0,
        medium TEXT DEFAULT 'Agua destilada congelada',
        sample_type TEXT NOT NULL CHECK(sample_type IN ('muestra','blanco','replica')),
        replicate_group TEXT, exposure_start TIMESTAMPTZ, exposure_end TIMESTAMPTZ,
        exposure_hours DOUBLE PRECISION, notes TEXT, created_at TIMESTAMPTZ);""")
    db.execute("""
    CREATE TABLE IF NOT EXISTS observations (
        id TEXT PRIMARY KEY, sample_id TEXT NOT NULL REFERENCES samples(id),
        user_id TEXT NOT NULL REFERENCES users(id), stain TEXT NOT NULL,
        image_path TEXT, microscope_mag INTEGER, n_observed INTEGER DEFAULT 0,
        morph_fiber INTEGER DEFAULT 0, morph_fragment INTEGER DEFAULT 0,
        morph_film INTEGER DEFAULT 0, morph_mineral INTEGER DEFAULT 0,
        n_uncertain INTEGER DEFAULT 0, obs_time TEXT,
        status TEXT DEFAULT 'pendiente'
          CHECK(status IN ('pendiente','aprobado','rechazado')),
        admin_comment TEXT, reviewed_by TEXT, reviewed_at TIMESTAMPTZ,
        created_at TIMESTAMPTZ);""")
    db.execute("""
    CREATE TABLE IF NOT EXISTS weather_snapshots (
        id TEXT PRIMARY KEY, sample_id TEXT, location_id TEXT, source TEXT,
        ts_start TIMESTAMPTZ, ts_end TIMESTAMPTZ,
        temp_avg DOUBLE PRECISION, hum_avg DOUBLE PRECISION,
        wind_avg DOUBLE PRECISION, wind_max DOUBLE PRECISION,
        wind_dir_avg DOUBLE PRECISION, pressure_avg DOUBLE PRECISION,
        raw TEXT, created_at TIMESTAMPTZ);""")
    db.execute("CREATE TABLE IF NOT EXISTS configs (key TEXT PRIMARY KEY, value TEXT);")
    db.execute("""
    CREATE TABLE IF NOT EXISTS user_prefs (
        user_id TEXT NOT NULL REFERENCES users(id), key TEXT NOT NULL,
        value TEXT, PRIMARY KEY (user_id, key));""")


def _seed_user(db, username, role, name, school=None, password="demo123"):
    from werkzeug.security import generate_password_hash
    import uuid, datetime
    cur = db.execute("SELECT id FROM users WHERE username=?", (username,))
    if cur.fetchone():
        return
    db.execute(
        "INSERT INTO users (id, username, password_hash, role, name, school, created_at)"
        " VALUES (?,?,?,?,?,?,?)",
        (str(uuid.uuid4()), username, generate_password_hash(password),
         role, name, school, _now()),
    )


def _now():
    import datetime
    return datetime.datetime.now(datetime.timezone.utc).isoformat()