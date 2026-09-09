/* ═══════════════════════════════════════════════════════════
   Armstrong Capital — ETF PDF Report Builder (HTML-render engine)
   etf-pdf-report.js

   Approach: build the report as real HTML A4 pages (styled by
   etf-report.css to duplicate the reference factsheet), capture
   each page with html2canvas, and assemble them into a single PDF
   with jsPDF. This matches the reference design far more precisely
   than hand-plotting coordinates.

   ALL numbers come from data already loaded on the live ETF page —
   nothing is fetched or recomputed here:
     ctx.etfObj     dashboard.json entry (price, aum, returns, ...)
     ctx.meta       etf_detail_data.json[symbol] (composition, holdings, description)
     ctx.analytics  etf_analytics.json etfs[symbol] (monthly returns + risk)
     ctx.mainData   dashboard.json (as_of_date, spy_returns)
     ctx.rm         { name, mobile, email } captured before download

   STATUS: Pages 1-2 built. Pages 3-7 added in the next round.
═══════════════════════════════════════════════════════════ */

'use strict';

const RP_TOTAL_PAGES = 7;
const RP_COMPANY_WEBSITE = 'www.armstrong-cap.com';   // fixed company website

// ── small formatting helpers (mirror the live page's own formatting) ──
function rpEsc(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
function rpAum(v) {
  if (v == null || isNaN(v)) return '—';
  if (v >= 1e12) return '$' + (v / 1e12).toFixed(2) + 'T';
  if (v >= 1e9)  return '$' + (v / 1e9).toFixed(1) + 'B';
  if (v >= 1e6)  return '$' + (v / 1e6).toFixed(1) + 'M';
  return '$' + v.toLocaleString();
}
function rpPct(v, dp) {
  if (v == null || isNaN(v)) return '—';
  dp = dp == null ? 2 : dp;
  return (v >= 0 ? '+' : '') + v.toFixed(dp) + '%';
}
function rpDateLong(iso) {
  if (!iso) return '—';
  const d = new Date(String(iso).slice(0, 10) + 'T00:00:00');
  if (isNaN(d)) return iso;
  const MON = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  return d.getDate() + ' ' + MON[d.getMonth()] + ' ' + d.getFullYear();
}
function rpInceptionYear(iso) {
  if (!iso) return '—';
  const d = new Date(String(iso).slice(0, 10) + 'T00:00:00');
  if (isNaN(d)) return iso;
  const MON = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  return MON[d.getMonth()] + ' ' + d.getFullYear();
}

// Reusable content-page header + footer (pages 2-7)
function rpHeader(ctx) {
  return `
    <div class="rp-header">
      <div class="rp-header-label">ETF Profile — ${rpEsc(ctx.symbol)} · ${rpEsc(ctx.etfObj.name || '')}</div>
      <div class="rp-header-logo"><img src="armstrong_logo.jpg" alt="Armstrong"></div>
    </div>`;
}
function rpFooter(pageNum, ctx) {
  return `
    <div class="rp-footer">
      <strong>Armstrong Capital &amp; Financial Services Pvt. Ltd.</strong>
      <span>Page ${pageNum} of ${RP_TOTAL_PAGES}</span>
    </div>`;
}

// Structured "prepared by" card — sits on the right side of the cover
function rpPreparedBy(ctx) {
  if (!ctx.rm) return '';
  return `
    <div class="rp-preparedby">
      <div class="rp-pb-title">Prepared exclusively for you by</div>
      <div class="rp-pb-body">
        <div class="rp-pb-name">${rpEsc(ctx.rm.name)}</div>
        <div class="rp-pb-role">Relationship Manager · Armstrong Capital</div>
        <div class="rp-pb-contact">
          <div class="rp-pb-row"><span>Mobile No.</span><b>${rpEsc(ctx.rm.mobile)}</b></div>
          <div class="rp-pb-row"><span>Email</span><b>${rpEsc(ctx.rm.email)}</b></div>
          <div class="rp-pb-row"><span>Website</span><b>${RP_COMPANY_WEBSITE}</b></div>
        </div>
      </div>
    </div>`;
}

// ── PAGE 1 — Cover ─────────────────────────────────────────
function rpPageCover(ctx) {
  const e = ctx.etfObj;
  const oneW = e.returns ? e.returns['1W'] : null;
  const up = oneW != null && oneW >= 0;
  const eyebrow = [e.category, 'US EQUITY'].filter(Boolean).join(' · ').toUpperCase();

  return `
  <div class="pdf-page" data-rp-page="1">
    <div class="rp-cover-topbar">
      <div class="rp-header-label">US ETF Research Factsheet</div>
      <div class="rp-header-label" style="color:#6B7280;font-weight:600;">As of ${rpDateLong(ctx.mainData.as_of_date)}</div>
    </div>

    <div class="rp-cover-body">
      <div class="rp-cover-head">
        <div class="rp-cover-logo">
          <img src="armstrong_logo.jpg" alt="Armstrong">
        </div>

        <div class="rp-cover-eyebrow">Exchange-Traded Fund · Research Factsheet</div>
        <div class="rp-cover-title">ETF Profile &amp;<br>Performance Review</div>
        <div class="rp-cover-rule"></div>

        <div class="rp-cover-intro">
          This factsheet delivers an institutional-grade overview of a single exchange-traded fund (ETF)
          — spanning its investment objective, portfolio composition, historical performance across market
          cycles, risk characteristics, and key portfolio metrics. Prepared by Armstrong Capital to support
          clear, well-informed investment decisions.
        </div>
      </div>

      <div class="rp-price-card">
        <div class="rp-price-left">
          <div class="rp-price-eyebrow">${rpEsc(eyebrow)}</div>
          <div class="rp-price-ticker">${rpEsc(ctx.symbol)}</div>
          <div class="rp-price-name">${rpEsc(e.name || '')}</div>
        </div>
        <div class="rp-price-right">
          <div class="rp-price-value">${e.price != null ? '$' + e.price.toFixed(2) : '—'}</div>
          <div class="rp-price-change ${up ? 'up' : 'down'}">${oneW != null ? (up ? '▲ ' : '▼ ') + rpPct(oneW) + ' (1W)' : ''}</div>
          <div class="rp-price-asof">AS OF ${rpDateLong(ctx.mainData.as_of_date).toUpperCase()} · SETTLED CLOSE</div>
        </div>
      </div>

      ${rpPreparedBy(ctx)}
    </div>

    ${rpFooter(1, ctx)}
  </div>`;
}

// ── PAGE 2 — Fund Overview & Key Fundamentals ──────────────
function rpPageOverview(ctx) {
  const e = ctx.etfObj, meta = ctx.meta;
  const spy = ctx.mainData.spy_returns || {};
  const ret12 = e.returns ? e.returns['12M'] : null;
  const vsSpy12 = e.vs_spy ? e.vs_spy['12M'] : null;

  const badges = [e.category, e.asset_class, e.signal ? e.signal + ' Momentum' : null]
    .filter(Boolean)
    .map(b => `<span class="rp-badge">${rpEsc(b)}</span>`).join('');

  const kpi = (label, value, sub, muted) => `
    <div class="rp-kpi">
      <div class="rp-kpi-label">${label}</div>
      <div class="rp-kpi-value">${value}</div>
      <div class="rp-kpi-sub ${muted ? 'muted' : ''}">${sub}</div>
    </div>`;

  const fundRows = [
    ['Fund Name', rpEsc(e.name || '—')],
    ['Ticker / Exchange', rpEsc(ctx.symbol)],
    ['Asset Class', rpEsc(e.asset_class || '—')],
    ['Category', rpEsc(e.category || '—')],
    ['Number of Holdings', e.holdings != null ? e.holdings : '—'],
    ['P/E Ratio', e.pe != null ? e.pe.toFixed(1) + '×' : '—'],
    ['Top 10 Weight', e.top10_pct != null ? e.top10_pct.toFixed(1) + '%' : '—'],
    ['Beta vs S&P 500', e.beta != null ? e.beta.toFixed(2) : '—'],
    ['Inception Date', rpInceptionYear(e.inception)],
    ['Net Assets (AUM)', rpAum(e.aum)],
    ['Expense Ratio', e.er != null ? e.er.toFixed(2) + '%' : '—'],
    ['Dividend Yield', e.yield != null ? (e.yield * 100).toFixed(2) + '%' : '—'],
  ];
  const half = Math.ceil(fundRows.length / 2);
  const col = rows => rows.map(r => `<div class="rp-fund-row"><span class="k">${r[0]}</span><span class="v">${r[1]}</span></div>`).join('');

  return `
  <div class="pdf-page" data-rp-page="2">
    ${rpHeader(ctx)}
    <div class="rp-section-eyebrow">Section 01</div>
    <div class="rp-section-title">Fund Overview &amp; Key Fundamentals</div>

    <div class="rp-badges">${badges}</div>

    <div class="rp-kpi-row">
      ${kpi('Net Assets', rpAum(e.aum), 'Total AUM', true)}
      ${kpi('Expense Ratio', e.er != null ? e.er.toFixed(2) + '%' : '—', 'Annual fee', true)}
      ${kpi('Holdings', e.holdings != null ? e.holdings : '—', e.top10_pct != null ? 'Top 10: ' + e.top10_pct.toFixed(0) + '%' : '', true)}
      ${kpi('1-YR Return', rpPct(ret12), vsSpy12 != null ? 'vs S&P ' + rpPct(vsSpy12) : '')}
    </div>

    <div class="rp-block-label">About the Fund</div>
    <div class="rp-about">${rpEsc(meta.description || (e.name + ' (' + ctx.symbol + ') is classified under the ' + (e.category || 'general') + ' category.'))}</div>

    <div class="rp-block-label">Key Fundamentals</div>
    <div class="rp-fund-grid">
      <div>${col(fundRows.slice(0, half))}</div>
      <div>${col(fundRows.slice(half))}</div>
    </div>

    <div class="rp-callout">
      <b>How to read this factsheet.</b> All figures are drawn from ${rpEsc(ctx.symbol)}'s live profile as of
      ${rpDateLong(ctx.mainData.as_of_date)}. Multi-year returns are annualized (CAGR). Returns exclude platform
      fees and taxes. Please read the full risk analysis before investing.
    </div>

    ${rpFooter(2, ctx)}
  </div>`;
}

// ── Shared: horizontal bar row (crisp HTML, no canvas) ─────
function rpBar(label, value, pct, color, maxPct) {
  const w = Math.max(1.5, Math.min(100, (pct / (maxPct || 100)) * 100));
  return `
    <div class="rp-bar-row">
      <div class="rp-bar-label">${rpEsc(label)}</div>
      <div class="rp-bar-track"><div class="rp-bar-fill" style="width:${w.toFixed(1)}%;background:${color};"></div></div>
      <div class="rp-bar-val">${rpEsc(value)}</div>
    </div>`;
}

// ── Inline SVG line chart (vector = crisp, no canvas/timing issues) ──
function rpLineChartSVG(indexed, seriesMeta) {
  const W = 706, H = 236, padL = 40, padR = 14, padT = 12, padB = 26;
  const plotW = W - padL - padR, plotH = H - padT - padB;
  const keys = Object.keys(indexed.series);
  let min = Infinity, max = -Infinity;
  keys.forEach(k => indexed.series[k].forEach(v => { if (v != null) { if (v < min) min = v; if (v > max) max = v; } }));
  if (!isFinite(min)) { min = 90; max = 110; }
  const span = (max - min) || 1;
  min -= span * 0.08; max += span * 0.08;
  const n = indexed.dates.length;
  const xAt = i => padL + (n <= 1 ? 0 : (i / (n - 1)) * plotW);
  const yAt = v => padT + (1 - (v - min) / (max - min)) * plotH;

  // horizontal gridlines at 4 round steps
  let grid = '';
  const steps = 4;
  for (let s = 0; s <= steps; s++) {
    const val = min + (s / steps) * (max - min);
    const y = yAt(val);
    grid += `<line x1="${padL}" y1="${y.toFixed(1)}" x2="${W - padR}" y2="${y.toFixed(1)}" stroke="#EEF2F7" stroke-width="1"/>`;
    grid += `<text x="${padL - 6}" y="${(y + 3).toFixed(1)}" text-anchor="end" font-size="8" fill="#6B7280">${Math.round(val)}</text>`;
  }
  // x month labels (~7 ticks)
  let xlabels = '';
  const MON = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  const ticks = 7;
  for (let t = 0; t <= ticks; t++) {
    const i = Math.round((t / ticks) * (n - 1));
    const d = new Date(indexed.dates[i]);
    if (isNaN(d)) continue;
    xlabels += `<text x="${xAt(i).toFixed(1)}" y="${H - 8}" text-anchor="middle" font-size="8" fill="#6B7280">${MON[d.getMonth()]}</text>`;
  }
  // series polylines
  let lines = '';
  keys.forEach(k => {
    const pts = indexed.series[k].map((v, i) => v == null ? null : `${xAt(i).toFixed(1)},${yAt(v).toFixed(1)}`).filter(Boolean).join(' ');
    lines += `<polyline points="${pts}" fill="none" stroke="${seriesMeta[k].color}" stroke-width="${seriesMeta[k].w || 2}" stroke-linejoin="round"/>`;
  });

  return `<svg class="rp-linechart" viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMidYMid meet">
    ${grid}${lines}${xlabels}</svg>`;
}

// Build indexed-to-100 series over the last `days` trading days
function rpIndexedSeries(ctx, tickers, days) {
  const h = ctx.historyData;
  if (!h || !h.series || !h.dates) return null;
  const start = Math.max(0, h.dates.length - days);
  const dates = h.dates.slice(start);
  const series = {};
  tickers.forEach(t => {
    const s = h.series[t];
    if (!s) return;
    const sl = s.slice(start);
    const base = sl.find(v => v != null && v > 0);
    if (base == null) return;
    series[t] = sl.map(v => v != null ? (v / base) * 100 : null);
  });
  return Object.keys(series).length ? { dates, series } : null;
}

// ── PAGE 3 — Price Performance & Returns ───────────────────
// Distinct, palette-consistent line colors per benchmark key (PDF chart)
const RP_BENCH_COLORS = { SPY: '#C9A227', NDX: '#2E8B57', NIFTY50: '#7A5AF8', NIFTY500: '#E2622C' };

// Total return over the shown window, straight from the indexed series (end - 100)
function rpSeriesReturn(indexed, key) {
  const s = indexed && indexed.series[key];
  if (!s) return null;
  for (let i = s.length - 1; i >= 0; i--) if (s[i] != null) return s[i] - 100;
  return null;
}

function rpPagePerformance(ctx) {
  const e = ctx.etfObj;
  const spy = ctx.mainData.spy_returns || {};
  const nas = ctx.ndxReturns || {};   // analyticsData.nasdaq100_trailing_returns
  const asOf = rpDateLong(ctx.mainData.as_of_date);

  // Chart reflects whatever benchmarks are selected on the live price chart
  // (defaults to S&P 500 when nothing is selected — see ctx.compareSelection).
  const sel = (ctx.compareSelection && ctx.compareSelection.length)
    ? ctx.compareSelection
    : [{ key: 'SPY', seriesKey: 'SPY', label: 'S&P 500' }];

  const tickers = [ctx.symbol].concat(sel.map(s => s.seriesKey));
  const indexed = rpIndexedSeries(ctx, tickers, 252);

  const seriesMeta = { [ctx.symbol]: { color: '#174EA6', w: 2.4 } };
  sel.forEach(s => { seriesMeta[s.seriesKey] = { color: RP_BENCH_COLORS[s.key] || '#C9A227', w: 2 }; });

  const chart = indexed
    ? rpLineChartSVG(indexed, seriesMeta)
    : '<div class="rp-chart-missing">Price history not available.</div>';

  // Legend: ETF first, then each selected benchmark — returns read from the
  // indexed series so the legend always matches the plotted lines.
  const legend = [`<span><i style="background:#174EA6"></i>${rpEsc(ctx.symbol)} (${rpPct(rpSeriesReturn(indexed, ctx.symbol), 1)})</span>`]
    .concat(sel.map(s =>
      `<span><i style="background:${RP_BENCH_COLORS[s.key] || '#C9A227'}"></i>${rpEsc(s.label)} (${rpPct(rpSeriesReturn(indexed, s.seriesKey), 1)})</span>`
    )).join('');

  const rows = [
    ['1 Month', '1M'], ['3 Months', '3M'], ['6 Months', '6M'], ['1 Year', '12M'],
    ['3 Years (CAGR)', '3Y'], ['5 Years (CAGR)', '5Y'], ['10 Years (CAGR)', '10Y'],
  ];
  const cls = v => v == null ? '' : (v >= 0 ? 'pos' : 'neg');
  const body = rows.map(([lbl, k]) => {
    const smh = e.returns ? e.returns[k] : null;
    const sp = spy[k];
    const nq = nas[k];
    const vsSp = e.vs_spy ? e.vs_spy[k] : (smh != null && sp != null ? smh - sp : null);
    const vsNq = (smh != null && nq != null) ? smh - nq : null;
    return `<tr>
      <td class="rp-rt-period">${lbl}</td>
      <td class="rp-rt-strong">${rpPct(smh, 1)}</td>
      <td>${rpPct(sp, 1)}</td>
      <td>${rpPct(nq, 1)}</td>
      <td class="${cls(vsSp)}">${rpPct(vsSp, 1)}</td>
      <td class="${cls(vsNq)}">${rpPct(vsNq, 1)}</td>
    </tr>`;
  }).join('');

  return `
  <div class="pdf-page" data-rp-page="3">
    ${rpHeader(ctx)}
    <div class="rp-section-eyebrow">Section 02</div>
    <div class="rp-section-title">Price Performance &amp; Returns</div>

    <div class="rp-subhead"><h3>Price Performance — 1 Year</h3>
      <span class="rp-subhead-note">Total return, indexed to 100 · as of ${asOf}</span></div>
    <div class="rp-chart-wrap">${chart}</div>
    <div class="rp-legend">${legend}</div>

    <div class="rp-subhead" style="margin-top:26px;"><h3>Returns vs Benchmarks</h3>
      <span class="rp-subhead-note">As of ${asOf} · periods above 1 year annualized (CAGR)</span></div>
    <table class="rp-returns-table">
      <thead><tr>
        <th class="rp-rt-period">Period</th><th>${rpEsc(ctx.symbol)}</th>
        <th>S&amp;P 500</th><th>Nasdaq-100</th><th>vs S&amp;P 500</th><th>vs Nasdaq-100</th>
      </tr></thead>
      <tbody>${body}</tbody>
    </table>

    <div class="rp-callout">
      <b>Benchmarks.</b> Trailing returns compare ${rpEsc(ctx.symbol)} against the S&amp;P 500 (SPY) and Nasdaq-100
      (^NDX). Green figures indicate outperformance versus the benchmark over that window. All figures are computed
      from the same adjusted (total-return) NAV series shown above.
    </div>

    ${rpFooter(3, ctx)}
  </div>`;
}

// ── PAGE 4 — Portfolio Composition & Holdings ──────────────
// Keep a breakdown to the 7 largest slices and roll everything else into a
// single "Other". Past seven the bars get too thin to read on an A4 page, and
// a long tail of sub-1% rows adds length without adding information. If the
// source already has an "Other" bucket the remainder is ADDED to it rather
// than creating a second one.
const RP_MAX_SLICES = 7;
function rpTopSlices(items, labelKey) {
  const clean = (items || []).filter(x => x && x.pct != null);
  if (clean.length <= RP_MAX_SLICES) return clean.slice();

  const sorted = clean.slice().sort((a, b) => b.pct - a.pct);
  const head = [];
  let otherPct = 0;
  sorted.forEach((x, i) => {
    const isOther = String(x[labelKey] || '').trim().toLowerCase() === 'other';
    if (i < RP_MAX_SLICES && !isOther) head.push(x);
    else otherPct += x.pct;
  });
  if (otherPct > 0) {
    const row = { pct: Math.round(otherPct * 100) / 100 };
    row[labelKey] = 'Other';
    head.push(row);
  }
  return head;
}

function rpPageComposition(ctx) {
  const meta = ctx.meta, e = ctx.etfObj;
  const navy = '#0B2A78', blue = '#2E6FD6', green = '#2E8B57', grey = '#8B93A1';

  // etfdb returns 15 positions and the adapter passes all of them through, so
  // this card was rendering 15 rows under a "Top 10" heading. Sliced to 10 to
  // match its own label — and it now sits level with the 7-slice sector card
  // beside it instead of running well past it.
  const holdings = (meta.top10_holdings || []).slice(0, 10);
  const holdRows = holdings.map(h => `
    <tr><td class="rp-hold-name">${rpEsc(h.name)}</td><td class="rp-hold-tk">${rpEsc(h.ticker)}</td>
    <td class="rp-hold-wt">${h.weight != null ? h.weight.toFixed(1) + '%' : '—'}</td></tr>`).join('');

  const sectorBars = rpTopSlices(meta.sector_holdings, 'sector').map(s =>
    rpBar(s.sector, s.pct.toFixed(1) + '%', s.pct, `linear-gradient(90deg,#174EA6,#2E8B57)`, 100)).join('');
  const mcapBars = (meta.market_cap || []).map(m =>
    rpBar(m.cap, (m.pct != null ? m.pct.toFixed(1) + '%' : '—'), m.pct || 0, navy, 100)).join('');
  const countryBars = rpTopSlices(meta.country_exposure, 'country').map(c =>
    rpBar(c.country, c.pct.toFixed(1) + '%', c.pct, blue, 100)).join('');

  return `
  <div class="pdf-page" data-rp-page="4">
    ${rpHeader(ctx)}
    <div class="rp-section-eyebrow">Section 03</div>
    <div class="rp-section-title">Portfolio Composition &amp; Holdings</div>

    <div class="rp-comp-grid">
      <div class="rp-comp-card">
        <div class="rp-comp-label">Top 10 Holdings</div>
        <table class="rp-hold-table">
          <thead><tr><th>Company</th><th>Ticker</th><th class="rp-hold-wt">Weight</th></tr></thead>
          <tbody>${holdRows || '<tr><td colspan="3" class="rp-empty">Not available</td></tr>'}</tbody>
        </table>
      </div>
      <div class="rp-comp-card">
        <div class="rp-comp-label">Sector Holdings</div>
        <div class="rp-bars">${sectorBars || '<div class="rp-empty">Not available</div>'}</div>
      </div>
    </div>

    <div class="rp-comp-grid" style="margin-top:16px;">
      <div class="rp-comp-card">
        <div class="rp-comp-label">Country Exposure</div>
        <div class="rp-bars">${countryBars || '<div class="rp-empty">Not available</div>'}</div>
      </div>
      <div class="rp-comp-card">
        <div class="rp-comp-label">Market-Cap Exposure</div>
        <div class="rp-bars">${mcapBars || '<div class="rp-empty">Not available</div>'}</div>
      </div>
    </div>

    ${rpFooter(4, ctx)}
  </div>`;
}

// ── Heatmap / seasonality color helpers ───────────────────
const RP_MON = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
const RP_MON_IDX = { Jan:0, Feb:1, Mar:2, Apr:3, May:4, Jun:5, Jul:6, Aug:7, Sep:8, Oct:9, Nov:10, Dec:11 };

function rpMix(h1, h2, t) {
  const a = hexToRgbArr(h1), b = hexToRgbArr(h2);
  const r = Math.round(a[0] + (b[0] - a[0]) * t);
  const g = Math.round(a[1] + (b[1] - a[1]) * t);
  const bl = Math.round(a[2] + (b[2] - a[2]) * t);
  return `rgb(${r},${g},${bl})`;
}
function hexToRgbArr(h) {
  h = h.replace('#', '');
  return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16)];
}
function rpHeatColor(v, maxAbs) {
  if (v == null || isNaN(v)) return '#F7F9FC';
  const m = maxAbs || 12;
  const t = Math.min(1, Math.abs(v) / m);
  return v >= 0 ? rpMix('#EAF6EE', '#2E8B57', t) : rpMix('#FBEBEB', '#D9534F', t);
}
function rpHeatText(v, maxAbs) {
  const m = maxAbs || 12;
  return (v != null && Math.abs(v) >= m * 0.55) ? '#FFFFFF' : '#14213D';
}

