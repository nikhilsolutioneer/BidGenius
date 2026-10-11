"""Small, auditable catalogue retrieval. No benchmark records are consulted."""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any

from .models import Issue, MatchCandidate, Position


def normalize_number(value: str) -> str:
    text = str(value).strip().replace("’", "").replace("'", "").replace("`", "").replace(" ", "").replace("\u2019", "")
    if "," in text and "." not in text:
        text = text.replace(",", ".")
    elif "," in text:
        text = text.replace(",", "")
    try:
        result = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"Invalid numeric value: {value}") from exc
    if not result.is_finite():
        raise ValueError("Numeric values must be finite")
    return format(result, "f")


def normalize_unit(value: str | None) -> str | None:
    if value is None:
        return None
    return {"stk": "pc", "stk.": "pc", "stück": "pc", "stueck": "pc", "st": "pc",
            "st.": "pc", "m²": "m2", "m 2": "m2", "m³": "m3", "pauschal": "LS",
            "pausch": "LS", "psch": "LS", "satz": "pc", "set": "pc"}.get(value.lower().strip(), value.strip())


def infer_attributes(text: str) -> dict[str, Any]:
    """Read labelled attributes only; numbers in acoustic tables are not dimensions."""
    attrs: dict[str, Any] = {}
    dn = re.search(r"(?:\bDN\s*|[Øø∅]\s*|(?:Durchmesser|Nennweite)\s*[:=]?\s*)(\d{2,4})", text, re.I)
    if dn:
        attrs["diameter_mm"] = dn.group(1)
    dim = re.search(r"\b(\d{2,4})\s*[x×]\s*(\d{2,4})(?:\s*[x×]\s*(\d{2,4}))?\s*(mm|cm)?\b", text, re.I)
    if dim:
        factor = Decimal(10) if dim.group(4) == "cm" else Decimal(1)
        attrs["width_mm"] = str(Decimal(dim.group(1)) * factor)
        attrs["height_mm"] = str(Decimal(dim.group(2)) * factor)
        if dim.group(3):
            attrs["length_mm"] = str(Decimal(dim.group(3)) * factor)
    for name, label in (("width_mm", r"Breite|Width|\bB"), ("height_mm", r"Höhe|Hoehe|Height|\bH"), ("length_mm", r"Länge|Laenge|Length|\bL")):
        hit = re.search(rf"(?:{label})\s*[:=]\s*(\d+(?:[.,]\d+)?)\s*(mm|cm)?", text, re.I)
        if hit:
            attrs[name] = str(Decimal(normalize_number(hit.group(1))) * (10 if hit.group(2) == "cm" else 1))
    thick = re.search(r"(?:Dämmstärke|Dämmstarke|Dicke|Dämmung|Isolation|Isolierung|Stärke|thickness)\s*[:=]?\s*(\d{1,3})\s*mm", text, re.I)
    if thick:
        attrs["thickness_mm"] = thick.group(1)
    angle = re.search(r"\b(15|30|45|60|90)\s*[°º]", text)
    if angle:
        attrs["angle_deg"] = angle.group(1)
    airflow = re.search(r"(?:Volumenstrom|Luftmenge|Luftleistung|airflow)[^\n\d]{0,25}(\d[\d'’`., \u2019]*)\s*m[³3]/h", text, re.I)
    if airflow:
        attrs["airflow_m3h"] = normalize_number(airflow.group(1))
    fire = re.search(r"\bEI\s*(30|60|90|120)(?:[- ]?(S))?", text, re.I)
    if fire:
        attrs["fire_class"] = "EI" + fire.group(1) + ("-S" if fire.group(2) else "")
    manufacturer = re.search(r"(?:Fabrikat|Hersteller|Manufacturer)[ \t]*(?::|=)?[ \t]*(?:z\.?[ \t]*B\.?[ \t]*)?([^\n,;]+)", text, re.I)
    if manufacturer:
        named = manufacturer.group(1).strip()
        if re.search(r"[A-Za-zÄÖÜäöü]{2}", named) and not re.match(r"Kanäle|Taschenfilter", named, re.I):
            attrs["manufacturer"] = named
    return attrs


