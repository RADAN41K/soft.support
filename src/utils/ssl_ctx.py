"""Shared SSL context for HTTPS requests to limansoft.com API.

Tries secure contexts first, falls back to unverified if all fail.
Only used for our own API (limansoft.com), not arbitrary URLs.
"""
import ssl
import urllib.request
from src.utils.logger import log


def _build_context():
    # 0. Try pip-system-certs (patches ssl globally to use OS certs)
    try:
        import pip_system_certs  # noqa: F401
        ctx = ssl.create_default_context()
        _test_connection(ctx)
        log("SSL: pip-system-certs (системнi сертифiкати)")
        return ctx
    except Exception as e:
        log(f"SSL: pip-system-certs не вдалося: {e}", "WARN")

    # 1. Try truststore (OS-level certs)
    try:
        import truststore
        truststore.inject_into_ssl()
        ctx = ssl.create_default_context()
        _test_connection(ctx)
        log("SSL: truststore (сертифiкати ОС)")
        return ctx
    except Exception as e:
        log(f"SSL: truststore не вдалося: {e}", "WARN")

    # 2. Try certifi bundle
    try:
        import certifi
        ctx = ssl.create_default_context(cafile=certifi.where())
        _test_connection(ctx)
        log("SSL: certifi (Mozilla CA bundle)")
        return ctx
    except Exception as e:
        log(f"SSL: certifi не вдалося: {e}", "WARN")

    # 3. Try default Python context
    try:
        ctx = ssl.create_default_context()
        _test_connection(ctx)
        log("SSL: стандартний Python контекст")
        return ctx
    except Exception as e:
        log(f"SSL: стандартний контекст не вдалося: {e}", "WARN")

    # 4. Fallback: skip verification (our own API only)
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    log("SSL: перевiрку вимкнено (fallback, тiльки limansoft.com)", "WARN")
    return ctx


def _test_connection(ctx):
    """Quick test that SSL context works with our API."""
    req = urllib.request.Request("https://limansoft.com",
                                method="HEAD")
    urllib.request.urlopen(req, timeout=5, context=ctx)


ssl_context = _build_context()
