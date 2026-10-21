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

  function loadData(force) {
    var local = fetch(LOCAL, { cache: force ? "reload" : "default" })
      .then(function (r) { return r.ok ? r.json() : null; })
      .catch(function () { return null; });

    var remote = fetch(REMOTE + (force ? "?t=" + Date.now() : ""), { cache: force ? "reload" : "no-cache" })
      .then(function (r) { return r.ok ? r.json() : null; })
      .catch(function () { return null; });

    return remote.then(function (rem) {
      return local.then(function (loc) {
        if (rem && rem.generated_at) {
          var rf = Date.parse(rem.generated_at) || 0;
          var lf = loc ? (Date.parse(loc.generated_at) || 0) : 0;
          if (rf >= lf) { setFeed("live", rem); return rem; }
          if (loc) { setFeed("stale", loc); return loc; }
          setFeed("live", rem); return rem;
        }
        if (loc) { setFeed("stale", loc); return loc; }
        setFeed("error", null);
        throw new Error("no data");
      });
    });
  }

  function setFeed(state, data) {
    var el = $("#meta-feed");
    if (!el) return;
    el.className = "feed-state " + (state === "live" ? "live" : state === "stale" ? "stale" : "");
    el.textContent = state === "live" ? "live"
      : state === "stale" ? "bundled copy"
      : "unavailable";
    if (data && data.generated_at) {
      $("#meta-updated").textContent = fmtTime(data.generated_at) + "  (" + ago(data.generated_at) + ")";
    }
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
      el.innerHTML = '<div class="empty">' + esc(emptyMsg) + "</div>";
      return;
    }
    el.innerHTML = items.map(card).join("");
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
      el.innerHTML = '<div class="empty">No newly observed phrasings in the last 72 hours. This panel fills as the collector accumulates runs.</div>';
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
    if (!ops.length) { el.innerHTML = '<div class="empty">No opportunities yet.</div>'; return; }
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
    if (!order.length) { el.innerHTML = '<div class="empty">No regional data yet.</div>'; return; }
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
    if (!list.length) { el.innerHTML = '<div class="empty">No source status recorded.</div>'; return; }
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
        '<div class="stat">' + (meta.join("<br>") || "—") + "</div></div>";
    }).join("");
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
    renderCards("list-emerging", pick(sec.emerging), "No topic currently meets the emerging bar. That is a real result, not a failure — it means nothing has crossed the acceleration and corroboration thresholds yet.");
    renderCards("list-before-viral", pick(sec.before_viral), "No candidate currently clears the burst-onset and corroboration bar. This panel fills as history accumulates.");
    renderCards("list-fastest", S.filtered.slice().sort(function (a, b) { return (b.acceleration || 0) - (a.acceleration || 0); }).slice(0, 20), "Nothing to rank yet.");
    renderCards("list-cross", pick(sec.cross_platform), "No topic yet appears on two independent sources.");
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
    pinterest_trends: "Pinterest"
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
    $("#refresh").addEventListener("click", function () { boot(true); });
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
      renderAll();
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
    bind();
    boot(false);
    setInterval(function () { boot(false); }, 10 * 60 * 1000);
  });
})();
