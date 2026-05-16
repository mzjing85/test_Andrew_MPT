import json
import threading
import webview

# Import the core functions from the CLI module
from Rebalancer import (
    set_portfolio,
    get_current_prices,
    check_rebalance,
    execute_rebalance,
    execute_transaction,
    set_portfolio_weight_change,
    get_rebalance_recommendations,
)


class Api:
    def __init__(self):
        self.threshold = 5.0

    def set_portfolio(self, holdings_json: str):
        """Accept JSON mapping ticker -> [quantity, target_weight] or {ticker: [q,w]}"""
        try:
            data = json.loads(holdings_json)
            holdings = {}
            for k, v in data.items():
                if isinstance(v, (list, tuple)) and len(v) >= 2:
                    qty = float(v[0])
                    wt = float(v[1])
                elif isinstance(v, dict) and "quantity" in v and "weight" in v:
                    qty = float(v["quantity"])
                    wt = float(v["weight"])
                else:
                    return {"error": f"invalid value for {k}, expected [quantity, weight]"}
                holdings[k.upper()] = (qty, wt)

            set_portfolio(holdings)
            return {"ok": True, "portfolio": {k: list(v) for k, v in holdings.items()}}
        except Exception as e:
            return {"error": str(e)}

    def get_prices(self, tickers_csv: str):
        try:
            tickers = [t.strip().upper() for t in tickers_csv.split(",") if t.strip()]
            prices = get_current_prices(tickers)
            return {"prices": prices}
        except Exception as e:
            return {"error": str(e)}

    def check_rebalance(self, threshold: float = None):
        try:
            thr = self.threshold if threshold is None else float(threshold)
            return check_rebalance(threshold=thr)
        except Exception as e:
            return {"error": str(e)}

    def execute_rebalance(self):
        try:
            txns = execute_rebalance(record=True)
            return {"transactions": txns}
        except Exception as e:
            return {"error": str(e)}

    def execute_transaction(self, ticker: str, action: str, shares: float, price: float = None):
        try:
            tx = execute_transaction(
                ticker=ticker,
                action=action,
                shares=float(shares),
                price=(float(price) if price else None),
                record=True,
            )
            return {"transaction": tx}
        except Exception as e:
            return {"error": str(e)}

    def set_weights(self, weights_json: str):
        try:
            data = json.loads(weights_json)
            set_portfolio_weight_change(data)
            return {"ok": True}
        except Exception as e:
            return {"error": str(e)}

    def set_threshold(self, thr: float):
        try:
            t = float(thr)
            if not (0 <= t < 100):
                return {"error": "threshold must be >=0 and <100"}
            self.threshold = t
            return {"ok": True, "threshold": self.threshold}
        except Exception as e:
            return {"error": str(e)}


