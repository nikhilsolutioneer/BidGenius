from pathlib import Path
from PIL import Image
import json

BASE = Path(__file__).resolve().parent
OUT = BASE / 'presentation_assets'
OUT.mkdir(exist_ok=True)
specs = {
    'overview': ('shots/crops/overview_top.png', (0, 0, 2032, 670)),
    'inspector': ('shots/crops/inspector_calc.png', (0, 0, 748, 910)),
    'scope': ('shots/crops/scope_pdf.png', (36, 368, 711, 740)),
    'scenario_cards': ('shots/crops/scenarios.png', (505, 807, 2016, 1117)),
    'scenario_chart': ('shots/crops/scenarios.png', (503, 179, 1255, 794)),
    'export': ('shots/export.png', (366, 565, 1710, 1170)),
}
dimensions = {}
for name, (src, box) in specs.items():
    im = Image.open(BASE / src).convert('RGB').crop(box)
    im.save(OUT / f'{name}.png', optimize=True)
    dimensions[name] = im.size
(OUT / 'dimensions.json').write_text(json.dumps(dimensions), encoding='utf-8')
print(json.dumps(dimensions))
