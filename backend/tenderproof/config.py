from __future__ import annotations

import os
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")
STARTER = ROOT / "Schulhaus_Oberglatt_Hackathon_Starter_Package_v2"


def data_directory() -> Path:
    path = Path(os.environ.get("TENDERPROOF_DATA_DIR", "data"))
    return path if path.is_absolute() else ROOT / path


def model_name() -> str:
    return os.environ.get("OPENAI_MODEL", "gpt-4o")


def ai_configured() -> bool:
    return bool(os.environ.get("OPENAI_API_KEY", "").strip())
