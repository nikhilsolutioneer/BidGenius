"""Read-only project diagnostic; provider results never alter the active run."""
import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from tenderproof import ai
from tenderproof.config import model_name
from tenderproof.models import PageRecord, SourceSpan


async def main():
    first, last = map(int, sys.argv[1:3])
    report = json.loads((ROOT / "artifacts/live-ai-verification.json").read_text(encoding="utf-8"))
    with sqlite3.connect((ROOT / "data/tenderproof.sqlite").as_uri() + "?mode=ro", uri=True) as db:
        project = json.loads(db.execute("SELECT data FROM projects WHERE id=?", (report["project_id"],)).fetchone()[0])
        args = (project["document"]["id"], first, last)
        pages = [PageRecord.model_validate_json(row[0]) for row in db.execute("SELECT data FROM pages WHERE document_id=? AND page BETWEEN ? AND ? ORDER BY page", args)]
        spans = [SourceSpan.model_validate_json(row[0]) for row in db.execute("SELECT data FROM source_spans WHERE document_id=? AND page BETWEEN ? AND ? ORDER BY page", args)]
    observations = []
    validate = ai.validate_ai_output
    def capture(*args):
        try:
            return validate(*args)
        except ValueError as exc:
            observations.append(str(exc)[:300])
            raise
    ai.validate_ai_output = capture
    result = {"pages": [first, last], "diagnosed_at": datetime.now(timezone.utc).isoformat(),
              "mode": "Independent repeated model request; active project and run unchanged"}
    try:
        batch = await ai.extract_ai_batch(pages, spans, project["catalog"], model_name())
        result.update(status="validated", usage=batch.usage, positions=len(batch.positions))
    except Exception as exc:
        result.update(status="failed", error_type=type(exc).__name__, usage=getattr(exc, "usage", {}))
    result["validation_observations"] = observations
    (ROOT / "artifacts" / f"ai-diagnostic-{first}-{last}.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
