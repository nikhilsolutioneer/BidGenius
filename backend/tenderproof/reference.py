"""Read production references. Evaluation fixtures are deliberately excluded."""
from __future__ import annotations

import csv
import json
from pathlib import Path

from .duct_rules import DUCT_DEFAULTS


def load_reference(package: Path) -> dict:
    package = Path(package)
    result = {}
    for filename, key, identity in (
        ("catalog.csv", "catalog", "product_id"),
        ("productivity.csv", "productivity", "install_code"),
    ):
        path = package / filename
        if not path.is_file():
            raise ValueError(f"Missing reference file: {filename}")
        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if identity not in (reader.fieldnames or []):
                raise ValueError(f"{filename} is missing {identity}")
            rows = [{str(k): (v or "").strip() for k, v in row.items() if k is not None} for row in reader]
        identifiers = [row[identity] for row in rows]
        if any(not value for value in identifiers) or len(set(identifiers)) != len(identifiers):
            raise ValueError(f"{filename} contains missing or duplicate identifiers")
        result[key] = rows
    path = package / "project_parameters.json"
    if not path.is_file():
        raise ValueError("Missing reference file: project_parameters.json")
    # Preserve decimal spelling rather than passing through binary floats.
    with path.open(encoding="utf-8-sig") as handle:
        parameters = json.load(handle, parse_float=str, parse_constant=lambda x: (_ for _ in ()).throw(ValueError(f"Invalid number: {x}")))
    if not isinstance(parameters, dict):
        raise ValueError("Project parameters must be an object")
    parameters.setdefault("duct_pricing", dict(DUCT_DEFAULTS))
    result["parameters"] = parameters
    return result


def assign_position_references(positions: list[dict]) -> list[dict]:
    """Derive human-readable estimator reference '<system> · p.<page> · #<n>'

    where n is the 1-based order of position appearance on that page in tender order.
    Also appends tender line/item number if present.
    """
    page_counters: dict[int, int] = {}
    for p in positions:
        page = p.get("source_page", 0)
        page_counters[page] = page_counters.get(page, 0) + 1
        n = page_counters[page]
        system = p.get("system") or "Unassigned"
        line_num = p.get("tender_line_number")
        if line_num:
            ref = f"{system} · p.{page} · #{n} (line {line_num})"
        else:
            ref = f"{system} · p.{page} · #{n}"
        p["reference"] = ref
    return positions


def fold_continuation_pages(positions: list[dict], spans: list[dict] | None = None) -> list[dict]:
    """Fold PKG-CONT-* continuation positions into parent package positions as additional evidence."""
    by_id = {p["id"]: p for p in positions}
    conts = [p for p in positions if p.get("id", "").startswith("PKG-CONT-")]
    
    # If spans are provided, we can also extract continuation spans directly
    if spans:
        pkg_spans = [s for s in spans if s.get("kind", "").startswith("package:")]
        for s in pkg_spans:
            owner = s.get("kind", "").split(":", 1)[1]
            parent = by_id.get(owner)
            if parent:
                parent_spans = parent.setdefault("source_span_ids", [])
                if s["id"] not in parent_spans:
                    parent_spans.append(s["id"])
                attrs = parent.setdefault("attributes", {})
                pages = attrs.setdefault("package_source_pages", [parent["source_page"]])
                if s["page"] not in pages:
                    pages.append(s["page"])
                field_sources = parent.setdefault("field_sources", {})
                spec_pages = field_sources.setdefault("specification_pages", [])
                if s["id"] not in spec_pages:
                    spec_pages.append(s["id"])

    # Also fold any explicit PKG-CONT positions
    for cont in conts:
        owner = cont.get("included_in")
        parent = by_id.get(owner) if owner else None
        if parent:
            for s_id in cont.get("source_span_ids", []):
                if s_id not in parent["source_span_ids"]:
                    parent["source_span_ids"].append(s_id)
            attrs = parent.setdefault("attributes", {})
            pages = attrs.setdefault("package_source_pages", [parent["source_page"]])
            if cont["source_page"] not in pages:
                pages.append(cont["source_page"])
            field_sources = parent.setdefault("field_sources", {})
            spec_pages = field_sources.setdefault("specification_pages", [])
            for s_id in cont.get("source_span_ids", []):
                if s_id not in spec_pages:
                    spec_pages.append(s_id)

    # Format specification span text on package parents
    for p in positions:
        pages = sorted(set(p.get("attributes", {}).get("package_source_pages", [])))
        if len(pages) > 1:
            p["attributes"]["specification_span_text"] = f"Specification spans pages {pages[0]}–{pages[-1]}"
            p["attributes"]["package_source_pages"] = pages

    # Return positions excluding any PKG-CONT continuation rows
    remaining = [p for p in positions if not p.get("id", "").startswith("PKG-CONT-")]
    return assign_position_references(remaining)

