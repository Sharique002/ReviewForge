"""
Flask Error Handlers
CSE476 CA2 — Automated Code Review Board (Q14)
"""

from flask import jsonify


def register_error_handlers(app):
    @app.errorhandler(400)
    def bad_request(error):
        return jsonify({"error": "Bad Request", "message": str(error)}), 400

    @app.errorhandler(404)
    def not_found(error):
        return jsonify({"error": "Not Found", "message": "The requested resource was not found."}), 404

    @app.errorhandler(413)
    def request_entity_too_large(error):
        return jsonify({
            "error": "Payload Too Large",
            "message": "Uploaded file exceeds the maximum permitted size limit (25MB)."
        }), 413

    @app.errorhandler(500)
    def internal_server_error(error):
        return jsonify({
            "error": "Internal Server Error",
            "message": "An unexpected server error occurred. Please consult the audit logs."
        }), 500