HTML = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Portfolio Rebalancer</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=DM+Mono:wght@300;400;500&family=DM+Sans:wght@300;400;500;600&display=swap" rel="stylesheet">
  <style>
    /* ── Design tokens ─────────────────────────────────────────── */
    :root {
      --bg:        #0d0f14;
      --surface:   #13161e;
      --surface2:  #1a1e29;
      --border:    #232839;
      --border2:   #2d3348;
      --text:      #e8eaf0;
      --muted:     #6b7190;
      --accent:    #c9a84c;
      --accent2:   #e8c97a;
      --green:     #3ddc97;
      --red:       #f06070;
      --blue:      #5b8af5;
      --radius:    10px;
      --radius-sm: 6px;
      --shadow:    0 4px 24px rgba(0,0,0,.45);
    }

    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    html, body { height: 100%; }
    body {
      background: var(--bg);
      color: var(--text);
      font-family: 'DM Sans', sans-serif;
      font-size: 14px;
      line-height: 1.6;
      display: flex;
      flex-direction: column;
    }

    /* ── Top bar ───────────────────────────────────────────────── */
    .topbar {
      display: flex;
      align-items: center;
      gap: 14px;
      padding: 0 28px;
      height: 58px;
      background: var(--surface);
      border-bottom: 1px solid var(--border);
      flex-shrink: 0;
    }
    .topbar-logo {
      font-family: 'DM Serif Display', serif;
      font-size: 20px;
      color: var(--accent);
      letter-spacing: .5px;
    }
    .topbar-logo span { color: var(--text); }
    .topbar-divider { width: 1px; height: 24px; background: var(--border2); }
    .topbar-subtitle { color: var(--muted); font-size: 12.5px; font-weight: 300; }
    .topbar-spacer { flex: 1; }
    .topbar-status {
      font-size: 12px;
      color: var(--muted);
      font-family: 'DM Mono', monospace;
      display: flex;
      align-items: center;
      gap: 7px;
    }
    .status-dot {
      width: 7px; height: 7px;
      border-radius: 50%;
      background: var(--muted);
      transition: background .4s;
    }
    .status-dot.ok   { background: var(--green); }
    .status-dot.err  { background: var(--red); }
    .status-dot.busy { background: var(--accent); animation: pulse 1s infinite; }
    @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.3} }

    /* ── Layout ────────────────────────────────────────────────── */
    .layout {
      display: flex;
      flex: 1;
      min-height: 0;
      overflow: hidden;
    }

    /* ── Sidebar nav ───────────────────────────────────────────── */
    .sidebar {
      width: 200px;
      background: var(--surface);
      border-right: 1px solid var(--border);
      display: flex;
      flex-direction: column;
      padding: 18px 0;
      flex-shrink: 0;
    }
    .nav-section-label {
      font-size: 10px;
      font-weight: 600;
      letter-spacing: 1.4px;
      text-transform: uppercase;
      color: var(--muted);
      padding: 0 20px 8px;
      margin-top: 8px;
    }
    .nav-item {
      display: flex;
      align-items: center;
      gap: 10px;
      padding: 9px 20px;
      cursor: pointer;
      border-left: 3px solid transparent;
      font-size: 13.5px;
      font-weight: 400;
      color: var(--muted);
      transition: all .18s;
      user-select: none;
    }
    .nav-item:hover { color: var(--text); background: var(--surface2); }
    .nav-item.active {
      color: var(--accent);
      border-left-color: var(--accent);
      background: rgba(201,168,76,.07);
      font-weight: 500;
    }
    .nav-icon { font-size: 15px; opacity: .85; width: 18px; text-align: center; }

    /* ── Main content ──────────────────────────────────────────── */
    .main {
      flex: 1;
      overflow-y: auto;
      padding: 28px 32px;
      display: flex;
      flex-direction: column;
      gap: 22px;
    }

    /* ── Panel cards ───────────────────────────────────────────── */
    .panel {
      display: none;
      flex-direction: column;
      gap: 22px;
    }
    .panel.active { display: flex; }

    .card {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: 22px 24px;
      box-shadow: var(--shadow);
    }
    .card-title {
      font-family: 'DM Serif Display', serif;
      font-size: 16px;
      color: var(--accent2);
      margin-bottom: 4px;
    }
    .card-desc {
      font-size: 12.5px;
      color: var(--muted);
      margin-bottom: 18px;
    }

    /* ── Form elements ─────────────────────────────────────────── */
    .field-group { display: flex; flex-direction: column; gap: 5px; margin-bottom: 14px; }
    .field-row { display: flex; gap: 12px; flex-wrap: wrap; }
    .field-row .field-group { flex: 1; min-width: 140px; }
    label {
      font-size: 11.5px;
      font-weight: 500;
      letter-spacing: .5px;
      text-transform: uppercase;
      color: var(--muted);
    }
    input, textarea, select {
      background: var(--bg);
      border: 1px solid var(--border2);
      border-radius: var(--radius-sm);
      color: var(--text);
      font-family: 'DM Mono', monospace;
      font-size: 13px;
      padding: 9px 12px;
      width: 100%;
      outline: none;
      transition: border-color .18s, box-shadow .18s;
      resize: vertical;
    }
    input:focus, textarea:focus, select:focus {
      border-color: var(--accent);
      box-shadow: 0 0 0 3px rgba(201,168,76,.12);
    }
    textarea { min-height: 80px; }

    /* ── Buttons ───────────────────────────────────────────────── */
    .btn-row { display: flex; gap: 10px; flex-wrap: wrap; margin-top: 6px; }
    button {
      cursor: pointer;
      border: none;
      border-radius: var(--radius-sm);
      font-family: 'DM Sans', sans-serif;
      font-size: 13px;
      font-weight: 500;
      padding: 9px 18px;
      transition: all .18s;
      display: inline-flex;
      align-items: center;
      gap: 6px;
    }
    .btn-primary {
      background: var(--accent);
      color: #0d0f14;
    }
    .btn-primary:hover { background: var(--accent2); transform: translateY(-1px); }
    .btn-secondary {
      background: var(--surface2);
      color: var(--text);
      border: 1px solid var(--border2);
    }
    .btn-secondary:hover { border-color: var(--accent); color: var(--accent); }
    .btn-danger {
      background: rgba(240,96,112,.12);
      color: var(--red);
      border: 1px solid rgba(240,96,112,.25);
    }
    .btn-danger:hover { background: rgba(240,96,112,.22); }
    .btn-success {
      background: rgba(61,220,151,.12);
      color: var(--green);
      border: 1px solid rgba(61,220,151,.25);
    }
    .btn-success:hover { background: rgba(61,220,151,.22); }

    /* ── Result area ───────────────────────────────────────────── */
    .result-block {
      background: var(--bg);
      border: 1px solid var(--border);
      border-radius: var(--radius-sm);
      padding: 16px;
      min-height: 60px;
      margin-top: 14px;
    }
    .result-block.hidden { display: none; }

    /* ── Ticker pill list ──────────────────────────────────────── */
    .ticker-pills {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      padding: 12px;
      background: var(--bg);
      border: 1px solid var(--border2);
      border-radius: var(--radius-sm);
      min-height: 44px;
      align-items: center;
    }
    .ticker-pill {
      font-family: 'DM Mono', monospace;
      font-size: 12px;
      font-weight: 500;
      letter-spacing: .5px;
      padding: 3px 10px;
      border-radius: 20px;
      background: rgba(201,168,76,.12);
      color: var(--accent2);
      border: 1px solid rgba(201,168,76,.25);
    }
    .ticker-pills-empty {
      font-size: 12.5px;
      color: var(--muted);
      font-style: italic;
    }

    /* ── Allocation table ──────────────────────────────────────── */
    .alloc-table { width: 100%; border-collapse: collapse; margin-top: 6px; }
    .alloc-table th {
      font-size: 11px;
      font-weight: 600;
      letter-spacing: .8px;
      text-transform: uppercase;
      color: var(--muted);
      text-align: left;
      padding: 6px 10px 10px;
      border-bottom: 1px solid var(--border2);
    }
    .alloc-table td {
      font-family: 'DM Mono', monospace;
      font-size: 13px;
      padding: 9px 10px;
      border-bottom: 1px solid var(--border);
      vertical-align: middle;
    }
    .alloc-table tr:last-child td { border-bottom: none; }
    .alloc-table tr:hover td { background: var(--surface2); }

    .tag {
      display: inline-block;
      font-size: 11px;
      font-weight: 600;
      letter-spacing: .5px;
      padding: 2px 8px;
      border-radius: 4px;
    }
    .tag-buy  { background: rgba(61,220,151,.14); color: var(--green); }
    .tag-sell { background: rgba(240,96,112,.14); color: var(--red); }
    .tag-none { background: var(--surface2); color: var(--muted); }

    /* ── Progress bar ──────────────────────────────────────────── */
    .bar-wrap {
      height: 6px;
      background: var(--border2);
      border-radius: 3px;
      overflow: hidden;
      width: 100px;
      display: inline-block;
      vertical-align: middle;
    }
    .bar-fill {
      height: 100%;
      border-radius: 3px;
      background: var(--accent);
      transition: width .4s;
    }
    .bar-fill.over { background: var(--red); }

    /* ── Status banner ─────────────────────────────────────────── */
    .banner {
      display: none;
      align-items: center;
      gap: 10px;
      padding: 11px 16px;
      border-radius: var(--radius-sm);
      font-size: 13px;
      font-weight: 500;
      margin-top: 12px;
      animation: fadeIn .3s;
    }
    .banner.show { display: flex; }
    .banner.ok  { background: rgba(61,220,151,.1);  color: var(--green); border: 1px solid rgba(61,220,151,.25); }
    .banner.err { background: rgba(240,96,112,.1);  color: var(--red);   border: 1px solid rgba(240,96,112,.25); }
    .banner.info{ background: rgba(91,138,245,.1);  color: var(--blue);  border: 1px solid rgba(91,138,245,.25); }
    @keyframes fadeIn { from{opacity:0;transform:translateY(-4px)} to{opacity:1;transform:none} }

    /* ── Transaction feed ──────────────────────────────────────── */
    .tx-feed { display: flex; flex-direction: column; gap: 8px; }
    .tx-item {
      display: flex;
      align-items: center;
      gap: 14px;
      padding: 10px 14px;
      background: var(--bg);
      border-radius: var(--radius-sm);
      border: 1px solid var(--border);
      font-size: 13px;
    }
    .tx-item .ticker {
      font-family: 'DM Mono', monospace;
      font-weight: 500;
      font-size: 14px;
      min-width: 50px;
    }
    .tx-item .amount {
      font-family: 'DM Mono', monospace;
      color: var(--accent2);
      margin-left: auto;
    }
    .tx-item .date { font-size: 11px; color: var(--muted); }

    /* ── Price chips ───────────────────────────────────────────── */
    .price-grid { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 14px; }
    .price-chip {
      background: var(--bg);
      border: 1px solid var(--border2);
      border-radius: var(--radius-sm);
      padding: 12px 18px;
      display: flex;
      flex-direction: column;
      gap: 3px;
      min-width: 110px;
    }
    .price-chip .sym { font-size: 11px; color: var(--muted); font-weight: 600; letter-spacing: .8px; text-transform: uppercase; }
    .price-chip .val { font-family: 'DM Mono', monospace; font-size: 20px; color: var(--accent2); }

    /* ── Portfolio value hero ──────────────────────────────────── */
    .hero-val {
      font-family: 'DM Serif Display', serif;
      font-size: 38px;
      color: var(--accent);
      letter-spacing: -.5px;
    }
    .hero-label { font-size: 12px; color: var(--muted); text-transform: uppercase; letter-spacing: 1px; margin-bottom: 4px; }
    .hero-meta { font-size: 12.5px; color: var(--muted); margin-top: 6px; }

    /* ── Scrollbar ─────────────────────────────────────────────── */
    ::-webkit-scrollbar { width: 6px; }
    ::-webkit-scrollbar-track { background: transparent; }
    ::-webkit-scrollbar-thumb { background: var(--border2); border-radius: 3px; }
    ::-webkit-scrollbar-thumb:hover { background: var(--muted); }

    /* ── Helpers ───────────────────────────────────────────────── */
    .mono  { font-family: 'DM Mono', monospace; }
    .green { color: var(--green); }
    .red   { color: var(--red);   }
    .gold  { color: var(--accent2); }
    .muted { color: var(--muted); }
    .mt8   { margin-top: 8px; }
  </style>
