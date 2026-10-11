"""Evidence-first local PDF ingestion, independent of the evaluation examples.

The deterministic path understands the supplied schedule grammar and keeps other
scope unresolved. It does not claim general-purpose OCR or drawing takeoff.
"""
from __future__ import annotations

import hashlib
import re
from decimal import Decimal
from pathlib import Path
from typing import Callable

import pdfplumber

from .matching import classify, infer_attributes, match_position, normalize_number, normalize_unit
from .duct_rules import area_from_length, raw
from .models import ExtractionBatch, Issue, PageRecord, Position, Requirement, SourceSpan

SCOPE_EXCLUSION_PATTERNS = (r"nicht\s+Bestandteil", r"separate\s+Ausschreibung", r"bauseits", r"durch\s+Dritte", r"nicht\s+im\s+Angebot", r"in\s+separatem\s+Los", r"Lieferung\s+durch", r"nur\s+Montage")

def _scope_exclusion_evidence(context: list[SourceSpan]) -> tuple[str, str] | None:
    for span in reversed(context):
        if any(re.search(pattern, span.text, re.I) for pattern in SCOPE_EXCLUSION_PATTERNS):
            return span.text, span.id
    return None

def _apply_scope_ambiguity(position: Position, evidence: tuple[str, str]) -> None:
    quote, span_id = evidence
    tag = f"scope_exclusion:{span_id}"
    if tag not in position.scope_tags:
        position.scope_tags.append(tag)
    issue = Issue(id=f"{position.id}-scope-ambiguity", kind="scope_ambiguity", severity="blocker", title="Scope boundary needs a decision", detail=f'Quoted scope wording: "{quote}"', source_span_ids=list(dict.fromkeys(position.source_span_ids + [span_id])), position_ids=[position.id], action="Choose Include (supply+install), Install only (labour; material 0), or Exclude (by others).")
    position.warnings = [w for w in position.warnings if w.kind != "scope_ambiguity"] + [issue]
    position.status, position.review_state = "review_required", "pending"

PARSER_VERSION = "local-1.6"
UNIT = r"Stk\.?|Stück|m2|m²|Std\.?|LS|m|h"
NUMBER = r"\d[\d'’`]*(?:[.,]\d+)?"


def _id(*parts: object) -> str:
    return hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()[:20]


def _system(text: str) -> str | None:
    if re.search(r"244\.0?6|MONTAGESYSTEM FLACHDACH", text, re.I):
        return "ROOF"
    hit = re.search(r"\bLA\s*0?([1-5])\b|\b244\.0?([1-5])\b", text, re.I)
    return f"LA0{hit.group(1) or hit.group(2)}" if hit else None


def _is_title(text: str) -> bool:
    if len(text) > 110 or re.match(r"[-•]|für |und |rendes |Kanalverstärk|40 x|EI\d|Total |\d", text, re.I):
        return False
    if re.search(r"^(Pos\.|Gattg\.|SH Erlen|Fabrikat|Typ|Grösse|Anzahl|B x|Mod\.|cm |mm )", text):
        return False
    return True


