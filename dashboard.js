/* ═══════════════════════════════════════════════════════════
   Armstrong Capital — ETF Momentum Dashboard
   dashboard.js  |  Full interactive logic
═══════════════════════════════════════════════════════════ */

'use strict';

// ── State ─────────────────────────────────────────────────
let DATA        = null;
let filtered    = [];
let sortCol     = 'momentum_score';
let sortDir     = -1;   // -1 = descending, +1 = ascending
let activeTab   = 'overview';
let datasetMode = '100';

const PERIODS_HEATMAP = ['1W','15D','1M','2M','3M','6M','9M','12M','2Y','3Y','5Y','7Y','10Y'];
const PERIODS_REL     = ['1W','1M','3M','6M','12M','2Y','3Y','5Y'];

const TOP_20_TICKERS = [
  "QQQ", "XLP", "GLD", "XLY", "VOO", "SMH", "URA", "AIQ", "CIBR", "REMX", 
  "BOTZ", "UFO", "SKYY", "PPA", "ESPO", "OZEM", "PJP", "SLV", "FNGS", "BBP"
];

let vhPeriod = '1W';

// ── Bootstrap ────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', async () => {
  bindTabs();
  await loadData();
});

// ── Data Load ─────────────────────────────────────────────
async function loadData() {
  await fetchAndRender();
}



async function fetchAndRender() {
  showLoading(true);
  hideError();
  try {
    const isLocal = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';
    const file = datasetMode === 'all' ? 'dashboard_all.json' : 'dashboard.json';
    const res = await fetch(file + '?nocache=' + Date.now());
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    DATA = await res.json();
    processData();
    showLoading(false);

    const today = new Promise(resolve => {
        const d = new Date();
        resolve(d.toISOString().split('T')[0]);
    });
    const currentDay = await today;
    const isUpToDate = DATA.as_of_date === currentDay;

    if (DATA) {
      if (isUpToDate) {
        showToast('Dashboard is up to date with today\'s market figures.', 'success');
      } else {
        showToast('Data shown is from ' + DATA.as_of_date + '. Next auto-update: 7:00 AM IST.', 'info');
      }
    }
  } catch (e) {
    showLoading(false);
    showError();
    console.error('Failed to load data:', e);
    showToast('Failed to fetch latest data.', 'error');
  }
}

function showToast(msg, type = 'info') {
  const container = document.getElementById('notification-container');
  if (!container) return;
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.innerHTML = `<span>${msg}</span>`;
  container.appendChild(toast);
  setTimeout(() => toast.remove(), 6000);
}

// ── Process & Render ──────────────────────────────────────
function processData() {
  // Meta bar
  document.getElementById('updateText').textContent =
    'Updated: ' + (DATA.last_updated || '—');
  document.getElementById('asOfDate').textContent =
    'As of: ' + (DATA.as_of_date || '—');

  // Permission: Editor Only actions
  if (!Auth.isEditor()) {
    const rBtn = document.getElementById('refreshBtn');
    if (rBtn) rBtn.style.display = 'none';
  }

  // Stats
  const etfs = DATA.etfs || [];
  const strong  = etfs.filter(e => e.signal === 'Strong').length;
  const neutral = etfs.filter(e => e.signal === 'Neutral').length;
  const weak    = etfs.filter(e => e.signal === 'Weak').length;

  setStatVal('statTotal',    etfs.length, '');
  setStatVal('statStrong',   strong,      'green');
  setStatVal('statNeutral',  neutral,     'yellow');
  setStatVal('statWeak',     weak,        'red');

  const spy3m = DATA.spy_returns?.['3M'];
  document.getElementById('spyScore').textContent =
    spy3m != null ? fmtPct(spy3m) : '—';
  colorizeVal(document.getElementById('spyScore'), spy3m);

  const top1 = (DATA.top10 || [])[0];
  document.getElementById('topEtfVal').textContent =
    top1 ? `${top1.symbol}  ${fmtScore(top1.score)}` : '—';

  // Populate category filter
  populateCategoryFilter(etfs);

  // Render all sections
  filtered = [...etfs];
  renderMarketBar();
  applyFilters();
  renderOverview();
  renderVisualHeatmap();
  renderHeatmap();
  renderRankings();
  renderSignals();
  renderRelative();

  // Control visibility of the ETF Performance comparison chart based on dataset mode
  const chartPanel = document.getElementById('perfChartPanel');
  if (chartPanel) {
    if (datasetMode === 'all') {
      chartPanel.style.display = 'none';
    } else {
      chartPanel.style.display = 'block';
      // Auto-draw VOO chart on load
      runPerfChart();
    }
  }
}

