/* ==========================================================================
   Trend Intelligence — dashboard
   Vanilla JS, no build step. The deployed site is a static copy; the data is
   fetched at runtime from the raw file host so the dashboard updates without
   a redeploy.
   ========================================================================== */

(function () {
  "use strict";

  // Where fresh data lives. The bundled copy (./data/latest.json) is the
  // fallback so the site is never blank.
  var REMOTE = "https://raw.githubusercontent.com/ola-kunle/trend-intel/data/data/latest.json";
  var LOCAL = "./data/latest.json";
  var REMOTE_VALIDATION = "https://raw.githubusercontent.com/ola-kunle/trend-intel/data/data/validation.json";
  var LOCAL_VALIDATION = "./data/validation.json";

  var S = {
    data: null,
    filtered: [],
    filters: { q: "", category: "", geo: "", source: "", lifecycle: "", confidence: "", tier: "", minscore: 0 },
    byKey: {}
  };

  var $ = function (sel, root) { return (root || document).querySelector(sel); };
  var $$ = function (sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); };

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function num(n, dp) {
    if (n == null || isNaN(n)) return "—";
    var v = Number(n);
    if (Math.abs(v) >= 1000000) return (v / 1000000).toFixed(1) + "M";
    if (Math.abs(v) >= 1000) return (v / 1000).toFixed(1) + "k";
    return v.toFixed(dp == null ? 0 : dp);
  }

  function pct(n) {
    if (n == null || isNaN(n)) return "—";
    return (Number(n) * 100).toFixed(0) + "%";
  }

  function ago(iso) {
    if (!iso) return "—";
    var t = Date.parse(iso);
    if (isNaN(t)) return "—";
    var d = (Date.now() - t) / 1000;
    if (d < 90) return Math.round(d) + "s ago";
    if (d < 5400) return Math.round(d / 60) + "m ago";
    if (d < 172800) return Math.round(d / 3600) + "h ago";
    return Math.round(d / 86400) + "d ago";
  }

  function fmtTime(iso) {
    if (!iso) return "—";
    var d = new Date(iso);
    if (isNaN(d.getTime())) return "—";
    return d.toISOString().replace("T", " ").slice(0, 16) + "Z";
  }

  /* ---------------------------------------------------------------- data */

  /* ---------------------------------------------------------------- data */

  // A fetch that stalls without erroring would otherwise leave the page on
  // "loading…" forever, because the render waited for the remote copy. Every
  // request therefore carries a timeout, and the page renders from whichever
  // copy arrives first.
  function fetchWithTimeout(url, ms, opts) {
    var ctrl = (typeof AbortController !== "undefined") ? new AbortController() : null;
    var timer = setTimeout(function () { if (ctrl) ctrl.abort(); }, ms);
    var o = opts || {};
    if (ctrl) o.signal = ctrl.signal;
    return fetch(url, o)
      .then(function (r) { return r.ok ? r.json() : null; })
      .catch(function () { return null; })
      .then(function (v) { clearTimeout(timer); return v; });
  }

  function ts(d) { return d ? (Date.parse(d.generated_at) || 0) : 0; }

  function applyData(d, state) {
    if (!d) return false;
    var err = $("#load-error");
    if (err) err.classList.add("hidden");
    // Never downgrade to older data.
    if (S.data && ts(d) < ts(S.data)) return false;
    S.data = d;
    setFeed(state, d);
    populateFilters();
    applyFilters();
    document.body.classList.add("data-loaded");
    hideSkeleton();
    return true;
  }

  function loadData(force) {
    showSkeleton();
    var stamp = force ? ("?t=" + Date.now()) : "";
    var localP = fetchWithTimeout(LOCAL + (force ? stamp : ""), 8000,
      { cache: force ? "reload" : "default" });
    var remoteP = fetchWithTimeout(REMOTE + stamp, 8000,
      { cache: force ? "reload" : "no-cache" });

    // Render from whichever arrives first; upgrade if the other is newer.
    localP.then(function (loc) { if (loc) applyData(loc, "bundled"); });
    remoteP.then(function (rem) { if (rem) applyData(rem, "live"); });

    return Promise.all([localP, remoteP]).then(function (res) {
      var loc = res[0], rem = res[1];
      if (rem && loc) {
        applyData(ts(rem) >= ts(loc) ? rem : loc, ts(rem) >= ts(loc) ? "live" : "bundled");
      } else if (rem) {
        applyData(rem, "live");
      } else if (loc) {
        applyData(loc, "bundled");
      } else {
        showError("Could not reach the live data host and no bundled snapshot was available.");
      }
      return S.data;
    }).catch(function (err) {
      showError(err && err.message ? err.message : "Unknown error");
      return null;
    });
  }

  function setFeed(state, data) {
    var el = $("#meta-feed");
    if (!el) return;
    var age = data && data.generated_at ? (Date.now() - Date.parse(data.generated_at)) / 3600000 : null;
    var cls = "feed-state ", txt = state;
    if (state === "live") {
      if (age != null && age > 6) { cls += "stale"; txt = "live \u00b7 stale"; }
      else { cls += "live"; txt = "live"; }
    } else if (state === "bundled") {
      cls += "stale"; txt = "bundled copy";
    } else {
      cls += "err"; txt = "unavailable";
    }
    el.className = cls;
    el.textContent = txt;
    if (data && data.generated_at) {
      $("#meta-updated").textContent = fmtTime(data.generated_at) + "  (" + ago(data.generated_at) + ")";
    }
    var strip = $("#strip-updated");
    if (strip && data && data.generated_at) strip.textContent = "data through " + fmtTime(data.generated_at);
  }

  function showSkeleton() {
    document.body.classList.remove("data-loaded");
    var el = $("#skeleton");
    if (el) el.classList.remove("hidden");
  }

  function hideSkeleton() {
    var el = $("#skeleton");
    if (el) el.classList.add("hidden");
  }

  function showError(msg) {
    hideSkeleton();
    var el = $("#load-error");
    if (!el) return;
    el.classList.remove("hidden");
    $("#load-error-msg").textContent = msg || "Unknown error";
    setFeed("error", null);
  }

  /* ------------------------------------------------------------- filters */

  function applyFilters() {
    var f = S.filters;
    var q = f.q.toLowerCase().trim();
    S.filtered = (S.data.trends || []).filter(function (t) {
      if (f.category && t.category !== f.category) return false;
      if (f.tier && t.evidence_tier !== f.tier) return false;
      if (f.lifecycle && t.lifecycle !== f.lifecycle) return false;
      if (f.confidence && (t.confidence || {}).level !== f.confidence) return false;
      if (f.geo && (t.geos || []).indexOf(f.geo) < 0) return false;
      if (f.source && (t.sources || []).indexOf(f.source) < 0) return false;
      if (f.minscore && (t.momentum_score || 0) < f.minscore) return false;
      if (q) {
        var hay = (t.name + " " + (t.category_label || "") + " " + (t.sources || []).join(" ") + " " +
          (t.questions || []).map(function (x) { return x.text; }).join(" ") + " " +
          (t.opportunities || []).map(function (x) { return x.angle; }).join(" ")).toLowerCase();
        if (hay.indexOf(q) < 0) return false;
      }
      return true;
    });
    renderAll();
  }

  /* -------------------------------------------------------------- render */

  function sparkline(series, w, h) {
    w = w || 190; h = h || 34;
    if (!series || series.length < 2) {
      return '<svg class="spark" viewBox="0 0 ' + w + ' ' + h + '"><line class="zero" x1="0" y1="' + (h / 2) + '" x2="' + w + '" y2="' + (h / 2) + '"/></svg>';
    }
    var vals = series.map(function (p) { return p.v; });
    var max = Math.max.apply(null, vals), min = Math.min.apply(null, vals);
    if (max === min) { max = min + 1; }
    var n = series.length;
    var pts = series.map(function (p, i) {
      var x = (i / (n - 1)) * (w - 2) + 1;
      var y = h - 2 - ((p.v - min) / (max - min)) * (h - 5);
      return [x, y];
    });
    var d = pts.map(function (p, i) { return (i ? "L" : "M") + p[0].toFixed(1) + " " + p[1].toFixed(1); }).join(" ");
    var area = d + " L" + pts[pts.length - 1][0].toFixed(1) + " " + h + " L" + pts[0][0].toFixed(1) + " " + h + " Z";
    return '<svg class="spark" viewBox="0 0 ' + w + ' ' + h + '" preserveAspectRatio="none">' +
      '<path class="area" d="' + area + '"/><path class="line" d="' + d + '"/></svg>';
  }

  function whyLine(t) {
    var bits = [];
    var obs = t.observations || 0;
    var src = t.cross_source_count || 0;
    var surfaces = t.surface_count || 0;
    bits.push("<b>" + obs + "</b> observation" + (obs === 1 ? "" : "s") + " across <b>" + src + "</b> source" + (src === 1 ? "" : "s") + " and <b>" + surfaces + "</b> surface" + (surfaces === 1 ? "" : "s"));
    if (t.has_baseline && t.acceleration != null) {
      var a = t.acceleration;
      bits.push("acceleration <b>" + (a >= 0 ? "+" : "") + pct(a) + "</b> against its own baseline");
    } else {
      bits.push("<b>no baseline yet</b> — reported as newly observed, not as a trend");
    }
    if (t.creator_count) bits.push("<b>" + t.creator_count + "</b> distinct creators observed");
    if (t.total_views) bits.push("<b>" + num(t.total_views) + "</b> cumulative views observed");
    return bits.join(" · ");
  }

  function card(t) {
    var conf = t.confidence || { level: "low", reasons: [] };
    var tier = t.evidence_tier || "adjacent";
    var tierLabel = t.evidence_tier_label || tier;
    var badges = [];
    badges.push('<span class="badge lifecycle ' + esc(t.lifecycle) + '">' + esc(t.lifecycle_label || t.lifecycle) + "</span>");
    badges.push('<span class="badge conf-' + esc(conf.level) + '">confidence: ' + esc(conf.level) + "</span>");
    badges.push('<span class="badge tier-' + esc(tier) + '">' + esc(tierLabel) + "</span>");
    if (t.discovered) badges.push('<span class="badge src">newly discovered</span>');
    if (t.first_seen_recent) badges.push('<span class="badge src">first seen &lt; 24h</span>');

    var srcBadges = (t.sources || []).slice(0, 6).map(function (s) {
      return '<span class="badge src">' + esc(SOURCE_SHORT[s] || s) + "</span>";
    }).join("");

    var angles = (t.opportunities || []).slice(0, 3).map(function (a) {
      return '<div class="angle">' + esc(a.angle) +
        (a.flagged ? '<span class="flag">' + esc(a.flagged) + "</span>" : "") + "</div>";
    }).join("");

    return '<article class="card" data-key="' + esc(t.key) + '">' +
      '<div class="card-left">' +
      '<div class="card-title"><h3>' + esc(t.name) + "</h3></div>" +
      '<div class="card-sub">' + esc(t.category_label || "Unclassified") +
      " · first observed " + esc(ago(t.first_observed)) +
      " · last signal " + esc(ago(t.last_observed)) + "</div>" +
      '<div class="badges">' + badges.join("") + "</div>" +
      '<div class="badges">' + srcBadges + "</div>" +
      '<div class="why">' + whyLine(t) + "</div>" +
      (angles ? '<div class="angles">' + angles + "</div>" : "") +
      "</div>" +
      '<div class="card-right">' +
      '<div class="score"><div class="num">' + (t.momentum_score || 0).toFixed(1) + '</div><div class="lbl">momentum</div>' +
      '<div class="bar"><i style="width:' + Math.max(2, Math.min(100, t.momentum_score || 0)) + '%"></i></div></div>' +
      sparkline(t.series) +
      "</div></article>";
  }

  function renderCards(elId, items, emptyMsg) {
    var el = $("#" + elId);
    if (!el) return;
    if (!items || !items.length) {
      el.innerHTML = emptyState(emptyMsg);
      return;
    }
    el.innerHTML = items.map(card).join("");
  }

  function emptyState(msg) {
    var st = (S.data && S.data.stats) || {};
    var win = st.window_days || 14;
    var hrs = win * 24;
    var last = S.data && S.data.generated_at
      ? fmtTime(S.data.generated_at) + " (" + ago(S.data.generated_at) + ")" : "unknown";
    var healthy = (S.data && S.data.stats && S.data.stats.sources_ok) || 0;
    var total = (S.data && S.data.stats && S.data.stats.sources_total) || 0;
    return '<div class="empty">' +
      '<div class="empty-icon">\u25cb</div>' +
      "<p>" + esc(msg) + "</p>" +
      '<p class="empty-meta">No qualifying signal in the last ' + hrs + " hours.</p>" +
      '<p class="empty-meta">Last successful run: <b>' + esc(last) + "</b> \u00b7 " + healthy + "/" + total + " sources healthy \u00b7 " +
      esc(st.concepts_total || 0) + " concepts monitored</p>" +
      '<p class="empty-meta">The collector is running; this panel fills as a topic accumulates a baseline and corroboration.</p>' +
      "</div>";
  }

  function renderStatbar() {
    var d = S.data, st = d.stats || {};
    var cells = [
      { k: "Concepts tracked", v: num(st.concepts_total), n: "all time" },
      { k: "Active in window", v: num(st.concepts_active), n: (st.window_days || 0) + " days" },
      { k: "Observations stored", v: num(st.observations_total), n: "timestamped" },
      { k: "Sources healthy", v: (st.sources_ok || 0) + "/" + (st.sources_total || 0), n: "live now", cls: st.sources_ok === st.sources_total ? "good" : "warn" },
      { k: "Emerging", v: num(((d.sections || {}).emerging || []).length), n: "with baseline", cls: "good" },
      { k: "Cross-surface", v: num(((d.sections || {}).cross_platform || []).length), n: "2+ sources" },
      { k: "Audience questions", v: num((d.questions || []).length), n: "captured" },
      { k: "Content angles", v: num((d.opportunities || []).length), n: "evidence-based" }
    ];
    $("#statbar").innerHTML = cells.map(function (c) {
      return '<div class="stat"><div class="k">' + esc(c.k) + '</div><div class="v ' + (c.cls || "") + '">' + esc(c.v) + '</div><div class="n">' + esc(c.n) + "</div></div>";
    }).join("");
  }

  function renderQuestions() {
    var qs = (S.data.questions || []).filter(function (q) {
      var f = S.filters;
      if (f.q && (q.text + " " + q.concept).toLowerCase().indexOf(f.q.toLowerCase()) < 0) return false;
      if (f.tier) {
        var t = S.byKey[q.concept_key];
        if (!t || t.evidence_tier !== f.tier) return false;
      }
      return true;
    });
    var el = $("#list-questions");
    if (!qs.length) { el.innerHTML = '<div class="empty">No questions captured yet.</div>'; return; }
    el.innerHTML = qs.slice(0, 90).map(function (q) {
      var link = q.url ? '<a href="' + esc(q.url) + '" target="_blank" rel="noopener">source ↗</a>' : "";
      return '<div class="q"><div class="qt">' + esc(q.text) + "</div>" +
        '<div class="qm"><span class="intent">' + esc((q.intent || "").replace(/_/g, " ")) + "</span>" +
        "<span>" + esc(SOURCE_SHORT[q.source] || q.source) + "</span>" +
        "<span>" + esc(q.concept) + "</span>" + link + "</div></div>";
    }).join("");
  }

  function renderPhrasings() {
    var ps = (S.data.new_phrasings || []).filter(function (p) {
      var f = S.filters;
      if (f.q && (p.text + " " + p.concept).toLowerCase().indexOf(f.q.toLowerCase()) < 0) return false;
      if (f.source && p.source !== f.source) return false;
      if (f.geo && p.geo !== f.geo) return false;
      return true;
    });
    var el = $("#list-phrasings");
    if (!ps.length) {
      el.innerHTML = emptyState("No newly observed phrasings in the last 72 hours. This panel fills as the collector accumulates runs.");
      return;
    }
    el.innerHTML = ps.map(function (p) {
      var link = p.url ? '<a href="' + esc(p.url) + '" target="_blank" rel="noopener">search ↗</a>' : "";
      return '<div class="q"><div class="qt">' + esc(p.text) + "</div>" +
        '<div class="qm"><span class="intent">first seen</span>' +
        "<span>" + esc(SOURCE_SHORT[p.source] || p.source) + "</span>" +
        "<span>" + esc(p.concept || "") + "</span>" +
        "<span>" + esc(p.lang || "") + "</span>" + link + "</div></div>";
    }).join("");
  }

  function renderOpportunities() {
    var ops = (S.data.opportunities || []).filter(function (o) {
      var f = S.filters;
      if (f.q && (o.concept + " " + o.angle).toLowerCase().indexOf(f.q.toLowerCase()) < 0) return false;
      if (f.tier && o.tier !== f.tier) return false;
      if (f.category) {
        var t = S.byKey[o.concept_key];
        if (!t || t.category !== f.category) return false;
      }
      return true;
    });
    var el = $("#list-opportunities");
    if (!ops.length) { el.innerHTML = emptyState("No evidence-backed opportunities yet."); return; }
    el.innerHTML = ops.slice(0, 60).map(function (o) {
      return '<div class="opp"><h4>' + esc(o.concept) + "</h4>" +
        '<div class="ang">' + esc(o.angle) + "</div>" +
        '<div class="meta"><span>momentum ' + (o.momentum || 0).toFixed(1) + "</span>" +
        "<span>confidence " + esc(o.confidence) + "</span>" +
        "<span>tier " + esc(o.tier) + "</span>" +
        (o.flagged ? "<span>⚠ " + esc(o.flagged) + "</span>" : "") + "</div></div>";
    }).join("");
  }

  function renderLifecycleTable() {
    var tb = $("#lifecycle-table tbody");
    var rows = S.filtered.slice().sort(function (a, b) {
      return (b.momentum_score || 0) - (a.momentum_score || 0);
    });
    if (!rows.length) { tb.innerHTML = '<tr><td colspan="9" class="empty">Nothing matches the current filters.</td></tr>'; return; }
    tb.innerHTML = rows.map(function (t) {
      return "<tr>" +
        '<td class="name">' + esc(t.name) + "</td>" +
        '<td><span class="badge lifecycle ' + esc(t.lifecycle) + '">' + esc(t.lifecycle_label || t.lifecycle) + "</span></td>" +
        '<td class="num">' + (t.momentum_score || 0).toFixed(1) + "</td>" +
        '<td class="num">' + (t.has_baseline ? ((t.acceleration >= 0 ? "+" : "") + pct(t.acceleration)) : "—") + "</td>" +
        '<td class="num">' + (t.cross_source_count || 0) + "</td>" +
        '<td class="num">' + (t.observations || 0) + "</td>" +
        '<td class="num">' + esc(ago(t.first_observed)) + "</td>" +
        '<td><span class="badge conf-' + esc((t.confidence || {}).level) + '">' + esc((t.confidence || {}).level) + "</span></td>" +
        '<td><span class="badge tier-' + esc(t.evidence_tier) + '">' + esc(t.evidence_tier_label || t.evidence_tier) + "</span></td>" +
        "</tr>";
    }).join("");
  }

  function renderRegional() {
    var reg = S.data.regional || {};
    var geos = S.data.geos || [];
    var order = geos.map(function (g) { return g.key; });
    Object.keys(reg).forEach(function (k) { if (order.indexOf(k) < 0) order.push(k); });
    var el = $("#regional-grid");
    if (!order.length) { el.innerHTML = emptyState("No regional data yet."); return; }
    el.innerHTML = order.map(function (k) {
      var label = (geos.filter(function (g) { return g.key === k; })[0] || {}).label || k;
      var items = (reg[k] || []).slice().sort(function (a, b) { return b.score - a.score; }).slice(0, 8);
      var body = items.length
        ? "<ul>" + items.map(function (i) {
            return "<li><span>" + esc(i.name) + "</span><span class=\"s\">" + (i.score || 0).toFixed(0) + "</span></li>";
          }).join("") + "</ul>"
        : '<div class="count">No signals recorded for this geography yet.</div>';
      return '<div class="geo"><h4>' + esc(label) + '</h4><div class="count">' +
        (items.length ? items.length + " topics with signal" : "") + "</div>" + body + "</div>";
    }).join("");
  }

  function renderSources() {
    var list = S.data.source_health || [];
    var el = $("#list-sources");
    if (!list.length) { el.innerHTML = emptyState("No source status recorded."); return; }
    el.innerHTML = list.map(function (s) {
      var cls = s.ok ? "ok" : (s.runs ? "bad" : "idle");
      var meta = [];
      if (s.meta && s.meta.total_trends) {
        meta.push("<b>" + s.meta.total_trends + "</b> trends scanned");
        meta.push("<b>" + s.meta.vertical_matched + "</b> in vertical");
      } else if (s.items != null) {
        meta.push("<b>" + s.items + "</b> items");
      }
      if (s.latency_ms) meta.push(Math.round(s.latency_ms) + " ms");
      if (s.success_rate != null) meta.push("success " + pct(s.success_rate));
      if (s.runs) meta.push(s.runs + " runs");
      return '<div class="source"><div><div class="name"><span class="dot ' + cls + '"></span>' + esc(s.label) +
        "</div>" + (s.message ? '<div class="msg">' + esc(s.message) + "</div>" : "") + "</div>" +
        '<div class="source-stat">' + (meta.join("<br>") || "—") + "</div></div>";
    }).join("");
  }

  function renderValidation(v) {
    var el = $("#validation-body");
    if (!el) return;
    if (!v) {
      el.innerHTML = '<p>The validation report has not been generated yet. It is produced on every collection cycle by <code>tools/validate.py</code>.</p>';
      return;
    }
    function pctf(x) { return (x == null ? "—" : (Number(x) * 100).toFixed(1) + "%"); }
    function numf(x) { return (x == null ? "—" : x); }
    var lt = v.lead_time_vs_manual_baseline || {};
    var cp = v.cross_platform_confirmation || {};
    var fp = v.false_positives || {};
    var pt = v.permutation_test || {};
    var verdictClass = v.history_span_days >= (v.minimum_history_for_conclusions_days || 21) ? "good" : "warn";
    el.innerHTML =
      '<h4>Verdict</h4>' +
      '<p><strong style="color:var(' + (verdictClass === "good" ? "--green" : "--amber") + ')">' + esc(v.verdict || "") + "</strong></p>" +
      '<h4>Observation window</h4><dl class="kv">' +
      "<dt>Collection cycles</dt><dd>" + esc(v.collection_cycles) + "</dd>" +
      "<dt>Wall-clock span</dt><dd>" + esc(v.history_span_days) + " days</dd>" +
      "<dt>Minimum for conclusions</dt><dd>" + esc(v.minimum_history_for_conclusions_days) + " days</dd>" +
      "<dt>Concepts with history</dt><dd>" + esc(v.concepts_with_history) + "</dd>" +
      "</dl>" +
      "<h4>Lead time vs the topic's own 'it became obvious' threshold</h4>" +
      '<dl class="kv"><dt>Concepts measured</dt><dd>' + esc(lt.n) + "</dd>" +
      "<dt>Median lead</dt><dd>" + esc(numf(lt.median_lead_cycles)) + " " + esc(lt.unit || "cycles") + "</dd>" +
      "<dt>Lead &gt; 0</dt><dd>" + esc(lt.positive_leads) + "</dd>" +
      "<dt>Lead &lt; 0</dt><dd>" + esc(lt.negative_leads) + "</dd></dl>" +
      '<p style="margin-top:8px">' + esc(lt.message || lt.interpretation || "") + "</p>" +
      "<h4>Cross-platform confirmation lag</h4>" +
      '<dl class="kv"><dt>Concepts measured</dt><dd>' + esc(cp.n) + "</dd>" +
      "<dt>Median lag</dt><dd>" + esc(numf(cp.median_lag_cycles)) + " cycles</dd></dl>" +
      '<p style="margin-top:8px">' + esc(cp.note || "") + "</p>" +
      "<h4>False positives (upper bound)</h4>" +
      '<dl class="kv"><dt>Flagged</dt><dd>' + esc(fp.n_flagged) + "</dd>" +
      "<dt>Reached own threshold</dt><dd>" + esc(fp.n_reached_own_threshold) + "</dd>" +
      "<dt>Rate</dt><dd>" + esc(pctf(fp.false_positive_rate)) + "</dd></dl>" +
      '<p style="margin-top:8px">' + esc(fp.note || "") + "</p>" +
      "<h4>Permutation test (Kleinberg)</h4>" +
      '<dl class="kv"><dt>Topics flagged, real ordering</dt><dd>' + esc(pt.real_topics_flagged) + "</dd>" +
      "<dt>Topics flagged, shuffled ordering</dt><dd>" + esc(pt.permuted_average_flagged) + "</dd>" +
      "<dt>Trials</dt><dd>" + esc(pt.trials) + "</dd></dl>" +
      '<p style="margin-top:8px">' + esc(pt.interpretation || "") + "</p>" +
      '<p style="margin-top:10px;color:var(--ink-faint)">Generated ' + esc(v.generated_at || "") + "</p>";
  }

  function loadValidation() {
    return fetch(LOCAL_VALIDATION, { cache: "no-cache" })
      .then(function (r) { return r.ok ? r.json() : null; })
      .catch(function () { return null; })
      .then(function (loc) {
        return fetch(REMOTE_VALIDATION, { cache: "no-cache" })
          .then(function (r) { return r.ok ? r.json() : null; })
          .catch(function () { return null; })
          .then(function (rem) {
            if (rem && rem.generated_at && (!loc || (Date.parse(rem.generated_at) >= Date.parse(loc.generated_at)))) {
              renderValidation(rem); return;
            }
            renderValidation(loc);
          });
      });
  }

  function renderCaptures() {
    var el = $("#capture-list");
    if (!el) return;
    var caps = (S.data && S.data.captures) || [];
    if (!caps.length) {
      el.innerHTML = '<div class="empty" style="text-align:left"><div class="empty-icon">\u25cb</div>' +
        '<p>No manual captures yet.</p>' +
        '<p class="empty-meta">Paste a trending list on the left, or run <b>python -m collector.capture</b> locally. ' +
        "Captured topics are timestamped, tracked from that moment, and gain a baseline once the collector has seen them four times." +
        "</p></div>";
      return;
    }
    el.innerHTML = caps.map(function (c) {
      return '<div class="cap">' +
        '<div class="cap-head"><b>' + esc((SOURCE_SHORT[c.source + "_manual"] || c.source)) + "</b>" +
        "<span>" + esc(c.region || "") + "</span>" +
        "<span>" + esc(ago(c.captured_at)) + "</span></div>" +
        '<div class="cap-tags">' + (c.tags || []).map(function (t) {
          return '<span class="cap-tag">#' + esc(t) + "</span>";
        }).join("") + "</div>" +
        (c.notes ? '<div class="cap-note">' + esc(c.notes) + "</div>" : "") +
        "</div>";
    }).join("");
  }

  function renderPlatforms() {
    var el = $("#platform-body");
    if (!el) return;
    var ig = (S.data && S.data.source_health || []).filter(function (s) { return s.source === "instagram_hashtag"; })[0];
    var tt = (S.data && S.data.source_health || []).filter(function (s) { return s.source === "tiktok_creative"; })[0];
    el.innerHTML =
      "<h4>TikTok — no automated public trend data exists</h4>" +
      "<p>Verified against the live platform on 21 October 2026, from both a datacentre IP and a residential one, in a real browser:</p>" +
      "<ul>" +
      "<li><code>creative_radar_api/v1/popular_trend/hashtag/list</code> returns <code>40101 no permission</code>.</li>" +
      "<li><code>cc_portal_api/api/trendsTcc</code> — the endpoint the Creative Center page itself calls — returns <b>HTTP 500</b> for anonymous clients.</li>" +
      "<li>The three hashtags that visibly render are identical across fresh sessions with zero table rows: they ship inside the frontend bundle and are not live data.</li>" +
      "<li><code>tiktok.com/csi</code> (Creator Search Insights, the rising-search surface) now <b>302s to a 404</b>.</li>" +
      "<li>TikTok's own terms prohibit automated and commercial screen scraping.</li>" +
      "</ul>" +
      "<p><strong>What is available:</strong> the Research API (academic and non-profit only, requires ethical review and independence from commercial interests), the Commercial Content API (advertising data, by application), and <b>the capture panel on this page</b> — you look at Creative Center in your own logged-in session, paste the list, and the system does the part a human cannot: timestamps it and tracks it over time.</p>" +
      "<p>Current status: <b>" + (tt && tt.ok ? "responding" : (tt ? "blocked &mdash; " + esc(tt.message || "") : "unknown")) + "</b></p>" +
      "<h4>Instagram — officially possible, and the adapter is built</h4>" +
      "<p>Instagram <i>can</i> be read, but only through Meta's official Graph API, and only for a fixed set of tags you already know. The constraint that matters is Meta's own: <b>30 unique hashtags per rolling 7 days</b> per Business or Creator account. Re-querying a tag already inside that window costs nothing, so the collector tracks the budget locally and spends it deliberately.</p>" +
      "<p>To switch it on you need a Meta app with <code>instagram_basic</code>, the <b>Instagram Public Content Access</b> feature, App Review, a Business or Creator account and Business Verification. That is weeks of paperwork, so the adapter sits inert and says so rather than failing quietly.</p>" +
      "<p>The tag queue is seeded <b>discovery-first</b>: topics the other sources have just found, then corroborated topics, then the curated seed list. That matters because Instagram cannot discover trends — the useful question to ask it is <i>how big is the audience for the thing we found elsewhere?</i></p>" +
      "<p>Current status: <b>" + (ig && ig.ok ? "connected" : (ig ? "awaiting authorisation &mdash; " + esc(ig.message || "") : "unknown")) + "</b></p>" +
      "<h4>What this means for the numbers you are reading</h4>" +
      "<p>Every topic on this site is discovered from the free public surfaces listed under Methodology, or captured by a human from a platform that does not expose an API. Nothing here is inferred from engagement figures TikTok or Instagram have not published, and no topic claims Instagram or TikTok reach unless a capture says so.</p>";
  }

  function renderMethod() {
    var m = S.data.methodology || {};
    var w = m.weights || {};
    var rows = Object.keys(w).map(function (k) {
      return "<tr><td>" + esc(k.replace(/_/g, " ")) + "</td><td>" + (w[k] * 100).toFixed(0) + "%</td></tr>";
    }).join("");
    var tiers = S.data.evidence_tiers || {};
    var tierRows = Object.keys(tiers).map(function (k) {
      var t = tiers[k];
      return "<tr><td><span class=\"badge tier-" + esc(k) + "\">" + esc(t.label) + "</span></td><td>" +
        esc(t.description) + "</td><td>" + esc(t.check) + "</td></tr>";
    }).join("");
    $("#method-body").innerHTML =
      "<h4>Principle</h4><p>" + esc(m.principle || "") + "</p>" +
      "<h4>Score composition</h4><table><tr><th>Component</th><th>Weight</th></tr>" + rows + "</table>" +
      "<p style=\"margin-top:10px\">" + esc(m.normalisation || "") + "</p>" +
      "<h4>Confidence</h4><p>" + esc(m.confidence || "") + "</p>" +
      "<h4>Seasonality</h4><p>" + esc(m.seasonality || "") + "</p>" +
      "<h4>Honesty rule</h4><p>" + esc(m.note || "") + "</p>" +
      "<h4>Evidence tiers</h4><table><tr><th>Tier</th><th>Meaning</th><th>How to check it</th></tr>" + tierRows + "</table>" +
      "<h4>Limits of this system</h4><ul>" +
      "<li>TikTok and Instagram expose no public trend API. Where this site shows no TikTok or Instagram signal, that is the platform's position, not a bug. TikTok Creative Center is checked as a manual baseline, not scraped.</li>" +
      "<li>Google Trends' global trending list is general-interest; a wellness topic appearing on it is a strong breakout signal precisely because it is rare.</li>" +
      "<li>Autocomplete and search-suggestion data cannot be localised by country on Google's own endpoint — only by language. Country-level targeting needs a keyed search API.</li>" +
      "<li>Reddit's public RSS endpoints are being retired on 13 November 2026; the source is expected to degrade.</li>" +
      "<li>No confidence value here is produced by a language model. Numbers come from the observation table; the model only writes prose.</li>" +
      "</ul>";
  }

  function renderSourceStrip() {
    var el = $("#source-strip");
    if (!el) return;
    var list = (S.data && S.data.source_health) || [];
    if (!list.length) {
      el.innerHTML = '<div class="strip-skeleton"><span></span><span></span><span></span><span></span></div>';
      return;
    }
    var ok = 0, degraded = 0, down = 0;
    list.forEach(function (s2) {
      if (s2.ok) ok++;
      else if (s2.runs) degraded++;
      else down++;
    });
    var lastRun = null;
    list.forEach(function (s2) {
      var h = (s2.history || []).filter(function (x) { return x.ok; });
      if (h.length) {
        var t = Date.parse(h[h.length - 1].ts);
        if (!lastRun || t > lastRun) lastRun = t;
      }
    });
    var dots = list.slice().sort(function (a, b) {
      var rank = function (x) { return x.ok ? 0 : (x.runs ? 1 : 2); };
      return rank(a) - rank(b);
    }).map(function (s2) {
      var k = s2.ok ? "ok" : (s2.runs ? "bad" : "idle");
      var t = s2.ok ? "healthy" : (s2.runs ? "degraded" : "awaiting authorisation");
      return '<a class="dot-chip" href="#sources" title="' + esc(s2.label) + " \u2014 " + t + (s2.message ? ": " + esc(s2.message) : "") + '">' +
        '<span class="dot ' + k + '"></span><span class="dot-name">' + esc(SOURCE_SHORT[s2.source] || s2.label) + "</span></a>";
    }).join("");
    el.innerHTML =
      '<div class="strip-lead">' +
      '<span class="strip-title">Sources</span>' +
      '<span class="strip-count"><b class="' + (down ? "warn" : "good") + '">' + ok + "/" + list.length + "</b> live</span>" +
      (degraded ? '<span class="strip-count"><b class="warn">' + degraded + "</b> degraded</span>" : "") +
      (down ? '<span class="strip-count"><b class="warn">' + down + "</b> awaiting access</span>" : "") +
      '<span class="strip-time" id="strip-updated">' + (lastRun ? "last successful run " + ago(new Date(lastRun).toISOString()) : "") + "</span>" +
      "</div>" +
      '<div class="strip-dots">' + dots + "</div>";
  }

  function renderAll() {
    var d = S.data;
    S.byKey = {};
    (d.trends || []).forEach(function (t) { S.byKey[t.key] = t; });

    var sec = d.sections || {};
    function pick(list) {
      return (list || []).map(function (k) { return S.byKey[k]; })
        .filter(Boolean).filter(function (t) { return S.filtered.indexOf(t) >= 0; });
    }

    renderStatbar();
    renderSourceStrip();
    var emergingHtml = "";
    var emergingItems = pick(sec.emerging);
    if (emergingItems.length) {
      emergingHtml = emergingItems.map(card).join("");
    } else {
      emergingHtml = emptyState("No topic currently meets the emerging bar. That is a real result, not a failure \u2014 nothing has crossed the acceleration and corroboration thresholds yet. History builds with every collection cycle.");
    }
    var newlyItems = pick(sec.newly_observed).slice(0, 24);
    if (newlyItems.length) {
      emergingHtml += '<h3 class="subgroup">Newly observed <span>first seen inside the window · no baseline yet · no early-detection claim</span></h3>' +
        newlyItems.map(card).join("");
    }
    $("#list-emerging").innerHTML = emergingHtml;
    renderCards("list-before-viral", pick(sec.before_viral), "No candidate currently clears the burst-onset and corroboration bar. This panel fills as history accumulates.");
    var hasAccel = S.filtered.some(function (t) { return t.has_baseline; });
    if (hasAccel) {
      renderCards("list-fastest", S.filtered.slice().sort(function (a, b) { return (b.acceleration || 0) - (a.acceleration || 0); }).slice(0, 20), "Nothing to rank yet.");
    } else {
      renderCards("list-fastest", S.filtered.slice().sort(function (a, b) {
        return (b.cross_source_count - a.cross_source_count) || (b.observations - a.observations);
      }).slice(0, 20), "Nothing to rank yet.");
    }
    renderCards("list-cross", pick(sec.cross_platform), "No topic yet appears on two independent sources.");
    renderCaptures();
    renderPlatforms();
    renderQuestions();
    renderPhrasings();
    renderOpportunities();
    renderLifecycleTable();
    renderRegional();
    renderSources();
    renderMethod();

    $("#filter-summary").textContent =
      S.filtered.length + " of " + ((d.trends || []).length) + " topics shown" +
      (S.filters.q ? " · search: \"" + S.filters.q + "\"" : "") +
      (S.data.generated_at ? " · snapshot " + fmtTime(S.data.generated_at) : "");
  }

  /* -------------------------------------------------------------- drawer */

  function openDrawer(key) {
    var t = S.byKey[key];
    if (!t) return;
    var conf = t.confidence || { level: "low", reasons: [] };
    var ev = (t.evidence || []).map(function (e) {
      return '<div class="ev"><div class="t">' + esc(e.title) + "</div>" +
        '<div class="m"><span>' + esc(SOURCE_SHORT[e.source] || e.source) + "</span>" +
        "<span>" + esc(e.geo || "") + "</span><span>" + esc(e.ts || "") + "</span>" +
        (e.value != null ? "<span>" + esc(e.metric) + "=" + num(e.value) + "</span>" : "") + "</div>" +
        (e.url ? '<div class="m"><a href="' + esc(e.url) + '" target="_blank" rel="noopener">open original ↗</a></div>' : "") +
        "</div>";
    }).join("");

    var qs = (t.questions || []).map(function (q) {
      return "<li>" + (q.url ? '<a href="' + esc(q.url) + '" target="_blank" rel="noopener">' + esc(q.text) + "</a>" : esc(q.text)) + "</li>";
    }).join("");

    var rel = (t.related || []).map(function (r) {
      return "<li>" + esc(r.concept) + " <em>(" + esc(r.relation) + ")</em></li>";
    }).join("");

    $("#drawer-title").textContent = t.name;
    $("#drawer-sub").innerHTML = esc(t.category_label || "Unclassified") + " · " + esc(t.lifecycle_label || "") +
      " · momentum " + (t.momentum_score || 0).toFixed(1);
    $("#drawer-body").innerHTML =
      (t.note ? '<div class="note"><span class="tag">Narrative note — generated prose, not a measurement</span>' + esc(t.note) + "</div>" : "") +
      "<h4>Why it is on this list</h4><p>" + whyLine(t) + "</p>" +
      "<h4>Evidence tier</h4><p><strong>" + esc(t.evidence_tier_label) + "</strong> — " + esc(t.evidence_tier_note) + " <em>How to check: " + esc(t.evidence_tier_check) + "</em></p>" +
      "<h4>Measurements</h4><dl class=\"kv\">" +
      "<dt>Observations</dt><dd>" + (t.observations || 0) + "</dd>" +
      "<dt>Time buckets</dt><dd>" + (t.time_buckets || 0) + "</dd>" +
      "<dt>Distinct sources</dt><dd>" + (t.cross_source_count || 0) + "</dd>" +
      "<dt>Distinct surfaces</dt><dd>" + (t.surface_count || 0) + "</dd>" +
      "<dt>Distinct creators</dt><dd>" + (t.creator_count || 0) + "</dd>" +
      "<dt>Velocity</dt><dd>" + (t.velocity != null ? pct(t.velocity) : "—") + "</dd>" +
      "<dt>Acceleration</dt><dd>" + (t.has_baseline ? ((t.acceleration >= 0 ? "+" : "") + pct(t.acceleration)) : "no baseline") + "</dd>" +
      "<dt>Burst onset score</dt><dd>" + (t.burst_score != null ? t.burst_score.toFixed(3) : "—") + "</dd>" +
      "<dt>Total weighted evidence</dt><dd>" + num(t.total_count, 1) + "</dd>" +
      "<dt>Observed views</dt><dd>" + num(t.total_views, 1) + "</dd>" +
      "<dt>First observed</dt><dd>" + esc(fmtTime(t.first_observed)) + "</dd>" +
      "<dt>Last observed</dt><dd>" + esc(fmtTime(t.last_observed)) + "</dd>" +
      "<dt>Geographies</dt><dd>" + esc((t.geos || []).join(", ") || "—") + "</dd>" +
      "<dt>Languages</dt><dd>" + esc((t.langs || []).join(", ") || "—") + "</dd>" +
      "</dl>" +
      "<h4>Confidence — " + esc(conf.level) + "</h4><ul>" +
      (conf.reasons || []).map(function (r) { return "<li>" + esc(r) + "</li>"; }).join("") + "</ul>" +
      (rel ? "<h4>Related but distinct</h4><ul>" + rel + "</ul>" : "") +
      (qs ? "<h4>Audience questions</h4><ul>" + qs + "</ul>" : "") +
      "<h4>Original evidence (" + (t.evidence || []).length + ")</h4>" + (ev || "<p>No evidence links captured.</p>") +
      "<h4>Content angles</h4><ul>" +
      (t.opportunities || []).map(function (a) {
        return "<li>" + esc(a.angle) + (a.flagged ? " <em>(" + esc(a.flagged) + ")</em>" : "") + "</li>";
      }).join("") + "</ul>";

    $("#drawer").classList.add("open");
    $("#drawer").setAttribute("aria-hidden", "false");
    $("#scrim").classList.add("open");
    document.body.style.overflow = "hidden";
  }

  function closeDrawer() {
    $("#drawer").classList.remove("open");
    $("#drawer").setAttribute("aria-hidden", "true");
    $("#scrim").classList.remove("open");
    document.body.style.overflow = "";
  }

  /* --------------------------------------------------------------- init */

  var SOURCE_SHORT = {
    google_trends_now: "Google Trends",
    google_trends_rss: "Google Trends RSS",
    google_suggest: "Google Suggest",
    youtube_suggest: "YouTube Suggest",
    youtube_search: "YouTube",
    wikipedia_views: "Wikipedia",
    mastodon_trends: "Mastodon",
    reddit_rss: "Reddit",
    news_rss: "News",
    europepmc: "Research",
    itunes_podcasts: "Podcasts",
    hn_algolia: "HN",
    tiktok_creative: "TikTok",
    instagram_hashtag: "Instagram",
    threads_search: "Threads",
    pinterest_trends: "Pinterest",
    tiktok_manual: "TikTok (captured)",
    instagram_manual: "Instagram (captured)",
    other_manual: "Manual capture"
  };

  function populateFilters() {
    var d = S.data;
    function opts(sel, items, labeller) {
      var el = $(sel);
      items.forEach(function (i) {
        var o = document.createElement("option");
        o.value = i.key != null ? i.key : i;
        o.textContent = labeller ? labeller(i) : i;
        el.appendChild(o);
      });
    }
    opts("#f-category", d.categories || [], function (c) { return c.label; });
    opts("#f-geo", d.geos || [], function (g) { return g.label; });
    var srcs = {};
    (d.trends || []).forEach(function (t) { (t.sources || []).forEach(function (s) { srcs[s] = 1; }); });
    opts("#f-source", Object.keys(srcs).sort(), function (s) { return SOURCE_SHORT[s] || s; });
    var lifes = {};
    (d.trends || []).forEach(function (t) { lifes[t.lifecycle] = 1; });
    opts("#f-lifecycle", Object.keys(lifes).sort(), function (l) {
      return (d.trends.filter(function (t) { return t.lifecycle === l; })[0] || {}).lifecycle_label || l;
    });
    opts("#f-confidence", ["high", "moderate", "low"]);
    opts("#f-tier", Object.keys(d.evidence_tiers || {}), function (k) { return d.evidence_tiers[k].label; });
  }

  function applyTheme(theme) {
    document.documentElement.setAttribute("data-theme", theme);
    try { localStorage.setItem("ti-theme", theme); } catch (e) {}
    var btn = $("#theme-toggle");
    if (btn) {
      btn.textContent = theme === "light" ? "\u25d1" : "\u25d0";
      btn.setAttribute("aria-label", theme === "light" ? "Switch to dark theme" : "Switch to light theme");
      btn.title = theme === "light" ? "Dark theme" : "Light theme";
    }
  }

  function initTheme() {
    var saved = null;
    try { saved = localStorage.getItem("ti-theme"); } catch (e) {}
    if (!saved) {
      saved = (window.matchMedia && window.matchMedia("(prefers-color-scheme: light)").matches) ? "light" : "dark";
    }
    applyTheme(saved);
  }

  function bind() {
    $("#f-search").addEventListener("input", function (e) { S.filters.q = e.target.value; applyFilters(); });
    ["#f-category", "#f-geo", "#f-source", "#f-lifecycle", "#f-confidence", "#f-tier"].forEach(function (sel) {
      $(sel).addEventListener("change", function (e) {
        S.filters[sel.replace("#f-", "")] = e.target.value; applyFilters();
      });
    });
    $("#f-minscore").addEventListener("change", function (e) {
      S.filters.minscore = Number(e.target.value || 0); applyFilters();
    });
    $("#f-clear").addEventListener("click", function () {
      S.filters = { q: "", category: "", geo: "", source: "", lifecycle: "", confidence: "", tier: "", minscore: 0 };
      $("#f-search").value = "";
      ["#f-category", "#f-geo", "#f-source", "#f-lifecycle", "#f-confidence", "#f-tier"].forEach(function (s) { $(s).value = ""; });
      $("#f-minscore").value = "0";
      applyFilters();
    });
    $("#refresh").addEventListener("click", function () {
      var btn = $("#refresh");
      if (btn.classList.contains("busy")) return;
      btn.classList.add("busy");
      btn.textContent = "\u21bb Refreshing\u2026";
      var t0 = Date.now();
      boot(true).then(function () {
        var ms = Date.now() - t0;
        var ok = !!S.data;
        btn.classList.remove("busy");
        btn.classList.toggle("ok", ok);
        btn.textContent = ok ? "\u2713 Updated" : "\u2717 Failed";
        setTimeout(function () {
          btn.classList.remove("ok");
          btn.textContent = "\u21bb Refresh";
        }, 2600);
      });
    });
    var cf = $("#capture-form");
    if (cf) {
      cf.addEventListener("submit", function (ev) {
        ev.preventDefault();
        var status = $("#capture-status");
        var tags = ($("#cap-tags").value || "").trim();
        if (!tags) { status.textContent = "Paste a list first."; return; }
        var entry = {
          tags: tags.split(/[\n,;\t]+/).map(function (t) {
            return t.trim().replace(/^\d+\s*[\.\)\:-]?\s*/, "").replace(/^[#@]/, "").toLowerCase();
          }).filter(Boolean),
          source: ($("#cap-source").value || "other"),
          region: ($("#cap-region").value || "GLOBAL"),
          notes: ($("#cap-notes").value || ""),
          captured_at: new Date().toISOString().replace(/\.\d+Z$/, "Z"),
          capture_id: "cap_" + Date.now()
        };
        var plain = entry.tags.join("\n");
        var done = function (msg) {
          status.innerHTML = msg + ' &nbsp;&middot;&nbsp; then run <code>python -m collector.capture --clipboard</code>';
          renderCaptures();
        };
        // 1. copy the tags so the CLI can pick them up
        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(plain).then(
            function () { done("Hashtags copied to your clipboard."); },
            function () { done("Copy the hashtags manually."); }
          );
        } else {
          done("Copy the hashtags manually.");
        }
        // 2. also offer a file, which is the more durable path
        try {
          var blob = new Blob([JSON.stringify([entry], null, 2)], { type: "application/json" });
          var a = document.createElement("a");
          a.href = URL.createObjectURL(blob);
          a.download = "trend-capture-" + entry.captured_at.slice(0, 10) + ".json";
          document.body.appendChild(a); a.click();
          setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 1500);
        } catch (e) {}
      });
    }
    $("#theme-toggle").addEventListener("click", function () {
      var cur = document.documentElement.getAttribute("data-theme") || "dark";
      applyTheme(cur === "light" ? "dark" : "light");
    });
    $("#drawer-close").addEventListener("click", closeDrawer);
    $("#scrim").addEventListener("click", closeDrawer);
    document.addEventListener("keydown", function (e) { if (e.key === "Escape") closeDrawer(); });
    document.addEventListener("click", function (e) {
      var c = e.target.closest(".card");
      if (c) openDrawer(c.getAttribute("data-key"));
    });
    $$("#tabs .tab").forEach(function (a) {
      a.addEventListener("click", function () {
        $$("#tabs .tab").forEach(function (x) { x.classList.remove("active"); });
        a.classList.add("active");
      });
    });
    window.addEventListener("hashchange", function () {
      var id = location.hash.slice(1);
      var tab = $$("#tabs .tab").filter(function (a) { return a.getAttribute("href") === "#" + id; })[0];
      if (tab) { $$("#tabs .tab").forEach(function (x) { x.classList.remove("active"); }); tab.classList.add("active"); }
    });
  }

  function boot(force) {
    return loadData(force).then(function (data) {
      S.data = data;
      populateFilters();
      applyFilters();
      loadValidation();
      $("#footer-meta").textContent =
        "Version " + (data.version || "?") + " · " +
        (data.stats ? data.stats.observations_total + " observations stored · " : "") +
        (data.llm && data.llm.enabled ? "narrative notes enabled (" + data.llm.provider + ")" : "narrative notes disabled (no LLM key configured)");
    }).catch(function (err) {
      $("#list-emerging").innerHTML = '<div class="empty">Could not load data: ' + esc(err.message) + "</div>";
      setFeed("error", null);
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    initTheme();
    bind();
    boot(false);
    setInterval(function () { boot(false); }, 10 * 60 * 1000);
    document.addEventListener("visibilitychange", function () {
      if (!document.hidden) boot(false);
    });
  });
})();
