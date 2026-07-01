/* app.js — Buscar (v2). Depende de shell.js (window.RH) y ui.js (Drawer). */
(function () {
  "use strict";
  const {
    escapeHtml, compactNumber, formatDate, relativeTime,
    typeMeta, typeLabel, typeChip, thumb, actionLinks, fetchJSON, openDrawer,
  } = window.RH;

  const $ = (s) => document.querySelector(s);
  const form = $("#searchForm");
  const queryInput = $("#queryInput");
  const cityInput = $("#cityInput");
  const sourceInput = $("#sourceInput");
  const dedupInput = $("#dedupInput");
  const clearButton = $("#clearButton");
  const typeChips = $("#typeChips");
  const messageArea = $("#messageArea");

  const homeView = $("#homeView");
  const resultsView = $("#resultsView");
  const resultsList = $("#resultsList");
  const resultsHeading = $("#resultsHeading");
  const resultCount = $("#resultCount");
  const resultTime = $("#resultTime");
  const loadMoreButton = $("#loadMoreButton");

  const statRecords = $("#statRecords");
  const statSources = $("#statSources");
  const statFresh = $("#statFresh");
  const typeBars = $("#typeBars");
  const recentList = $("#recentList");

  const drawerEl = $("#recordDrawer");
  const drawerTitle = $("#drawerTitle");
  const drawerType = $("#drawerType");
  const drawerBody = $("#drawerBody");

  const state = { type: "", nextOffset: null, lastParams: null, loading: false };

  // ----------------------------------------------------------- mensajes
  function setMessage(kind, title, body) {
    // Monocromo: el tipo se distingue por símbolo + (solo error) borde izq. rojo.
    const mark = kind === "error" ? "✕" : kind === "warn" ? "⚠" : "✓";
    const tone = kind === "error"
      ? "border-l-4 border-red-600 bg-ink-50 text-ink-900"
      : "border-l-4 border-ink-900 bg-ink-50 text-ink-900";
    messageArea.innerHTML = `<div role="alert" class="border ${tone} px-4 py-3 text-sm">
      <strong>${mark} ${escapeHtml(title)}</strong>${body ? `<div class="mt-0.5 text-ink-600">${escapeHtml(body)}</div>` : ""}</div>`;
  }
  const clearMessage = () => { messageArea.innerHTML = ""; };

  // ----------------------------------------------------------- tarjeta
  function reasonLabel(r) {
    const map = {
      cedula_exacta: "cédula exacta", cedula_prefijo: "cédula parcial",
      titulo_exacto: "título exacto", persona_exacto: "persona exacta",
      persona_contiene: "persona", organizacion: "organización", ubicacion: "ubicación",
    };
    return map[r] || String(r).replaceAll("_", " ");
  }

  function recordCard(result) {
    const r = result.record;
    const title = r.title || r.person_name || "Registro sin título";
    const loc = [r.city, r.state].filter(Boolean).join(", ");
    const verified = r.verified === true
      ? `<span class="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2 py-0.5 text-xs font-medium text-emerald-700 ring-1 ring-inset ring-emerald-200">✓ Verificado</span>`
      : "";
    const also = result.also_in_count > 1
      ? `<a href="/entidad?id=${encodeURIComponent(result.entity_id || "")}" class="inline-flex items-center gap-1 rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-600 hover:bg-slate-200">en ${compactNumber(result.also_in_count)} fuentes →</a>`
      : "";
    const reasons = (result.reasons || []).filter((x) => x !== "sin_consulta").slice(0, 3)
      .map((x) => `<span class="text-xs text-slate-400">· ${escapeHtml(reasonLabel(x))}</span>`).join(" ");
    const actions = actionLinks(r);

    return `<article class="group rounded-xl border border-slate-200 bg-white p-3 shadow-sm transition hover:border-slate-300 hover:shadow">
      <div class="flex gap-3">
        ${thumb(r)}
        <div class="min-w-0 flex-1">
          <div class="flex items-start justify-between gap-2">
            <button type="button" data-id="${escapeHtml(r.id)}" class="rh-plain min-w-0 text-left">
              <span class="block truncate font-semibold text-slate-900 group-hover:underline">${escapeHtml(title)}</span>
            </button>
            <span class="flex-shrink-0 text-xs text-slate-400">${escapeHtml(r.source_name || "")}</span>
          </div>
          <div class="mt-1 flex flex-wrap items-center gap-1.5">
            ${typeChip(r.record_type)}
            ${loc ? `<span class="text-xs text-slate-500">${escapeHtml(loc)}</span>` : ""}
            ${verified} ${also}
          </div>
          ${r.summary ? `<p class="mt-1.5 line-clamp-2 text-sm text-slate-500">${escapeHtml(r.summary)}</p>` : ""}
          ${reasons ? `<div class="mt-1">${reasons}</div>` : ""}
          ${actions ? `<div class="mt-2.5 flex flex-wrap gap-1.5">${actions}</div>` : ""}
        </div>
      </div>
    </article>`;
  }

  function skeletons(n = 4) {
    return Array.from({ length: n }).map(() =>
      `<div class="rounded-xl border border-slate-200 bg-white p-3"><div class="flex gap-3">
        <div class="h-12 w-12 flex-shrink-0 rounded-lg shimmer"></div>
        <div class="flex-1 space-y-2"><div class="h-3.5 w-1/2 rounded shimmer"></div>
        <div class="h-3 w-1/3 rounded shimmer"></div><div class="h-3 w-2/3 rounded shimmer"></div></div></div></div>`
    ).join("");
  }

  // ----------------------------------------------------------- detalle (drawer)
  function detailRow(label, value, isHtml) {
    const v = value == null || value === "" ? "—" : value;
    return `<div class="grid grid-cols-[7rem_1fr] gap-3 border-b border-slate-100 py-2 last:border-0">
      <dt class="text-xs font-medium uppercase tracking-wide text-slate-400">${escapeHtml(label)}</dt>
      <dd class="text-sm text-slate-800">${isHtml ? v : escapeHtml(v)}</dd></div>`;
  }

  function renderDetail(r) {
    const loc = [r.location_name, r.city, r.state, r.country].filter(Boolean).join(" · ");
    const tags = (r.tags || []).length
      ? r.tags.map((t) => `<span class="mr-1 inline-block rounded bg-slate-100 px-1.5 py-0.5 text-xs text-slate-600">${escapeHtml(t)}</span>`).join("")
      : "—";
    let src = escapeHtml(r.source_name || "—");
    if (r.source_url) src = `<a class="text-ink-900 underline" href="${escapeHtml(r.source_url)}" target="_blank" rel="noopener">${escapeHtml(r.source_name || r.source_url)} →</a>`;
    const also = r.entity_id
      ? `<a href="/entidad?id=${encodeURIComponent(r.entity_id)}" class="rh-action mt-3 inline-flex items-center gap-1.5 bg-ink-900 px-3 py-2 text-sm text-white hover:bg-ink-600">Ver en todas las fuentes →</a>`
      : "";

    // Protección de datos de las familias: enmascarar cédula/teléfono y, si es
    // menor, ocultar foto y contacto (mismo criterio ético que el bot).
    const esMenor = (r.age != null && Number(r.age) < 18) || (r.tags || []).includes("menor");
    const soloDig = (s) => String(s || "").replace(/\D/g, "");
    const maskTel = (s) => { const d = soloDig(s); return d.length >= 4 ? "•••• ••" + d.slice(-2) : (s ? "(protegido)" : ""); };
    const maskCed = (s) => { const d = soloDig(s); return d.length >= 4 ? "•••" + d.slice(-4) : (s ? "(protegida)" : ""); };
    const contactoVis = (r.contact && !esMenor) ? maskTel(r.contact) : "";
    const cedulaVis = r.cedula ? maskCed(r.cedula) : "";
    const mostrarFoto = r.image_url && !esMenor;
    const avisoMenor = esMenor
      ? `<div class="mb-4 border-l-4 border-ink-900 bg-slate-50 px-3 py-2 text-xs text-slate-700">Menor de edad: por protección se ocultan foto y contacto. Coordina con la fuente o la autoridad.</div>`
      : "";

    drawerType.innerHTML = typeChip(r.record_type);
    drawerTitle.textContent = r.title || r.person_name || "Detalle";
    drawerBody.innerHTML = `
      ${avisoMenor}
      ${mostrarFoto ? `<img src="${escapeHtml(r.image_url)}" alt="Foto de ${escapeHtml(r.person_name || r.title || typeLabel(r.record_type))}" referrerpolicy="no-referrer" class="mb-4 max-h-56 w-full object-cover ring-1 ring-slate-200" onerror="this.remove()">` : ""}
      ${actionLinks(r) ? `<div class="mb-4 flex flex-wrap gap-2">${actionLinks(r)}</div>` : ""}
      ${r.summary ? `<p class="mb-4 text-sm text-slate-600">${escapeHtml(r.summary)}</p>` : ""}
      <dl>
        ${detailRow("Persona", r.person_name)}
        ${detailRow("Cédula", cedulaVis)}
        ${detailRow("Edad", r.age)}
        ${detailRow("Organización", r.organization)}
        ${detailRow("Ubicación", loc)}
        ${detailRow("Contacto", contactoVis)}
        ${detailRow("Estado", r.status)}
        ${detailRow("Etiquetas", tags, true)}
        ${detailRow("Fuente", src, true)}
        ${detailRow("Observado", formatDate(r.observed_at))}
        ${detailRow("Actualizado", formatDate(r.updated_at))}
      </dl>
      ${also}`;
  }

  async function openRecord(id) {
    const dr = openDrawer(drawerEl);
    drawerTitle.textContent = "Cargando…";
    drawerType.innerHTML = "";
    drawerBody.innerHTML = skeletons(1);
    dr && dr.show();
    try {
      const r = await fetchJSON(`/api/records/${encodeURIComponent(id)}`);
      renderDetail(r);
    } catch (_) {
      drawerTitle.textContent = "Error";
      drawerBody.innerHTML = `<div class="rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-800">No se pudo cargar el registro.</div>`;
    }
  }

  // ----------------------------------------------------------- búsqueda
  function readParams(offset) {
    const p = new URLSearchParams();
    p.set("offset", String(offset));
    p.set("limit", "20");
    const q = queryInput.value.trim();
    const city = cityInput.value.trim();
    const src = sourceInput.value;
    if (q) p.set(q.match(/^\d{5,}$/) ? "cedula" : "q", q);
    if (city) p.set("city", city);
    if (src) p.set("source_id", src);
    if (state.type) p.set("record_type", state.type);
    if (dedupInput.checked) p.set("group_by_entity", "true");
    return p;
  }

  function showResults() { homeView.hidden = true; resultsView.hidden = false; }
  function showHome() { resultsView.hidden = true; homeView.hidden = false; }

  function renderResults(data, append) {
    clearMessage();
    resultCount.textContent = `Ordenados por relevancia (lo más parecido arriba) · ${compactNumber(data.total_matches)} coincidencias en ${compactNumber(data.source_count)} fuentes`;
    resultTime.textContent = `${compactNumber(data.elapsed_ms)} ms`;
    const html = data.results.map(recordCard).join("");
    if (append) resultsList.insertAdjacentHTML("beforeend", html);
    else resultsList.innerHTML = html || emptyState();
    const next = data.returned_offset + data.returned_limit;
    state.nextOffset = next < data.total_matches ? next : null;
    loadMoreButton.hidden = state.nextOffset === null;
  }

  function emptyState() {
    return `<div class="rounded-xl border border-dashed border-slate-300 bg-white p-8 text-center">
      <p class="font-semibold text-slate-700">Sin resultados</p>
      <p class="mt-1 text-sm text-slate-500">Ajusta los filtros o prueba con otro término. También puedes <a href="/mapa" class="text-ink-900 underline">ver el mapa</a>.</p></div>`;
  }

  async function runSearch(offset = 0, append = false) {
    if (state.loading) return;
    state.loading = true;
    const params = append && state.lastParams ? new URLSearchParams(state.lastParams) : readParams(offset);
    params.set("offset", String(offset));
    state.lastParams = new URLSearchParams(params);

    showResults();
    if (!append) { resultsHeading.focus(); resultsList.innerHTML = skeletons(); resultCount.textContent = "Buscando…"; resultTime.textContent = ""; }
    loadMoreButton.disabled = true;

    try {
      const data = await fetchJSON(`/api/records/search?${params}`);
      renderResults(data, append);
    } catch (err) {
      const d = err.payload?.detail || err.payload;
      const msg = d?.error || "Revisa la conexión e intenta de nuevo.";
      if (append) {
        // El error de "Cargar más" se muestra junto al botón, no arriba (fuera de pantalla).
        loadMoreButton.textContent = "Reintentar";
        resultCount.textContent = msg;
      } else {
        setMessage("error", d?.error_code || "No se pudo buscar", msg);
        resultsList.innerHTML = ""; resultCount.textContent = "Error"; loadMoreButton.hidden = true;
      }
    } finally {
      state.loading = false; loadMoreButton.disabled = false;
    }
  }

  // ----------------------------------------------------------- estado inicial
  function renderTypeBars(recordTypes) {
    const entries = Object.entries(recordTypes || {})
      .map(([type, count]) => ({ type, count: Number(count) || 0 }))
      .filter((e) => e.count > 0).sort((a, b) => b.count - a.count);
    if (!entries.length) { typeBars.innerHTML = `<p class="text-sm text-slate-400">Sin datos por tipo todavía.</p>`; return; }
    const max = entries[0].count;
    typeBars.innerHTML = entries.map((e) => {
      const m = typeMeta(e.type);
      const pct = Math.max(3, Math.round((e.count / max) * 100));
      return `<button type="button" data-type="${e.type}" class="rh-plain block w-full py-1.5 text-left">
        <div class="flex items-center justify-between text-sm"><span class="text-slate-600">${escapeHtml(m.label)}</span><span class="tabular-nums font-semibold text-slate-900">${compactNumber(e.count)}</span></div>
        <div class="mt-1 h-1.5 overflow-hidden rounded-full bg-slate-100"><div class="h-full rounded-full ${m.dot}" style="width:${pct}%"></div></div></button>`;
    }).join("");
  }

  // Rellena las insignias de conteo del bloque "Ayuda e insumos" (home)
  function fillAyudaCounts(recordTypes) {
    const rt = recordTypes || {};
    document.querySelectorAll("[data-cnt]").forEach((el) => {
      const n = Number(rt[el.dataset.cnt]) || 0;
      el.textContent = compactNumber(n);
    });
  }

  function applyStats(s) {
    statRecords.textContent = compactNumber(s.total_records);
    statSources.textContent = compactNumber(s.total_sources);
    const last = (s.sources || []).map((x) => x.last_sync).filter(Boolean).sort().pop();
    statFresh.textContent = last ? relativeTime(last) : "nunca";
    renderTypeBars(s.record_types);
    fillAyudaCounts(s.record_types);
    sourceInput.innerHTML = '<option value="">Todas las fuentes</option>' +
      (s.sources || []).filter((x) => x.record_count > 0).sort((a, b) => b.record_count - a.record_count)
        .map((x) => `<option value="${escapeHtml(x.id)}">${escapeHtml(x.name)} (${compactNumber(x.record_count)})</option>`).join("");
  }

  async function loadRecent() {
    try {
      const data = await fetchJSON(`/api/records/feed?since=0&limit=6`);
      const recs = (data.records || []).slice(-6).reverse();
      if (!recs.length) { recentList.innerHTML = `<p class="text-sm text-slate-400">Aún no hay registros. Sincroniza una fuente para empezar.</p>`; return; }
      recentList.innerHTML = recs.map((r) => recordCard({ record: r, reasons: [], also_in_count: 0, entity_id: r.entity_id })).join("");
    } catch (_) {
      recentList.innerHTML = `<p class="text-sm text-slate-400">No se pudieron cargar los registros recientes.</p>`;
    }
  }

  // ----------------------------------------------------------- chips
  function setActiveChip() {
    typeChips.querySelectorAll("[data-type]").forEach((b) =>
      b.setAttribute("aria-pressed", String(b.dataset.type === state.type)));
  }

  // ----------------------------------------------------------- eventos
  form.addEventListener("submit", (e) => { e.preventDefault(); runSearch(0, false); });

  typeChips.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-type]");
    if (!btn) return;
    state.type = btn.dataset.type;
    setActiveChip();
    runSearch(0, false);
  });

  clearButton.addEventListener("click", () => {
    form.reset(); state.type = ""; state.nextOffset = null; state.lastParams = null;
    setActiveChip(); clearMessage(); showHome(); queryInput.focus();
  });

  // Barras de tipo en home → buscar ese tipo
  typeBars.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-type]");
    if (!btn) return;
    state.type = btn.dataset.type; queryInput.value = ""; setActiveChip(); runSearch(0, false);
  });

  [resultsList, recentList].forEach((el) => el.addEventListener("click", (e) => {
    const item = e.target.closest("[data-id]");
    if (item) openRecord(item.dataset.id);
  }));

  loadMoreButton.addEventListener("click", () => { if (state.nextOffset !== null) runSearch(state.nextOffset, true); });

  // ----------------------------------------------------------- init
  window.RH.onStats(applyStats);
  loadRecent();
  queryInput.focus();
})();
