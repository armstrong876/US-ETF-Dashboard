/**
 * US ETF Momentum Dashboard - Google Sheets Script
 * ------------------------------------------------
 * Instructions:
 * 1. Open a new Google Sheet.
 * 2. Go to Extensions > Apps Script.
 * 3. Paste this code and save.
 * 4. Run the 'initializeDashboard' function.
 */

const TICKERS = [
  "QQQ", "XLP", "GLD", "XLY", "VOO", "SMH", "URA", "AIQ", "CIBR", "REMX",
  "BOTZ", "UFO", "SKYY", "PPA", "ESPO", "OZEM", "PJP", "SLV", "FNGS", "BBP",
  "SPY", "XLE", "XLF", "IWM", "EWZ", "FXI", "GDX", "IEFA", "IAU", "XLI",
  "VWO", "EWJ", "INDA", "IVV", "SOXX", "EWT", "ACWI", "IVW", "VGK", "MCHI",
  "IWD", "SIL", "SPMD", "IWF", "SPSM", "EWG", "EWU", "IHI", "EZU", "SDVY",
  "IBB", "DBC", "FTXO", "CQQQ", "SPTM", "IXC", "VFH", "XLV", "XLK", "XLU",
  "XLC", "XLB", "XRT", "ITA", "KBE", "KRE", "VNQ", "IYR", "SCHD", "DVY",
  "VYM", "TLT", "IEF", "SHY", "LQD", "HYG", "TIP", "EMB", "VIG", "NOBL"
];

function onOpen() {
  const ui = SpreadsheetApp.getUi();
  ui.createMenu('🚀 ETF Dashboard')
      .addItem('Refresh Data', 'refreshETFData')
      .addItem('Setup Dashboard', 'initializeDashboard')
      .addToUi();
}

function initializeDashboard() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  let sheet = ss.getSheetByName('ETF Momentum');
  if (!sheet) {
    sheet = ss.insertSheet('ETF Momentum');
  }
  
  sheet.clear();
  
  // Headers
  const headers = [['Ticker', 'Name', 'Price', '1W Ret', '1M Ret', '3M Ret', '6M Ret', '1Y Ret', 'Momentum Score']];
  sheet.getRange(1, 1, 1, headers[0].length).setValues(headers)
       .setBackground('#1a1f2e').setFontColor('white').setFontWeight('bold');
  
  // Fill Tickers
  const tickerData = TICKERS.map(t => [t]);
  sheet.getRange(2, 1, TICKERS.length, 1).setValues(tickerData);
  
  // Formulas
  for (let i = 0; i < TICKERS.length; i++) {
    const row = i + 2;
    // Name
    sheet.getRange(row, 2).setFormula(`=GOOGLEFINANCE(A${row}, "name")`);
    // Price
    sheet.getRange(row, 3).setFormula(`=GOOGLEFINANCE(A${row}, "price")`);
    
    // Returns calculation (Simplified for Sheet formulas)
    // 1W, 1M, 3M, 6M, 1Y
    sheet.getRange(row, 4).setFormula(`=(C${row}/INDEX(GOOGLEFINANCE(A${row}, "price", TODAY()-7, TODAY()), 2, 2))-1`);
    sheet.getRange(row, 5).setFormula(`=(C${row}/INDEX(GOOGLEFINANCE(A${row}, "price", TODAY()-30, TODAY()), 2, 2))-1`);
    sheet.getRange(row, 6).setFormula(`=(C${row}/INDEX(GOOGLEFINANCE(A${row}, "price", TODAY()-90, TODAY()), 2, 2))-1`);
    sheet.getRange(row, 7).setFormula(`=(C${row}/INDEX(GOOGLEFINANCE(A${row}, "price", TODAY()-180, TODAY()), 2, 2))-1`);
    sheet.getRange(row, 8).setFormula(`=(C${row}/INDEX(GOOGLEFINANCE(A${row}, "price", TODAY()-365, TODAY()), 2, 2))-1`);
    
    // Momentum Score: (1M*0.2 + 3M*0.3 + 6M*0.3 + 12M*0.2) * 100
    sheet.getRange(row, 9).setFormula(`=(E${row}*0.2 + F${row}*0.3 + G${row}*0.3 + H${row}*0.2)*100`);
  }
  
  // Formatting
  sheet.getRange(2, 4, TICKERS.length, 5).setNumberFormat('0.0%');
  sheet.getRange(2, 9, TICKERS.length, 1).setNumberFormat('0.0');
  
  // Heatmap Conditional Formatting
  const range = sheet.getRange(2, 4, TICKERS.length, 5);
  const rule = SpreadsheetApp.newConditionalFormatRule()
      .setGradientMaxColorValue('#22c55e')
      .setGradientMidColorValue('#ffffff')
      .setGradientMinColorValue('#ef4444')
      .setRanges([range])
      .build();
  
  const rules = sheet.getConditionalFormatRules();
  rules.push(rule);
  sheet.setConditionalFormatRules(rules);
  
  SpreadsheetApp.getUi().alert('Dashboard Initialized! Formulas will take a moment to load.');
}

function refreshETFData() {
  // Since we use GOOGLEFINANCE formulas, we just need to "poke" the sheet to refresh
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const sheet = ss.getSheetByName('ETF Momentum');
  if (sheet) {
    sheet.getRange('A1').setValue('Ticker '); // Tiny change to trigger refresh
    SpreadsheetApp.flush();
    sheet.getRange('A1').setValue('Ticker');
  }
}