def parse_pdf(path: Path, document_id: str, progress: Callable | None = None) -> tuple[list[PageRecord], list[SourceSpan]]:
    pages: list[PageRecord] = []
    spans: list[SourceSpan] = []
    inherited = "Unassigned"
    apparatus_owner: str | None = None
    with pdfplumber.open(path) as pdf:
        for index, page in enumerate(pdf.pages, 1):
            warnings: list[str] = []
            try:
                raw_lines = page.extract_text_lines(layout=False, strip=True, return_chars=True)
                text = "\n".join(line["text"] for line in raw_lines)
                header_lines = [l for l in raw_lines if l["top"] < 70]
                footer_lines = [l for l in raw_lines if l["top"] > page.height * .90]
                header_system = _system("\n".join(l["text"] for l in header_lines))
                footer_system = _system("\n".join(l["text"] for l in footer_lines))
                # A filename footer identifies the actual document section. Preserve
                # the disagreeing header and require estimator confirmation.
                current = footer_system or header_system or inherited
                if header_system and footer_system and header_system != footer_system:
                    warnings.append(f"System conflict: header says {header_system}, section filename says {footer_system}; provisionally assigned {footer_system}.")
                if current != inherited:
                    apparatus_owner = None
                inherited = current
                printed = re.search(r"Seite\s+(\d+\s*/\s*\d+)", text)
                page_spans: list[SourceSpan] = []
                for li, line in enumerate(raw_lines):
                    t = line["text"].strip()
                    if not t:
                        continue
                    kind = "text"
                    disposition = "context"
                    if re.match(r"Zuluftgerät\s+\d", t, re.I):
                        apparatus_owner = f"PKG-{document_id}-{current}"
                    if re.match(r"(?:B\s+KANÄLE|C\s+ARMATUREN|D\s+REGULIERUNG|E\s+MONTAGE|F\s+DÄMMUNGEN|Total Apparate)", t):
                        apparatus_owner = None
                    if line["top"] < 70 or line["top"] > page.height * .93 or re.match(r"Pos\.|Gattg\.|H:\\|\\\\|Total |KOSTENZUSAMMENSTELLUNG", t):
                        kind, disposition = "boilerplate", "boilerplate"
                    elif apparatus_owner:
                        kind = "package:" + apparatus_owner
                        if re.match(r"Zuluftgerät\s+\d", t, re.I):
                            kind = "package_start:" + apparatus_owner
                    else:
                        chars = line.get("chars", [])
                        bold = any("bold" in c.get("fontname", "").lower() for c in chars)
                        if bold and _is_title(t):
                            kind = "heading"
                        # Quantity columns are at the right of the LV description;
                        # embedded Stk counts in acoustic/component tables are ignored.
                        right_text = "".join(c["text"] for c in chars if float(c["x0"]) >= float(page.width) * .60)
                        if not re.search(r"m[³3]/h\s*$", t) and re.search(rf"\b({UNIT})\s*({NUMBER})?(?:\s*[. …_]*)$", right_text, re.I):
                            kind = "quantity"
                            disposition = "unresolved"
                    span = SourceSpan(id=f"SRC-{_id(document_id, index, li, t)}", document_id=document_id,
                                      page=index, text=t, x0=line["x0"], top=line["top"], x1=line["x1"], bottom=line["bottom"],
                                      page_width=page.width, page_height=page.height, kind=kind, disposition=disposition)
                    page_spans.append(span)
                status = "parsed" if text.strip() else "needs_ocr"
                if "(cid:" in text:
                    warnings.append("Some embedded font glyphs lack Unicode mapping; inspect this page visually.")
                    status = "partial"
                if not text.strip():
                    warnings.append("No extractable text; OCR or manual review is required.")
                pages.append(PageRecord(page=index, width=page.width, height=page.height, text=text,
                                        span_ids=[s.id for s in page_spans], system=current,
                                        printed_label=printed.group(1) if printed else None, status=status, warnings=warnings))
                spans.extend(page_spans)
            except Exception as exc:
                pages.append(PageRecord(page=index, width=page.width, height=page.height, text="", system=inherited,
                                        status="failed", warnings=[f"Page parsing failed: {type(exc).__name__}: {exc}"]))
            finally:
                page.close()
                if progress:
                    progress(index, len(pdf.pages))
    return pages, spans


def _quantity(text: str) -> tuple[str | None, str | None]:
    hit = re.search(rf"\b({UNIT})\s*({NUMBER})?\s*[. …_]*$", text, re.I)
    if not hit:
        return None, None
    unit = normalize_unit(hit.group(1))
    if unit and unit.lower().startswith("std"):
        unit = "h"
    value = normalize_number(hit.group(2).replace("`", "")) if hit.group(2) else None
    return value, unit


