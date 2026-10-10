"""
API REST de MicroAlerta: sesión, ubicaciones, tinción limitada (admin),
reportes de muestreo ciudadano, cola de revisión admin, clima y comunidad.
"""
import datetime as dt
import io
import json
import os
import uuid
from functools import wraps

from flask import Blueprint, current_app, g, jsonify, request, send_file, session

from . import config, db, excel, science, weather

bp = Blueprint("api", __name__, url_prefix="/api")

_REPORT_JOIN = """
FROM observations o
JOIN samples s      ON o.sample_id    = s.id
JOIN locations l    ON s.location_id  = l.id
JOIN users u        ON o.user_id      = u.id
"""


def _uid():
    return str(uuid.uuid4())


def _now():
    return dt.datetime.now().replace(microsecond=0).isoformat()


def _parse_dt(s):
    if not s:
        return None
    if isinstance(s, dt.datetime):
        return s
    t = str(s).replace(" ", "T")
    if t.endswith("Z"):
        t = t[:-1] + "+00:00"
    try:
        return dt.datetime.fromisoformat(t)
    except ValueError:
        return None


def _user_dict(row):
    return {"id": row["id"], "username": row["username"], "role": row["role"],
            "name": row["name"], "school": row["school"]}

def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        conn = db.get_db(current_app)
        try:
            row = conn.execute("SELECT * FROM users WHERE id=?",
                               (session.get("uid"),)).fetchone()
        finally:
            conn.close()
        if not row:
            return jsonify({"error": "login_required"}), 401
        g.user = _user_dict(row)
        return f(*args, **kwargs)
    return wrapper


def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        conn = db.get_db(current_app)
        try:
            row = conn.execute("SELECT * FROM users WHERE id=?",
                               (session.get("uid"),)).fetchone()
        finally:
            conn.close()
        if not row:
            return jsonify({"error": "login_required"}), 401
        if row["role"] != "admin":
            return jsonify({"error": "solo_administrador"}), 403
        g.user = _user_dict(row)
        return f(*args, **kwargs)
    return wrapper


# ── Sesión ─────────────────────────────────────────────────────────────────
@bp.get("/health")
def health():
    return jsonify({"ok": True, "app": "MicroAlerta"})


@bp.get("/session")
def get_session():
    conn = db.get_db(current_app)
    try:
        row = conn.execute("SELECT * FROM users WHERE id=?",
                           (session.get("uid"),)).fetchone()
    finally:
        conn.close()
    return jsonify({"user": _user_dict(row) if row else None})


@bp.post("/login")
def login():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    conn = db.get_db(current_app)
    try:
        row = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
    finally:
        conn.close()
    from werkzeug.security import check_password_hash
    if not row or not check_password_hash(row["password_hash"], password):
        return jsonify({"error": "credenciales inválidas"}), 401
    session["uid"] = row["id"]
    return jsonify({"user": _user_dict(row)})


@bp.post("/logout")
def logout():
    session.pop("uid", None)
    return jsonify({"ok": True})


# ── Tinciones: variables limitadas que el formulario ofrece ────────────────
def _stains(conn):
    row = conn.execute("SELECT value FROM configs WHERE key='allowed_stains'").fetchone()
    try:
        items = json.loads(row["value"]) if row else config.STAIN_DEFAULTS
    except Exception:
        items = config.STAIN_DEFAULTS
    return [i for i in items if i.get("enabled")]


@bp.get("/stains")
def list_stains():
    conn = db.get_db(current_app)
    try:
        if request.args.get("all") == "1":
            row = conn.execute("SELECT value FROM configs WHERE key='allowed_stains'").fetchone()
            try:
                items = json.loads(row["value"]) if row else config.STAIN_DEFAULTS
            except Exception:
                items = config.STAIN_DEFAULTS
            return jsonify({"stains": items})
        return jsonify({"stains": _stains(conn)})
    finally:
        conn.close()


@bp.put("/stains")
@admin_required
def update_stains():
    data = request.get_json(silent=True) or {}
    allowed = set(data.get("allowed", []))
    items = []
    for opt in config.STAIN_DEFAULTS:
        opt = dict(opt)
        opt["enabled"] = opt["value"] in allowed
        items.append(opt)
    conn = db.get_db(current_app)
    try:
        conn.execute("UPDATE configs SET value=? WHERE key='allowed_stains'",
                     (json.dumps(items, ensure_ascii=False),))
        conn.commit()
        return jsonify({"stains": [i for i in items if i.get("enabled")]})
    finally:
        conn.close()


# ── Ubicaciones ────────────────────────────────────────────────────────────
@bp.get("/locations")
def list_locations():
    conn = db.get_db(current_app)
    try:
        include = request.args.get("include_inactive") == "1"
        sql = "SELECT * FROM locations"
        if not include:
            sql += " WHERE active=1"
        sql += " ORDER BY city, name"
        rows = conn.execute(sql).fetchall()
        return jsonify({"locations": [dict(r) for r in rows]})
    finally:
        conn.close()


