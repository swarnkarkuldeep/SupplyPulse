/* SupplyPulse demo page. All numbers come from window.SCA_DATA (site/data.js, built by `python -m sca site`). */
(function () {
  "use strict";

  const D = window.SCA_DATA;
  const R = D.results;
  const $ = (sel, root = document) => root.querySelector(sel);

  // ---------------------------------------------------------------- formatting
  const int = (n) => Math.round(n).toLocaleString("en-US");
  const pct = (x, d = 1) => (x * 100).toFixed(d) + "%";
  const usd = (n) => "$" + int(n);
  const usdShort = (n) => (Math.abs(n) >= 1e6 ? "$" + (n / 1e6).toFixed(1) + "M" : Math.abs(n) >= 1e3 ? "$" + Math.round(n / 1e3) + "k" : "$" + Math.round(n));
  const asDate = (v) => new Date(typeof v === "string" ? v + "T00:00:00Z" : v);
  const monthLabel = (v) => asDate(v).toLocaleDateString("en-US", { month: "short", year: "numeric", timeZone: "UTC" });
  const dayLabel = (v) => asDate(v).toLocaleDateString("en-US", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
  const cap = (s) => s.charAt(0).toUpperCase() + s.slice(1);
  const MODEL = { seasonal_naive: "Seasonal naive", moving_average: "Moving average", sarima: "SARIMA", prophet: "Prophet", lightgbm: "LightGBM", logistic: "Logistic regression", shipping_mode_only: "Shipping mode only" };
  const modelName = (k) => MODEL[k] || cap(k.replace(/_/g, " "));
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);

  function bind(name, html) {
    const node = $(`[data-bind="${name}"]`);
    if (node) node.innerHTML = html;
  }

  function barRow({ label, sub, value, shown, cls, max = 1, min = 0 }) {
    const w = Math.max(0, Math.min(100, ((value - min) / (max - min)) * 100));
    return `<div class="bar-row"><div class="bar-label">${esc(label)}${sub ? `<small>${esc(sub)}</small>` : ""}</div>
      <div class="bar-track" role="img" aria-label="${esc(label)}: ${esc(shown)}"><div class="bar-fill ${cls || ""}" style="width:${w}%"></div></div>
      <div class="bar-val">${esc(shown)}</div></div>`;
  }

  // ---------------------------------------------------------------- line chart
  const niceTicks = (lo, hi, n = 4) => {
    const span = hi - lo || 1;
    const raw = span / n;
    const mag = Math.pow(10, Math.floor(Math.log10(raw)));
    const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw) || mag * 10;
    const out = [];
    for (let v = Math.ceil(lo / step) * step; v <= hi + 1e-9; v += step) out.push(+v.toFixed(10));
    return out;
  };

  /** Draw lines/bands/rules into `host`. cfg: series[{name,color,dash,width,dots,pts:[[x,y,extra]]}], bands, vlines, hlines, xFmt, yFmt, tip. */
  function lineChart(host, cfg) {
    const W = Math.max(300, host.clientWidth - 16);
    const H = cfg.height || Math.round(Math.max(250, Math.min(380, W * 0.4)));
    const m = { l: cfg.left || 54, r: 16, t: 14, b: 30 };
    const all = [];
    cfg.series.forEach((s) => s.pts.forEach((p) => p[1] != null && all.push(p)));
    (cfg.bands || []).forEach((b) => b.pts.forEach((p) => all.push([p[0], p[1]], [p[0], p[2]])));
    const xs = all.map((p) => p[0]);
    const xMin = Math.min(...xs), xMax = Math.max(...xs);
    let yMin = cfg.yMin != null ? cfg.yMin : Math.min(...all.map((p) => p[1]));
    let yMax = Math.max(...all.map((p) => p[1]), ...(cfg.hlines || []).map((h) => h.y));
    yMax += (yMax - yMin) * 0.06;
    if (cfg.yMin == null) yMin -= (yMax - yMin) * 0.06;
    const X = (v) => m.l + ((v - xMin) / (xMax - xMin || 1)) * (W - m.l - m.r);
    const Y = (v) => H - m.b - ((v - yMin) / (yMax - yMin || 1)) * (H - m.t - m.b);

    let g = "";
    niceTicks(yMin, yMax, 5).forEach((v) => {
      g += `<line class="tick-y" x1="${m.l}" x2="${W - m.r}" y1="${Y(v)}" y2="${Y(v)}"/><text x="${m.l - 8}" y="${Y(v) + 4}" text-anchor="end">${esc(cfg.yFmt(v))}</text>`;
    });
    g += `<line class="axis" x1="${m.l}" x2="${W - m.r}" y1="${H - m.b}" y2="${H - m.b}"/>`;
    const xt = cfg.xTicks(xMin, xMax);
    xt.forEach((v) => (g += `<line class="axis" x1="${X(v)}" x2="${X(v)}" y1="${H - m.b}" y2="${H - m.b + 4}"/><text x="${X(v)}" y="${H - 8}" text-anchor="middle">${esc((cfg.tickFmt || cfg.xFmt)(v))}</text>`));
    (cfg.bands || []).forEach((b) => {
      const up = b.pts.map((p) => `${X(p[0])},${Y(p[2])}`);
      const dn = b.pts.slice().reverse().map((p) => `${X(p[0])},${Y(p[1])}`);
      g += `<polygon points="${up.concat(dn).join(" ")}" fill="${b.color}" opacity="0.16"/>`;
    });
    (cfg.hlines || []).forEach((h) => {
      g += `<line x1="${m.l}" x2="${W - m.r}" y1="${Y(h.y)}" y2="${Y(h.y)}" stroke="${h.color || "#101a2c"}" stroke-width="2" stroke-dasharray="6 4"/><text x="${W - m.r}" y="${Y(h.y) - 6}" text-anchor="end" style="font-weight:700;fill:#101a2c">${esc(h.label)}</text>`;
    });
    (cfg.vlines || []).forEach((v) => {
      g += `<line x1="${X(v.x)}" x2="${X(v.x)}" y1="${m.t}" y2="${H - m.b}" stroke="#101a2c" stroke-width="1.5" stroke-dasharray="3 3"/><text x="${X(v.x) + (X(v.x) > W * 0.6 ? -6 : 6)}" y="${m.t + 12}" text-anchor="${X(v.x) > W * 0.6 ? "end" : "start"}" style="font-weight:600;fill:#101a2c">${esc(v.label)}</text>`;
    });
    cfg.series.forEach((s) => {
      let d = "", pen = false;
      s.pts.forEach((p) => {
        if (p[1] == null) { pen = false; return; }
        d += `${pen ? "L" : "M"}${X(p[0]).toFixed(1)},${Y(p[1]).toFixed(1)}`;
        pen = true;
      });
      g += `<path d="${d}" fill="none" stroke="${s.color}" stroke-width="${s.width || 2.25}" ${s.dash ? `stroke-dasharray="${s.dash}"` : ""} stroke-linejoin="round" stroke-linecap="round"/>`;
      if (s.dots) s.pts.forEach((p) => p[1] != null && (g += `<circle cx="${X(p[0])}" cy="${Y(p[1])}" r="4" fill="${s.color}" stroke="#f6f7f4" stroke-width="1.5"/>`));
    });
    host.innerHTML = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(cfg.label)}">${g}<g id="cross"></g><rect id="hit" x="${m.l}" y="${m.t}" width="${W - m.l - m.r}" height="${H - m.t - m.b}" fill="transparent"/></svg><div class="tip" hidden></div>${cfg.legend === false ? "" : `<div class="lg" style="display:flex;gap:18px;flex-wrap:wrap;padding:6px 8px 8px;font-size:13px;font-weight:600">${cfg.series.filter((s) => s.name).map((s) => `<span><i style="display:inline-block;width:18px;height:0;border-top:${s.dash ? "3px dashed" : "3px solid"} ${s.color};vertical-align:middle;margin-right:6px"></i>${esc(s.name)}</span>`).join("")}${(cfg.bands || []).map((b) => `<span><i style="display:inline-block;width:14px;height:12px;background:${b.color};opacity:.3;vertical-align:middle;margin-right:6px"></i>${esc(b.name)}</span>`).join("")}</div>`}`;

    const svg = $("svg", host), hit = $("#hit", svg), cross = $("#cross", svg), tip = $(".tip", host);
    const xsSorted = [...new Set(cfg.series.flatMap((s) => s.pts.filter((p) => p[1] != null).map((p) => p[0])))].sort((a, b) => a - b);
    const nearest = (arr, x) => arr.reduce((best, p) => (best == null || Math.abs(p[0] - x) < Math.abs(best[0] - x) ? p : best), null);
    hit.addEventListener("pointermove", (e) => {
      const box = svg.getBoundingClientRect();
      const px = ((e.clientX - box.left) / box.width) * W;
      const x = xMin + ((px - m.l) / (W - m.l - m.r)) * (xMax - xMin);
      const at = xsSorted.reduce((b, v) => (Math.abs(v - x) < Math.abs(b - x) ? v : b), xsSorted[0]);
      const rows = cfg.series.map((s) => ({ s, p: nearest(s.pts.filter((p) => p[1] != null), at) })).filter((r) => r.p && Math.abs(r.p[0] - at) < (xMax - xMin) / 40);
      if (!rows.length) { tip.hidden = true; cross.innerHTML = ""; return; }
      cross.innerHTML = `<line x1="${X(at)}" x2="${X(at)}" y1="${m.t}" y2="${H - m.b}" stroke="#101a2c" stroke-width="1"/>` + rows.map((r) => `<circle cx="${X(r.p[0])}" cy="${Y(r.p[1])}" r="4.5" fill="${r.s.color}" stroke="#101a2c" stroke-width="1.5"/>`).join("");
      tip.hidden = false;
      tip.innerHTML = `<b>${esc(cfg.xFmt(at))}</b>` + rows.map((r) => `<div><i style="background:${r.s.color}"></i>${esc(cfg.tip ? cfg.tip(r.s, r.p) : r.s.name + " " + cfg.yFmt(r.p[1]))}</div>`).join("");
      const w = tip.offsetWidth;
      const left = Math.min(Math.max((X(at) / W) * box.width, w / 2), box.width - w / 2);
      tip.style.left = left + 8 + "px";
      tip.style.top = "8px";
    });
    hit.addEventListener("pointerleave", () => { tip.hidden = true; cross.innerHTML = ""; });
  }

  const redraws = [];
  function track(fn) { redraws.push(fn); fn(); }
  let resizeTimer;
  new ResizeObserver(() => { clearTimeout(resizeTimer); resizeTimer = setTimeout(() => redraws.forEach((f) => f()), 120); }).observe(document.body);

  const ms = (iso) => Date.parse(iso + "T00:00:00Z");
  const yearTicks = (a, b) => {
    const out = [];
    for (let y = new Date(a).getUTCFullYear(); y <= new Date(b).getUTCFullYear() + 1; y++) {
      const t = Date.UTC(y, 0, 1);
      if (t >= a && t <= b) out.push(t);
    }
    return out;
  };
  const quarterTicks = (a, b) => {
    const out = [];
    const y0 = new Date(a).getUTCFullYear();
    for (let y = y0; y <= new Date(b).getUTCFullYear(); y++) for (let q = 0; q < 12; q += 3) { const t = Date.UTC(y, q, 1); if (t >= a && t <= b) out.push(t); }
    return out;
  };

  // ---------------------------------------------------------------- hero and manifest
  const onTime = pct(R.on_time);
  $('[data-bind="hero-ontime"]').textContent = onTime;
  bind("hero-lede", `SupplyPulse reads ${int(R.rows_clean)} order lines from a sports-goods retailer (the public DataCo dataset), keeps ${int(R.orders)} valid orders, and answers five operating questions with a database, a late-delivery model, a demand forecast and an inventory simulation. Every number on this page was produced by code you can run.`);

  const rows = [
    ["Are orders arriving on time?", `<b>${onTime}</b> of ${int(R.orders)} orders were on time. First Class orders were late ${pct(R.late_first_class, 0)} of the time.`, "#delivery", "Delivery"],
    ["Which orders will be late?", `A model reaches <b>ROC-AUC ${R.roc_auc.toFixed(2)}</b> on orders it never saw. Shipping mode alone reaches ${R.roc_auc_mode_only.toFixed(2)}.`, "#delivery", "Delivery"],
    ["How much will each category sell?", `SARIMA forecasts weekly units with <b>${pct(R.wape)} error</b> over ${R.n_categories} categories, ${pct(R.wape_improvement, 0)} better than repeating last year. A plain moving average is ${((R.wape_ma - R.wape) * 100).toFixed(1)} points behind.`, "#demand", "Demand"],
    ["How much safety stock is enough?", `The textbook formula aims for 95% service and delivers <b>${pct(R.textbook_service_95, 0)}</b> once supplier lead times vary.`, "#inventory", "Inventory"],
    ["Can the written review be trusted?", `Every number in it must match a fact from the database. A made-up number is rejected. You can try it.`, "#review", "Review pack"],
  ];
  $("#manifest-rows").innerHTML = rows.map((r, i) => `<a class="m-row" role="row" style="--i:${i}" href="${r[2]}"><span class="m-q" role="cell">${esc(r[0])}</span><span class="m-a" role="cell">${r[1]}</span><span class="m-go" role="cell">${r[3]}</span></a>`).join("");

  // ---------------------------------------------------------------- business
  bind("business-text", `Monthly figures for valid orders. ${pct(R.excluded_share)} of order lines were cancelled or suspected fraud, so they are flagged and left out of every analysis.`);
  const METRICS = [
    { key: "revenue", label: "Revenue", fmt: usdShort, tip: usd, min: 0 },
    { key: "orders", label: "Orders", fmt: (v) => int(v), tip: int, min: 0 },
    { key: "margin_pct", label: "Margin", fmt: (v) => v.toFixed(0) + "%", tip: (v) => v.toFixed(1) + "%", min: 0 },
    { key: "on_time_pct", label: "On time", fmt: (v) => v.toFixed(0) + "%", tip: (v) => v.toFixed(1) + "%", min: 0 },
  ];
  let metric = METRICS[0];
  $("#business-metric").innerHTML = METRICS.map((mt, i) => `<button type="button" data-k="${mt.key}" aria-pressed="${i === 0}">${mt.label}</button>`).join("");
  $("#business-metric").addEventListener("click", (e) => {
    const b = e.target.closest("button");
    if (!b) return;
    metric = METRICS.find((mt) => mt.key === b.dataset.k);
    $("#business-metric").querySelectorAll("button").forEach((x) => x.setAttribute("aria-pressed", x === b));
    drawBusiness();
  });
  function drawBusiness() {
    lineChart($("#business-chart"), {
      label: `${metric.label} by month`,
      series: [{ name: metric.label, color: "#101a2c", dots: true, width: 2.5, pts: D.monthly.map((r) => [ms(r.month), r[metric.key]]) }],
      vlines: [{ x: ms(R.cutoff), label: `Volume drops ${pct(R.tail_drop_pct, 0)}` }],
      yMin: metric.min, yFmt: metric.fmt, xFmt: monthLabel, xTicks: yearTicks, tip: (s, p) => `${metric.label} ${metric.tip(p[1])}`, legend: false,
    });
  }
  track(drawBusiness);
  $("#business-figs").innerHTML = [
    ["Revenue", usd(R.revenue), "valid orders, Jan 2015 to Jan 2018"],
    ["Profit", usd(R.profit), `${pct(R.margin)} margin`],
    ["On-time delivery", onTime, `${int(R.orders)} orders`],
    ["Loss-making items", pct(R.loss_items_share), `they erase ${pct(R.loss_vs_gross_profit, 0)} of gross profit; 10 products hold ${pct(R.loss_top10_products, 0)} of the loss`],
  ].map(([t, v, s]) => `<div><dt>${t}</dt><dd>${v}<small>${s}</small></dd></div>`).join("");

  // ---------------------------------------------------------------- delivery
  bind("delivery-text", `Shipping mode explains most of lateness. A model adds a little on top, and a threshold decides how many alerts you are willing to chase.`);
  $("#mode-bars").innerHTML = D.delivery.by_mode.map((m) => barRow({ label: m.shipping_mode, sub: `${m.scheduled_days === 0 ? "same day" : m.scheduled_days + (m.scheduled_days === 1 ? " day" : " days")} promised, ${int(m.orders)} orders`, value: m.late, shown: pct(m.late, 0), cls: "late" })).join("");
  const hj = D.delivery.hour_jump[0];
  if (hj) {
    $("#hour-note").innerHTML = `${esc(hj.shipping_mode)} orders placed before noon are late <b>${pct(hj.late_before, 0)}</b> of the time (${int(hj.orders_before)} orders). From noon on, <b>${pct(hj.late_after, 0)}</b> are (${int(hj.orders_after)} orders). Real carriers do not behave like a switch, which is one sign this dataset is synthetic.`;
  }

  const chosen = R.risk_champion;
  const RM = D.risk.metrics[chosen];
  const scores = D.risk.scores.s;
  const labels = D.risk.scores.y;
  const n = scores.length;
  const lateTotal = [...labels].reduce((a, c) => a + (c === "1" ? 1 : 0), 0);
  const thr = $("#thr");
  const chosenThr = Math.round(RM.threshold * 1000);
  thr.value = chosenThr;
  $("#thr-reset").textContent = `Use the threshold picked on validation data (${RM.threshold.toFixed(2)})`;
  function drawAlerts() {
    const t = +thr.value;
    $("#thr-out").textContent = (t / 1000).toFixed(2);
    let tp = 0, fp = 0;
    for (let i = 0; i < n; i++) if (scores[i] >= t) (labels[i] === "1" ? tp++ : fp++);
    const fn = lateTotal - tp, tn = n - lateTotal - fp;
    const precision = tp + fp ? tp / (tp + fp) : null;
    const recall = tp / lateTotal;
    const cell = (cls, big, small) => `<div class="cell ${cls}"><b>${int(big)}</b><span>${small}</span></div>`;
    $("#matrix").innerHTML = `<span></span><span class="h">Flagged late</span><span class="h">Not flagged</span>
      <span class="h rh">Actually late</span>${cell("good", tp, "caught")}${cell("bad", fn, "missed")}
      <span class="h rh">Actually on time</span>${cell("bad", fp, "false alarms")}${cell("good", tn, "correctly left alone")}`;
    $("#alert-figs").innerHTML = [
      ["Precision", precision == null ? "n/a" : pct(precision), "of flagged orders really were late"],
      ["Recall", pct(recall), "of late orders were flagged"],
      ["Flagged", pct((tp + fp) / n, 0), `of ${int(n)} test orders`],
      ["Base rate", pct(lateTotal / n), "of test orders were late"],
    ].map(([a, b, c]) => `<div><dt>${a}</dt><dd>${b}<small>${c}</small></dd></div>`).join("");
  }
  thr.addEventListener("input", drawAlerts);
  $("#thr-reset").addEventListener("click", () => { thr.value = chosenThr; drawAlerts(); });
  drawAlerts();

  const aucs = ["shipping_mode_only", "logistic", "lightgbm"].map((k) => [k, D.risk.metrics[k].roc_auc]);
  $("#auc-bars").innerHTML = aucs.map(([k, v]) => barRow({ label: modelName(k), sub: "ROC-AUC on test orders", value: v, shown: v.toFixed(3), min: 0.5, max: 1, cls: k === chosen ? "hi" : "" })).join("");
  const gain = D.risk.metrics[chosen].roc_auc - D.risk.metrics.shipping_mode_only.roc_auc;
  $("#auc-note").innerHTML = `Bars start at 0.5, which is a coin flip. Knowing only the shipping mode gets <b>${D.risk.metrics.shipping_mode_only.roc_auc.toFixed(3)}</b>; the full model adds <b>${gain.toFixed(3)}</b>. The honest summary is a useful model whose lift over a one-column baseline is modest.`;
  $("#driver-bars").innerHTML = D.risk.drivers.map((d) => barRow({ label: cap(d.feature.replace(/_/g, " ")), value: d.share, shown: pct(d.share, 0), max: D.risk.drivers[0].share * 1.05 })).join("");

  // ---------------------------------------------------------------- demand
  const F = D.forecast;
  bind("demand-text", `Each category gets a weekly forecast, tested the way it would be used: train on the past, predict the next ${F.horizon_weeks} weeks, repeat ${F.folds} times. Forecasts end at ${dayLabel(F.cutoff)}, where weekly volume in this dataset falls by about ${pct(R.tail_drop_pct, 0)} for reasons the data does not explain.`);
  const cats = Object.keys(F.categories).sort();
  const catSel = $("#cat");
  catSel.innerHTML = cats.map((c) => `<option>${esc(c)}</option>`).join("");
  function drawDemand() {
    const c = F.categories[catSel.value];
    const showBack = $("#show-back").checked;
    const dedupe = (rowsIn) => { const m = new Map(); rowsIn.forEach((r) => m.set(r[0], r)); return [...m.values()].sort((a, b) => a[0].localeCompare(b[0])); };
    const back = dedupe(c.backtest);
    const series = [{ name: "Actual units per week", color: "#101a2c", width: 2, pts: c.history.map((r) => [ms(r[0]), r[1]]) }];
    if (showBack) series.push({ name: `Backtest (${modelName(F.champion)})`, color: "#2b5c9e", dash: "5 4", width: 2.25, pts: back.map((r) => [ms(r[0]), r[2], "bt"]) });
    series.push({ name: `Forecast (${modelName(F.champion)})`, color: "#2b5c9e", width: 2.75, pts: c.forecast.map((r) => [ms(r[0]), r[1], "fc"]) });
    lineChart($("#demand-chart"), {
      label: `Weekly units for ${catSel.value}: history, backtest and forecast`,
      series,
      bands: [{ name: `${pct(D.assumptions.interval_level, 0)} prediction interval`, color: "#2b5c9e", pts: c.forecast.map((r) => [ms(r[0]), r[2], r[3]]) }],
      vlines: [{ x: ms(F.cutoff), label: "Forecast starts" }],
      yFmt: (v) => int(v), xFmt: dayLabel, tickFmt: monthLabel, xTicks: quarterTicks, tip: (s, p) => `${s.name.split(" (")[0]}: ${int(p[1])} units`, legend: true,
    });
    $("#demand-note").innerHTML = `${esc(catSel.value)}: ${modelName(F.champion)} is wrong by <b>${pct(c.wape)}</b> on average in the backtest (WAPE, error as a share of units sold). The forecast is a central estimate with a band, not a promise.`;
  }
  catSel.addEventListener("change", drawDemand);
  $("#show-back").addEventListener("change", drawDemand);
  track(drawDemand);
  const maxW = Math.max(...F.models.map((m) => m.wape));
  $("#model-bars").innerHTML = F.models.slice().sort((a, b) => a.wape - b.wape).map((m) => barRow({ label: modelName(m.model), sub: m.model === F.champion ? "champion" : "", value: m.wape, shown: pct(m.wape), max: maxW * 1.08, cls: m.model === F.champion ? "hi" : "" })).join("");
  $("#model-note").innerHTML = `Lower is better. The champion beats the seasonal-naive baseline by <b>${pct(R.wape_improvement, 0)}</b>, but a moving average is only <b>${((R.wape_ma - R.wape) * 100).toFixed(1)} points</b> behind, which is inside the noise of a ${F.folds}-fold backtest. A simple model is a fair choice here.`;

  // ---------------------------------------------------------------- inventory
  const A = D.assumptions;
  bind("inventory-text", `The textbook formula assumes supplier lead time is fixed. Simulating ${int(A.paths)} years of weekly orders with lead times of ${A.lead_time_weeks.join(", ")} weeks shows how far the formula falls short, and what closing the gap costs.`);
  const icats = Object.keys(D.inventory).sort();
  $("#icat").innerHTML = icats.map((c) => `<option>${esc(c)}</option>`).join("");
  const targets = [...new Set(D.inventory[icats[0]].grid.map((g) => g.analytic_service_target).filter((v) => v != null))].sort();
  $("#svc").innerHTML = targets.map((t) => `<option value="${t}" ${t === 0.95 ? "selected" : ""}>${pct(t, 0)}</option>`).join("");
  function drawInventory() {
    const cat = D.inventory[$("#icat").value];
    const target = +$("#svc").value;
    const text = cat.grid.filter((g) => g.basis === "textbook");
    const aware = cat.grid.filter((g) => g.basis === "lead_time_aware").sort((a, b) => a.holding_cost - b.holding_cost);
    const tb = text.find((g) => g.analytic_service_target === target);
    const fix = aware.find((g) => g.cycle_service_level >= target);
    const miss = tb.cycle_service_level < target - 0.005;
    const extra = fix ? fix.holding_cost / tb.holding_cost - 1 : null;
    $("#inv-read").innerHTML = `
      <div class="${miss ? "miss" : "hit"}"><h4>Textbook formula for ${pct(target, 0)}</h4><b>${pct(tb.cycle_service_level, 1)}</b>
        <p>simulated service with ${int(tb.safety_stock)} units of safety stock, holding cost ${usd(tb.holding_cost)} a year.</p></div>
      <div class="hit"><h4>Sized for lead-time variability</h4>${fix ? `<b>${int(fix.safety_stock)} units</b>
        <p>reaches ${pct(fix.cycle_service_level, 1)} simulated service at ${usd(fix.holding_cost)} a year (${extra >= 0 ? "+" : ""}${pct(extra, 0)} versus the textbook stock).</p>` : `<b>not reached</b><p>no tested stock level reaches ${pct(target, 0)}.</p>`}</div>`;
    const pts = (rowsIn) => rowsIn.map((g) => [g.holding_cost, g.cycle_service_level, g.safety_stock]);
    lineChart($("#inv-chart"), {
      label: "Simulated service level against yearly holding cost",
      series: [
        { name: "Textbook formula", color: "#c8381f", dots: true, pts: pts(text.slice().sort((a, b) => a.holding_cost - b.holding_cost)) },
        { name: "Sized for lead-time variability", color: "#1e7b5c", dots: true, pts: pts(aware) },
      ],
      hlines: [{ y: target, label: `You asked for ${pct(target, 0)}` }],
      yMin: Math.min(0.5, ...aware.map((g) => g.cycle_service_level)), left: 56,
      yFmt: (v) => pct(v, 0), xFmt: (v) => usd(v), xTicks: (a, b) => niceTicks(a, b, 5),
      tip: (s, p) => `${s.name}: ${int(p[2])} units, ${pct(p[1], 1)} service`, legend: true,
    });
    $("#inv-note").innerHTML = `Service here means the share of replenishment cycles with no stockout. Assumptions, not measurements: lead times of ${A.lead_time_weeks.join(", ")} weeks with probabilities ${A.lead_time_probs.map((p) => pct(p, 0)).join(", ")}, and a holding cost of ${pct(A.holding_cost_pct_per_week, 1)} of unit cost per week.`;
  }
  $("#icat").addEventListener("change", drawInventory);
  $("#svc").addEventListener("change", drawInventory);
  track(drawInventory);

  // ---------------------------------------------------------------- review pack
  bind("review-text", `A language model drafts the monthly review from a fixed list of facts. A checker then reads every line: each number must match a fact cited on that line, or the draft is rejected. Click any number or citation to see its source.`);

  const CITE = /\[(F\d+)\]/g;
  const NUM = /(?<![A-Za-z0-9])\$?[-−]?\d[\d,]*(?:\.\d+)?%?/g;
  // a bare four-digit number is a year only if some fact's period names it (the same rule as grounding.py)
  const isYear = (tok, years) => years.has(tok);

  /** Numbers in a line that no cited fact supports (same rule as src/sca/grounding.py, re-implemented for this page). */
  function checkLine(text, facts, years) {
    const cited = [...text.matchAll(CITE)].map((m) => m[1]);
    const pool = facts.filter((f) => cited.includes(f.id));
    const stripped = text.replace(CITE, " ");
    const results = [];
    for (const m of stripped.matchAll(NUM)) {
      const raw = m[0];
      const cleanTok = raw.replace(/[$,%]/g, "").replace("−", "-");
      const val = parseFloat(cleanTok);
      const dec = (cleanTok.split(".")[1] || "").length;
      let ok = false, fact = null;
      if (isYear(cleanTok, years)) {
        ok = true;
      } else {
        for (const f of pool) {
          const cands = [f.value, f.comparison_value, f.delta].filter((v) => typeof v === "number");
          if (cands.some((c) => Math.abs(+c.toFixed(dec) - val) < 1e-9 || Math.abs(+Math.abs(c).toFixed(dec) - Math.abs(val)) < 1e-9)) { ok = true; fact = f; break; }
        }
      }
      results.push({ raw, ok, fact, index: m.index });
    }
    return { cited, results };
  }

  const packSel = $("#pack");
  packSel.innerHTML = D.packs.map((p, i) => `<option value="${i}">${new Date(p.period + "-01T00:00:00Z").toLocaleDateString("en-US", { month: "long", year: "numeric", timeZone: "UTC" })}</option>`).join("");

  let blocks = [], tampered = null, pack = null, years = new Set();
  function parseBlocks(md) {
    const out = [];
    for (const line of md.split(/\r?\n/)) {
      if (/^---\s*$/.test(line)) break;
      if (/^# /.test(line) || !line.trim()) continue;
      if (/^## /.test(line)) out.push({ t: "h", text: line.slice(3).trim() });
      else if (/^\s*(?:[-*+]\s+)?\d+[.)]\s+/.test(line)) out.push({ t: "li", ordered: true, text: line.replace(/^\s*(?:[-*+]\s+)?\d+[.)]\s+/, "") });
      else if (/^\s*[-*+]\s+/.test(line)) out.push({ t: "li", text: line.replace(/^\s*[-*+]\s+/, "") });
      else out.push({ t: "p", text: line.trim() });
    }
    return out;
  }
  function loadPack() {
    pack = D.packs[+packSel.value];
    tampered = null;
    years = new Set();
    pack.facts.forEach((f) => [f.period, f.comparison_period].forEach((s) => (String(s || "").match(/\d{4}/g) || []).forEach((y) => years.add(y))));
    blocks = parseBlocks(pack.markdown);
    const v = pack.validation;
    const who = v.mode === "llm" ? `Written by ${cap(v.provider)}` : "Template text";
    $("#pack-origin").textContent = `${who}, number-checked`;
    $("#pack-origin").className = "pill " + (v.mode === "llm" ? "llm" : "");
    drawAttempts();
    drawPaper();
    $("#fact").innerHTML = `<h4>Source of a number</h4><p class="muted">Click a number or a citation such as [F1] in the text above.</p>`;
  }

  function lineHtml(b, bi) {
    const info = checkLine(b.text, pack.facts, years);
    const parts = b.text.split(/(\*\*[^*]+\*\*)/g).filter(Boolean);
    let html = "", offset = 0;
    const renderPlain = (seg) => {
      let out = "", last = 0;
      const tokens = [...seg.matchAll(new RegExp(CITE.source + "|" + NUM.source, "g"))];
      for (const t of tokens) {
        out += esc(seg.slice(last, t.index));
        last = t.index + t[0].length;
        if (t[1]) { out += `<button type="button" class="cite" data-fact="${t[1]}" data-block="${bi}" aria-label="Fact ${t[1]}">${t[1]}</button>`; continue; }
        const cleanTok = t[0].replace(/[$,%]/g, "");
        if (isYear(cleanTok, years)) { out += esc(t[0]); continue; }
        const r = info.results.find((x) => x.raw === t[0] && !x.used);
        if (r) r.used = true;
        const bad = r && !r.ok;
        out += `<button type="button" class="num ${bad ? "bad" : ""}" data-block="${bi}" data-num="${esc(t[0])}" ${bad ? 'data-bad="1"' : ""}>${esc(t[0])}</button>`;
      }
      return out + esc(seg.slice(last));
    };
    parts.forEach((seg) => {
      html += /^\*\*/.test(seg) ? `<strong>${renderPlain(seg.slice(2, -2))}</strong>` : renderPlain(seg);
      offset += seg.length;
    });
    return { html, info };
  }

  function drawPaper() {
    let html = "", total = 0, bad = 0, firstBad = null;
    let inList = false;
    blocks.forEach((b, bi) => {
      const text = tampered && tampered.block === bi ? tampered.text : b.text;
      const { html: h, info } = lineHtml({ text }, bi);
      const lineBad = info.results.filter((r) => !r.ok).length;
      total += info.results.filter((r) => !isYear(r.raw, years)).length;
      bad += lineBad;
      if (lineBad && firstBad == null) firstBad = { b, info };
      if (inList && (b.t !== "li" || !!b.ordered !== inList.ordered)) { html += inList.ordered ? "</ol>" : "</ul>"; inList = false; }
      if (b.t === "h") html += `<h4>${esc(b.text)}</h4>`;
      else if (b.t === "li") { if (!inList) { html += b.ordered ? "<ol>" : "<ul>"; inList = { ordered: !!b.ordered }; } html += `<li><span class="line ${lineBad ? "rejected" : ""}">${h}</span></li>`; }
      else html += `<p><span class="line ${lineBad ? "rejected" : ""}">${h}</span></p>`;
    });
    if (inList) html += inList.ordered ? "</ol>" : "</ul>";
    $("#paper").innerHTML = html;
    const bar = $("#check-bar");
    bar.classList.toggle("fail", bad > 0);
    bar.innerHTML = bad === 0
      ? `${total} of ${total} numbers match a fact cited on the same line.<small>This page re-implements the rule from src/sca/grounding.py so you can try it here.</small>`
      : `${total - bad} of ${total} numbers match. ${bad} ${bad === 1 ? "does" : "do"} not, so this draft would be rejected.<small>The pipeline would send the model the error once, then fall back to the template text, which passes the same check.</small>`;
    $("#restore").hidden = !tampered;
    $("#tamper").hidden = !!tampered;
  }

  function showFact(id, token, bad) {
    const f = pack.facts.find((x) => x.id === id);
    if (bad) {
      $("#fact").innerHTML = `<h4>No cited fact says this</h4><p><b>${esc(token)}</b></p><p class="muted">The facts cited on this line do not contain that number, so the check rejects the line.</p>`;
      return;
    }
    if (!f) return;
    const unit = (v) => (f.unit === "USD" ? "$" + v.toLocaleString("en-US", { maximumFractionDigits: 2 }) : f.unit === "%" ? v + "%" : f.unit === "pp" ? v + " pp" : `${typeof v === "number" ? v.toLocaleString("en-US") : v} ${f.unit || ""}`.trim());
    const cmp = f.comparison_value != null ? `<p class="muted">Compared with ${esc(unit(f.comparison_value))} (${esc(f.comparison_period || "")})${f.delta != null ? `; change ${f.delta > 0 ? "+" : ""}${f.delta}${f.delta_unit === "%" ? "%" : " " + (f.delta_unit || "")}` : ""}</p>` : "";
    $("#fact").innerHTML = `<h4>${esc(f.id)}: ${esc(f.metric)}</h4><p><b>${esc(typeof f.value === "number" ? unit(f.value) : f.value)}</b> <span class="muted">for ${esc(f.period)}</span></p>${cmp}
      <p class="muted">From <code>sql/sqlserver/kpi_queries/${esc(f.source_query)}.sql</code>, query checksum <code>${esc(pack.query_checksum)}</code></p>`;
  }

  $("#paper").addEventListener("click", (e) => {
    const btn = e.target.closest("button");
    if (!btn) return;
    $("#paper").querySelectorAll("[aria-pressed]").forEach((x) => x.removeAttribute("aria-pressed"));
    btn.setAttribute("aria-pressed", "true");
    const bi = +btn.dataset.block;
    const text = tampered && tampered.block === bi ? tampered.text : blocks[bi].text;
    if (btn.dataset.bad) { showFact(null, btn.textContent, true); return; }
    if (btn.dataset.fact) { showFact(btn.dataset.fact); return; }
    const info = checkLine(text, pack.facts, years);
    const hit = info.results.find((r) => r.raw === btn.dataset.num && r.fact);
    if (hit) showFact(hit.fact.id);
  });

  $("#tamper").addEventListener("click", () => {
    for (let bi = 0; bi < blocks.length; bi++) {
      const b = blocks[bi];
      if (b.t === "h" || !CITE.test(b.text)) { CITE.lastIndex = 0; continue; }
      CITE.lastIndex = 0;
      const info = checkLine(b.text, pack.facts, years);
      const target = info.results.find((r) => !isYear(r.raw.replace(/[$,%]/g, ""), years));
      if (!target) continue;
      const cleanTok = target.raw.replace(/[$,%]/g, "");
      const dec = (cleanTok.split(".")[1] || "").length;
      for (const k of [1.18, 1.37, 0.71]) {
        const num = parseFloat(cleanTok.replace(",", "")) * k;
        const fake = (target.raw.startsWith("$") ? "$" : "") + num.toLocaleString("en-US", { minimumFractionDigits: dec, maximumFractionDigits: dec }) + (target.raw.endsWith("%") ? "%" : "");
        const text = b.text.slice(0, target.index) + fake + b.text.slice(target.index + target.raw.length);
        tampered = { block: bi, text, fake };
        if (checkLine(text, pack.facts, years).results.some((r) => !r.ok)) break;
        tampered = null;
      }
      if (tampered) break;
    }
    drawPaper();
    if (tampered) { $("#fact").innerHTML = `<h4>You changed a number</h4><p>Now it reads <b>${esc(tampered.fake)}</b>.</p><p class="muted">No fact cited on that line says so. Click the red number to see what the check reports.</p>`; }
  });
  $("#restore").addEventListener("click", () => { tampered = null; drawPaper(); $("#fact").innerHTML = `<h4>Source of a number</h4><p class="muted">Click a number or a citation such as [F1] in the text above.</p>`; });
  packSel.addEventListener("change", loadPack);

  function drawAttempts() {
    const v = pack.validation;
    const items = v.attempts.map((a) => {
      const who = cap(a.provider || "model");
      if (a.error) return `<li class="fail">${who}: request failed (${esc((a.error.match(/(\d{3}) ([A-Z_]+)/) || [, "error", ""]).slice(1).join(" ").trim())}).</li>`;
      if (a.ok) return `<li class="pass">${who}: draft passed, ${a.numbers_checked} numbers checked.</li>`;
      return `<li class="fail">${who}: draft rejected, ${esc((a.offending_numbers || []).join(", ") || "uncited line")} not supported by a cited fact.</li>`;
    });
    if (v.mode === "template") items.push(`<li class="pass">Fell back to the deterministic template, which passes the same check${v.reason ? ` (${esc(v.reason)})` : ""}.</li>`);
    $("#attempts").innerHTML = `<summary>How this text was produced (${v.attempts.length} model ${v.attempts.length === 1 ? "attempt" : "attempts"})</summary><ol>${items.join("")}</ol>`;
  }
  loadPack();

  // ---------------------------------------------------------------- trust
  bind("trust-text", `A project is only as useful as its limits are clear. These are the ones I know about.`);
  $("#trust-figs").innerHTML = [
    ["Automated data checks", int(R.dq_checks), `${R.dq_failing_errors} failures at error level, ${R.dq_failing_warnings} warnings`],
    ["Tests", int(R.tests), "including a leakage guard and a simulation check against a known answer"],
    ["Rows kept", int(R.rows_clean), `of ${int(R.rows_raw)}; cancelled and fraud orders are flagged, not deleted`],
    ["DAX measures", int(R.dax_measures), "written and tested against the schema"],
  ].map(([t, v, s]) => `<div><dt>${t}</dt><dd>${v}<small>${s}</small></dd></div>`).join("");
  const limits = [
    `The dataset looks synthetic. Same Day orders switch from 0% to 100% late at noon, and margin barely moves with discount (R-squared ${R.discount_r2.toFixed(3)}), so the findings say more about the method than about retail.`,
    `The simulation's costs and supplier lead times are assumptions, not measurements. Change them in config.yaml and rerun.`,
    `The discount and margin regression shows association, not cause.`,
    `Weekly volume falls by about ${pct(R.tail_drop_pct, 0)} after ${dayLabel(R.cutoff)} and the data does not say why, so forecasts stop there.`,
    `The backtest is ${R.folds} windows of ${R.horizon_weeks || F.horizon_weeks} weeks. SARIMA beating a moving average by ${((R.wape_ma - R.wape) * 100).toFixed(1)} points is inside that noise.`,
    `The number check proves every number in the review matches a fact. It does not prove the wording is right, so the text is a draft for a person to read.`,
    `The Power BI report is not built; the measures, theme and page specs are in dashboard/. The SQL Server load through pyodbc has not been run on this machine; the T-SQL was validated on SQL Server 2022 in Docker and the pipeline runs on SQLite.`,
  ];
  $("#limits").innerHTML = limits.map((l) => `<li>${esc(l)}</li>`).join("");
})();
