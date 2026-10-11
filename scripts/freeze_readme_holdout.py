"""Evaluation only: transcribed PDF rows, never production inputs."""
import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
rows = []
def add(system, page, snippet, quantity, unit='pc', context=''):
    rows.append(dict(id=f'R{len(rows)+1:03}', system=system, page=page,
                     source_snippet=snippet, quantity=str(quantity), unit=unit,
                     context=context, product_id=None))

# Values below were read from PDF text, without predicted positions or prices.
for system, page, lines in [
 ('LA01',75,[(4679,200,300),(8608,300,200),(2851,400,950),(4122,450,100),(2181,500,150),(11178,700,450),(920,950,400),(15720,1100,350)]),
 ('LA02',100,[(18000,200,400),(9880,350,300),(24522,350,400),(1904,350,500),(13961,400,200),(8215,400,350),(2685,400,400),(1663,450,700)]),
 ('LA03',131,[(3802,100,350),(11364,200,350),(7042,250,600),(2822,350,100),(19763,350,200),(7015,350,500),(6622,400,550),(6693,450,450)]),
 ('LA05',182,[(3350,150,700),(1140,150,740),(22894,200,600),(1856,600,200),(14281,700,150),(1930,740,200),(1951,740,250)]),
]:
    for length,a,b in lines:
        add(system,page,f'{length}L Luftleitung {a} {b}', Decimal(2)*(a+b)*length/Decimal(1000000),'m2')
for system,page in [('LA01',82),('LA02',110),('LA05',191)]:
    for snippet,qty in [('Drehantrieb, 20 Nm, Stk. 2',2),('Drehantrieb, 5 Nm Stk. 1',1),('Kanalrauchmelder Stk. 1',1),('Druckwächter Stk. 4',4),('Frostschutzwächter, 2-Punkt Stk 1',1),('Druckdifferenzfühler Stk 2',2)]:
        add(system,page,snippet,qty)
for system,page,snippet,qty,unit in [
 ('LA01',85,'mit Alu-Folie, gestiftet m2 18',18,'m2'),
 ('LA01',85,'mit Alu-Folie, gestiftet m2 220',220,'m2'),
 ('LA02',108,'Druckverlust 31Pa Stk 2',2,'pc'),
 ('LA02',108,'Farbpfeile Stk 100',100,'pc'),
 ('LA03',136,'250 100 150 Stk 2',2,'pc'),
 ('LA03',136,'100 10 28.5x20.5 27 Stk 2',2,'pc'),
 ('LA03',136,'Druckverlust 36Pa Stk 2',2,'pc'),
 ('LA03',133,'Nachweis dem Bericht beilegen Stk 2',2,'pc'),
 ('LA04',161,'Grösse (B x H) 17.5 x 49 x 24 cm Stk 24',24,'pc'),
 ('LA04',161,'Typ z.B. EBS-D-3-1 Stk 24',24,'pc'),
 ('LA04',161,'Grösse (B x H) 17.5 x 49 x 24 cm Stk 10',10,'pc'),
 ('LA04',161,'Typ z.B. EBS-D-3-1 Stk 10',10,'pc'),
 ('LA04',161,'Anschluss v. hinten 2 x 124 mm Stk 10',10,'pc'),
 ('LA04',161,'Anschluss v. hinten 2 x 179 mm Stk 12',12,'pc'),
 ('LA04',165,'Grösse ø 10 cm Stk 6',6,'pc'),
 ('LA04',165,'Grösse 40 x 20 cm Stk 20',20,'pc'),
 ('LA04',165,'Grösse 40x20 cm Stk 20',20,'pc'),
 ('LA04',165,'für Kanaleinbau Stk 4',4,'pc'),
 ('LA04',165,'Montagerahmen für isolierte Kanäle Stk 4',4,'pc'),
 ('LA04',165,'100 x 50 mm Stk 40',40,'pc'),
 ('LA04',165,'Farbpfeile Stk 150',150,'pc'),
 ('LA04',157,'1BS Bogen symmetrisch 400 350 90',1,'pc'),
 ('LA04',157,'4BS Bogen symmetrisch 450 200 90',4,'pc'),
 ('LA04',157,'1BS Bogen symmetrisch 450 350 90',1,'pc'),
 ('LA05',185,'Grösse Ø 10 cm Stk 8',8,'pc'),
 ('LA05',185,'Grösse Ø 10 cm Stk 14',14,'pc'),
 ('LA05',186,'Grösse (B x H) 40 x 10 cm Stk 4',4,'pc'),
 ('LA05',186,'Grösse (B x H) 50 x 10 cm Stk 10',10,'pc'),
 ('LA05',189,'Druckverlust 17Pa Stk 1',1,'pc'),
 ('LA03',131,'1BO Boden 100 350',1,'pc'),
 ('LA03',131,'2BO Boden 250 600',2,'pc'),
 ('LA03',131,'1BO Boden 350 100',1,'pc'),
 ('ROOF',197,'Montagefüsse z.B. Stk 150',150,'pc'),
 ('ROOF',197,'Montageschiene z.B. m 500',500,'m'),
]: add(system,page,snippet,qty,unit)
payload=dict(frozen_at=datetime.now(timezone.utc).isoformat(),
    purpose='Independent quantity/unit detection evaluation, not catalogue mapping ground truth.',
    annotation_method='Source text manually read; explicit row quantities transcribed; straight duct dimensions normalized by Decimal only.',
    limitations='Stratified purposive sample, not statistical completeness proof. Last two rooftop rows also exist in prior regression set; report separately. No holdout-based extraction tuning.',
    rows=rows)
target=ROOT/'tests/fixtures/readme_holdout.json'
if target.exists(): raise SystemExit('Frozen fixture already exists; refusing overwrite')
target.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(dict(rows=len(rows),sha256=hashlib.sha256(target.read_bytes()).hexdigest())))