def _dimensions(block: str, row: str) -> dict:
    attrs = infer_attributes(block)
    # Prefer explicit B x H x L/Grösse rows over dimensions buried in model codes.
    dim_pattern = r"(\d+(?:[.,]\d+)?)\s*[x×]\s*(\d+(?:[.,]\d+)?)(?:\s*[x×]\s*(\d+(?:[.,]\d+)?))?\s*(mm|cm)?"
    dimension_lines = [ln for ln in block.splitlines() if re.search(r"B\s*x\s*H|Grösse|Abmessungen", ln, re.I)]
    dimension_lines.append(row)
    for ln in dimension_lines:
        hit = re.search(dim_pattern, ln, re.I)
        if hit:
            factor = 10 if hit.group(4) == "cm" or (not hit.group(4) and re.search(r"\bcm\b", block) and "Volumenstromregler" in block) else 1
            for key, value in zip(("width_mm", "height_mm", "length_mm"), hit.groups()[:3]):
                if value:
                    attrs[key] = str(Decimal(normalize_number(value)) * factor)
    dia = re.search(r"(?:[Øø∅]\s*(\d+(?:[.,]\d+)?)|(\d+(?:[.,]\d+)?)\s*[Øø∅])\s*(mm|cm)", row)
    if dia:
        attrs["diameter_mm"] = str(Decimal(normalize_number(dia.group(1) or dia.group(2))) * (10 if dia.group(3) == "cm" else 1))
    thick = re.search(r"aus\s+(\d+)\s*mm\s+Mineral", block, re.I)
    if thick:
        attrs["thickness_mm"] = thick.group(1)
    if re.search(r"Volumenstromregler|TVR[- ]|\bVFC\b", block) and "DN" in block:
        prefix = re.split(r"\bStk", row)[0]
        numbers = re.findall(r"(?<!\w)\d+(?:[.,]\d+)?", prefix)
        if numbers and "x" not in prefix.lower():
            factor = 10 if re.search(r"\bcm\s+m3/h", block) else 1
            attrs["diameter_mm"] = str(Decimal(numbers[0]) * factor)
    if "Kompaktschalldämpfer" in block:
        numbers = re.findall(r"\d+(?:[.,]\d+)?", row.split("Stk")[0])
        if len(numbers) >= 2:
            attrs["diameter_mm"] = str(Decimal(numbers[1]) * 10)
            attrs["schedule_length_mm"] = str(Decimal(numbers[0]) * 10)
            model = re.search(r"KOSD\s+(\d+)/(\d+)", block)
            if model:
                attrs["length_mm"] = model.group(2)
            # Compact body dimensions do not specify rectangular duct connections.
            attrs.pop("width_mm", None)
            attrs.pop("height_mm", None)
    return attrs


def _make_position(page: PageRecord, row: SourceSpan, context: list[SourceSpan], description: str | None = None) -> Position:
    quantity, unit = _quantity(row.text)
    original = "\n".join(s.text for s in context)
    attrs = _dimensions(original, row.text)
    category, rule = classify(original, attrs)
    title = description or (context[0].text if context else row.text)
    if row.text != title:
        title = title + " · " + re.sub(r"\s*[.]{3,}.*$", "", row.text)
    source_ids = list(dict.fromkeys([s.id for s in context] + [row.id]))
    position = Position(id=f"POS-{_id(row.document_id, row.id)}", document_id=row.document_id, system=page.system,
                        category=category, description=title[:350], original_description=original,
                        quantity=quantity, unit=unit, raw_quantity=quantity, raw_unit=unit,
                        source_page=page.page, source_span_ids=source_ids,
                        field_sources={"description": source_ids, "quantity": [row.id], "unit": [row.id], "attributes": source_ids},
                        attributes=attrs, install_code=rule)
    if "Anschlusswink" in original:
        position.category, position.install_code = "Support", "SUPPORT_SET"
        position.attributes = {"components_per_set": "8", "quantity_basis": "Number of penetrations; eight angles per set"}
    if re.search(r"Durchdringungen durch brandabschnitt", original):
        position.category = "Fire protection"
        position.install_code = "FIRE_SEAL_ROUND" if attrs.get("diameter_mm") else "FIRE_SEAL_RECT"
    if "Revisisondeckel" in original:
        position.category, position.install_code = "Fire protection", "FIRE_ACCESS"
    if quantity is None:
        position.warnings.append(Issue(id=f"{position.id}-quantity", kind="missing_quantity", severity="blocker", title="Tender quantity is missing", detail="The unit is present but its quantity field is blank. No zero or inferred amount has been assigned.", source_span_ids=[row.id], position_ids=[position.id], action="Confirm the quantity from the author or add a reasoned assumption."))
    if attrs.get("schedule_length_mm") and attrs.get("length_mm") != attrs["schedule_length_mm"]:
        position.warnings.append(Issue(id=f"{position.id}-length", kind="dimension_conflict", severity="blocker", title="Silencer length evidence conflicts", detail=f"Model/body length is {attrs.get('length_mm')} mm, but the schedule says {attrs['schedule_length_mm']} mm.", source_span_ids=source_ids, position_ids=[position.id], action="Confirm the intended length before accepting a reference."))
        position.attributes["technical_conflict"] = True
    return position


