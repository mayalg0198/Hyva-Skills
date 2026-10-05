# Changelog: Hyvä Commerce Modules (Cumulative — Versioned)

> **Usage:** This file stores changelogs per version for each Hyvä Commerce module. The `fetch-changelog.py` script automatically extracts the relevant changes based on `from_version` / `to_version` in `.hyva-upgrade.json`.
>
> **Adding new versions:** When a new module release is available, prepend a new `## [module-name@x.y.z]` section following the format below.

---

## [admin-dashboard@2.0.2] — 2026-Q2

### `hyva-themes/commerce-module-admin-dashboard`
* **i18n support:** Widget tags, category names, action labels, and titles are now translatable.
* **Orphaned widget cleanup:** Automatically removes orphaned widgets (widgets with no valid type registration).

---

## [admin-dashboard@2.0.1] — 2026-Q1 ⚠️ BREAKING API

### `hyva-themes/commerce-module-admin-dashboard`
* **Decoupled API architecture:** ⚠️ BREAKING
  * All contracts moved to an independent package: `hyva-themes/commerce-module-admin-dashboard-api: 3.0.x`.
  * XML schema: `urn:magento:module:Hyva_AdminDashboardApi:etc/adminhtml/hyva_dashboard_widget.xsd`.
  * `WidgetTypeDispatcher`: Runtime bridge that allows widgets using both old and new API to coexist.
* **Dashboard Views & Role-based access:**
  * Multiple named Dashboard Views per business role (Sales, Marketing, Logistics).
  * Role permissions: `dashboard_views_create`, `dashboard_views_save`, `dashboard_views_delete`, `dashboard_views_assign`.
* **New widget types:** `abandoned_carts`, `customer_order_totals`, `top_coupons`, `recently_edited_products`, `recently_edited_categories`, `recently_edited_cms_pages`, `recently_edited_cms_blocks`, `module_versions`.

---

## [cms@1.2.4] — 2026-Q2

### `hyva-themes/commerce-module-cms`
* **Storage capacity increase:** Template and Snippet fields upgraded to `MEDIUMTEXT` (16 MB).

---

## [cms@1.2.2] — 2026-Q1 ⚠️ BREAKING CACHE

### `hyva-themes/commerce-module-cms`
* **Separate Magewire cache type:** ⚠️ BREAKING
  * Cache type renamed to **`hyva_cms_magewire`** to avoid conflict with the core `magewire` cache type (Magewire v3 / Hyvä Checkout 1.4+).
* **Cascade layer order:**
  * `@layer hyva-cms-tailwind` is now injected at the top of `<head>`, before theme stylesheets — ensures theme CSS utilities always take precedence over CMS component styles.
* **Tailwind v4 JIT fix:** Fixed live compilation errors when editing fields in the Liveview Editor.

---

## [cms@1.2.0] — 2026-Q1

### `hyva-themes/commerce-module-cms`
* **Tailwind CSS v4 & Server-Side JIT Compiler:**
  * `magento2-cms-tailwind-compiler` replaces in-browser JIT compilation.
  * Output CSS is scoped per component: `.hcms-{type}-{id}`.
* **Auto Attributes:**
  * Automatically injects `data-liveview-element`, `id`, and `getEditorAttrs()` on the first HTML element of each component.
  * Opt out per block: `$block->setData('auto_attributes', false)`.
* **Monaco Editor + Tiptap Editor:**
  * Monaco for raw HTML code fields; Tiptap for rich text (supports `{{hyva_image}}`, `{{hyva_link}}` directives).
  * Responsive preview with scale-to-fit true-resolution.

---

## [image-editor@1.1.0] — 2026-Q1

### `hyva-themes/commerce-module-image-editor`
* **Centralized config tab:** Settings moved to `<tab id="hyva_commerce">` in Admin (all Commerce settings in one place).
* **Load images via Admin URL:** Eliminates CORS errors when Admin domain differs from Storefront domain.
* **Post-save event dispatch:** Fires a JS event after saving an image, making it easy to hook custom behavior.

---

## [image-editor@1.0.0] — Baseline

### `hyva-themes/commerce-module-image-editor`
* Integrated Filerobot Image Editor into the Magento Media Gallery.
* Features: Crop, rotate, color adjustment, filters, watermark, Duplicate, Revert to original.
* Checkerboard background for transparent PNG preview.

---

## [media-optimization@1.1.0] — 2026-Q1

### `hyva-themes/commerce-module-media-optimization`
* **Async queue processing:** Image resizing and WebP/AVIF conversion pushed to a Message Queue (RabbitMQ), processed in the background without blocking the initial page response.
* **`image_types.xml`:** Centralized declaration of image sizes, ratios, and formats. Dedicated cache type: `hyva_image_types`.
* **Auto WebP/AVIF conversion:** Automatically scans and replaces images in HTML/CSS output (supports both GD and Imagick).
* **Auto `srcset` generation:** Generates `srcset` attributes based on configured viewport breakpoints.
* **Full CDN & Media Store URL support.**

---

<!-- TEMPLATE FOR NEW VERSIONS — Copy and fill in when a new release is available:

## [module-name@x.y.z] — YYYY-QN

### `hyva-themes/commerce-module-{name}`
* ...

-->
