"""HTTP response header constants shared by views and static serving."""

from __future__ import annotations

# The built React app only needs its own origin. There are no inline scripts,
# external fonts or third-party embeds; inline styles cover React's style
# attribute support. This also applies inside the Electron shell because the
# page is loaded from the server.
CONTENT_SECURITY_POLICY = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; "
    "font-src 'self'; "
    "connect-src 'self'; "
    "object-src 'none'; "
    "base-uri 'self'; "
    "form-action 'self'; "
    "frame-ancestors 'none'"
)