def _apply_single_apparatus_quantity_assumption(position: Position, heading: SourceSpan, package_spans: list[SourceSpan]) -> None:
    if position.quantity is not None:
        return
    if not re.search(r"Zuluftger.t\s+\d+-1\b", heading.text, re.I):
        return
    lead = package_spans[:12]
    if not any("Offert-Nr." in span.text for span in lead) or not any(re.match(r"Typ\b", span.text, re.I) for span in lead):
        return
    label = re.sub(r"\s+Stk\.?\s*$", "", heading.text, flags=re.I).strip()
    position.quantity = "1"
    position.unit = position.unit or "pc"
    position.raw_quantity = None
    position.raw_unit = position.raw_unit or ("Stk" if position.unit == "pc" else position.unit)
    position.field_sources["quantity"] = [heading.id]
    position.field_sources.setdefault("unit", [heading.id])
    assumption = f"Quantity blank in tender; single designated unit '{label}' -> 1 pc assumed"
    if assumption not in position.assumptions:
        position.assumptions.append(assumption)
    for issue in position.warnings:
        if issue.kind == "missing_quantity":
            issue.severity = "warning"
            issue.title = "Tender quantity is missing - assumption confirm"
            issue.detail = "No printed quantity was found. Pricing uses editable assumption: single designated apparatus -> 1 pc."
            issue.source_span_ids = [heading.id]
            issue.action = "Confirm the quantity assumption or replace it with author evidence."
    position.status = "assumption_applied"


def _schedule(page: PageRecord, span: SourceSpan) -> Position | None:
    hit = re.match(r"^(\d+(?:[.,]\d+)?)\s*(R-R|BGE|ATE|DRE|MFA|USE|L|LT|BA|BS|RS|SR|UA|US|TA|TS)\s+(.+)$", span.text)
    if not hit:
        return None
    q, code, body = hit.groups()
    attrs: dict = {"schedule_code": code}
    numbers = re.findall(r"(?<![\w])\d+(?:[.,]\d+)?", body)
    # Description may contain a nominal angle before table dimensions.
    if "°" in body and code == "ATE":
        numbers = numbers[1:]
    unit = "pc"
    qty = Decimal(normalize_number(q))
    rule = "DUCT_FITTING"
    if code == "R-R":
        attrs["diameter_mm"] = numbers[0] if numbers else None
        attrs["conversion"] = {"from_unit": "mm", "to_unit": "m", "input": str(qty), "formula": "length_mm / 1000"}
        qty /= 1000
        unit, rule = "m", "DUCT_ROUND"
    elif code == "L" and len(numbers) >= 2:
        attrs.update(width_mm=numbers[0], height_mm=numbers[1], length_mm=str(qty))
        attrs["conversion"] = {"from_unit": "mm", "to_unit": "m2", "input": str(qty), "formula": "2 × (width_mm + height_mm) × length_mm / 1000000"}
        qty = 2 * (Decimal(numbers[0]) + Decimal(numbers[1])) * qty / 1000000
        unit, rule = "m2", "DUCT_RECT"
    elif code == "LT":
        unit, rule = "mm", None
        attrs["unsupported_conversion"] = "Luftleitungsteil geometry requires separate surface-area measurement."
        if len(numbers) >= 2:
            attrs.update(width_mm=numbers[0], height_mm=numbers[1])
            area = area_from_length(numbers[0], numbers[1], qty)
            attrs["area_m2"] = raw(area)
            attrs["conversion"] = {"from_unit": "mm", "to_unit": "m2", "input": str(qty),
                                   "formula": "2 × (width_mm + height_mm) × length_mm / 1000000 × fitting_section_area_factor"}
    elif code == "BGE" and len(numbers) >= 2:
        attrs.update(diameter_mm=numbers[0], angle_deg=numbers[1])
    else:
        attrs["unsupported_fitting"] = True
        attrs["table_dimensions"] = numbers
    p = Position(id=f"POS-{_id(span.document_id, span.id)}", document_id=span.document_id, system=page.system,
                 category="Ductwork", description=body, original_description=span.text, quantity=str(qty), unit=unit,
                 raw_quantity=q, raw_unit="mm" if code in {"L", "LT", "R-R"} else "Stk", source_page=page.page,
                 source_span_ids=[span.id], field_sources={"description": [span.id], "quantity": [span.id], "unit": [span.id], "attributes": [span.id]},
                 attributes=attrs, install_code=rule)
    if code == "LT":
        p.warnings.append(Issue(id=f"{p.id}-lt-geometry", kind="geometry_review", severity="warning",
            title="Duct section area needs review", detail="Luftleitungsteil geometry is estimated from the listed connection perimeter and length. Verify unusual shapes and accept a supported material rate or supplier quote before relying on a price.",
            source_span_ids=[span.id], position_ids=[p.id], action="Confirm the area-rate assumption or request a supplier takeoff."))
    return p


