# Hyvä implementation rules & checklist (generic)

Rule IDs (`ALP-1`, `TW-3` …) let reports cite them. Project rule files found by `detect.py`
(e.g. `.agents/skills/_shared/hyva-rules.md`, `CLAUDE.md`) **override** this file where they differ.

Blocks wrapped in HTML comments of the form `if csp=…`, `if tw=…`, `if hyvacsp=…` are filtered by
`scripts/rules.py` (read its output, not this raw file). Two switches from `detect.py` decide which variant applies:

- **CSP strict** = a theme chain ends in `-csp`, **or** most local `<script>` templates already call
  `registerInlineScript` (e.g. 265/300), **or** the project has a CSP gate (`make verify`/`csp-gate`).
  Otherwise **CSP-ready** (standard Alpine build; CSP style is a convention, not a requirement).
- **TW3** (`tailwind.config.js`, `tailwindcss ^3`) vs **TW4** (`tailwind-source.css` + `@theme`/`@utility`,
  `hyva.config.json` tokens, `tailwindcss ^4`).

---

## 1. Alpine.js

### ALP-1 Directive values are property or method paths only
<!--if csp=strict-->**[bug]** here: the CSP Alpine build throws "Alpine is unable to interpret…". Applies to code you write or touch; do not rewrite unrelated legacy expressions.
<!--/if--><!--if csp=ready-->**[convention]** here (standard Alpine build): write new/touched code this way so the CSP theme can be adopted later; do not rewrite unrelated legacy expressions.
<!--/if-->

| Instead of | Write |
|---|---|
| `@click="open = !open"` | `@click="toggle"` + `toggle() { this.open = !this.open; }` |
| `@click="toggle()"` / `@click="select(item.id)"` | `@click="toggle"` / `@click="select"` + read `this.$el.dataset` / loop var via `$data` |
| `x-show="!open"` / `x-show="count > 5"` | `x-show="isClosed"` / `x-show="hasMany"` + getter |
| `:class="open ? 'block' : 'hidden'"` | `:class="visibilityClass"` + getter |
| `x-text="'Hello ' + name"` | `x-text="greeting"` + getter |
| `@click="$dispatch('evt')"` | `@click="notify"` + `notify() { this.$dispatch('evt'); }` |
| `x-data="dropdown(true)"` / `x-data="{ open: false }"` | `x-data="dropdown"` + options from `data-*` in `init()` |
| `x-for="i in 10"` | `x-for="i in tenItems"` |

<!--if csp=strict-->For deep conversions or CSP console errors, load the `hyva-compat-csp-update` skill.
<!--/if--><!--if csp=ready-->An unresponsive button is **not** a CSP symptom here — check console errors, `x-data` scope, component registration, stale build.
<!--/if-->

### ALP-2 Component registration
```html
<script>
    function initMyComponent() {
        return {
            open: false,
            init() { this.endpoint = this.$el.dataset.endpoint; },
            toggle() { this.open = !this.open; },
        };
    }
    window.addEventListener('alpine:init', () => Alpine.data('initMyComponent', initMyComponent), {once: true});
</script>
<?php $hyvaCsp->registerInlineScript() ?>
```
<!--if hyvacsp=yes-->- `$hyvaCsp` is injected in every template: call `$hyvaCsp->registerInlineScript()` right after **each** `</script>` (**[bug]** if CSP strict).
<!--/if--><!--if hyvacsp=no-->- No HyvaCsp viewmodel in this project: write `<?php isset($hyvaCsp) && $hyvaCsp->registerInlineScript() ?>` (harmless no-op). **[bug]** never `$viewModels->require(HyvaCsp::class)` — fatal error.
<!--/if-->

### ALP-3 Static `<script>` bodies
No per-render PHP values (URLs, IDs, store codes, translations, form keys) inside `<script>`:
put them in `data-*` on the component root and read `this.$el.dataset` in `init()`. CSP strict →
<!--if csp=strict-->**[bug]** here (hash changes per render, FPC CSP header grows; a project `csp-gate` fails).<!--/if-->
```html
<div x-data="initMyComponent"
     data-endpoint="<?= $escaper->escapeUrl($block->getUrl('route/path')) ?>"
     data-items="<?= $escaper->escapeHtmlAttr(json_encode($items)) ?>">
```

