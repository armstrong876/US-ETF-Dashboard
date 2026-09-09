/* ═══════════════════════════════════════════════════════════
   Armstrong Capital — ETF PDF Report Design System
   etf-pdf-design.js | Shared palette, typography, and vector
   drawing primitives used by every page of the report.

   Built once, locked. All 6 report pages must draw through
   these helpers so the report stays visually consistent as
   pages are added — never hardcode a color/size inline.
═══════════════════════════════════════════════════════════ */

'use strict';

const PDF = {
  // ── A4 canvas, all coordinates in points (pt) ──
  PAGE_W: 595.28,
  PAGE_H: 841.89,
  MARGIN: 32,

  // ── Locked color palette ──
  COLOR: {
    primaryBlue:   '#0B2A78',
    secondaryBlue: '#174EA6',
    green:         '#2E8B57',
    lightGreen:    '#DFF5E8',
    red:           '#D9534F',
    lightGrey:     '#F7F9FC',
    border:        '#E5EAF2',
    text:          '#14213D',
    textSecondary: '#6B7280',
    white:         '#FFFFFF',
  },

  // ── Typography scale (pt) — matches the brief's px hierarchy ──
  TYPE: {
    heroTitle:     36,  // 32-40px range, cover page hero
    sectionHead:   24,  // 22-26px range
    cardTitle:     16,  // 15-17px range
    body:          11.5,
    note:          9.5,
  },
};

// ── Color helpers ─────────────────────────────────────────
function hexToRgb(hex) {
  const h = hex.replace('#', '');
  return [
    parseInt(h.substring(0, 2), 16),
    parseInt(h.substring(2, 4), 16),
    parseInt(h.substring(4, 6), 16),
  ];
}
function setFill(doc, hex) { const [r, g, b] = hexToRgb(hex); doc.setFillColor(r, g, b); }
function setText(doc, hex) { const [r, g, b] = hexToRgb(hex); doc.setTextColor(r, g, b); }
function setDraw(doc, hex) { const [r, g, b] = hexToRgb(hex); doc.setDrawColor(r, g, b); }

// ── Rounded card with an optional soft shadow (simulated via a
// low-opacity offset duplicate — jsPDF has no native blur/shadow) ──
function roundedCard(doc, x, y, w, h, opts = {}) {
  const {
    fill = PDF.COLOR.white,
    border = PDF.COLOR.border,
    radius = 11,
    shadow = true,
  } = opts;

  if (shadow) {
    doc.saveGraphicsState();
    doc.setGState(new doc.GState({ opacity: 0.06 }));
    setFill(doc, PDF.COLOR.text);
    doc.roundedRect(x + 1.5, y + 2.5, w, h, radius, radius, 'F');
    doc.restoreGraphicsState();
  }

  setFill(doc, fill);
  setDraw(doc, border);
  doc.setLineWidth(0.75);
  doc.roundedRect(x, y, w, h, radius, radius, 'FD');
}

// ── Vertical multi-band gradient fill (robust fallback — true PDF
// shading is version-finicky, so we approximate with N thin bands) ──
function gradientRect(doc, x, y, w, h, hexFrom, hexTo, steps = 40) {
  const from = hexToRgb(hexFrom), to = hexToRgb(hexTo);
  const bandH = h / steps;
  for (let i = 0; i < steps; i++) {
    const t = i / (steps - 1);
    const r = Math.round(from[0] + (to[0] - from[0]) * t);
    const g = Math.round(from[1] + (to[1] - from[1]) * t);
    const b = Math.round(from[2] + (to[2] - from[2]) * t);
    doc.setFillColor(r, g, b);
    doc.rect(x, y + i * bandH, w, bandH + 0.5, 'F'); // +0.5 avoids hairline seams
  }
}

