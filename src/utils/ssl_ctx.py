"""Shared SSL context that works even when system CA certs are missing.

Strategy (in order):
1. truststore — injects OS-level CA store (Windows/macOS/Linux)
2. certifi — bundled Mozilla CA certs
3. Default Python ssl context
"""
import ssl


def _build_context():
    ctx = ssl.create_default_context()

    # Try truststore first — uses Windows cert store like browsers do
    try:
        import truststore
        truststore.inject_into_ssl()
        return ctx
    except (ImportError, Exception):
        pass

    # Fallback to certifi bundle
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        pass

    return ctx


ssl_context = _build_context()
