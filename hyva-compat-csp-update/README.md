# Hyvä Compatibility Module — Strict CSP Upgrade Toolkit

> **An audit, fix and refactor toolkit for making Hyvä compatibility modules, custom modules and theme overrides run under strict Content Security Policy (Alpine CSP build, no `unsafe-eval`, no `unsafe-inline`).**

---

## 🛡️ Overview

Hyvä's CSP Alpine build (`alpine3-csp.js`) resolves every directive value with `expression.split('.')` on the component scope: only plain property / method paths work. Inline `<script>` blocks must be registered with `$hyvaCsp->registerInlineScript()` right after `</script>` (nonce, or hash when the page is FPC-cacheable). Converted templates keep working on the regular Hyvä theme, so the conversion can land before CSP is switched on.

### Key Capabilities

- **Audit** every directive the CSP evaluator cannot resolve: calls (with or without parentheses), negation, assignments / `++`, comparisons, logical operators, ternaries, object literals, literals (`true`, `0`, `'abc'`), arithmetic, inline functions, `x-for` over expressions or numbers.
- **Script registration checks**: unregistered executable inline scripts (JSON / template scripts ignored), registration placed inside `<script>`, the non-standard `$viewModels->require(HyvaCsp::class)` form (warning, or fatal where the class does not exist), unguarded `$hyvaCsp` in Luma-compatible code.
- **FPC hash growth**: script text that changes per render (`uniqid()`, `rand()`, `time()`… directly or through a variable).
- **Blocked markup**: inline `on*="…"` event handlers and `javascript:` URLs.
- **Safe fixer**: inserts `registerInlineScript()` after each unregistered script, moves misplaced calls, optional `isset()` form and normalisation of the `$viewModels` form, **refuses to register per-render scripts**, `php -l` with automatic revert, never touches `vendor/`, `generated/`, `var/`, `pub/static/`.
- **Refactor recipes** per finding (`suggest`) and a cold / warm **FPC pressure test** of the CSP header for local environments.

---

## ⚡ Installation

```bash
git clone https://github.com/mayalg0198/Hyva-Skills.git /tmp/hyva-skills
cp -r /tmp/hyva-skills/hyva-compat-csp-update ~/.claude/skills/      # Claude Code
# or: cp -r … .agents/skills/  /  ~/.gemini/config/skills/
rm -rf /tmp/hyva-skills
python3 -I ~/.claude/skills/hyva-compat-csp-update/evals/run_evals.py  # 44 offline checks
```

Requirements: Bash 4+, Python 3.8+ (standard library only), `php` on PATH for the fixer's lint check (optional).

---

## 🛠️ CLI (run from the Magento root)

```bash
S=~/.claude/skills/hyva-compat-csp-update      # wherever the skill is installed

bash $S/run.sh doctor
bash $S/run.sh audit app/code/Vendor/ModuleHyvaCompatibility [--fail-on-warning] [--output json]
bash $S/run.sh fix-scripts app/code/Vendor/ModuleHyvaCompatibility --dry-run     # always first
bash $S/run.sh fix-scripts app/code/Vendor/ModuleHyvaCompatibility [--guarded] [--normalize]
bash $S/run.sh suggest app/code/Vendor/ModuleHyvaCompatibility/view/frontend/templates/x.phtml
bash $S/run.sh test-pressure https://store.test/ --flush-cmd "govard tool magento cache:clean full_page" --insecure
```

`test-pressure` sends 90 requests: point it at a local environment only.

---

## 🧭 Workflow

1. `audit` one module or page flow.
2. `fix-scripts --dry-run`, review, apply. Scripts it lists as **not registered** contain per-render values: move them to `data-*` first.
3. `suggest` each remaining template and refactor (getters, `data-*`, `Alpine.data` factories).
4. `audit --fail-on-warning` until it exits 0.
5. Browser: no `Alpine is unable to interpret`, no `Refused to execute inline script`, no `unsafe-eval` in the console, on the CSP theme and on the regular theme.

Registration, for reference:

```php
<script>
    function initFoo() { return { open: false, toggle() { this.open = !this.open; } }; }
    window.addEventListener('alpine:init', () => Alpine.data('initFoo', initFoo), {once: true});
</script>
<?php $hyvaCsp->registerInlineScript() ?>
```

Use `<?php isset($hyvaCsp) && $hyvaCsp->registerInlineScript() ?>` in modules that may also render on Luma or on theme-module versions without `HyvaCsp`.

---

## 📚 References

- [`SKILL.md`](SKILL.md) — agent workflow and the full rule table
- [Alpine v3 CSP rules & migration patterns](references/alpine3-csp-rules.md)
- [CSP troubleshooting & gotchas](references/csp-troubleshooting-gotchas.md)
- [Inline script registration patterns](references/inline-script-patterns.md)
