"""
Prueba de humo del servidor real (HTTP por socket) usando threads.

    python tools/smoke_test.py
"""
import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
from werkzeug.serving import make_server

from microalerta import create_app
from microalerta.seed import seed_db

PORT = 8011
BASE = f"http://127.0.0.1:{PORT}"


def main():
    app = create_app()
    seed_db(app)
    server = make_server("127.0.0.1", PORT, app, threaded=True)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    time.sleep(1.0)

    results = []

    def check(name, value):
        results.append((name, value))

    try:
        check("health", requests.get(BASE + "/api/health", timeout=5).json())

        r = requests.get(BASE + "/", timeout=5)
        check("index", (r.status_code, "MicroAlerta" in r.text, len(r.text)))

        d = requests.get(BASE + "/api/community", timeout=5).json()
        check("community", (d.get("total_approved"), list(d.get("cities", {}).keys())))

        d = requests.get(BASE + "/api/stains", timeout=5).json()
        check("stains", [s["value"] for s in d["stains"]])

        r = requests.get(BASE + "/static/css/app.css", timeout=5)
        check("css", (r.status_code, len(r.content)))

        r = requests.get(BASE + "/static/icons/icon-192.png", timeout=5)
        check("icon", (r.status_code, r.content[:8] == b"\x89PNG\r\n\x1a\n"))

        r = requests.get(BASE + "/api/weather?lat=-27.37&lon=-70.33", timeout=12)
        w = (r.json() or {}).get("weather")
        check("weather", (r.status_code, w and w.get("source"), w and w.get("temp")))

        s = requests.Session()
        r = s.post(BASE + "/api/login", json={"username": "colegio", "password": "demo123"}, timeout=5)
        check("login", (r.status_code, r.json()["user"]["role"]))

        r = s.get(BASE + "/api/reports?status=aprobado", timeout=5)
        check("reports", (r.status_code, len(r.json()["reports"])))

        r = requests.get(BASE + "/api/selfcare?conc=6&hum=15&wind=50&temp=30", timeout=5)
        check("selfcare", (r.status_code, len(r.json()["recommendations"])))
    finally:
        server.shutdown()

    for name, value in results:
        print(f"OK  {name}: {value}")


if __name__ == "__main__":
    main()