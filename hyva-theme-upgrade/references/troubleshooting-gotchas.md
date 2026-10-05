# Troubleshooting & Common Gotchas (Hyvä Theme Upgrade)

This document contains deep-dive analysis, root causes, and verified fixes for the 17 most common edge cases, regressions, and architectural bugs encountered during Hyvä Theme upgrades and Tailwind CSS v3→v4 migrations.

---

### 1. Tailwind v4 `@apply` in Standalone / Scoped CSS Files
* **Symptom:** `@tailwindcss/cli` throws an error `Cannot resolve utility` or `Unknown utility class` when `@apply` is used inside custom component stylesheets (e.g. `web/tailwind/components/*.css`).
* **Root Cause:** In Tailwind v4, stylesheets do not inherit utilities automatically unless the stylesheet references the root theme. If a separate CSS file uses `@apply` without `@reference "tailwindcss";` or `@reference "../../../tailwind/tailwind.css";`, the compiler fails to locate the utility classes.
* **Solution:** Add `@reference` at the top of the standalone CSS file:
  ```css
  @reference "tailwindcss";

  .my-button {
      @apply bg-primary hover:bg-primary-dark;
  }
  ```
  *Note:* Using standard CSS nesting (`&:hover { @apply ...; }`) is also supported and provides cleaner specificity control.

---

### 2. Admin Dashboard Missing Legacy Widgets
* **Symptom:** After upgrading `commerce-module-admin-dashboard` to 2.0.1+, original Magento sales charts disappear.
* **Solution:**
  ```bash
  bin/magento config:set hyva_admin_dashboard/general/keep_default 1
  bin/magento cache:flush
  ```

---

### 3. PDP Swatches Click Does Nothing
* **Symptom:** Clicking swatch options has no effect — no active state, no gallery update, no price change.
* **Root Cause:** Custom template missing `.swatch-option` class, or 3rd-party swatch JS (e.g. `Amasty_ColorSwatchesProHyva`) still expects old `[x-data*=Options]` Alpine scope that no longer exists in Hyvä 1.5.1+.
* **Solution:** Verify `.swatch-option` class is present. Check browser console for JS errors. Refer to Flow 2 in [upgrade-matrix-by-page.md](./upgrade-matrix-by-page.md).

---

### 4. Hyvä CMS Component Changes Not Reflecting
* **Symptom:** Liveview Editor saves but frontend shows old content.
* **Solution:** Hyvä CMS 1.2.4 has a separate cache type:
  ```bash
  bin/magento cache:clean hyva_cms_magewire
  ```

---

### 5. npm Binary Architecture Mismatch
* **Symptom:** `node_modules` installs fine on host but container crashes with "invalid ELF header".
* **Root Cause:** Host Linux uses glibc (`linux-x64-gnu`), while container (Alpine) uses musl (`linux-x64-musl`). Node native addons (e.g. `lightningcss`) are not portable between them.
* **Solution:** Always run containerized npm command (e.g. `make npm_install` or via container runner) rather than running `npm install` directly on host OS.

---

### 6. Problematic 3rd-Party Vendor Module CSS (Global Rule Override)
* **Symptom:** A 3rd-party vendor module defines aggressive global rules like `#maincontent { @apply container mx-auto px-6; }` that break layout site-wide (e.g. full-width pages or banners).
* **Root Cause:** `@hyva-themes/hyva-modules` automatically imports all vendor module `module.css` files into `generated/hyva-source.css`.
* **Solution:** Use the official Hyvä mechanism in `web/tailwind/hyva.config.json` with `"keepSource": true`. This skips importing the module's bad CSS while keeping its templates scanned for utility classes:
  ```json
  "exclude": [
      {
          "src": "vendor/your-vendor/module-name/src",
          "keepSource": true
      }
  ]
  ```
  Then run `make build` (or Tailwind build) to regenerate `generated/hyva-source.css`.

---

### 7. Legacy Alpine v2 `x-spread` & Undefined `eventListeners` in 3rd-Party Overrides
* **Symptom:** Browser console crashes with:
  ```
  Uncaught ReferenceError: eventListeners is not defined
  Uncaught TypeError: Cannot convert undefined or null to object (Expression: "eventListeners")
  ```
