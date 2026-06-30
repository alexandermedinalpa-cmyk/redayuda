/* mapa.js — mapa Leaflet de registros con coordenadas. */
(function () {
  "use strict";
  const R = window.RH;
  const { escapeHtml, compactNumber, typeMeta, fetchJSON } = R;

  const TYPES = [
    { v: "", label: "Todo" },
    { v: "centro_acopio", label: "Acopio" },
    { v: "centro_donacion", label: "Donación" },
    { v: "persona_hospitalizada", label: "Hospitalizados" },
    { v: "recurso", label: "Recursos" },
    { v: "persona_desaparecida", label: "Desaparecidos" },
  ];

  const form = document.getElementById("mapForm");
  const queryInput = document.getElementById("mapQuery");
  const chipsEl = document.getElementById("mapChips");
  const countEl = document.getElementById("mapCount");
  const messageEl = document.getElementById("mapMessage");
  const legendEl = document.getElementById("mapLegend");

  const cityInput = document.getElementById("mapCity");
  let map, layer, state = { type: "", q: "", city: "" };

  // chips (reusa .rh-chip del sistema de diseño)
  chipsEl.innerHTML = TYPES.map((t) =>
    `<button type="button" class="rh-chip" data-type="${t.v}" aria-pressed="${t.v === "" ? "true" : "false"}">${t.label}</button>`
  ).join("");

  function setChips() {
    chipsEl.querySelectorAll("[data-type]").forEach((b) =>
      b.setAttribute("aria-pressed", String(b.dataset.type === state.type)));
  }

  // Leyenda: tipo ↔ ICONO (segundo canal, no solo color)
  if (legendEl) {
    legendEl.innerHTML = TYPES.filter((t) => t.v).map((t) => {
      const m = typeMeta(t.v);
      return `<span>${R.icons[m.icon]}${escapeHtml(t.label)}</span>`;
    }).join("");
  }

  // Marcador por tipo: icono distinto (no solo tono), borde negro siempre.
  function markerIcon(m) {
    return L.divIcon({
      className: "",
      html: `<span style="display:grid;place-items:center;width:26px;height:26px;background:#fff;border:1.5px solid #121212;color:#121212;box-shadow:0 1px 3px rgba(0,0,0,.45)"><span style="display:block;width:15px;height:15px">${R.icons[m.icon]}</span></span>`,
      iconSize: [26, 26], iconAnchor: [13, 13], popupAnchor: [0, -14],
    });
  }

  function initMap() {
    // scrollWheelZoom off: evita el "scroll-jacking"; se activa al hacer click.
    map = L.map("map", { scrollWheelZoom: false }).setView([8.0, -66.0], 6);
    map.on("click", () => map.scrollWheelZoom.enable());
    map.on("popupclose", () => map.scrollWheelZoom.disable());
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19, attribution: "© OpenStreetMap",
    }).addTo(map);
    layer = L.layerGroup().addTo(map);
  }

  function popupHtml(r) {
    const m = typeMeta(r.record_type);
    const loc = [r.city, r.state].filter(Boolean).join(", ");
    const geo = (r.latitude != null && r.longitude != null)
      ? `<div style="margin-top:6px;display:flex;gap:12px;font-size:11px">
           <a href="https://www.google.com/maps/search/?api=1&query=${r.latitude},${r.longitude}" target="_blank" rel="noopener" style="color:#121212">📍 Google Maps</a>
           <a href="https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=${r.latitude},${r.longitude}" target="_blank" rel="noopener" style="color:#121212">🧍 Street View</a>
         </div>`
      : "";
    return `<div style="min-width:180px">
      <div style="font-weight:600;margin-bottom:2px">${escapeHtml(r.title || r.person_name || "Registro")}</div>
      <div style="font-size:11px;text-transform:uppercase;letter-spacing:.04em;color:#4a4a4a">${escapeHtml(m.label)}${loc ? " · " + escapeHtml(loc) : ""}</div>
      ${geo}
      <button type="button" data-detail="${escapeHtml(r.id)}" style="margin-top:6px;font-size:11px;font-weight:500;text-transform:uppercase;letter-spacing:.05em;color:#121212;background:none;border:0;border-bottom:1px solid #121212;cursor:pointer;padding:0">Ver detalle →</button>
    </div>`;
  }

  async function load() {
    messageEl.innerHTML = "";
    countEl.textContent = "Cargando…";
    const p = new URLSearchParams({ limit: "100", offset: "0" });
    if (state.q) p.set(state.q.match(/^\d{5,}$/) ? "cedula" : "q", state.q);
    if (state.type) p.set("record_type", state.type);
    if (state.city) p.set("city", state.city);
    try {
      const data = await fetchJSON(`/api/records/search?${p}`);
      const withGeo = data.results.map((x) => x.record).filter((r) => r.latitude != null && r.longitude != null);
      layer.clearLayers();
      countEl.textContent = `${compactNumber(withGeo.length)} con ubicación · ${compactNumber(data.total_matches)} en total`;
      if (!withGeo.length) {
        messageEl.innerHTML = `<div class="border-l-4 border-ink-900 bg-ink-50 px-4 py-3 text-sm text-ink-900">⚠ Ningún resultado tiene coordenadas. Prueba otro filtro o usa la <a href="/" class="underline">búsqueda</a>.</div>`;
        return;
      }
      const pts = [];
      withGeo.forEach((r) => {
        const m = typeMeta(r.record_type);
        const marker = L.marker([r.latitude, r.longitude], { icon: markerIcon(m) }).bindPopup(popupHtml(r));
        layer.addLayer(marker);
        pts.push([r.latitude, r.longitude]);
      });
      if (pts.length) map.fitBounds(pts, { padding: [40, 40], maxZoom: 13 });
    } catch (_) {
      countEl.textContent = "";
      messageEl.innerHTML = `<div class="border-l-4 border-red-600 bg-ink-50 px-4 py-3 text-sm text-ink-900">✕ No se pudo cargar el mapa.</div>`;
    }
  }

  // eventos
  form.addEventListener("submit", (e) => { e.preventDefault(); state.q = queryInput.value.trim(); state.city = cityInput ? cityInput.value.trim() : ""; load(); });
  queryInput.addEventListener("search", () => { state.q = queryInput.value.trim(); load(); });
  if (cityInput) {
    cityInput.addEventListener("search", () => { state.city = cityInput.value.trim(); load(); });
    cityInput.addEventListener("change", () => { state.city = cityInput.value.trim(); load(); });
  }
  chipsEl.addEventListener("click", (e) => {
    const b = e.target.closest("[data-type]"); if (!b) return;
    state.type = b.dataset.type; setChips(); load();
  });
  // delegación del botón "ver detalle" dentro de los popups de Leaflet
  document.addEventListener("click", (e) => {
    const b = e.target.closest("[data-detail]");
    if (b && R.openRecord) R.openRecord(b.dataset.detail);
  });

  initMap();
  load();
})();
