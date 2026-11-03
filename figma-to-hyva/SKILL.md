---
name: figma-to-hyva
description: >-
  Use when implementing a Figma design (figma.com URL, node ID, frame or screenshot) as Hyvä
  frontend code in any Magento 2 project — a new widget, block, CMS section, page template,
  template override or checkout step built with Tailwind (v3 or v4) + Alpine.js, CSP or not.
  Triggers: "intégrer la maquette", "implement this Figma", "build this component from Figma",
  "làm theo Figma", "dựng giao diện từ Figma", "code block này theo Figma". Not for fixing review
  comments on existing work, nor for a pure design QA of an existing page (use figma-reviewer).
hooks:
  PostToolUse:
    - matcher: "Write|Edit"
      hooks:
        - type: command
          command: "python3 -I ~/.claude/skills/figma-to-hyva/scripts/hook_lint.py"
---

# Figma → Hyvä implementation (any Magento 2 + Hyvä project)

Principle: **scripts do the deterministic work, the model decides layout and judgement.** Anything
below that says "run" is a script in `~/.claude/skills/figma-to-hyva/scripts/` (`S=` that path; always
`python3 -I`). Send independent calls in the same message; never re-read a file or re-fetch a Figma
node already in context. The PostToolUse hook lints every `.phtml`/`.php` you write (changed lines
only) and feeds errors back immediately.

## Step 0 — Context (one turn, in parallel)

1. `Bash`: `python3 -I $S/detect.py --brief` → versions, theme, **MODE (csp, TW3/TW4, hyvacsp)**,
   breakpoints, tokens, env/build/flush commands, quality gate, guidance files, `figma token: set|unset`.
   Cached in `var/figma-to-hyva/`; `--refresh` after changing themes/lock files.
2. `Bash`: `python3 -I $S/rules.py --compact --sections 1,2,3` → only the rules for this MODE
   (add section `4` for PHP/layout/widget work; drop `--compact` when unsure).
3. `Bash`: `python3 -I $S/cache.py map get` (known Figma component → partial) and, with a URL,
   `cache.py get <fileKey> <nodeId>`.
4. With a URL and no token: `Skill` `figma:figma-design-to-code` (mandatory before
   `get_design_context`). Next turn: `Read` the guidance files listed by detect (they override
   generic rules).

Ask all missing inputs (Figma URL/node or screenshot, placement, content source) in **one**
`AskUserQuestion`. Never invent a design.

## Step 1 — Read the design (keep raw Figma out of context)

Pick the path from detect (`figma token`) and the cache result:

| Situation | Do |
|---|---|
| Cache `FRESH` / `UNVERIFIED` and user wants no refetch | read `<prefix>.md` only |
| Token set (REST) | `figma_api.py version <fileKey>` → compare with cache; if stale/miss: `figma_api.py node <fileKey> <nodeId> --out $(cache.py path <fileKey> <nodeId>)`; never prints raw data |
| Token unset (MCP) | one **subagent per frame**, in parallel, using `references/figma-reader-prompt.md` (it returns ~1–2k tokens; raw MCP output never enters this context) |
| No Figma access / quota error (exit 4, refusal) | stop calling Figma; use the user's screenshot + specs (`Read` the image) |

Then, in parallel: `Read <prefix>.md` (indented tree), `tokens.py batch <prefix>.json --bp <base|md|xl>`
(frame width 375 → `base`, 768 → `md`, 1440 → `xl`; one run per frame) and `cache.py put … --version`.
Output per text style: `EXACT .token` or `NO EXACT TOKEN — closest …`; colours: `EXACT name` or nearest;
spacing: a class valid for TW3/TW4. Use exact matches; list every non-match (arbitrary value or
closest token + diff) for the report. Re-fetch only the node that changed, never the file.