@bp.post("/locations")
@admin_required
def create_location():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    lat = data.get("lat")
    lon = data.get("lon")
    if not name or lat is None or lon is None:
        return jsonify({"error": "faltan campos (name, lat, lon)"}), 400
    loc_id = _uid()
    conn = db.get_db(current_app)
    try:
        conn.execute(
            "INSERT INTO locations (id,name,city,region,lat,lon,kind,active,color,created_at)"
            " VALUES (?,?,?,?,?,?,?,1,?,?)",
            (loc_id, name, (data.get("city") or "").strip(), "Atacama", lat, lon,
             data.get("kind", "comunidad"), data.get("color", "#1E88E5"), _now()))
        conn.commit()
        row = conn.execute("SELECT * FROM locations WHERE id=?", (loc_id,)).fetchone()
        return jsonify({"location": dict(row)})
    finally:
        conn.close()

def _f(val, default):
    """Convierte a float; usa `default` si está vacío."""
    try:
        return float(val) if val not in (None, "") else default
    except (TypeError, ValueError):
        return default


def _report_cols():
    return ("o.id AS obs_id, o.sample_id, o.stain, o.image_path, o.microscope_mag, "
            "o.n_observed, o.morph_fiber, o.morph_fragment, o.morph_film, o.morph_mineral, "
            "o.n_uncertain, o.obs_time AS obs_time, o.status, o.admin_comment, o.created_at AS obs_created_at, "
            "s.location_id AS sample_location_id, s.dish_id, s.volume_ml, s.area_cm2, "
            "s.medium, s.sample_type, s.replicate_group, s.exposure_start, s.exposure_end, "
            "s.exposure_hours, s.notes, "
            "l.id AS location_id, l.name AS location_name, l.city, l.lat, l.lon, l.color, "
            "u.name AS user_name, u.school AS user_school, u.username")


def _build_report(conn, row):
    rep = dict(row)
    metrics = science.compute_metrics(rep.get("n_observed"), rep.get("volume_ml"),
                                      rep.get("area_cm2"), rep.get("exposure_hours"))
    rep["metrics"] = metrics
    rep["semaphore"] = science.semaphore(metrics["conc_p_ml"])
    rep["index"] = science.plastic_index(metrics["conc_p_ml"])
    return rep


def _store_snapshot(conn, sample_id, loc_row, wdata, ts_start, ts_end):
    """Guarda/adjunta el histórico meteorológico de la ventana de exposición."""
    try:
        conn.execute(
            "INSERT INTO weather_snapshots (id,sample_id,location_id,source,"
            "ts_start,ts_end,temp_avg,hum_avg,wind_avg,wind_max,wind_dir_avg,"
            "pressure_avg,precip_mm,raw,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (_uid(), sample_id, loc_row["id"], (wdata or {}).get("source"),
             ts_start, ts_end,
             (wdata or {}).get("temp"), (wdata or {}).get("hum"),
             (wdata or {}).get("wind"), (wdata or {}).get("wind_max"),
             (wdata or {}).get("wind_dir"), (wdata or {}).get("pressure"),
             (wdata or {}).get("precip"),
             json.dumps(wdata, ensure_ascii=False)[:400], _now()))
        return True
    except Exception:
        return False


@bp.get("/reports")
def list_reports():
    conn = db.get_db(current_app)
    try:
        sql = "SELECT " + _report_cols() + _REPORT_JOIN
        conds, args = [], []
        for arg, col in (("status", "o.status"), ("sample_type", "s.sample_type"),
                         ("location_id", "s.location_id")):
            if request.args.get(arg):
                conds.append(f"{col}=?")
                args.append(request.args.get(arg))
        if conds:
            sql += " WHERE " + " AND ".join(conds)
        sql += " ORDER BY o.created_at DESC, o.rowid DESC LIMIT ?"
        args.append(min(int(request.args.get("limit", 100)), 300))
        rows = conn.execute(sql, args).fetchall()
        return jsonify({"reports": [_build_report(conn, r) for r in rows]})
    finally:
        conn.close()

