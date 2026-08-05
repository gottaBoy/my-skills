---
name: zota-ui-modernization
description: Modernize and safely refactor Zota Web or hawkbit-updater-ui React interfaces built with Ant Design. Use for global UI consistency, typography, spacing, density, responsive layouts, light/dark themes, tables, filters, detail pages, dashboards, bilingual Chinese/English UX, accessibility, visual regression, or removal of deprecated Ant Design APIs without changing business behavior.
---

# Zota UI Modernization

Build a restrained, efficient OTA operations console while preserving business behavior, existing strengths, and bilingual support.

## Read First

- Read `references/design-system.md` before changing visual styles or shared components.
- Read `references/migration-and-validation.md` before editing more than one shared component or page.
- Run `scripts/audit-ui-drift.sh <project-root>` before and after a global modernization pass.
- Read the target repository `AGENTS.md`, current branch, worktree status, theme provider, global CSS, shared layouts, and affected pages before editing.

## Scope Rules

- Treat Ant Design theme tokens as the primary visual source of truth.
- Keep CSS variables only for domain semantic tokens that Ant Design does not express.
- Do not override broad `.ant-*` selectors with `!important` unless fixing an upstream defect that is documented and narrowly scoped.
- Preserve API calls, routing, permissions, mutations, polling, forms, and table behavior unless the user explicitly requests behavioral changes.
- Preserve the login page's independent brand art direction unless login is in scope.
- Support only Chinese and English; never mix languages inside one active locale.
- Use compliant product language. Do not claim autonomous-driving capability, safety guarantees, L4 readiness, or AI outcomes that the product does not prove.
- Do not introduce new UI frameworks when Ant Design and existing shared patterns can solve the task.

## Workflow

### 1. Establish the Baseline

1. Record `git status --short --branch` and protect existing changes.
2. Identify all applicable `AGENTS.md` files.
3. Run the audit script and save the report outside the repository or under `/tmp`.
4. Start from representative routes: dashboard, one list, one detail, one wizard/modal, login, and a mobile route.
5. Capture light, dark, desktop, and mobile screenshots before editing.

### 2. Consolidate the System

Apply changes in this order:

1. Theme tokens and semantic CSS variables.
2. Global element defaults and removal of broad Ant overrides.
3. Shared page shell, header, cards, filters, tables, forms, and detail layouts.
4. Dashboard and feature-specific components.
5. Page-level exceptions only when a shared pattern cannot express the need.

Never begin by patching many individual pages. Fix the highest shared ownership layer that accurately owns the behavior.

### 3. Protect Product Behavior

- Keep component props and public exports compatible during shared-component refactors.
- Retain loading, empty, error, data, disabled, permission-denied, and destructive-confirmation states.
- Keep URL state, query parameters, sorting, filtering, selection, pagination, refresh, and column settings working.
- Keep status meaning independent of color by retaining text or icons.
- Keep icon-only actions labelled with `aria-label` and a tooltip where meaning is not universal.

### 4. Verify in Layers

Run the gates from `references/migration-and-validation.md`:

1. Static drift audit.
2. TypeScript production build.
3. ESLint, separating pre-existing findings from regressions.
4. Route smoke tests with real local data where available.
5. Playwright desktop/mobile and light/dark visual checks.
6. Browser console and failed-request checks.
7. Interaction checks for search, filters, table actions, drawers, modals, forms, and locale switching.

Do not call a UI pass complete if the build passes but key routes are visually blank, clipped, overlapping, untranslated, or emit new console warnings.

## Completion Contract

Before finishing, report:

- Changed system layers and representative pages.
- Business behavior intentionally left unchanged.
- Build, lint, audit, Playwright, console, and network results.
- Any pre-existing failures or routes that could not be validated.
- Before/after screenshots or their paths for material visual changes.

Do not commit, create branches, start Docker, or replace existing user changes unless explicitly requested.