// Month-end value per calendar month for a daily normalized series
function rpMonthEnd(ctx, key) {
  const h = ctx.historyData;
  if (!h || !h.series || !h.series[key]) return null;
  const d = h.dates, s = h.series[key];
  const me = {};
  for (let i = 0; i < d.length; i++) { if (s[i] != null) me[d[i].slice(0, 7)] = s[i]; }
  return me;
}
// {year: {monthIdx: pct}} month-over-month returns from month-end values
function rpMonthlyByYear(me) {
  if (!me) return {};
  const ks = Object.keys(me).sort();
  const by = {};
  for (let j = 1; j < ks.length; j++) {
    const [y, m] = ks[j].split('-');
    const ret = (me[ks[j]] / me[ks[j - 1]] - 1) * 100;
    (by[y] = by[y] || {})[parseInt(m, 10) - 1] = ret;
  }
  return by;
}
function rpMonthlyAvg(byYear) {
  const sum = Array(12).fill(0), cnt = Array(12).fill(0);
  Object.values(byYear).forEach(mo => { for (let m = 0; m < 12; m++) if (mo[m] != null) { sum[m] += mo[m]; cnt[m]++; } });
  return sum.map((s, m) => cnt[m] ? s / cnt[m] : null);
}
// Calendar-year returns from month-end values (last-of-year / last-of-prev-year)
function rpAnnualReturns(me) {
  if (!me) return {};
  const ks = Object.keys(me).sort();
  const yearEnd = {};
  ks.forEach(k => { yearEnd[k.split('-')[0]] = me[k]; });
  const years = Object.keys(yearEnd).sort();
  const out = {};
  for (let i = 1; i < years.length; i++) out[years[i]] = (yearEnd[years[i]] / yearEnd[years[i - 1]] - 1) * 100;
  return out;
}
// Convert SMH month-name calendar -> {year:{monthIdx:pct}}
function rpSmhByYear(cal) {
  const by = {};
  if (!cal) return by;
  Object.keys(cal).forEach(y => { by[y] = {}; Object.keys(cal[y]).forEach(mn => { by[y][RP_MON_IDX[mn]] = cal[y][mn]; }); });
  return by;
}

