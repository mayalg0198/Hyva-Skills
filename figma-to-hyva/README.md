# Figma → Hyvä — Design-to-Code Toolkit

> **Implement a Figma frame as Hyvä code (Tailwind v3/v4 + Alpine.js, CSP or not) in any Magento 2 project, with scripts doing the deterministic work and the agent doing the judgement.**

---

## 🧭 Overview

The skill detects the project's stack, reads the design with as few Figma reads as possible, maps every Figma value to the project's own tokens, builds the component, then verifies it with numbers instead of screenshots.

### Key Capabilities

- **Project detection (cached)**: Magento / Hyvä versions, Hyvä themes and parents, Tailwind v3 or v4, design tokens, breakpoints, i18n files, `HyvaCsp` availability, CSP strictness inferred from existing templates, Govard / Warden / DDEV commands, local URL, quality gate.
- **Figma without context bloat**: REST fetch (`FR_FIGMA_TOKEN` / `FIGMA_TOKEN`) or one subagent per frame (MCP), condensed to a small tree + JSON spec, cached per node version.
- **Token mapping**: Figma text styles → project typography classes / `@utility` per breakpoint, hex → theme colours (exact or nearest ΔE), px → spacing classes valid for Tailwind 3 or 4.
- **Hyvä rule linter**: Alpine CSP directives, inline-script registration, PHP inside `<script>`, dynamic Tailwind classes, TW3 invalid spacing / important syntax, escaping, alt / `rel` / click-on-div — on changed lines only, also run automatically after each edit (PostToolUse hook).
- **Scaffolding**: CMS widget module (widget.xml, typed Block with boolean/number params handled, escaped and translated template, CSP-aware Alpine component) from a small JSON spec; never overwrites.
- **Verification**: quiet build + cache flush, check that every Tailwind class used exists in the built CSS, i18n sync across locale CSVs, asset dedupe against the theme, computed-style comparison and pixel diff against Figma, auto-ticked completion checklist.

---

## ⚡ Installation

### Claude Code (recommended)

The `SKILL.md` and its hook call the scripts at `~/.claude/skills/figma-to-hyva/`, so install it there:

```bash
git clone https://github.com/mayalg0198/Hyva-Skills.git /tmp/hyva-skills
cp -r /tmp/hyva-skills/figma-to-hyva ~/.claude/skills/
rm -rf /tmp/hyva-skills
python3 -I ~/.claude/skills/figma-to-hyva/evals/run_evals.py   # 39 offline checks
```

Installing it somewhere else (e.g. `.agents/skills/`) works for the scripts, but replace
`~/.claude/skills/figma-to-hyva` in `SKILL.md` (including the `hooks:` block) with the new path.

### Requirements

- Python 3.10+ (standard library only); optional Pillow for `pixel_diff.py`, `npx svgo` for SVG optimisation.
- Optional skills it hands off to when present: `figma:figma-design-to-code` (Figma MCP),
  `figma-reviewer`, `magento2-hyva-dev`, `magento2-dev-core`, `hyva-compat-csp-update`,
  `magento2-linter`, `govard-magento`, `verification-before-completion`, `systematic-debugging`.

---

## 🛠️ CLI Quick Reference

Run from the Magento root (`S=~/.claude/skills/figma-to-hyva/scripts`):

```bash
python3 -I $S/detect.py --brief                     # stack, MODE (csp / TW3|TW4), commands
python3 -I $S/rules.py --compact --sections 1,2,3   # only the rules that apply here

python3 -I $S/figma_api.py node <fileKey> <nodeId> --out "$(python3 -I $S/cache.py path <fileKey> <nodeId>)"
python3 -I $S/tokens.py batch spec.json --bp xl     # Figma styles → project tokens
python3 -I $S/tokens.py space --px 50 --prop mt     # mt-[50px] on TW3, mt-12.5 on TW4

python3 -I $S/scaffold.py widget.json --write       # widget module skeleton
python3 -I $S/assets.py place exported/*.svg        # dedupe + place in web/svg|images
python3 -I $S/i18n_sync.py --changed --write --translations map.json

python3 -I $S/lint_phtml.py --changed               # Hyvä rules on changed lines
python3 -I $S/build_verify.py                       # build + flush + class presence check
python3 -I $S/style_compare.py spec.json computed.json
python3 -I $S/pixel_diff.py figma.png web.png
python3 -I $S/report.py --browser --visual-diff 1.2 # completion checklist with evidence
```

Caches and run logs live in `<magento-root>/var/figma-to-hyva/` (git-ignored by Magento).

---

## 📖 Documentation

- [`SKILL.md`](./SKILL.md) — the agent workflow
- [Hyvä rules (conditional by CSP / Tailwind)](./references/hyva-rules.md) — read through `scripts/rules.py`
- [Figma reader subagent prompt](./references/figma-reader-prompt.md)
- [Verifying with numbers](./references/verify.md)
