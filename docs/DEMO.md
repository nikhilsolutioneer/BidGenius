# BidGenius AI — Five-minute demonstration

Use the timestamped **Prepared demo** project. The preparation script imports the supplied tender with the local parser, leaves estimator decisions untouched, confirms that commercial history and scenario overrides are empty, and exports the current revision. The app opens this pinned project by default and shows its preparation time in the project bar.

| Time | Action and point |
|---|---|
| 0:00–0:35 | Start on Overview. Lead with the priced offer, then show completeness: pages processed, extracted, priced and unpriced counts, and any partial-page warning. Explain that page coverage does not prove every tender position was found. |
| 0:35–1:45 | Open one AHU position and follow it end to end: select the highlighted PDF evidence, inspect the tender airflow, review the catalogue size-up and provisional supplier reference, then show the quote-required flag and trace labour through its productivity rule, role rate and unrounded hours. Call out any one-unit quantity assumption where the tender quantity is blank. |
| 1:45–2:25 | Open a priced duct-schedule row such as LA01 p.75 #9. Show the source dimensions, area and material formula, catalogue rate, and installation productivity rule. Then open the adjacent LT fitting #11: its geometry is a provisional takeoff and its direct price is unknown until a supported rate or supplier quote is accepted. |
| 2:25–3:10 | Open What-if. Move one named control and let the live preview show the material, labour, hours, baseline, selling-price and scenario deltas. Apply only if useful, with a reason; otherwise reset the preview. |
| 3:10–4:10 | Open Scenarios. Show the reference price and margin used by the probability model, compare them with the package defaults, and explain any visible override. Read one “Why this recommendation” line as a comparison of bid price, margin, illustrative probability and expected contribution. These values are assumption-based, not an optimality claim. |
| 4:10–5:00 | Open Export and download the ZIP for the current draft revision. Point out the source evidence, pricing build-up, unresolved scope, assumptions and scenario snapshot included for handover. |

Prepare a fresh project through the app process that owns the data directory. BidGenius AI locks a data directory to one server process. If the app is already running on port 8000, use it directly:

```bat
.venv\Scripts\python.exe scripts\prepare_demo.py --base-url http://127.0.0.1:8000
```

For a spare-port rehearsal, start BidGenius AI on port 8001 when no other process is using that data directory, then pass `--base-url http://127.0.0.1:8001` to the script.

The script always creates a new project and never deletes or edits saved projects. It writes `artifacts/prepared-demo.json` with the project ID, UTC timestamp, page/position coverage, financial totals, default commercial context and ZIP export details. The app uses that manifest to choose the default project when it exists in the active data store.

## Explain the commercial edge

The estimator can defend quantities, prices, installation labour, allowances and review decisions. Scope ownership prevents repeated installation or commissioning charges. Provisional supplier prices stay provisional; unknown quantities stay unknown. Missing drawings/Excel, incompatible references and the LA05 heading error remain visible. The app supplies an inspectable first price and a handover package, with no claim of a completed procurement submission.

## Fallback

If internet or OpenAI is unavailable, use the prepared local run. PDF inspection, revisions, calculations, scenario comparisons and export operate offline. Do not claim a live model call. If a processing run is interrupted, use Resume and show the preserved batch progress.
