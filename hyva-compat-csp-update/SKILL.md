---
name: hyva-compat-csp-update
description: Use when making Hyvä templates (compat modules, app/code modules, theme overrides) work under strict Content Security Policy without unsafe-eval or unsafe-inline on Magento 2 — e.g. "Alpine is unable to interpret the following expression using the CSP-friendly build", inline scripts blocked by script-src, missing registerInlineScript / $hyvaCsp, x-data object literals, @click with arguments, ternaries in bindings, or CSP header growth under Full Page Cache. Keywords alpine3-csp.js, hyvaCsp, registerInlineScript, Alpine.data, unsafe-eval, magento2-default-theme-csp.
---

# Hyvä strict CSP conversion

Converts Hyvä templates so they run with the CSP Alpine build (`alpine3-csp.js`) and
without `unsafe-inline`. Converted templates still work on non-CSP stores, so the
conversion can be done before CSP is switched on.

**Not for:** Hyvä version upgrades or Tailwind migration — use `hyva-theme-upgrade`.

## Running the tooling

`<skill>` = this skill's base directory (shown when the skill loads). Run from the
Magento root, always through `bash`:

| Command | Purpose |
|---|---|
| `bash <skill>/run.sh doctor` | Python, project root, CSP theme packages |
| `bash <skill>/run.sh audit <dir> [--fail-on-warning]` | CSP anti-patterns + unregistered inline scripts per template |
| `bash <skill>/run.sh suggest <file.phtml>` | Refactor recipe for each finding in one template |
| `bash <skill>/run.sh fix-scripts <dir> --dry-run` | Preview `registerInlineScript()` insertion — **always dry-run first** |
| `bash <skill>/run.sh fix-scripts <dir> [--guarded] [--normalize]` | Apply it; `--guarded` = isset() form for modules that also render on Luma; `--normalize` rewrites `$viewModels->require(HyvaCsp::class)->registerInlineScript()` to `$hyvaCsp->…`. Scripts whose text changes per render are **not** registered and are listed. (writes files, `php -l` each, reverts on lint failure; refuses `vendor/`, `var/`, `generated/`) |
| `bash <skill>/run.sh test-pressure <local-url> [--flush-cmd "<cmd>"] [--insecure]` | Cold/warm FPC test of the CSP header — **local env only** (90 requests). In a container use e.g. `--flush-cmd "govard tool magento cache:clean full_page"` |

## Workflow

1. `doctor`, then `audit` the target directory. Work one module or page flow at a time.
2. `fix-scripts --dry-run`, review the diff, then apply. Read every touched template.
3. For each remaining finding run `suggest`, then refactor using the rules below and
   `references/alpine3-csp-rules.md` (one recipe per anti-pattern).
4. Re-run `audit --fail-on-warning` on the directory until it exits 0.
5. In the browser, the console shows no
   `Alpine is unable to interpret`, no `Refused to execute inline script`, and no
   `unsafe-eval` violation. Click through every converted component.
   The CSP Alpine build is only loaded by a theme based on Hyvä's CSP theme
   (`hyva-themes/magento2-default-theme-csp`); on the regular theme converted
   templates keep working with normal Alpine, so check there too. Magento's storefront
   CSP is report-only by default; to enforce it on a **local** env:
   `bin/magento config:set csp/mode/storefront/report_only 0 && bin/magento cache:flush`
   (run inside the container; tell the user, as it changes their local config).
6. Report the changed files (`git status --short`). **Never** run `git add`, `commit`,
   `push` or `stash` — the user reviews and commits.

## Rules the CSP evaluator imposes

`alpine3-csp.js` resolves every directive value with `expression.split('.')` lookups
on the component scope. A directive value may therefore only be a **property or
method name path**: no parentheses, operators, literals, or `!`.

