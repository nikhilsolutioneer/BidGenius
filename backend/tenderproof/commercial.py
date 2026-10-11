"""Local, revisioned commercial evidence. Imported history never silently prices a bid."""
from __future__ import annotations

from copy import deepcopy
import csv
from datetime import date
from decimal import Decimal
import hashlib
import io
from pathlib import PurePosixPath
from statistics import median
from typing import Any

from pydantic import Field

from .models import Model, RevisionMutation
from .pricing import ZERO, calculate_scenarios, decimal_value, raw
from .storage import DomainError, now


class HistoricalPreview(Model):
    filename: str = Field(min_length=1, max_length=255)
    csv_text: str = Field(max_length=2_000_000)


class HistoricalImport(RevisionMutation, HistoricalPreview):
    pass


class CommercialPatch(RevisionMutation):
    changes: dict[str, Any]


class ScenarioSave(RevisionMutation):
    overrides: dict[str, Any] = Field(default_factory=dict)


def default_state() -> dict:
    return {"records": [], "imports": [], "context": {
        "selected_record_ids": [], "adopt_observed_win_rate": False,
        "adopt_reference_ratio": False, "adoption_rationale": "",
        "capacity": {"period_start": None, "period_end": None, "available_hours": None, "committed_hours": None},
        "scenario_overrides": {}, "comparable_snapshot": [],
    }}


def state(project: dict) -> dict:
    return deepcopy(project.get("commercial_state") or default_state())


def preview_history(project: dict, filename: str, csv_text: str) -> dict:
    """Validate the exact uploaded text. Duplicate records are skipped, conflicts block import."""
    digest = hashlib.sha256(csv_text.encode("utf-8")).hexdigest()
    result = {"filename": PurePosixPath(filename.replace("\\", "/")).name, "sha256": digest,
              "rows": [], "errors": [], "duplicates": [], "valid_count": 0, "can_import": False}
    if len(csv_text.encode("utf-8")) > 2_000_000:
        result["errors"].append({"row": 0, "message": "CSV exceeds the 2 MB limit."})
        return result
    required = {"record_id", "project_name", "currency", "bid_amount", "outcome"}
    optional = {"project_date", "scope_description", "estimated_baseline", "winning_price", "installation_hours"}
    reader = csv.DictReader(io.StringIO(csv_text.lstrip("\ufeff")))
    if not reader.fieldnames or not required <= set(reader.fieldnames):
        result["errors"].append({"row": 1, "message": "Required headers: " + ", ".join(sorted(required))})
        return result
    if len(reader.fieldnames) != len(set(reader.fieldnames)) or set(reader.fieldnames) - required - optional:
        result["errors"].append({"row": 1, "message": "Duplicate or unsupported CSV headers."})
        return result
    existing = {r["record_id"]: r for r in state(project)["records"]}
    known = deepcopy(existing)
    for index, source in enumerate(reader, start=2):
        if index > 5001:
            result["errors"].append({"row": index, "message": "CSV exceeds 5,000 records."})
            break
        try:
            if None in source or any(source.get(k) is None for k in required):
                raise ValueError("Row has an incorrect number of columns.")
            row = {key: (source.get(key) or "").strip() for key in sorted(required | optional)}
            if any(not row[k] for k in required):
                raise ValueError("All required fields must be populated.")
            if any(len(value) > 2000 for value in row.values()):
                raise ValueError("A field exceeds 2,000 characters.")
            row["currency"] = row["currency"].upper()
            if len(row["currency"]) != 3 or not row["currency"].isalpha():
                raise ValueError("Currency must be a three-letter code; only CHF is comparable.")
            row["outcome"] = row["outcome"].lower()
            if row["outcome"] not in ("won", "lost", "unknown"):
                raise ValueError("Outcome must be won, lost, or unknown.")
            for key in ("bid_amount", "estimated_baseline", "winning_price", "installation_hours"):
                row[key] = raw(decimal_value(row[key], key, positive=True)) if row[key] else None
            if row["project_date"]:
                date.fromisoformat(row["project_date"])
            else:
                row["project_date"] = None
            old = known.get(row["record_id"])
            if old:
                if any(old.get(k) != row.get(k) for k in row):
                    raise ValueError(f"Record ID {row['record_id']} already exists with different values.")
                result["duplicates"].append({"row": index, "record_id": row["record_id"]})
                continue
            known[row["record_id"]] = row
            result["rows"].append({**row, "comparable": row["currency"] == "CHF", "source_row": index})
        except (ValueError, TypeError) as exc:
            result["errors"].append({"row": index, "message": str(exc)})
    result["valid_count"] = len(result["rows"])
    result["can_import"] = bool(result["rows"]) and not result["errors"]
    return result


