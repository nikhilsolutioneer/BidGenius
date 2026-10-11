# BidGenius AI rebrand verification

The latest logo refinement uses the complete official Equans Switzerland SVG, unchanged, with BidGenius AI and the slogan in a separate product block. The full logo moves to the header on mobile. Source and usage notes are in `frontend/public/brand/README.md`; the asset intentionally retains its original brand colours. `brand-lockup-1440.png` is the actual rendered sidebar branding, and `official-brand-*` captures show the desktop, tablet and mobile layouts.

The `before-*` screenshots capture the incomplete first rebrand at the start of this correction, not the original TenderProof UI. The original pre-rebrand screenshots were not captured by the earlier pass and cannot be reconstructed faithfully.

The `after-*` screenshots show the completed Equans theme. Each of Overview, Estimate (with evidence inspector open), Scenarios and Export has a 1440×900 and 390×844 viewport screenshot, plus a `-full.png` capture of the full page. `after-preview-1440x900.png` also shows the staged selling-price preview; no estimate changes were saved.

Validation:

- `npm.cmd run build`: passed, including TypeScript compilation.
- `npx.cmd playwright test tests/rebrand.spec.ts`: passed. Axe checks all four pages at both sizes, plus the desktop live preview. The test checks the actual page and a solid brightest-blend substitute for the navy/green hero gradients, which axe cannot otherwise reliably resolve.
- `after-contrast.json`: empty array means zero reported colour-contrast violations.
- All eight page/viewport states pass the document-width overflow assertion.
- Frontend colour literals are centralized in the CSS root tokens. No legacy hex/rgb colours remain in JSX.
- Roboto 400/500/700 is installed; Inter is removed. CSS and inline JSX text sizes are at least 12px; root size is 14px.
- No user-visible TenderProof text remains in frontend source or the HTML title. The two `tenderproof_project` matches are the preserved internal storage key, used by existing workspace tests and saved selections.
- German export template syntax parses successfully; the print header and colours are updated. Backend package names, API routes and export filename prefixes retain compatibility.

Visual review corrected the unreadable sidebar wordmark, conflicting blue theme rules, low-contrast price hints and sidebar footer, cramped workspace card, and overlapping mobile Export totals. No unresolved visual regressions were identified in the reviewed states. The dense Estimate table still uses its existing horizontal scrolling when the inspector reduces available width; the mobile inspector remains an overlay.

Reproduction: run the prepared backend on port 8001 and `npm.cmd run dev` in frontend (port 5173), then run the Playwright command above. The test routes API requests to the prepared backend. It only navigates and requests an unsaved preview; it does not import, approve, export, or apply changes to project data.
