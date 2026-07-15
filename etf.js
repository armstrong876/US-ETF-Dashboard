/* ═══════════════════════════════════════════════════════════
   Armstrong Capital — ETF Momentum Dashboard
   etf.js  |  Interactive logic for ETF detailed profile page
═══════════════════════════════════════════════════════════ */

'use strict';

// ── State variables ──
let symbol = '';
let mainData = null;
let historyData = null;
let detailDb = null;
let analyticsData = null;
let etfObj = null;

let priceChart = null;
let sectorChart = null;
let countryChart = null;
let mcapBarChart = null;
let captureChart = null;
let drawdownChart = null;

let chartTimeframe = '1Y'; // default
// Multi-select index comparison — any combination can be active at once.
const compareBenchmarks = new Set();
const BENCHMARK_SERIES_KEY = { 'SPY': 'SPY', 'NDX': '^NDX', 'NIFTY50': '^NSEI', 'NIFTY500': '^CRSLDX' };
const BENCHMARK_LABEL = { 'SPY': 'S&P 500', 'NDX': 'Nasdaq-100', 'NIFTY50': 'Nifty 50', 'NIFTY500': 'Nifty 500' };
const BENCHMARK_COLOR = { 'SPY': '#ef4444', 'NDX': '#f59e0b', 'NIFTY50': '#8b5cf6', 'NIFTY500': '#14b8a6' };
const BENCHMARK_ORDER = ['SPY', 'NDX', 'NIFTY50', 'NIFTY500'];

// Periods definitions
const ALL_PERIODS = ['1W', '15D', '1M', '2M', '3M', '6M', '9M', '12M', '2Y', '3Y', '5Y', '7Y', '10Y'];
const MONTH_ABBR = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];

// Theme definitions (fallback, by asset class — unchanged, still used by every
// ETF outside the SYMBOL_THEMES override below)
const ASSET_THEMES = {
  'Equity': { accent: '#6366f1', glow: 'rgba(99, 102, 241, 0.15)' },
  'Commodity': { accent: '#f59e0b', glow: 'rgba(245, 158, 11, 0.15)' },
  'Bond': { accent: '#14b8a6', glow: 'rgba(20, 184, 166, 0.15)' },
  'Fixed Income': { accent: '#14b8a6', glow: 'rgba(20, 184, 166, 0.15)' },
  'Currency': { accent: '#10b981', glow: 'rgba(16, 185, 129, 0.15)' },
  'Default': { accent: '#8b5cf6', glow: 'rgba(139, 92, 246, 0.15)' }
};

// Per-symbol professional accent overrides (currently scoped to QQQ & SMH —
// extend this map as more ETFs get their own detail-page treatment)
const SYMBOL_THEMES = {
  'QQQ': { accent: '#3b82f6', glow: 'rgba(59, 130, 246, 0.16)' },   // professional blue
  'SMH': { accent: '#f59e0b', glow: 'rgba(245, 158, 11, 0.16)' },   // professional amber/gold
};

// Bootstrap
document.addEventListener('DOMContentLoaded', async () => {
  initTheme();
  parseQueryString();
  await loadAllData();
  attachMaintenanceShortcut();
});

// Monthly composition/holdings refresh — deliberately has no visible control
// anywhere in the UI. Fires only on this exact key combination.
function attachMaintenanceShortcut() {
  document.addEventListener('keydown', (ev) => {
    if (ev.ctrlKey && ev.shiftKey && !ev.altKey && ev.code === 'KeyA') {
      ev.preventDefault();
      runCompositionRefresh();
    }
  });
}

async function runCompositionRefresh() {
  if (!confirm('Refresh ETF composition & holdings data now (QQQ/SMH)? This calls Yahoo Finance and may take a minute.')) return;
  try {
    const res = await fetch('/api/refresh-etf-details', { method: 'POST' });
    const data = await res.json();
    alert(data.message || (res.ok ? 'Refresh complete.' : 'Refresh failed.'));
    if (res.ok) window.location.reload();
  } catch (err) {
    alert('Refresh failed: ' + err.message);
  }
}

// Parse symbol query parameter
function parseQueryString() {
  const params = new URLSearchParams(window.location.search);
  symbol = (params.get('symbol') || '').toUpperCase().trim();
}

// Set up UI theme
function initTheme() {
  const isLight = localStorage.getItem('theme') === 'light';
  if (isLight) {
    document.body.classList.add('light-theme');
    const toggleBtn = document.getElementById('themeToggleBtn');
    if (toggleBtn) toggleBtn.textContent = '🌙 Dark Mode';
  }
}

// Toggle light/dark theme
function toggleEtfTheme() {
  const isLight = document.body.classList.toggle('light-theme');
  localStorage.setItem('theme', isLight ? 'light' : 'dark');
  const toggleBtn = document.getElementById('themeToggleBtn');
  if (toggleBtn) toggleBtn.textContent = isLight ? '🌙 Dark Mode' : '☀️ Light Mode';
  
  // Re-draw all charts to update gridlines and fonts colors
  renderPriceChart();
  renderCompositionCharts();
  renderRiskCharts();
}

// Fetch all required data sources
async function loadAllData() {
  showOverlay(true);
  try {
    // 1. Fetch dashboard.json
    let res = await fetch('dashboard.json?nocache=' + Date.now());
    if (!res.ok) throw new Error('Failed to load dashboard.json');
    mainData = await res.json();

    // 2. Fetch history.json
    res = await fetch('history.json?nocache=' + Date.now());
    if (!res.ok) throw new Error('Failed to load history.json');
    historyData = await res.json();

    // 3. Fetch etf_detail_data.json
    res = await fetch('etf_detail_data.json?nocache=' + Date.now());
    if (res.ok) {
      detailDb = await res.json();
    } else {
      console.warn('etf_detail_data.json not found, using fallbacks');
      detailDb = {};
    }

    // 4. Fetch etf_analytics.json (Monthly Returns + Risk Analysis + real NDX returns)
    res = await fetch('etf_analytics.json?nocache=' + Date.now());
    if (res.ok) {
      analyticsData = await res.json();
    } else {
      console.warn('etf_analytics.json not found, using fallbacks');
      analyticsData = {};
    }

    findAndProcessEtf();
  } catch (err) {
    console.error(err);
    showOverlay(false);
    showError('Failed to load dashboard data resources. Please check connection and try again.');
  }
}

function showOverlay(visible) {
  const overlay = document.getElementById('etfLoadingOverlay');
  if (overlay) {
    overlay.style.display = visible ? 'flex' : 'none';
  }
}

function showError(msg) {
  const errOverlay = document.getElementById('etfErrorOverlay');
  const errMsg = document.getElementById('etfErrorMsg');
  if (errOverlay && errMsg) {
    errMsg.textContent = msg;
    errOverlay.style.display = 'flex';
  }
}