// ── PAGE 5 — Returns Heatmap & Seasonality ─────────────────
function rpPageSeasonality(ctx) {
  const e = ctx.etfObj;
  const spy = ctx.mainData.spy_returns || {};
  const asOf = rpDateLong(ctx.mainData.as_of_date);
  const sym = ctx.symbol;

  // ── Trailing returns heatmap ──
  const HMP = [['1W','1W'],['15D','15D'],['1M','1M'],['2M','2M'],['3M','3M'],['6M','6M'],['9M','9M'],
               ['1Y','12M'],['2Y','2Y'],['3Y','3Y'],['5Y','5Y'],['7Y','7Y'],['10Y','10Y']];
  const hmCell = v => `<td style="background:${rpHeatColor(v, 30)};color:${rpHeatText(v, 30)}">${rpPct(v, 1)}</td>`;
  const hmHead = '<th></th>' + HMP.map(p => `<th>${p[0]}</th>`).join('');
  const hmRow = (label, get) => `<tr><td class="rp-hm-lbl">${label}</td>${HMP.map(p => hmCell(get(p[1]))).join('')}</tr>`;
  const heatmap = `<table class="rp-heatmap"><thead><tr>${hmHead}</tr></thead><tbody>
    ${hmRow(sym, k => e.returns ? e.returns[k] : null)}
    ${hmRow('S&P 500', k => spy[k])}
    ${hmRow('Excess', k => e.vs_spy ? e.vs_spy[k] : null)}
  </tbody></table>`;

  // ── Seasonality: SMH year rows + S&P avg + SMH avg ──
  const cal = ctx.analytics ? ctx.analytics.monthly_returns_calendar : null;
  const totals = ctx.analytics ? ctx.analytics.monthly_returns_annual_total : null;
  const smhBy = rpSmhByYear(cal);
  const years = Object.keys(smhBy).map(Number).sort((a, b) => b - a).slice(0, 7); // most recent 7
  const spyBy = rpMonthlyByYear(rpMonthEnd(ctx, 'SPY'));
  // Averages computed over the SAME years shown in the table
  const pick = (obj) => { const o = {}; years.forEach(y => { if (obj[String(y)]) o[String(y)] = obj[String(y)]; }); return o; };
  const spyAvg = rpMonthlyAvg(pick(spyBy));
  const smhAvg = rpMonthlyAvg(pick(smhBy));

  const seaCell = v => `<td style="background:${rpHeatColor(v, 12)};color:${rpHeatText(v, 12)}">${v == null ? '—' : rpPct(v, 1)}</td>`;
  const fyCell = v => `<td class="rp-sea-fy" style="color:${v == null ? '#6B7280' : (v >= 0 ? '#2E8B57' : '#D9534F')}">${v == null ? '—' : rpPct(v, 1)}</td>`;
  const seaHead = '<th></th>' + RP_MON.map(m => `<th>${m}</th>`).join('') + '<th>FY</th>';
  const yearRows = years.map(y => {
    const mo = smhBy[y] || {};
    const cells = RP_MON.map((_, m) => seaCell(mo[m])).join('');
    return `<tr><td class="rp-sea-yr">${y}</td>${cells}${fyCell(totals ? totals[String(y)] : null)}</tr>`;
  }).join('');
  // FY for avg rows = mean of annual returns over the shown years
  const spyAnnual = rpAnnualReturns(rpMonthEnd(ctx, 'SPY'));
  const smhFyAvg = totals ? avgOf(years.map(y => totals[String(y)])) : null;
  const spyFyAvg = avgOf(years.map(y => spyAnnual[String(y)]));
  const avgRow = (label, arr, fy) =>
    `<tr class="rp-sea-avgrow"><td class="rp-sea-yr">${label}</td>${arr.map(seaCell).join('')}${fyCell(fy)}</tr>`;

  const seasonality = `<table class="rp-seasonality"><thead><tr>${seaHead}</tr></thead><tbody>
    ${yearRows}
    <tr class="rp-sea-gap"><td colspan="14"></td></tr>
    ${avgRow('S&P', spyAvg, spyFyAvg)}
    ${avgRow(sym + ' Avg', smhAvg, smhFyAvg)}
  </tbody></table>`;

  // ── Best & Worst calendar years ──
  const bwYears = years.slice(0, 6); // most recent 6
  const now = new Date();
  const curYear = now.getFullYear();
  const bwRows = bwYears.map(y => {
    const smhR = totals ? totals[String(y)] : null;
    const spyR = spyAnnual[String(y)];
    const ex = (smhR != null && spyR != null) ? smhR - spyR : null;
    const label = (y === curYear) ? `${y} (YTD)` : String(y);
    return { y, label, smhR, spyR, ex };
  });
  const bwTableRows = bwRows.map(r => `<tr>
    <td class="rp-bw-yr">${r.label}</td>
    <td class="rp-bw-smh ${r.smhR >= 0 ? 'pos' : 'neg'}">${rpPct(r.smhR, 1)}</td>
    <td>${rpPct(r.spyR, 1)}</td>
    <td class="${r.ex >= 0 ? 'pos' : 'neg'}">${rpPct(r.ex, 1)}</td>
  </tr>`).join('');

  // gain/loss bars centered at 0
  const maxAbs = Math.max(10, ...bwRows.map(r => Math.abs(r.smhR || 0)));
  const bwBars = bwRows.map(r => {
    const v = r.smhR || 0;
    const half = 50; // percent of track for each side
    const w = Math.min(half, (Math.abs(v) / maxAbs) * half);
    const pos = v >= 0;
    return `<div class="rp-bw-barrow">
      <div class="rp-bw-barlabel">${r.label}</div>
      <div class="rp-bw-bartrack">
        <div class="rp-bw-barmid"></div>
        <div class="rp-bw-bar ${pos ? 'pos' : 'neg'}" style="left:${pos ? half : half - w}%;width:${w}%;"></div>
      </div>
      <div class="rp-bw-barval ${pos ? 'pos' : 'neg'}">${rpPct(v, 1)}</div>
    </div>`;
  }).join('');

  // dynamic insight cards
  const posCount = bwRows.filter(r => r.smhR != null && r.smhR >= 0).length;
  const worst = bwRows.reduce((a, b) => (b.smhR != null && (a == null || b.smhR < a.smhR) ? b : a), null);
  const best = bwRows.reduce((a, b) => (b.smhR != null && (a == null || b.smhR > a.smhR) ? b : a), null);
  const bestMonthIdx = smhAvg.reduce((bi, v, i) => (v != null && (smhAvg[bi] == null || v > smhAvg[bi]) ? i : bi), 0);
  const worstMonthIdx = smhAvg.reduce((wi, v, i) => (v != null && (smhAvg[wi] == null || v < smhAvg[wi]) ? i : wi), 0);

  const insights = `
    <div class="rp-insight"><b>Consistency.</b> ${sym} finished positive in ${posCount} of the last ${bwRows.length} periods shown${worst && worst.smhR < 0 ? `, with ${worst.y} the weakest (${rpPct(worst.smhR, 1)})` : ''}.</div>
    <div class="rp-insight"><b>Seasonal edge.</b> ${RP_MON[bestMonthIdx]} has historically been the strongest month on average; ${RP_MON[worstMonthIdx]} the weakest.</div>
    <div class="rp-insight"><b>Amplitude.</b> Annual outcomes are wide${best && worst ? ` — from ${rpPct(best.smhR, 1)} (${best.y}) to ${rpPct(worst.smhR, 1)} (${worst.y})` : ''} — underscoring the fund's cyclical character.</div>`;

  return `
  <div class="pdf-page" data-rp-page="5">
    ${rpHeader(ctx)}
    <div class="rp-section-eyebrow">Section 04</div>
    <div class="rp-section-title">Returns Heatmap &amp; Seasonality</div>

    <div class="rp-subhead"><h3>Trailing Returns Heatmap</h3>
      <span class="rp-subhead-note">${sym} vs S&amp;P 500 · as of ${asOf}</span></div>
    ${heatmap}

    <div class="rp-subhead" style="margin-top:22px;"><h3>Seasonality — Monthly Returns by Year</h3>
      <span class="rp-subhead-note">Calendar-month total returns</span></div>
    ${seasonality}
    <div class="rp-fine">Avg = mean monthly return across the years shown. Current year is year-to-date.</div>

    <div class="rp-subhead" style="margin-top:22px;"><h3>Best &amp; Worst Calendar Years</h3>
      <span class="rp-subhead-note">${sym} vs S&amp;P 500</span></div>
    <div class="rp-bw-grid">
      <table class="rp-bw-table">
        <thead><tr><th class="rp-bw-yr">Year</th><th>${sym}</th><th>S&amp;P 500</th><th>Excess vs S&amp;P</th></tr></thead>
        <tbody>${bwTableRows}</tbody>
      </table>
      <div class="rp-bw-chartcard">
        <div class="rp-comp-label">${sym} Annual Return — Gain / Loss</div>
        <div class="rp-bw-bars">${bwBars}</div>
        <div class="rp-bw-barnote">Bars centred at 0% · green = gain, red = loss</div>
      </div>
    </div>
    <div class="rp-insight-row">${insights}</div>

    ${rpFooter(5, ctx)}
  </div>`;
}