def statistics(records: list[dict], selected: list[str]) -> dict:
    rows = [r for r in records if r["record_id"] in selected]
    eligible = [r for r in rows if r["currency"] == "CHF"]
    wins = sum(r["outcome"] == "won" for r in eligible)
    losses = sum(r["outcome"] == "lost" for r in eligible)
    ratios = [Decimal(r["bid_amount"]) / Decimal(r["estimated_baseline"]) for r in eligible if r.get("estimated_baseline")]
    return {"selected_count": len(rows), "eligible_count": len(eligible), "wins": wins, "losses": losses,
            "unknown": sum(r["outcome"] == "unknown" for r in eligible),
            "observed_win_rate": raw(Decimal(wins) / (wins + losses)) if wins + losses else None,
            "median_bid_to_baseline_ratio": raw(median(ratios)) if ratios else None,
            "ratio_sample_size": len(ratios), "outcome_sample_size": wins + losses}


def capacity_view(project: dict, capacity: dict) -> dict:
    positions = [p for p in project.get("positions", []) if p.get("status") not in ("non_priceable", "out_of_scope") and p.get("pricing_basis") != "included_elsewhere"]
    hours = [(p.get("cost") or {}).get("unrounded_hours") for p in positions]
    required = sum((Decimal(h) for h in hours if h is not None), ZERO)
    available, committed = capacity.get("available_hours"), capacity.get("committed_hours")
    remaining = Decimal(available) - Decimal(committed) if available is not None and committed is not None else None
    return {"known_required_hours": raw(required), "remaining_hours": raw(remaining) if remaining is not None else None,
            "shortfall_hours": raw(max(ZERO, required - remaining)) if remaining is not None else None,
            "labour_incomplete": any(h is None for h in hours), "unknown_labour_positions": sum(h is None for h in hours),
            "period_start": capacity.get("period_start"), "period_end": capacity.get("period_end"),
            "notice": "Known included-scope labour; estimator must confirm alignment with the capacity period. No automatic probability adjustment."}


def apply_commercial(project: dict) -> None:
    """Called after every calculation, so saved assumptions survive subsequent revisions."""
    current = state(project)
    context = current["context"]
    overrides = deepcopy(context["scenario_overrides"])
    validate_overrides(overrides)
    stats = statistics(current["records"], context["selected_record_ids"])
    if context["adopt_observed_win_rate"]:
        if stats["observed_win_rate"] is None:
            raise DomainError("Selected CHF history has no known outcomes to adopt.")
        overrides["reference_win_probability"] = stats["observed_win_rate"]
    if context["adopt_reference_ratio"]:
        if stats["median_bid_to_baseline_ratio"] is None:
            raise DomainError("Selected CHF history has no bid/baseline ratios to adopt.")
        overrides["reference_price_multiplier"] = stats["median_bid_to_baseline_ratio"]
    estimate = project.get("estimate", {})
    totals = estimate.get("totals", {})
    if totals.get("cost_baseline_chf") is None:
        return
    scenarios = calculate_scenarios(totals.get("unrounded_cost_baseline_chf", totals["cost_baseline_chf"]), project["parameters"], overrides)
    scenarios["recommendation_label"] = "Recommended bid range for included scope"
    scenarios["commercial_evidence"] = {"statistics": stats, "context": deepcopy(context),
        "capacity": capacity_view(project, context["capacity"]),
        "notice": "Selected historical observations are descriptive, not calibrated predictions. Non-CHF records are excluded."}
    estimate["scenarios"] = scenarios


def commercial_view(project: dict) -> dict:
    current = state(project)
    return {"revision": project["revision"], **current,
        "statistics": statistics(current["records"], current["context"]["selected_record_ids"]),
        "capacity": capacity_view(project, current["context"]["capacity"]),
        "scenarios": deepcopy(project.get("estimate", {}).get("scenarios", {}))}