</head>
<body>

<!-- ── Top bar ───────────────────────────────────────────── -->
<div class="topbar">
  <div class="topbar-logo">Rebalancer<span>.</span></div>
  <div class="topbar-divider"></div>
  <div class="topbar-subtitle">Portfolio Management Tool</div>
  <div class="topbar-spacer"></div>
  <div class="topbar-status">
    <div class="status-dot" id="statusDot"></div>
    <span id="statusText">Idle</span>
  </div>
</div>

<!-- ── Body ─────────────────────────────────────────────── -->
<div class="layout">

  <!-- Sidebar -->
  <nav class="sidebar">
    <div class="nav-section-label">Portfolio</div>
    <div class="nav-item active" onclick="switchPanel('setup', this)">
      <span class="nav-icon">⬡</span> Setup
    </div>
    <div class="nav-item" onclick="switchPanel('prices', this)">
      <span class="nav-icon">◈</span> Prices
    </div>

    <div class="nav-section-label" style="margin-top:12px">Rebalancing</div>
    <div class="nav-item" onclick="switchPanel('check', this)">
      <span class="nav-icon">⊹</span> Analysis
    </div>
    <div class="nav-item" onclick="switchPanel('execute', this)">
      <span class="nav-icon">⟳</span> Execute
    </div>

    <div class="nav-section-label" style="margin-top:12px">Manage</div>
    <div class="nav-item" onclick="switchPanel('transaction', this)">
      <span class="nav-icon">⊕</span> Transactions
    </div>
    <div class="nav-item" onclick="switchPanel('weights', this)">
      <span class="nav-icon">⊘</span> Weights
    </div>
  </nav>

  <!-- Main -->
  <div class="main">

    <!-- ══ SETUP PANEL ══════════════════════════════════════ -->
    <div class="panel active" id="panel-setup">
      <div class="card">
        <div class="card-title">Portfolio Setup</div>
        <div class="card-desc">Define your holdings and target allocations. Weights must sum to exactly 1.0.</div>

        <div class="field-group">
          <label>Assets</label>
          <div id="portfolio-rows" style="display:flex;flex-direction:column;gap:8px"></div>
          <div style="margin-top:8px; display:flex; gap:8px; align-items:center">
            <button id="add-asset" class="btn-secondary">+ Add asset</button>
            <div class="mono muted" style="font-size:12px">Ticker · Shares · Weight (0–1, must sum to 1.0)</div>
          </div>
        </div>

        <div class="btn-row">
          <button class="btn-primary" onclick="doSetPortfolio()">⊕ Set Portfolio</button>
          <button class="btn-secondary" onclick="insertExample()">Insert Example</button>
        </div>

        <div class="banner" id="setupBanner"></div>
        <div id="setupResult" class="result-block hidden"></div>
      </div>
    </div>

    <!-- ══ PRICES PANEL ═════════════════════════════════════ -->
    <div class="panel" id="panel-prices">
      <div class="card">
        <div class="card-title">Live Prices</div>
        <div class="card-desc">
          Fetches current market prices for every asset in your portfolio via yFinance.
          Set up your portfolio first, then fetch prices here.
        </div>

        <label style="display:block;margin-bottom:8px">Portfolio tickers</label>
        <div class="ticker-pills" id="portfolioTickerPills">
          <span class="ticker-pills-empty">No portfolio set — go to Setup first.</span>
        </div>

        <div class="btn-row" style="margin-top:16px">
          <button class="btn-primary" onclick="doGetPrices()">◈ Fetch Prices</button>
        </div>

        <div id="priceChips" class="price-grid"></div>
        <div class="banner" id="priceBanner"></div>
      </div>
    </div>

    <!-- ══ CHECK PANEL ══════════════════════════════════════ -->
    <div class="panel" id="panel-check">
      <div class="card">
        <div class="card-title">Rebalance Analysis</div>
        <div class="card-desc">Compare current allocations against targets and see recommended trades.</div>

        <div class="field-group" style="max-width:200px">
          <label>Drift Threshold (%)</label>
          <input id="threshold" type="number" value="5" min="0" max="99" step="0.5" />
        </div>

        <div class="btn-row">
          <button class="btn-primary" onclick="doCheck()">⊹ Run Analysis</button>
        </div>

        <div id="checkResult"></div>
        <div class="banner" id="checkBanner"></div>
      </div>
    </div>

    <!-- ══ EXECUTE PANEL ════════════════════════════════════ -->
    <div class="panel" id="panel-execute">
      <div class="card">
        <div class="card-title">Execute Rebalance</div>
        <div class="card-desc">Apply all recommended trades to your portfolio and record them to <span class="mono">transactions.json</span>.</div>

        <div class="banner info show" style="margin-top:0;margin-bottom:16px">
          ⚠ This action modifies your portfolio quantities and writes to disk.
        </div>

        <div class="btn-row">
          <button class="btn-success" onclick="doExecute()">⟳ Execute &amp; Record Transactions</button>
        </div>

        <div id="execResult" class="mt8"></div>
        <div class="banner" id="execBanner"></div>
      </div>
    </div>

    <!-- ══ TRANSACTION PANEL ════════════════════════════════ -->
    <div class="panel" id="panel-transaction">
      <div class="card">
        <div class="card-title">Record Transaction</div>
        <div class="card-desc">Manually log an arbitrary buy or sell for any portfolio ticker.</div>

        <div class="field-row">
          <div class="field-group">
            <label>Ticker</label>
            <input id="txTicker" placeholder="SPY" />
          </div>
          <div class="field-group">
            <label>Action</label>
            <select id="txAction">
              <option value="buy">Buy</option>
              <option value="sell">Sell</option>
            </select>
          </div>
          <div class="field-group">
            <label>Shares</label>
            <input id="txShares" type="number" placeholder="10" min="0" step="0.0001" />
          </div>
          <div class="field-group">
            <label>Price (optional)</label>
            <input id="txPrice" type="number" placeholder="current price" min="0" step="0.01" />
          </div>
        </div>

        <div class="btn-row">
          <button class="btn-primary" onclick="doTransaction()">⊕ Record Transaction</button>
        </div>

        <div class="banner" id="txBanner"></div>
        <div id="txResult" class="mt8"></div>
      </div>
    </div>

    <!-- ══ WEIGHTS PANEL ════════════════════════════════════ -->
    <div class="panel" id="panel-weights">
      <div class="card">
        <div class="card-title">Adjust Target Weights</div>
        <div class="card-desc">Update the target allocation for every portfolio ticker. All weights must sum to exactly 1.0.</div>

        <div class="field-group">
          <label>Weights</label>
          <div id="weights-rows" style="display:flex;flex-direction:column;gap:8px"></div>
          <div style="margin-top:8px; display:flex; gap:8px; align-items:center">
            <button id="add-weight" class="btn-secondary">+ Add weight</button>
            <div class="mono muted" style="font-size:12px">Ticker · Weight (0–1, must include every portfolio ticker)</div>
          </div>
        </div>

        <div class="btn-row">
          <button class="btn-primary" onclick="doSetWeights()">⊘ Apply Weights</button>
        </div>

        <div class="banner" id="weightsBanner"></div>
      </div>
    </div>

  </div><!-- /main -->
