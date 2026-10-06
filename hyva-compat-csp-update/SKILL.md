---
name: hyva-compat-csp-update
description: Upgrades Hyvä compatibility modules, custom modules, and theme overrides to strict Content Security Policy (CSP) compliance on Magento 2. Use when auditing templates for CSP violations, registering inline script nonces with isset($hyvaCsp), converting Alpine.js expressions to alpine3-csp.js dot-paths and HTML5 data-attributes, eliminating unsafe-eval / argument calls / ternaries, or preparing any Hyvä compat module for strict CSP deployment. Keywords alpine3-csp.js, x-data, registerInlineScript, hyvaCsp, unsafe-eval, CSP violation, dot-path evaluator.
---

# Hyvä strict CSP upgrade

Upgrading Hyvä compatibility modules (`Amasty_*HyvaCompatibility`, `Mirasvit_*`,
custom B2B modules, community packages) and theme overrides to 100% Strict CSP
compliance without breaking backwards compatibility. This file is the entry point;
the detail lives in `references/`.

## References

- `references/alpine3-csp-rules.md` — complete anti-pattern → CSP-compliant
  transformation reference: argument calls, ternaries, object literals, binary
  concatenation, inline arrow functions, `x-spread` / `$el.__x` (Alpine v2), CSS
  selector fixes for `x-data`, and dot-path evaluator mechanics under `alpine3-csp.js`.
- `references/inline-script-patterns.md` — how `registerInlineScript()` works
  (output-buffer scan of last closed `</script>`), correct placement immediately
  after `</script>`, `isset($hyvaCsp)` guard requirement, and companion JS
  extraction to `view/frontend/web/js/`.
- `references/csp-troubleshooting-gotchas.md` — root causes and verified fixes for
  `x-for` loop scope mechanics, dynamic tree traversal crashes, CSS selector breakage
  on Hyvä 1.5.2+, cache-pressure CSP header growth, and edge cases.

## CLI runner

The CLI runner at `.agents/skills/hyva-compat-csp-update/run.sh` automates auditing and fixes:

- `./run.sh doctor` — verify environment and required tools.
- `./run.sh audit <path>` — scan templates for CSP anti-patterns and inline script violations.
- `./run.sh fix-scripts <path> --dry-run` — preview automatic `registerInlineScript()` insertion.
- `./run.sh fix-scripts <path>` — inject nonce registration immediately after `</script>`.
- `./run.sh suggest <template>` — suggest CSP-compliant Alpine refactoring recipes for a template.
- `./run.sh test-pressure <url>` — runtime verification of CSP header size and cache pressure.

## CSP conversion rules

Non-negotiable under Hyvä's CSP build:

1. **Inline script nonces**: `registerInlineScript()` reads `ob_get_contents()`
   for the last closed `</script>` tag. It must be placed immediately after
   `</script>`, never inside the `<script>` block. Always guard with `isset($hyvaCsp)`
   so templates remain backwards-compatible when CSP is disabled.
2. **Evaluator dot-paths only**: Under `alpine3-csp.js` the evaluator splits
   expressions by dot only. Any function call with arguments, ternary operator,
   object literal, binary concatenation, or inline arrow definition must be
   refactored to a named getter on the Alpine component or bridged via HTML5
   `data-*` attributes.
3. **Loops and iteration**: In `x-for` loops, keep direct dot-path accesses
   (`x-html="item.name"`, `:id="item.id"`) native and standardise the iterator to
   `(item, index) in items`. Do not wrap simple property reads in root getters.
4. **Tree traversal**: Guard recursive tree traversal with optional chaining
   (`if (!tree?.children?.length) return;`).
5. **Component extraction**: For large JS blocks, extract component factories to
   `view/frontend/web/js/component.js` and register on `alpine:init`. External script
   files do not need per-block nonces.

## Pitfalls

- Never place `$hyvaCsp->registerInlineScript()` inside `<script>` tags; it evaluates
  via PHP output-buffering and must follow closing `</script>`.
- Never call `$hyvaCsp->registerInlineScript()` without `isset($hyvaCsp)` check. Bare
  calls trigger fatal errors on stores or themes where Hyvä CSP module is disabled.
- Never pass arguments in Alpine directives (e.g. `@click="select(item.id)"`).
  Instead pass context via `data-item-id` on the element or read from the event target.
- Never create nested `x-data` wrappers to resolve expressions when an ancestor
  already holds state; nested scopes shadow data and run `init()` twice.
- Re-run audit with `--fail-on-warning` and verify browser console shows zero
  `unsafe-eval` violations, zero inline script blocks, and zero Alpine Expression Errors.