// ── Section header: accent bar + heading text, used to open a
// content block consistently on every page ──
function sectionHeader(doc, text, x, y, opts = {}) {
  const { subtitle = null, color = PDF.COLOR.primaryBlue } = opts;
  setFill(doc, color);
  doc.roundedRect(x, y - 13, 4, 18, 1.5, 1.5, 'F');
  setText(doc, PDF.COLOR.text);
  doc.setFont('helvetica', 'bold');
  doc.setFontSize(PDF.TYPE.sectionHead * 0.72); // section headers inside body pages read a touch smaller than a hero
  doc.text(text, x + 12, y);
  if (subtitle) {
    setText(doc, PDF.COLOR.textSecondary);
    doc.setFont('helvetica', 'normal');
    doc.setFontSize(PDF.TYPE.note);
    doc.text(subtitle, x + 12, y + 13);
  }
  doc.setFont('helvetica', 'normal');
}

// ── KPI card: label + big value + optional delta, in a rounded card ──
function kpiCard(doc, x, y, w, h, { icon = null, label, value, valueColor = PDF.COLOR.text, sub = null }) {
  roundedCard(doc, x, y, w, h, { fill: PDF.COLOR.white });
  const pad = 12;
  let cursorY = y + pad + 8;

  if (icon) {
    setText(doc, PDF.COLOR.secondaryBlue);
    doc.setFontSize(14);
    doc.text(icon, x + pad, cursorY);
    cursorY += 16;
  }

  setText(doc, PDF.COLOR.textSecondary);
  doc.setFont('helvetica', 'bold');
  doc.setFontSize(8.5);
  doc.text(String(label).toUpperCase(), x + pad, cursorY);
  cursorY += 16;

  setText(doc, valueColor);
  doc.setFont('helvetica', 'bold');
  doc.setFontSize(PDF.TYPE.cardTitle + 4);
  doc.text(String(value), x + pad, cursorY);

  if (sub) {
    cursorY += 13;
    setText(doc, PDF.COLOR.textSecondary);
    doc.setFont('helvetica', 'normal');
    doc.setFontSize(PDF.TYPE.note);
    doc.text(String(sub), x + pad, cursorY);
  }
  doc.setFont('helvetica', 'normal');
}

// ── Footer: page number, disclaimer strip, and (last page only)
// the RM/advisor attribution line ──
function drawFooter(doc, pageNum, totalPages, opts = {}) {
  const { showAdvisor = false, rm = null } = opts;
  const y = PDF.PAGE_H - 26;

  setDraw(doc, PDF.COLOR.border);
  doc.setLineWidth(0.6);
  doc.line(PDF.MARGIN, y - 10, PDF.PAGE_W - PDF.MARGIN, y - 10);

  setText(doc, PDF.COLOR.textSecondary);
  doc.setFont('helvetica', 'normal');
  doc.setFontSize(PDF.TYPE.note);
  doc.text('Armstrong Capital — For informational purposes only. Not investment advice.',
    PDF.MARGIN, y);
  doc.text(`Page ${pageNum} of ${totalPages}`, PDF.PAGE_W - PDF.MARGIN, y, { align: 'right' });

  if (showAdvisor && rm && rm.name) {
    setText(doc, PDF.COLOR.text);
    doc.setFont('helvetica', 'bold');
    doc.setFontSize(PDF.TYPE.note);
    const line = `Prepared for you by: ${rm.name}  |  ${rm.mobile || '—'}  |  ${rm.email || '—'}`;
    doc.text(line, PDF.PAGE_W / 2, y + 12, { align: 'center' });
    doc.setFont('helvetica', 'normal');
  }
}

// ── Simple vector sparkline (mini trend line) inside a bounded box ──
function sparkline(doc, x, y, w, h, values, opts = {}) {
  if (!values || values.length < 2) return;
  const { color = PDF.COLOR.secondaryBlue, lineWidth = 1.2 } = opts;
  const min = Math.min(...values), max = Math.max(...values);
  const range = (max - min) || 1;
  const pts = values.map((v, i) => [
    x + (i / (values.length - 1)) * w,
    y + h - ((v - min) / range) * h,
  ]);

  setDraw(doc, color);
  doc.setLineWidth(lineWidth);
  for (let i = 0; i < pts.length - 1; i++) {
    doc.line(pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1]);
  }
  // end dot
  setFill(doc, color);
  doc.circle(pts[pts.length - 1][0], pts[pts.length - 1][1], 1.6, 'F');
}
