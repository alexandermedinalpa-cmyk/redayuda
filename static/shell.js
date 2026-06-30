/* shell.js — Red Humanitaria de Datos (v2)
 * Inyecta nav + footer, cablea el menú móvil y el pulso de salud, y expone
 * window.RH con helpers compartidos por todas las páginas.
 * Carga con `defer`, después de ui.js (Drawer) y antes del script de cada página. */
(function (window, document) {
  "use strict";

  // ---------------------------------------------------------------- helpers
  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;").replaceAll("'", "&#039;");
  }

  function compactNumber(value) {
    if (value === null || value === undefined || Number.isNaN(Number(value))) return "—";
    return new Intl.NumberFormat("es-VE").format(Number(value));
  }

  function formatDate(value) {
    if (!value) return "—";
    const d = new Date(value);
    if (Number.isNaN(d.getTime())) return "—";
    return new Intl.DateTimeFormat("es-VE", { dateStyle: "medium", timeStyle: "short" }).format(d);
  }

  // "hace 3 h" / "hace 2 d" / "nunca"
  function relativeTime(value) {
    if (!value) return "nunca";
    const d = new Date(value);
    if (Number.isNaN(d.getTime())) return "—";
    const sec = Math.round((Date.now() - d.getTime()) / 1000);
    if (sec < 60) return "hace segundos";
    const min = Math.round(sec / 60);
    if (min < 60) return `hace ${min} min`;
    const h = Math.round(min / 60);
    if (h < 24) return `hace ${h} h`;
    const days = Math.round(h / 24);
    if (days < 30) return `hace ${days} d`;
    return formatDate(value);
  }

  // Semáforo de frescura por last_sync → tono Tailwind
  function freshness(value) {
    if (!value) return { tone: "slate", label: "sin sincronizar" };
    const h = (Date.now() - new Date(value).getTime()) / 36e5;
    if (h < 24) return { tone: "emerald", label: "al día" };
    if (h < 24 * 7) return { tone: "amber", label: "rezagada" };
    return { tone: "rose", label: "obsoleta" };
  }

  // ---------------------------------------------------------------- iconos
  const ICONS = {
    persona: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="8" r="3.25"/><path d="M5.5 19a6.5 6.5 0 0 1 13 0"/></svg>',
    centro: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M3.5 7.5 12 3l8.5 4.5v9L12 21l-8.5-4.5z"/><path d="M3.5 7.5 12 12l8.5-4.5M12 12v9"/></svg>',
    hospital: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M4 21V5a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v16"/><path d="M9 12h6M12 9v6M2 21h20"/></svg>',
    lugar: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M12 21s6-5.2 6-10a6 6 0 1 0-12 0c0 4.8 6 10 6 10z"/><circle cx="12" cy="11" r="2.25"/></svg>',
    phone: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M6.5 3.5h3l1.5 4-2 1.5a12 12 0 0 0 5.5 5.5l1.5-2 4 1.5v3a2 2 0 0 1-2 2A16 16 0 0 1 4.5 5.5a2 2 0 0 1 2-2z"/></svg>',
    pin: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M12 21s6-5.2 6-10a6 6 0 1 0-12 0c0 4.8 6 10 6 10z"/><circle cx="12" cy="11" r="2.25"/></svg>',
    link: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M10 13a5 5 0 0 0 7 0l2-2a5 5 0 0 0-7-7l-1 1"/><path d="M14 11a5 5 0 0 0-7 0l-2 2a5 5 0 0 0 7 7l1-1"/></svg>',
    layers: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="m12 3 9 5-9 5-9-5 9-5z"/><path d="m3 13 9 5 9-5"/></svg>',
  };

  // Metadatos por record_type: etiqueta, icono, color (clases Tailwind) y hex para mapa.
  // Monocromático: el chip es idéntico (borde negro); el tipo se distingue por
  // el cuadrito (sombra de gris) y la etiqueta. El mapa usa shades de gris.
  const CHIP = "bg-white text-ink-900 ring-ink-900";
  const TYPE_META = {
    persona_desaparecida: { label: "Persona desaparecida", icon: "persona", chip: CHIP, dot: "bg-ink-900", hex: "#121212" },
    persona_localizada:   { label: "Persona localizada",   icon: "persona", chip: CHIP, dot: "bg-ink-500", hex: "#4a4a4a" },
    persona_hospitalizada:{ label: "Persona hospitalizada",icon: "hospital",chip: CHIP, dot: "bg-ink-600", hex: "#292929" },
    centro_acopio:        { label: "Centro de acopio",     icon: "centro",  chip: CHIP, dot: "bg-ink-700", hex: "#3a3a3a" },
    centro_donacion:      { label: "Centro de donación",   icon: "centro",  chip: CHIP, dot: "bg-ink-400", hex: "#9b9b9b" },
    recurso:              { label: "Recurso",              icon: "lugar",   chip: CHIP, dot: "bg-ink-300", hex: "#cfcfcf" },
    otro:                 { label: "Otro",                 icon: "lugar",   chip: CHIP, dot: "bg-ink-200", hex: "#e0e0e0" },
  };
  function typeMeta(t) { return TYPE_META[t] || { label: t || "—", icon: "lugar", chip: CHIP, dot: "bg-ink-400", hex: "#9b9b9b" }; }
  function typeLabel(t) { return typeMeta(t).label; }

  // Chip de tipo (cuadrado, borde negro, etiqueta en mayúsculas)
  function typeChip(t) {
    const m = typeMeta(t);
    return `<span class="inline-flex items-center gap-1.5 px-2 py-0.5 text-[0.65rem] font-medium uppercase tracking-wide ring-1 ring-inset ${m.chip}"><span class="h-1.5 w-1.5 ${m.dot}"></span>${escapeHtml(m.label)}</span>`;
  }

  // Miniatura: imagen o icono por tipo
  function thumb(record, size = "h-12 w-12") {
    const m = typeMeta(record.record_type);
    if (record.image_url) {
      return `<img src="${escapeHtml(record.image_url)}" alt="Foto de ${escapeHtml(record.person_name || record.title || m.label)}" loading="lazy" referrerpolicy="no-referrer"
        class="${size} flex-shrink-0 rounded-lg object-cover ring-1 ring-slate-200"
        onerror="this.replaceWith(Object.assign(document.createElement('div'),{className:'${size} flex-shrink-0 grid place-items-center rounded-lg bg-slate-100 text-slate-400 ring-1 ring-slate-200',innerHTML:RH.icons.${m.icon}}))">`;
    }
    return `<div class="${size} flex-shrink-0 grid place-items-center rounded-lg bg-slate-100 text-slate-400 ring-1 ring-slate-200"><span class="block h-6 w-6">${ICONS[m.icon]}</span></div>`;
  }

  // Acciones directas de un registro (tel / mapa / fuente)
  function actionLinks(record) {
    const solid = "rh-action inline-flex items-center gap-1.5 bg-ink-900 px-3 py-1.5 text-xs text-white hover:bg-ink-600";
    const ghost = "rh-action inline-flex items-center gap-1.5 px-3 py-1.5 text-xs text-ink-900 ring-1 ring-inset ring-ink-900 hover:bg-ink-50";
    const out = [];
    if (record.contact) {
      const tel = String(record.contact).replace(/[^\d+]/g, "");
      if (tel.length >= 7) {
        out.push(`<a href="tel:${escapeHtml(tel)}" class="${solid}"><span class="h-3.5 w-3.5">${ICONS.phone}</span>Llamar</a>`);
      } else {
        out.push(`<span class="inline-flex items-center gap-1.5 px-2.5 py-1.5 text-xs text-ink-600 ring-1 ring-inset ring-ink-200">${escapeHtml(record.contact)}</span>`);
      }
    }
    if (record.latitude != null && record.longitude != null) {
      const lat = record.latitude, lon = record.longitude;
      out.push(`<a href="https://www.google.com/maps/search/?api=1&query=${lat},${lon}" target="_blank" rel="noopener" class="${solid}"><span class="h-3.5 w-3.5">${ICONS.pin}</span>Google Maps</a>`);
      out.push(`<a href="https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=${lat},${lon}" target="_blank" rel="noopener" class="${ghost}"><span class="h-3.5 w-3.5">${ICONS.pin}</span>Street View</a>`);
      out.push(`<a href="https://www.openstreetmap.org/?mlat=${lat}&mlon=${lon}#map=16/${lat}/${lon}" target="_blank" rel="noopener" class="${ghost}"><span class="h-3.5 w-3.5">${ICONS.pin}</span>OSM</a>`);
    }
    if (record.source_url) {
      out.push(`<a href="${escapeHtml(record.source_url)}" target="_blank" rel="noopener" class="${ghost}"><span class="h-3.5 w-3.5">${ICONS.link}</span>Fuente</a>`);
    }
    return out.join("");
  }

  async function fetchJSON(url, opts) {
    const res = await fetch(url, opts);
    const text = await res.text();
    let data = null;
    try { data = text ? JSON.parse(text) : null; } catch (_) { data = null; }
    if (!res.ok) {
      const err = new Error("http " + res.status);
      err.status = res.status; err.payload = data;
      throw err;
    }
    return data;
  }

  // ---------------------------------------------------------------- nav/footer
  const NAV = [
    { href: "/", label: "Buscar", key: "buscar" },
    { href: "/mapa", label: "Mapa", key: "mapa" },
    { href: "/fuentes", label: "Fuentes", key: "fuentes" },
    { href: "/desarrolladores", label: "Desarrolladores", key: "dev" },
    { href: "/contribuir", label: "Registrar fuente", key: "contribuir" },
  ];

  function isActive(href) {
    const p = location.pathname;
    if (href === "/") return p === "/";
    return p === href || p.startsWith(href + "/");
  }

  function renderShell() {
    const header = document.getElementById("rh-header");
    if (header) {
      const links = NAV.map((n) => {
        const active = isActive(n.href);
        const cls = active
          ? "text-ink-900 border-ink-900"
          : "text-ink-500 border-transparent hover:text-ink-900";
        return `<a href="${n.href}" data-nav="${n.key}" ${active ? 'aria-current="page"' : ""} class="px-1 py-1 text-xs font-medium uppercase tracking-wide border-b-2 ${cls} transition">${n.label}</a>`;
      }).join("");

      header.className = "sticky top-0 z-40 border-b border-ink-900 bg-white";
      header.innerHTML = `
        <div class="mx-auto flex max-w-6xl items-center gap-4 px-4 py-3">
          <a href="/" class="flex items-center gap-2.5">
            <span class="grid h-9 w-9 place-items-center bg-ink-900 text-sm font-bold tracking-tight text-white">RH</span>
            <span class="hidden sm:flex flex-col leading-tight">
              <span class="text-sm font-medium text-ink-900">Red Humanitaria de Datos</span>
              <span class="text-[0.65rem] uppercase tracking-wide text-ink-500">Índice común · Venezuela</span>
            </span>
          </a>
          <nav class="ml-auto hidden items-center gap-5 md:flex" aria-label="Navegación principal">${links}
            <span id="rh-health" class="inline-flex items-center gap-1.5 px-2.5 py-1 text-[0.65rem] font-medium uppercase tracking-wide text-ink-500 ring-1 ring-inset ring-ink-200"><span class="h-1.5 w-1.5 bg-ink-300"></span>…</span>
          </nav>
          <button id="rh-menu-btn" type="button" class="ml-auto inline-grid h-9 w-9 place-items-center text-ink-900 ring-1 ring-ink-900 md:hidden" aria-label="Abrir menú" aria-expanded="false">
            <svg viewBox="0 0 24 24" class="h-5 w-5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M4 7h16M4 12h16M4 17h16"/></svg>
          </button>
        </div>
        <nav id="rh-menu" hidden class="border-t border-ink-200 bg-white px-4 py-2 md:hidden" aria-label="Navegación móvil">
          ${NAV.map((n) => `<a href="${n.href}" class="block px-2 py-2 text-xs font-medium uppercase tracking-wide ${isActive(n.href) ? "text-ink-900" : "text-ink-500"}">${n.label}</a>`).join("")}
          <span id="rh-health-m" class="mt-1 block px-2 py-2 text-[0.65rem] font-medium uppercase tracking-wide text-ink-500">…</span>
        </nav>`;

      const btn = header.querySelector("#rh-menu-btn");
      const menu = header.querySelector("#rh-menu");
      btn.addEventListener("click", () => {
        const open = menu.hidden;
        menu.hidden = !open;
        btn.setAttribute("aria-expanded", String(open));
      });
    }

    const footer = document.getElementById("rh-footer");
    if (footer) {
      footer.className = "mt-16 border-t border-ink-900 bg-white";
      footer.innerHTML = `
        <div class="mx-auto flex max-w-6xl flex-col gap-3 px-4 py-8 text-sm text-ink-500 sm:flex-row sm:items-center sm:justify-between">
          <span>Red Humanitaria de Datos — un índice común para las apps de ayuda, en vez de duplicar el esfuerzo.</span>
          <nav class="flex gap-5 text-xs font-medium uppercase tracking-wide" aria-label="Enlaces del pie">
            <a class="hover:text-ink-900" href="/fuentes">Fuentes</a>
            <a class="hover:text-ink-900" href="/desarrolladores">Desarrolladores</a>
            <a class="hover:text-ink-900" href="/docs">API docs</a>
            <a class="hover:text-ink-900" href="/admin">Admin</a>
          </nav>
        </div>`;
    }
  }

  async function loadHealth() {
    const pill = document.getElementById("rh-health");
    if (!pill) return;
    try {
      const s = await fetchJSON("/api/network/stats");
      const ok = s.total_records > 0;
      pill.className = "inline-flex items-center gap-1.5 px-2.5 py-1 text-[0.65rem] font-medium uppercase tracking-wide text-ink-900 ring-1 ring-inset ring-ink-900";
      pill.innerHTML = `<span class="h-1.5 w-1.5 ${ok ? "bg-ink-900" : "bg-ink-300"}"></span>${compactNumber(s.total_records)} registros`;
      const pillM = document.getElementById("rh-health-m");
      if (pillM) pillM.textContent = `${compactNumber(s.total_records)} registros · ${compactNumber(s.total_sources)} fuentes`;
      window.RH._stats = s;
      document.dispatchEvent(new CustomEvent("rh:stats", { detail: s }));
    } catch (_) {
      pill.className = "inline-flex items-center gap-1.5 px-2.5 py-1 text-[0.65rem] font-medium uppercase tracking-wide text-red-600 ring-1 ring-inset ring-red-600";
      pill.innerHTML = `<span class="h-1.5 w-1.5 bg-red-600"></span>sin conexión`;
    }
  }

  function openDrawer(el) {
    return window.Drawer ? window.Drawer.getOrCreateInstance(el) : null;
  }

  // ---------------------------------------------------------------- export
  window.RH = {
    escapeHtml, compactNumber, formatDate, relativeTime, freshness,
    typeMeta, typeLabel, typeChip, thumb, actionLinks, fetchJSON,
    openDrawer, icons: ICONS, TYPE_META,
    onStats(cb) { if (window.RH._stats) cb(window.RH._stats); document.addEventListener("rh:stats", (e) => cb(e.detail)); },
    _stats: null,
  };

  function boot() { renderShell(); loadHealth(); }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})(window, document);