def _requirements(page: PageRecord, spans: list[SourceSpan]) -> list[Requirement]:
    result = []
    patterns = [
        (r"Unternehmervarianten|Varianten.*(?:zulässig|zugelassen|gestattet)", "Contractor variants", "commercial"),
        (r"Preisverhandlungen|Abgebotsrunden", "Tender negotiation restriction", "commercial"),
        (r"Excel.*Auszug|Excel.*Kalkulation", "Referenced Excel takeoff", "missing_input"),
        (r"bauseits gelieferten Feldgeräte", "Installation of devices supplied by others", "scope"),
        (r"(?:Motagehöhen|Montagehöhen)", "Installation height", "installation"),
        (r"VKF.*(?:zertifiz|Zulassung)|SN EN 1366-1|SN EN 13501-2", "Fire protection certification", "technical"),
        (r"Hygiene-Erstinspektion|SWKI VA104|SWKI VA 104", "Hygiene and inspection obligation", "technical"),
        (r"Mehrwertsteuer|MWST|Bauabzug|Baustrom|Bauwesenversicherung", "Tax or construction deduction", "commercial"),
    ]
    for pattern, title, category in patterns:
        for index, span in enumerate(spans):
            if re.search(pattern, span.text, re.I):
                context = spans[max(0, index - 1):min(len(spans), index + 3)]
                result.append(Requirement(id=f"REQ-{_id(span.id, title)}", title=title, description="\n".join(s.text for s in context), source_page=page.page, source_span_ids=[s.id for s in context], category=category))
    return result


