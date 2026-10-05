# Changelog: Hyvä Theme (Cumulative — Versioned)

> **Usage:** This file stores changelogs per version. The `fetch-changelog.py` script automatically extracts the relevant changes between `from_version` and `to_version` declared in `.hyva-upgrade.json`.
>
> **Adding new versions:** When a new Hyvä release is available, prepend a new `## [x.y.z]` section following the format below.

---

## [1.5.2] — 2026-07-10

### `hyva-themes/magento2-default-theme`
* **Design Token `ink` replaces `fg`:**
  * New token pair: `--color-ink` (primary text/element color) and `--color-ink-muted` (secondary/muted text).
  * Backward-compatible aliases kept: `--color-fg: var(--color-ink)` and `--color-fg-secondary: var(--color-ink-muted)`.
  * Scan child theme templates and CSS for `-fg` utility classes and migrate to `-ink` / `-ink-muted`.
* **npm package update:** `@hyva-themes/hyva-modules` bumped to `^1.4.0` (and `1.5.0`).
* **Swatch Tooltip fix:** Fixed tooltip appearing unexpectedly on touch devices; fixed gap alignment.
* **CSP Safe Render:** Selected option rendering now complies with strict CSP.
* **Minicart Option Render:** Fixed custom product options not rendering correctly in minicart.
* **Gallery & Navigation:** Fixed gallery scroll direction; improved pager display for Configurable Products; fixed last-page pagination button.

### `hyva-themes/magento2-theme-module`
* *(No breaking changes compared to 1.5.1)*

---

## [1.5.1] — 2026-07-01 ⚠️ BREAKING

### `hyva-themes/magento2-default-theme`
* **PHP-Rendered Configurable Product Swatches (MR #1492):** ⚠️ BREAKING
  * **Before:** Swatches were populated via Alpine.js client-side rendering loop → caused layout shift (CLS) and pop-in on PDP load.
  * **Now:** Color, image, and text swatch options are **PHP-rendered directly into the initial HTML**.
  * **Impact:** Any child theme overriding legacy swatch templates (`Magento_Swatches` / `Magento_ConfigurableProduct`) must be reviewed and updated against the new PHP-rendered approach.
  * **CSS Component:** All swatch visuals are now controlled by the `.swatch-option` CSS component class.
* **PHP-Rendered Product Gallery (MR #1484):**
  * Gallery rendered in initial HTML by PHP, hydrated by Alpine.js → Improved LCP.
  * Integrated Lightbox with keyboard navigation.
  * Configurable via `view.xml` (loop, caption, pager type, vertical/horizontal thumbnail layout).
  * New `gallery.additional` layout container for injecting badges/promo labels from external modules.
* **Tailwind CSS v4.3:**
  * Added scrollbar styling, logical property utilities (logical insets), font features, nested `@variant`.
* **BrowserSync fix:** Fixed rewrite rule that accidentally truncated `window.BASE_URL` to `/`.

### `hyva-themes/magento2-theme-module`
* **`Product\Placeholder` ViewModel:** Fetch product placeholder image without Luma helpers.
* **`getSwatchDimension()`:** Get standard swatch dimensions from system configuration.
* **CLI Sample Data:** New commands `hyva:sampledata:deploy` and `hyva:sampledata:remove`.
* **PHP 8.5 & Magento 2.4.9 compatibility:** Updated type signatures, Symfony Console, PHPUnit 12.
* **Lucide Icons:** Upgraded to `v0.563`.
* **View Transition:** Toggle PLP→PDP view transition effect via configuration.

---

## [1.4.7 → 1.4.10] — 2026-06 to 2026-07

### `hyva-themes/magento2-default-theme`
* **Alpine Snap Slider v2.2.2:** Added `x-snap-slider.loop` modifier, stable index-based navigation with `isNavigating` guard, `inert` attribute on pager when no overflow.
* **HTML Dialog v2.3.0:** New `modeless` attribute support (dialog does not block page interaction).
* **Anti-spam Submit Guard:** Automatically disables submit buttons on account forms after submission to prevent duplicate requests.
* **Bfcache Form Keys:** Automatically refreshes form key when a page is restored from Back-Forward Cache.

---

## [1.4.4 → 1.4.6] — 2026-03 to 2026-05

### `hyva-themes/magento2-default-theme`
* **Search Keyboard Shortcut:** `Cmd+K` (macOS) / `Ctrl+K` (Windows/Linux) to open the search bar.
* **Preload Main Image:** Preload the main PDP gallery image to improve LCP.
* **reCAPTCHA:** Customizable Legal Notice; automatically disables submit when reCAPTCHA validation fails.
* **Cart Items Script consolidation:** Merged cart action handlers into a single script (aligns with CSP theme).

---

## [1.4.3] — 2026-02

> Baseline version. No changelog (this is the upgrade starting point).

---

<!-- TEMPLATE FOR NEW VERSIONS — Copy and fill in when a new release is available:

## [x.y.z] — YYYY-MM-DD

### `hyva-themes/magento2-default-theme`
* ...

### `hyva-themes/magento2-theme-module`
* ...

-->
