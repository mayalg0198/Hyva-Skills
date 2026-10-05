# CSP Troubleshooting & Edge Cases (Hyvä Compatibility Modules)

This reference documents the root causes, real-world symptoms, and verified fixes for the most critical CSP-related gotchas encountered when upgrading Hyvä compatibility modules, 3rd-party vendor modules, and custom theme overrides.

---

### Gotcha 1: `registerInlineScript()` Placement & Output Buffer Corruption
* **Symptom:**
  - Script is blocked by browser CSP even though `registerInlineScript()` is present.
  - Or fatal error / corrupted HTML output buffer:
    ```
    Call to a member function extractLastElement() on null
    ```
  - Or an earlier script tag is accidentally hashed/nonced instead of the current one.
* **Root Cause:**
  - In `Hyva\Theme\ViewModel\HyvaCsp`:
    ```php
    $pageContent = rtrim(ob_get_contents());
    $script = $this->htmlPageContent->extractLastElement($pageContent, 'script');
    ```
  - Hyvä inspects PHP's output buffer (`ob_get_contents()`) and extracts the **last closed `<script>...</script>` element**.
  - If `registerInlineScript()` is placed **inside** `<script>`, the closing `</script>` tag has not yet been rendered to the output buffer. `extractLastElement()` fails, returns `null`, or captures a script from a preceding block.
* **Fix:**
  - Always place `<?php isset($hyvaCsp) && $hyvaCsp->registerInlineScript(); ?>` **immediately AFTER the closing `</script>` tag**:
    ```html
    <script>
        function initWidget() { ... }
    </script>
    <?php isset($hyvaCsp) && $hyvaCsp->registerInlineScript(); ?>
    ```

---

### Gotcha 2: Fatal PHP Crash When CSP Module is Disabled (`isset($hyvaCsp)`)
* **Symptom:**
  - When CSP module is disabled or in fallback themes, page crashes with:
    ```
    Fatal error: Uncaught Error: Call to a member function registerInlineScript() on null
    // or
    Undefined variable: hyvaCsp
    ```
* **Root Cause:**
  - Calling `$hyvaCsp->registerInlineScript()` bare assumes `$hyvaCsp` is always defined. If the Hyvä CSP module is disabled or if the template is rendered in an area without the ViewModel, `$hyvaCsp` is `null` or undefined.
* **Fix:**
  - Always guard with `isset($hyvaCsp)`:
    ```php
    <?php isset($hyvaCsp) && $hyvaCsp->registerInlineScript(); ?>
    <!-- or -->
    <?php if (isset($hyvaCsp)) $hyvaCsp->registerInlineScript(); ?>
    ```

---

### Gotcha 3: Complex Config Objects in `x-data` Evaluator (`alpine3-csp.js`)
* **Symptom:**
  - Component fails to initialize or console displays:
    ```
    Alpine Error: Alpine is unable to interpret the following expression using the CSP-friendly build:
    "{ filterCode: '...', optionId: 123 }"
    ```
* **Root Cause:**
  - `alpine3-csp.js` cannot evaluate inline JavaScript object literals or function arguments inside `x-data`.
* **Fix (HTML5 `data-*` + Dataset):**
  - Pass all configuration and backend variables via HTML5 `data-*` attributes:
    ```html
    <!-- ❌ Non-CSP: Inline config object -->
    <div x-data="initFilter({ filterCode: 'category', optionId: '42' })">

    <!-- ✅ Hyvä Strict CSP Compliant Pattern -->
    <div x-data="initFilter"
         data-filter-code="category"
         data-option-id="42">
    ```
  - In the Alpine component data factory:
    ```javascript
    function initFilter() {
        return {
            filterCode: null,
            optionId: null,
            init() {
                this.filterCode = this.$el.dataset.filterCode;
                this.optionId = this.$el.dataset.optionId;
            }
        };
    }
    ```

---

### Gotcha 4: Broken Stylesheets from Modernizing `x-data` Syntax
* **Symptom:**
  - After changing `x-data="initQtyField()"` to `x-data="initQtyField"` for CSP compliance, custom CSS styles or layout disappear.
