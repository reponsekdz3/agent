from __future__ import annotations

import logging
import threading
import time
from typing import Any

import requests

log = logging.getLogger(__name__)


class OnlineEnricher:
    """Optional enrichment module that queries the internet for non-sensitive
    public information about detected labels. This module respects the
    `allow_online_enrichment` flag in settings and must be used with care.
    """

    def __init__(self, settings) -> None:
        self.settings = settings
        self._stop = threading.Event()

    def enrich(self, label: str) -> dict[str, Any] | None:
        if not getattr(self.settings.vision, "allow_online_enrichment", False):
            return None
        try:
            # minimal example: use Wikipedia REST to fetch a summary for the label
            url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{label}"
            r = requests.get(url, timeout=2.0)
            if r.status_code != 200:
                return None
            data = r.json()
            return {"title": data.get("title"), "desc": data.get("extract"), "source": data.get("content_urls", {}).get("desktop", {}).get("page")}
        except Exception:
            log.debug("Online enrichment failed for %s", label)
            return None