function avgOf(arr) {
  const v = arr.filter(x => x != null && !isNaN(x));
  return v.length ? v.reduce((a, b) => a + b, 0) / v.length : null;
}

// ── PAGE 6 — Momentum & Risk Analysis ──────────────────────
// Point on a circle. ang in degrees: 0 = right, 90 = up, 180 = left.
function rpPolar(cx, cy, r, ang) {
  const a = ang * Math.PI / 180;
  return [cx + r * Math.cos(a), cy - r * Math.sin(a)];
}
// Semicircle momentum gauge (red → amber → green), needle set by score.
// Needle mirrors the live page: score -30 → far left, +30 → far right.
function rpGaugeSVG(score, signal) {
  const cx = 130, cy = 128, r = 104, sw = 20;
  const arc = (a1, a2, col) => {
    const [x1, y1] = rpPolar(cx, cy, r, a1);
    const [x2, y2] = rpPolar(cx, cy, r, a2);
    return `<path d="M ${x1.toFixed(1)} ${y1.toFixed(1)} A ${r} ${r} 0 0 1 ${x2.toFixed(1)} ${y2.toFixed(1)}" fill="none" stroke="${col}" stroke-width="${sw}" stroke-linecap="butt"/>`;
  };
  const deg = Math.max(-30, Math.min(30, score)) / 30 * 90;   // -90..+90
  const needleAng = 90 - deg;                                  // 90=up, 0=right, 180=left
  const [nx, ny] = rpPolar(cx, cy, r - 14, needleAng);
  return `
    <svg viewBox="0 0 260 150" class="rp-gauge-svg">
      ${arc(180, 120, '#D9534F')}
      ${arc(120, 60,  '#E0A800')}
      ${arc(60, 0,    '#2E8B57')}
      <line x1="${cx}" y1="${cy}" x2="${nx.toFixed(1)}" y2="${ny.toFixed(1)}" stroke="#14213D" stroke-width="4" stroke-linecap="round"/>
      <circle cx="${cx}" cy="${cy}" r="8" fill="#0B2A78"/>
      <text x="${cx}" y="${cy - 30}" text-anchor="middle" class="rp-gauge-num">${score != null ? score.toFixed(1) : '—'}</text>
    </svg>`;
}
// Underwater drawdown area (values are % <= 0), rendered as a red-filled SVG.
function rpDrawdownSVG(values) {
  const W = 706, H = 156, padL = 8, padR = 8, padT = 10, padB = 18;
  const vals = values.filter(v => v != null && !isNaN(v));
  if (vals.length < 2) return '<div class="rp-empty">Drawdown data not available</div>';
  const minV = Math.min(...vals);                 // most negative
  const n = vals.length;
  const xOf = i => padL + (i / (n - 1)) * (W - padL - padR);
  const yOf = v => padT + (minV === 0 ? 0 : (0 - v) / (0 - minV)) * (H - padT - padB);
  let line = '';
  for (let i = 0; i < n; i++) line += (i ? 'L' : 'M') + xOf(i).toFixed(1) + ' ' + yOf(vals[i]).toFixed(1) + ' ';
  const area = `M ${padL} ${padT} ` + line.replace(/^M/, 'L') + `L ${(W - padR).toFixed(1)} ${padT} Z`;
  const yZero = padT;
  const yMin = H - padB;
  return `
    <svg viewBox="0 0 ${W} ${H}" class="rp-dd-svg" preserveAspectRatio="none">
      <line x1="${padL}" y1="${yZero}" x2="${W - padR}" y2="${yZero}" stroke="#E5EAF2" stroke-width="1"/>
      <path d="${area}" fill="rgba(217,83,79,0.16)"/>
      <path d="${line}" fill="none" stroke="#D9534F" stroke-width="1.6"/>
      <text x="${padL + 2}" y="${yZero - 3}" class="rp-dd-axis">0%</text>
      <text x="${padL + 2}" y="${yMin + 13}" class="rp-dd-axis">${minV.toFixed(0)}%</text>
    </svg>`;
}

