# Inline Script Patterns & CSP Nonce Registration

In Magento 2 with Hyvä Theme under strict Content Security Policy, all inline `<script>` blocks must be authorized with a cryptographic nonce or SHA256 script hash registered in Magento's CSP policy.

---

## 1. Canonical Hyvä Nonce Registration

Hyvä provides `Hyva\Theme\ViewModel\HyvaCsp`; its template engine plugin injects it as `$hyvaCsp` into **every** template, like `$escaper`. Hyvä's own templates call it bare: `<?php $hyvaCsp->registerInlineScript() ?>`.

### The Standard Pattern:
Place this line **immediately AFTER the closing `</script>` tag**:
```html
<script>
    'use strict';

    function initMyCompatComponent() {
        return {
            // component logic
        };
    }
</script>
<?php isset($hyvaCsp) && $hyvaCsp->registerInlineScript(); ?>
```

### Why It MUST Be Placed AFTER `</script>` (Output Buffering):
In `vendor/hyva-themes/magento2-theme-module/src/ViewModel/HyvaCsp.php`:
```php
$pageContent = rtrim(ob_get_contents());
$script = $this->htmlPageContent->extractLastElement($pageContent, 'script');
```
Hyvä inspects PHP's output buffer (`ob_get_contents()`) and extracts the **last closed `<script>...</script>` element**.
- If placed **inside** `<script>`, the closing `</script>` tag has not yet been outputted to the buffer. `extractLastElement` fails (returns `null`), no nonce or hash is generated, or worse, it captures an earlier script tag from preceding blocks and corrupts the buffer via `ob_clean()`.
- If placed **immediately after `</script>`**, the element is completely flushed to the buffer, allowing Hyvä to calculate the SHA-256 hash or inject the nonce attribute cleanly.

### When to use the `isset($hyvaCsp)` guard:
- Not needed in Hyvä-only themes/modules: `$hyvaCsp` is always injected, and on stores that allow inline scripts `registerInlineScript()` just returns.
- Needed in compat modules whose templates may also render on **Luma** or on theme-module versions that predate `$hyvaCsp` — there a bare call is a fatal `Call to a member function registerInlineScript() on null`.
- The guarded form `isset($hyvaCsp) && $hyvaCsp->registerInlineScript();` is harmless everywhere, so the audit accepts both.

---

## 2. Injected ViewModels in Custom Layouts (rarely needed)

`$hyvaCsp` is already available in templates rendered by Hyvä. Inject it explicitly only for templates rendered outside Hyvä's template engine (e.g. a custom renderer), via layout XML:

```xml
<?xml version="1.0"?>
<page xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
      xsi:noNamespaceSchemaLocation="urn:magento:framework:View/Layout/etc/page_configuration.xsd">
    <body>
        <referenceBlock name="my.compat.block">
            <arguments>
                <argument name="hyva_csp" xsi:type="object">Hyva\Theme\ViewModel\HyvaCsp</argument>
            </arguments>
        </referenceBlock>
    </body>
</page>
```

In the `.phtml` template:
```php
<?php
/** @var \Hyva\Theme\ViewModel\HyvaCsp $hyvaCsp */
$hyvaCsp = $block->getData('hyva_csp');
?>
<script>
    // JS code
</script>
<?php isset($hyvaCsp) && $hyvaCsp->registerInlineScript(); ?>
```

---

## 3. Companion JS Architecture (External Scripts)

For complex compatibility modules (e.g. Swatches, Ajax Cart, Mega Menu), the cleanest architectural pattern is **externalizing the Alpine component script** into a dedicated companion `.js` file or component script template:

### Structure:
```text
view/frontend/
├── templates/
│   ├── product/view/swatches.phtml
│   └── js/swatches-component-script.phtml
└── web/
    └── js/swatches.js
```

### Registration via `alpine:init`:
In `view/frontend/web/js/swatches.js`:
```javascript
document.addEventListener('alpine:init', () => {
    Alpine.data('initMySwatches', () => ({
        selectedOption: null,
        init() {
            // initialization
        },
        select(event) {
            this.selectedOption = event.currentTarget.dataset.optionId;
        }
    }));
});
```

And in layout XML, load it as a standard static asset:
```xml
<head>
    <script src="Vendor_ModuleHyvaCompatibility::js/swatches.js"/>
</head>
```
*Benefits:* External `.js` files loaded via `<script src="...">` are automatically covered by standard CSP script-src origin policies without needing per-block nonces!
