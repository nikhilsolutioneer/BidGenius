"""Verify configured model access without sending any project content."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from tenderproof.config import ai_configured, model_name
from openai import OpenAI

if not ai_configured():
    raise SystemExit("OPENAI_API_KEY is not configured. Add it to .env; local parsing remains available.")
try:
    model = OpenAI(timeout=20, max_retries=1).models.retrieve(model_name())
    print(f"Model access verified: {model.id}. No document content was sent.")
except Exception as exc:
    raise SystemExit(f"Model access check failed ({type(exc).__name__}). Check your account, key, and OPENAI_MODEL; credentials were not printed.")