function rpPageMomentumRisk(ctx) {
  const e = ctx.etfObj;
  const sym = ctx.symbol;
  const risk = ctx.analytics ? ctx.analytics.risk_analysis : null;
  const benchLabel = (ctx.analytics && (ctx.analytics.benchmark_label || ctx.analytics.benchmark_symbol)) || 'S&P 500';

  // Momentum score breakdown (identical weights/formula to the live page)
  const rets = e.returns || {};
  const weights = { '1M': 0.20, '3M': 0.30, '6M': 0.30, '12M': 0.20 };
  const periods = ['1M', '3M', '6M', '12M'];
  let cumulative = 0;
  const momRows = periods.map(p => {
    const ret = rets[p] != null ? rets[p] : 0;
    const w = weights[p];
    const contrib = ret * w;
    cumulative += contrib;
    const cCol = contrib >= 0 ? '#2E8B57' : '#D9534F';
    return `<tr>
      <td class="rp-mom-p">${p} Return</td>
      <td>${rpPct(ret, 2)}</td>
      <td>${(w * 100).toFixed(0)}%</td>
      <td style="color:${cCol};font-weight:700">${contrib >= 0 ? '+' : ''}${contrib.toFixed(2)}</td>
    </tr>`;
  }).join('');

  const sigCls = /strong/i.test(e.signal || '') ? 'strong' : /weak/i.test(e.signal || '') ? 'weak' : 'neutral';

  // Drawdown series — IDENTICAL to the live one-pager: last ~756 trading days
  // (~3Y) of daily close, decline from the running peak.
  const fullPx = ctx.historyData && ctx.historyData.series ? ctx.historyData.series[sym] : null;
  let ddVals = [];
  if (fullPx && fullPx.length) {
    const startIdx = Math.max(0, fullPx.length - 756);
    const px = fullPx.slice(startIdx);
    let peak = -Infinity;
    ddVals = px.map(v => {
      if (v == null || isNaN(v)) return null;
      peak = Math.max(peak, v);
      return peak > 0 ? (v / peak - 1) * 100 : 0;
    });
  }

  // Risk cards
  const rCard = (label, val, sub, cls) =>
    `<div class="rp-risk-card"><div class="rp-risk-lbl">${label}</div>
       <div class="rp-risk-val ${cls || ''}">${val}</div>
       <div class="rp-risk-sub">${sub}</div></div>`;
  let riskCards = '';
  if (risk) {
    const num = (v, dp, suf) => v != null ? v.toFixed(dp == null ? 2 : dp) + (suf || '') : '—';
    riskCards = [
      rCard('Volatility (Ann.)', num(risk.std_dev_annual_pct, 1, '%'), `${risk.window_months}-mo std deviation`, ''),
      rCard('Sharpe Ratio', num(risk.sharpe_ratio), 'Return per unit of risk', risk.sharpe_ratio >= 1 ? 'pos' : ''),
      rCard('Sortino Ratio', num(risk.sortino_ratio), 'Downside-risk adjusted', risk.sortino_ratio >= 1 ? 'pos' : ''),
      rCard('Beta', num(risk.beta), `Sensitivity vs ${benchLabel}`, ''),
      rCard('Alpha (Ann.)', risk.alpha_annual_pct != null ? rpPct(risk.alpha_annual_pct, 1) : '—', `Excess vs ${benchLabel}`, risk.alpha_annual_pct >= 0 ? 'pos' : 'neg'),
      rCard('Max Drawdown', num(risk.max_drawdown_pct, 1, '%'), `Trough ${rpDateLong(risk.max_drawdown_trough_date)}`, 'neg'),
      rCard('Upside Capture', num(risk.upside_capture_pct, 1, '%'), `vs ${benchLabel} up-moves`, risk.upside_capture_pct >= 100 ? 'pos' : ''),
      rCard('Downside Capture', num(risk.downside_capture_pct, 1, '%'), `vs ${benchLabel} down-moves`, risk.downside_capture_pct <= 100 ? 'pos' : 'neg'),
    ].join('');
  } else {
    riskCards = '<div class="rp-empty">Risk analytics not available for this fund.</div>';
  }

  return `
  <div class="pdf-page" data-rp-page="6">
    ${rpHeader(ctx)}
    <div class="rp-section-eyebrow">Section 05</div>
    <div class="rp-section-title">Momentum &amp; Risk Analysis</div>

    <div class="rp-mr-grid">
      <div class="rp-mr-card">
        <div class="rp-comp-label">Momentum Signal</div>
        ${rpGaugeSVG(e.momentum_score, e.signal)}
        <div class="rp-sig-box ${sigCls}">Signal: <b>${rpEsc(e.signal || '—')}</b></div>
      </div>
      <div class="rp-mr-card">
        <div class="rp-comp-label">Composite Score Breakdown</div>
        <table class="rp-mom-table">
          <thead><tr><th>Period</th><th>Return</th><th>Weight</th><th>Contribution</th></tr></thead>
          <tbody>${momRows}</tbody>
          <tfoot><tr>
            <td class="rp-mom-p">Composite Score</td><td>—</td><td>100%</td>
            <td style="color:${cumulative >= 0 ? '#2E8B57' : '#D9534F'};font-weight:800">${cumulative.toFixed(2)}</td>
          </tr></tfoot>
        </table>
        <div class="rp-fine">Weighted blend of trailing returns (1M 20% · 3M 30% · 6M 30% · 12M 20%).</div>
      </div>
    </div>

    <div class="rp-subhead" style="margin-top:18px;"><h3>Drawdown History</h3>
      <span class="rp-subhead-note">Decline from prior peak · daily${risk && risk.max_drawdown_pct != null ? ` · deepest ${rpPct(risk.max_drawdown_pct, 1)}` : ''}</span></div>
    <div class="rp-dd-card">${rpDrawdownSVG(ddVals)}</div>

    <div class="rp-subhead" style="margin-top:18px;"><h3>Risk Analysis</h3>
      <span class="rp-subhead-note">${risk ? `${risk.window_months}-mo window vs ${benchLabel} · rf ${risk.risk_free_rate_annual_pct}%` : ''}</span></div>
    <div class="rp-risk-grid">${riskCards}</div>

    <div class="rp-fine">Risk metrics are computed from historical returns and are not a forecast. Past performance does not guarantee future results.</div>

    ${rpFooter(6, ctx)}
  </div>`;
}

