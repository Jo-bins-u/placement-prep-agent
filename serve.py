"""Production server (works on Windows and Linux) - use this instead of `python app.py`
when anyone other than you will use the app.

    python serve.py                      # http://127.0.0.1:8000, 8 threads

Put it behind a TLS reverse proxy (e.g. Caddy or nginx) for HTTPS and set in .env:
    PREPWISE_HTTPS=1          # Secure cookies + HSTS
    PREPWISE_TRUST_PROXY=1    # real client IPs for rate limiting (only behind one trusted proxy)
Environment: HOST (default 127.0.0.1), PORT (default 8000), THREADS (default 8).
"""

import os

from waitress import serve

from app import app

if __name__ == "__main__":
    if os.getenv("FLASK_DEBUG") == "1":
        raise SystemExit("FLASK_DEBUG=1 is for local development only - unset it before serving.")
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8000"))
    print(f"Prepwise serving on http://{host}:{port} (waitress)")
    serve(app, host=host, port=port, threads=int(os.getenv("THREADS", "8")),
          ident="Prepwise",            # don't advertise the server software/version
          max_request_body_size=6 * 1024 * 1024,
          clear_untrusted_proxy_headers=True)