// Locate ETF in dashboard universe and configure page theme
function findAndProcessEtf() {
  if (!symbol) {
    showOverlay(false);
    showError('No ETF ticker specified. Please return to the dashboard.');
    return;
  }

  // Find ETF object in dashboard.json
  const list = mainData.etfs || [];
  etfObj = list.find(e => e.symbol === symbol);

  if (!etfObj) {
    showOverlay(false);
    showError(`ETF '${symbol}' is not part of the active 80 ETF momentum universe.`);
    return;
  }

  document.getElementById('etfLoadingSymbol').textContent = `Configuring ${symbol} profile…`;

  // Apply Accent Color System — per-symbol override first, then asset-class fallback
  const theme = SYMBOL_THEMES[etfObj.symbol] || ASSET_THEMES[etfObj.asset_class] || ASSET_THEMES['Default'];
  document.documentElement.style.setProperty('--etf-accent', theme.accent);
  document.documentElement.style.setProperty('--etf-accent-glow', theme.glow);

  // Set Title tab
  document.title = `${etfObj.symbol} Profile | Armstrong Capital`;

  // "As of" date in the top nav — same source as the main dashboard (dashboard.json)
  const navAsOf = document.getElementById('navAsOf');
  if (navAsOf) navAsOf.textContent = 'As of: ' + (mainData.as_of_date || '—');

  // Populate structural contents
  populateHero();
  populateFundamentals();
  populateReturnsTable();
  populateHeatmapTable();
  populateComposition();
  populateTop10Holdings();
  populateMomentumSection();
  populateMonthlyReturns();
  populateRiskAnalysis();

  // Draw Charts
  renderPriceChart();

  // Reveal UI panels
  showOverlay(false);
  document.getElementById('etfHero').style.display = 'block';
  document.getElementById('etfMain').style.display = 'flex';
}

// Populate Hero segment
function populateHero() {
  document.getElementById('etfTicker').textContent = etfObj.symbol;
  document.getElementById('etfFullName').textContent = etfObj.name;
  
  // Asset class badge
  const asset = document.getElementById('etfAssetBadge');
  asset.textContent = etfObj.asset_class || 'N/A';
  
  // Category badge
  const cat = document.getElementById('etfCatBadge');
  cat.textContent = etfObj.category || 'N/A';

  // Description text
  const desc = document.getElementById('etfDescription');
  const meta = detailDb[symbol];
  desc.textContent = meta && meta.description 
    ? meta.description 
    : `${etfObj.name} (${etfObj.symbol}) is a professional investment fund classified under the ${etfObj.category || 'general'} sector. It tracks momentum signals and fundamental valuation markers to maintain optimal risk-adjusted returns relative to benchmark targets.`;

  // Signal Pill
  const signalPill = document.getElementById('etfSignalPill');
  signalPill.className = `etf-signal-pill ${etfObj.signal.toLowerCase()}`;
  signalPill.textContent = `${getSignalEmoji(etfObj.signal)} ${etfObj.signal}`;

  // Key stats strip — deliberately NOT a repeat of the Key Fundamentals section
  // below (AUM/ER/Yield/Beta/PE/Holdings/Inception all live there). Only
  // things unique to a hero glance: live price + short-term momentum.
  const strip = document.getElementById('etfKeyMetrics');
  const ret1w = etfObj.returns ? etfObj.returns['1W'] : null;
  const ret1m = etfObj.returns ? etfObj.returns['1M'] : null;
  const metrics = [
    { label: 'Latest Price', val: `$${etfObj.price ? etfObj.price.toFixed(2) : '—'}`, cls: '' },
    { label: '1W Return', val: ret1w != null ? `${ret1w >= 0 ? '+' : ''}${ret1w.toFixed(2)}%` : '—', cls: ret1w >= 0 ? 'green' : 'red' },
    { label: '1M Return', val: ret1m != null ? `${ret1m >= 0 ? '+' : ''}${ret1m.toFixed(2)}%` : '—', cls: ret1m >= 0 ? 'green' : 'red' },
  ];

  strip.innerHTML = metrics.map(m => `
    <div class="etf-metric-item">
      <span class="etf-metric-val ${m.cls}">${m.val}</span>
      <span class="etf-metric-lbl">${m.label}</span>
    </div>
  `).join('');
}

// Populate Fundamentals grid section
function populateFundamentals() {
  const grid = document.getElementById('fundamentalsGrid');
  const meta = detailDb[symbol];

  const cards = [
    { label: 'Total Assets (AUM)', val: formatAUM(etfObj.aum), desc: 'Total market capitalization value of asset base under management.', icon: '🏦' },
    { label: 'Expense Ratio', val: etfObj.er != null ? `${etfObj.er.toFixed(2)}%` : '—', desc: 'Annual operational fee charged to fund shareholders.', icon: '💸' },
    { label: 'Valuation P/E Ratio', val: etfObj.pe != null ? etfObj.pe.toFixed(2) : '—', desc: 'Weighted price-to-earnings metric of underlying assets.', icon: '📊' },
    { label: 'Portfolio Beta', val: etfObj.beta != null ? etfObj.beta.toFixed(2) : '—', desc: 'Systemic risk factor showing sensitivity relative to S&P 500.', icon: '⚖️' },
    { label: 'Dividend Yield', val: etfObj.yield != null ? `${(etfObj.yield * 100).toFixed(2)}%` : '—', desc: 'Trailing twelve months yield paid out as distributions.', icon: '💰' },
    { label: 'Total Stock Holdings', val: etfObj.holdings || '—', desc: 'Count of unique asset components held inside the ETF container.', icon: '📂' },
    { label: 'Top 10 Concentration', val: etfObj.top10_pct != null ? `${etfObj.top10_pct.toFixed(1)}%` : '—', desc: 'Cumulative weight percentage held by the top 10 largest positions.', icon: '🎯' },
    { label: 'Inception Date', val: etfObj.inception || '—', desc: 'Official date the fund was registered and opened for public trading.', icon: '📅' }
  ];

  grid.innerHTML = cards.map(c => `
    <div class="fund-card">
      <div class="fund-icon-circle">${c.icon}</div>
      <div class="fund-info-block">
        <span class="fund-lbl">${c.label}</span>
        <span class="fund-val">${c.val}</span>
        <span class="fund-sub-lbl">${c.desc}</span>
      </div>
    </div>
  `).join('');
}

// Side-by-side Returns comparison table vs SPY and ^NDX
function populateReturnsTable() {
  const body = document.getElementById('returnsTableBody');
  document.getElementById('returnColETF').textContent = etfObj.symbol;

  const spyRets = mainData.spy_returns || {};
  const ndxRets = (analyticsData && analyticsData.nasdaq100_trailing_returns) || {};
  const etfRets = etfObj.returns || {};

  // Periods of interest
  const tablePeriods = ['1W', '1M', '3M', '6M', '12M', '2Y', '3Y', '5Y'];

  body.innerHTML = tablePeriods.map(p => {
    const etfVal = etfRets[p];
    const spyVal = spyRets[p];
    const ndxVal = ndxRets[p];

    const vsSpy = etfVal != null && spyVal != null ? (etfVal - spyVal) : null;
    const vsNdx = etfVal != null && ndxVal != null ? (etfVal - ndxVal) : null;

    return `
      <tr>
        <td class="mono" style="font-weight:700;">${p}</td>
        <td class="mono ${etfVal >= 0 ? 'green' : etfVal < 0 ? 'red' : ''}">${etfVal != null ? etfVal.toFixed(2) + '%' : '—'}</td>
        <td class="mono" style="color:var(--text-secondary);">${spyVal != null ? spyVal.toFixed(2) + '%' : '—'}</td>
        <td class="mono" style="color:var(--text-secondary);">${ndxVal != null ? ndxVal.toFixed(2) + '%' : '—'}</td>
        <td class="mono etf-ret-cell ${vsSpy >= 0 ? 'pos' : vsSpy < 0 ? 'neg' : ''}">${vsSpy != null ? (vsSpy >= 0 ? '+' : '') + vsSpy.toFixed(2) + '%' : '—'}</td>
        <td class="mono etf-ret-cell ${vsNdx >= 0 ? 'pos' : vsNdx < 0 ? 'neg' : ''}">${vsNdx != null ? (vsNdx >= 0 ? '+' : '') + vsNdx.toFixed(2) + '%' : '—'}</td>
      </tr>
    `;
  }).join('');
}