// ── PAGE 7 — Thank You / back cover ────────────────────────
function rpPageThankYou(ctx) {
  const rm = ctx.rm || {};
  const contact = `
    <div class="rp-ty-contact">
      <div class="rp-ty-crow"><span>Prepared by</span><b>${rpEsc(rm.name || '—')}</b></div>
      <div class="rp-ty-crow"><span>Mobile No.</span><b>${rpEsc(rm.mobile || '—')}</b></div>
      <div class="rp-ty-crow"><span>Email</span><b>${rpEsc(rm.email || '—')}</b></div>
      <div class="rp-ty-crow"><span>Website</span><b>${RP_COMPANY_WEBSITE}</b></div>
    </div>`;
  return `
  <div class="pdf-page rp-ty-page" data-rp-page="7">
    <div class="rp-ty-inner">
      <div class="rp-ty-logo"><img src="armstrong_logo.jpg" alt="Armstrong"></div>
      <div class="rp-ty-title">Thank You</div>
      <div class="rp-ty-rule"></div>
      <div class="rp-ty-sub">Thank you for your trust and confidence. We would be pleased to assist you
        with any questions regarding the ETF information. Please contact us for further assistance.</div>

      <div class="rp-ty-eyebrow">Relationship Manager</div>
      ${contact}

      <div class="rp-ty-company">
        <div class="rp-ty-cname">Armstrong Capital &amp; Financial Services Pvt. Ltd.</div>
      </div>
    </div>
    <div class="rp-ty-disclaimer">
      <div class="rp-ty-disc-title">Disclaimer</div>
      <p>This ETF Document has been prepared by Armstrong Capital &amp; Financial Services Pvt. Ltd. for
      informational and educational purposes only. It does not constitute investment advice, an offer, or a
      recommendation to buy, sell, or hold any security. While the information contained herein is derived from
      sources believed to be reliable, Armstrong Capital makes no representation or warranty as to its accuracy,
      completeness, or timeliness. Investments in Exchange-Traded Funds (ETFs) are subject to market risks,
      including the potential loss of principal, and past performance is not indicative of future results.
      Investors should carefully consider their investment objectives, financial circumstances, risk tolerance,
      and suitability before making any investment decision. Investments in international ETFs are also subject
      to currency fluctuations, geopolitical developments, and other risks associated with global markets.</p>
      <div class="rp-ty-disc-foot">&copy; ${new Date().getFullYear()} Armstrong Capital &amp; Financial Services Pvt. Ltd. · All rights reserved.</div>
    </div>
  </div>`;
}