// ── Category Filter Population ─────────────────────────────
function populateCategoryFilter(etfs) {
  const sel = document.getElementById('categoryFilter');
  const cats = [...new Set(etfs.map(e => e.category).filter(Boolean))].sort();
  sel.innerHTML = '<option value="">All Categories</option>';
  cats.forEach(c => {
    const opt = document.createElement('option');
    opt.value = c; opt.textContent = c;
    sel.appendChild(opt);
  });
}

// ── Filters & Sort ────────────────────────────────────────
function applyFilters() {
  if (!DATA) return;

  const q      = document.getElementById('searchInput').value.trim().toLowerCase();
  const signal = document.getElementById('signalFilter').value;
  const cat    = document.getElementById('categoryFilter').value;
  const asset  = document.getElementById('assetFilter').value;
  const sortBy = document.getElementById('sortBy').value;

  filtered = DATA.etfs.filter(e => {
    if (q && !e.symbol.toLowerCase().includes(q) && !e.name?.toLowerCase().includes(q)) return false;
    if (signal && e.signal !== signal) return false;
    if (cat   && e.category   !== cat)   return false;
    if (asset && e.asset_class !== asset) return false;
    return true;
  });

  // Dynamic sort
  filtered.sort((a, b) => {
    let va = getSortValue(a, sortCol);
    let vb = getSortValue(b, sortCol);
    if (va == null && vb == null) return 0;
    if (va == null) return 1;
    if (vb == null) return -1;
    if (typeof va === 'string') return va.localeCompare(vb) * sortDir;
    return (va - vb) * sortDir;
  });

  document.getElementById('resultsCount').textContent =
    `${filtered.length} of ${DATA.etfs.length} ETFs`;

  renderMarketBar();
  renderOverview();
  renderVisualHeatmap();
  renderHeatmap();
  renderRelative();
}

function getSortValue(e, col) {
  switch(col) {
    case 'momentum_score': return e.momentum_score;
    case 'aum':       return e.aum;
    case 'er':        return e.er;
    case 'pe':        return e.pe;
    case 'beta':      return e.beta;
    case 'alpha':     return e.alpha;
    case 'holdings':  return e.holdings;
    case 'top10_pct': return e.top10_pct;
    case 'inception': return e.inception;
    case 'category':  return e.category;
    case 'name':      return e.name;
    case 'symbol':    return e.symbol;
    case 'ret_1M':  return e.returns?.['1M'];
    case 'ret_3M':  return e.returns?.['3M'];
    case 'ret_6M':  return e.returns?.['6M'];
    case 'ret_12M': return e.returns?.['12M'];
    case 'ret_1W':  return e.returns?.['1W'];
    case 'ret_15D': return e.returns?.['15D'];
    case 'ret_2M':  return e.returns?.['2M'];
    case 'ret_9M':  return e.returns?.['9M'];
    case 'ret_2Y':  return e.returns?.['2Y'];
    case 'ret_3Y':  return e.returns?.['3Y'];
    case 'ret_5Y':  return e.returns?.['5Y'];
    case 'ret_7Y':  return e.returns?.['7Y'];
    case 'ret_10Y': return e.returns?.['10Y'];
    
    // Relative strength columns
    case 'rel_1W':  return e.vs_spy?.['1W'];
    case 'rel_1M':  return e.vs_spy?.['1M'];
    case 'rel_3M':  return e.vs_spy?.['3M'];
    case 'rel_6M':  return e.vs_spy?.['6M'];
    case 'rel_12M': return e.vs_spy?.['12M'];
    case 'rel_2Y':  return e.vs_spy?.['2Y'];
    case 'rel_3Y':  return e.vs_spy?.['3Y'];
    case 'rel_5Y':  return e.vs_spy?.['5Y'];

    default:        return null;
  }
}

function handleSortSelect() {
  const val = document.getElementById('sortBy').value;
  if (!val) return;
  sortCol = val;
  sortDir = -1;
  applyFilters();
}

