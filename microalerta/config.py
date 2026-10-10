"""
Configuración y constantes científicas del protocolo MicroAlerta.
"""
import os

# Ruta raíz del proyecto (microalerta/microalerta/config.py -> microalerta/)
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ── Base de datos ────────────────────────────────────────────────────────────
# SQLite por defecto (cero dependencias). Para producción/despliegue con
# múltiples procesos, apunta DATABASE_URL a PostgreSQL:
#   set DATABASE_URL=postgresql://usuario:clave@host:5432/microalerta
# Requiere el driver psycopg (ver requirements.txt, sección [postgres]).
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
DATABASE = os.environ.get("MICROALERTA_DB", os.path.join(PROJECT_ROOT, "microalerta.db"))
DB_ENGINE = "postgres" if DATABASE_URL else "sqlite"
UPLOAD_DIR = os.path.join(PROJECT_ROOT, "static", "uploads")

# Excel de datos (se regenera solo con cada muestra registrada/aprobada)
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
EXCEL_PATH = os.path.join(DATA_DIR, "MicroAlerta_datos.xlsx")

# ── Protocolo de muestreo pasivo (placa Petri) ───────────────────────────────
DEFAULT_MEDIUM = "Agua destilada congelada"
DEFAULT_VOLUME_ML = 40.0
DEFAULT_AREA_CM2 = 4.0        # área de observación analizada (cm²)
EXPOSURE_MINUTES_DEFAULT = 1440  # 24 h si no se informa

# ── Aseguramiento de calidad (control cerrado y réplicas) ──────────────────
BLANK_TOLERANCE = 2           # partículas máx. admitidas en el blanco analítico
MIN_REPLICATES = 3            # réplicas mínimas recomendadas por grupo/zona

# ── Semáforo de concentración (p/mL) ──────────────────────────────────────
# Referencia saludable ~< 0.5 p/mL (orden OMS/orientación del proyecto previo)
THRESHOLD_GREEN = 0.5
THRESHOLD_YELLOW = 2.0
THRESHOLD_ORANGE = 5.0

# ── Tinción por eliminación: variables limitadas a estas opciones ─────────
# Los admins habilitan/deshabilitan; el formulario solo ofrece las habilitadas.
STAIN_DEFAULTS = [
    {"value": "lugol", "label": "Lugol (alcohol-yodo, reacción al almidón)", "enabled": True},
    {"value": "azul_metileno", "label": "Azul de metileno 1%", "enabled": True},
    {"value": "ninguna", "label": "Sin tinción (solo agua)", "enabled": True},
]

# ── Imágenes ─────────────────────────────────────────────────────────────────
IMAGE_ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
IMAGE_MAX_MB = 12

# Morfologías observadas por proceso de eliminación
MORPHOLOGIES = ["fiber", "fragment", "film", "mineral"]

# Video tutorial de la guía (el admin puede actualizarlo desde el panel)
DEFAULT_VIDEO_URL = "https://www.youtube.com/results?search_query=microplasticos+aire+placa+petri+protocolo+escolar"