const $ = (id) => document.getElementById(id);
let currentSpec = null;
let loadedCandles = [];

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    cache: "no-store",
  });
  let body = {};
  try { body = await response.json(); } catch (_) { body = {}; }
  if (!response.ok) {
    const detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail || "Request failed");
    throw new Error(detail);
  }
  return body;
}
function message(id, text, type = "") {
  const element = $(id);
  element.textContent = text;
  element.className = "inline-message" + (type ? " " + type : "");
}
function number(value, digits = 2) {
  const result = Number(value);
  return Number.isFinite(result) ? result.toLocaleString(undefined, { maximumFractionDigits: digits }) : "—";
}
function show(id, visible) { $(id).classList.toggle("hidden", !visible); }

function renderSpec(spec) {
  currentSpec = spec;
  const box = $("spec-preview");
  box.replaceChildren();
  const title = document.createElement("div");
  title.className = "spec-title";
  title.textContent = spec.name;
  box.append(title);
  const grid = document.createElement("div");
  grid.className = "spec-grid";
  [["Symbol", spec.symbol], ["Timeframe", spec.timeframe], ["Fast EMA", spec.fast_ema],
   ["Slow EMA", spec.slow_ema], ["Engine", "Long-only"], ["Execution", "Paper-first"]].forEach(([label, value]) => {
    const cell = document.createElement("div");
    const labelNode = document.createElement("span");
    labelNode.textContent = label;
    const valueNode = document.createElement("strong");
    valueNode.textContent = String(value);
    cell.append(labelNode, valueNode);
    grid.append(cell);
  });
  box.append(grid);
  const controls = document.createElement("div");
  controls.className = "spec-actions";
  const save = document.createElement("button");
  save.className = "button button-secondary";
  save.type = "button";
  save.textContent = "Save strategy";
  save.addEventListener("click", saveCurrentStrategy);
  controls.append(save);
  box.append(controls);
  show("spec-preview", true);
  $("backtest").disabled = loadedCandles.length < 10;
}
async function buildStrategy() {
  message("builder-message", "Building…");
  $("parse").disabled = true;
  try {
    const spec = await api("/api/strategies/parse", {
      method: "POST", body: JSON.stringify({ prompt: $("prompt").value }),
    });
    renderSpec(spec);
    message("builder-message", "Validated strategy ready.", "success");
  } catch (error) { message("builder-message", error.message, "error"); }
  finally { $("parse").disabled = false; }
}
async function saveCurrentStrategy() {
  if (!currentSpec) return;
  const name = window.prompt("Name this strategy", currentSpec.name);
  if (!name || name.trim().length < 2) return;
  try {
    await api("/api/strategies", {
      method: "POST", body: JSON.stringify({ name: name.trim(), spec: currentSpec }),
    });
    message("builder-message", "Saved inactive. Activate only after paper testing.", "success");
    await loadStrategies();
  } catch (error) { message("builder-message", error.message, "error"); }
}
function parseCsv(text) {
  const lines = text.trim().split(/\r?\n/).filter(Boolean);
  if (lines.length < 11) throw new Error("CSV needs a header and at least 10 candle rows.");
  const headers = lines[0].split(",").map((x) => x.trim().toLowerCase());
  const idx = (name) => headers.indexOf(name);
  for (const name of ["timestamp", "open", "high", "low", "close"]) {
    if (idx(name) < 0) throw new Error("Missing CSV column: " + name);
  }
  return lines.slice(1).map((line) => {
    const cells = line.split(",").map((x) => x.trim());
    const date = new Date(cells[idx("timestamp")]);
    const values = ["open", "high", "low", "close"].map((key) => Number(cells[idx(key)]));
    if (Number.isNaN(date.getTime()) || values.some((value) => !Number.isFinite(value))) {
      throw new Error("CSV has an invalid timestamp or numeric candle value.");
    }
    return {
      timestamp: date.toISOString(), open: values[0], high: values[1], low: values[2], close: values[3],
      volume: idx("volume") < 0 ? 0 : Number(cells[idx("volume")] || 0),
    };
  });
}
$("csv-file").addEventListener("change", async (event) => {
  const file = event.target.files && event.target.files[0];
  loadedCandles = [];
  $("backtest").disabled = true;
  if (!file) return;
  try {
    if (file.size > 5 * 1024 * 1024) throw new Error("CSV files must be 5 MB or smaller.");
    loadedCandles = parseCsv(await file.text());
    if (loadedCandles.length > 10000) throw new Error("CSV may contain no more than 10,000 rows.");
    $("backtest").disabled = !currentSpec;
    message("backtest-message", loadedCandles.length + " candles loaded locally.", "success");
  } catch (error) {
    loadedCandles = [];
    message("backtest-message", error.message, "error");
  }
});
async function runBacktest() {
  if (!currentSpec || loadedCandles.length < 10) return;
  message("backtest-message", "Running simulation…");
  $("backtest").disabled = true;
  try {
    const result = await api("/api/backtests/run", { method: "POST", body: JSON.stringify({
      spec: currentSpec, candles: loadedCandles, starting_cash: Number($("cash").value),
      position_fraction: Number($("allocation").value) / 100,
      fee_bps: Number($("fees").value), slippage_bps: Number($("slippage").value),
    }) });
    renderBacktest(result);
    message("backtest-message", "Simulation complete. Historical results are not predictive.", "success");
  } catch (error) { message("backtest-message", error.message, "error"); }
  finally { $("backtest").disabled = loadedCandles.length < 10 || !currentSpec; }
}
function renderBacktest(result) {
  const target = $("backtest-results");
  target.replaceChildren();
  const grid = document.createElement("div");
  grid.className = "metric-grid";
  [["Total return", number(result.total_return_pct, 3) + "%"],
   ["Max drawdown", number(result.max_drawdown_pct, 3) + "%"], ["Closed trades", String(result.trade_count)],
   ["Win rate", number(result.win_rate_pct, 2) + "%"], ["Starting cash", number(result.starting_cash)],
   ["Ending equity", number(result.ending_equity)]].forEach(([label, value]) => {
    const metric = document.createElement("div");
    metric.className = "metric";
    const small = document.createElement("span");
    small.textContent = label;
    const strong = document.createElement("strong");
    strong.textContent = value;
    metric.append(small, strong);
    grid.append(metric);
  });
  target.append(grid);
  const note = document.createElement("p");
  note.className = "small-note";
  note.textContent = result.warning;
  target.append(note);
  if (result.trades.length) {
    const heading = document.createElement("h3");
    heading.textContent = "Trade ledger";
    target.append(heading);
    const table = document.createElement("div");
    table.className = "strategy-list";
    result.trades.slice(-20).forEach((trade) => {
      const row = document.createElement("div");
      row.className = "strategy-row";
      const info = document.createElement("div");
      const title = document.createElement("div");
      title.className = "strategy-name";
      title.textContent = trade.entry_time.slice(0, 16).replace("T", " ") + " → " + trade.exit_time.slice(0, 16).replace("T", " ");
      const meta = document.createElement("div");
      meta.className = "strategy-meta";
      meta.textContent = "Entry " + number(trade.entry_price, 4) + " · Exit " + number(trade.exit_price, 4);
      info.append(title, meta);
      const pnl = document.createElement("strong");
      pnl.className = trade.pnl >= 0 ? "positive" : "negative";
      pnl.textContent = (trade.pnl >= 0 ? "+" : "") + number(trade.pnl) + " (" + number(trade.return_pct, 2) + "%)";
      row.append(info, pnl);
      table.append(row);
    });
    target.append(table);
  }
  show("backtest-results", true);
}
async function loadStatus() {
  try {
    await api("/api/health");
    $("engine-status").textContent = "Ready";
    const status = await api("/api/status");
    $("broker-status").textContent = status.alpaca_paper_configured ? "Configured" : "Not connected";
    $("automation-status").textContent = status.automation_enabled ? "Enabled" : "Off";
    $("connection").textContent = "LOCAL ENGINE ONLINE";
  } catch (_) {
    $("engine-status").textContent = "Unavailable";
    $("connection").textContent = "API UNAVAILABLE";
  }
}
async function loadAccount() {
  $("account-results").textContent = "Checking paper account…";
  try {
    const account = await api("/api/brokers/alpaca/paper/account");
    const grid = document.createElement("div");
    grid.className = "account-grid";
    [["Status", account.status], ["Currency", account.currency], ["Equity", number(account.equity)],
     ["Buying power", number(account.buying_power)]].forEach(([label, value]) => {
      const node = document.createElement("div");
      node.className = "account-item";
      const span = document.createElement("span");
      span.textContent = label;
      const strong = document.createElement("strong");
      strong.textContent = String(value);
      node.append(span, strong);
      grid.append(node);
    });
    $("account-results").replaceChildren(grid);
  } catch (error) { $("account-results").textContent = error.message; }
}
async function submitPaperOrder() {
  if (!$("order-confirm").checked) {
    message("order-message", "Confirm that this is a paper-account order first.", "error");
    return;
  }
  const body = { symbol: $("order-symbol").value.trim().toUpperCase(), side: $("order-side").value,
    quantity: Number($("order-qty").value), limit_price: Number($("order-price").value), confirmed: true };
  if (!window.confirm("Submit this limit order to the Alpaca PAPER account? No live order route exists in this build.")) return;
  $("submit-order").disabled = true;
  try {
    const order = await api("/api/brokers/alpaca/paper/orders", { method: "POST", body: JSON.stringify(body) });
    message("order-message", "Paper order accepted: " + order.status + " · " + order.symbol + " · ID " + order.id, "success");
  } catch (error) { message("order-message", error.message, "error"); }
  finally { $("submit-order").disabled = false; }
}
async function mutateStrategy(id, action) {
  if (action === "activate" && !window.confirm("Activate paper automation? The worker may submit limit orders while you are away.")) return;
  try {
    await api("/api/strategies/" + encodeURIComponent(id) + "/" + action, {
      method: "POST", body: action === "activate" ? JSON.stringify({ confirmed: true }) : JSON.stringify({}),
    });
    await loadStrategies();
    await loadStatus();
  } catch (error) { window.alert(error.message); }
}
async function removeStrategy(id) {
  if (!window.confirm("Delete this inactive strategy?")) return;
  try {
    await api("/api/strategies/" + encodeURIComponent(id), { method: "DELETE" });
    await loadStrategies();
  } catch (error) { window.alert(error.message); }
}
async function loadStrategies() {
  const target = $("strategy-list");
  target.replaceChildren();
  try {
    const items = await api("/api/strategies");
    if (!items.length) {
      const empty = document.createElement("div");
      empty.className = "empty-state";
      empty.textContent = "No strategies saved yet.";
      target.append(empty);
      return;
    }
    items.forEach((item) => {
      const row = document.createElement("div");
      row.className = "strategy-row";
      const info = document.createElement("div");
      const title = document.createElement("div");
      title.className = "strategy-name";
      title.textContent = item.name;
      const meta = document.createElement("div");
      meta.className = "strategy-meta";
      meta.textContent = item.spec.symbol + " · " + item.spec.timeframe + " · EMA " + item.spec.fast_ema + "/" + item.spec.slow_ema;
      info.append(title, meta);
      const controls = document.createElement("div");
      controls.className = "strategy-controls";
      const tag = document.createElement("span");
      tag.className = "tag" + (item.active ? " active" : "");
      tag.textContent = item.active ? "PAPER WORKER ACTIVE" : "INACTIVE";
      controls.append(tag);
      const toggle = document.createElement("button");
      toggle.className = "button button-quiet";
      toggle.type = "button";
      toggle.textContent = item.active ? "Deactivate" : "Activate";
      toggle.addEventListener("click", () => mutateStrategy(item.id, item.active ? "deactivate" : "activate"));
      controls.append(toggle);
      if (!item.active) {
        const del = document.createElement("button");
        del.className = "button button-quiet";
        del.type = "button";
        del.textContent = "Delete";
        del.addEventListener("click", () => removeStrategy(item.id));
        controls.append(del);
      }
      row.append(info, controls);
      target.append(row);
    });
  } catch (error) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.textContent = error.message;
    target.append(empty);
  }
}
$("parse").addEventListener("click", buildStrategy);
$("backtest").addEventListener("click", runBacktest);
$("account").addEventListener("click", loadAccount);
$("submit-order").addEventListener("click", submitPaperOrder);
$("refresh").addEventListener("click", async () => { await loadStatus(); await loadStrategies(); });
$("reload-strategies").addEventListener("click", loadStrategies);
window.addEventListener("DOMContentLoaded", async () => {
  if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js").catch(() => {});
  await loadStatus();
  await loadStrategies();
});