@bp.post("/reports")
@login_required
def create_report():
    """Crea muestra (placa Petri) + observación (microscopio, foto, tinción)."""
    form = request.form
    conn = db.get_db(current_app)
    try:
        loc = conn.execute("SELECT * FROM locations WHERE id=?",
                           (form.get("location_id"),)).fetchone()
        if not loc:
            return jsonify({"error": "ubicación inválida"}), 400

        stain = form.get("stain")
        allowed_values = {i["value"] for i in _stains(conn)}
        if stain not in allowed_values:
            return jsonify({"error": "tinción no permitida",
                            "allowed": sorted(allowed_values)}), 400

        img = request.files.get("image")
        rel_path = None
        if img and img.filename:
            ext = os.path.splitext(img.filename)[1].lower()
            if ext not in config.IMAGE_ALLOWED_EXT:
                return jsonify({"error": "formato de imagen no permitido"}), 400
            fname = _uid() + ext
            img.save(os.path.join(current_app.config["UPLOAD_DIR"], fname))
            rel_path = "/static/uploads/" + fname

        exp_start = _parse_dt(form.get("exposure_start"))
        exp_end = _parse_dt(form.get("exposure_end"))
        exp_h = None
        if exp_start and exp_end:
            exp_h = max(0.0, round((exp_end - exp_start).total_seconds() / 3600.0, 2))

        sample_type = form.get("sample_type", "muestra")
        if sample_type not in ("muestra", "blanco", "replica"):
            sample_type = "muestra"

        sample_id = _uid()
        conn.execute(
            "INSERT INTO samples (id,location_id,user_id,dish_id,volume_ml,area_cm2,medium,"
            "sample_type,replicate_group,exposure_start,exposure_end,exposure_hours,notes,created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (sample_id, loc["id"], g.user["id"], form.get("dish_id"),
             _f(form.get("volume_ml"), config.DEFAULT_VOLUME_ML),
             _f(form.get("area_cm2"), config.DEFAULT_AREA_CM2),
             form.get("medium") or config.DEFAULT_MEDIUM,
             sample_type, form.get("replicate_group") or None,
             form.get("exposure_start"), form.get("exposure_end"), exp_h,
             form.get("notes"), _now()))

        obs_id = _uid()
        conn.execute(
            "INSERT INTO observations (id,sample_id,user_id,stain,image_path,microscope_mag,"
            "n_observed,morph_fiber,morph_fragment,morph_film,morph_mineral,n_uncertain,"
            "obs_time,status,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (obs_id, sample_id, g.user["id"], stain, rel_path,
             int(_f(form.get("microscope_mag"), 400)),
             int(_f(form.get("n_observed"), 0)),
             int(_f(form.get("morph_fiber"), 0)),
             int(_f(form.get("morph_fragment"), 0)),
             int(_f(form.get("morph_film"), 0)),
             int(_f(form.get("morph_mineral"), 0)),
             int(_f(form.get("n_uncertain"), 0)),
             (form.get("obs_time") or "").strip() or None,
             "pendiente", _now()))

        # Clima de la ventana de exposición (Open-Meteo, fallback DGAC/METAR)
        try:
            svc = weather.WeatherService()
            start_for_w = exp_start or dt.datetime.now(dt.timezone.utc)
            wdata = svc.report_weather(loc["lat"], loc["lon"], start_for_w, exp_end)
            if wdata:
                _store_snapshot(conn, sample_id, loc, wdata,
                                form.get("exposure_start"), form.get("exposure_end"))
        except Exception:
            pass
        conn.commit()
        backfill_weather_history(current_app)   # completa el clima de muestras antiguas
        excel.sync(current_app)          # Excel de datos al día

        row = conn.execute("SELECT " + _report_cols() + _REPORT_JOIN +
                           " WHERE o.id=?", (obs_id,)).fetchone()
        return jsonify({"report": _build_report(conn, row)}), 201
    finally:
        conn.close()

@bp.get("/reports/<obs_id>")
def report_detail(obs_id):
    conn = db.get_db(current_app)
    try:
        row = conn.execute("SELECT " + _report_cols() + _REPORT_JOIN +
                           " WHERE o.id=?", (obs_id,)).fetchone()
        if not row:
            return jsonify({"error": "no existe"}), 404
        rep = _build_report(conn, row)

        wrow = conn.execute("SELECT * FROM weather_snapshots WHERE sample_id=?",
                            (row["sample_id"],)).fetchone()
        rep["weather"] = dict(wrow) if wrow else None

        grp = row["replicate_group"]
        rep["qc_notes"] = []
        if grp:
            group_rows = conn.execute(
                "SELECT s.sample_type, o.n_observed FROM samples s "
                "JOIN observations o ON o.sample_id=s.id WHERE s.replicate_group=?",
                (grp,)).fetchall()
            rep["qc_notes"] = science.replicates_qc([dict(r) for r in group_rows])
        bl = conn.execute(
            "SELECT o.n_observed FROM observations o JOIN samples s ON o.sample_id=s.id "
            "WHERE s.sample_type='blanco' AND s.replicate_group=? AND o.id!=? LIMIT 1",
            (grp, obs_id)).fetchone() if grp else None
        if bl is not None:
            rep["blank_qc"] = science.blank_qc(bl["n_observed"])
        return jsonify(rep)
    finally:
        conn.close()


@bp.get("/pending")
@admin_required
def pending_list():
    conn = db.get_db(current_app)
    try:
        rows = conn.execute(
            "SELECT " + _report_cols() + _REPORT_JOIN +
            " WHERE o.status='pendiente' ORDER BY o.created_at DESC, o.rowid DESC LIMIT 50").fetchall()
        return jsonify({"pending": [_build_report(conn, r) for r in rows]})
    finally:
        conn.close()