// Populate the Returns Heatmap table
function populateHeatmapTable() {
  const body = document.getElementById('heatmapRowBody');
  const etfRets = etfObj.returns || {};
  const vsSpy = etfObj.vs_spy || {};

  // Row 1: ETF Returns
  let html = `
    <tr>
      <td class="hm-row-label">ETF Returns (${etfObj.symbol})</td>
      ${ALL_PERIODS.map(p => {
        const val = etfRets[p];
        return `<td class="${getHeatmapCellClass(val)}">${val != null ? val.toFixed(1) + '%' : '—'}</td>`;
      }).join('')}
    </tr>
  `;

  // Row 2: vs S&P 500 Outperformance
  html += `
    <tr>
      <td class="hm-row-label">Outperformance vs SPY</td>
      ${ALL_PERIODS.map(p => {
        const val = vsSpy[p];
        const display = val != null ? (val >= 0 ? '+' : '') + val.toFixed(1) + '%' : '—';
        return `<td class="${getHeatmapCellClass(val)}">${display}</td>`;
      }).join('')}
    </tr>
  `;

  body.innerHTML = html;
}

// Helper to color heatmap cells based on percentage value
function getHeatmapCellClass(val) {
  if (val == null) return 'hm-cell-neu';
  if (val >= 15) return 'hm-cell-pos-5';
  if (val >= 8) return 'hm-cell-pos-4';
  if (val >= 4) return 'hm-cell-pos-3';
  if (val >= 1) return 'hm-cell-pos-2';
  if (val > 0) return 'hm-cell-pos-1';
  if (val <= -15) return 'hm-cell-neg-5';
  if (val <= -8) return 'hm-cell-neg-4';
  if (val <= -4) return 'hm-cell-neg-3';
  if (val <= -1) return 'hm-cell-neg-2';
  return 'hm-cell-neg-1';
}

// Populate Portfolio Composition (Sector/Country/Market Cap)
function populateComposition() {
  const grid = document.getElementById('compositionGrid');
  const naMsg = document.getElementById('compositionNA');
  const meta = detailDb[symbol];

  // If no composition metadata is defined in etf_detail_data.json, show message
  if (!meta || !meta.sector_holdings) {
    grid.style.display = 'none';
    naMsg.style.display = 'flex';
    return;
  }

  grid.style.display = 'grid';
  naMsg.style.display = 'none';

  // "As of" date for holdings — shown month-end (ETF holdings are conventionally
  // reported as of month-end). Derived from the composition data's last_updated.
  const compAsOf = document.getElementById('compositionAsOf');
  if (compAsOf) compAsOf.textContent = 'Holdings as of ' + lastMonthEndLabel(meta.last_updated);

  // Render donut legends (Sector / Country — many categories, donut is the
  // right form here since no single slice dominates the way market-cap does)
  renderDonutLegend('sectorLegend', meta.sector_holdings, 'sector');
  renderDonutLegend('countryLegend', meta.country_exposure, 'country');

  const accentColor = getComputedStyle(document.documentElement).getPropertyValue('--etf-accent').trim() || '#3b82f6';

  // Developed / Emerging Markets — a binary split, so this is exactly the
  // "pie of 2 slices" case to avoid; keep it a compact 100%-stacked bar.
  const side = document.getElementById('mcapSide');
  if (side) {
    const hasDevEm = meta.developed_markets_pct != null && meta.emerging_markets_pct != null;
    if (hasDevEm) {
      const devEmList = [
        { label: 'Developed Mkts.', pct: meta.developed_markets_pct },
        { label: 'Emerging Mkts.', pct: meta.emerging_markets_pct },
      ];
      renderStackedBar('devEmStackedBar', devEmList, 'label', [accentColor, '#64748b']);
      document.getElementById('devEmLegend').innerHTML = renderBarLegend(devEmList, 'label', [accentColor, '#64748b']);
    } else {
      document.getElementById('devEmStackedBar').innerHTML = '';
      document.getElementById('devEmLegend').innerHTML = '';
    }

    // Concentration (HHI) + Wgt. Avg Mkt Cap — side by side
    const statRows = [];
    if (meta.concentration_hhi != null) statRows.push({ lbl: 'Concentration (HHI)', val: meta.concentration_hhi.toFixed(0), sub: hhiNote(meta.concentration_hhi) });
    if (meta.weighted_avg_market_cap) statRows.push({ lbl: 'Wgt. Avg Mkt Cap', val: formatMillionsUsd(meta.weighted_avg_market_cap), sub: 'Weighted average' });

    document.getElementById('mcapSideStats').innerHTML = statRows.map(r => `
      <div class="mcap-side-stat">
        <span class="mcap-side-lbl">${r.lbl}</span>
        <span class="mcap-side-val">${r.val}</span>
        ${r.sub ? `<span class="mcap-side-sub">${r.sub}</span>` : ''}
      </div>
    `).join('');
  }

  // Sector / Country donuts + Market Cap horizontal bar (Chart.js)
  renderCompositionCharts();
}

// etfrc reports weighted-avg market cap in millions as a "$1,545,461" string.
// Compact it to $1.55T / $845.2B etc.
function formatMillionsUsd(raw) {
  if (raw == null) return '—';
  const millions = parseFloat(String(raw).replace(/[$,]/g, ''));
  if (isNaN(millions)) return String(raw);
  const v = millions * 1e6;
  if (v >= 1e12) return `$${(v / 1e12).toFixed(2)}T`;
  if (v >= 1e9)  return `$${(v / 1e9).toFixed(1)}B`;
  if (v >= 1e6)  return `$${(v / 1e6).toFixed(1)}M`;
  return `$${v.toLocaleString()}`;
}

// Horizontal 100%-stacked bar — the correct form for part-to-whole data,
// especially when one category dominates (where a donut/pie reads as an
// near-empty ring instead of conveying the split).
function renderStackedBar(elementId, items, keyName, colors) {
  const el = document.getElementById(elementId);
  if (!el) return;
  const total = items.reduce((s, it) => s + (it.pct || 0), 0) || 1;
  el.innerHTML = items
    .filter(it => it.pct > 0)
    .map((it, i) => `<div class="stacked-bar-seg" style="width:${(it.pct / total * 100).toFixed(2)}%; background:${colors[i]};" title="${it[keyName]}: ${it.pct.toFixed(1)}%"></div>`)
    .join('');
}

function renderBarLegend(items, keyName, colors) {
  return items.map((it, i) => `
    <div class="legend-item">
      <div class="legend-left">
        <span class="legend-color-dot" style="background-color: ${colors[i]};"></span>
        <span class="legend-name">${it[keyName]}</span>
      </div>
      <span class="legend-val">${it.pct.toFixed(1)}%</span>
    </div>
  `).join('');
}

// Herfindahl-Hirschman Index (sum of squared weights, 0-10000) — standard
// concentration read: <1500 diversified, 1500-2500 moderate, >2500 concentrated
function hhiNote(hhi) {
  if (hhi < 1500) return 'Diversified';
  if (hhi < 2500) return 'Moderately concentrated';
  return 'Highly concentrated';
}

// Most recent completed month-end on/before the given date, formatted like
// "June 30, 2026" (ETF holdings are conventionally reported as of month-end).
function lastMonthEndLabel(dateStr) {
  const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June',
                  'July', 'August', 'September', 'October', 'November', 'December'];
  let d = dateStr ? new Date(String(dateStr).replace(' ', 'T')) : new Date();
  if (isNaN(d.getTime())) d = new Date();
  // Day 0 of the current month = the last day of the previous month
  const monthEnd = new Date(d.getFullYear(), d.getMonth(), 0);
  return MONTHS[monthEnd.getMonth()] + ' ' + monthEnd.getDate() + ', ' + monthEnd.getFullYear();
}

