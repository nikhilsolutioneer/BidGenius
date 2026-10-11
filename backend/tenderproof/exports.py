"""Revision-pinned, offline-readable review packages. No external submission."""
from __future__ import annotations

import csv
from html import escape
import io
import json
from pathlib import Path
import zipfile

from .service import EstimateService, identifier
from .storage import Repository, now
from .commercial import commercial_view


def text_cell(value) -> str:
    text = "" if value is None else str(value)
    return "'" + text if text.startswith(("=", "+", "-", "@", "\t", "\r")) else text


def csv_export(project: dict) -> str:
    from .reference import fold_continuation_pages
    buffer = io.StringIO(newline="")
    headers = ["reference", "position_id", "lv_id", "origin", "system", "category", "description", "quantity", "unit", "source_page",
               "product_id", "pricing_basis", "status", "review_state", "match_evidence_band", "technical_equivalence",
               "material_cost_chf", "unrounded_hours", "labour_role", "hourly_rate_chf", "labour_cost_chf", "direct_cost_chf", "source_span_ids", "assumptions"]
    writer = csv.DictWriter(buffer, fieldnames=headers)
    writer.writeheader()
    positions = fold_continuation_pages(project["positions"])
    for p in positions:
        row = {**p, **(p.get("cost") or {}), "reference": p.get("reference", p["id"]), "position_id": p["id"], "lv_id": p["id"], "source_span_ids": "|".join(p["source_span_ids"]), "assumptions": " | ".join(p["assumptions"])}
        writer.writerow({name: text_cell(row.get(name)) for name in headers})
    return "\ufeff" + buffer.getvalue()


def rfq_export(project: dict) -> str:
    from .reference import fold_continuation_pages
    lines = ["ANFRAGEENTWURF — NICHT VERSENDET", project["name"], f"Kalkulationsstand: Revision {project['revision']}", "",
             "Bitte offerieren Sie folgende Lieferumfänge. Referenzpreise sind keine bestätigten Lieferantenofferten.",
             "Bitte Lieferumfang, Montage, Transport, Inbetriebnahme, Lieferfrist, Gültigkeit und technische Nachweise separat bestätigen.", ""]
    positions = fold_continuation_pages(project["positions"])
    for p in positions:
        if p["status"] not in ("supplier_quote_required", "insufficient_information") and p["pricing_basis"] != "supplier_reference":
            continue
        ref = p.get("reference") or f"{p['system']} · p.{p['source_page']}"
        lines += [f"{ref} ({p['id']}) — PDF Seite {p['source_page']}", p["description"],
                  f"Menge: {p['quantity'] or 'offen'} {p['unit'] or ''}", f"Katalogreferenz: {p['product_id'] or 'keine'}",
                  "Offene Punkte: " + "; ".join(p["assumptions"] + [w["title"] for w in p["warnings"]]), ""]
    return "\n".join(lines)


def register_export(project: dict, summary: dict) -> str:
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["Typ", "Referenz", "Beschreibung", "Status", "PDF_Seite", "Quellen", "Betrag_CHF"])
    rows = []
    rows.extend(["Anforderung", r["id"], r["title"] + ": " + r["description"], r["review_state"], r["source_page"], "|".join(r["source_span_ids"]), ""] for r in project["requirements"])
    rows.extend(["Annahme", a.get("position_id", a.get("key", "Projekt")), a.get("text", ""), "Annahme", "", "|".join(a.get("source_span_ids", [])), ""] for a in summary["assumptions"])
    rows.extend(["Risiko" if a["kind"] == "risk" else "Chance", a["id"], a["title"] + ": " + a["basis"], a["review_state"], "", "|".join(a["source_span_ids"]), a["amount_chf"]] for a in project["adjustments"])
    rows.extend(["Prüfpunkt", i["id"], i["title"] + ": " + i["detail"], i["review_state"], "", "|".join(i["source_span_ids"]), ""] for i in summary["issues"])
    commercial = commercial_view(project)
    context = commercial["context"]
    rows.append(["Kommerzielle Annahmen", "Projekt", json.dumps(context, ensure_ascii=False), "Revisionsstand", "", "", ""])
    for record in commercial["records"]:
        rows.append(["Historische Offerte", record["record_id"], record["project_name"] + " / " + record["source_filename"], record["outcome"], "", record["source_sha256"], record["bid_amount"] if record["currency"] == "CHF" else ""])
    completeness = summary.get("completeness", {})
    if completeness:
        rows.append(["Preiskomplettheit", "Projekt", f"Bepreist: {completeness.get('positions_priced')} von {completeness.get('positions_total')} Positionen ({completeness.get('pct_positions_priced')}%). {completeness.get('positions_included_elsewhere')} anderweitig gedeckt; {completeness.get('positions_unpriced')} unbepreist. Benchmark ohne {completeness.get('positions_no_basis')} Positionen ohne Vergleichsbasis: CHF {completeness.get('allowance_low_chf')} bis CHF {completeness.get('allowance_high_chf')} (Median CHF {completeness.get('allowance_median_chf')})", "Richtsatz", "", "", completeness.get("allowance_median_chf", "")])
    for row in rows:
        writer.writerow([text_cell(value) for value in row])
    return "\ufeff" + output.getvalue()