* **Root Cause:**
  - 3rd-party modules or child theme CSS often use exact attribute matchers:
    ```css
    /* Fails when parentheses () are removed */
    [x-data="initQtyField()"] {
        display: flex;
    }
    ```
* **Fix:**
  - Update CSS selectors to substring contains matcher `*=` so they match both with and without parentheses:
    ```css
    /* ✅ Robust matcher */
    [x-data*="initQtyField"] {
        display: flex;
    }
    ```

---

### Gotcha 5: The `x-for` Loop Scope Anti-Pattern
* **Symptom:**
  - After migrating templates for CSP, lists or autocomplete results show blank labels, missing titles, or throw:
    ```
    Alpine Expression Error: Cannot read properties of undefined (reading '...')
    ```
* **Root Cause:**
  - Developers mistakenly wrap simple dot-path properties (like `item.name` or `product.sku`) into root-level methods (`x-html="getItemNameHtml"`).
  - A root method evaluates on `this` (the root component), which does NOT automatically know which `item` is currently being rendered inside `x-for`.
* **Fix:**
  1. **Keep Direct Properties Native:** Inside `x-for="item in items"`, `item` is natively pushed onto Alpine's local scope stack. Simple expressions like `x-html="item.name"`, `:id="item.id"`, `:src="item.thumb"` are **100% natively supported** by `alpine3-csp.js` with zero overhead.
  2. **Standardize Loop Iterator:** When a root helper method *does* need loop context (e.g. for dynamic URLs), standardize the loop variable to `item`:
     ```html
     <template x-for="(item, index) in items">
         <a :href="itemUrl" x-html="item.name"></a>
     </template>
     ```
     ```javascript
     itemUrl() {
         return this.item?.url || '#';
     }
     ```

---

### Gotcha 6: Legacy Alpine v2 `x-spread` & Undefined `eventListeners`
* **Symptom:**
  - Browser console crashes with:
    ```
    Uncaught ReferenceError: eventListeners is not defined
    Uncaught TypeError: Cannot convert undefined or null to object (Expression: "eventListeners")
    ```
* **Root Cause:**
  - `x-spread` was removed in Alpine v3.
  - When vendor modules modernized their data factories to return specific reactive properties rather than an `eventListeners` object, legacy child theme overrides containing `x-bind="eventListeners"` or `x-spread="eventListeners"` crash.
* **Fix:**
  - Remove `x-spread="..."` and bind discrete event listeners or attributes directly:
    ```html
    <!-- ❌ Legacy v2 -->
    <li x-data="initInput" x-bind="eventListeners" x-spread="eventListeners">

    <!-- ✅ Alpine v3 Strict CSP -->
    <li x-data="initInput"
        @click="handleClick"
        @keydown.enter="handleEnter">
    ```

---

### Gotcha 7: Dynamic Tree Traversal & Optional Chaining in Alpine Components
* **Symptom:**
  - Nested category trees, mega menus, or permission trees crash with:
    ```
    Uncaught TypeError: Cannot read properties of undefined (reading 'length')
    ```
* **Root Cause:**
  - Terminal leaf nodes lack a `children` array (`undefined`).
  - In standard Alpine without CSP, uncaught errors could sometimes be masked by eval fallback, but in strict CSP mode, unhandled TypeErrors halt component execution completely.
* **Fix:**
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

### Gotcha 8: Dynamic Script Hash Growth & Cache Bloat (Nondeterministic Script Text)
* **Symptom:**
  - CSP response headers bloat dramatically over time (from 219 bytes to 2,105+ bytes).
  - 1 to 30+ SHA-256 hashes accumulate in a script-free cached block, risking HTTP 502/Bad Gateway errors due to header size limits (4KB / 8KB limit in Nginx/Fastly/Varnish).
* **Root Cause:**
  - Dynamic PHP values (such as `<?= uniqid() ?>`, timestamps, random IDs, or session tokens) are embedded directly inside an executable `<script>` tag:
    ```html
    <!-- ❌ Root Cause: Nondeterministic script text -->
    <script>
        const token = '<?= uniqid() ?>';
        const widgetId = 'widget_<?= microtime(true) ?>';
    </script>
    <?php isset($hyvaCsp) && $hyvaCsp->registerInlineScript(); ?>
    ```
  - **Every single render produces new script text**, causing `HyvaCsp` to generate a NEW SHA-256 hash. These hashes accumulate in the persistent Full Page Cache (FPC) state.