</div><!-- /layout -->

<script>
/* ── Global state ───────────────────────────────────────── */
// Tracks tickers currently in the portfolio so Prices panel stays in sync
let portfolioTickers = [];

/* ── Status helpers ─────────────────────────────────────── */
function setStatus(state, text) {
  document.getElementById('statusDot').className = 'status-dot ' + state;
  document.getElementById('statusText').textContent = text;
}
function showBanner(id, type, msg) {
  const el = document.getElementById(id);
  el.className = 'banner show ' + type;
  el.textContent = msg;
  setTimeout(() => { el.className = 'banner'; }, 6000);
}
function busy(label) { setStatus('busy', label); }
function idle()       { setStatus('', 'Idle'); }
function done(ok)     { setStatus(ok ? 'ok' : 'err', ok ? 'Ready' : 'Error'); setTimeout(idle, 3000); }
function fmt$(n)      { return '$' + Number(n).toLocaleString('en-US', {minimumFractionDigits:2, maximumFractionDigits:2}); }
function fmtPct(n)    { return Number(n).toFixed(2) + '%'; }

/* ── Navigation ─────────────────────────────────────────── */
function switchPanel(id, el) {
  document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  document.getElementById('panel-' + id).classList.add('active');
  el.classList.add('active');
  // Refresh pill display whenever user opens the Prices panel
  if (id === 'prices') refreshTickerPills();
}