def html_export(project: dict, summary: dict) -> str:
    from .reference import fold_continuation_pages
    e = lambda value: escape(str(value if value is not None else "Offen"))
    totals = summary["totals"]
    rows = []
    positions = fold_continuation_pages(project["positions"])
    for p in positions:
        c = p.get("cost") or {}
        pos_ref = p.get("reference") or f"{p['system']} · p.{p['source_page']}"
        ownership = p.get('pricing_basis') == 'included_elsewhere'
        material = 'Anderweitig gedeckt' if ownership else e(c.get('material_cost_chf'))
        hours = 'Anderweitig gedeckt' if ownership else e(c.get('adjusted_install_hours'))
        labour_note = '' if ownership or c.get('hourly_rate_chf') is None else f"<small>{e(c.get('labour_role'))} · CHF {e(c.get('hourly_rate_chf'))}/h</small>"
        direct = 'Anderweitig gedeckt' if ownership else e(c.get('direct_cost_chf'))
        rows.append(f"<tr><td>{e(p['system'])}<small>{e(pos_ref)}</small></td><td>{e(p['description'])}<small>{e(p['status'])} · {e(p['pricing_basis'])}</small></td><td>{e(p['quantity'])} {e(p['unit'])}</td><td>{material}</td><td>{hours}{labour_note}</td><td>{direct}</td><td>{e(p['source_page'])}</td></tr>")
    german_labels = {"material": "Material inkl. Verschnitt", "labour": "Montagelohn", "small_material": "Kleinmaterial", "supplier_contingency": "Lieferantenrisiko", "transport": "Transport und Geräte", "engineering": "Engineering", "commissioning": "Inbetriebnahme", "hygiene": "Hygiene", "documentation": "Dokumentation", "risk": "Genehmigte Risiken", "opportunity": "Genehmigte Chancen", "overhead": "Gemeinkosten", "display_rounding": "Rundungsausgleich"}
    buildup = "".join(f"<tr><td>{e(german_labels.get(row['key'], row['label']))}<small>{e(row.get('basis', ''))}</small></td><td>CHF {e(row['amount_chf'])}</td></tr>" for row in summary["build_up"])
    requirements = "".join(f"<li><strong>{e(r['title'])}</strong> — {e(r['description'])} <small>PDF Seite {e(r['source_page'])}</small></li>" for r in summary["requirements"])
    adjustments = "".join(f"<li>{e(a['kind'])}: {e(a['title'])} — CHF {e(a['amount_chf'])}; {e(a['review_state'])}. {e(a['basis'])}</li>" for a in project["adjustments"])
    assumptions = "".join(f"<li>{e(a.get('text', a))}</li>" for a in summary.get("assumptions", []))
    outstanding = "".join(f"<li>{e(p['system'])} / Seite {e(p['source_page'])}: {e(p['description'])} — {e(p['status'])}</li>" for p in positions if p["status"] not in ("calculated", "non_priceable", "out_of_scope") or p["review_state"] != "accepted")
    scenarios = summary.get("scenarios", {})
    scenario_rows = "".join(f"<tr><td>{e(s['scenario'])}</td><td>{e(s['bid_price_chf'])}</td><td>{e(s['margin_pct'])}% / {e(s['achieved_margin_pct'])}%</td><td>{e(s['estimated_win_probability'])}</td><td>{e(s['expected_contribution_chf'])}</td></tr>" for s in scenarios.get("scenarios", []))
    commercial = commercial_view(project)
    completeness = summary.get("completeness", {})
    completeness_html = ""
    if completeness:
        completeness_html = f"""
<h2>Preiskomplettheit & Benchmark-Richtsatz unbepreister Positionen</h2>
<div class="notice" style="background:#E8F5EE;border-left:4px solid #277350">
  <p><strong>Bepreister Leistungsumfang:</strong> {e(completeness.get('positions_priced', 0))} von {e(completeness.get('positions_total', 0))} Positionen ({e(completeness.get('pct_positions_priced', '0'))}%).</p>
  <p><strong>Status Positionen:</strong> {e(completeness.get('positions_included_elsewhere', 0))} anderweitig gedeckt, {e(completeness.get('positions_unpriced', 0))} unbepreist, davon {e(completeness.get('positions_partial', 0))} mit bekannten Teilkosten.</p>
  <p><strong>Benchmark-Bandbreite unbepreister Positionen (P25–P75):</strong> CHF {e(completeness.get('allowance_low_chf', '0.00'))} bis CHF {e(completeness.get('allowance_high_chf', '0.00'))} (Median: CHF {e(completeness.get('allowance_median_chf', '0.00'))}).</p>
  <small><em>Hinweis: {e(completeness.get('positions_no_basis', 0))} unbepreiste Positionen ohne Vergleichsbasis fehlen in dieser Bandbreite. Bekannte Teilkosten sind abgezogen. Der Richtsatz fliesst nicht automatisch in die Kalkulationsbasis ein.</em></small>
</div>
"""
    return f"""<!doctype html><html lang="de-CH"><head><meta charset="utf-8"><title>BidGenius AI — Kalkulationsentwurf R{project['revision']}</title>
<style>body{{font:14px/1.55 Roboto,Arial,sans-serif;color:#00243A;max-width:1200px;margin:40px auto;padding:0 25px}}header{{border-bottom:3px solid #00243A;padding-bottom:24px}}h1{{font-size:28px}}h2{{margin-top:32px}}small{{display:block;color:#5A6B78;font-size:12px}}.notice{{padding:16px;background:#FEF3E2;border-left:4px solid #B45309}}.price{{font-size:30px;font-weight:bold}}table{{width:100%;border-collapse:collapse}}td,th{{padding:9px 6px;border-bottom:1px solid #DCE4E2;text-align:left;vertical-align:top}}th{{background:#F4F7F6}}li{{margin:9px 0}}.print{{padding:10px 16px;cursor:pointer}}@media print{{body{{margin:0;font-size:12px}}.print{{display:none}}thead{{display:table-header-group}}tr{{break-inside:avoid}}}}</style></head><body>
<button class="print" onclick="window.print()">Drucken / als PDF speichern</button>
<header><strong>BIDGENIUS AI · PRÜFBARE KALKULATION</strong><h1>{e(project['name'])}</h1><p>Revision {project['revision']} · {e(project['updated_at'])}</p></header>
<p class="notice"><strong>KALKULATIONSENTWURF — KEINE VERBINDLICHE ANGEBOTSABGABE.</strong><br>Indikativer Preis für berücksichtigte Leistungen. Offene Mengen, Lieferantenofferten und Annahmen sind separat ausgewiesen. Mehrwertsteuer und Bauabzüge sind nicht automatisch enthalten.</p>
<p>Indikativer Verkaufspreis</p><p class="price">CHF {e(totals.get('selling_price_chf'))}</p>
{completeness_html}
<h2>Kostenaufbau</h2><table><tbody>{buildup}</tbody></table>
<h2>Positionen und Quellen</h2><table><thead><tr><th>System</th><th>Leistung / Status</th><th>Menge</th><th>Material CHF</th><th>Stunden / Ansatz</th><th>Direkt CHF</th><th>PDF Seite</th></tr></thead><tbody>{''.join(rows)}</tbody></table>
<h2>Risiken und Chancen</h2><ul>{adjustments or '<li>Keine zusätzlichen genehmigten Anpassungen.</li>'}</ul>
<h2>Empfohlene Angebotsspanne für berücksichtigte Leistungen</h2><p>CHF {e(scenarios.get('low_chf'))} – {e(scenarios.get('high_chf'))}. Annahmenbasiert; Gewinnwahrscheinlichkeiten sind illustrativ und keine kalibrierten Prognosen.</p>
<table><thead><tr><th>Szenario</th><th>Angebot CHF</th><th>Marge gewünscht / erreicht</th><th>Illustrative Wahrscheinlichkeit</th><th>Erwarteter Beitrag CHF</th></tr></thead><tbody>{scenario_rows}</tbody></table>
<h3>Kommerzielle Annahmen und Kapazität</h3><p>{e(json.dumps({'assumptions': scenarios.get('assumptions', {}), 'statistics': commercial['statistics'], 'capacity': commercial['capacity'], 'rationale': commercial['context']['adoption_rationale']}, ensure_ascii=False))}</p>
<h2>Annahmen</h2><ul>{assumptions}</ul><h2>Anforderungen</h2><ul>{requirements}</ul>
<h2>Offene Prüfungen und Leistungsgrenzen</h2><ul>{outstanding}</ul>
<footer><small>Originaldokument: {e(project['document']['filename'])} · SHA-256 {e(project['document']['sha256'])}<br>Kalkulationsbasis: Draft estimate. Die JSON-Datei des Prüfpakets enthält die vollständigen Quelldaten und Revisionsentscheidungen.</small></footer></body></html>"""


