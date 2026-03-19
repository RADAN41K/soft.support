"""Shared SSL context that works even when system CA certs are missing."""
import ssl

try:
    import certifi
    ssl_context = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    ssl_context = ssl.create_default_context()