/* ── Ticker pill display ────────────────────────────────── */
function refreshTickerPills() {
  const container = document.getElementById('portfolioTickerPills');
  if (portfolioTickers.length === 0) {
    container.innerHTML = '<span class="ticker-pills-empty">No portfolio set — go to Setup first.</span>';
  } else {
    container.innerHTML = portfolioTickers.map(t =>
      `<span class="ticker-pill">${t}</span>`
    ).join('');
  }
}

/* ── SETUP ──────────────────────────────────────────────── */
async function doSetPortfolio() {
  const rows = Array.from(document.getElementById('portfolio-rows').querySelectorAll('.row'));
  const obj = {};
  for (const r of rows) {
    const t = r.querySelector('.p-ticker').value.trim().toUpperCase();
    const s = r.querySelector('.p-shares').value.trim();
    const w = r.querySelector('.p-weight').value.trim();
    if (!t) continue;
    obj[t] = [parseFloat(s) || 0, parseFloat(w) || 0];
  }
  if (Object.keys(obj).length === 0) {
    showBanner('setupBanner', 'err', '✖ No assets provided.');
    return;
  }
  busy('Setting portfolio…');
  const res = await window.pywebview.api.set_portfolio(JSON.stringify(obj));
  done(!res.error);
  if (res.error) {
    showBanner('setupBanner', 'err', '✖ ' + res.error);
    document.getElementById('setupResult').classList.add('hidden');
  } else {
    // Update global ticker list so Prices panel reflects the new portfolio
    portfolioTickers = Object.keys(res.portfolio);
    showBanner('setupBanner', 'ok', '✔ Portfolio set — ' + portfolioTickers.length + ' assets loaded.');
    const el = document.getElementById('setupResult');
    el.classList.remove('hidden');
    el.innerHTML = renderPortfolioTable(res.portfolio);
  }
}