function setSortCol(col) {
  if (sortCol === col) sortDir = -sortDir;
  else { sortCol = col; sortDir = -1; }
  
  const sortSelect = document.getElementById('sortBy');
  const optionExists = Array.from(sortSelect.options).some(o => o.value === col);
  if (optionExists) sortSelect.value = col;
  else sortSelect.value = ""; 

  applyFilters();
}

function toggleSortDir() {
  sortDir = -sortDir;
  applyFilters();
}

// ══════════════════════ MARKET BAR ══════════════════════════════
function renderMarketBar() {
  const container = document.getElementById('marketBar');
  const indices = DATA.market_indices || [];
  if (!indices.length) { container.style.display = 'none'; return; }
  
  container.style.display = 'grid';
  container.innerHTML = indices.map(idx => buildMarketCard(idx)).join('');
}

function buildMarketCard(idx) {
  const c1d = idx.chg_1d || 0;
  const c3m = idx.chg_3m || 0;
  const c6m = idx.chg_6m || 0;
  const c1y = idx.chg_1y || 0;

  const fmt = (v) => (v >= 0 ? '+' : '') + v.toFixed(2) + '%';
  const getCl = (v) => v >= 0 ? 'green' : 'red';
  
  return `
    <div class="market-card">
      <div class="market-name">${idx.name}</div>
      <div class="market-price-row">
        <span class="market-price">${idx.price.toLocaleString()}</span>
        <span class="market-chg-1d ${getCl(c1d)}">${fmt(c1d)} (1 day)</span>
      </div>
      <div class="market-stats-grid">
        <div class="m-stat-row">
          <div class="m-stat-sub">3M <span class="${getCl(c3m)}">${fmt(c3m)}</span></div>
          <div class="m-stat-sub">6M <span class="${getCl(c6m)}">${fmt(c6m)}</span></div>
          <div class="m-stat-sub">1Y <span class="${getCl(c1y)}">${fmt(c1y)}</span></div>
        </div>
      </div>
    </div>
  `;
}

// ══════════════════════ OVERVIEW TABLE ══════════════════════
function renderOverview() {
  const tbody = document.getElementById('overviewBody');
  const rows  = filtered.map((e, i) => buildOverviewRow(e, i + 1)).join('');
  tbody.innerHTML = rows;
  updateTableHeaders('overviewTable');
}

function buildOverviewRow(e, rank) {
  const isTop20 = datasetMode === '100' && TOP_20_TICKERS.includes(e.symbol);
  const hlClass = isTop20 ? 'top-20-highlight' : '';

  return `
    <tr class="${hlClass}">
      <td class="col-rank">${rank}</td>
      <td class="sticky-col col-ticker">
        <div class="ticker-box">
          <span class="ticker-sym">${e.symbol}</span>
        </div>
      </td>
      <td class="col-name">${e.name || '—'}</td>
      <td>${e.category || '—'}</td>
      <td>${fmtAUM(e.aum)}</td>
      <td class="mono">${e.inception || '—'}</td>
      <td class="mono">${e.pe ? e.pe.toFixed(2) : '—'}</td>
      <td class="mono">${e.beta ? e.beta.toFixed(2) : '—'}</td>
      <td class="mono">${e.holdings || '—'}</td>
      <td class="mono">${e.top10_pct ? e.top10_pct.toFixed(2) + '%' : '—'}</td>
      <td class="mono">${e.er != null ? e.er.toFixed(2) + '%' : '—'}</td>
    </tr>
  `;
}

function renderHeatmap() {
  const tbody = document.getElementById('heatmapBody');
  const rows  = filtered.map((e, i) => buildHeatRow(e, i + 1)).join('');
  tbody.innerHTML = rows;
  updateTableHeaders('heatmapTable');
}

function updateTableHeaders(tableId) {
  const btn = document.getElementById('sortDirBtn');
  if (btn) btn.textContent = sortDir === -1 ? '↓ Desc' : '↑ Asc';

  document.querySelectorAll(`#${tableId} th`).forEach(th => {
    // Strip old arrows
    th.textContent = th.textContent.replace(/ [↑↓↕]/g, '');
    const occ = th.getAttribute('onclick');
    if (occ && occ.includes(`'${sortCol}'`)) {
      th.textContent += sortDir === -1 ? ' ↓' : ' ↑';
    } else if (occ) {
      th.textContent += ' ↕';
    }
  });
}

