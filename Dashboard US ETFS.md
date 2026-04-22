
You want a **momentum dashboard** that:

-   Tracks ~100 ETFs
    
-   Calculates **multi-timeframe returns**
    
-   Displays them visually (heatmap / ranking / signals)
    

This is essentially a **relative strength + momentum screener**.

* * *

# ⚙️ Should You Use Google Sheets Alone or Apps Script?

### ✅ Use BOTH (best setup)

-   **Google Sheets** → Data display, formulas, dashboard
    
-   **Apps Script** → Data fetching + automation
    

### ❌ Avoid Sheets-only approach

Using only `GOOGLEFINANCE()` will:

-   Break for long lookbacks (like 7Y, 10Y)
    
-   Be inconsistent for ETFs
    
-   Be slow with 100 tickers × many formulas
    

👉 So yes — **Apps Script is the right move**

* * *

# 🏗️ Architecture (Recommended Setup)

## 1\. Data Layer (Raw Prices)

Sheet: `DATA`

You want:

Date | ETF1 | ETF2 | ETF3 ... ETF100

Populate using:

-   Apps Script (preferred)
    
-   Or APIs like:
    
    -   Yahoo Finance
        
    -   Alpha Vantage
        
    -   Twelve Data
        

👉 Store **daily close prices**

* * *

## 2\. Return Engine (Core Calculations)

Sheet: `RETURNS`

For each ETF, compute:

ETF

1W

15D

1M

2M

3M

6M

9M

12M

2Y

3Y

5Y

7Y

10Y

Formula concept:

Return = (Current Price / Past Price) - 1

Example:

\= (TODAY\_PRICE / PRICE\_5\_DAYS\_AGO) - 1

* * *

## 3\. Dashboard Layer (Visualization)

Sheet: `DASHBOARD`

This is where things get interesting:

### 🔥 Must-have visuals:

-   Heatmap (green = strong, red = weak)
    
-   Ranking table (top momentum ETFs)
    
-   Momentum score (weighted)
    

* * *

# 📊 Momentum Scoring Idea (Important)

Instead of just raw returns, create a **composite score**:

Example:

Momentum Score =  
(1M \* 0.2) +  
(3M \* 0.3) +  
(6M \* 0.3) +  
(12M \* 0.2)

👉 This smooths noise and gives better signals

* * *

# 🧑‍💻 Apps Script (Core Advantage)

Use Apps Script to:

### 1\. Fetch Historical Prices

Example (Yahoo Finance style):

JavaScript

