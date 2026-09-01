"""Application factory for the Web API."""

from __future__ import annotations

from flask import Flask, jsonify
from flask_cors import CORS


def create_app() -> Flask:
    app = Flask(__name__)
    CORS(app)

    @app.errorhandler(Exception)
    def _handle_error(error):
        message = str(error) or error.__class__.__name__
        status = getattr(error, "code", 500)
        if not isinstance(status, int) or status < 400:
            status = 500
        return jsonify({"error": message}), status

    @app.get("/api/health")
    def health():
        return jsonify({"status": "ok"})

    from web_api.projects import blueprint as projects_bp
    app.register_blueprint(projects_bp)
    from web_api.episodes import blueprint as episodes_bp
    app.register_blueprint(episodes_bp)
    from web_api.tasks import blueprint as tasks_bp
    app.register_blueprint(tasks_bp)
    from web_api.assets import blueprint as assets_bp
    app.register_blueprint(assets_bp)
    from web_api.shots import blueprint as shots_bp
    app.register_blueprint(shots_bp)
    from web_api.timeline import blueprint as timeline_bp
    app.register_blueprint(timeline_bp)
    from web_api.previews import blueprint as previews_bp
    app.register_blueprint(previews_bp)
    from web_api.exports import blueprint as exports_bp
    app.register_blueprint(exports_bp)

    @app.get("/api/projects/<name>/media/<path:subpath>")
    def media(name: str, subpath: str):
        import os as _os

        from web_api.projects import PROJECTS_ROOT
        root = _os.path.join(PROJECTS_ROOT, _os.path.basename(str(name)))
        target = _os.path.realpath(_os.path.join(root, subpath))
        if not target.startswith(_os.path.realpath(root) + _os.sep):
            return jsonify({"error": "非法路径"}), 404
        if not _os.path.isfile(target):
            return jsonify({"error": "文件不存在"}), 404
        extension = _os.path.splitext(target)[1].lower()
        mime = {
            ".mp4": "video/mp4", ".webm": "video/webm", ".mov": "video/quicktime",
            ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
            ".webp": "image/webp",
        }.get(extension)
        if mime is None:
            return jsonify({"error": "不支持的文件类型"}), 404
        from flask import send_file
        return send_file(target, mimetype=mime)

    return app
