from __future__ import annotations

import argparse
import logging

import uvicorn

from nexuscam.api.app import build
from nexuscam.logging_setup import configure_logging
from nexuscam.settings import AppSettings


def main() -> None:
    parser = argparse.ArgumentParser(prog="nexuscam", description="NexusCam control plane")
    parser.add_argument("--config", default="config/default.yaml")
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--source", default=None, help="demo | usb | rtsp | http | phone | URL")
    parser.add_argument("--download-models", action="store_true")
    args = parser.parse_args()

    configure_logging(logging.INFO)
    settings = AppSettings.load(args.config)
    if args.host:
        settings.server.host = args.host
    if args.port:
        settings.server.port = args.port
    if args.source:
        settings.capture.backend = args.source
        if "://" in args.source:
            settings.capture.rtsp_url = args.source
            settings.capture.backend = "rtsp" if args.source.startswith("rtsp") else "http"
    if args.download_models:
        from nexuscam.vision.weights import ensure_ssd

        ensure_ssd(download=True)

    app, _runtime = build(settings)
    uvicorn.run(app, host=settings.server.host, port=settings.server.port, log_level="info")


if __name__ == "__main__":
    main()
