from __future__ import annotations

import threading
import webbrowser

import uvicorn


def open_ui() -> None:
    webbrowser.open("http://127.0.0.1:8000", new=2)


if __name__ == "__main__":
    threading.Timer(1.5, open_ui).start()
    uvicorn.run("scalper.api:app", host="127.0.0.1", port=8000, log_level="warning")