| ❌ Not allowed | ✅ Write instead |
|---|---|
| `@click="toggle()"`, `@click="select(item.id)"` | `@click="toggle"`; pass context via `data-*` → `event.currentTarget.dataset` |
| `x-show="!open"`, `a && b`, `a === 'x'`, `a ? b : c` | Getter: `x-show="isClosed"` + `get isClosed() { return !this.open }` |
| `:class="{ 'active': isActive }"`, `'tab-' + id` | Getter returning the class string or id |
| `x-data="{ open: false }"`, `x-data="init({ id: 4 })"` | `x-data="initFoo"` + `data-*` read in `init()` |
| `open = true` assignment in a directive | Named method: `@click="show"` |
| `:disabled="true"`, `:tabindex="0"`, `:value="'abc'"` (literals) | Static attribute, or a getter — the evaluator looks up a property named `true` |
| `x-for="i in 10"`, `x-for="item in items.filter(…)"` | `x-for="item in visibleItems"` + getter returning an array |
| `onclick="…"`, `oninput="…"` (any `on*` attribute) | `@click="method"` on an Alpine element, or `addEventListener` in a registered script — blocked by `script-src` on every Alpine build |
| `href="javascript:…"` | `<button type="button" @click="method">` (or `href="#"` + `@click.prevent`) |

Components named in `x-data` must be registered with `Alpine.data` — the CSP build
does not look up `window` globals:

```php
<script>
    function initFoo() {
        return { open: false, init() { this.id = this.$el.dataset.id; }, show() { this.open = true; } };
    }
    window.addEventListener('alpine:init', () => Alpine.data('initFoo', initFoo), {once: true});
</script>
<?php $hyvaCsp->registerInlineScript() ?>
```

- `registerInlineScript()` goes **immediately after** `</script>`, never inside it. It
  reads the output buffer for the last closed `<script>` and adds a nonce, or a hash
  when the page is FPC-cacheable.
- Hyvä's template engine injects `$hyvaCsp` into every template. Use the guarded form
  `isset($hyvaCsp) && $hyvaCsp->registerInlineScript()` only in modules that must
  also render on Luma or on theme-module versions that predate `$hyvaCsp`.
- `$viewModels->require(HyvaCsp::class)->registerInlineScript()` does register the script
  (same shared view model, the call only reads the output buffer) but is not Hyvä's form
  and is a fatal error on theme modules without `HyvaCsp`. Use the injected `$hyvaCsp`
  (`fix-scripts --normalize`). Audit reports it as a warning, or fatal when the class is missing.
- Script text must be deterministic: no `uniqid()`, `time()`, random IDs or tokens
  inside `<script>`, because each variant adds a hash to the cached CSP header. Put
  dynamic values in `data-*` or `<script type="application/json">`. `fix-scripts`
  refuses to register such scripts (direct calls or variables assigned from them):
  refactor them first, then re-run it.
- Per-instance IDs (`x-data="initSlider<?= $id ?>()"`, `function initSlider<?= $uniqueId ?>()`):
  register **one** factory name and pass the instance ID via `data-*`
  (`x-data="initSlider" data-slider-id="<?= $id ?>"`). A per-instance function name
  makes the script text differ per render.
- Inside `x-for="item in items"`, `x-text="item.name"` works as is. Don't wrap simple
  loop reads in getters.
- Changing `x-data="initFoo()"` to `x-data="initFoo"` breaks CSS such as
  `[x-data="initFoo()"]`. Use `[x-data*="initFoo"]`.
- Large components: move the factory to `view/frontend/web/js/*.js` loaded with
  `<script src>`. External files need no nonce.

## When something breaks

Symptom → cause → fix lives in `references/csp-troubleshooting-gotchas.md` (placement
and buffer corruption, block-cached HTML losing its `Alpine.data` registration, header
growth, FPC race). Registration patterns and companion-JS layout:
`references/inline-script-patterns.md`.

## Changing the tooling

After editing any script or rule: `python3 -I <skill>/evals/run_evals.py` (offline, 44 checks:
every directive the CSP evaluator rejects, silent cases, registration forms, fixer safety).