* **Root Cause:**
  - In Alpine v2 (used in old Hyvä / vendor compatibility modules), `x-spread="eventListeners"` or `x-spread="overlay"` bound event dictionaries.
  - In Alpine v3 (Hyvä 1.4+ / 1.5.2), `x-spread` was removed and replaced with `x-bind="obj"`.
  - When 3rd-party vendor modules modernized their data factories to return specific reactive properties rather than an `eventListeners` object, legacy child theme overrides containing `x-bind="eventListeners"` or `x-spread="..."` crash because `eventListeners` evaluates to `undefined` in component scope.
* **Solution:**
  1. Remove all `x-spread="..."` directives.
  2. If using strict CSP dot-path evaluator, pass data attributes:
     ```html
     <!-- ❌ Old v2 legacy -->
     <li x-data="initInput_..." x-bind="eventListeners" x-spread="eventListeners">

     <!-- ❌ Non-CSP Alpine v3 (breaks under Hyvä strict CSP dot-path evaluator) -->
     <li x-data="initInputDefault({ filterCode: '...', optionId: '...' })"
         :class="{ 'filter-link-selected text-blue-600': isSelected }">

     <!-- ✅ Hyvä Strict CSP Compliant Pattern -->
     <li x-data="initInputDefault"
         data-filter-code="<?= $escaper->escapeHtmlAttr($filterCode) ?>"
         data-option-id="<?= $escaper->escapeHtmlAttr($itemValue) ?>"
         data-is-multiselect="<?= $isMultiselect ? '1' : '0' ?>"
         :class="itemClass"
         class="item flex justify-between py-1 hover:text-black">
     ```
  3. Run pre-flight check:
     ```bash
     ./run.sh audit --audit-csp
     ```

---

### 8. Tailwind v4 Form Element Specificity & `:where()` in `@layer base`
* **Symptom:** Global form label styling forces `display: block; margin-bottom: 0.5rem;` on inline/flex form elements (checkboxes, radio buttons, filter lists, newsletter toggles, checkout radio groups), breaking alignments site-wide.
* **Root Cause:**
  - Writing nested rules like `form, fieldset { label { @apply mb-2 block; } }` outside `@layer base` produces raw CSS `:is(form, fieldset) label` with high specificity `(0,0,2)` in the unlayered cascade.
  - Unlayered CSS rules override all utility classes (`.flex`, `.inline-flex`, `.items-center` in `@layer utilities`) regardless of source order.
* **Solution:**
  - Always place global element defaults inside `@layer base`.
  - Use `:where()` to drop selector specificity to zero `(0,0,0)`:
    ```css
    @layer base {
        :where(form label, fieldset label) {
            @apply mb-2 block;
        }
    }
    ```
  - This ensures default block labels for standard form fields while allowing any component utility classes (e.g. `<label class="flex items-center gap-2">`) to override seamlessly.

---

### 9. Native Addon Binary Architecture (`lightningcss` musl vs gnu)
* **Symptom:** Container crashes with `Cannot find module 'lightningcss.linux-x64-musl.node'` or `invalid ELF header`, or running `npm` on host removes `musl` binaries from `package-lock.json`.
* **Root Cause:** Host OS is Linux glibc (`gnu`), while the Docker container runs Alpine Linux (`musl`). Node native binaries are architecture-dependent.
* **Solution:**
  1. Define both `lightningcss-linux-x64-musl` and `lightningcss-linux-x64-gnu` under `optionalDependencies` in `package.json`.
  2. ALWAYS run npm commands inside the Docker environment (e.g. `make npm_install` and `make build`). Never run `npm install` directly on the host OS.

---

### 10. Hyvä 1.5.2 i18n Translation Integrity (`i18n/<locale>.csv`)
* **Symptom:** Storefront buttons, tooltips, aria-labels, sorting dropdowns, or price prefixes appear in English ("From %1", "Configure", "Share product", "Sort by", "Set Ascending Direction") on non-English store views.
* **Root Cause:** Hyvä 1.5.2 introduced standardized phrases for accessibility (e.g. `__('From %1')`, `__('Sort By')`, `__('Set Ascending Direction')`, `__('Share product')`, `__('Configure')`).
* **Solution:** Run `./run.sh i18n` to scan templates for untranslated strings, then add missing keys to your theme's `i18n/<locale>.csv`.

---