// ── Render engine: build HTML pages -> capture each -> assemble PDF ──

// Raster scale for every report page. 794 CSS px wide at this scale, placed on
// an 8.27in A4 page, gives 794*RP_SCALE/8.27 DPI:
//   3 -> ~288 dpi (print)      4 -> ~384 dpi
// One constant so single-ETF and multi-ETF PDFs can never drift apart.
//
// MEASURED: 4x costs ~9s per page — 102s for an 11-page multi-ETF report, and
// over 5 minutes for a full 32-page one. 3x lands at ~288 dpi, which is already
// true print resolution for text at these sizes, and keeps a build responsive.
// The quality win that actually mattered was waiting for the webfonts
// (rpFontsReady) — before that, pages rasterised in a fallback face.
const RP_SCALE = 3;

// html2canvas paints whatever font is resolved AT THAT MOMENT. If Inter and
// JetBrains Mono have not finished loading it silently falls back to a generic
// sans — which is the single biggest cause of a report that looks soft or
// "off" despite a high raster scale. Waiting for the font set fixes that.
async function rpFontsReady() {
  try {
    if (document.fonts && document.fonts.ready) {
      await document.fonts.ready;
      // nudge both faces so a lazily-activated face is definitely resolved
      await Promise.all([
        document.fonts.load('700 14px Inter'),
        document.fonts.load('400 12px "JetBrains Mono"'),
      ]).catch(() => {});
    }
  } catch (e) { /* older browsers: fall through, nothing lost */ }
}