function renderDonutLegend(elementId, items, keyName) {
  const el = document.getElementById(elementId);
  const colors = getLegendColors(items.length);
  el.innerHTML = items.map((it, idx) => `
    <div class="legend-item">
      <div class="legend-left">
        <span class="legend-color-dot" style="background-color: ${colors[idx]};"></span>
        <span class="legend-name" title="${it[keyName]}">${it[keyName]}</span>
      </div>
      <span class="legend-val">${it.pct.toFixed(1)}%</span>
    </div>
  `).join('');
}

// Build Top 10 Holdings positions
function populateTop10Holdings() {
  const container = document.getElementById('top10Body');
  const headerText = document.getElementById('top10Concentration');
  const meta = detailDb[symbol];

  if (!meta || !meta.top10_holdings) {
    headerText.textContent = etfObj.top10_pct != null 
      ? `Top 10 concentration is ${etfObj.top10_pct.toFixed(2)}% of portfolio assets.` 
      : 'Top holdings information not available.';
    container.innerHTML = `
      <div class="etf-na-msg" style="grid-column: 1 / -1;">
        <span>🏦</span>
        <p>Positions information coming soon for this ETF.</p>
      </div>
    `;
    return;
  }

  headerText.textContent = `Cumulative weight: ${etfObj.top10_pct ? etfObj.top10_pct.toFixed(2) : '—'}% of total net assets.`;

  container.innerHTML = meta.top10_holdings.map(h => `
    <div class="holding-card">
      <div class="holding-card-top">
        <span class="holding-ticker">${h.ticker}</span>
        <span class="holding-weight">${h.weight.toFixed(2)}%</span>
      </div>
      <div class="holding-name" title="${h.name}">${h.name}</div>
      <div class="holding-sector">${h.sector}</div>
    </div>
  `).join('');
}

// Populate Momentum breakdown logic and indicator dial gauge
function populateMomentumSection() {
  // Score display
  const scoreVal = etfObj.momentum_score != null ? etfObj.momentum_score : 0;
  document.getElementById('gaugeScore').textContent = scoreVal.toFixed(1);

  // Position Needle
  // Needle ranges from -90deg (Score -30) to +90deg (Score +30)
  let clamped = Math.max(-30, Math.min(30, scoreVal));
  let deg = (clamped / 30) * 90; // scale linearly
  document.getElementById('gaugeNeedleWrap').style.transform = `translate(-50%, 0) rotate(${deg}deg)`;

  // Under-gauge Signal status box
  const signalBox = document.getElementById('momentumSignalBox');
  const statusCl = etfObj.signal.toLowerCase();
  signalBox.className = `sig-status-box ${statusCl}`;
  signalBox.innerHTML = `Signal Status: <strong>${etfObj.signal}</strong>`;

  // Breakdown Calculations Table
  const tableBody = document.getElementById('momentumBreakdownBody');
  const etfRets = etfObj.returns || {};

  const weights = { '1M': 0.20, '3M': 0.30, '6M': 0.30, '12M': 0.20 };
  const periods = ['1M', '3M', '6M', '12M'];

  let cumulativeScore = 0;

  tableBody.innerHTML = periods.map(p => {
    const ret = etfRets[p] || 0;
    const w = weights[p];
    const contribution = ret * w;
    cumulativeScore += contribution;

    return `
      <tr>
        <td class="mono" style="font-weight:600;">${p} Ret</td>
        <td class="mono">${ret >= 0 ? '+' : ''}${ret.toFixed(2)}%</td>
        <td class="mono">${(w * 100).toFixed(0)}%</td>
        <td class="mono ${contribution >= 0 ? 'green' : 'red'}">${contribution >= 0 ? '+' : ''}${contribution.toFixed(2)}</td>
      </tr>
    `;
  }).join('');

  // Total momentum footer row
  const totalRow = document.getElementById('momentumTotalRow');
  totalRow.innerHTML = `
    <td>Composite Score</td>
    <td>—</td>
    <td>100%</td>
    <td class="${cumulativeScore >= 0 ? 'green' : 'red'}" style="font-size:14px; font-weight:800;">${cumulativeScore.toFixed(2)}</td>
  `;
}

// ── CHARTS RENDERING (Chart.js) ───────────────────────────

