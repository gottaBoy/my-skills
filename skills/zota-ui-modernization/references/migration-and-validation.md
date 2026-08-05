# Migration and Validation Gates

## Migration Order

1. Record the current branch, dirty files, build status, screenshots, console output, and representative API state.
2. Consolidate light/dark token files and remove conflicting global component overrides.
3. Normalize shared layouts, page headers, section cards, filters, tables, forms, descriptions, and status tags.
4. Migrate dashboards and feature-specific wrappers onto shared tokens.
5. Remove page-level hardcoded values only after the shared replacement exists.
6. Recheck login separately so console density changes do not damage its brand layout.

Keep each patch behavior-preserving and small enough to diagnose. Do not mix API refactors with visual refactors.

## Static Gate

Run:

```bash
.github/skills/zota-ui-modernization/scripts/audit-ui-drift.sh hawkbit-updater-ui
```

Review every new broad Ant selector, `!important`, tiny font, oversized radius, deprecated property, and hardcoded visual value. The report is diagnostic; justified exceptions are allowed.

## Build and Lint Gate

From the frontend root:

```bash
npm run build
npm run lint
```

Build must pass. Lint must not gain new errors. If the repository already has lint debt, record the baseline and prove changed files do not add findings.

## Browser Gate

Use the actual local frontend and backend when available. Do not start Docker unless explicitly requested.

Validate at least:

- Login.
- Dashboard.
- One target/device list.
- One distribution/software-module list.
- One rollout list and rollout detail.
- One software-module detail.
- One modal, drawer, or wizard.

For each route, check:

- No blank main content.
- No overlap, clipping, accidental horizontal page scroll, or unstable layout shift.
- Loading, empty, error, and populated states remain understandable.
- Search, clear, filter chips, refresh, column settings, pagination, row actions, and navigation still work.
- Destructive commands still require confirmation.
- Chinese and English switch without mixed active-locale text.

## Playwright Gate

Capture desktop and mobile screenshots in light mode, plus representative dark-mode screenshots. Use element measurements when visual judgment is ambiguous.

Record browser console messages and failed requests. Fail the gate for new:

- React render/runtime exceptions.
- Ant Design deprecation or disconnected-form warnings.
- Recharts zero-width/zero-height warnings.
- Missing translation keys or mixed-language labels.
- Unexpected 4xx/5xx requests caused by the UI change.

Ignore only understood environmental noise and document it.

## Regression Checklist

- Theme switching preserves contrast and focus states.
- Locale switching preserves layout and all user-facing strings.
- Header and side navigation remain usable at desktop and mobile widths.
- Table columns remain readable at common widths.
- Tags, badges, and status cards use consistent semantic meaning.
- Hover states are consistent and do not move layout.
- Charts have explicit stable container dimensions.
- Modals, drawers, dropdowns, and tooltips remain within the viewport.
- Existing authentication and authorization behavior is unchanged.
- Existing dirty files not owned by the task remain intact.