def create_export(repo: Repository, service: EstimateService, project_id: str, revision: int, format_name: str) -> dict:
    project = repo.revision(project_id, revision)
    summary = service.summary(project_id, revision)
    document = repo.document(project["document"]["id"])
    sources = repo.spans(document["id"])
    payload = {
        "schema_version": "1.0", "created_at": now(), "draft": not project["review_complete"],
        "project": {**service.public_project(project), "latest_run": project.get("run_provenance")}, "summary": summary, "positions": [{**p, "lv_id": p["id"]} for p in project["positions"]],
        "sources": sources, "catalogue_snapshot": project["catalog"], "productivity_snapshot": project["productivity"],
        "parameters": project["parameters"], "adjustments": project["adjustments"], "history": project["history"],
        "commercial": commercial_view(project),
        "notice": "Indicative included-scope estimate. Unresolved items are not zero. Probabilities are illustrative assumptions.",
    }
    content = {
        "csv": csv_export(project),
        "json": json.dumps(payload, ensure_ascii=False, indent=2),
        "html": html_export(project, summary),
        "rfq": rfq_export(project),
    }
    export_id = identifier("export")
    extension = "txt" if format_name == "rfq" else format_name
    filename = f"TenderProof_R{revision}_{export_id}.{extension}"
    directory = repo.directory / "exports"
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / filename
    if format_name == "zip":
        with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, suffix in (("csv", "csv"), ("json", "json"), ("html", "html"), ("rfq", "txt")):
                archive.writestr(f"TenderProof_R{revision}_{name}.{suffix}", content[name])
            archive.writestr(f"TenderProof_R{revision}_Anforderungen_Annahmen_Register.csv", register_export(project, summary))
            archive.writestr(f"TenderProof_R{revision}_Szenarien.json", json.dumps(summary.get("scenarios", {}), ensure_ascii=False, indent=2))
            for index, source in enumerate(commercial_view(project)["imports"], start=1):
                archive.writestr(f"historical/{index}_{source['sha256'][:12]}.csv", source["csv_text"])
            archive.write(document["path"], "source/" + document["filename"])
            archive.writestr("README.txt", "BidGenius AI review package\nOpen the HTML file and print to PDF if needed. CSV contains line items. JSON contains immutable revision data, evidence coordinates, reference data and assumptions. RFQ is a draft and has not been sent. The source PDF is included.\n")
    else:
        destination.write_text(content[format_name], encoding="utf-8")
    return {"url": f"/api/exports/{filename}", "filename": filename, "revision": revision}