// Helper: Convert hex color to rgba with alpha
function hexToRgba(hex, alpha) {
  const h = hex.replace('#', '');
  const r = parseInt(h.substring(0, 2), 16);
  const g = parseInt(h.substring(2, 4), 16);
  const b = parseInt(h.substring(4, 6), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

// Draw Price Performance Line Chart
function renderPriceChart() {
  const canvas = document.getElementById('priceChartCanvas');
  if (!canvas) return;

  if (priceChart) priceChart.destroy();

  const isLight = document.body.classList.contains('light-theme');
  const fontColor = isLight ? '#475569' : '#8b9ab5';
  const gridColor = isLight ? 'rgba(0,0,0,0.05)' : 'rgba(255,255,255,0.05)';

  // Resolve timeline slicing dates
  const timeline = getPriceChartData();
  if (!timeline) return;

  const accentColor = getComputedStyle(document.documentElement).getPropertyValue('--etf-accent').trim() || '#6366f1';

  // Datasets
  const datasets = [];
  const compareOn = compareBenchmarks.size > 0;

  if (compareOn) {
    // Normalized compare mode (%): ETF line + one line per selected index
    datasets.push({
      label: `${symbol} Return (%)`,
      data: timeline.etfPct,
      borderColor: accentColor,
      borderWidth: 2.5,
      pointRadius: 0,
      pointHoverRadius: 5,
      tension: 0.1,
      fill: false
    });

    BENCHMARK_ORDER.forEach(key => {
      if (!compareBenchmarks.has(key)) return;
      const series = timeline.benchPct[key];
      if (!series) return;
      datasets.push({
        label: `${BENCHMARK_LABEL[key]} (%)`,
        data: series,
        borderColor: BENCHMARK_COLOR[key],
        borderWidth: 1.5,
        borderDash: [5, 4],
        pointRadius: 0,
        pointHoverRadius: 4,
        tension: 0.1,
        fill: false
      });
    });
  } else {
    // Normal NAV Price mode ($)
    // Build gradient fill background
    const ctx = canvas.getContext('2d');
    const gradient = ctx.createLinearGradient(0, 0, 0, 400);
    gradient.addColorStop(0, hexToRgba(accentColor, 0.3));
    gradient.addColorStop(1, 'rgba(0,0,0,0)');

    datasets.push({
      label: `${symbol} Price ($)`,
      data: timeline.etfRaw,
      borderColor: accentColor,
      backgroundColor: gradient,
      borderWidth: 2,
      pointRadius: 0,
      pointHoverRadius: 6,
      tension: 0.05,
      fill: true
    });
  }

  // Draw chart
  priceChart = new Chart(canvas, {
    type: 'line',
    data: {
      labels: timeline.labels,
      datasets: datasets
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: {
        mode: 'index',
        intersect: false
      },
      plugins: {
        legend: {
          display: true,
          position: 'top',
          labels: {
            color: fontColor,
            font: { family: 'Inter', size: 11, weight: '500' }
          }
        },
        tooltip: {
          backgroundColor: isLight ? '#ffffff' : '#161a24',
          titleColor: isLight ? '#0f172a' : '#f0f2ff',
          bodyColor: isLight ? '#475569' : '#8b9ab5',
          borderColor: isLight ? '#cbd5e1' : 'rgba(255,255,255,0.1)',
          borderWidth: 1,
          padding: 10,
          callbacks: {
            label: function(context) {
              let label = context.dataset.label || '';
              if (label) label += ': ';
              if (context.parsed.y !== null) {
                label += compareOn
                  ? context.parsed.y.toFixed(2) + '%'
                  : '$' + context.parsed.y.toFixed(2);
              }
              return label;
            }
          }
        }
      },
      scales: {
        x: {
          grid: { color: gridColor },
          ticks: {
            color: fontColor,
            font: { family: 'JetBrains Mono', size: 9 },
            maxTicksLimit: 8
          }
        },
        y: {
          grid: { color: gridColor },
          ticks: {
            color: fontColor,
            font: { family: 'JetBrains Mono', size: 9 },
            callback: function(val) {
              return compareOn ? val.toFixed(1) + '%' : '$' + val.toFixed(1);
            }
          }
        }
      }
    }
  });

  // Update Footer subtitle
  const ft = document.getElementById('priceChartFooter');
  if (ft) {
    if (compareOn) {
      const names = BENCHMARK_ORDER.filter(k => compareBenchmarks.has(k)).map(k => BENCHMARK_LABEL[k]).join(', ');
      ft.textContent = `Normalized total return (%) from 0.00% on ${timeline.labels[0]}, vs ${names}.`;
    } else {
      ft.textContent = `Daily adjusted closing levels ($) from ${timeline.labels[0]} to ${timeline.labels[timeline.labels.length - 1]}.`;
    }
  }
}

// Slice price arrays and reconstruct RAW and PCT structures
function getPriceChartData() {
  if (!historyData || !historyData.dates) return null;

  const dates = historyData.dates;
  const etfNorm = historyData.series[symbol];

  if (!etfNorm) return null;

  // Resolve scaling factor: Raw = Normalized * (Price_latest / Normalized_latest)
  const normLatest = etfNorm[etfNorm.length - 1];
  const scaleFactor = etfObj.price / normLatest;

  // Get index boundary matching timeframe
  let startIndex = 0;
  const lastIndex = dates.length - 1;
  const lastDate = new Date(dates[lastIndex]);

  if (chartTimeframe === 'custom') {
    const fromStr = document.getElementById('etfFromDate').value;
    const toStr = document.getElementById('etfToDate').value;
    
    let fromIdx = dates.findIndex(d => d >= fromStr);
    let toIdx = dates.findIndex(d => d >= toStr);

    if (fromIdx === -1) fromIdx = 0;
    if (toIdx === -1) toIdx = lastIndex;
    startIndex = fromIdx;
  } else {
    let monthsToSubtract = 12;
    if (chartTimeframe === '1M') monthsToSubtract = 1;
    else if (chartTimeframe === '3M') monthsToSubtract = 3;
    else if (chartTimeframe === '6M') monthsToSubtract = 6;
    else if (chartTimeframe === '3Y') monthsToSubtract = 36;
    else if (chartTimeframe === '5Y') monthsToSubtract = 60;
    else if (chartTimeframe === 'All') monthsToSubtract = 999;

    if (monthsToSubtract < 900) {
      const targetDate = new Date(lastDate);
      targetDate.setMonth(targetDate.getMonth() - monthsToSubtract);
      const targetStr = targetDate.toISOString().split('T')[0];
      startIndex = dates.findIndex(d => d >= targetStr);
      if (startIndex === -1) startIndex = 0;
    }
  }

  // Slice arrays
  const slicedDates = dates.slice(startIndex);
  const slicedEtfNorm = etfNorm.slice(startIndex);

  // Build raw dollars arrays
  const etfRaw = slicedEtfNorm.map(v => v * scaleFactor);

  // Build normalized percentage returns starting at 0%
  const etfStartVal = etfRaw[0];
  const etfPct = etfRaw.map(v => ((v / etfStartVal) - 1) * 100);

  // Normalized % return for each SELECTED benchmark index, keyed by button id
  const benchPct = {};
  compareBenchmarks.forEach(key => {
    const seriesKey = BENCHMARK_SERIES_KEY[key];
    const raw = seriesKey ? historyData.series[seriesKey] : null;
    if (!raw) return;
    const sliced = raw.slice(startIndex);
    // find first non-null base so a benchmark with a later start still normalizes
    const base = sliced.find(v => v != null && v > 0);
    if (base == null) return;
    benchPct[key] = sliced.map(v => (v != null ? ((v / base) - 1) * 100 : null));
  });

  return {
    labels: slicedDates,
    etfRaw,
    etfPct,
    benchPct
  };
}

// Draw Portfolio composition Donut rings (Sectors & Countries)
function renderCompositionCharts() {
  const meta = detailDb[symbol];
  if (!meta || !meta.sector_holdings) return;

  const isLight = document.body.classList.contains('light-theme');
  const borderCol = isLight ? '#ffffff' : '#1a1f2e';

  // 1. Sector Donut
  const sectorCanvas = document.getElementById('sectorChartCanvas');
  if (sectorCanvas) {
    if (sectorChart) sectorChart.destroy();
    
    const labels = meta.sector_holdings.map(h => h.sector);
    const data = meta.sector_holdings.map(h => h.pct);
    const colors = getLegendColors(data.length);

    sectorChart = new Chart(sectorCanvas, {
      type: 'doughnut',
      data: {
        labels,
        datasets: [{
          data,
          backgroundColor: colors,
          borderColor: borderCol,
          borderWidth: 2
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: '70%',
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: (ctx) => ` ${ctx.label}: ${ctx.raw.toFixed(1)}%`
            }
          }
        }
      }
    });
  }

  // 2. Country Donut
  const countryCanvas = document.getElementById('countryChartCanvas');
  if (countryCanvas) {
    if (countryChart) countryChart.destroy();

    const labels = meta.country_exposure.map(c => c.country);
    const data = meta.country_exposure.map(c => c.pct);
    const colors = getLegendColors(data.length);

    countryChart = new Chart(countryCanvas, {
      type: 'doughnut',
      data: {
        labels,
        datasets: [{
          data,
          backgroundColor: colors,
          borderColor: borderCol,
          borderWidth: 2
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: '70%',
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: (ctx) => ` ${ctx.label}: ${ctx.raw.toFixed(1)}%`
            }
          }
        }
      }
    });
  }

  // 3. Market Cap Exposure — horizontal bar chart. Cap tiers are ordered
  // magnitudes, so a bar chart (one hue, sequential shade) reads them cleanly.
  const mcapCanvas = document.getElementById('mcapBarChartCanvas');
  if (mcapCanvas && meta.market_cap && meta.market_cap.length) {
    if (mcapBarChart) mcapBarChart.destroy();
    const accentColor = getComputedStyle(document.documentElement).getPropertyValue('--etf-accent').trim() || '#3b82f6';
    const isLight = document.body.classList.contains('light-theme');
    const fontColor = isLight ? '#475569' : '#8b9ab5';
    const gridColor = isLight ? 'rgba(0,0,0,0.05)' : 'rgba(255,255,255,0.05)';

    const labels = meta.market_cap.map(m => m.cap);
    const data = meta.market_cap.map(m => m.pct);
    const colors = data.map((_, i) => hexToRgba(accentColor, 1 - i * 0.22));

    mcapBarChart = new Chart(mcapCanvas, {
      type: 'bar',
      data: {
        labels,
        datasets: [{
          data,
          backgroundColor: colors,
          borderRadius: 4,
          barThickness: 22,
          maxBarThickness: 24
        }]
      },
      options: {
        indexAxis: 'y',
        responsive: true,
        maintainAspectRatio: false,
        layout: { padding: { right: 44 } },
        plugins: {
          legend: { display: false },
          tooltip: { callbacks: { label: (ctx) => ` ${ctx.raw.toFixed(1)}%` } }
        },
        scales: {
          x: {
            display: false,
            max: Math.min(100, Math.max(...data) * 1.15),
            grid: { display: false }
          },
          y: {
            grid: { color: gridColor, drawBorder: false },
            ticks: { color: fontColor, font: { family: 'Inter', size: 11, weight: '600' } }
          }
        }
      },
      plugins: [{
        id: 'mcapValueLabels',
        afterDatasetsDraw(chart) {
          const { ctx } = chart;
          const meta0 = chart.getDatasetMeta(0);
          ctx.save();
          ctx.font = '600 12px JetBrains Mono, monospace';
          ctx.fillStyle = fontColor;
          ctx.textBaseline = 'middle';
          meta0.data.forEach((bar, i) => {
            const val = data[i];
            ctx.fillText(`${val.toFixed(1)}%`, bar.x + 8, bar.y);
          });
          ctx.restore();
        }
      }]
    });
  }
}

