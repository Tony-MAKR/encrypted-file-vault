"""Cache policy for the built frontend served by WhiteNoise.

The Vite build emits content-hashed files under ``assets/``; those can be
cached forever. Everything else (favicon, legacy files) gets a short cache so
a new build is picked up quickly. ``index.html`` is never cached because it
points at the current asset hashes.
"""

from __future__ import annotations

from wsgiref.headers import Headers

from apps.core.headers import CONTENT_SECURITY_POLICY


def add_static_headers(headers: Headers, path: str, url: str) -> None:
    del path  # Only the public URL matters for the cache policy.
    if url.endswith("index.html") or url == "/":
        headers["Cache-Control"] = "no-store"
    elif "/assets/" in url:
        headers["Cache-Control"] = "public, max-age=31536000, immutable"
    else:
        headers["Cache-Control"] = "public, max-age=3600"

    # WhiteNoise responses bypass Django middleware, so add the same policy
    # here for any HTML file it may serve directly.
    if url.endswith((".html", "/")):
        headers["Content-Security-Policy"] = CONTENT_SECURITY_POLICY
        headers["X-Content-Type-Options"] = "nosniff"
        headers["Referrer-Policy"] = "same-origin"
        headers["X-Frame-Options"] = "DENY"