function addPortfolioRow(ticker='', shares='', weight='') {
  const cont = document.getElementById('portfolio-rows');
  const row = document.createElement('div');
  row.className = 'row';
  row.style.cssText = 'display:flex;gap:8px;align-items:center';
  row.innerHTML = `
    <input class='p-ticker' placeholder='TICKER'       value='${ticker}' style='width:130px' />
    <input class='p-shares' placeholder='shares'       value='${shares}' style='width:130px' type='number' min='0' step='0.0001' />
    <input class='p-weight' placeholder='weight (0–1)' value='${weight}' style='width:140px' type='number' min='0' max='1' step='0.01' />
    <button class='btn-secondary' style='min-width:76px'>Remove</button>
  `;
  row.querySelector('button').onclick = () => row.remove();
  cont.appendChild(row);
}

function clearPortfolioRows() { document.getElementById('portfolio-rows').innerHTML = ''; }

document.getElementById('add-asset').addEventListener('click', e => { e.preventDefault(); addPortfolioRow(); });
addPortfolioRow(); // start with one blank row

function renderPortfolioTable(port) {
  let rows = '';
  for (const [ticker, [qty, wt]] of Object.entries(port)) {
    rows += `<tr>
      <td class="gold" style="font-weight:500">${ticker}</td>
      <td>${Number(qty).toLocaleString()}</td>
      <td>${fmtPct(wt * 100)}</td>
      <td><div class="bar-wrap"><div class="bar-fill" style="width:${Math.min(wt*100,100)}%"></div></div></td>
    </tr>`;
  }
  return `<table class="alloc-table">
    <thead><tr><th>Ticker</th><th>Qty</th><th>Target</th><th>Allocation</th></tr></thead>
    <tbody>${rows}</tbody>
  </table>`;
}

function insertExample() {
  clearPortfolioRows();
  addPortfolioRow('SPY', '100', '0.5');
  addPortfolioRow('TLT', '50',  '0.3');
  addPortfolioRow('GLD', '20',  '0.2');
}

