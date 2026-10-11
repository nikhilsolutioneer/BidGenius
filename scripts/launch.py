"""Native local launcher: optional numeric port, no cloud infrastructure."""
from pathlib import Path
import os
import socket
import sys
import threading
import urllib.request
import webbrowser

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from dotenv import load_dotenv
load_dotenv(ROOT / ".env")
os.chdir(ROOT)
try:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else int(os.getenv("TENDERPROOF_PORT", "8000"))
    if not 1024 <= port <= 65535:
        raise ValueError()
except ValueError:
    raise SystemExit("Use start.cmd [port], for example start.cmd 8001.")
with socket.socket() as probe:
    try:
        probe.bind(("127.0.0.1", port))
    except OSError:
        raise SystemExit(f"Port {port} is already in use. Keep the existing app running and use: start.cmd {port + 1}")


def open_browser():
    import time
    for _ in range(30):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=1):
                webbrowser.open(f"http://127.0.0.1:{port}")
                return
        except OSError:
            time.sleep(.5)


print(f"TenderProof: http://127.0.0.1:{port} | Ctrl+C stops the app. Data stays on this laptop.")
threading.Thread(target=open_browser, daemon=True).start()
import uvicorn
uvicorn.run("tenderproof.main:app", host="127.0.0.1", port=port, log_level="info")
