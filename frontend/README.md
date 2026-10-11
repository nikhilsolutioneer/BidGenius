# BidGenius AI frontend

React/TypeScript estimator workspace, built with Vite, Tailwind CSS, Radix Dialog, TanStack Table, Lucide, and PDF.js. Fonts and the PDF worker are bundled locally. Financial values and revisions come from the Python backend.

From this directory on Windows:

```powershell
npm.cmd ci
npm.cmd run build
```

The backend serves `dist/`. For development, `npm.cmd run dev` proxies `/api` to port 8000; update `vite.config.ts` if using a different development backend port.

Browser verification requires a running BidGenius AI backend and a processed actual tender:

```powershell
npm.cmd exec playwright -- install chromium
$env:PLAYWRIGHT_BASE_URL = 'http://127.0.0.1:8000'
npm.cmd test
```

`workspace.spec.ts` performs real reversible edits: position correction, manual recovery, adjustment approval, requirement review, and corresponding reversals. It also verifies PDF evidence, scenarios, exports, and responsive layout. `accessibility.spec.ts` audits the rendered workspace with axe and captures desktop/tablet/mobile screenshots. It does not claim exhaustive accessibility conformance.

Screenshots are written to `test-artifacts/`. Playwright saves failure traces and an HTML report. Core domain types are generated from Pydantic in `src/generated/contracts.ts`; regenerate them using the root `scripts/generate_contracts.py` after backend contract changes.

No API credentials are requested or stored by the frontend. Set credentials in the server's local `.env` file.
