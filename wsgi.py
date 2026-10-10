"""Punto de entrada WSGI para despliegue en producción (Render, Railway, etc.).

Gunicorn importa este módulo (``gunicorn wsgi:app``) en lugar de ejecutar
``app.py`` (que arranca el servidor de desarrollo con ``app.run``).

Responsabilidades:
  1. Crear la app con ``create_app()`` (esto ya inicializa la base de datos).
  2. Ejecutar la siembra idempotente de datos demo (usuarios, puntos de
     muestreo, configuración) para que la app sea usable al primer arranque.
  3. Regenerar el Excel de datos (best-effort; en un servidor sin entorno
     gráfico NO se intenta abrir Excel, solo se escribe el archivo).

Notas para producción en Render:
  - El disco del plan gratuito es EFÍMERO: las imágenes subidas y las muestras
    creadas por usuarios se pierden al redesplegar o cuando el servicio se
    "duerme". Los datos demo se reconstruyen solos en cada arranque porque
    ``seed_db`` es idempotente. Para persistencia real, montar un Render Disk
    o apuntar ``DATABASE_URL`` a PostgreSQL.
  - Define la variable de entorno ``MICROALERTA_SECRET`` con un valor propio
    para firmar las sesiones de forma segura.
"""
import os

# Rutas absolutas: config.py deriva PROJECT_ROOT de __file__, así que el
# directorio de trabajo no afecta a la base de datos, uploads ni el Excel.
from microalerta import create_app, excel
from microalerta.seed import seed_db

app = create_app()

# Siembra idempotente: crea usuarios/puntos/config demo solo si faltan.
try:
    seed_db(app, force=False)
except Exception as exc:  # noqa: BLE001
    print("wsgi: siembra omitida (%s)" % exc, flush=True)

# Excel listo al arrancar (best-effort; sin abrir la app de Excel).
try:
    excel.sync(app)
except Exception as exc:  # noqa: BLE001
    print("wsgi: excel.sync omitido (%s)" % exc, flush=True)