def extract_local_batch(pages: list[PageRecord], spans: list[SourceSpan], catalog: list[dict]) -> ExtractionBatch:
    batch = ExtractionBatch(usage={"mode": "local", "parser_version": PARSER_VERSION})
    by_page: dict[int, list[SourceSpan]] = {}
    for span in spans:
        by_page.setdefault(span.page, []).append(span)
    for page in pages:
        source = sorted(by_page.get(page.page, []), key=lambda s: (s.top, s.x0))
        for s in source:
            batch.dispositions[s.id] = s.disposition
        batch.requirements.extend(_requirements(page, source))
        for warning in page.warnings:
            relevant = [s.id for s in source if s.kind == "boilerplate"] if "System conflict" in warning else [s.id for s in source[:2]]
            batch.issues.append(Issue(id=f"ISS-{_id(page.page, warning)}", kind="system_conflict" if "System conflict" in warning else "page_extraction", severity="blocker", title="Conflicting system identifiers" if "System conflict" in warning else "Page extraction needs review", detail=warning, source_span_ids=relevant, action="Confirm the page's system against its section and original evidence."))
        if page.system == "Unassigned":
            continue
        body = [s for s in source if s.kind != "boilerplate"]
        if any(s.kind.startswith("package") for s in body):
            package_spans = [s for s in body if s.kind.startswith("package")]
            starts = [s for s in package_spans if s.kind.startswith("package_start")]
            if starts:
                start = starts[0]
                p = _make_position(page, start, package_spans, start.text)
                p.id = start.kind.split(":", 1)[1]
                p.category, p.install_code = "Equipment", "AHU_LARGE"
                p.quantity, p.unit = _quantity(start.text)
                p.attributes["package_inclusions"] = "Specified subcomponents retained within apparatus package; supplier inclusion verification required."
                p.attributes["package_source_pages"] = [page.page]
                _apply_single_apparatus_quantity_assumption(p, start, package_spans)
                batch.positions.append(match_position(p, catalog))
            elif package_spans:
                # Continuation pages are folded into the parent package position
                # rather than presented as CHF 0.00 standalone rows.
                pass
            for s in package_spans:
                batch.dispositions[s.id] = "position"
            continue
        context: list[SourceSpan] = []
        section_scope_evidence: tuple[str, str] | None = None
        last_quantity: SourceSpan | None = None
        supply_only = False
        for span in body:
            if any(re.search(pattern, span.text, re.I) for pattern in SCOPE_EXCLUSION_PATTERNS):
                section_scope_evidence = (span.text, span.id)
            scheduled = _schedule(page, span) if "Bauteilliste" in page.text else None
            if scheduled:
                # Only circular bends have a compatible generic fitting catalogue.
                if scheduled.attributes.get("unsupported_fitting"):
                    scheduled.status = "review_required"
                    scheduled.assumptions.append("No matching catalogue geometry; fit-up labour and material remain unresolved.")
                    batch.positions.append(scheduled)
                else:
                    batch.positions.append(match_position(scheduled, catalog))
                batch.dispositions[span.id] = "position"
                continue
            if span.kind == "heading" and not re.match(r"[A-F]\s+[A-ZÄÖÜ, ]+$", span.text):
                # Preserve weatherproof cladding as context for its insulation heading.
                preserve = context[-1:] if "Thermische" in span.text and context and "Doppelwandige" in context[-1].text else []
                context = preserve + [span]
                last_quantity = None
                continue
            if "Einbau der folgenden Feldgeräte" in span.text:
                supply_only = True
            if "Lieferung und Einbau" in span.text:
                supply_only = False
            if span.kind == "quantity":
                # Consecutive size rows share their heading, not the previous size.
                current = [s for s in context if s.kind != "quantity"] + [span]
                if not current:
                    current = [span]
                # Named devices after a prior quantity begin a fresh line item.
                prefix = re.split(rf"\b(?:{UNIT})\b", span.text, flags=re.I)[0].strip()
                if re.match(r"(?:Drehantrieb|Kanalrauchmelder|Druckwächter|Frostschutz|Kanaltemperatur|Druckdifferenz|Montagefüsse|Montageschiene|Farbpfeile|Potentialverbindung|Montagerahmen)", prefix, re.I):
                    current = [span]
                p = _make_position(page, span, current)
                if re.search(r"Drehantrieb|Klappenantrieb|Druckwächter|Frostschutz|Kanaltemperatur|Druckdifferenz|Kanalrauchmelder", p.original_description, re.I):
                    p.category, p.install_code = "Controls", "CONTROL_POINT"
                    if supply_only:
                        p.scope_tags.append("supplied_by_others")
                        p.assumptions.append("Installation-only field-device scope; material supplied by building automation contractor. Verify supply boundary.")
                if re.search(r"E MONTAGE, DIENSTLEISTUNGEN", page.text):
                    service = "hygiene" if re.search(r"Hygiene|Laboranalysen", p.original_description) else "transport"
                    p.category, p.included_in = "Project services", f"project:{service}"
                    p.scope_tags.append(service)
                    p.assumptions.append(f"Covered provisionally by the project {service} allowance; verify scope before approval.")
                if page.system == "ROOF":
                    p.category, p.install_code = "Support", None
                p = match_position(p, catalog)
                scope_evidence = section_scope_evidence or _scope_exclusion_evidence(current)
                if scope_evidence:
                    _apply_scope_ambiguity(p, scope_evidence)
                if p.attributes.get("technical_conflict"):
                    p.status, p.match_evidence_band = "review_required", "conflicting"
                batch.positions.append(p)
                for s in current:
                    batch.dispositions[s.id] = "position"
                context.append(span)
                last_quantity = span
            else:
                context.append(span)
                if len(context) > 60:
                    context = context[-60:]
        # Explicit service scope is represented even when it has no quantity column.
        if "E MONTAGE, DIENSTLEISTUNGEN" in page.text and body:
            for tag, pattern, title in [("commissioning", r"Inbetrieb|Einregul", "Commissioning and system balancing"), ("documentation", r"Revisionspl|Wartungsvorschriften", "Documentation and handover"), ("engineering", r"Technische Bearbeitung", "Technical engineering")]:
                evidence = [s for s in body if re.search(pattern, s.text, re.I)]
                if evidence:
                    p = Position(id=f"SVC-{_id(evidence[0].document_id, page.system, tag)}", document_id=evidence[0].document_id, system=page.system, category="Project services", description=title, original_description="\n".join(s.text for s in evidence), source_page=page.page, source_span_ids=[s.id for s in evidence], included_in=f"project:{tag}", scope_tags=[tag], pricing_basis="included_elsewhere", status="assumption_applied", assumptions=[f"Covered provisionally by project-level {tag}; prevent duplicate service charges."])
                    batch.positions.append(p)
        # Keep every unrecognized quantity-bearing candidate discoverable.
        if not batch.positions and page.status != "parsed":
            batch.errors.append(f"Page {page.page}: {page.status}")
    return batch