@bp.post("/reports/<obs_id>/review")
@admin_required
def review_report(obs_id):
    data = request.get_json(silent=True) or {}
    status = data.get("status")
    if status not in ("aprobado", "rechazado"):
        return jsonify({"error": "status debe ser aprobado o rechazado"}), 400
    conn = db.get_db(current_app)
    try:
        cur = conn.execute(
            "UPDATE observations SET status=?, admin_comment=?, reviewed_by=?, reviewed_at=? "
            "WHERE id=?", (status, (data.get("comment") or "").strip() or None,
                           g.user["id"], _now(), obs_id))
        if cur.rowcount == 0:
            return jsonify({"error": "no existe"}), 404
        conn.commit()

        # Al aprobar se (re)asocia el histórico meteorológico definitivo de la
        # ventana de exposición, para correlacionar deposición con clima.
        if status == "aprobado":
            orow = conn.execute("SELECT sample_id FROM observations WHERE id=?",
                                (obs_id,)).fetchone()
            if orow and orow["sample_id"]:
                srow = conn.execute("SELECT * FROM samples WHERE id=?",
                                    (orow["sample_id"],)).fetchone()
                if srow:
                    lrow = conn.execute("SELECT * FROM locations WHERE id=?",
                                        (srow["location_id"],)).fetchone()
                    if lrow:
                        try:
                            wd = weather.WeatherService().report_weather(
                                lrow["lat"], lrow["lon"],
                                _parse_dt(srow["exposure_start"]),
                                _parse_dt(srow["exposure_end"]))
                            if wd:
                                conn.execute("DELETE FROM weather_snapshots WHERE sample_id=?",
                                             (srow["id"],))
                                conn.commit()
                                _store_snapshot(conn, srow["id"], lrow, wd,
                                                srow["exposure_start"], srow["exposure_end"])
                                conn.commit()
                        except Exception:
                            pass

        backfill_weather_history(current_app)   # completa el clima que aún falte
        excel.sync(current_app)          # Excel de datos al día tras la revisión
        row = conn.execute("SELECT " + _report_cols() + _REPORT_JOIN +
                           " WHERE o.id=?", (obs_id,)).fetchone()
        return jsonify({"report": _build_report(conn, row)})
    finally:
        conn.close()


@bp.put("/locations/<loc_id>")
@admin_required
def update_location(loc_id):
    """Edita un punto de muestreo (activar/desactivar, nombre, color...)."""
    data = request.get_json(silent=True) or {}
    conn = db.get_db(current_app)
    try:
        row = conn.execute("SELECT * FROM locations WHERE id=?",
                           (loc_id,)).fetchone()
        if not row:
            return jsonify({"error": "no existe"}), 404
        if "kind" in data and data["kind"] not in ("escuela", "comunidad", "referencia"):
            return jsonify({"error": "tipo de punto inválido"}), 400
        for f in ("name", "city", "kind", "color"):
            if f in data and data[f] is not None:
                conn.execute(f"UPDATE locations SET {f}=? WHERE id=?",
                             (str(data[f]).strip(), loc_id))
        for f in ("lat", "lon"):
            if f in data and data[f] is not None:
                try:
                    conn.execute(f"UPDATE locations SET {f}=? WHERE id=?",
                                 (float(data[f]), loc_id))
                except (TypeError, ValueError):
                    return jsonify({"error": f"{f} debe ser numérico"}), 400
        if "active" in data:
            conn.execute("UPDATE locations SET active=? WHERE id=?",
                         (1 if data["active"] else 0, loc_id))
        conn.commit()
        out = conn.execute("SELECT * FROM locations WHERE id=?",
                           (loc_id,)).fetchone()
        return jsonify({"location": dict(out)})
    finally:
        conn.close()


