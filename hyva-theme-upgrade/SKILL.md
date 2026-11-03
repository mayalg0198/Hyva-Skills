---
name: hyva-theme-upgrade
description: Use when upgrading a Hyvä child theme on Magento 2 / Adobe Commerce to a newer hyva-themes/magento2-default-theme or theme-module version (e.g. 1.4.x → 1.5.x), migrating its Tailwind CSS v3 config to v4 @theme, reconciling child template overrides with changed vendor templates, or debugging post-upgrade regressions (swatches not clickable, broken gallery, fg/ink tokens, @apply "Cannot resolve utility", BASE_URL is not defined, oxide/lightningcss ELF errors). Keywords hyva-upgrade.json, diff-template, audit-theme, gallery.additional.
---

# Hyvä theme upgrade

Runbook for moving a Hyvä child theme across Hyvä releases. Project settings
(version range, theme path, locales, URLs) live in `.hyva-upgrade.json` at the
Magento root.

**Not for:** strict-CSP conversion of templates (`registerInlineScript`,
`alpine3-csp.js`, cache-pressure tests) — use `hyva-compat-csp-update`. Magento
core upgrades (composer/PHP/DB) — only touch them as far as the Hyvä packages need.

## Running the tooling

`<skill>` below means this skill's base directory (shown when the skill loads,
e.g. `~/.claude/skills/hyva-theme-upgrade`). Always run from the Magento root and
call through `bash`:

```bash
cp <skill>/.hyva-upgrade.json.sample .hyva-upgrade.json   # once; then set from_version, to_version, themePath
bash <skill>/run.sh doctor          # env + config health — run first, fix every ❌
bash <skill>/run.sh help            # all flags
```

Every command accepts `--config <file>`: keep the config outside the project (e.g. in
`var/hyva-upgrade/`) and nothing needs excluding from git.

| Command | Purpose |
|---|---|
| `changelog [--module theme\|commerce]` | Breaking changes for `from_version` → `to_version` (from `references/changelog-*.md`) |
| `audit [--module X] [--lint-php]` | Version-gated scan: Alpine v2 directives, `*-opacity-*`, `-fg` tokens, bfcache/anti-spam guards |
| `vendor [--modified-only\|--identical-only] [--diff]` | Every child override vs its upstream template |
| `diff <Module_Name/templates/…phtml>` | One override vs upstream (exit 1 = differs, normal) |
| `layout [--fail-on-orphan]` | Layout XML references to removed/renamed blocks & containers |
| `i18n [--locale fr_FR]` | `__('…')` phrases missing from `i18n/*.csv` |
| `visual <path> [--viewport mobile]` | Screenshot + pixel diff `baselineUrl` vs `targetUrl` (needs Chrome + Pillow) |

**Build commands:** if the project `Makefile` has `npm_install` / `build` targets,
use them. Otherwise run `npm ci && npm run build` in `<themePath>/web/tailwind`
**inside the dev container** (`govard tool npm …`, `warden env exec …`) — never on
the host when the container is Alpine/musl (corrupts `@tailwindcss/oxide`,
`lightningcss`).

## Workflow

Work phase by phase; do not start a phase until the previous one's exit check passes.

1. **Impact analysis** — `run.sh changelog`, then read the matching sections of
   `references/changelog-theme-upgrade.md`. List every ⚠️ BREAKING item that
   touches a template the child theme overrides (`run.sh vendor --modified-only`).
   *Exit:* written list of affected overrides.
2. **Bump packages** (skip if `doctor` already reports the installed versions = `to_version`):
   ```bash
   composer require hyva-themes/magento2-default-theme:<to_version> hyva-themes/magento2-theme-module:<to_version> -W
   diff <(jq .dependencies <vendorThemePath>/web/tailwind/package.json) <(jq .dependencies <themePath>/web/tailwind/package.json)
   ```
   Copy upstream versions of `tailwindcss`, `@tailwindcss/cli`, `@hyva-themes/hyva-modules`
   into the child `package.json`, then reinstall npm deps in the container. Hyvä
   Commerce modules: same `composer require`, versions from `commerce_versions`.
   *Exit:* `run.sh doctor` clean, CSS build succeeds.
