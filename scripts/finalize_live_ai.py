"""Persist the final live-run snapshot without exposing credentials."""
from datetime import datetime, timezone
import json
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
run_id = "run_f06fcfffe69d4221"
with urllib.request.urlopen(f"http://127.0.0.1:8000/api/runs/{run_id}", timeout=60) as response:
    run = json.load(response)
path = ROOT / "artifacts" / "live-ai-verification.json"
report = json.loads(path.read_text(encoding="utf-8"))
report["run"] = run
report["completed_snapshot_at"] = datetime.now(timezone.utc).isoformat()
report["accounting_note"] = (
    "Run usage is the server counter. Add pre_restart_known_usage_not_in_run_counter "
    "and the separately recorded diagnostic request when reconciling provider billing."
)
path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
print(json.dumps({"status": run["status"], "pages": run["pages_processed"], "positions": run["positions_found"], "errors": len(run["errors"])}, indent=2))
