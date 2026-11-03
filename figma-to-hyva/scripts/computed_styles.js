// Run in the page (Claude in Chrome `javascript_tool`, or DevTools). Replace SELECTOR first.
// Returns compact JSON of computed styles for every text element inside the block, to feed
// scripts/style_compare.py together with spec.json. Output is small on purpose (text elements only).
(() => {
  const SELECTOR = '__SELECTOR__';
  const root = document.querySelector(SELECTOR);
  if (!root) return JSON.stringify({ error: 'selector matched nothing: ' + SELECTOR });
  const rgb2hex = (c) => {
    const m = c.match(/\d+(\.\d+)?/g);
    if (!m) return c;
    return '#' + m.slice(0, 3).map((n) => Math.round(+n).toString(16).padStart(2, '0')).join('');
  };
  const out = [];
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT);
  for (let el = root; el; el = walker.nextNode()) {
    const own = [...el.childNodes].filter((n) => n.nodeType === 3).map((n) => n.textContent.trim()).join(' ').trim();
    if (!own) continue;
    const cs = getComputedStyle(el);
    const r = el.getBoundingClientRect();
    out.push({
      text: own.slice(0, 40),
      tag: el.tagName.toLowerCase(),
      size: parseFloat(cs.fontSize),
      lh: cs.lineHeight === 'normal' ? null : parseFloat(cs.lineHeight),
      weight: parseInt(cs.fontWeight, 10),
      family: cs.fontFamily.split(',')[0].replace(/["']/g, '').trim(),
      color: rgb2hex(cs.color),
      w: Math.round(r.width),
      h: Math.round(r.height),
    });
    if (out.length >= 60) break;
  }
  return JSON.stringify({ viewport: innerWidth, items: out });
})();