Assets: files exported by the reader/`figma_api.py export … --format svg` → `assets.py place <files>`
(rejects empty/non-images, flags **identical existing assets to reuse**, keeps SVG root width/height,
prints the `getViewFileUrl` path). Heroicons/`SvgIcons` only for exact visual matches.
Register a reusable block: `cache.py map set "<Figma component>" <template path>`.

The MCP/REST code is a reference, not code to paste: rewrite absolute positioning as flex/grid.

## Step 2 — Locate (one turn of parallel searches)

`Grep`/`Glob` together: similar components in theme(s) and `app/code` (token classes from detect,
component names, the layout handle), the block rendering the target, child-theme overrides of the same
template. Wide/unknown codebase → one `Explore` agent. Trace layout XML → Block/ViewModel → template
(`PHP-1`). Placement: markup only → `<theme>/<Module_Name>/templates/…` (override: copy the installed
vendor version first, `TPL-7`); PHP data or editor config → a module per `CLAUDE.md`
(`magento2-dev-core` for the PHP side). If placement isn't obvious, propose and confirm.

## Step 3 — Implement

- New widget/module or empty template: write a small spec and run
  `scaffold.py spec.json` (dry run) then `--write` — typed, strict, escaped, translated, boolean/number
  params per PHP-4/5, Alpine registered for the project's CSP mode, project copyright header,
  never overwrites. Then fill in only the Figma-specific markup.
- Order: PHP → layout XML → template → Alpine → CSS/tokens. Independent files in **one turn** of
  parallel `Write`/`Edit`. Mobile-first, `md:`/`xl:` per detect `screens`. Build every state/empty
  state from the spec. Follow the rules printed in Step 0 (the hook enforces the mechanical ones).
- Strings: `i18n_sync.py --changed` lists missing keys per CSV; translate them into a JSON map and run
  `i18n_sync.py --changed --write --translations map.json`.
- Pattern not covered → `magento2-hyva-dev`; CSP conversion of legacy inline scripts →
  `hyva-compat-csp-update`.
- **≥ 3 independent sections:** after Step 1 dispatch one subagent per section in a single message
  (`dispatching-parallel-agents`; `model: sonnet`), each with its spec prefix, the Step 0 rules output,
  and its own target files (no shared files). Run the mechanical steps below on a cheaper model too
  (i18n translation map, asset placement); keep layout decisions and review on the main model.

## Step 4 — Verify (scripts first, images last)

1. `Bash` (single call, quiet output): `python3 -I $S/build_verify.py [--generate] [--di]` → CSS
   build, cache flush, optional DI compile, then **every Tailwind class in changed templates must exist
   in the built CSS** (catches TW-1/TW-3 and stale builds). Fix `MISSING` classes before looking at the page.
2. Numeric check in Chrome per frame width (`references/verify.md`): `computed_styles.js` →
   `style_compare.py` (font-size/line-height/weight/colour vs spec), then one screenshot →
   `pixel_diff.py` (% differing, worst regions). Open images only where these fail.
   `figma-reviewer` for a block-level task list; no browser → say so, never claim parity.
3. Quality gate from detect (`make verify`, project lint skill, else `magento2-linter`).
4. `Bash`: `python3 -I $S/report.py [--browser] [--visual-diff <pct>] [--gate-ok] --figma-calls <n>`
   → checklist with ticks only for what scripts verified; also logs the run.
5. Load `verification-before-completion` before saying it is done; broken rendering →
   `systematic-debugging` (stale build, cache, MISSING classes first).

## Step 5 — Report

Paste `report.py` output, then: files created/changed and why; deviations from Figma (no token,
closest token + diff, missing asset, technical limit); open questions; editor/admin steps (widget to
insert, config, CMS block). Never `git add`/commit unless asked.

## Measuring the skill

`python3 -I ~/.claude/skills/figma-to-hyva/evals/run_evals.py` (offline, ~39 checks) after editing any
script; `runlog.py log node=… figma_calls=… tokens_k=… minutes=…` and `runlog.py summary` to compare runs.
