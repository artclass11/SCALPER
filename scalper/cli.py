"""Local server entry point."""

from __future__ import annotations

import argparse
import os


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the SCALPER local-first API and web UI.")
    parser.add_argument("--host", default=os.getenv("SCALPER_HOST", "127.0.0.1"))
    parser.add_argument("--port", default=int(os.getenv("SCALPER_PORT", "8000")), type=int)
    args = parser.parse_args()
    token = os.getenv("SCALPER_API_TOKEN", "").strip()
    if args.host not in {"127.0.0.1", "::1", "localhost"} and len(token) < 32:
        parser.error("Non-loopback binds require a SCALPER_API_TOKEN of at least 32 characters and a secure gateway.")
    if not 1 <= args.port <= 65535:
        parser.error("Port must be between 1 and 65535.")
    import uvicorn
    uvicorn.run("scalper.api:app", host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