function buildHeatRow(e, rank) {
  const rets = e.returns || {};
  const cells = PERIODS_HEATMAP.map(p => heatCell(rets[p])).join('');
  const ms    = e.momentum_score;
  const scoreClass = ms == null ? '' : ms >= 15 ? 'score-high' : ms >= 5 ? 'score-mid' : 'score-low';

  const isTop20 = datasetMode === '100' && TOP_20_TICKERS.includes(e.symbol);
  const hlClass = isTop20 ? 'top-20-highlight' : '';

  return `<tr class="${hlClass}">
    <td class="col-rank sticky-col">${rank}</td>
    <td class="col-ticker sticky-col">${e.symbol}</td>
    <td class="col-name"  title="${esc(e.name)}">${esc(e.name)}</td>
    <td class="col-cat"   title="${esc(e.category)}">${esc(e.category)}</td>
    ${cells}
    <td class="score-col ${scoreClass}">${ms != null ? ms.toFixed(2) : '—'}</td>
    <td>${signalDisplay(e.signal)}</td>
  </tr>`;
}

function heatCell(val) {
  if (val == null) return `<td class="heat-neutral">—</td>`;
  const cls = heatClass(val);
  return `<td class="${cls}">${fmtPct(val)}</td>`;
}

function heatClass(v) {
  if (v == null) return 'heat-neutral';
  if (v > 0) return 'heat-pos';
  if (v < 0) return 'heat-neg';
  return 'heat-neutral';
}

// ══════════════════════ RANKINGS TAB ════════════════════════
function renderRankings() {
  const top10    = DATA.top10    || [];
  const bottom10 = DATA.bottom10 || [];

  const header = `
    <div class="rank-card header">
      <span class="rank-num">#</span>
      <span class="rank-sym">Ticker</span>
      <span class="rank-name">ETF Name</span>
      <span class="rank-score">Score</span>
      <span class="rank-ret">3M Ret</span>
      <span class="rank-ret">1Y Ret</span>
      <span class="rank-sig">Signal</span>
    </div>`;

  document.getElementById('top10Cards').innerHTML =
    header + top10.map(r => buildRankCard(r, true)).join('');
  document.getElementById('bottom10Cards').innerHTML =
    header + bottom10.map(r => buildRankCard(r, false)).join('');
}

function buildRankCard(r, isTop) {
  const scoreColor = isTop ? 'var(--green)' : 'var(--red)';
  const r1m  = r.ret_1m  != null ? fmtPct(r.ret_1m)  : '—';
  const r3m  = r.ret_3m  != null ? fmtPct(r.ret_3m)  : '—';
  const r6m  = r.ret_6m  != null ? fmtPct(r.ret_6m)  : '—';
  const r12m = r.ret_12m != null ? fmtPct(r.ret_12m) : '—';

  const isTop20 = datasetMode === '100' && TOP_20_TICKERS.includes(r.symbol);
  const hlClass = isTop20 ? 'top-20-highlight' : '';

  return `
  <div class="rank-card ${hlClass}">
    <span class="rank-num">${r.rank}</span>
    <span class="rank-sym">${r.symbol}</span>
    <span class="rank-name" title="${esc(r.name)}">${esc(r.name)}</span>
    <span class="rank-score" style="color:${scoreColor}">${fmtScore(r.score)}</span>
    <span class="rank-ret" style="color:${r.ret_3m>=0?'var(--green)':'var(--red)'}">${r3m}</span>
    <span class="rank-ret" style="color:${r.ret_12m>=0?'var(--green)':'var(--red)'}">${r12m}</span>
    <span class="rank-sig">${signalDisplay(r.signal)}</span>
  </div>`;
}

// ══════════════════════ SIGNALS TAB ═════════════════════════
function renderSignals() {
  const etfs = DATA.etfs || [];
  // Sort: Strong first, then Neutral, then Weak
  const order = { Strong: 0, Neutral: 1, Weak: 2, 'N/A': 3 };
  const sorted = [...etfs].sort((a, b) => (order[a.signal] ?? 3) - (order[b.signal] ?? 3) || (b.momentum_score ?? -999) - (a.momentum_score ?? -999));
  const grid  = document.getElementById('signalsGrid');
  const cards = sorted.map(e => buildSignalCard(e)).join('');
  grid.innerHTML = cards;
}