### 11. Tailwind v4 Modal Backdrop / Overlay Opacity (`bg-opacity-*` Deprecation)
* **Symptom:** Modal backdrop overlays (e.g. dialog popups, search popups, image zoom modals) turn **pitch black solid** (`#000000`) instead of semi-transparent backdrop, completely hiding the background page.
* **Root Cause:**
  - In Tailwind v3, `bg-black bg-opacity-50` split opacity into `--tw-bg-opacity: 0.5`.
  - In Tailwind v4, `@import "tailwindcss"` dropped the legacy `bg-opacity-*` helper classes. `bg-black bg-opacity-50` evaluates only `bg-black` (`background-color: #000;`), ignoring `bg-opacity-50`.
* **Solution:** Replace `bg-black bg-opacity-50` with Tailwind v4 modern slash opacity syntax `bg-black/50` (or `bg-black/20`).

---

### 12. CSS Attribute Selectors Matching Alpine Data Directives
* **Symptom:** Custom popup styling or quantity stepper layout breaks/disappears after updating template `x-data` syntax.
* **Root Cause:** In Hyvä 1.5.2, `x-data="initQtyField()"` was modernized to `x-data="initQtyField"`. Exact attribute match CSS selectors like `[x-data="initQtyField()"]` fail to match.
* **Solution:** Use substring match `[x-data*="initQtyField"]` in CSS stylesheets so the rule applies regardless of whether parentheses are present.

---

### 13. Tailwind v4 Component CSS Cascade Layering (`@layer components`)
* **Symptom:** Utility classes like `.border-0`, `.rounded-none`, `.max-w-full` applied on form elements (e.g. `<select class="form-select ... border-0 ...">`) are ignored, and default `border-width: 1px` persists.
* **Root Cause:** In Tailwind v4, styles declared outside `@layer` are treated as unlayered CSS. Unlayered CSS rules always override `@layer utilities` (including `.border-0`), regardless of declaration order.
* **Solution:** Always wrap component class definitions (e.g. `.form-input, .form-select, ...` in `web/tailwind/components/forms.css`) inside `@layer components { ... }`. This allows utility classes in `@layer utilities` to take precedence over component styles.

---

### 14. `hyva-variables.js: Uncaught SyntaxError: Invalid or unexpected token` / `BASE_URL is not defined`
* **Symptom:** Browser console crashes on initial page load:
  ```
  hyva-variables.js:245 Uncaught SyntaxError: Invalid or unexpected token
  error.js:14 Alpine Expression Error: BASE_URL is not defined
  ReferenceError: CURRENT_STORE_CODE is not defined
  Uncaught TypeError: Cannot read properties of undefined (reading 'lifetime')
  ```
* **Root Cause:**
  `pub/static/deployed_version.txt` was written with a trailing newline (e.g. via `echo $(date +%s) > pub/static/deployed_version.txt`). Magento's `Version\Storage\File` reads this file via `file_get_contents()` without trimming whitespace. Consequently, `var THEME_PATH = 'https://.../version123\n/frontend/...';` splits across lines in raw HTML, causing a fatal JavaScript syntax error in `hyva-variables.js`. Because `hyva-variables.js` terminates prematurely, all Hyvä global variables (`BASE_URL`, `CURRENT_STORE_CODE`, `COOKIE_CONFIG`) are never declared.
* **Solution:**
  1. Remove trailing newline:
     ```bash
     printf "%s" "$(cat pub/static/deployed_version.txt | tr -d '\r\n')" > pub/static/deployed_version.txt
     ```
  2. Flush Magento cache:
     ```bash
     bin/magento cache:clean
     ```
  3. Validate with `./run.sh doctor`.

---

### 15. Hyvä Strict CSP Evaluator & `x-for` Loop Scope Mechanics (`alpine3-csp.js`)
* **Symptom:**
  - After migrating templates for CSP compliance, lists or autocomplete results show blank labels, missing titles, or throw:
    ```
    Alpine Expression Error: Cannot read properties of undefined (reading '...')
    ```
  - Or developers mistakenly wrap simple dot-path properties (like `product.name` or `item.sku`) into complex zero-argument methods on the root component (`productNameHtml`, `itemSku`), which fail because `this.item` or `this.product` does not exist in root context or does not match the loop variable name.
