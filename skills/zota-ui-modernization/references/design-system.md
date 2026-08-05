# Zota Web Design System

## Product Character

Zota Web is an OTA operations console for intelligent-driving heavy-truck systems. Make it technical, calm, precise, and work-focused. Favor fast scanning and repeated operation over marketing decoration.

## Source of Truth

Use Ant Design `ConfigProvider` theme tokens for component-wide values. Define a small semantic layer only for domain concepts such as rollout state, device health, and chart series. Do not maintain parallel typography, spacing, radius, and shadow systems.

## Typography

Use the existing cross-platform Chinese/English system font stack.

| Role | Size | Weight | Line height |
|---|---:|---:|---:|
| Page title | 22px | 600 | 1.35 |
| Compact functional title | 18px | 600 | 1.35 |
| Section title | 16px | 600 | 1.4 |
| Card/table title | 14px | 600 | 1.5 |
| Body and controls | 14px | 400 | 1.57 |
| Secondary table text | 13px | 400 | 1.5 |
| Metadata and helper text | 12px | 400 | 1.5 |

- Prefer weights `400` and `600`; use `500` only for navigation or compact labels.
- Avoid routine `10px` and `11px` text.
- Use monospace only for IDs, versions, hashes, timestamps, addresses, and code-like values.
- Do not uppercase ordinary labels or add negative letter spacing.

## Spacing and Density

Use only `4, 8, 12, 16, 24, 32` as the normal spacing ladder.

- Desktop page padding: `16px`, expanding to `24px` when content width permits.
- Mobile page padding: `12px`.
- Default card padding: `16px`.
- Compact toolbar padding: `8px 12px`.
- Section gap: `16px` or `24px`.
- Default control height: `32px`; large form or primary action: `40px`.
- Application header: `52px`; compact functional title bars: `36-44px`.
- Desktop data row: `40px`; detail description row: `38-40px`.
- Mobile interactive hit target: at least `44px`, even when the visible control is smaller.

Do not use full-height cards merely to fill the viewport. Let short tables end naturally and provide an intentional empty or summary region when useful.

## Radius, Border, and Elevation

- Page cards and panels: `8px`.
- Buttons, inputs, and selects: `6px`.
- Modals and drawers: `8-12px`.
- Tags: `4-6px`; use pill radius only for compact semantic status.
- Use one-pixel neutral borders for ordinary containment.
- Reserve shadows for overlays, popovers, sticky controls, and active elevation.
- Do not nest decorative cards inside cards. Use dividers, bands, or unframed grids for internal sections.

## Color

- Use primary blue for navigation, focus, links, and primary actions.
- Use green, cyan/blue, amber, and red only for semantic states.
- Pair every status color with text or an icon.
- Keep page backgrounds neutral in light and dark themes.
- Avoid a one-note blue/slate dark theme; retain neutral gray separation.
- Avoid gradients, glow, glass effects, strong colored shadows, and animated shine in the operations console.

## Motion

- Use `120-160ms` color, border, opacity, or shadow transitions.
- Avoid hover translation for frequently repeated cards and buttons.
- Never let hover change dimensions or shift neighboring content.
- Respect `prefers-reduced-motion`.

## Shared Patterns

### Page Header

Keep the title, concise subtitle, and primary actions aligned in one hierarchy. Wrap actions below the title on narrow screens. Do not repeat product explanations inside the page.

- Render generic feature descriptions inline after the page title with a subtle divider.
- Hide generic descriptions on narrow mobile screens when the title already identifies the workflow.
- Put the mobile section-navigation trigger in the title row instead of allocating another toolbar row.

### Filter Toolbar

- Place filter/search controls on the left and commands on the right.
- Keep search flexible with sensible min/max width.
- Move status counters to a secondary group and reduce them on mobile.
- Allow filter chips to wrap or scroll without squeezing the search input.
- On mobile, show the primary search/action row first and make detailed filters expandable.

### Tables

- Use deliberate column widths and `ellipsis` for long values.
- Keep names flexible; keep status, time, numeric, and operation columns stable.
- Use the shared table implementation for density, loading, empty state, selection, pagination, and horizontal scrolling.
- Avoid oversized empty table containers.

### Detail Pages

Use one primary information surface. Build internal metric and metadata sections with unframed grids or subtle background bands. Keep Descriptions density aligned with tables.

### Dashboard

Treat it as a monitoring workspace, not a collection of promotional cards. Keep key metrics compact, hover behavior identical, chart dimensions stable, and operational exceptions visually stronger than decorative summaries.

## Responsive and Accessibility

- Validate at `1440x900`, `1024x768`, `768x1024`, and `390x844` or equivalent representative viewports.
- Prevent horizontal page overflow; allow deliberate table-local scrolling.
- Keep keyboard focus visible in light and dark themes.
- Preserve semantic headings, labels, `aria-label`, tooltips, and error messages.
- Check Chinese expansion, English word length, empty values, large counts, and long IDs.