function buildSignalCard(e) {
  const ms  = e.momentum_score;
  const sig = e.signal === 'Strong' ? 'strong'
            : e.signal === 'Neutral' ? 'neutral' : 'weak';
  const emoji = sig === 'strong' ? '🟢' : sig === 'neutral' ? '🟡' : '🔴';
  const scoreClass = ms == null ? 'neu' : ms >= 5 ? 'pos' : 'neg';
  const r1m  = e.returns?.['1M'];
  const r3m  = e.returns?.['3M'];
  const r12m = e.returns?.['12M'];

  const isTop20 = datasetMode === '100' && TOP_20_TICKERS.includes(e.symbol);
  const hlClass = isTop20 ? 'top-20-highlight' : '';

  return `
  <div class="signal-card sig-${sig} ${hlClass}">
    <div class="sig-top">
      <span class="sig-ticker">${e.symbol}</span>
      <span class="sig-emoji">${emoji}</span>
    </div>
    <div class="sig-name" title="${esc(e.name)}">${esc(e.name)}</div>
    <div class="sig-score ${scoreClass}">${ms != null ? ms.toFixed(1) : '—'}</div>
    <div class="sig-meta">
      <span class="sig-micro ${r1m!=null&&r1m>=0?'pos':r1m!=null?'neg':''}">1M ${r1m!=null?fmtPct(r1m):'—'}</span>
      <span class="sig-micro ${r3m!=null&&r3m>=0?'pos':r3m!=null?'neg':''}">3M ${r3m!=null?fmtPct(r3m):'—'}</span>
      <span class="sig-micro ${r12m!=null&&r12m>=0?'pos':r12m!=null?'neg':''}">12M ${r12m!=null?fmtPct(r12m):'—'}</span>
    </div>
  </div>`;
}

// ══════════════════════ RELATIVE STRENGTH TAB ═══════════════
function renderRelative() {
  const tbody = document.getElementById('relBody');
  const rows  = filtered.map((e, i) => buildRelRow(e, i + 1)).join('');
  tbody.innerHTML = rows;
  updateTableHeaders('relTable');
}

function buildRelRow(e, rank) {
  const vs  = e.vs_spy || {};
  const ms  = e.momentum_score;
  const scoreClass = ms == null ? '' : ms >= 15 ? 'score-high' : ms >= 5 ? 'score-mid' : 'score-low';

  const cells = PERIODS_REL.map(p => {
    const v = vs[p];
    if (v == null) return `<td class="heat-neutral">—</td>`;
    return `<td class="${heatClass(v)}">${fmtPct(v)}</td>`;
  }).join('');

  const isTop20 = datasetMode === '100' && TOP_20_TICKERS.includes(e.symbol);
  const hlClass = isTop20 ? 'top-20-highlight' : '';

  return `<tr class="${hlClass}">
    <td class="col-rank sticky-col">${rank}</td>
    <td class="col-ticker sticky-col">${e.symbol}</td>
    <td class="col-name" title="${esc(e.name)}">${esc(e.name)}</td>
    ${cells}
    <td class="score-col ${scoreClass}">${ms != null ? ms.toFixed(2) : '—'}</td>
    <td>${signalDisplay(e.signal)}</td>
  </tr>`;
}

// ══════════════════════ TABS ════════════════════════════════
function bindTabs() {
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const tab = btn.dataset.tab;
      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
      btn.classList.add('active');
      document.getElementById('tab-' + tab).classList.add('active');
      activeTab = tab;
    });
  });

  // Visual Heatmap controls
  document.querySelectorAll('.vh-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.vh-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      vhPeriod = btn.dataset.period;
      renderVisualHeatmap();
    });
  });
}

