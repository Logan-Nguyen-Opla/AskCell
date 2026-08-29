/**
 * viz.js
 * ------
 * Small dependency-free color helper shared by the visualization components:
 *   - categorical color palette (population coloring in FlowViewer/ControlsPanel)
 *
 * Kept tiny and pure so it tree-shakes well and is trivial to test.
 */

/* ----------------------- Categorical colors ----------------------- */
// Accessibility-validated categorical series (fixed order, colorblind-safe on
// dark surfaces). Used for population coloring in the cytometry scatter and
// its legend. Beyond this, we fall back to golden-angle hue rotation so an
// UNLIMITED number of categories stay visually distinct (no looping back onto
// earlier colors).
const CATEGORY_BASE = [
  "#3987e5", // 1 blue
  "#d95926", // 2 orange
  "#199e70", // 3 aqua
  "#c98500", // 4 yellow
  "#d55181", // 5 magenta
  "#008300", // 6 green
  "#9085e9", // 7 violet
  "#e66767", // 8 red
];
const UNKNOWN_RGB = [148, 163, 184]; // slate-400 for cells with no label

function hexToRgb(hex) {
  const h = hex.replace("#", "");
  return [
    parseInt(h.slice(0, 2), 16),
    parseInt(h.slice(2, 4), 16),
    parseInt(h.slice(4, 6), 16),
  ];
}
const CATEGORY_BASE_RGB = CATEGORY_BASE.map(hexToRgb);

function hslToRgb(h, s, l) {
  const hn = (((h % 360) + 360) % 360) / 360;
  const a = s * Math.min(l, 1 - l);
  const f = (n) => {
    const k = (n + hn * 12) % 12;
    return l - a * Math.max(-1, Math.min(k - 3, 9 - k, 1));
  };
  return [Math.round(f(0) * 255), Math.round(f(8) * 255), Math.round(f(4) * 255)];
}

/** Distinct [r,g,b] for category index `i` (any non-negative integer). */
export function categoryRgb(i) {
  if (i == null || i < 0) return UNKNOWN_RGB;
  if (i < CATEGORY_BASE_RGB.length) return CATEGORY_BASE_RGB[i];
  // Golden-angle hue rotation; alternate lightness bands for extra separation.
  const j = i - CATEGORY_BASE_RGB.length;
  const hue = (j * 137.508) % 360;
  const light = j % 2 === 0 ? 0.62 : 0.5;
  return hslToRgb(hue, 0.6, light);
}

/** Distinct hex string for category index `i`. */
export function categoryHex(i) {
  const [r, g, b] = categoryRgb(i);
  const h = (v) => v.toString(16).padStart(2, "0");
  return `#${h(r)}${h(g)}${h(b)}`;
}
