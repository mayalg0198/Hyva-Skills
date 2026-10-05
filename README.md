# Hyvä AI Agent Skills Suite (`Hyva-Skills`)

> **Production-grade AI agent skills, automated toolkits, and runbooks for Hyvä Themes on Magento 2 / Adobe Commerce.**

Compatible with [Google Antigravity](https://antigravity.dev), Claude Code, Cursor, Windsurf, and other modern agentic coding environments.

---

## 📦 Included Skills

| Skill | Description | Key Capabilities |
| :--- | :--- | :--- |
| [**`hyva-compat-csp-update`**](./hyva-compat-csp-update) | **Strict CSP Upgrade Toolkit** | AST template auditing, automated `$hyvaCsp` nonce registration, Alpine 3 CSP conversion, FPC cache pressure verification |
| [**`hyva-theme-upgrade`**](./hyva-theme-upgrade) | **Hyvä Theme & Tailwind Upgrade** | Version-aware theme migration, Tailwind v3 → v4 migration, vendor template diffing, visual regression testing, i18n audit |

---

## 🚀 Installation & Usage

### 1. In a Magento Project (`.agents/skills`)
To use these skills directly with your AI coding assistant within a Magento 2 repository:

```bash
mkdir -p .agents/skills

# Clone the suite into your project's .agents directory:
git clone https://github.com/mayalg0198/Hyva-Skills.git .agents/skills/hyva-skills-temp
cp -r .agents/skills/hyva-skills-temp/hyva-compat-csp-update .agents/skills/
cp -r .agents/skills/hyva-skills-temp/hyva-theme-upgrade .agents/skills/
rm -rf .agents/skills/hyva-skills-temp
```

### 2. Global Installation (Machine-Wide)
To make these skills available across all projects on your machine (Antigravity):

```bash
mkdir -p ~/.gemini/config/skills
git clone https://github.com/mayalg0198/Hyva-Skills.git ~/.gemini/config/skills/hyva-skills-repo
cp -r ~/.gemini/config/skills/hyva-skills-repo/hyva-compat-csp-update ~/.gemini/config/skills/
cp -r ~/.gemini/config/skills/hyva-skills-repo/hyva-theme-upgrade ~/.gemini/config/skills/
rm -rf ~/.gemini/config/skills/hyva-skills-repo
```

---

## 🛠️ CLI Quick Reference

Both skills feature standalone, unified shell runners (`run.sh`) that can be executed directly from terminal or by AI agents.

### Hyvä Strict CSP Toolkit (`hyva-compat-csp-update`)

```bash
# Doctor: Check environment & dependencies
./hyva-compat-csp-update/run.sh doctor

# Audit: Scan templates for strict CSP antipatterns
./hyva-compat-csp-update/run.sh audit app/code/Vendor/ModuleHyvaCompatibility

# Fix: Automatically inject backwards-compatible script nonces
./hyva-compat-csp-update/run.sh fix-scripts app/code/Vendor/ModuleHyvaCompatibility --dry-run
./hyva-compat-csp-update/run.sh fix-scripts app/code/Vendor/ModuleHyvaCompatibility

# Suggest: Get Alpine.js CSP refactoring recipes
./hyva-compat-csp-update/run.sh suggest path/to/template.phtml

# Test Pressure: Validate FPC cache stability under load
./hyva-compat-csp-update/run.sh test-pressure https://store.test/product-url
```

### Hyvä Theme Upgrade Toolkit (`hyva-theme-upgrade`)

```bash
# Doctor: Verify environment and config
./hyva-theme-upgrade/run.sh doctor

# Audit: Audit theme overrides, vendor diffs, legacy directives, and i18n
./hyva-theme-upgrade/run.sh audit

# Fetch changelog: Inspect vendor differences between versions
./hyva-theme-upgrade/run.sh fetch-changelog 1.4.3 1.5.2

# Visual diff: Compare staging vs local rendered output
./hyva-theme-upgrade/run.sh visual-diff
```

---

## 📖 Documentation & Guides

- [`hyva-compat-csp-update` Documentation](./hyva-compat-csp-update/README.md)
  - [Alpine v3 CSP Rules & Migration](./hyva-compat-csp-update/references/alpine3-csp-rules.md)
  - [CSP Troubleshooting & Gotchas](./hyva-compat-csp-update/references/csp-troubleshooting-gotchas.md)
  - [Inline Script Nonce Patterns](./hyva-compat-csp-update/references/inline-script-patterns.md)
- [`hyva-theme-upgrade` Documentation](./hyva-theme-upgrade/README.md)
  - [Troubleshooting & Gotchas](./hyva-theme-upgrade/references/troubleshooting-gotchas.md)
  - [Upgrade Matrix by Page](./hyva-theme-upgrade/references/upgrade-matrix-by-page.md)
  - [Commerce Modules Changelog](./hyva-theme-upgrade/references/changelog-commerce-modules.md)

---

## 🤝 Contributing

Contributions, issues, and feature requests for new Hyvä migration tools and agent skills are welcome! Feel free to open an issue or pull request.