// ══════════════════════ VISUAL HEATMAP ══════════════════════
function renderVisualHeatmap() {
  const container = document.querySelector('.visual-heatmap-container');
  if (!container) return;

  if (datasetMode === 'all') {
    container.style.display = 'none';
    return;
  }
  
  container.style.display = 'block';

  if (!DATA || !DATA.etfs) return;
  const grid = document.getElementById('visualHeatmapGrid');
  if (!grid) return;

  // Clone and sort by the selected period return
  const sorted = [...DATA.etfs].sort((a, b) => {
    let va, vb;
    if (vhPeriod === 'momentum_score') {
      va = a.momentum_score ?? -9999;
      vb = b.momentum_score ?? -9999;
    } else {
      va = a.returns?.[vhPeriod] ?? -9999;
      vb = b.returns?.[vhPeriod] ?? -9999;
    }
    return vb - va; // highest to lowest
  });

  grid.innerHTML = sorted.map(e => {
    let val, disp;
    if (vhPeriod === 'momentum_score') {
      val = e.momentum_score;
      disp = fmtScore(val);
    } else {
      val = e.returns?.[vhPeriod];
      disp = fmtPct(val);
    }
    
    const bgClass = heatClass(val);
    
    return `
      <div class="heatmap-tile ${bgClass}">
        <div class="vh-top">
          <span class="vh-ticker">${e.symbol}</span>
          <span class="vh-ret">${disp}</span>
        </div>
        <div class="vh-sector" title="${esc(e.category)}">${esc(e.category || 'Unknown')}</div>
        <div class="vh-name" title="${esc(e.name)}">${esc(e.name || '')}</div>
      </div>
    `;
  }).join('');
}

function switchDataset(mode) {
  if (datasetMode === mode) return;
  datasetMode = mode;
  document.getElementById('ds100').classList.toggle('active', mode === '100');
  document.getElementById('dsAll').classList.toggle('active', mode === 'all');
  loadData();
}

// ══════════════════════ HELPERS ═════════════════════════════
function fmtAUM(v) {
  if (!v) return '—';
  if (v >= 1e12) return '$' + (v / 1e12).toFixed(2) + 'T';
  if (v >= 1e9)  return '$' + (v / 1e9).toFixed(2) + 'B';
  if (v >= 1e6)  return '$' + (v / 1e6).toFixed(2) + 'M';
  return '$' + v.toLocaleString();
}

function fmtPct(v) {
  if (v == null) return '—';
  const sign = v >= 0 ? '+' : '';
  return sign + v.toFixed(2) + '%';
}

function fmtScore(v) {
  if (v == null) return '—';
  const sign = v >= 0 ? '+' : '';
  return sign + v.toFixed(2);
}

function signalDisplay(sig) {
  if (!sig || sig === 'N/A') return 'N/A';
  if (sig === 'Strong') return '🟢 Strong';
  if (sig === 'Neutral') return '🟡 Neutral';
  if (sig === 'Weak')   return '🔴 Weak';
  return sig;
}

function colorizeVal(el, v) {
  if (v == null) return;
  el.style.color = v >= 0 ? 'var(--green)' : 'var(--red)';
}

function setStatVal(id, val, colorClass) {
  const el = document.querySelector(`#${id} .stat-value`);
  if (!el) return;
  el.textContent = val;
  el.className = 'stat-value' + (colorClass ? ' ' + colorClass : '');
}