/* ── PRICES ─────────────────────────────────────────────── */
async function doGetPrices() {
  if (portfolioTickers.length === 0) {
    showBanner('priceBanner', 'err', '✖ No portfolio set. Go to Setup and set your portfolio first.');
    return;
  }
  busy('Fetching prices…');
  // Always use the tickers from the portfolio — no manual input
  const res = await window.pywebview.api.get_prices(portfolioTickers.join(','));
  done(!res.error);
  const chips = document.getElementById('priceChips');
  if (res.error) {
    showBanner('priceBanner', 'err', '✖ ' + res.error);
    chips.innerHTML = '';
  } else {
    showBanner('priceBanner', 'ok', '✔ Prices fetched — ' + Object.keys(res.prices).length + ' tickers.');
    chips.innerHTML = Object.entries(res.prices).map(([sym, val]) =>
      `<div class="price-chip">
        <div class="sym">${sym}</div>
        <div class="val">${fmt$(val)}</div>
      </div>`
    ).join('');
  }
}

/* ── CHECK ──────────────────────────────────────────────── */
async function doCheck() {
  const thr = parseFloat(document.getElementById('threshold').value) || 5;
  busy('Analysing…');
  const res = await window.pywebview.api.check_rebalance(thr);
  done(!res.error);
  const out = document.getElementById('checkResult');
  if (res.error) {
    showBanner('checkBanner', 'err', '✖ ' + res.error);
    out.innerHTML = '';
    return;
  }

  const needsColor = res.needs_rebalance ? 'red' : 'green';
  const needsLabel = res.needs_rebalance ? '⚠ Rebalance needed' : '✔ Portfolio is balanced';

  let rows = '';
  for (const ticker of Object.keys(res.current_allocations)) {
    const cur  = res.current_allocations[ticker];
    const tgt  = res.target_allocations[ticker];
    const diff = res.differences[ticker];
    const over = diff > thr;
    rows += `<tr>
      <td class="gold" style="font-weight:500">${ticker}</td>
      <td>${fmtPct(cur)}</td>
      <td>${fmtPct(tgt)}</td>
      <td class="${over ? 'red' : 'green'}" style="font-weight:${over?'600':'400'}">${fmtPct(diff)}</td>
      <td><div class="bar-wrap" style="width:120px"><div class="bar-fill ${over?'over':''}" style="width:${Math.min(cur,100)}%"></div></div></td>
    </tr>`;
  }

  let recRows = '';
  if (res.recommendations) {
    for (const [ticker, r] of Object.entries(res.recommendations)) {
      if (r.action === 'none') continue;
      const cls  = r.action === 'BUY' ? 'buy' : 'sell';
      const sign = r.action === 'BUY' ? '+' : '−';
      recRows += `<tr>
        <td class="gold" style="font-weight:500">${ticker}</td>
        <td><span class="tag tag-${cls}">${r.action}</span></td>
        <td class="${cls==='buy'?'green':'red'}">${sign}${fmt$(Math.abs(r.dollar_change))}</td>
        <td class="${cls==='buy'?'green':'red'}">${sign}${Math.abs(r.shares_change).toFixed(4)} shares</td>
        <td class="muted">${fmt$(r.price)}</td>
      </tr>`;
    }
  }

  out.innerHTML = `
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:18px;flex-wrap:wrap;gap:12px;margin-top:18px">
      <div>
        <div class="hero-label">Portfolio Value</div>
        <div class="hero-val">${fmt$(res.portfolio_value)}</div>
        <div class="hero-meta">Threshold: ${fmtPct(thr)}</div>
      </div>
      <div style="font-size:15px;font-weight:600;padding:10px 18px;border-radius:8px;
                  background:${res.needs_rebalance?'rgba(240,96,112,.1)':'rgba(61,220,151,.1)'};
                  border:1px solid ${res.needs_rebalance?'rgba(240,96,112,.25)':'rgba(61,220,151,.25)'};
                  color:var(--${needsColor})">
        ${needsLabel}
      </div>
    </div>
    <div class="card-title" style="margin-bottom:8px">Allocations</div>
    <table class="alloc-table" style="margin-bottom:22px">
      <thead><tr><th>Ticker</th><th>Current</th><th>Target</th><th>Drift</th><th>Bar</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>
    ${recRows
      ? `<div class="card-title" style="margin-bottom:8px">Recommended Trades</div>
         <table class="alloc-table">
           <thead><tr><th>Ticker</th><th>Action</th><th>$ Amount</th><th>Shares</th><th>@ Price</th></tr></thead>
           <tbody>${recRows}</tbody>
         </table>`
      : '<div class="muted" style="font-size:13px;margin-top:8px">No trades recommended — all assets within threshold.</div>'
    }`;
}

