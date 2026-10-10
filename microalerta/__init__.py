"""
MicroAlerta — sistema ciudadano de monitoreo de supuestas partículas tipo microplástico
en el aire de Atacama y Copiapó.

"""
import os

from flask import Flask, jsonify, request, send_from_directory

from . import config


def create_app(test_config=None):
    """App factory. `test_config` permite apuntar a DB/upload temporales en tests."""
    static_dir = os.path.join(config.PROJECT_ROOT, "static")
    app = Flask(__name__,
                static_folder=static_dir,
                static_url_path="/static")
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("MICROALERTA_SECRET", "dev-clave-copiapo-2026"),
        DATABASE=os.environ.get("MICROALERTA_DB", config.DATABASE),
        UPLOAD_DIR=os.environ.get("MICROALERTA_UPLOADS", config.UPLOAD_DIR),
        EXCEL_PATH=os.environ.get("MICROALERTA_EXCEL", config.EXCEL_PATH),
        MAX_CONTENT_LENGTH=config.IMAGE_MAX_MB * 1024 * 1024,
        JSON_AS_ASCII=False,
    )
    if test_config:
        app.config.update(test_config)

    os.makedirs(app.config["UPLOAD_DIR"], exist_ok=True)

    # Frontend PWA (mobile-first) servido desde /static
    from . import db
    from . import api

    db.init_db(app)
    api.register(app)

    @app.route("/")
    def index():
        return send_from_directory(app.static_folder, "index.html")

    @app.errorhandler(404)
    def spa_fallback(e):
        # Rutas no-API vuelven al shell de la SPA (enrutado por hash).
        if request.path.startswith("/api/"):
            return jsonify({"error": "not_found", "detail": str(e)}), 404
        return send_from_directory(app.static_folder, "index.html")

    @app.errorhandler(413)
    def too_large(e):
        return jsonify({"error": "imagen demasiado grande", "detail": str(e)}), 413

    return app