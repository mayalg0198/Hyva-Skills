# Alpine.js v3 Strict CSP Rules & Evaluator Mechanics (`alpine3-csp.js`)

In stores enforcing Content Security Policy (strict CSP without `'unsafe-eval'`), standard Alpine.js cannot use its default JavaScript expression parser (which relies on `new Function(...)` or `eval()`).

Hyvä Theme solves this with a dedicated CSP-compliant evaluator: `alpine3-csp.js`.

---

## 1. How `alpine3-csp.js` Evaluates Expressions

Instead of evaluating raw JavaScript strings, `alpine3-csp.js` evaluates expressions by **dot-splitting**:
```javascript
expression.split('.').reduce((scope, key) => scope?.[key], currentScope)
```

### ✅ What is 100% Natively Supported
1. **Simple Dot-Path Property Access:**
   ```html
   <span x-text="product.name"></span>
   <img :src="item.thumbnail" :alt="item.title">
   <div :id="section.code"></div>
   ```
2. **Zero-Argument Function Calls & Handlers:**
   ```html
   <button @click="submitForm">Submit</button>
   <button @click="toggleMenu()">Toggle</button>
   ```
3. **Native `x-for` Loop Scopes:**
   Inside `x-for="item in items"`, `item` is placed on Alpine's scope stack (`completeScope`). Direct dot-path member accesses on `item` work natively with zero overhead!
   ```html
   <template x-for="item in items">
       <div :id="item.id" x-text="item.name"></div>
   </template>
   ```
4. **Standard Event Listeners & Modifiers:**
   ```html
   <div @click.outside="close" @keydown.window.escape="close">
   ```

---

## 2. Forbidden Syntax & Refactoring Recipes

### ❌ 1. Function Calls with Arguments
* **Forbidden:**
  ```html
  <button @click="selectItem(item.id, index)">Select</button>
  ```
* **Why it fails:** `alpine3-csp.js` does not parse argument lists; attempting to run arguments triggers `unsafe-eval` errors.
* **✅ CSP Compliant Fix (HTML5 `data-*` + Dataset):**
  ```html
  <button @click="selectItem"
          data-item-id="<?= $escaper->escapeHtmlAttr($item->getId()) ?>"
          data-index="<?= (int)$index ?>">
      Select
  </button>
  ```
  ```javascript
  // In Alpine component JS factory:
  selectItem(event) {
      const itemId = event.currentTarget.dataset.itemId;
      const index = parseInt(event.currentTarget.dataset.index, 10);
      // Execute logic cleanly
  }
  ```

---

### ❌ 2. Ternary Operators (`a ? b : c`)
* **Forbidden:**
  ```html
  <div :class="isSelected ? 'bg-primary text-white' : 'bg-gray-100 text-black'">
  ```
* **Why it fails:** Ternary operators `?` and `:` are not dot-paths.
* **✅ CSP Compliant Fix (Component Getter):**
  ```html
  <div :class="itemClass">
  ```
  ```javascript
  // In Alpine component JS factory:
  get itemClass() {
      return this.isSelected
          ? 'bg-primary text-white'
          : 'bg-gray-100 text-black';
  }
  ```

---

### ❌ 3. Object Literals in Class Bindings
* **Forbidden:**
  ```html
  <li :class="{ 'active text-blue-600': isActive, 'disabled': isDisabled }">
  ```
* **Why it fails:** Object literals `{ ... }` require JS evaluation.
* **✅ CSP Compliant Fix:**
  ```html
  <li :class="statusClass">
  ```
  ```javascript
  // In Alpine component JS factory:
  get statusClass() {
      const classes = [];
      if (this.isActive) classes.push('active', 'text-blue-600');
      if (this.isDisabled) classes.push('disabled');
      return classes.join(' ');
  }
  ```

---

### ❌ 4. String Concatenation & Arithmetic
* **Forbidden:**
  ```html
  <div :id="'tab-panel-' + tabId" :style="'width: ' + progress + '%'">
  ```
* **Why it fails:** `+` operator requires JS evaluation.
* **✅ CSP Compliant Fix:**
  ```html
  <div :id="tabPanelId" :style="progressStyle">
  ```
  ```javascript
  // In Alpine component JS factory:
  get tabPanelId() {
      return `tab-panel-${this.tabId}`;
  },
  get progressStyle() {
      return `width: ${this.progress}%`;
  }
  ```