/* ── EXECUTE ─────────────────────────────────────────────── */
async function doExecute() {
  busy('Executing rebalance…');
  const res = await window.pywebview.api.execute_rebalance();
  done(!res.error);
  const out = document.getElementById('execResult');
  if (res.error) {
    showBanner('execBanner', 'err', '✖ ' + res.error);
    out.innerHTML = '';
    return;
  }
  const txns = res.transactions;
  if (!txns || txns.length === 0) {
    showBanner('execBanner', 'info', 'ℹ No trades were necessary — portfolio is already balanced.');
    out.innerHTML = '';
    return;
  }
  showBanner('execBanner', 'ok', `✔ ${txns.length} transaction(s) recorded to transactions.json`);
  out.innerHTML = '<div class="tx-feed">' +
    txns.slice(-20).reverse().map(tx => {
      const cls = tx.action === 'BUY' ? 'tag-buy' : 'tag-sell';
      return `<div class="tx-item">
        <span class="ticker gold">${tx.ticker}</span>
        <span class="tag ${cls}">${tx.action}</span>
        <span class="muted">${Number(tx.shares).toFixed(4)} shares</span>
        <span class="muted">@ ${fmt$(tx.price)}</span>
        <span class="amount">${fmt$(tx.dollar_amount)}</span>
        <span class="date">${new Date(tx.date).toLocaleString()}</span>
      </div>`;
    }).join('') + '</div>';
}

/* ── TRANSACTION ─────────────────────────────────────────── */
async function doTransaction() {
  const ticker   = document.getElementById('txTicker').value.trim().toUpperCase();
  const action   = document.getElementById('txAction').value;
  const shares   = parseFloat(document.getElementById('txShares').value);
  const priceRaw = document.getElementById('txPrice').value.trim();
  const price    = priceRaw ? parseFloat(priceRaw) : null;

  if (!ticker || isNaN(shares) || shares <= 0) {
    showBanner('txBanner', 'err', '✖ Please enter a valid ticker and share count.');
    return;
  }
  busy('Recording transaction…');
  const res = await window.pywebview.api.execute_transaction(ticker, action, shares, price);
  done(!res.error);
  const out = document.getElementById('txResult');
  if (res.error) {
    showBanner('txBanner', 'err', '✖ ' + res.error);
    out.innerHTML = '';
    return;
  }
  const tx  = res.transaction;
  const cls = tx.action === 'BUY' ? 'tag-buy' : 'tag-sell';
  showBanner('txBanner', 'ok', '✔ Transaction recorded.');
  out.innerHTML = `<div class="tx-feed"><div class="tx-item">
    <span class="ticker gold">${tx.ticker}</span>
    <span class="tag ${cls}">${tx.action}</span>
    <span class="muted">${Number(tx.shares).toFixed(4)} shares</span>
    <span class="muted">@ ${fmt$(tx.price)}</span>
    <span class="amount">${fmt$(tx.dollar_amount)}</span>
    <span class="date">${new Date(tx.date).toLocaleString()}</span>
  </div></div>`;
}

/* ── WEIGHTS ─────────────────────────────────────────────── */
async function doSetWeights() {
  const rows = Array.from(document.getElementById('weights-rows').querySelectorAll('.row'));
  const obj = {};
  for (const r of rows) {
    const t = r.querySelector('.w-ticker').value.trim().toUpperCase();
    const w = r.querySelector('.w-weight').value.trim();
    if (!t) continue;
    obj[t] = parseFloat(w) || 0;
  }
  if (Object.keys(obj).length === 0) {
    showBanner('weightsBanner', 'err', '✖ No weights provided.');
    return;
  }
  busy('Updating weights…');
  const res = await window.pywebview.api.set_weights(JSON.stringify(obj));
  done(!res.error);
  if (res.error) {
    showBanner('weightsBanner', 'err', '✖ ' + res.error);
  } else {
    showBanner('weightsBanner', 'ok', '✔ Target weights updated successfully.');
  }
}

function addWeightRow(ticker='', weight='') {
  const cont = document.getElementById('weights-rows');
  const row = document.createElement('div');
  row.className = 'row';
  row.style.cssText = 'display:flex;gap:8px;align-items:center';
  row.innerHTML = `
    <input class='w-ticker' placeholder='TICKER'       value='${ticker}' style='width:200px' />
    <input class='w-weight' placeholder='weight (0–1)' value='${weight}' style='width:140px' type='number' min='0' max='1' step='0.01' />
    <button class='btn-secondary' style='min-width:76px'>Remove</button>
  `;
  row.querySelector('button').onclick = () => row.remove();
  cont.appendChild(row);
}

document.getElementById('add-weight').addEventListener('click', e => { e.preventDefault(); addWeightRow(); });
addWeightRow();
</script>
</body>
</html>
"""


def start_gui():
    api = Api()
    window = webview.create_window(
        'Portfolio Rebalancer',
        html=HTML,
        js_api=api,
        width=1040,
        height=760,
        min_size=(800, 600),
    )
    webview.start(gui='gtk', debug=False)


if __name__ == '__main__':
    start_gui()