def import_history(service, project_id: str, request: HistoricalImport) -> dict:
    def apply(project):
        before = state(project)
        preview = preview_history(project, request.filename, request.csv_text)
        if not preview["can_import"]:
            raise DomainError("Historical import requires valid new rows.", 422, detail=preview)
        current = deepcopy(before)
        imported_at = now()
        source = {"filename": preview["filename"], "sha256": preview["sha256"], "imported_at": imported_at,
                  "row_count": preview["valid_count"], "csv_text": request.csv_text}
        current["imports"].append(source)
        current["records"].extend({**row, "source_filename": source["filename"], "source_sha256": source["sha256"], "imported_at": imported_at} for row in preview["rows"])
        project["commercial_state"] = current
        return "commercial", project_id, before, deepcopy(current), {"imported_count": preview["valid_count"], "duplicates": preview["duplicates"]}
    return service.mutate(project_id, request.expected_revision, request.reason, apply)


SCENARIO_KEYS = {"scenario_margins_pct", "reference_margin_pct", "reference_win_probability",
    "price_sensitivity_probability_points_per_1pct_price", "strategic_appetite_adjustment", "competition_adjustment",
    "minimum_probability", "maximum_probability"}


def validate_overrides(overrides: dict) -> None:
    if not isinstance(overrides, dict) or set(overrides) - SCENARIO_KEYS:
        raise DomainError("Unsupported scenario assumption.")
    for key, value in overrides.items():
        if key == "scenario_margins_pct":
            if not isinstance(value, dict) or not value or any(not isinstance(name, str) or not name.strip() for name in value):
                raise DomainError("Scenario margins must be a non-empty named object.")
            for name, margin in value.items():
                if decimal_value(margin, name, minimum=ZERO) >= 100:
                    raise DomainError("Scenario margins must be below 100 percent.")
        else:
            decimal_value(value, key)


def patch_commercial(service, project_id: str, request: CommercialPatch) -> dict:
    def apply(project):
        before = state(project)
        current = deepcopy(before)
        context = current["context"]
        allowed = set(context) - {"comparable_snapshot"}
        if set(request.changes) - allowed:
            raise DomainError("Unsupported commercial-context field.")
        for key, value in request.changes.items():
            if key in ("capacity", "scenario_overrides"):
                if not isinstance(value, dict):
                    raise DomainError(f"{key} must be an object.")
                context[key].update(value)
            else:
                context[key] = value
        selected = context["selected_record_ids"]
        if not isinstance(selected, list) or any(not isinstance(i, str) for i in selected) or len(set(selected)) != len(selected):
            raise DomainError("Select unique historical record IDs.")
        by_id = {r["record_id"]: r for r in current["records"]}
        if any(i not in by_id for i in selected):
            raise DomainError("A selected historical record does not exist.")
        for key in ("adopt_observed_win_rate", "adopt_reference_ratio"):
            if not isinstance(context[key], bool):
                raise DomainError(f"{key} must be true or false.")
        rationale = context["adoption_rationale"]
        if not isinstance(rationale, str) or len(rationale) > 2000:
            raise DomainError("Historical adoption rationale must be text of at most 2,000 characters.")
        if (context["adopt_observed_win_rate"] or context["adopt_reference_ratio"]) and len(rationale.strip()) < 3:
            raise DomainError("Explicit historical adoption requires a rationale.")
        capacity = context["capacity"]
        if set(capacity) - {"period_start", "period_end", "available_hours", "committed_hours"}:
            raise DomainError("Unsupported capacity field.")
        for key in ("available_hours", "committed_hours"):
            if capacity.get(key) not in (None, ""):
                capacity[key] = raw(decimal_value(capacity[key], key, minimum=ZERO))
            else:
                capacity[key] = None
        for key in ("period_start", "period_end"):
            if capacity.get(key) is not None and not isinstance(capacity[key], str):
                raise DomainError("Capacity period dates must use YYYY-MM-DD text.")
            capacity[key] = date.fromisoformat(capacity[key]).isoformat() if capacity.get(key) else None
        if bool(capacity.get("period_start")) != bool(capacity.get("period_end")):
            raise DomainError("Specify both capacity period dates.")
        if capacity.get("period_start") and capacity["period_start"] > capacity["period_end"]:
            raise DomainError("Capacity period end must follow its start.")
        if any(capacity.get(k) is not None for k in ("available_hours", "committed_hours")) and not capacity.get("period_start"):
            raise DomainError("Specify the period for available and committed capacity.")
        validate_overrides(context["scenario_overrides"])
        context["comparable_snapshot"] = [deepcopy(by_id[i]) for i in selected]
        project["commercial_state"] = current
        # Validate adoption and the scenario calculator inside the transaction.
        apply_commercial(project)
        return "commercial", project_id, before, deepcopy(current), {}
    return service.mutate(project_id, request.expected_revision, request.reason, apply)