* **Fix (Stable Pattern):**
  - Keep executable JavaScript text **100% deterministic and static**.
  - Pass all dynamic tokens, IDs, and session data via HTML5 `data-*` attributes or inert JSON (`<script type="application/json">`):
    ```html
    <!-- ✅ Stable Pattern: Static script text, dynamic HTML data -->
    <div data-token="<?= $escaper->escapeHtmlAttr($token) ?>"
         data-widget-id="<?= $escaper->escapeHtmlAttr($widgetId) ?>"
         x-data="myComponent">
    </div>

    <script>
        Alpine.data('myComponent', () => ({
            token: null,
            init() {
                this.token = this.$el.dataset.token;
            }
        }));
    </script>
    <?php isset($hyvaCsp) && $hyvaCsp->registerInlineScript(); ?>
    ```

---

### Gotcha 9: Full Page Cache Race Condition (Shared Cache vs Request-Bound Response)
* **Symptom:**
  - Intermittent CSP policy drops on high-concurrency cold traffic: `script-src` header disappears or meta tag insertion fails (`meta=0 and script-src=0 on FPC miss`).
  - A bad response wins the cache write and persists in FPC, causing site-wide script blockage.
* **Root Cause:**
  - During concurrent cold requests (FPC miss), multiple workers render concurrently:
    - Worker A renders healthy HTML and writes to cache.
    - Worker B inspects Worker A's cached response, strips header `script-src`, fails meta insertion, and writes a broken response into the cache.
  - Occurs when policy collectors inspect shared cached state rather than the request-bound response.
* **Fix (Response Path Binding):**
  - Bind all CSP processing and fallback decisions strictly to the **current request and response being sent to the browser**:
    - Hook into `controller_front_send_response_before`.
    - Apply response processors (e.g. `Sutunam HeaderSplitter::afterRender()`, `LaminasCspHeaderProcessor::processHeaders()`).
    - Ensure FPC hits do not create false-positive fallback logs.

---

### Gotcha 10: HTML and JavaScript Registrations Caching Separately (Decoupled Block Caching)
* **Symptom:**
  - Cached product blocks, sliders, or AJAX/Magewire widgets render HTML, but interactivity is dead (`Alpine Expression Error: component is not defined`).
  - Cached product HTML loses its Alpine component registration.
* **Root Cause:**
  - When child blocks or widgets have their own block HTML caching (`cache_lifetime`), the HTML is cached while the `<script>` registration inside the block is skipped on warm cache hit.
  - Or the script hash is not re-collected on block cache retrieval.
* **Fix:**
  - **Decouple component registration from dynamic block HTML**:
    - Move reusable registrations (`Alpine.data('componentName', ...)`) to **stable page-level blocks** (e.g. layout XML in `<head>` or main layout template) or external companion `.js` files.
    - Keep cached widget templates purely declarative (`<div x-data="componentName" data-...>`).

---

### Gotcha 11: Verification Under Cache Pressure (Static Gate & Concurrency Protocol)
* **Principle:**
  > **"CSP policy, executable JavaScript, and cache behavior form one reliability contract."**
  Static checks alone cannot prove storefront stability under production FPC load!
* **Testing Protocol:**
  1. **Pre-Push Static Gate:**
     - Run AST auditor to reject nondeterministic expressions (`uniqid`, `time`, `rand`) inside `<script>`.
  2. **Runtime Verification Under Cache Pressure:**
     - **Cold cycle:** 5 concurrent requests (`curl` or benchmark) immediately after `bin/magento cache:flush`.
       - *Verify:* HTTP 200, valid `script-src` header present, no FPC race error.
     - **Warm cycle:** 40 repeated requests on the same URL.
       - *Verify:* Constant CSP header size (0 hash accumulation), persistent FPC hit.
     - Run both cycles twice.