* **Root Cause:**
  - Hyvä's CSP evaluator (`alpine3-csp.js`) evaluates expressions strictly by dot-splitting: `expression.split('.').reduce(...)` over the active component scope stack.
  - Inside an `x-for="item in items"` loop, `item` is placed onto the local scope stack (`completeScope`).
  - Therefore, simple dot-path member accesses like `x-html="item.name"`, `:id="product.sku"`, `:src="item.thumb"` are **100% natively supported** by `alpine3-csp.js` with zero overhead.
  - Conversely, expressions that **violate** the CSP evaluator are:
    - Function calls with arguments: `@click="select(item.id)"`
    - Ternary operators: `:class="item.active ? 'active' : ''"`
    - Binary expressions: `:id="'prefix-' + item.id"`
    - Object literals: `:class="{ 'font-bold': item.is_bold }"`
  - **The Scope Anti-Pattern:** When developers attempt to "fix" CSP compliance by converting `x-html="product.name"` into a root-level method `x-html="productNameHtml"`, `productNameHtml()` evaluates on `this` (the root component), which does NOT automatically know which `product` is currently being rendered unless:
    1. The loop variable in `x-for` is explicitly named `item` and the root method accesses `this.item`. If the loop variable is named `(product, index) in products`, `this.item` is `undefined`!
    2. If the root method was never declared on the parent Alpine component data factory, it fails silently or returns empty string.
* **Best Practices & Rules:**
  1. **Keep Direct Properties Native:** Never replace simple dot-paths (`product.name`, `item.title`, `item.sku`) with root getters. Direct dot access is clean, fast, and fully CSP-compliant.
  2. **Loop Variable Naming Uniformity:** When a root helper method *does* need to access loop context (e.g. for URL construction or complex formatting), always standardize the loop iterator variable name:
     ```html
     <!-- Standardized: (item, index) in items -->
     <template x-for="(item, index) in getSectionData(sectionKey)">
         <a :href="recentSearchUrl" x-html="item.name"></a>
     </template>
     ```
  3. **Reserve Root Methods For Transforms Only:** Only create Alpine helper methods on the root component when logic involves branching, fallback URLs, or conditional formatting:
     ```javascript
     // In Alpine component factory:
     recentSearchUrl() {
         return this.item?.url || '#';
     }
     ```

---

### 16. Fragile CSS Class Attribute Selectors (`[class^="..."]` vs `[class*="..."]`)
* **Symptom:** Page-specific styling works on isolated prototypes but fails to apply on the Hyvä storefront.
* **Root Cause:**
  - CSS selectors written with prefix attribute matcher `[class^="my-page-handle"]` only match elements where the class attribute literally *starts* with that string.
  - In Magento 2 Hyvä layouts, `<body>` classes are dynamically composed and often prepend layout or customer handles (e.g. `<body class="page-layout-1column my-page-handle ...">`).
  - Since `page-layout-1column` comes first, `[class^="..."]` evaluates to `false` and the stylesheet rule is ignored.
* **Solution:**
  - Replace prefix matchers `^=` with substring contains matchers `*=` or standard class selectors:
    ```css
    /* ❌ Fragile: fails if body has layout class first */
    [class^="custom-view-handle"] {
        h1 { @apply text-2xl font-bold; }
    }

    /* ✅ Robust: matches regardless of class order on body */
    [class*="custom-view-handle"] {
        h1 { @apply text-2xl font-bold; }
    }
    ```

---

### 17. Dynamic Tree Traversal in Alpine Components (Optional Chaining in Loops & Recursion)
* **Symptom:**
  - Nested category trees, mega menus, or permission trees crash on initial open or render empty with:
    ```
    Uncaught TypeError: Cannot read properties of undefined (reading 'length')
    ```
* **Root Cause:**
  - Recursive tree templates traverse hierarchical data objects (e.g., `item.children`).
  - Terminal leaf nodes or newly added nodes frequently lack a `children` array (it is `null` or `undefined`).
  - Accessing `this.item.children.length` or `tree.children.length` directly without optional chaining causes a fatal TypeError that stops Alpine execution across the entire component.
* **Solution:**
  - Always guard nested array traversal with optional chaining and fallback:
    ```javascript
    // ❌ Fragile
    if (!tree.children || !tree.children.length) return;
    return this[key].children.length;

    // ✅ Safe & Modern
    if (!tree?.children?.length) return;
    return this[key]?.children?.length || 0;
    ```

---