// Shared html2canvas options, so both PDFs rasterise identically.
function rpCanvasOpts() {
  return {
    scale: RP_SCALE,
    useCORS: true,
    backgroundColor: '#FFFFFF',
    width: 794,
    height: 1123,
    windowWidth: 794,
    windowHeight: 1123,
    logging: false,
    imageTimeout: 0,
  };
}

async function generateEtfPdf(ctx) {
  const { jsPDF } = window.jspdf;
  const root = document.getElementById('pdfReportRoot');

  // Full 7-page factsheet.
  const pagesHtml = [
    rpPageCover(ctx),
    rpPageOverview(ctx),
    rpPagePerformance(ctx),
    rpPageComposition(ctx),
    rpPageSeasonality(ctx),
    rpPageMomentumRisk(ctx),
    rpPageThankYou(ctx),
  ].join('');
  root.innerHTML = pagesHtml;

  // Wait for the logo image(s) AND the webfonts before capturing anything.
  await Promise.all(Array.from(root.querySelectorAll('img')).map(img =>
    img.complete ? Promise.resolve() : new Promise(res => { img.onload = img.onerror = res; })
  ));
  await rpFontsReady();

  const doc = new jsPDF({ unit: 'pt', format: 'a4', compress: true });
  const PAGE_W = 595.28, PAGE_H = 841.89;
  const pageEls = root.querySelectorAll('.pdf-page');

  for (let i = 0; i < pageEls.length; i++) {
    const canvas = await html2canvas(pageEls[i], rpCanvasOpts());
    // PNG (lossless) — no JPEG softening of text edges. jsPDF stores it
    // FlateDecode so quality is preserved.
    const img = canvas.toDataURL('image/png');
    if (i > 0) doc.addPage();
    doc.addImage(img, 'PNG', 0, 0, PAGE_W, PAGE_H, undefined, 'FAST');
  }

  root.innerHTML = ''; // free the DOM/memory

  // Silent download straight to the Downloads folder (no new tab / preview).
  const blob = doc.output('blob');
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `${ctx.symbol}_ETF_Profile_Armstrong_Capital.pdf`;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  setTimeout(() => URL.revokeObjectURL(url), 4000);
}