- **ALP-4 [bug] Loop scope.** In `<template x-for="item in items">`, `this.item` is undefined in methods.
- **ALP-5 [bug]** `<template>` has exactly one root element, every tag closed.
- **ALP-6 [bug]** `x-cloak` on anything hidden until Alpine boots (modal, drawer, dropdown).
- **ALP-7** Heavy below-the-fold widgets: `x-defer="intersect"` / `x-defer="idle"` (Hyvä ≥ 1.3.x defer plugin).
- **ALP-8** Prefer Hyvä built-ins before writing JS: `hyva.formatPrice`, `hyva.getFormKey`,
  `hyva.trapFocus`/`releaseFocus`, private-content `reload-customer-section-data`, the Hyvä
  `Modal` ViewModel (`$viewModels->require(Modal::class)->createModal()`) and slider snippets
  already used in the theme.

---

## 2. Tailwind & design tokens

- **TW-1 [bug] No dynamic class names** (`'grid-cols-' . $n` is purged). Use a map of literals:
  `$map = [2 => 'grid-cols-1 md:grid-cols-2', 3 => 'grid-cols-1 md:grid-cols-2 lg:grid-cols-3'];`
- **TW-2 Tokens first.** Figma text style → the project's text classes / `@utility` (listed by
  `detect.py`), colours → theme colours (`text-primary`, `bg-neutral-3`, TW4 `--color-*`).
  Arbitrary values (`text-[32px]`, `text-[#e84127]`) only when nothing matches — and list them in
  the report.
<!--if tw=3-->- **TW-3 [bug] Spacing scale.** Only the default scale exists — `mt-12.5`, `right-3.75` silently generate nothing → use `mt-[50px]` (`scripts/tokens.py space --px 50 --prop mt`).
- **TW-4 [bug] Important modifier** is a prefix: `!hidden`, `md:!text-center` (not `hidden!`).
- **TW-5 Where custom CSS goes.** `@layer components` in `web/tailwind/components/*.css`; one selector block per component; no duplicates.
<!--/if--><!--if tw=4-->- **TW-3 Spacing scale.** Any multiple of `--spacing` works (`mt-12.5` = 50px); use arbitrary values only off-grid (`scripts/tokens.py space --px 50 --prop mt`).
- **TW-4 Important modifier** is a suffix: `hidden!` (prefix still accepted, deprecated).
- **TW-5 Where custom CSS goes.** `@utility` / `@layer components` in the theme CSS files; design tokens in `hyva.config.json` → run the `generate` script (`hyva-tokens`) after editing it. One selector block per component; no duplicates.
<!--/if-->
- **TW-6 Rebuild after adding classes.** A class that "does nothing" usually means a stale build.
- **TW-7 Breakpoints.** Figma mobile (≈375) → unprefixed, tablet → `md:`, desktop (1280–1440) →
  `lg:`/`xl:` per the project `screens`. Mobile-first always.

---

## 3. Templates (.phtml)

- **TPL-1 No business logic.** Queries/calculations in a Block or ViewModel
  (`$viewModels->require(MyViewModel::class)`).
- **TPL-2 [bug] Escaping**: HTML text `escapeHtml`, attribute `escapeHtmlAttr`, `href`/`src`
  `escapeUrl`, inside JS string `escapeJs`, array → `data-*` `escapeHtmlAttr(json_encode($a))`.
- **TPL-3 Translations.** `$escaper->escapeHtml(__('...'))` and add the string to the theme's or
  module's `i18n/*.csv` (all locales `detect.py` lists when the wording differs).
- **TPL-4** Accurate `/** @var */` docblocks (`$block` = class declared in layout XML,
  `$escaper`, `$viewModels`, `$hyvaCsp`, `$heroicons`).
