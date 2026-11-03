# Verifying against Figma with numbers, not screenshots

Images are the most expensive thing to put in context. Measure first, look only at what fails.

1. **Computed styles** (cheapest, exact): in Claude in Chrome open the page at the frame width
   (375 / 768 / 1440 — resize the window), run `scripts/computed_styles.js` through `javascript_tool`
   with `__SELECTOR__` replaced by the block's CSS selector, save the returned JSON to a file, then
   `python3 -I scripts/style_compare.py <spec.json> <computed.json>` → only mismatches are printed
   (font-size, line-height, weight, colour; texts missing on the page).
2. **Pixel diff**: take ONE screenshot of the block (Chrome tool saving to a file, or the
   `figma-reviewer` capture when the site needs basic auth) and the Figma screenshot of the same node
   (`get_screenshot` result saved, or `figma_api.py export … --format png`), then
   `python3 -I scripts/pixel_diff.py figma.png web.png --max-pct 2` → % differing, worst cells as
   pixel boxes. Open the diff image only when it exceeds the threshold.
3. **Block-level pixel QA** with a task list (exact Figma vs website values): the `figma-reviewer`
   skill (`review.py`) — reads `figma-review.config.json`, handles breakpoints and states.
4. **Interactions / empty states**: exercise in the browser; read the console once at the end.
5. Record what was and was not measured: `report.py --browser --visual-diff <pct>`; never claim
   visual parity from step 1 or 2 alone for hover/focus/active states.