function fetchETFData() {  
  const tickers \= \["SPY", "QQQ", "IWM"\]; // extend to 100  
  const sheet \= SpreadsheetApp.getActiveSpreadsheet().getSheetByName("DATA");  
  
  tickers.forEach((ticker, i) => {  
    const url \= \`https://query1.finance.yahoo.com/v8/finance/chart/${ticker}?range=10y&interval=1d\`;  
    const response \= UrlFetchApp.fetch(url);  
    const data \= JSON.parse(response.getContentText());  
  
    const prices \= data.chart.result\[0\].indicators.quote\[0\].close;  
  
    for (let j \= 0; j < prices.length; j++) {  
      sheet.getRange(j + 2, i + 2).setValue(prices\[j\]);  
    }  
  });  
}

* * *

### 2\. Automate Updates

-   Set trigger: daily / hourly
    
-   Keeps dashboard fresh
    

* * *

# ⚡ Performance Tips (VERY IMPORTANT)

With 100 ETFs × 10+ timeframes:

### Avoid:

-   Thousands of volatile formulas
    
-   Repeated VLOOKUPs
    

### Use:

-   Helper columns
    
-   Cached values (Apps Script writes data once)
    
-   Array formulas
    

* * *

# 🎨 Visualization Ideas

### 1\. Heatmap Table

-   Use conditional formatting
    
-   Color scale:
    
    -   Red → Negative
        
    -   Yellow → Neutral
        
    -   Green → Strong
        

* * *

### 2\. Momentum Ranking

Sort ETFs by:

-   3M return
    
-   or composite score
    

* * *

### 3\. Trend Signals

Add simple labels:

-   🟢 Strong → top quartile
    
-   🟡 Neutral
    
-   🔴 Weak → bottom quartile
    

* * *

# 🧠 Advanced Ideas (Optional but Powerful)

### 📈 Relative Strength vs Benchmark

Compare each ETF vs SPY:

ETF Return - SPY Return

* * *


    



# 🏗️ STEP 1 — GOOGLE SHEET STRUCTURE

Create **4 tabs exactly like this:**

### 1️⃣ `TICKERS`

A1: ETF  
A2: SPY  
A3: QQQ  
A4: IWM  
...  
(up to your 100 ETFs)

* * *

### 2️⃣ `DATA` (Raw price history)

A1: Date  
B1: SPY  
C1: QQQ  
...

👉 This will store **daily close prices (10 years)**

* * *

### 3️⃣ `RETURNS` (Core engine)

A1: ETF  
B1: 1W  
C1: 15D  
D1: 1M  
E1: 2M  
F1: 3M  
G1: 6M  
H1: 9M  
I1: 12M  
J1: 2Y  
K1: 3Y  
L1: 5Y  
M1: 7Y  
N1: 10Y  
O1: MOMENTUM SCORE

* * *

### 4️⃣ `DASHBOARD`

This is your **visual layer**

-   Heatmap
    
-   Rankings
    
-   Signals
    

* * *

# ⚙️ STEP 2 — APPS SCRIPT (CORE ENGINE)

👉 Go to:  
**Extensions → Apps Script**

Paste this FULL script:

JavaScript

function fetchETFData() {  
  const sheet \= SpreadsheetApp.getActiveSpreadsheet().getSheetByName("DATA");  
  const tickersSheet \= SpreadsheetApp.getActiveSpreadsheet().getSheetByName("TICKERS");  
  
  const tickers \= tickersSheet.getRange("A2:A").getValues().flat().filter(String);  
  
  const today \= Math.floor(Date.now() / 1000);  
  const tenYearsAgo \= today \- (10 \* 365 \* 24 \* 60 \* 60);  
  
  // Clear old data  
  sheet.clear();  
  
  // Headers  
  sheet.getRange(1,1).setValue("Date");  
  tickers.forEach((t, i) => sheet.getRange(1, i+2).setValue(t));  
  
  let allPrices \= \[\];  
  
  tickers.forEach((ticker, colIndex) => {  
    const url \= \`https://query1.finance.yahoo.com/v8/finance/chart/${ticker}?period1=${tenYearsAgo}&period2=${today}&interval=1d\`;  
      
    const response \= UrlFetchApp.fetch(url);  
    const data \= JSON.parse(response.getContentText());  
  
    const timestamps \= data.chart.result\[0\].timestamp;  
    const prices \= data.chart.result\[0\].indicators.quote\[0\].close;  
  
    timestamps.forEach((ts, i) => {  
      const date \= new Date(ts \* 1000);  
  
      if (!allPrices\[i\]) {  
        allPrices\[i\] \= \[\];  
        allPrices\[i\]\[0\] \= date;  
      }  
  
      allPrices\[i\]\[colIndex + 1\] \= prices\[i\];  
    });  
  });  
  
  // Write all data at once (IMPORTANT for speed)  
  sheet.getRange(2,1,allPrices.length, allPrices\[0\].length).setValues(allPrices);  
}

* * *

## ⏱️ Add Automation (VERY IMPORTANT)

In Apps Script:

-   Click **Triggers**
    
-   Add trigger:
    
    -   Function: `fetchETFData`
        
    -   Frequency: **Daily**
        

👉 This avoids rate limits and slow sheets Stack Overflow

* * *

# 📊 STEP 3 — RETURNS CALCULATION

Inside `RETURNS`

### A2:

\=TICKERS!A2

* * *

## 🔑 Core Formula Template

Example for **1 Month Return (D2):**

\=INDEX(DATA!B:B, MATCH(TODAY(), DATA!A:A, 1)) /  
 INDEX(DATA!B:B, MATCH(TODAY()-30, DATA!A:A, 1)) - 1

* * *

## 🧠 Map periods like this:

Label

Days

1W

5

15D

15

1M

21

2M

42

3M

63

6M

126

9M

189

12M

252

2Y

504

3Y

756

5Y

1260

7Y

1764

10Y

2520

👉 Replace `30` with these values

* * *

# 🧠 STEP 4 — MOMENTUM SCORE (IMPORTANT EDGE)

In column O:

\= (D2\*0.2) + (F2\*0.3) + (G2\*0.3) + (I2\*0.2)

👉 This emphasizes:

-   Medium-term trends
    
-   Avoids short-term noise
    

* * *

# 🎨 STEP 5 — DASHBOARD (THIS IS WHERE IT GETS POWERFUL)

## 1️⃣ Heatmap Table

-   Select RETURNS table
    
-   Format → Conditional formatting
    
-   Color scale:
    
    -   Red = -10%
        
    -   Yellow = 0%
        
    -   Green = +10%
        

* * *

## 2️⃣ Ranking Table

\=SORT(RETURNS!A2:O101, 15, FALSE)

👉 Sort by momentum score

* * *

## 3️⃣ Top 5 ETFs

\=INDEX(SORT(RETURNS!A2:O101,15,FALSE), SEQUENCE(5), {1,15})

* * *

# 🚀 STEP 6 — OPTIONAL (BUT HIGHLY RECOMMENDED)

## 📈 Relative Strength vs SPY

Add column:

\= ETF\_RETURN - SPY\_RETURN

* * *

## 🔥 Momentum Signals

\=IF(O2>0.15,"🟢 Strong",  
 IF(O2>0.05,"🟡 Neutral","🔴 Weak"))

* * *

# ⚠️ KEY INSIGHTS (FROM REAL-WORLD USE)

From multiple implementations of this type of system:

-   Apps Script batching is critical to avoid rate limits Stack Overflow
    
-   `GOOGLEFINANCE()` is unreliable for ETFs & long history Medium
    
-   Momentum systems work best with **3–12 month weighting** Medium
    