### 18. `registerInlineScript()` Placement & Output Buffer Corruption
* **Symptom:**
  - Script is blocked by browser CSP even though `registerInlineScript()` is present.
  - Or fatal error / corrupted HTML output buffer: `Call to a member function extractLastElement() on null`.
  - Or an earlier script tag is accidentally hashed/nonced instead of the current one.
* **Root Cause:**
  - In `Hyva\Theme\ViewModel\HyvaCsp`:
    ```php
    $pageContent = rtrim(ob_get_contents());
    $script = $this->htmlPageContent->extractLastElement($pageContent, 'script');
    ```
  - Hyvä inspects PHP's output buffer (`ob_get_contents()`) and extracts the **last closed `<script>...</script>` element**.
  - If `registerInlineScript()` is placed **inside** `<script>`, the closing `</script>` tag has not yet been rendered to the output buffer. `extractLastElement()` fails, returns `null`, or captures a script from a preceding block.
* **Solution:**
  - Always place `<?php isset($hyvaCsp) && $hyvaCsp->registerInlineScript(); ?>` **immediately AFTER the closing `</script>` tag**:
    ```html
    <script>
        function initWidget() { ... }
    </script>
    <?php isset($hyvaCsp) && $hyvaCsp->registerInlineScript(); ?>
    ```

---

### 19. Dynamic Script Hash Growth & Cache Bloat in FPC (Nondeterministic Script Text)
* **Symptom:**
  - CSP response headers bloat dramatically over time (from 219 bytes to 2,105+ bytes).
  - 1 to 30+ SHA-256 hashes accumulate in a script-free cached block, risking HTTP 502/Bad Gateway errors due to header size limits (4KB / 8KB limit in Nginx/Fastly/Varnish).
* **Root Cause:**
  - Dynamic PHP values (`uniqid()`, `microtime()`, `rand()`, dynamic tokens) are embedded directly inside an executable `<script>` tag.
  - Every render produces new script text, causing `HyvaCsp` to generate a NEW SHA-256 hash that accumulates in persistent FPC cache.
* **Solution:**
  - Keep executable JavaScript text **100% deterministic and static**.
  - Pass dynamic values via HTML5 `data-*` attributes or inert JSON (`<script type="application/json">`).

---

### 20. Full Page Cache Race Condition (Shared Cache vs Request-Bound Response)
* **Symptom:**
  - Intermittent CSP policy drops on concurrent cold traffic: `script-src` header disappears or meta tag insertion fails (`meta=0 and script-src=0 on FPC miss`).
  - A bad response wins the cache write and persists in FPC, causing site-wide script blockage.
* **Root Cause:**
  - During concurrent cold requests (FPC miss), worker B inspects worker A's cached response, strips header `script-src`, fails meta insertion, and writes a broken response into the cache.
* **Solution:**
  - Bind all CSP processing and fallback decisions strictly to the **current request and response being sent to the browser** (`controller_front_send_response_before`, `Sutunam HeaderSplitter::afterRender()`, `LaminasCspHeaderProcessor::processHeaders()`).

---

### 21. HTML and JavaScript Registrations Caching Separately (Decoupled Block Caching)
* **Symptom:**
  - Cached product blocks, sliders, or AJAX/Magewire widgets render HTML, but interactivity is dead (`Alpine Expression Error: component is not defined`).
  - Cached product HTML loses its Alpine component registration.
* **Root Cause:**
  - When child blocks or widgets have their own block HTML caching (`cache_lifetime`), the HTML is cached while the `<script>` registration inside the block is skipped on warm cache hit.
* **Solution:**
  - Move reusable component registrations (`Alpine.data('componentName', ...)`) to **stable page-level blocks** (e.g. layout XML in `<head>`) or external companion `.js` files. Keep cached widget templates purely declarative (`<div x-data="componentName" data-...>`).

---

### 22. Verification Under Cache Pressure (Concurrency Testing Protocol)
* **Principle:**
  > **"CSP policy, executable JavaScript, and cache behavior form one reliability contract."**
  Static checks alone cannot prove storefront stability under production FPC load!
* **Testing Protocol:**
  - **Cold cycle:** 5 concurrent requests immediately after `bin/magento cache:flush` (verify valid `script-src` header, no FPC race error).
  - **Warm cycle:** 40 repeated requests on the same URL (verify constant CSP header size, 0 hash accumulation).
  - Run both cycles twice.
  - *Automated tool:* Use `./run.sh test-pressure <URL>` in the `hyva-compat-csp-update` skill.