// ── MONTHLY RETURNS (replaces the old Relative Strength vs SPY section) ──

// Populate the Monthly Returns calendar (year rows x month columns + Total)
function populateMonthlyReturns() {
  const headRow = document.getElementById('monthlyReturnsHeadRow');
  const body = document.getElementById('monthlyReturnsBody');
  const desc = document.getElementById('monthlyReturnsDesc');
  const footer = document.getElementById('monthlyReturnsFooter');

  const entry = analyticsData && analyticsData.etfs ? analyticsData.etfs[symbol] : null;
  const calendar = entry && entry.monthly_returns_calendar;
  const totals = entry && entry.monthly_returns_annual_total;
  const asOf = analyticsData && analyticsData.as_of_date;

  if (!calendar || Object.keys(calendar).length === 0) {
    desc.textContent = 'Monthly returns not available for this ETF yet.';
    headRow.innerHTML = '';
    body.innerHTML = '';
    footer.textContent = '';
    return;
  }

  desc.textContent = `Calendar-year monthly returns of ${symbol}, computed from daily adjusted (total-return) NAV.`;

  // Header row: Year | Jan..Dec | Total
  headRow.innerHTML = `<th class="hm-row-label">Year</th>` +
    MONTH_ABBR.map(m => `<th>${m}</th>`).join('') +
    `<th>Total</th>`;

  const years = Object.keys(calendar).map(Number).sort((a, b) => b - a); // most recent first

  body.innerHTML = years.map(y => {
    const months = calendar[y] || {};
    const monthCells = MONTH_ABBR.map(m => {
      const val = months[m];
      if (val == null) return `<td class="hm-cell-neu">—</td>`;
      return `<td class="${getHeatmapCellClass(val)}">${val >= 0 ? '+' : ''}${val.toFixed(2)}%</td>`;
    }).join('');
    const total = totals ? totals[y] : null;
    const totalCell = total == null ? `<td class="hm-row-label">—</td>`
      : `<td class="hm-row-label ${total >= 0 ? 'green' : 'red'}" style="font-weight:700;">${total >= 0 ? '+' : ''}${total.toFixed(2)}%</td>`;
    return `<tr><td class="hm-row-label">${y}</td>${monthCells}${totalCell}</tr>`;
  }).join('');

  footer.textContent = asOf
    ? `Latest calendar month reflects month-to-date return as of ${asOf} (synced with the daily screener update). Completed months reflect the full return through each month's final trading day.`
    : '';
}

// ── RISK ANALYSIS ──────────────────────────────────────────

function populateRiskAnalysis() {
  const section = document.getElementById('riskSection');
  const naMsg = document.getElementById('riskNA');
  const entry = analyticsData && analyticsData.etfs ? analyticsData.etfs[symbol] : null;
  const risk = entry && entry.risk_analysis;

  if (!risk) {
    section.style.display = 'none';
    naMsg.style.display = 'flex';
    return;
  }

  section.style.display = 'block';
  naMsg.style.display = 'none';

  const benchLabel = entry.benchmark_label || entry.benchmark_symbol || 'benchmark';
  document.getElementById('riskSectionDesc').textContent =
    `${risk.window_months}-month window vs ${benchLabel} · Risk-free rate: ${risk.risk_free_rate_annual_pct}% (US 3M T-Bill) · As of ${analyticsData.as_of_date}`;

  const interpHeading = document.getElementById('riskInterpHeading');
  if (interpHeading) interpHeading.textContent = `${symbol} — Risk Profile Interpretation`;

  document.getElementById('riskStdDev').textContent = `${risk.std_dev_annual_pct.toFixed(2)}%`;
  document.getElementById('riskSharpe').textContent = risk.sharpe_ratio != null ? risk.sharpe_ratio.toFixed(2) : '—';
  document.getElementById('riskSortino').textContent = risk.sortino_ratio != null ? risk.sortino_ratio.toFixed(2) : '—';
  document.getElementById('riskBeta').textContent = risk.beta != null ? risk.beta.toFixed(2) : '—';
  document.getElementById('riskBetaSub').textContent = `Sensitivity vs ${benchLabel}`;
  document.getElementById('riskAlpha').textContent = risk.alpha_annual_pct != null ? `${risk.alpha_annual_pct >= 0 ? '+' : ''}${risk.alpha_annual_pct.toFixed(2)}%` : '—';

  const ddEl = document.getElementById('riskMaxDD');
  ddEl.textContent = `${risk.max_drawdown_pct.toFixed(2)}%`;
  ddEl.className = 'risk-metric-val red';
  document.getElementById('riskMaxDDSub').textContent = `Trough: ${risk.max_drawdown_trough_date}`;

  const recEl = document.getElementById('riskRecovery');
  recEl.textContent = risk.recovery_date ? `${risk.recovery_days}d` : `${risk.recovery_days}d (ongoing)`;
  document.getElementById('riskRecoverySub').textContent = risk.recovery_date
    ? `Recovered by ${risk.recovery_date}`
    : 'Has not yet regained its prior peak';

  const compEl = document.getElementById('riskComposite');
  compEl.textContent = risk.composite_score.toFixed(1);
  compEl.className = 'risk-metric-val ' + (risk.composite_score >= 65 ? 'green' : risk.composite_score >= 45 ? '' : 'red');
  document.getElementById('riskCompositeSub').textContent = risk.composite_note;

  renderRiskCharts();
  renderRiskNarrative(risk, benchLabel);
}

// Build a professional, evaluative, data-driven risk narrative — every
// sentence, verdict, and the overall banner are recomputed from the current
// numbers on every load. Nothing here is fixed copy; change the inputs and
// the read changes with them.
const VERDICT_META = {
  good:    { label: 'Favorable',  cls: 'green'  },
  neutral: { label: 'Neutral',    cls: 'yellow' },
  caution: { label: 'Caution',    cls: 'red'    },
};

function verdictBadge(kind) {
  const m = VERDICT_META[kind];
  return `<span class="risk-verdict-tag ${m.cls}">${m.label}</span>`;
}