@bp.get('/export.xlsx')
@admin_required
def export_excel():
    conn = db.get_db(current_app)
    try:
        wb, row_count = excel.build_workbook(conn)
    finally:
        conn.close()
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    resp = send_file(
        buf, as_attachment=True, download_name='MicroAlerta_datos.xlsx',
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    resp.headers['X-Rows'] = str(row_count)   # filas del dataset exportado
    return resp


@bp.get("/export/summary")
@admin_required
def export_summary():
    """Resumen breve del Excel de datos."""
    conn = db.get_db(current_app)
    try:
        n = conn.execute(
            "SELECT COUNT(*) FROM observations WHERE status='aprobado'").fetchone()[0]
        w = conn.execute(
            "SELECT COUNT(*) FROM weather_snapshots").fetchone()[0]
        locs = conn.execute(
            "SELECT COUNT(*) FROM locations WHERE active=1").fetchone()[0]
    finally:
        conn.close()
    return jsonify({
        "approved_samples": n,
        "weather_snapshots": w,
        "active_locations": locs,
        "file": "/api/export.xlsx",
        "file_name": "MicroAlerta_datos.xlsx",
    })


@bp.get("/export.csv")
@admin_required
def export_csv():
    """Mismo dataset del Excel en CSV (UTF-8 con BOM) para graficar."""
    import csv
    from datetime import datetime as _dt
    conn = db.get_db(current_app)
    try:
        rows, headers = excel.dataset_rows(conn)
    finally:
        conn.close()
    buf = io.StringIO()
    buf.write("\ufeff")
    w = csv.writer(buf)
    w.writerow(headers)
    for r in rows:
        w.writerow([(""
                      if v is None
                      else v.isoformat(sep=" ") if isinstance(v, _dt)
                      else v) for v in r])
    data = buf.getvalue().encode("utf-8")
    bio = io.BytesIO(data)
    bio.seek(0)
    return send_file(
        bio, as_attachment=True, download_name="MicroAlerta_datos.csv",
                mimetype="text/csv; charset=utf-8")


@bp.get("/community")
def community():
    """Agregado por punto de muestreo para mapa/inicio comunitario."""
    conn = db.get_db(current_app)
    try:
        rows = conn.execute(
            "SELECT " + _report_cols() + _REPORT_JOIN +
            " WHERE o.status='aprobado' ORDER BY o.created_at DESC, o.rowid DESC LIMIT 50").fetchall()
        weathers = {}
        for w in conn.execute("SELECT * FROM weather_snapshots"):
            weathers[w["sample_id"]] = dict(w)
        latest = {}
        for r in rows:
            lid = r["location_id"]
            if lid not in latest:
                rep = _build_report(conn, r)
                rep["weather"] = weathers.get(r["sample_id"])
                latest[lid] = {"location": {"id": r["location_id"], "name": r["location_name"],
                                            "city": r["city"], "lat": r["lat"], "lon": r["lon"],
                                            "color": r["color"]},
                               "report": rep}
        summary = {
            "locations": list(latest.values()),
            "cities": {},
            "counts_by_kind": {},
            "total_approved": len(rows),
        }
        for r in rows:
            summary["cities"][r["city"]] = summary["cities"].get(r["city"], 0) + 1
            k = r["sample_type"]
            summary["counts_by_kind"][k] = summary["counts_by_kind"].get(k, 0) + 1
        return jsonify(summary)
    finally:
        conn.close()


@bp.get("/weather")
def weather_endpoint():
    lat = request.args.get("lat")
    lon = request.args.get("lon")
    if not lat or not lon:
        return jsonify({"error": "faltan lat/lon"}), 400
    start = _parse_dt(request.args.get("start"))
    end = _parse_dt(request.args.get("end"))
    if not start:
        start = dt.datetime.now(dt.timezone.utc)
    try:
        data = weather.WeatherService().report_weather(float(lat), float(lon), start, end)
        return jsonify({"weather": data})
    except Exception as exc:
        return jsonify({"error": "clima no disponible", "detail": str(exc)}), 502


@bp.post("/weather/backfill")
@admin_required
def weather_backfill():
    """Completa el clima de las muestras que aún no lo tienen y rehace el Excel."""
    resumen = backfill_weather_history(current_app)
    excel.sync(current_app)
    return jsonify({"ok": True, "backfill": resumen, "file": "/api/export.xlsx"})


@bp.get("/selfcare")
def selfcare_endpoint():
    args = request.args
    def _num(key):
        v = args.get(key)
        return float(v) if v not in (None, "") else None
    conc = _num("conc") or 0.0
    try:
        hum = _num("hum")
        wind = _num("wind")
        temp = _num("temp")
    except ValueError:
        return jsonify({"error": "valores num\u00e9ricos inv\u00e1lidos"}), 400
    prefs = {"temp": args.get("utemp"), "wind": args.get("uwind"),
             "conc": args.get("uconc")}
    recs = science.self_care(conc, hum, wind, temp, units_pref=prefs)
    return jsonify({"recommendations": recs})


@bp.get("/semaphore")
def semaphore_scale_endpoint():
    """Escala del semáforo (colores, rangos y recomendaciones) para la leyenda."""
    return jsonify({"levels": science.semaphore_scale()})


@bp.get("/stats")
@admin_required
def stats():
    conn = db.get_db(current_app)
    try:
        counts = {}
        for key, sql in (
                ("users", "SELECT COUNT(*) AS c FROM users"),
                ("locations", "SELECT COUNT(*) AS c FROM locations"),
                ("samples", "SELECT COUNT(*) AS c FROM samples"),
                ("observations", "SELECT COUNT(*) AS c FROM observations"),
                ("pending", "SELECT COUNT(*) AS c FROM observations WHERE status='pendiente'"),
                ("approved", "SELECT COUNT(*) AS c FROM observations WHERE status='aprobado'"),
                ("rejected", "SELECT COUNT(*) AS c FROM observations WHERE status='rechazado'")):
            counts[key] = conn.execute(sql).fetchone()["c"]
        by_location = [dict(r) for r in conn.execute(
            "SELECT l.name AS name, l.city AS city, COUNT(*) AS n,"
            " ROUND(AVG(o.n_observed*1.0/NULLIF(s.volume_ml,0)),3) AS avg_conc"
            " FROM observations o JOIN samples s ON o.sample_id=s.id"
            " JOIN locations l ON s.location_id=l.id"
            " WHERE o.status='aprobado' GROUP BY l.id ORDER BY n DESC LIMIT 15")]
        morph = {k: conn.execute(
            "SELECT COALESCE(SUM(" + k + "),0) AS v FROM observations WHERE status='aprobado'"
        ).fetchone()["v"] for k in ("morph_fiber", "morph_fragment",
                                    "morph_film", "morph_mineral")}
        by_stain = {r["stain"]: r["n"] for r in conn.execute(
            "SELECT stain, COUNT(*) AS n FROM observations"
            " WHERE status='aprobado' GROUP BY stain")}
        avg_conc = conn.execute(
            "SELECT ROUND(AVG(o.n_observed*1.0/NULLIF(s.volume_ml,0)),3) AS a"
            " FROM observations o JOIN samples s ON o.sample_id=s.id"
            " WHERE o.status='aprobado'").fetchone()["a"]
        return jsonify({
            "stats": counts,
            "by_location": by_location,
            "by_morphology": morph,
            "by_stain": by_stain,
            "avg_conc_approved": avg_conc,
        })
    finally:
        conn.close()


@bp.put("/reports/<obs_id>")
@admin_required
def update_report(obs_id):
    data = request.get_json(silent=True) or {}
    conn = db.get_db(current_app)
    try:
        row = conn.execute("SELECT sample_id FROM observations WHERE id=?",
                           (obs_id,)).fetchone()
        if not row:
            return jsonify({"error": "no existe"}), 404
        if data.get("stain") is not None:
            allowed_values = {i["value"] for i in _stains(conn)}
            if data["stain"] not in allowed_values:
                return jsonify({"error": "tinci\u00f3n no permitida"}), 400
        if data.get("sample_type") is not None and \
                data["sample_type"] not in ("muestra", "blanco", "replica"):
            return jsonify({"error": "tipo de plato inv\u00e1lido"}), 400
        for f in ("stain", "n_observed", "microscope_mag", "morph_fiber",
                  "morph_fragment", "morph_film", "morph_mineral", "n_uncertain"):
            if f in data:
                conn.execute("UPDATE observations SET " + f + "=? WHERE id=?", (data[f], obs_id))
        sid = row["sample_id"]
        for f in ("dish_id", "replicate_group", "sample_type", "medium", "notes"):
            if f in data:
                conn.execute("UPDATE samples SET " + f + "=? WHERE id=?", (data[f], sid))
        conn.commit()
        excel.sync(current_app)
        out = conn.execute("SELECT " + _report_cols() + _REPORT_JOIN +
                           " WHERE o.id=?", (obs_id,)).fetchone()
        return jsonify({"report": _build_report(conn, out)})
    finally:
        conn.close()


@bp.delete("/reports/<obs_id>")
@admin_required
def delete_report(obs_id):
    conn = db.get_db(current_app)
    try:
        row = conn.execute("SELECT sample_id FROM observations WHERE id=?",
                           (obs_id,)).fetchone()
        if not row:
            return jsonify({"error": "no existe"}), 404
        conn.execute("DELETE FROM weather_snapshots WHERE sample_id=?",
                     (row["sample_id"],))
        conn.execute("DELETE FROM observations WHERE id=?", (obs_id,))
        conn.execute("DELETE FROM samples WHERE id=?", (row["sample_id"],))
        conn.commit()
        excel.sync(current_app)
        return jsonify({"ok": True})
    finally:
        conn.close()






@bp.get("/config")
def public_config():
    conn = db.get_db(current_app)
    try:
        r = conn.execute("SELECT value FROM configs WHERE key='video_url'").fetchone()
        return jsonify({"video_url": r["value"] if r else config.DEFAULT_VIDEO_URL})
    finally:
        conn.close()


@bp.put("/config/video")
@admin_required
def set_video_url():
    url = ((request.get_json(silent=True) or {}).get("url") or "").strip()
    if not url.startswith("http"):
        return jsonify({"error": "url inválida"}), 400
    conn = db.get_db(current_app)
    try:
        conn.execute("INSERT INTO configs (key,value) VALUES ('video_url',?) "
                     "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (url,))
        conn.commit()
        return jsonify({"video_url": url})
    finally:
        conn.close()


# ── Preferencias por usuario (las unidades siguen a la cuenta) ──────────────
@bp.get("/prefs")
@login_required
def get_prefs():
    conn = db.get_db(current_app)
    try:
        rows = conn.execute("SELECT key, value FROM user_prefs WHERE user_id=?",
                            (g.user["id"],)).fetchall()
        prefs = {}
        for r in rows:
            try:
                prefs[r["key"]] = json.loads(r["value"])
            except Exception:
                pass
        return jsonify({"prefs": prefs})
    finally:
        conn.close()


@bp.put("/prefs")
@login_required
def put_prefs():
    from . import units as units_mod
    data = request.get_json(silent=True) or {}
    if "units" not in data:
        return jsonify({"error": "faltan 'units'"}), 400
    clean = units_mod.normalize_units(data["units"])
    conn = db.get_db(current_app)
    try:
        conn.execute(
            "INSERT INTO user_prefs (user_id,key,value) VALUES (?,'units',?) "
            "ON CONFLICT(user_id,key) DO UPDATE SET value=excluded.value",
            (g.user["id"], json.dumps(clean)))
        conn.commit()
        return jsonify({"prefs": {"units": clean}})
    finally:
        conn.close()


def _preferred_exposure_times(obs_dt):
    """Candidatos de hora declarada: la propia y, si cae a medianoche,
    la lectura de las 16:40 (hora local Atacama) del mismo día."""
    times = [obs_dt]
    if obs_dt.hour == 0 and obs_dt.minute == 0:
        times.append(obs_dt.replace(hour=16, minute=40))
    return times


def _fetch_snapshot(lat, lon, target_dt):
    try:
        return weather.WeatherService().report_weather(lat, lon, target_dt, target_dt)
    except Exception:
        return None


def _insert_weather_snapshot(app, sample_id, location_id, target_dt, snapshot):
    """Guarda el snapshot del backfill en la base configurada por la app."""
    conn = db.get_db(app)
    try:
        _store_snapshot(conn, sample_id, {"id": location_id}, snapshot,
                        target_dt, target_dt)
        conn.commit()
        return True
    finally:
        conn.close()


def _purge_orphan_snapshots(conn):
    """Borra snapshots cuyo `sample_id` ya no existe.

    Son restos de versiones anteriores (cuando el backfill guardaba ids que no
    correspondían a ninguna muestra): ensuciaban el conteo de /export/summary y
    no aparecían en el Excel.
    """
    cur = conn.execute(
        "DELETE FROM weather_snapshots WHERE sample_id IS NULL"
        " OR sample_id NOT IN (SELECT id FROM samples)")
    try:
        return int(cur.rowcount or 0)
    except Exception:
        return 0


# ── Panel: diagnóstico del sistema + mantenimiento ──────────────────────────
@bp.get("/diagnose")
def diagnose():
    """Verificación de todo lo necesario para que la app funcione.

    Usado por la vista "Panel": servidor, base de datos, sesión,
    tinciones habilitadas, puntos de muestreo, Excel de datos, clima
    (fuente en vivo) y video de la guía. Público (sin sesión) y de lectura.
    """
    checks = []

    def add(name, status, detail):
        checks.append({"name": name, "status": status, "detail": detail})

    add("Servidor y API", "ok", "Flask respondiendo correctamente")

    conn = None
    try:
        conn = db.get_db(current_app)
        users = conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]
        locs = conn.execute(
            "SELECT COUNT(*) AS c FROM locations WHERE active=1").fetchone()["c"]
        samples = conn.execute("SELECT COUNT(*) AS c FROM samples").fetchone()["c"]
        obs = conn.execute("SELECT COUNT(*) AS c FROM observations").fetchone()["c"]
        pending = conn.execute(
            "SELECT COUNT(*) AS c FROM observations WHERE status='pendiente'"
        ).fetchone()["c"]
        add("Base de datos", "ok",
            "%s usuarios · %s puntos activos · %s placas · %s reportes (%s pendientes)"
            % (users, locs, samples, obs, pending))
    except Exception as exc:                            # noqa: BLE001
        add("Base de datos", "error", "No responde: %s" % exc)
        return jsonify({"ok": False, "checks": checks})
    try:
        # Sesión actual (pública: informa si hay alguien identificado).
        uid = session.get("uid")
        user_row = None
        if uid:
            user_row = conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
        if user_row:
            add("Sesión", "ok",
                "Identificado como %s (%s)" % (user_row["name"] or user_row["username"],
                                               user_row["role"]))
        else:
            add("Sesión", "warn", "Sin iniciar sesión — entra con tu cuenta para reportar")

        # Tinciones habilitadas (limitadas por el administrador).
        cur = conn.execute("SELECT value FROM configs WHERE key='allowed_stains'")
        r = cur.fetchone()
        allowed = json.loads(r["value"]) if r else config.STAIN_DEFAULTS
        enabled = [s for s in allowed if s.get("enabled")]
        if enabled:
            add("Tinciones habilitadas", "ok",
                "%d opción(es): %s" % (len(enabled),
                                       ", ".join(s["value"] for s in enabled)))
        else:
            add("Tinciones habilitadas", "error",
                "Ninguna habilitada — el formulario de reporte no podrá ofrecer tinción")

        # Puntos de muestreo activos.
        pts = [row["name"] for row in conn.execute(
            "SELECT name FROM locations WHERE active=1 ORDER BY name LIMIT 4")]
        if pts:
            add("Puntos de muestreo", "ok",
                "%d activos (p. ej. %s)" % (locs, " · ".join(pts)))
        else:
            add("Puntos de muestreo", "error",
                "Sin puntos activos — alta en Panel admin → Puntos")

        # Video de la guía.
        cur = conn.execute("SELECT value FROM configs WHERE key='video_url'")
        r = cur.fetchone()
        vid = r["value"] if r else config.DEFAULT_VIDEO_URL
        add("Video de la guía", "ok" if vid else "warn",
            (vid[:80] + "…") if len(vid) > 80 else (vid or "Sin configurar"))
    finally:
        conn.close()

    # Excel de datos (archivo en disco).
    xlsx = current_app.config.get("EXCEL_PATH") or config.EXCEL_PATH
    if xlsx and os.path.exists(xlsx):
        try:
            mtime = dt.datetime.fromtimestamp(os.path.getmtime(xlsx))
            size_kb = os.path.getsize(xlsx) // 1024
            add("Excel de datos", "ok",
                "Actualizado %s · %s KB · descarga en /api/export.xlsx"
                % (mtime.strftime("%d/%m/%y %H:%M"), size_kb))
        except OSError as exc:
            add("Excel de datos", "warn", "No se pudo inspeccionar: %s" % exc)
    else:
        add("Excel de datos", "warn",
            "Aún no generado — se crea al registrar la primera muestra")

    # Fuentes de clima en vivo (solo si hay red; con timeout corto).
    if current_app.config.get("TESTING"):
        add("Fuente de clima", "ok", "omitido (modo prueba)")
    else:
        try:
            wd = weather.WeatherService().get_current(-27.37, -70.33)   # Copiapó
            if wd and wd.get("temp") is not None:
                add("Fuente de clima", "ok",
                    "%s · %.1f °C · humedad %s%% · viento %s km/h"
                    % (wd.get("source", "?"), wd["temp"],
                       wd.get("hum", "?"), wd.get("wind", "?")))
            else:
                add("Fuente de clima", "warn",
                    "Sin respuesta de Open-Meteo/met.no/METAR — reintenta luego")
        except Exception as exc:                        # noqa: BLE001
            add("Fuente de clima", "warn", "No disponible ahora (%s)" % exc)

    ok_all = all(c["status"] != "error" for c in checks)
    return jsonify({"ok": ok_all, "checks": checks})


@bp.post("/maintenance")
@admin_required
def maintenance():
    """Acciones de mantenimiento del Panel (solo admin)."""
    action = ((request.get_json(silent=True) or {}).get("action") or "").strip()
    if action == "backfill_weather":
        resumen = backfill_weather_history(current_app)
        excel.sync(current_app)
        return jsonify({"ok": True, "backfill": resumen})
    if action == "excel_sync":
        path = excel.sync(current_app)
        return jsonify({"ok": bool(path), "file": "/api/export.xlsx"})
    return jsonify({"error": "accion desconocida"}), 400


def backfill_weather_history(app):
    """Completa el historial meteorológico que falte, muestra por muestra.

    Recorre TODAS las observaciones (igual que el Excel de datos: aprobadas,
    pendientes o rechazadas) y para cada muestra sin snapshot —o con snapshot
    incompleto— busca el clima de su ventana de exposición: archivo histórico
    si la placa ya se retiró, medición en vivo si la ventana incluye hoy.
    Guarda temperatura, humedad, viento, ráfaga, dirección del viento, presión,
    precipitación y la fuente del dato. Devuelve un resumen de lo realizado.
    """
    conn = db.get_db(app)
    try:
        purgados = _purge_orphan_snapshots(conn)
        conn.commit()
        rows = conn.execute(
            "SELECT o.id AS obs_id, o.sample_id, o.obs_time, o.created_at, o.status,"
            "       s.exposure_start, s.exposure_end,"
            "       l.id AS location_id, l.lat, l.lon"
            " FROM observations o"
            " JOIN samples s      ON o.sample_id   = s.id"
            " JOIN locations l    ON s.location_id = l.id"
            " LEFT JOIN weather_snapshots ws ON ws.sample_id = o.sample_id"
            " WHERE ws.id IS NULL OR ws.temp_avg IS NULL OR ws.wind_avg IS NULL"
            " ORDER BY o.created_at DESC, o.id ASC").fetchall()
    finally:
        conn.close()

    rellenadas, sin_datos = 0, 0
    for r in rows:
        try:
            lat, lon = float(r["lat"]), float(r["lon"])
        except (TypeError, ValueError):
            sin_datos += 1
            continue
        ref_dt = _parse_dt(r["exposure_start"] or r["obs_time"] or r["created_at"])
        if not ref_dt:
            sin_datos += 1
            continue
        for target_dt in _preferred_exposure_times(ref_dt):
            snapshot = _fetch_snapshot(lat, lon, target_dt)
            if not snapshot:
                continue
            if snapshot.get("temp") is None or snapshot.get("wind") is None:
                continue
            _insert_weather_snapshot(app, r["sample_id"], r["location_id"],
                                     target_dt, snapshot)
            rellenadas += 1
            break
        else:
            sin_datos += 1

    resumen = {"muestras_sin_clima": len(rows), "rellenadas": rellenadas,
               "sin_datos": sin_datos, "snapshots_huerfanos_borrados": purgados}
    try:
        app.logger.info("clima backfill: %s", resumen)
    except Exception:
        pass
    return resumen


def register(app):
    app.register_blueprint(bp)