def classify(text: str, attrs: dict | None = None) -> tuple[str, str | None]:
    t = text.lower()
    attrs = attrs or {}
    # Specific products precede broad duct and damper words.
    if re.search(r"zeigerthermometer|kanalrauchmelder|druckwächter|frostschutzwächter", t):
        return "Controls", None
    if re.search(r"kanaldichtheitsprüfung|kanaldichtheitspruefung", t):
        return "Project services", None
    if re.search(r"revisionsdeckel|revisionsöffnung|inspection cover", t):
        return "Fire protection", "FIRE_ACCESS"
    if re.search(r"brandabschott|brandschutzabschott|fire seal|brandabschlu", t):
        return "Fire protection", "FIRE_SEAL_RECT" if attrs.get("width_mm") else "FIRE_SEAL_ROUND"
    if re.search(r"brandschutzklappe|fire damper", t):
        return "Fire protection", "FIRE_DAMPER"
    if re.search(r"schalldämpfer|schalldaempfer|silencer", t):
        return "Silencer", "SILENCER"
    if re.search(r"variabl\w*\s+(?:luft)?volumen|variable volume|\bvav\b|\btvr[- ]", t):
        return "Flow controller", "VAV_CONTROLLER"
    if re.search(r"konstant.*volumen|konstant.*regler|konstanten vol\.strom|constant volume|\bcav\b|volumenstrombegrenzer", t):
        return "Flow controller", "CAV_CONTROLLER"
    if re.search(r"volumenstromregler|volumenstrom-regler|variable volume|\bvav\b", t):
        return "Flow controller", "VAV_CONTROLLER"
    if re.search(r"anschlusswink|connection.angle|winkel.set", t):
        return "Support", "SUPPORT_SET"
    if re.search(r"dämm|dämmung|isolation|isolierung|insulation|mineralwoll", t):
        thickness = str(attrs.get("thickness_mm", ""))
        rule = {"30": "INSULATION_30", "60": "INSULATION_60"}.get(thickness)
        if thickness == "100" and re.search(r"wetterfest|ummantelung|cladding|weatherproof", t):
            rule = "INSULATION_EXT"
        return "Insulation", rule
    if re.search(r"differenzdruck|druckdifferenz|temperaturfühler|temperaturfuehler|stellantrieb|drehantrieb|volumenstrommess|pressure transmitter|temperature sensor|actuator 24|flow transmitter", t):
        return "Controls", "CONTROL_POINT"
    if re.search(r"zuluftventil|abluftventil|tellerventil|air valve|supply valve|exhaust valve|drallauslass|luftdurchlass|lüftungsgitter|lueftungsgitter|zuluftgitter|abluftgitter", t):
        return "Air terminal", "DIFFUSER"
    if re.search(r"drosselklappe|regulierklappe|regulierorgan|balancing damper|jalousieklappe|absperrklappe", t):
        return "Damper", "DAMPER"
    if re.search(r"monobloc|monoblock|lüftungsgerät|lueftungsgeraet|lüftungsaggregat|air.handling|zentralgerät", t):
        return "Equipment", "AHU_LARGE"
    if re.search(r"ventilator|\bfan\b", t):
        return "Equipment", "FAN"
    if re.search(r"inbetriebnahme|einregulier|commissioning|luftmengenmessung", t):
        return "Project services", "COMMISSION_SYSTEM"
    if re.search(r"dokumentation|revisionsunterlagen|documentation", t):
        return "Project services", "DOCUMENT_SYSTEM"
    if re.search(r"bogen|bend|abzweig|reduktion|t-stück|t-stueck|übergang|uebergang|formstück|formstueck", t):
        return "Ductwork", "DUCT_FITTING"
    if re.search(r"wickelfalz|spiral.*rohr|circular.*duct|lüftungsrohr|lueftungsrohr", t):
        return "Ductwork", "DUCT_ROUND"
    if re.search(r"kanal|rechteck.*leitung|rectangular.*duct", t):
        return "Ductwork", "DUCT_RECT"
    if re.search(r"dach.*stütz|dach.*stuetz|rooftop support|konstruktion.*dach|auflager", t):
        return "Support", None
    return "unclassified", None


