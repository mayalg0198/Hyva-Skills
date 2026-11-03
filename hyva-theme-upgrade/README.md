# Hyvä Theme Upgrade Toolkit

> **A portable, version-aware runbook and script suite for upgrading any Hyvä Theme child theme on Magento 2 / Adobe Commerce.**

---

## What This Is

This is an agent **skill** for Claude Code (and [Antigravity IDE](https://antigravity.dev)) — a reusable runbook plus scripts that guide AI-assisted upgrades of [Hyvä Themes](https://hyva.io) projects. Its changelog references cover Hyvä 1.3.x → 1.5.2 (July 2026 release). It handles:

- **Hyvä Theme Module & Default Theme** upgrades across any version range
- **Tailwind CSS v3 → v4** migration
- **Hyvä Commerce** module alignment (CMS, Admin Dashboard, Image Editor, Media Optimization)
- **Template auditing** across 300+ customized override files
- **Visual regression detection** via automated screenshots

---

## Quick Start

### 1. Copy the config sample into your project root

```bash
cp <skill>/.hyva-upgrade.json.sample .hyva-upgrade.json
```

Edit `.hyva-upgrade.json` with your project's version range and paths:

```json
{
  "from_version": "1.4.3",
  "to_version": "1.5.2",
  "themePath": "app/design/frontend/Vendor/YourTheme",
  "vendorThemePath": "vendor/hyva-themes/magento2-default-theme",
  "baselineUrl": "https://staging.your-store.com",
  "targetUrl": "https://your-store.test",
  "cssFreeze": false,
  "locales": ["en_US"],
  "commerce_versions": {
    "cms": { "from": "1.1.0", "to": "1.2.4" }
  }
}
```

> **Note:** `.hyva-upgrade.json` is project-specific (local URLs, paths) and must never be committed. The skill's own
> `.gitignore` does **not** protect your project — add it locally with `echo .hyva-upgrade.json >> .git/info/exclude`.
> `run.sh doctor` warns when it is not ignored.

### 2. Verify environment health (Doctor)

```bash
bash <skill>/run.sh doctor
```

### 3. Run the unified pre-flight audit

```bash
bash <skill>/run.sh audit
```

### 4. Fetch the changelog for your version range

```bash
bash <skill>/run.sh changelog
```

---

## File Structure

```
hyva-theme-upgrade/
├── SKILL.md                          # Agent runbook (full upgrade workflow)
├── .hyva-upgrade.json.sample         # Config template — copy to project root
├── requirements.txt                  # Python dependencies
│
├── scripts/
│   ├── audit-theme.py               # Version-aware pre-flight auditor (8 checks)
│   ├── audit-i18n.py                # Multi-locale translation coverage checker
│   ├── diff-template.sh             # Template diff: child vs vendor
│   ├── scan-legacy-directives.sh    # Detect Alpine v2 legacy syntax
│   ├── fetch-changelog.py           # Extract changelog for your version range
│   ├── visual-diff.py               # Screenshot + pixel-diff comparison
│   └── visual-diff.sh               # Shell wrapper for visual-diff.py
│
└── references/
    ├── changelog-theme-upgrade.md   # Hyvä Theme versioned changelog
    ├── changelog-commerce-modules.md# Hyvä Commerce modules versioned changelog
    └── upgrade-matrix-by-page.md    # Template: per-flow tracking matrix
```

---

## Scripts Reference

### `audit-theme.py` — Version-Aware Pre-Flight Auditor

Reads `from_version`/`to_version` from `.hyva-upgrade.json` and checks only the patterns relevant to your upgrade range.

```bash
# Basic audit (auto-discovers theme, reads config)
python3 <skill>/scripts/audit-theme.py

# With PHP syntax check
python3 <skill>/scripts/audit-theme.py --lint-php

# Skip vendor-alignment warnings (when 3rd-party modules override gallery/swatch)
python3 <skill>/scripts/audit-theme.py --skip-vendor-align

# JSON output for CI integration (exit code 1 on fatal issues)
python3 <skill>/scripts/audit-theme.py --output json > audit-report.json
```

**Checks performed (version-gated):**
| Check | Since |
|-------|-------|
| Fatal Alpine v2 directives (`x-spread`, `$el.__x`) | Always |
| Unsafe `localStorage` `JSON.parse` | Always |
| Deprecated Tailwind v3 `*-opacity-*` classes | ≥ 1.5.0 |
| Legacy design tokens (`-fg` → `-ink`) | ≥ 1.5.2 |
| Missing bfcache `@pageshow.window` handler | ≥ 1.4.7 |
| Missing anti-spam `isSubmitting` guard | ≥ 1.4.7 |
| Vendor feature parity (`gallery.additional`) | ≥ 1.5.1 |
| PHP syntax errors (`php -l`) | `--lint-php` flag |

---

### `diff-template.sh` — Template Comparison

Diff any customized template against its vendor counterpart. No git required.

```bash
# Diff against Hyvä vendor default theme
bash <skill>/scripts/diff-template.sh Magento_Catalog/templates/product/view/gallery.phtml

# Diff a 3rd-party override (auto-searches vendor/)
bash <skill>/scripts/diff-template.sh Amasty_ColorSwatchesProHyva/templates/product/view/conf.phtml
```

**Exit codes:** `0` = identical, `1` = diff output printed (expected), `2` = error.

---

### `fetch-changelog.py` — Version-Range Changelog Extractor

Extracts only the changelog sections relevant to your `from_version` → `to_version`.

```bash
python3 <skill>/scripts/fetch-changelog.py                    # Theme + Commerce
python3 <skill>/scripts/fetch-changelog.py --module theme     # Theme only
python3 <skill>/scripts/fetch-changelog.py --module commerce  # Commerce only
```

---

### `scan-legacy-directives.sh` — Legacy Alpine Scanner

```bash
bash <skill>/scripts/scan-legacy-directives.sh              # Scan entire theme
bash <skill>/scripts/scan-legacy-directives.sh Magento_Checkout  # Scan specific module
```

---

### `visual-diff.py` — Screenshot Comparison

Captures headless Chrome screenshots of the baseline (staging) and target (local) sites, then generates a pixel-diff heatmap and interactive swipe report.

```bash
bash <skill>/scripts/visual-diff.sh <page-slug>
# Example:
bash <skill>/scripts/visual-diff.sh contactez-nous
```

Requires Chrome/Chromium and `Pillow` (see `requirements.txt`).

---

## The 5-Phase Upgrade Workflow

See [`SKILL.md`](./SKILL.md) for the full agent runbook, including:

1. **Phase 1** — Changelog & Impact Analysis (run `fetch-changelog.py`)
2. **Phase 2** — Environment & Tooling Setup (npm, container rules)
3. **Phase 3** — Design Tokens & Tailwind v4 Migration
4. **Phase 4** — Template & Module Alignment (7 Page Flows, 5-Step SOP)
5. **Phase 5** — Recompilation, Deployment & Verification

---

## Extending the Changelogs

When a new Hyvä version is released, prepend a section to the changelog files:

**`references/changelog-theme-upgrade.md`:**
```markdown
## [x.y.z] — YYYY-MM-DD

### `hyva-themes/magento2-default-theme`
* ...

### `hyva-themes/magento2-theme-module`
* ...
```

**`references/changelog-commerce-modules.md`:**
```markdown
## [module-name@x.y.z] — YYYY-QN

### `hyva-themes/commerce-module-{name}`
* ...
```

Then update `to_version` in `.hyva-upgrade.json` and re-run `fetch-changelog.py`.

---

## Installation

`<skill>` in this README means the directory holding this skill. Run every command from the Magento project root.

- **Claude Code:** `~/.claude/skills/hyva-theme-upgrade/` (personal) or `<project>/.claude/skills/hyva-theme-upgrade/` (shared with the team).
- **Antigravity IDE:** `<project>/.agents/skills/hyva-theme-upgrade/` (see below).

The scripts locate the project root by walking up from the current directory, so they work wherever the skill is installed.
Every command accepts `--config <file>` to use a config stored outside the project (nothing to exclude from git then).

Self-check after installing or editing a script: `python3 -I <skill>/evals/run_evals.py` (offline, 21 checks on a
generated fixture project: doctor, layout orphans incl. modules registered under `src/`, vendor override matching,
template diff, i18n, audit, changelog, and that read-only commands never touch the project).

## Using With Antigravity IDE

Place this skill in your project at `.agents/skills/hyva-theme-upgrade/`. The Antigravity agent will automatically discover and use it when you ask it to help with Hyvä upgrade tasks.

```
your-magento-project/
├── .agents/
│   └── skills/
│       └── hyva-theme-upgrade/   ← this skill
├── .hyva-upgrade.json            ← your project config (exclude it from git)
└── app/design/frontend/...
```

---

## License

MIT — free to use, modify, and share.