### ❌ 5. Comparison Expressions (`===`, `!==`, `<`, `>`, etc.)
* **Forbidden:**
  ```html
  <div x-show="activeVideoType === 'youtube'" :class="{ 'hidden': activeVideoType !== 'youtube' }">
  ```
* **Why it fails:** `alpine3-csp.js` evaluator only parses dot-paths (`split('.')`). Comparison operators trigger CSP syntax errors.
* **✅ CSP Compliant Fix:**
  ```html
  <div x-show="isYoutubeVideo" :class="youtubeHiddenClass">
  ```
  ```javascript
  // In Alpine component JS factory:
  get isYoutubeVideo() {
      return this.activeVideoType === 'youtube';
  },
  get youtubeHiddenClass() {
      return this.activeVideoType !== 'youtube' ? 'hidden' : '';
  }
  ```

---

### ❌ 6. Logical Operators (`&&`, `||`)
* **Forbidden:**
  ```html
  <div x-show="isOpen && hasItems" :disabled="isLoading || hasErrors">
  ```
* **Why it fails:** Logical operators `&&` and `||` cannot be evaluated by dot-path splitting.
* **✅ CSP Compliant Fix:**
  ```html
  <div x-show="shouldShowDropdown" :disabled="isButtonDisabled">
  ```
  ```javascript
  // In Alpine component JS factory:
  get shouldShowDropdown() {
      return this.isOpen && this.hasItems;
  },
  get isButtonDisabled() {
      return this.isLoading || this.hasErrors;
  }
  ```

---

### ❌ 7. Config Objects in `x-data`
* **Forbidden:**
  ```html
  <div x-data="initComponent({ filterCode: 'category', optionId: 42, isMulti: true })">
  ```
* **Why it fails:** Object literal arguments in `x-data` violate the CSP evaluator.
* **✅ CSP Compliant Fix (HTML5 `data-*` Attributes):**
  ```html
  <div x-data="initComponent"
       data-filter-code="category"
       data-option-id="42"
       data-is-multi="true">
  ```
  ```javascript
  function initComponent() {
      return {
          filterCode: null,
          optionId: null,
          isMulti: false,
          init() {
              this.filterCode = this.$el.dataset.filterCode;
              this.optionId = parseInt(this.$el.dataset.optionId, 10);
              this.isMulti = this.$el.dataset.isMulti === 'true';
          }
      };
  }
  ```

---

## 3. The `x-for` Scope Mechanics & Iterator Standardization

> [!WARNING]
> **Do not over-engineer simple loop properties into root getters!**

When refactoring for CSP, developers sometimes mistakenly convert simple properties like `x-html="item.name"` into root component getters like `x-html="getItemNameHtml"`.

**Why this breaks:**
A method on the root component evaluates in root context (`this`). It does NOT automatically know which `item` is currently being rendered inside an `x-for` loop unless the loop iterator matches and is passed in.

* **Keep simple properties native:**
  Inside `x-for="item in items"`, `item` is pushed directly onto Alpine's local scope stack. Simple member accesses work natively without overhead:
  ```html
  <!-- ✅ 100% CSP compliant, fast, and simple -->
  <template x-for="item in items">
      <span x-text="item.name"></span>
  </template>
  ```
* **Standardize iterator naming when helper methods are needed:**
  When a root helper method *does* need loop context (e.g. for dynamic URLs or formatted values), always standardize the loop iterator variable name to `item`:
  ```html
  <template x-for="(item, index) in items">
      <a :href="itemUrl" x-html="item.name"></a>
  </template>
  ```
  ```javascript
  // Root method safely accessing loop variable item:
  itemUrl() {
      return this.item?.url || '#';
  }
  ```

---

## 4. Dynamic Tree Traversal & Optional Chaining

In nested structures (mega menus, permission trees, category hierarchies), terminal leaf nodes frequently lack a `children` array:

* **Fragile (Triggers fatal TypeError under CSP):**
  ```javascript
  if (!tree.children || !tree.children.length) return;
  return this[key].children.length;
  ```
* **Safe & Modern (Optional Chaining):**
  ```javascript
  if (!tree?.children?.length) return;
  return this[key]?.children?.length || 0;
  ```

---

## 5. CSS Attribute Selector Gotcha (`[x-data*="..."]`)

When modernizing `x-data="initQtyField()"` to `x-data="initQtyField"` for CSP compliance, exact attribute CSS selectors break:
```css
/* ❌ Breaks when parentheses are removed */
[x-data="initQtyField()"] { ... }

/* ✅ Robust: matches with or without parentheses */
[x-data*="initQtyField"] { ... }
```