function renderRiskNarrative(risk, benchLabel) {
  const list = document.getElementById('riskNarrativeList');
  const points = []; // { verdict, icon, metric, headline, text }

  // Beta — sensitivity to the benchmark, and what that implies for sizing
  if (risk.beta != null) {
    if (risk.beta > 1.15) {
      points.push({ verdict: 'caution', icon: '📈', metric: 'Beta', headline: `Amplifies the market by ~${Math.round((risk.beta - 1) * 100)}%`, text:
        `At a beta of ${risk.beta.toFixed(2)} vs ${benchLabel}, ${symbol} magnifies the benchmark's moves in <em>both</em> directions. Great in a rally, painful in a drawdown — a sizing consideration, not a buy/avoid signal on its own.` });
    } else if (risk.beta < 0.85) {
      points.push({ verdict: 'good', icon: '🛡️', metric: 'Beta', headline: 'Cushions market swings', text:
        `A beta of ${risk.beta.toFixed(2)} means ${symbol} has absorbed less of ${benchLabel}'s volatility — a defensive trait that helps in selloffs, though it can also cap upside in strong rallies.` });
    } else {
      points.push({ verdict: 'neutral', icon: '📊', metric: 'Beta', headline: 'Moves in step with the market', text:
        `A beta of ${risk.beta.toFixed(2)} sits near 1, so ${symbol} has tracked ${benchLabel} closely. Little diversification signal here — it mainly confirms the fund behaves as its category should.` });
    }
  }

  // Alpha — is there a genuine edge beyond benchmark exposure, or not
  if (risk.alpha_annual_pct != null) {
    if (risk.alpha_annual_pct > 1) {
      points.push({ verdict: 'good', icon: '✨', metric: 'Alpha', headline: `Genuine edge of +${risk.alpha_annual_pct.toFixed(1)}%/yr`, text:
        `${symbol} beat what its market exposure alone would predict by <strong>${risk.alpha_annual_pct.toFixed(2)}%/yr</strong> — evidence of a real structural or selection edge, not just a leveraged bet on ${benchLabel}. This is what separates "adds value" from "just a beta play."` });
    } else if (risk.alpha_annual_pct < -1) {
      points.push({ verdict: 'caution', icon: '📉', metric: 'Alpha', headline: `Lagged its expected return by ${Math.abs(risk.alpha_annual_pct).toFixed(1)}%/yr`, text:
        `${symbol} underdelivered versus what its beta to ${benchLabel} would predict by <strong>${risk.alpha_annual_pct.toFixed(2)}%/yr</strong>. A cheaper, plain benchmark exposure would plausibly have matched it risk-adjusted.` });
    } else {
      points.push({ verdict: 'neutral', icon: '⚖️', metric: 'Alpha', headline: 'No edge either way', text:
        `Alpha near zero (${risk.alpha_annual_pct.toFixed(2)}%/yr) means performance is fully explained by exposure to ${benchLabel} — no meaningful unexplained skill in either direction.` });
    }
  }

  // Sharpe — return earned per unit of total risk
  if (risk.sharpe_ratio != null) {
    if (risk.sharpe_ratio >= 1) {
      points.push({ verdict: 'good', icon: '🎯', metric: 'Sharpe Ratio', headline: 'Strong reward for the risk taken', text:
        `A Sharpe of ${risk.sharpe_ratio.toFixed(2)} means investors have been well compensated for the volatility they've stomached. It penalizes up- and down-swings equally, though — which is exactly why we read it alongside Sortino next.` });
    } else if (risk.sharpe_ratio >= 0.5) {
      points.push({ verdict: 'neutral', icon: '🎯', metric: 'Sharpe Ratio', headline: 'Fair, not decisive', text:
        `A Sharpe of ${risk.sharpe_ratio.toFixed(2)} says returns have covered the risk taken, but not by a wide margin. Worth weighing against steadier alternatives in the same category.` });
    } else {
      points.push({ verdict: 'caution', icon: '🎯', metric: 'Sharpe Ratio', headline: 'Risk outweighed reward', text:
        `A Sharpe of ${risk.sharpe_ratio.toFixed(2)} is weak — the return earned hasn't adequately paid for the volatility endured over this window. A lower-volatility alternative may have delivered a comparable risk-adjusted outcome.` });
    }
  }

  // Sortino — same idea as Sharpe, but isolates downside risk only
  if (risk.sortino_ratio != null && risk.sharpe_ratio != null) {
    const upsideDriven = risk.sortino_ratio > risk.sharpe_ratio + 0.3;
    points.push({ verdict: risk.sortino_ratio >= 1 ? 'good' : 'neutral', icon: '🌪️', metric: 'Sortino Ratio',
      headline: upsideDriven ? 'Most of the "risk" is upside' : 'Risk is fairly two-sided',
      text: upsideDriven
        ? `At ${risk.sortino_ratio.toFixed(2)}, Sortino runs well above Sharpe — a tell that much of ${symbol}'s volatility comes from sharp <em>upside</em> moves, the kind Sharpe unfairly punishes but Sortino ignores.`
        : `At ${risk.sortino_ratio.toFixed(2)}, Sortino sits close to Sharpe, meaning ${symbol}'s swings are split fairly evenly between gains and losses.` });
  }

  // Max Drawdown + Recovery — worst-case pain and how long it lasted
  if (risk.max_drawdown_pct != null) {
    const sev = risk.max_drawdown_pct <= -40 ? 'severe' : risk.max_drawdown_pct <= -20 ? 'significant' : 'moderate';
    const ddVerdict = risk.max_drawdown_pct <= -40 ? 'caution' : risk.max_drawdown_pct <= -20 ? 'neutral' : 'good';
    const recoveryClause = risk.recovery_date
      ? `then clawed all the way back by ${risk.recovery_date} — <strong>${risk.recovery_days} days</strong> underwater for anyone who bought the peak.`
      : `and it still hasn't fully recovered — <strong>${risk.recovery_days} days</strong> and counting, a real consideration on a shorter horizon.`;
    points.push({ verdict: ddVerdict, icon: '📉', metric: 'Max Drawdown', headline: `${sev.charAt(0).toUpperCase() + sev.slice(1)}: ${risk.max_drawdown_pct.toFixed(1)}% peak-to-trough`, text:
      `The deepest fall was <strong>${risk.max_drawdown_pct.toFixed(2)}%</strong>, bottoming ${risk.max_drawdown_trough_date}, ${recoveryClause}` });
  }

  // Upside / Downside Capture — is the asymmetry working for or against the investor
  if (risk.upside_capture_pct != null && risk.downside_capture_pct != null) {
    const spread = risk.upside_capture_pct - risk.downside_capture_pct;
    if (spread > 5) {
      points.push({ verdict: 'good', icon: '🪝', metric: 'Capture', headline: 'Catches rallies, dodges selloffs', text:
        `${symbol} banked <strong>${risk.upside_capture_pct.toFixed(0)}%</strong> of ${benchLabel}'s up-month gains but wore only <strong>${risk.downside_capture_pct.toFixed(0)}%</strong> of its down-month losses — the asymmetry every risk-conscious holder wants.` });
    } else if (spread < -5) {
      points.push({ verdict: 'caution', icon: '🪝', metric: 'Capture', headline: 'Feels selloffs more than rallies', text:
        `${symbol} absorbed <strong>${risk.downside_capture_pct.toFixed(0)}%</strong> of ${benchLabel}'s down-month losses but captured only <strong>${risk.upside_capture_pct.toFixed(0)}%</strong> of its up-month gains — the wrong-way asymmetry.` });
    } else {
      points.push({ verdict: 'neutral', icon: '🪝', metric: 'Capture', headline: 'Symmetric with the market', text:
        `Upside (${risk.upside_capture_pct.toFixed(0)}%) and downside (${risk.downside_capture_pct.toFixed(0)}%) capture are roughly balanced vs ${benchLabel} — the fund neither cushions selloffs nor outruns rallies.` });
    }
  }

  list.innerHTML = points.map(p => `
    <div class="risk-interp-card ${VERDICT_META[p.verdict].cls}">
      <div class="risk-interp-icon">${p.icon}</div>
      <div class="risk-interp-body">
        <div class="risk-interp-head">
          <span class="risk-interp-metric">${p.metric}</span>
          ${verdictBadge(p.verdict)}
        </div>
        <div class="risk-interp-headline">${p.headline}</div>
        <div class="risk-interp-text">${p.text}</div>
      </div>
    </div>
  `).join('');

  renderRiskVerdictBanner(risk, points);
}