- **TPL-5** No dead reads (`$block->getData('x')` never used).
- **TPL-6 Icons & images.** Heroicons via `$heroicons = $viewModels->require(HeroiconsOutline::class)`
  → `$heroicons->chevronDownHtml('w-4 h-4', 16, 16)` (camelCase of the SVG file name). Theme SVG
  icons via `SvgIcons` (`$svgIcons->renderHtml('name', 'w-6 h-6')`) from `web/svg/`. Reuse only
  **exact** matches; otherwise add the Figma-exported asset to `web/images|svg/` and reference it with
  `$block->getViewFileUrl('images/x.svg')`. Images: `width`/`height`, `loading="lazy"` below the fold.
- **TPL-7 Overriding a core/Hyvä template.** Copy the **vendor version of the installed release**,
  then change; list every CTA/action you drop and confirm it is intended by Figma.
- **TPL-8 CTA fallback.** Links that trigger Alpine keep a valid `href`.

### Accessibility & SEO
- **A11Y-1** Semantic elements (`section`, `article`, `nav`, `header`, `footer`, `button`).
- **A11Y-2** One `h1` per page; no skipped heading levels — Figma's visual size ≠ heading level.
- **A11Y-3** Meaningful `alt`; decorative → `alt=""` + `aria-hidden="true"`.
- **A11Y-4** Custom interactive elements: role, `tabindex="0"`, accessible name, keyboard handlers;
  prefer `<button>`. Visible focus (`focus-visible:ring-*`). Touch targets ≥ 24×24 px.
- **A11Y-5** `target="_blank"` → `rel="noopener noreferrer"`.

---

## 4. Layout XML & PHP

- **PHP-1 Trace before editing.** Layout XML → Block/ViewModel → `.phtml` → children.
- **PHP-2 [bug]** `referenceContainer` for containers (`main`, `content`, `page.top`, `footer`…),
  `referenceBlock` for blocks — check how the target is declared.
- **PHP-3 [bug]** `addChild($alias)` registers `<parentName>.<alias>` → use `getChildBlock($alias)`.
- **PHP-4 [bug] Widget booleans**: "No" is stored as `'0'`, so read `(bool) $this->getData('x')`.
- **PHP-5** New boolean widget param defaulting to "Yes": `!$this->hasData('x') || (bool) $this->getData('x')`.
- **PHP-6** Restore mutated shared state in `finally`; memoize repeated getters.
- **PHP-7 N+1.** Load attributes, images, prices, ratings on the collection before rendering.
- **PHP-8 Cache.** ViewModels loading entities shown under FPC implement `IdentityInterface`.
- **PHP-9 `widget.xml`**: `label`, `description`, `depends` first; numeric fields validated and clamped in PHP.
- **PHP-10 Clean code.** `declare(strict_types=1)`, typed properties/returns, constructor DI,
  no `createBlock()` / ObjectManager, no unused imports; project copyright header if `CLAUDE.md` asks.
- **PHP-11** Sanitize layout handles built from identifiers: `preg_replace('/[^a-z0-9_]/', '_', strtolower($id))`.
- **PHP-12** Scripts a component needs are declared for every layout handle it appears on.

For module scaffolding, DI, repositories → `magento2-dev-core`.

---

## 5. Completion checklist

Copy into the final message; tick only what you actually verified.

- [ ] **Traced** layout XML → block/ViewModel → template (PHP-1)
- [ ] **Alpine**: ALP-1 (strict or convention), every inline script registered (ALP-2), static scripts (ALP-3), `x-cloak`
- [ ] **Escaping & i18n**: TPL-2; new strings in every needed `i18n/*.csv` (TPL-3)
- [ ] **Tailwind**: no dynamic classes (TW-1), tokens used (TW-2), spacing valid for TW3/TW4 (TW-3), CSS rebuilt
- [ ] **Assets**: every Figma asset in place, local, right size; no temporary Figma URLs
- [ ] **Layout/PHP**: PHP-2 … PHP-12 for the files touched; DI compiled if classes/plugins added
- [ ] **Caches flushed** (`cache:flush layout block_html full_page`)
- [ ] **Browser** at mobile / `md` / desktop: matches the Figma screenshot, no console errors, interactions and empty states work
- [ ] **Quality gate**: project gate (`make verify`, project lint skill) or `magento2-linter` on changed files — 0 new errors
