"""Retain installed dependency licence notices and a reproducible inventory."""
from importlib import metadata
import hashlib
import json
from pathlib import Path
import re
import shutil

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "third-party-licenses"
OUT.mkdir(parents=True, exist_ok=True)
rows = []


def slug(value):
    return re.sub(r"[^a-zA-Z0-9._-]", "_", value)


def retain(source, group, name):
    target = OUT / group / slug(name)
    target.mkdir(parents=True, exist_ok=True)
    copied = []
    for file in source:
        if file.is_file() and file.stat().st_size < 2_000_000:
            dest = target / slug(file.name)
            if dest.is_file() and dest.read_bytes() != file.read_bytes():
                dest = target / (slug(file.name) + "." + hashlib.sha256(file.read_bytes()).hexdigest()[:10])
            shutil.copyfile(file, dest)
            copied.append(str(dest.relative_to(ROOT)).replace("\\", "/"))
    return copied


for distribution in sorted(metadata.distributions(), key=lambda d: d.metadata.get("Name", "").lower()):
    name = distribution.metadata.get("Name", "unknown")
    files = [Path(distribution.locate_file(f)) for f in distribution.files or []
             if re.match(r"(?i)(license|licence|copying|notice|authors)(\.|$|_)", Path(f).name)]
    licence = distribution.metadata.get("License-Expression") or distribution.metadata.get("License", "See retained notices")
    if len(licence) > 100:
        licence = "See retained licence text"
    rows.append({"ecosystem": "Python", "name": name, "version": distribution.version, "license": licence,
                 "notices": retain(files, "python", name)})

modules = ROOT / "frontend" / "node_modules"
seen = set()
for path in sorted(modules.rglob("package.json")):
    try:
        package = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        continue
    name, version = package.get("name"), package.get("version")
    if not name or not version or (name, version) in seen:
        continue
    # Only actual dependency roots, not package test fixtures or examples.
    folder = path.parent
    if folder.parent.name != "node_modules" and not (folder.parent.name.startswith("@") and folder.parent.parent.name == "node_modules"):
        continue
    seen.add((name, version))
    files = [f for f in folder.iterdir() if re.match(r"(?i)(license|licence|copying|notice|ofl|authors)(\.|$|_)", f.name)]
    rows.append({"ecosystem": "npm", "name": name, "version": version, "license": package.get("license", "See retained notices"),
                 "notices": retain(files, "npm", f"{name}-{version}")})

(OUT / "inventory.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
intro = """# Third-party notices

The MIT licence in this repository covers original TenderProof code only.
Dependency licence and copyright texts are retained in `docs/third-party-licenses/`.
The machine-readable inventory records installed versions and notice paths.
Run `scripts/collect_notices.py` after changing dependencies.

The supplied Equans tender PDF, catalogue, productivity rules and example datasets
retain their original owners' rights; they are not relicensed by this application.
OpenAI's SDK is open-source, but OpenAI inference is an external proprietary
service subject to its terms. Inter's font licence and PDF.js notices are retained
with the npm dependencies. Python, Node and browser runtimes have their own licences.

| Ecosystem | Dependency | Version | Licence |
|---|---|---|---|
"""
text = intro + "\n".join(f"| {r['ecosystem']} | {r['name']} | {r['version']} | {str(r['license']).replace('|', '/').replace(chr(10), ' ')} |" for r in rows) + "\n"
(ROOT / "THIRD_PARTY_NOTICES.md").write_text(text, encoding="utf-8")
print(f"Recorded {len(rows)} installed dependency packages and retained available licence texts.")