// The synthesis hero — a big composite score dial plus a verdict tier, derived
// from the composite score AND how many individual cards landed favorable vs.
// cautionary (so it reflects genuine agreement across metrics, not just the score).
function renderRiskVerdictBanner(risk, points) {
  const banner = document.getElementById('riskVerdictBanner');
  if (!banner) return;

  const goodCount = points.filter(p => p.verdict === 'good').length;
  const cautionCount = points.filter(p => p.verdict === 'caution').length;

  let tier, cls, summary;
  if (risk.composite_score >= 65 && cautionCount <= 1) {
    tier = 'Favorable Risk Profile'; cls = 'green';
    summary = `${goodCount} of ${points.length} signals below are favorable and the composite agrees. This isn't "low risk" in absolute terms — it means ${symbol} has historically paid investors well for the risk it carries.`;
  } else if (risk.composite_score < 45 || cautionCount >= 3) {
    tier = 'Cautionary Risk Profile'; cls = 'red';
    summary = `${cautionCount} of ${points.length} signals below flag concerns and the composite is on the weak side. Not a reason to avoid ${symbol} outright — a prompt to weigh these trade-offs against your horizon before sizing in.`;
  } else {
    tier = 'Mixed Risk Profile'; cls = 'yellow';
    summary = `Signals are split — ${goodCount} favorable, ${cautionCount} cautionary. The composite lands mid-range, so read the individual cards below rather than trusting one number.`;
  }

  banner.innerHTML = `
    <div class="risk-hero-score ${cls}">
      <span class="risk-hero-score-val">${risk.composite_score.toFixed(0)}</span>
      <span class="risk-hero-score-max">/100</span>
    </div>
    <div class="risk-hero-text">
      <span class="risk-hero-tier ${cls}">${tier}</span>
      <span class="risk-hero-summary">${summary}</span>
    </div>
  `;
}

// Chart 1: Upside/Downside Capture bar. Chart 2: 3Y drawdown history from the
// same price history already loaded for the main price chart (no new fetch).
function renderRiskCharts() {
  const entry = analyticsData && analyticsData.etfs ? analyticsData.etfs[symbol] : null;
  const risk = entry && entry.risk_analysis;
  if (!risk) return;

  const isLight = document.body.classList.contains('light-theme');
  const fontColor = isLight ? '#475569' : '#8b9ab5';
  const gridColor = isLight ? 'rgba(0,0,0,0.05)' : 'rgba(255,255,255,0.05)';
  const accentColor = getComputedStyle(document.documentElement).getPropertyValue('--etf-accent').trim() || '#3b82f6';

  // Capture chart
  const capCanvas = document.getElementById('captureChartCanvas');
  if (capCanvas) {
    if (captureChart) captureChart.destroy();
    captureChart = new Chart(capCanvas, {
      type: 'bar',
      data: {
        labels: ['Upside Capture', 'Downside Capture'],
        datasets: [{
          data: [risk.upside_capture_pct, risk.downside_capture_pct],
          backgroundColor: [hexToRgba(accentColor, 0.75), 'rgba(239, 68, 68, 0.55)'],
          borderRadius: 4
        }]
      },
      options: {
        indexAxis: 'y',
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: { callbacks: { label: (ctx) => ` ${ctx.raw != null ? ctx.raw.toFixed(1) + '%' : '—'}` } }
        },
        scales: {
          x: { grid: { color: gridColor }, ticks: { color: fontColor, font: { family: 'JetBrains Mono', size: 9 }, callback: v => v + '%' } },
          y: { grid: { display: false }, ticks: { color: fontColor, font: { family: 'Inter', size: 11, weight: '600' } } }
        }
      }
    });
  }

  // Drawdown chart — last 3Y of daily adjusted close from history.json
  const ddCanvas = document.getElementById('drawdownChartCanvas');
  if (ddCanvas && historyData && historyData.series && historyData.series[symbol]) {
    if (drawdownChart) drawdownChart.destroy();
    const dates = historyData.dates;
    const series = historyData.series[symbol];
    const startIdx = Math.max(0, dates.length - 756); // ~3 trading years
    const slicedDates = dates.slice(startIdx);
    const slicedSeries = series.slice(startIdx);

    let peak = -Infinity;
    const dd = slicedSeries.map(v => {
      if (v == null) return null;
      peak = Math.max(peak, v);
      return ((v / peak) - 1) * 100;
    });

    drawdownChart = new Chart(ddCanvas, {
      type: 'line',
      data: {
        labels: slicedDates,
        datasets: [{
          data: dd,
          borderColor: 'rgba(239, 68, 68, 0.9)',
          backgroundColor: 'rgba(239, 68, 68, 0.15)',
          borderWidth: 1.5,
          pointRadius: 0,
          fill: true,
          tension: 0.05
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: { callbacks: { label: (ctx) => ` ${ctx.parsed.y.toFixed(2)}%` } }
        },
        scales: {
          x: { grid: { color: gridColor }, ticks: { color: fontColor, font: { family: 'JetBrains Mono', size: 9 }, maxTicksLimit: 6 } },
          y: { grid: { color: gridColor }, ticks: { color: fontColor, font: { family: 'JetBrains Mono', size: 9 }, callback: v => v + '%' } }
        }
      }
    });
  }
}

// ── ACTIONS / CONTROLS ────────────────────────────────────

// Set Timeframe from button clicks
window.setEtfTf = function(tf) {
  chartTimeframe = tf;

  // Toggle active class on buttons
  const container = document.getElementById('etfTfPills');
  if (container) {
    container.querySelectorAll('.etf-tf-btn').forEach(btn => {
      if (btn.getAttribute('data-tf') === tf) btn.classList.add('active');
      else btn.classList.remove('active');
    });
  }

  // Toggle custom dates view
  const customRow = document.getElementById('etfCustomDates');
  if (customRow) {
    customRow.style.display = tf === 'custom' ? 'flex' : 'none';
  }

  if (tf !== 'custom') {
    renderPriceChart();
  }
};

// Toggle an index into/out of the multi-select comparison. Any combination
// (S&P 500, Nasdaq-100, Nifty 50, Nifty 500) can be active at the same time.
window.toggleCompareIndex = function(key) {
  if (compareBenchmarks.has(key)) compareBenchmarks.delete(key);
  else compareBenchmarks.add(key);

  const btn = document.querySelector(`.etf-compare-btn[data-idx="${key}"]`);
  if (btn) {
    btn.classList.toggle('active', compareBenchmarks.has(key));
    if (compareBenchmarks.has(key)) {
      // tint the active button with that index's line color for a clear legend link
      btn.style.borderColor = BENCHMARK_COLOR[key];
      btn.style.color = BENCHMARK_COLOR[key];
    } else {
      btn.style.borderColor = '';
      btn.style.color = '';
    }
  }
  renderPriceChart();
};

// ── HELPERS ───────────────────────────────────────────────

function getSignalEmoji(sig) {
  if (sig === 'Strong') return '🟢';
  if (sig === 'Neutral') return '🟡';
  return '🔴';
}

function formatAUM(v) {
  if (v == null || isNaN(v)) return '—';
  if (v >= 1e12) return `$${(v / 1e12).toFixed(2)}T`;
  if (v >= 1e9)  return `$${(v / 1e9).toFixed(2)}B`;
  if (v >= 1e6)  return `$${(v / 1e6).toFixed(2)}M`;
  return `$${v.toLocaleString()}`;
}

// Generate color shades dynamically for composition donut pieces
function getLegendColors(num) {
  const baseColors = [
    '#6366f1', // Indigo
    '#10b981', // Emerald
    '#f59e0b', // Amber
    '#3b82f6', // Blue
    '#ec4899', // Pink
    '#8b5cf6', // Purple
    '#06b6d4', // Cyan
    '#f97316', // Orange
    '#84cc16', // Lime
    '#64748b'  // Slate / Gray
  ];
  return baseColors.slice(0, num);
}