function esc(str) {
  if (!str) return '';
  return str.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function showLoading(show) {
  document.getElementById('loadingOverlay').style.display = show ? 'flex' : 'none';
}

function showError()  { document.getElementById('errorOverlay').style.display = 'flex'; }
function hideError()  { document.getElementById('errorOverlay').style.display = 'none'; }

// ══════════════════════ PERFORMANCE COMPARISON CHART ════════════════════════
let HIST_DATA  = null;
let perfChart  = null;
let CURRENT_TIMEFRAME = '1Y'; // Default timeframe

// Fetch history.json once and cache it
async function loadHistData() {
  if (HIST_DATA) return HIST_DATA;
  try {
    const res  = await fetch('history.json?nocache=' + Date.now());
    if (!res.ok) throw new Error('history.json not found');
    HIST_DATA = await res.json();
    return HIST_DATA;
  } catch(e) {
    console.error('loadHistData error:', e);
    return null;
  }
}

// Curated colour palette for lines (VOO first = green)
const PERF_COLORS = [
  '#43a047', // VOO — green
  '#1565c0', // slot 1 — royal blue
  '#e65100', // slot 2 — deep orange
  '#6a1b9a', // slot 3 — purple
  '#00838f', // slot 4 — teal
  '#c62828', // slot 5 — crimson
];

// Set active timeframe and toggle inputs if 'custom' is selected
async function setChartTimeframe(tf) {
  CURRENT_TIMEFRAME = tf;

  // Toggle active class on buttons
  const buttons = document.querySelectorAll('.perf-tf-btn');
  buttons.forEach(btn => btn.classList.remove('active'));
  
  const activeBtn = document.getElementById(`tf-${tf}`);
  if (activeBtn) activeBtn.classList.add('active');

  const customDatesDiv = document.getElementById('perfCustomDates');
  if (tf === 'custom') {
    customDatesDiv.style.display = 'flex';
    // Initialize dates if empty
    const hist = await loadHistData();
    if (hist && hist.dates.length > 0) {
      const lastDate = hist.dates[hist.dates.length - 1];
      const fromDateInput = document.getElementById('perfFromDate');
      const toDateInput = document.getElementById('perfToDate');
      
      // Default to 1 Year range
      const defaultFrom = new Date(new Date(lastDate).getTime() - 365 * 24 * 60 * 60 * 1000).toISOString().split('T')[0];
      
      fromDateInput.value = fromDateInput.value || defaultFrom;
      toDateInput.value = toDateInput.value || lastDate;
      
      fromDateInput.min = hist.dates[0];
      fromDateInput.max = lastDate;
      toDateInput.min = hist.dates[0];
      toDateInput.max = lastDate;
    }
  } else {
    customDatesDiv.style.display = 'none';
  }

  runPerfChart();
}

async function runPerfChart() {
  const footer = document.getElementById('perfChartFooter');
  footer.innerHTML = '<span class="perf-error" style="color:#6b7a99">Loading chart data…</span>';

  const hist = await loadHistData();
  if (!hist) {
    footer.innerHTML = '<span class="perf-error">⚠️ history.json not available. Run data_engine.py first.</span>';
    return;
  }

  // Determine date slicing indices based on timeframe
  const dates = hist.dates;
  let startIdx = 0;
  let endIdx = dates.length - 1;

  if (CURRENT_TIMEFRAME === 'custom') {
    const fromVal = document.getElementById('perfFromDate').value;
    const toVal = document.getElementById('perfToDate').value;
    if (fromVal) {
      const idx = dates.findIndex(d => d >= fromVal);
      if (idx !== -1) startIdx = idx;
    }
    if (toVal) {
      let idx = -1;
      for (let i = dates.length - 1; i >= 0; i--) {
        if (dates[i] <= toVal) {
          idx = i;
          break;
        }
      }
      if (idx !== -1) endIdx = idx;
    }
  } else {
    let days = 365;
    if (CURRENT_TIMEFRAME === '1M') days = 30;
    else if (CURRENT_TIMEFRAME === '3M') days = 90;
    else if (CURRENT_TIMEFRAME === '6M') days = 180;
    else if (CURRENT_TIMEFRAME === '1Y') days = 365;
    else if (CURRENT_TIMEFRAME === '3Y') days = 3 * 365;
    else if (CURRENT_TIMEFRAME === '5Y') days = 5 * 365;

    const lastDateStr = dates[dates.length - 1];
    const lastDate = new Date(lastDateStr);
    const targetDate = new Date(lastDate.getTime() - days * 24 * 60 * 60 * 1000);
    const targetStr = targetDate.toISOString().split('T')[0];

    const idx = dates.findIndex(d => d >= targetStr);
    if (idx !== -1) startIdx = idx;
  }

  if (startIdx >= endIdx) {
    startIdx = Math.max(0, endIdx - 5); // Fallback: show at least 5 days
  }

  const slicedLabels = dates.slice(startIdx, endIdx + 1);

  // Collect user inputs (uppercased, trimmed, deduplicated)
  const userTickers = ['perf1','perf2','perf3','perf4','perf5']
    .map(id => document.getElementById(id).value.trim().toUpperCase())
    .filter(t => t.length > 0);
  const unique = [...new Set(userTickers)].slice(0, 5);

  // Always include VOO as fixed anchor
  const allTickers = ['VOO', ...unique.filter(t => t !== 'VOO')];
  const datasets = [];
  const missing  = [];

  allTickers.forEach((ticker, i) => {
    const series = hist.series[ticker];
    if (!series) { missing.push(ticker); return; }
    
    // Slice series data
    const rawSlice = series.slice(startIdx, endIdx + 1);
    
    // Re-normalise to start at 0 (percentage return) on the first day of the slice
    const baseVal = rawSlice[0];
    if (baseVal === undefined || baseVal === 0) {
      missing.push(ticker);
      return;
    }
    const normalizedSlice = rawSlice.map(v => Number(((v / baseVal - 1) * 100).toFixed(4)));
    const color = PERF_COLORS[i] || PERF_COLORS[PERF_COLORS.length - 1];
    
    datasets.push({
      label:           ticker,
      data:            normalizedSlice,
      borderColor:     color,
      backgroundColor: color + '18',
      borderWidth:     ticker === 'VOO' ? 2.5 : 2,
      pointRadius:     0,
      pointHitRadius:  12,
      tension:         0.3,
      fill:            false,
    });
  });

  if (datasets.length === 0) {
    footer.innerHTML = '<span class="perf-error">⚠️ None of the entered tickers were found in history data.</span>';
    return;
  }

  // Destroy existing chart if any
  if (perfChart) { perfChart.destroy(); perfChart = null; }

  const isLight = document.body.classList.contains('light-theme');
  const tickColor = isLight ? '#475569' : '#8898aa';
  const gridColor = isLight ? 'rgba(0,0,0,0.08)' : 'rgba(255,255,255,0.06)';

  const ctx = document.getElementById('perfChartCanvas').getContext('2d');
  perfChart = new Chart(ctx, {
    type: 'line',
    data: { labels: slicedLabels, datasets },
    options: {
      responsive: true,
      maintainAspectRatio: true,
      aspectRatio: 3.2,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: isLight ? '#ffffff' : '#1a1f2e',
          borderColor:     isLight ? '#dde2ea' : 'rgba(255,255,255,0.08)',
          borderWidth:     1,
          titleColor:      isLight ? '#0f172a' : '#f0f2ff',
          bodyColor:       isLight ? '#334155' : '#8b9ab5',
          padding:         12,
          cornerRadius:    10,
          boxShadow:       '0 4px 20px rgba(0,0,0,0.12)',
          callbacks: {
            title: items => `📅 ${items[0].label}`,
            label: item => {
              const val = item.raw != null ? item.raw.toFixed(2) : '—';
              const sign = item.raw > 0 ? '+' : '';
              return ` ${item.dataset.label}: ${sign}${val}%`;
            }
          }
        }
      },
      scales: {
        x: {
          ticks: {
            maxTicksLimit: 12,
            color: tickColor,
            font: { size: 11 }
          },
          grid: { color: gridColor }
        },
        y: {
          ticks: {
            color: tickColor,
            font: { size: 11 },
            callback: v => (v >= 0 ? '+' : '') + v.toFixed(0) + '%'
          },
          grid:  { color: gridColor },
          title: { display: true, text: 'Return (%)', color: tickColor, font: { size: 11 } }
        }
      }
    }
  });

  // Render legend at bottom
  const legendHTML = datasets.map(ds =>
    `<span class="perf-legend-item" style="color: var(--text-secondary)">
       <span class="perf-legend-dot" style="background:${ds.borderColor}"></span>
       ${ds.label}
     </span>`
  ).join('');
  const missingNote = missing.length
    ? `<span class="perf-error" style="margin-left:auto">Not found: ${missing.join(', ')}</span>`
    : '';
  footer.innerHTML = legendHTML + missingNote;

  // Allow Enter key in inputs
  ['perf1','perf2','perf3','perf4','perf5'].forEach(id => {
    document.getElementById(id).onkeydown = e => { if (e.key === 'Enter') runPerfChart(); };
  });
}

// ── Theme Switcher Logic ─────────────────────────────────────────────────────
function initTheme() {
  const savedTheme = localStorage.getItem('dashboard_theme') || 'dark';
  const isLight = savedTheme === 'light';
  
  document.body.classList.toggle('light-theme', isLight);
  updateThemeButton(isLight);
}

function toggleTheme() {
  const isLight = document.body.classList.toggle('light-theme');
  localStorage.setItem('dashboard_theme', isLight ? 'light' : 'dark');
  updateThemeButton(isLight);
  
  // Re-run perf chart so the canvas styles, gridlines and scale colors redraw instantly
  const chartPanel = document.getElementById('perfChartPanel');
  if (chartPanel && chartPanel.style.display !== 'none') {
    runPerfChart();
  }
}

function updateThemeButton(isLight) {
  const btn = document.getElementById('themeToggleBtn');
  if (btn) {
    btn.innerHTML = isLight ? '🌙 Black Mode' : '☀️ Light Mode';
  }
}

// Call theme initialization on load
initTheme();



