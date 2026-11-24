"""
Flask Application Factory
CSE476 CA2 — Automated Code Review Board (Q14)
"""

import os
from flask import Flask, send_from_directory
from flask_cors import CORS

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from backend.routes import api_bp
from backend.error_handlers import register_error_handlers
from orchestration.workflow import ReviewWorkflow
from memory.persistence import DatabaseManager, JsonlAuditLogger


def create_app(test_config=None) -> Flask:
    static_folder = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "static"))
    app = Flask(__name__, static_folder=static_folder, static_url_path="")
    CORS(app)

    # Security Limits: 25 MB max upload
    app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024
    app.config["UPLOAD_FOLDER"] = os.path.join(os.path.dirname(__file__), "..", "uploads")
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    # Core singletons
    db_path = os.environ.get("REVIEWS_DB_PATH", os.path.join(os.path.dirname(__file__), "..", "data", "reviews.db"))
    log_dir = os.environ.get("REVIEWS_LOG_DIR", os.path.join(os.path.dirname(__file__), "..", "logs"))
    
    app.config["DATABASE"] = DatabaseManager(db_path=db_path)
    app.config["LOGGER"] = JsonlAuditLogger(log_dir=log_dir)
    app.config["WORKFLOW"] = ReviewWorkflow(db_path=db_path, log_dir=log_dir)

    if test_config:
        app.config.update(test_config)

    # Register API blueprint
    app.register_blueprint(api_bp, url_prefix="/api")
    register_error_handlers(app)

    # Root route serves dashboard
    @app.route("/")
    def index():
        return send_from_directory(app.static_folder, "index.html")

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(host="0.0.0.0", port=5000, debug=True)
