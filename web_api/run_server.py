"""Web API 服务入口：python -m web_api.run_server [--port 8787]"""
from __future__ import annotations

import argparse

from core.paths import configure_ffmpeg_environment


def main() -> None:
    parser = argparse.ArgumentParser(description="AIGC Pipeline Web API")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    configure_ffmpeg_environment()
    from web_api.app import create_app
    app = create_app()
    print(f"Web API 启动: http://{args.host}:{args.port}")
    app.run(host=args.host, port=args.port, debug=args.debug, threaded=True)


if __name__ == "__main__":
    main()