3. **Tailwind & tokens** — only if `from_version` < 1.4.0 (child still has
   `tailwind.config.js`): move it into `@theme` CSS. Crossing 1.5.2: add
   `--color-ink` / `--color-ink-muted` aliases and migrate `-fg` utilities.
   *Exit:* `run.sh audit` shows no token/opacity findings.
4. **Templates, one page flow at a time** — copy `references/upgrade-matrix-by-page.md`
   to `var/hyva-upgrade/matrix.md` (git-ignored) and track status there. Per flow: `run.sh diff` each override →
   port upstream changes (keep project customisations) → `run.sh layout` → build CSS
   → `run.sh i18n` → smoke test (add to cart, login, swatch on PDP).
   Overrides that are identical to upstream (`vendor --identical-only`) are
   candidates for deletion.
5. **Recompile & verify** — in the container:
   `bin/magento setup:upgrade && bin/magento cache:flush && bin/magento setup:di:compile`,
   then (production mode only) `bin/magento setup:static-content:deploy -f <locales>`;
   finally `run.sh visual <path>` on home, PLP, PDP, cart.
   *Exit:* `run.sh audit` exit 0, no console errors, CLS 0 on PDP/PLP.

## Git — the user commits, not you

- Never run `git add`, `git commit`, `git push`, `git stash` or `git reset` during
  an upgrade, even at the end of a phase. Report the changed files
  (`git status --short`) and let the user review and commit.
- Local-only files created by this workflow must never be staged:
  `.hyva-upgrade.json`, `var/hyva-upgrade/`, `var/diffs/` (visual diff output).
  If `run.sh doctor` warns that `.hyva-upgrade.json` is not ignored, tell the user
  the fix (`echo .hyva-upgrade.json >> .git/info/exclude`) instead of committing.

## Version milestones

| Crossing | What changes | Check |
|---|---|---|
| 1.4.0 | Tailwind v4: `tailwind.config.js` → `@theme` in CSS | `web/tailwind/package.json` `tailwindcss` major |
| 1.4.7 | bfcache form-key refresh, anti-spam `isSubmitting` guard | `run.sh audit` |
| 1.5.1 | PHP-rendered swatches & gallery, `.swatch-option`, `gallery.additional`, `tailwindcss >= 4.3` | Overrides of `Magento_Swatches`, `Magento_ConfigurableProduct`, `product/view/gallery.phtml` |
| 1.5.2 | `fg` → `ink` color tokens (aliases kept) | `run.sh audit` |

## Invariants — never break these

- Custom events: `dispatchMessages`, `reload-customer-section-data`, `toggle-cart`,
  `update-gallery-images`, `update-prices`.
- DOM hooks: `#product-addtocart-button`, `.swatch-option`, `[data-gallery-role=gallery]`.
- `cache:flush` between `setup:upgrade` and `setup:di:compile` (stale DI metadata
  poisons generated interceptors).
- If `cssFreeze` is `true` in `.hyva-upgrade.json`, do not edit `web/tailwind/**/*.css`
  during phase 4; fix CSS only in phase 3.
- A missing layout container (e.g. after `product.info.media` changes) orphans child
  blocks silently — `run.sh layout` after every vendor bump.

## When something breaks

Match the symptom in `references/troubleshooting-gotchas.md` (Tailwind v4 cascade /
`@layer` / `@apply`, swatches, gallery, CMS cache, ELF/musl, `deployed_version.txt`
newline). Commerce module notes: `references/changelog-commerce-modules.md`.
CSP- and FPC-related symptoms belong to `hyva-compat-csp-update`.

## Changing the tooling

After editing any script: `python3 -I <skill>/evals/run_evals.py` (offline, 21 checks on a
generated fixture project). Overrides of modules whose `registration.php` lives under `src/`
(e.g. `magento2-hyva-checkout`) must appear in `run.sh vendor` — the suite guards that.