def _catalog_attrs(product: dict) -> dict:
    attrs = infer_attributes(product.get("description", "") + " " + product.get("model", ""))
    if product.get("category") == "Insulation":
        hit = re.search(r"\b(30|60|100)\s*mm", product.get("description", ""))
        if hit:
            attrs["thickness_mm"] = hit.group(1)
    flow = re.search(r"(?:AHU|FAN)-(\d+)", product.get("model", ""))
    if flow:
        attrs["airflow_m3h"] = flow.group(1)
    return attrs


def _fmt_airflow(value: Decimal | str) -> str:
    flow = Decimal(str(value))
    if flow == flow.to_integral_value():
        return f"{int(flow):,}"
    return format(flow.normalize(), "f")


def _is_supplier_airflow_package(position: Position, product: dict) -> bool:
    code = product.get("install_code") or position.install_code
    return code in {"AHU_LARGE", "FAN"} and product.get("source_type") == "supplier_package"


def match_position(position: Position, catalog: list[dict]) -> Position:
    p = position.model_copy(deep=True)
    text = p.original_description or p.description
    p.attributes = {**infer_attributes(text), **p.attributes}
    category, install = classify(text, p.attributes)
    if p.category == "unclassified":
        p.category = category
    if p.install_code is None:
        p.install_code = install
    p.unit = normalize_unit(p.unit)
    rule_units = {item["install_code"]: item.get("unit") for item in catalog if item.get("install_code")}
    rule_units.update(COMMISSION_SYSTEM="system", DOCUMENT_SYSTEM="system")
    required_unit = rule_units.get(p.install_code)
    if not p.product_id and not p.overrides.get("install_code") and p.unit and required_unit and p.unit != required_unit:
        rejected_rule = p.install_code
        p.install_code = "UNKNOWN"
        p.warnings = [w for w in p.warnings if w.kind != "installation_unit"] + [Issue(
            id=f"{p.id}-installation-unit", kind="installation_unit", severity="warning",
            title="Installation rule requires a different unit",
            detail=f"Inferred rule {rejected_rule} uses {required_unit}; source quantity uses {p.unit}. Labour remains unresolved.",
            source_span_ids=p.source_span_ids, position_ids=[p.id],
            action="Select a compatible installation rule or add a reviewed labour estimate.")]
    if p.included_in:
        p.pricing_basis, p.status = "included_elsewhere", "assumption_applied"
        return p
    if "supplied_by_others" in p.scope_tags:
        p.pricing_basis = "labour_only"
        p.install_code = p.install_code or ("CONTROL_POINT" if p.category == "Controls" else None)
        p.status = "assumption_applied" if p.quantity is not None and p.install_code else "insufficient_information"
        return p
    candidates: list[tuple[int, dict, MatchCandidate]] = []
    explicit = p.product_id
    for product in catalog:
        if product.get("product_id") != explicit and (not p.install_code or product.get("install_code") != p.install_code):
            continue
        a = _catalog_attrs(product)
        satisfied, missing, conflicts = [], [], []
        if p.unit and product.get("unit") == p.unit:
            satisfied.append(f"Unit: {p.unit}")
        elif p.unit:
            conflicts.append(f"Unit {p.unit} differs from catalogue {product.get('unit')}")
        else:
            missing.append("Tender unit")
        if p.install_code == product.get("install_code"):
            satisfied.append(f"Function: {p.install_code}")
        elif p.install_code:
            conflicts.append("Installation function differs")
        if p.attributes.get("diameter_mm") and a.get("width_mm") and a.get("height_mm") and not a.get("diameter_mm"):
            conflicts.append("Circular tender connection differs from rectangular catalogue geometry")
        if p.attributes.get("width_mm") and p.attributes.get("height_mm") and a.get("diameter_mm") and not p.attributes.get("diameter_mm"):
            conflicts.append("Rectangular tender connection differs from circular catalogue geometry")
        for key in ("diameter_mm", "width_mm", "height_mm", "length_mm", "thickness_mm", "angle_deg", "fire_class", "airflow_m3h"):
            if key in a:
                if key not in p.attributes:
                    missing.append(key)
                elif (str(a[key]) == str(p.attributes[key]) or (key != "fire_class" and Decimal(str(a[key])) == Decimal(str(p.attributes[key])))):
                    satisfied.append(f"{key}: {a[key]}")
                elif key == "airflow_m3h" and abs(Decimal(str(a[key])) - Decimal(str(p.attributes[key]))) / Decimal(str(a[key])) <= Decimal("0.15"):
                    missing.append(f"Approximate airflow reference {_fmt_airflow(a[key])}; tender {_fmt_airflow(p.attributes[key])}")
                elif key == "airflow_m3h" and _is_supplier_airflow_package(p, product) and Decimal(str(a[key])) >= Decimal(str(p.attributes[key])):
                    missing.append(f"Size-up airflow reference {_fmt_airflow(a[key])}; tender {_fmt_airflow(p.attributes[key])}")
                else:
                    conflicts.append(f"{key}: tender {p.attributes[key]}, catalogue {a[key]}")
            elif key in p.attributes and key in {"diameter_mm", "width_mm", "height_mm"}:
                missing.append(f"Catalogue {key}")
        if p.install_code == "DIFFUSER":
            exhaust = bool(re.search(r"abluft|exhaust", text, re.I))
            prod_exhaust = "exhaust" in product.get("description", "").lower()
            if exhaust != prod_exhaust:
                conflicts.append("Supply/exhaust function differs")
            else:
                satisfied.append("Supply/exhaust function")
        if p.install_code == "CONTROL_POINT":
            terms = ((r"differenzdruck|pressure", "pressure"), (r"temperatur|temperature", "temperature"), (r"stellantrieb|actuator", "actuator"), (r"volumenstrom|volume flow", "volume flow"))
            for pattern, english in terms:
                if re.search(pattern, text, re.I) and english not in product.get("description", "").lower():
                    conflicts.append("Control device function differs")
        candidate = MatchCandidate(product_id=product["product_id"], satisfied=satisfied, missing=missing, conflicts=conflicts,
                                   explanation="Pricing reference only. Synthetic catalogue manufacturer does not establish technical equivalence.")
        score = len(satisfied) * 5 - len(missing) * 2 - len(conflicts) * 50
        candidates.append((score, product, candidate))
    candidates.sort(key=lambda item: (-item[0], item[1]["product_id"]))
    p.candidates = [c for _, _, c in candidates[:5]]
    selected = next(((prod, c) for _, prod, c in candidates if prod["product_id"] == explicit), None)
    if selected is None:
        eligible = [(prod, c) for _, prod, c in candidates if not c.conflicts]
        airflow_eligible = [(prod, c) for prod, c in eligible
                            if _is_supplier_airflow_package(p, prod) and _catalog_attrs(prod).get("airflow_m3h") and p.attributes.get("airflow_m3h")]
        if airflow_eligible:
            selected = min(airflow_eligible, key=lambda item: Decimal(str(_catalog_attrs(item[0])["airflow_m3h"])))
        # Missing key dimensions must not cause a guessed selection between alternatives.
        elif len(eligible) == 1:
            selected = eligible[0]
    if selected is None:
        p.product_id = None
        p.pricing_basis = "unpriced"
        p.status = "insufficient_information" if p.quantity is None or not p.unit else "review_required"
        p.match_evidence_band = "conflicting" if candidates and all(c.conflicts for _, _, c in candidates) else "partial"
        return p
    product, candidate = selected
    p.product_id = product["product_id"]
    p.install_code = product.get("install_code")
    p.category = product.get("category", p.category)
    p.match_evidence_band = "conflicting" if candidate.conflicts else ("partial" if candidate.missing else "strong")
    if candidate.conflicts:
        p.status = "review_required"
        p.technical_equivalence = "incompatible"
        p.warnings = [w for w in p.warnings if w.kind != "match_conflict"] + [Issue(id=f"{p.id}-match-conflict", kind="match_conflict", severity="blocker", title="Catalogue reference conflicts with tender", detail="; ".join(candidate.conflicts), source_span_ids=p.source_span_ids, position_ids=[p.id], action="Choose a compatible reference or document a pricing-only assumption.")]
    else:
        p.status = "supplier_quote_required" if str(product.get("supplier_quote_required", "false")).lower() == "true" else "calculated"
    p.pricing_basis = "supplier_reference" if product.get("source_type") == "supplier_package" else "catalogue"
    p.attributes["catalogue_manufacturer"] = product.get("manufacturer")
    tender_maker = p.attributes.get("manufacturer")
    if tender_maker and str(tender_maker).casefold() != str(product.get("manufacturer", "")).casefold():
        candidate.explanation = f"Tender manufacturer reference: {tender_maker}. Catalogue manufacturer: {product.get('manufacturer')}. Different manufacturer; pricing reference only, technical equivalence remains unverified."
    selected_attrs = _catalog_attrs(product)
    functional_gaps = {"feuchte": "humidity", "humidity": "humidity", "co2": "CO2", "voc": "VOC", "druck": "pressure", "pressure": "pressure", "rauch": "smoke", "smoke": "smoke", "frost": "frost"}
    gap = next((english for term, english in functional_gaps.items() if term in text.casefold() and term not in product.get("description", "").casefold()), None)
    if gap:
        p.match_evidence_band, p.status = "partial", "review_required"
        detail = "Tender requires humidity sensing; reference is temperature-only" if gap == "humidity" else f"Tender requires {gap}; catalogue reference does not state that function."
        warning = Issue(id=f"{p.id}-functional-gap", kind="functional_gap", severity="blocker", title="Catalogue reference lacks a tender function", detail=detail, source_span_ids=p.source_span_ids, position_ids=[p.id], action="Select a reference that covers the tender function or record a justified pricing-only assumption.")
        p.warnings = [w for w in p.warnings if w.kind != "functional_gap"] + [warning]
    if _is_supplier_airflow_package(p, product) and p.attributes.get("airflow_m3h") and selected_attrs.get("airflow_m3h"):
        tender_flow = Decimal(str(p.attributes["airflow_m3h"]))
        catalogue_flow = Decimal(str(selected_attrs["airflow_m3h"]))
        verb = "Sized up" if catalogue_flow > tender_flow else "Sized by airflow"
        assumption = (f"{verb}: tender {_fmt_airflow(tender_flow)} m3/h -> {product['product_id']} "
                      f"({_fmt_airflow(catalogue_flow)} m3/h); supplier quote required")
        if assumption not in p.assumptions:
            p.assumptions.append(assumption)
    if p.pricing_basis == "supplier_reference":
        p.attributes.setdefault("package_inclusions", "unknown")
        assumption = "Supplier reference treated as supply-only; package inclusions and actual quotation require review."
        if assumption not in p.assumptions:
            p.assumptions.append(assumption)
    if p.quantity is None:
        p.status = "insufficient_information"
    return p


def validate_explicit_reference(position: Position, catalog: list[dict], product_id: str) -> Position:
    """Validate a reviewer-selected reference without substituting another product.

    Conflicts remain visible and do not establish technical approval. Unit
    incompatibility is additionally rejected by the authoritative calculator.
    """
    if not any(item.get("product_id") == product_id for item in catalog):
        raise ValueError("Unknown catalogue product ID")
    p = position.model_copy(deep=True, update={"product_id": product_id})
    # A manual replacement of an included or labour-only row must first clear
    # its supply allocation explicitly; never buy supplied-by-others material.
    if p.included_in or "supplied_by_others" in p.scope_tags:
        raise ValueError("Clear the scope allocation before selecting purchased material")
    return match_position(p, catalog)
