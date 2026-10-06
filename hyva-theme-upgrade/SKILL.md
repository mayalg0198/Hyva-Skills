---
name: hyva-theme-upgrade
description: Upgrades a Hyvä Theme child theme on Magento 2 / Adobe Commerce across major version bumps (e.g. 1.4.x to 1.5.x), migrates Tailwind CSS from v3 to v4, aligns templates with upstream vendor diffs, validates i18n dictionaries, and resolves CSS cascade or specificity regressions. Use when upgrading Hyvä Theme versions, auditing child theme templates for Alpine v3 compliance, checking vendor template diffs, or debugging regressions in product swatches, gallery, checkout, or search popups. Keywords hyva-theme, theme-upgrade, tailwind-v4, hyva-upgrade.json, diff-template, audit-theme, gallery.additional, ink-tokens.
---

# Hyvä theme upgrade

Version-aware runbook for upgrading any Hyvä child theme on Magento 2 / Adobe
Commerce. This file is the entry point; the detail lives in `references/`.

The upgrade workflow handles Hyvä Theme Module and Default Theme version bumps,
the Tailwind CSS v3 to v4 transition, and Hyvä Commerce module alignment across
all storefront page flows. Configuration and target versions are defined in
`.hyva-upgrade.json`.

## References

- `references/upgrade-matrix-by-page.md` — the 7 Page Flows × 5-step SOP
  (Homepage, Category/PLP, Product/PDP, Cart/Mini-cart, Checkout, Customer
  Account, Search & CMS), template override checklists, and required event
  contracts.
- `references/troubleshooting-gotchas.md` — deep-dive root causes and verified
  fixes for 17 upgrade regressions: PHP-rendered swatches, gallery breakage,
  Tailwind v4 `@theme` migration traps, container musl/glibc issues, and poisoned
  DI compilation.
- `references/changelog-theme-upgrade.md` — upstream breaking changes across
  Hyvä Theme releases from 1.3.x through 1.5.x, including CSS token shifts,
  layout handle renames, and container changes.
- `references/changelog-commerce-modules.md` — breaking changes and compatibility
  notes for Hyvä Enterprise and Adobe Commerce modules (B2B, quick-order,
  live-search).

## Upgrade workflow

The upgrade follows a structured 5-phase execution sequence:

1. **Changelog & impact analysis**: Run `./run.sh changelog` to fetch breaking
   changes scoped precisely to `from_version` → `to_version`. Read the version
   milestones to understand architectural shifts before modifying any templates.
2. **Environment verification**: Install dependencies inside the development
   container via `make npm_install`. Verify CSS build succeeds with `make build`
   and launch the dev watcher.
3. **Design tokens & Tailwind v4 migration**: If crossing 1.4.0+, migrate
   `tailwind.config.js` to `@theme` CSS-first configuration. Alias legacy design
   tokens (`fg` → `ink` for 1.5.2+) in theme CSS.
4. **Template alignment by page flow**: Walk through the 7 page flows in order.
   For each flow, execute the 5-step SOP: scan legacy directives, compare child
   overrides against vendor diffs (`./run.sh vendor`), update layout XML references,
   rebuild CSS, and run i18n audits.
5. **Rebuild & verification**: Execute full DI compilation and static content
   deployment (`make build && php bin/magento setup:di:compile`). Validate with
   visual diffs and verify zero console errors and zero CLS.

## CLI tooling

The automated runner lives at `.agents/skills/hyva-theme-upgrade/run.sh`:

- `./run.sh doctor` — verify environment tooling (PHP, Node, Python, jq) and configuration.
- `./run.sh changelog` — fetch breaking changes between configured version bounds.
- `./run.sh audit` — pre-flight scan of the child theme for deprecated directives and tokens.
- `./run.sh vendor` — inspect upstream vendor template diffs for customized overrides.
- `./run.sh layout` — scan for orphaned layout XML references.
- `./run.sh i18n` — audit multi-locale translation dictionary coverage.
- `./run.sh visual-diff <slug>` — headless Chrome pixel diff against baseline URL.

Before running any script, copy `.agents/skills/hyva-theme-upgrade/.hyva-upgrade.json.sample`
to `.hyva-upgrade.json` in the project root and configure `from_version`, `to_version`,
and `themePath`.

## Architectural milestones

- **Hyvä 1.4.0 (Tailwind v4)**: Replaces `tailwind.config.js` with `@theme`
  CSS-first syntax. Detect Tailwind version from `web/tailwind/package.json`.
- **Hyvä 1.5.1 (Swatches & Gallery)**: Shifts swatch and gallery rendering to
  server-rendered PHP. Requires `tailwindcss >= 4.3` and adopts the
  `gallery.additional` layout container.
- **Hyvä 1.5.2 (Design Tokens)**: Renames foreground color tokens from `fg` to
  `ink`. Add `--color-ink` and `--color-ink-muted` aliases in theme CSS.

## Pitfalls

- Never run `npm` on a glibc host when the development container runs Alpine/musl.
  Native binary mismatches corrupt `@tailwindcss/oxide`. Always run build tools
  inside the container via `make npm_install`, `govard tool npm`, or `warden env exec`.
- Do not modify `web/tailwind/**/*.css` during template alignment. Theme CSS
  should be frozen once tokens are migrated; run `make build` to confirm output.
- Never alter or rename core Hyvä custom events: `dispatchMessages`,
  `reload-customer-section-data`, `toggle-cart`, `update-gallery-images`, and
  `update-prices`. External modules and checkout rely on these exact event names.
- Never remove required DOM hooks and selectors: `#product-addtocart-button`,
  `.swatch-option`, and `[data-gallery-role=gallery]`.
- Always flush Magento cache between `setup:upgrade` and `setup:di:compile`.
  Compiling with stale DI metadata poisons the generated interceptors.
- Check layout XML references after vendor updates: container renames (such as
  `product.info.media` adjustments) can leave child layout blocks orphaned with
  no visual error.
- Strict CSP conversion is out of scope for general theme upgrades unless
  explicitly configured. For strict CSP templates and `registerInlineScript`
  wiring, use the companion skill `hyva-compat-csp-update`.
