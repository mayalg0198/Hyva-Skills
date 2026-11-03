# Prompt for the Figma-reader subagent (MCP path)

Use when `figma token: unset` (no REST). The raw `get_design_context` output is huge and would be
re-sent on every later turn of the main conversation; a subagent absorbs it and returns ~1–2k tokens.
Spawn with `Agent` (`subagent_type: general-purpose`, `model: sonnet`), one agent per frame, all in
the same message. Fill the `<…>` placeholders; do not paraphrase the rules.

```
Read one Figma frame and write a compact spec to disk. Do not implement anything.

1. Invoke the `figma:figma-design-to-code` skill, then ToolSearch
   `select:mcp__claude_ai_Figma__create_session,mcp__claude_ai_Figma__get_design_context,mcp__claude_ai_Figma__get_screenshot,mcp__claude_ai_Figma__download_assets`.
2. create_session for fileKey <FILE_KEY>, then ONE get_design_context for nodeId <NODE_ID>
   (skillNames: figma-design-to-code). If it is flagged sparse, call it once per visible child in one
   parallel batch. If any call is refused for quota/seat reasons, STOP and report that exact error.
3. The tool result is saved to a file when large (path shown in the result). Run:
   python3 -I ~/.claude/skills/figma-to-hyva/scripts/condense.py tsx <that file> --out <SPEC_PREFIX>
   (if the output was short and inline, write it to <SPEC_PREFIX>.tsx first, then condense that file).
4. Download the assets get_design_context lists into <ASSET_DIR> as it instructs (no other download tool).
5. Reply with ONLY: the spec prefix path, the condense summary line, the asset file list with sizes,
   frame size, and anything ambiguous (hidden layers, missing states, text that looks truncated).
   Do not paste the code, the tree or the screenshot.
```

After it returns: `cache.py put <FILE_KEY> <NODE_ID> --version <V> --prefix <SPEC_PREFIX>`, read
`<SPEC_PREFIX>.md` (the tree) once, and run `tokens.py batch <SPEC_PREFIX>.json --bp <base|md|xl>`.
