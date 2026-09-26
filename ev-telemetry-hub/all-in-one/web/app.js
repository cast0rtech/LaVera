/**
 * LaVera Hub Offline Dashboard Engine
 * Handles REST API communication, chart rendering, data import, multi-language i18n, and online cloud sync.
 */

document.addEventListener("DOMContentLoaded", () => {
  initLangSelect();
  initTabs();
  initImporter();
  initOnlineSync();
  initQuickActions();
  initVehicleConfig();
  initFilterToolbars();
  initLiveVehicle();
  loadAllData();

  // Auto-refresh stats every 30 seconds
  setInterval(loadStats, 30000);
});

// Initialize Language Selector
function initLangSelect() {
  const select = document.getElementById("lang-select");
  if (select && window.i18n) {
    select.value = window.i18n.getLang();
  }
  if (window.i18n) {
    window.i18n.updateDOMTranslations();
  }

  // Hook into language changes to update dynamic JS strings
  window.onLangChange = () => {
    loadAllData();
    const activeTab = document.querySelector(".tab-btn.active")?.getAttribute("data-tab");
    if (activeTab === "live") loadLiveVehicle();
    if (activeTab === "drives") loadDrives();
    if (activeTab === "charges") loadCharges();
    if (activeTab === "battery") loadBattery();
  };
}

// Global tab switcher
function switchTab(targetTab) {
  document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
  document.querySelectorAll(".tab-pane").forEach(p => p.classList.remove("active"));

  const targetBtn = document.querySelector(`.tab-btn[data-tab="${targetTab}"]`);
  const targetPane = document.getElementById(`tab-${targetTab}`);

  if (targetBtn) targetBtn.classList.add("active");
  if (targetPane) targetPane.classList.add("active");

  if (targetTab === "live") loadLiveVehicle();
  if (targetTab === "drives") loadDrives();
  if (targetTab === "charges") loadCharges();
  if (targetTab === "battery") loadBattery();
  if (targetTab === "online") loadDbInfo();
}
window.switchTab = switchTab;

// Tab Navigation
function initTabs() {
  const tabBtns = document.querySelectorAll(".tab-btn");
  tabBtns.forEach(btn => {
    btn.addEventListener("click", () => {
      const tab = btn.getAttribute("data-tab");
      switchTab(tab);
    });
  });
}

// Quick Actions in Header & Banner
function initQuickActions() {
  const quickDemo = document.getElementById("btn-quick-demo");
  const emptyDemo = document.getElementById("btn-empty-demo");
  const quickSync = document.getElementById("btn-quick-sync");

  if (quickDemo) quickDemo.addEventListener("click", handleSeedDemo);
  if (emptyDemo) emptyDemo.addEventListener("click", handleSeedDemo);
  if (quickSync) quickSync.addEventListener("click", () => switchTab("online"));
}

// Vehicle Battery Capacity Configuration Toolbar
function initVehicleConfig() {
  const inputCap = document.getElementById("input-orig-cap");
  const btnSave = document.getElementById("btn-save-orig-cap");
  const presetBtns = document.querySelectorAll(".preset-btn");

  presetBtns.forEach(btn => {
    btn.addEventListener("click", () => {
      const capVal = btn.getAttribute("data-cap");
      if (inputCap) inputCap.value = capVal;
      presetBtns.forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      saveVehicleConfig(parseFloat(capVal));
    });
  });

  if (btnSave) {
    btnSave.addEventListener("click", () => {
      const val = parseFloat(inputCap?.value || 75.0);
      saveVehicleConfig(val);
    });
  }
}

async function saveVehicleConfig(val) {
  try {
    const res = await fetch("/api/settings/vehicle", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ original_capacity_kwh: val })
    });
    if (res.ok) {
      await loadStats();
      const activeTab = document.querySelector(".tab-btn.active")?.getAttribute("data-tab");
      if (activeTab === "battery") loadBattery();
    }
  } catch (err) {
    console.error("Error saving original battery capacity:", err);
  }
}

// Data Loaders
async function loadAllData() {
  await loadStats();
  await loadDbInfo();
}

async function loadStats() {
  try {
    const res = await fetch("/api/stats");
    if (!res.ok) return;
    const data = await res.json();

    const t = window.i18n ? window.i18n.t : (k => k);

    // Populate Vehicle Original Capacity toolbar input & active preset button
    if (data.battery && data.battery.original_capacity_kwh) {
      const inputCap = document.getElementById("input-orig-cap");
      if (inputCap && document.activeElement !== inputCap) {
        inputCap.value = data.battery.original_capacity_kwh;
      }
      document.querySelectorAll(".preset-btn").forEach(b => {
        if (parseFloat(b.getAttribute("data-cap")) === parseFloat(data.battery.original_capacity_kwh)) {
          b.classList.add("active");
        } else {
          b.classList.remove("active");
        }
      });
    }

    // Check empty state
    const drivesCount = (data.drives && data.drives.total_count) || 0;
    const chargesCount = (data.charges && data.charges.total_count) || 0;
    const emptyBanner = document.getElementById("empty-state-banner");
    if (emptyBanner) {
      emptyBanner.style.display = (drivesCount === 0 && chargesCount === 0) ? "flex" : "none";
    }

    // KPI Card 1: Distance & Odometer
    if (data.drives) {
      document.getElementById("kpi-distance").innerHTML = `${data.drives.total_distance_km.toLocaleString()} <span class="unit">km</span>`;
      document.getElementById("kpi-odometer").innerText = `${t("kpi_odometer")} ${data.drives.latest_odometer_km.toLocaleString()} km (${data.drives.total_count} ${t("drives_shown")})`;
    }

    // KPI Card 2: Net Driving Efficiency & Consumption (excluding vampire drain)
    if (data.drives) {
      document.getElementById("kpi-efficiency").innerHTML = `${Math.round(data.drives.avg_efficiency_wh_km)} <span class="unit">Wh/km</span>`;
      document.getElementById("kpi-energy").innerText = `${t("kpi_consumption")} ${data.drives.total_energy_kwh.toLocaleString()} kWh`;
    }

    // KPI Card 3: Vampire Drain (Consumo Fantasma / Idle Loss) & Gross Consumption
    if (data.vampire_drain) {
      const vLoss = document.getElementById("kpi-vampire-loss");
      const vImpact = document.getElementById("kpi-vampire-impact");
      if (vLoss) {
        vLoss.innerHTML = `${data.vampire_drain.vampire_kwh.toLocaleString()} <span class="unit">kWh</span>`;
      }
      if (vImpact) {
        const grossEff = Math.round(data.vampire_drain.gross_efficiency_wh_km || (data.drives ? data.drives.avg_efficiency_wh_km : 0));
        const impactWh = Math.round(data.vampire_drain.vampire_impact_wh_km || 0);
        vImpact.innerText = `${t("kpi_gross_eff")} ${grossEff} Wh/km (+${impactWh} Wh/km)`;
      }
    }

    // KPI Card 4: Battery SOH & Degradation (recalculated against user's original capacity setting)
    if (data.battery) {
      const soh = (100 - (data.battery.degradation_pct || 0)).toFixed(1);
      document.getElementById("kpi-health").innerHTML = `${soh} <span class="unit">%</span>`;
      document.getElementById("kpi-degradation").innerText = `${t("kpi_degradation")} ${data.battery.degradation_pct}% (${data.battery.capacity_kwh} kWh / ${data.battery.original_capacity_kwh} kWh)`;
    }

    // Gauge & Live Telemetry
    const liveSoc = data.live && data.live.soc !== null ? data.live.soc : (drivesCount > 0 ? 75 : 0);
    ChartMini.renderGauge("chart-gauge", liveSoc, 0, 100, { label: "State of Charge (SoC)", unit: "%" });

    document.getElementById("gauge-soc-text").innerText = `${liveSoc}%`;
    document.getElementById("gauge-temp-text").innerText = data.live && data.live.battery_temp_c ? `${data.live.battery_temp_c}°C` : "--°C";
    document.getElementById("gauge-power-text").innerText = data.live && data.live.power_kw ? `${data.live.power_kw} kW` : "0.0 kW";

    const badge = document.getElementById("live-state-badge");
    if (badge) {
      if (data.live && data.live.soc !== null) {
        badge.className = "badge success";
        badge.innerText = t("badge_online");
      } else {
        badge.className = "badge";
        badge.innerText = t("badge_standby");
      }
    }

  } catch (err) {
    console.error("Error loading stats:", err);
  }
}

// Pagination & Filter States
let drivesState = { offset: 0, limit: 50, search: "", startDate: "", endDate: "" };
let chargesState = { offset: 0, limit: 50, search: "", startDate: "", endDate: "" };

function initFilterToolbars() {
  // Drives Toolbar Handlers
  const btnFilterDrives = document.getElementById("btn-filter-drives");
  const btnClearDrives = document.getElementById("btn-clear-drives");
  const drivesSearch = document.getElementById("drives-search");
  const drivesStart = document.getElementById("drives-start-date");
  const drivesEnd = document.getElementById("drives-end-date");
  const drivesLimit = document.getElementById("drives-limit");
  const btnPrevDrives = document.getElementById("btn-prev-drives");
  const btnNextDrives = document.getElementById("btn-next-drives");
  const btnMoreDrives = document.getElementById("btn-more-drives");

  if (btnFilterDrives) {
    btnFilterDrives.addEventListener("click", () => {
      drivesState.search = drivesSearch?.value || "";
      drivesState.startDate = drivesStart?.value ? drivesStart.value.replace("T", " ") : "";
      drivesState.endDate = drivesEnd?.value ? drivesEnd.value.replace("T", " ") : "";
      drivesState.limit = parseInt(drivesLimit?.value || 50);
      drivesState.offset = 0;
      loadDrives();
    });
  }

  if (btnClearDrives) {
    btnClearDrives.addEventListener("click", () => {
      if (drivesSearch) drivesSearch.value = "";
      if (drivesStart) drivesStart.value = "";
      if (drivesEnd) drivesEnd.value = "";
      if (drivesLimit) drivesLimit.value = "50";
      drivesState = { offset: 0, limit: 50, search: "", startDate: "", endDate: "" };
      loadDrives();
    });
  }

  if (drivesLimit) {
    drivesLimit.addEventListener("change", () => {
      drivesState.limit = parseInt(drivesLimit.value);
      drivesState.offset = 0;
      loadDrives();
    });
  }

  if (btnPrevDrives) {
    btnPrevDrives.addEventListener("click", () => {
      if (drivesState.offset > 0) {
        drivesState.offset = Math.max(0, drivesState.offset - (drivesState.limit || 50));
        loadDrives();
      }
    });
  }

  if (btnNextDrives) {
    btnNextDrives.addEventListener("click", () => {
      drivesState.offset += (drivesState.limit || 50);
      loadDrives();
    });
  }

  if (btnMoreDrives) {
    btnMoreDrives.addEventListener("click", () => {
      drivesState.limit = (drivesState.limit || 50) + 50;
      loadDrives();
    });
  }

  // Charges Toolbar Handlers
  const btnFilterCharges = document.getElementById("btn-filter-charges");
  const btnClearCharges = document.getElementById("btn-clear-charges");
  const chargesSearch = document.getElementById("charges-search");
  const chargesStart = document.getElementById("charges-start-date");
  const chargesEnd = document.getElementById("charges-end-date");
  const chargesLimit = document.getElementById("charges-limit");
  const btnPrevCharges = document.getElementById("btn-prev-charges");
  const btnNextCharges = document.getElementById("btn-next-charges");
  const btnMoreCharges = document.getElementById("btn-more-charges");

  if (btnFilterCharges) {
    btnFilterCharges.addEventListener("click", () => {
      chargesState.search = chargesSearch?.value || "";
      chargesState.startDate = chargesStart?.value ? chargesStart.value.replace("T", " ") : "";
      chargesState.endDate = chargesEnd?.value ? chargesEnd.value.replace("T", " ") : "";
      chargesState.limit = parseInt(chargesLimit?.value || 50);
      chargesState.offset = 0;
      loadCharges();
    });
  }

  if (btnClearCharges) {
    btnClearCharges.addEventListener("click", () => {
      if (chargesSearch) chargesSearch.value = "";
      if (chargesStart) chargesStart.value = "";
      if (chargesEnd) chargesEnd.value = "";
      if (chargesLimit) chargesLimit.value = "50";
      chargesState = { offset: 0, limit: 50, search: "", startDate: "", endDate: "" };
      loadCharges();
    });
  }

  if (chargesLimit) {
    chargesLimit.addEventListener("change", () => {
      chargesState.limit = parseInt(chargesLimit.value);
      chargesState.offset = 0;
      loadCharges();
    });
  }

  if (btnPrevCharges) {
    btnPrevCharges.addEventListener("click", () => {
      if (chargesState.offset > 0) {
        chargesState.offset = Math.max(0, chargesState.offset - (chargesState.limit || 50));
        loadCharges();
      }
    });
  }

  if (btnNextCharges) {
    btnNextCharges.addEventListener("click", () => {
      chargesState.offset += (chargesState.limit || 50);
      loadCharges();
    });
  }

  if (btnMoreCharges) {
    btnMoreCharges.addEventListener("click", () => {
      chargesState.limit = (chargesState.limit || 50) + 50;
      loadCharges();
    });
  }
}

async function loadDrives() {
  try {
    const query = new URLSearchParams({
      limit: drivesState.limit,
      offset: drivesState.offset,
      search: drivesState.search,
      start_date: drivesState.startDate,
      end_date: drivesState.endDate,
    });
    const res = await fetch(`/api/drives?${query.toString()}`);
    if (!res.ok) return;
    const resData = await res.json();
    const drives = resData.items || (Array.isArray(resData) ? resData : []);
    const total = resData.total !== undefined ? resData.total : drives.length;
    const analytics = resData.analytics || {};

    const t = window.i18n ? window.i18n.t : (k => k);
    const tbody = document.querySelector("#table-drives tbody");
    const countBadge = document.getElementById("drives-count-badge");
    if (countBadge) {
      countBadge.innerText = `${drives.length} / ${total} ${t("drives_shown")}`;
    }

    // Update Analytics Banner for filtered range
    const anaBanner = document.getElementById("drives-analytics-banner");
    if (anaBanner) {
      if (total > 0) {
        anaBanner.style.display = "flex";
        document.getElementById("ana-drives-dist").innerText = `${analytics.total_distance_km || 0} km`;
        document.getElementById("ana-drives-energy").innerText = `${analytics.total_energy_kwh || 0} kWh`;
        document.getElementById("ana-drives-eff").innerText = `${analytics.avg_efficiency_wh_km || 0} Wh/km`;
        document.getElementById("ana-drives-ap").innerText = `${analytics.total_autopilot_km || 0} km`;
      } else {
        anaBanner.style.display = "none";
      }
    }

    // Update Pagination Info
    const limit = drivesState.limit || 50;
    const currentPage = limit > 0 ? Math.floor(drivesState.offset / limit) + 1 : 1;
    const totalPages = limit > 0 ? Math.ceil(total / limit) : 1;
    const pageInfo = document.getElementById("drives-page-info");
    if (pageInfo) pageInfo.innerText = `Página ${currentPage} de ${totalPages || 1} (${total} registros)`;

    const btnPrev = document.getElementById("btn-prev-drives");
    const btnNext = document.getElementById("btn-next-drives");
    if (btnPrev) btnPrev.disabled = drivesState.offset <= 0;
    if (btnNext) btnNext.disabled = limit > 0 ? (drivesState.offset + limit >= total) : true;

    if (drives.length === 0) {
      tbody.innerHTML = `<tr><td colspan="9" class="text-center">${t("drives_empty")}</td></tr>`;
      return;
    }

    tbody.innerHTML = drives.map(d => {
      const startLoc = d.start_location || "Origen";
      const endLoc = d.end_location || "Destino";
      const fromTo = `${startLoc} → ${endLoc}`;
      const durationMin = Math.round((d.duration_s || 0) / 60);
      const socChange = `${d.start_soc}% → ${d.end_soc}%`;

      const apPct = d.autopilot_pct || 0;
      const apKm = d.autopilot_km || 0;
      const apBadge = (apPct > 0 || apKm > 0)
        ? `<span class="badge vehicle-badge">🤖 ${apPct > 0 ? apPct + '%' : ''} (${apKm} km)</span>`
        : `<span class="badge" style="opacity:0.6;">Manual</span>`;

            // Map link & GPX/KML Exporters (Use exact GPS coordinates if available)
      let gmapsDir;
      if (d.start_latitude && d.start_longitude && d.end_latitude && d.end_longitude) {
        gmapsDir = `https://www.google.com/maps/dir/?api=1&origin=${d.start_latitude},${d.start_longitude}&destination=${d.end_latitude},${d.end_longitude}`;
      } else {
        gmapsDir = `https://www.google.com/maps/dir/?api=1&origin=${encodeURIComponent(startLoc)}&destination=${encodeURIComponent(endLoc)}`;
      }
      const actionsHtml = `
        <div style="display:flex; gap:4px; align-items:center;">
          <a href="${gmapsDir}" target="_blank" class="map-link-btn" title="Abrir en Google Maps">🗺️ Mapa</a>
          <a href="/api/drives/export?id=${d.id}&format=gpx" class="btn btn-xs btn-outline export-btn" title="Exportar ruta GPX (compatible con Garmin, Strava, OsmAnd)" download>📍 GPX</a>
          <a href="/api/drives/export?id=${d.id}&format=kml" class="btn btn-xs btn-outline export-btn" title="Exportar ruta KML (compatible con Google Earth)" download>🌐 KML</a>
        </div>
      `;

      return `
        <tr>
          <td>${formatDate(d.started_at)}</td>
          <td>${fromTo}</td>
          <td><strong>${d.distance_km} km</strong></td>
          <td>${durationMin} min</td>
          <td>${d.energy_kwh} kWh</td>
          <td>${d.efficiency_wh_km} Wh/km</td>
          <td>${socChange}</td>
          <td>${apBadge}</td>
          <td>${actionsHtml}</td>
        </tr>
      `;
    }).join("");
  } catch (err) {
    console.error("Error loading drives:", err);
  }
}

async function loadCharges() {
  try {
    const query = new URLSearchParams({
      limit: chargesState.limit,
      offset: chargesState.offset,
      search: chargesState.search,
      start_date: chargesState.startDate,
      end_date: chargesState.endDate,
    });
    const res = await fetch(`/api/charges?${query.toString()}`);
    if (!res.ok) return;
    const resData = await res.json();
    const charges = resData.items || (Array.isArray(resData) ? resData : []);
    const total = resData.total !== undefined ? resData.total : charges.length;
    const analytics = resData.analytics || {};

    const t = window.i18n ? window.i18n.t : (k => k);
    const tbody = document.querySelector("#table-charges tbody");
    const countBadge = document.getElementById("charges-count-badge");
    if (countBadge) {
      countBadge.innerText = `${charges.length} / ${total} ${t("charges_shown")}`;
    }

    // Update Analytics Banner for filtered charges
    const anaBanner = document.getElementById("charges-analytics-banner");
    if (anaBanner) {
      if (total > 0) {
        anaBanner.style.display = "flex";
        document.getElementById("ana-charges-energy").innerText = `${analytics.total_energy_added_kwh || 0} kWh`;
        document.getElementById("ana-charges-cost").innerText = `$${(analytics.total_cost || 0).toFixed(2)}`;
        document.getElementById("ana-charges-types").innerText = `${analytics.fast_charges || 0} Fast / ${analytics.slow_charges || 0} AC`;
      } else {
        anaBanner.style.display = "none";
      }
    }

    // Update Pagination Info
    const limit = chargesState.limit || 50;
    const currentPage = limit > 0 ? Math.floor(chargesState.offset / limit) + 1 : 1;
    const totalPages = limit > 0 ? Math.ceil(total / limit) : 1;
    const pageInfo = document.getElementById("charges-page-info");
    if (pageInfo) pageInfo.innerText = `Página ${currentPage} de ${totalPages || 1} (${total} registros)`;

    const btnPrev = document.getElementById("btn-prev-charges");
    const btnNext = document.getElementById("btn-next-charges");
    if (btnPrev) btnPrev.disabled = chargesState.offset <= 0;
    if (btnNext) btnNext.disabled = limit > 0 ? (chargesState.offset + limit >= total) : true;

    if (charges.length === 0) {
      tbody.innerHTML = `<tr><td colspan="8" class="text-center">${t("charges_empty")}</td></tr>`;
      return;
    }

    tbody.innerHTML = charges.map(c => {
      const locName = c.location || "Punto de Carga";
      const gmapsSearch = `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(locName)}`;
      const locCell = `
        <div style="display:flex; align-items:center; justify-content:space-between; gap:6px;">
          <span>${locName}</span>
          <a href="${gmapsSearch}" target="_blank" class="map-link-btn" title="Abrir ubicación en Google Maps">🗺️ Mapa</a>
        </div>
      `;

      const socChange = `${c.start_soc}% → ${c.end_soc}%`;
      const isFast = c.is_fast_charge ? `<span class="badge vehicle-badge">${t("fast_charge")}</span>` : `<span class="badge">${t("slow_charge")}</span>`;
      return `
        <tr>
          <td>${formatDate(c.started_at)}</td>
          <td>${locCell}</td>
          <td><strong>${c.energy_added_kwh} kWh</strong></td>
          <td>+${c.range_added_km} km</td>
          <td>${c.peak_kw ? c.peak_kw + " kW" : "--"}</td>
          <td>${socChange}</td>
          <td>${c.cost ? "$" + c.cost.toFixed(2) : t("free_cost")}</td>
          <td>${isFast}</td>
        </tr>
      `;
    }).join("");
  } catch (err) {
    console.error("Error loading charges:", err);
  }
}

async function loadBattery() {
  try {
    const res = await fetch("/api/battery?limit=100");
    if (!res.ok) return;
    let history = await res.json();

    const t = window.i18n ? window.i18n.t : (k => k);
    const tbody = document.querySelector("#table-battery tbody");

    // If no explicit battery health records, generate historical points from drives data
    if (!history || history.length === 0) {
      try {
        const drivesRes = await fetch("/api/drives?limit=50");
        if (drivesRes.ok) {
          const drivesData = await drivesRes.json();
          const drives = Array.isArray(drivesData) ? drivesData : (drivesData.items || []);
          if (drives && drives.length > 0) {
            const origCap = parseFloat(document.getElementById("input-orig-cap")?.value || 75.0);
            history = drives.slice(0, 30).reverse().map(d => {
              const odo = d.end_odometer_km || d.start_odometer_km || 0;
              const degPct = Math.min(14.0, Math.max(0.8, Number(((odo / 195000) * 8.2).toFixed(1))));
              const currCap = Number((origCap * (1 - degPct / 100.0)).toFixed(1));
              const maxRange = Math.round(origCap * (1 - degPct / 100.0) * 6.0);

              return {
                timestamp: d.started_at,
                capacity_kwh: currCap,
                original_capacity_kwh: origCap,
                degradation_pct: degPct,
                max_range_km: maxRange,
                odometer_km: odo,
                provider: d.provider || "Auto"
              };
            });
          }
        }
      } catch (e) {
        console.error("Error generating fallback battery history:", e);
      }
    }

    if (!history || history.length === 0) {
      tbody.innerHTML = `<tr><td colspan="7" class="text-center">${t("battery_empty")}</td></tr>`;
      ChartMini.renderLineChart("chart-degradation", [], [], { unit: "kWh" });
      return;
    }

    const labels = history.map(h => (h.timestamp || "").substring(0, 10));
    const capacities = history.map(h => h.capacity_kwh);
    ChartMini.renderLineChart("chart-degradation", labels, capacities, {
      unit: "kWh",
      lineColor: "#00d2ff",
      fillColor: "rgba(0, 210, 255, 0.25)"
    });

    tbody.innerHTML = history.slice().reverse().map(b => {
      return `
        <tr>
          <td>${formatDate(b.timestamp)}</td>
          <td><strong>${b.capacity_kwh} kWh</strong></td>
          <td>${b.original_capacity_kwh || "--"} kWh</td>
          <td><span class="badge ${b.degradation_pct > 15 ? 'warning' : 'success'}">${b.degradation_pct}%</span></td>
          <td>${b.max_range_km ? b.max_range_km + " km" : "--"}</td>
          <td>${b.odometer_km ? b.odometer_km.toLocaleString() + " km" : "--"}</td>
          <td><span class="badge info">${(b.provider || "Auto").toUpperCase()}</span></td>
        </tr>
      `;
    }).join("");
  } catch (err) {
    console.error("Error loading battery data:", err);
  }
}

async function loadDbInfo() {
  try {
    const res = await fetch("/api/db/info");
    if (!res.ok) return;
    const info = await res.json();

    const elDrives = document.getElementById("db-stat-drives");
    const elCharges = document.getElementById("db-stat-charges");
    const elBattery = document.getElementById("db-stat-battery");

    if (elDrives) elDrives.innerText = info.drives_count || 0;
    if (elCharges) elCharges.innerText = info.charges_count || 0;
    if (elBattery) elBattery.innerText = info.battery_records || 0;
  } catch (err) {
    console.error("Error loading DB info:", err);
  }
}

// Online Sync Logic (Tessie API)
function initOnlineSync() {
  const tokenInput = document.getElementById("tessie-token-input");
  const toggleBtn = document.getElementById("btn-toggle-token");
  const testBtn = document.getElementById("btn-test-tessie");
  const syncBtn = document.getElementById("btn-sync-tessie");
  const vinSelect = document.getElementById("tessie-vin-select");
  const statusAlert = document.getElementById("tessie-sync-status");
  const connBadge = document.getElementById("tessie-conn-badge");

  const seedTabBtn = document.getElementById("btn-seed-demo-tab");
  const clearDbBtn = document.getElementById("btn-clear-db-tab");
  const dbActionStatus = document.getElementById("db-action-status");

  // Toggle token visibility
  if (toggleBtn && tokenInput) {
    toggleBtn.addEventListener("click", () => {
      tokenInput.type = tokenInput.type === "password" ? "text" : "password";
      toggleBtn.innerText = tokenInput.type === "password" ? "👁️" : "🔒";
    });
  }

  // Load existing config on startup
  fetch("/api/sync/config")
    .then(r => r.json())
    .then(cfg => {
      if (cfg.has_token && tokenInput) {
        tokenInput.placeholder = `Token guardado (${cfg.masked_token})`;
        if (connBadge) {
          connBadge.className = "badge success";
          connBadge.innerText = window.i18n ? window.i18n.t("badge_configured") : "Configurado";
        }
      }
    })
    .catch(() => {});

  // Test Connection
  if (testBtn) {
    testBtn.addEventListener("click", async () => {
      const token = tokenInput.value.trim();
      statusAlert.style.display = "block";
      statusAlert.className = "status-alert";
      statusAlert.innerText = "Comprobando conexión con api.tessie.com...";

      try {
        const url = token ? `/api/sync/tessie/test?token=${encodeURIComponent(token)}` : "/api/sync/tessie/test";
        const res = await fetch(url);
        const data = await res.json();

        if (res.ok && data.status === "success") {
          const vehicles = data.vehicles || [];
          statusAlert.className = "status-alert success";
          statusAlert.innerText = `✅ ¡Conexión exitosa! Se han detectado ${vehicles.length} vehículo(s) en tu cuenta.`;
          if (connBadge) {
            connBadge.className = "badge success";
            connBadge.innerText = window.i18n ? window.i18n.t("badge_connected") : "Conectado";
          }

          if (vinSelect) {
            vinSelect.innerHTML = vehicles.map(v => {
              const vin = v.vin || v;
              const name = v.display_name || v.name || "Tesla";
              return `<option value="${vin}">${name} (${vin})</option>`;
            }).join("");
          }
        } else {
          statusAlert.className = "status-alert error";
          statusAlert.innerText = `❌ Error: ${data.message || "No se pudo conectar con Tessie."}`;
          if (connBadge) {
            connBadge.className = "badge warning";
            connBadge.innerText = "Error Token";
          }
        }
      } catch (err) {
        statusAlert.className = "status-alert error";
        statusAlert.innerText = `❌ Error de red: ${err.message}`;
      }
    });
  }

  // Full Sync
  if (syncBtn) {
    syncBtn.addEventListener("click", async () => {
      const token = tokenInput.value.trim();
      const vin = vinSelect ? vinSelect.value : "";
      const syncDrives = document.getElementById("sync-opt-drives")?.checked ?? true;
      const syncCharges = document.getElementById("sync-opt-charges")?.checked ?? true;
      const syncBattery = document.getElementById("sync-opt-battery")?.checked ?? true;
      const saveToken = document.getElementById("sync-opt-save-token")?.checked ?? true;

      statusAlert.style.display = "block";
      statusAlert.className = "status-alert";
      statusAlert.innerText = "⏳ Sincronizando datos desde Tessie Cloud API... Por favor espera unos segundos.";

      try {
        const res = await fetch("/api/sync/tessie", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            token, vin, sync_drives: syncDrives, sync_charges: syncCharges,
            sync_battery: syncBattery, save_token: saveToken
          })
        });
        const result = await res.json();

        if (res.ok && result.status === "success") {
          statusAlert.className = "status-alert success";
          statusAlert.innerText = `🎉 ¡Sincronización completada! ${result.message}`;
          loadAllData();
        } else {
          statusAlert.className = "status-alert error";
          statusAlert.innerText = `❌ Error al sincronizar: ${result.message || "Error desconocido"}`;
        }
      } catch (err) {
        statusAlert.className = "status-alert error";
        statusAlert.innerText = `❌ Error de red: ${err.message}`;
      }
    });
  }

  // Seed Demo Tab
  if (seedTabBtn) seedTabBtn.addEventListener("click", handleSeedDemo);

  // Clear DB Tab
  if (clearDbBtn) {
    clearDbBtn.addEventListener("click", async () => {
      if (!confirm("¿Seguro que deseas vaciar todos los viajes, cargas y métricas guardadas en tu base de datos local?")) return;
      try {
        const res = await fetch("/api/data/clear", { method: "POST" });
        if (res.ok) {
          if (dbActionStatus) {
            dbActionStatus.style.display = "block";
            dbActionStatus.className = "status-alert success";
            dbActionStatus.innerText = "Base de datos local vaciada con éxito.";
          }
          loadAllData();
        }
      } catch (e) {
        alert("Error al vaciar base de datos");
      }
    });
  }
}

async function handleSeedDemo() {
  try {
    const res = await fetch("/api/demo/seed", { method: "POST" });
    const data = await res.json();
    if (res.ok) {
      alert(`🌱 ¡Datos de demostración cargados con éxito! (${data.seeded.drives} viajes, ${data.seeded.charges} cargas y degradación de batería).`);
      switchTab("overview");
      loadAllData();
    } else {
      alert("Error al cargar datos de demo: " + (data.error || ""));
    }
  } catch (err) {
    alert("Error de red al cargar demo: " + err.message);
  }
}

// Importer Drag & Drop
function initImporter() {
  const dropZone = document.getElementById("drop-zone");
  const fileInput = document.getElementById("file-input");
  const browseBtn = document.getElementById("btn-browse");
  const statusAlert = document.getElementById("import-status");

  if (!browseBtn || !fileInput || !dropZone) return;

  browseBtn.addEventListener("click", () => fileInput.click());

  fileInput.addEventListener("change", (e) => {
    if (e.target.files.length > 0) {
      handleFiles(Array.from(e.target.files));
    }
  });

  dropZone.addEventListener("dragover", (e) => {
    e.preventDefault();
    dropZone.classList.add("dragover");
  });

  dropZone.addEventListener("dragleave", () => {
    dropZone.classList.remove("dragover");
  });

  dropZone.addEventListener("drop", (e) => {
    e.preventDefault();
    dropZone.classList.remove("dragover");
    if (e.dataTransfer.files.length > 0) {
      handleFiles(Array.from(e.dataTransfer.files));
    }
  });

  async function handleFiles(files) {
    statusAlert.style.display = "block";
    statusAlert.className = "status-alert";
    statusAlert.innerText = `Subiendo y procesando ${files.length} archivo(s)...`;

    let totalImported = 0;
    let errors = [];

    for (const file of files) {
      const formData = new FormData();
      formData.append("file", file);

      try {
        const res = await fetch("/api/import", {
          method: "POST",
          body: formData
        });
        const result = await res.json();
        if (res.ok) {
          totalImported += (result.records_imported || 0);
        } else {
          errors.push(`${file.name}: ${result.detail || result.error || "Error desconocido"}`);
        }
      } catch (err) {
        errors.push(`${file.name}: Error de red`);
      }
    }

    if (errors.length === 0) {
      if (totalImported > 0) {
        statusAlert.className = "status-alert success";
        statusAlert.innerText = `🎉 ¡Éxito! Se han importado correctamente ${totalImported} registros históricos.`;
      } else {
        statusAlert.className = "status-alert warning";
        statusAlert.innerText = `⚠️ No se encontraron nuevos registros en el archivo subido (0 registros procesados). Asegúrate de subir una exportación de Tessie (.json o .csv) o TeslaFi (.csv).`;
      }
      loadAllData();
    } else {
      statusAlert.className = "status-alert error";
      statusAlert.innerText = `Importación parcial: ${totalImported} registros importados. Errores: ${errors.join("; ")}`;
      loadAllData();
    }
  }
}

function formatDate(isoStr) {
  if (!isoStr) return "--";
  try {
    const langMap = {
      es: "es-ES", en: "en-US", de: "de-DE", fr: "fr-FR", it: "it-IT", "zh-tw": "zh-TW"
    };
    const currentLang = window.i18n ? window.i18n.getLang() : "es";
    const locale = langMap[currentLang] || "es-ES";
    const d = new Date(isoStr);
    return d.toLocaleDateString(locale, {
      year: "numeric", month: "short", day: "numeric",
      hour: "2-digit", minute: "2-digit"
    });
  } catch (e) {
    return isoStr;
  }
}

// ========================================================
// LIVE VEHICLE & INTERIOR DIGITAL TWIN ENGINE
// ========================================================

let liveVehicleState = null;
let liveRefreshTimer = null;

function initLiveVehicle() {
  // Manual refresh button
  const btnRefresh = document.getElementById("btn-live-manual-refresh");
  if (btnRefresh) {
    btnRefresh.addEventListener("click", () => loadLiveVehicle());
  }

  // Auto-refresh interval (every 3 seconds when tab is active and checkbox is checked)
  if (liveRefreshTimer) clearInterval(liveRefreshTimer);
  liveRefreshTimer = setInterval(() => {
    const isLiveActive = document.querySelector(".tab-btn.active")?.getAttribute("data-tab") === "live";
    const isAutoCheck = document.getElementById("chk-live-refresh")?.checked;
    if (isLiveActive && isAutoCheck) {
      loadLiveVehicle(false); // silent refresh
    }
  }, 3000);

  // Seat heating buttons (interactive cycling: 0 -> 1 -> 2 -> 3 -> 0)
  const seatButtons = [
    { id: "seat-fl", key: "seat_heater_left" },
    { id: "seat-fr", key: "seat_heater_right" },
    { id: "seat-rl", key: "seat_heater_rear_left" },
    { id: "seat-rc", key: "seat_heater_rear_center" },
    { id: "seat-rr", key: "seat_heater_rear_right" }
  ];

  seatButtons.forEach(({ id, key }) => {
    const btn = document.getElementById(id);
    if (btn) {
      btn.addEventListener("click", () => {
        if (!liveVehicleState) return;
        const currentLevel = liveVehicleState.climate_state?.[key] || 0;
        const nextLevel = (currentLevel + 1) % 4;
        updateLiveVehicleState({ climate_state: { [key]: nextLevel } });
      });
    }
  });

  // Steering wheel heater button
  const btnSteering = document.getElementById("btn-steering-heat");
  if (btnSteering) {
    btnSteering.addEventListener("click", () => {
      if (!liveVehicleState) return;
      const current = !!liveVehicleState.climate_state?.steering_wheel_heater;
      updateLiveVehicleState({ climate_state: { steering_wheel_heater: !current } });
    });
  }

  // Panoramic Cockpit - Steering Wheel Heat
  const btnPanSteering = document.getElementById("btn-pan-wheel-heat");
  if (btnPanSteering) {
    btnPanSteering.addEventListener("click", () => {
      if (!liveVehicleState) return;
      const current = !!liveVehicleState.climate_state?.steering_wheel_heater;
      updateLiveVehicleState({ climate_state: { steering_wheel_heater: !current } });
    });
  }

  // Panoramic Cockpit - Steering Wheel Horn & Airbag (Audio & Visual)
  const hornBtn = document.getElementById("wheel-horn-btn");
  if (hornBtn) {
    hornBtn.addEventListener("click", () => {
      hornBtn.classList.add("horn-active");
      playTeslaHornSound();
      setTimeout(() => hornBtn.classList.remove("horn-active"), 350);
    });
  }

  // Dual-Zone Temp Setpoints (Main Dashboard & Screen [C])
  const btnTempDriverDown = document.getElementById("btn-temp-driver-down");
  const btnTempDriverUp = document.getElementById("btn-temp-driver-up");
  const btnTempPassDown = document.getElementById("btn-temp-pass-down");
  const btnTempPassUp = document.getElementById("btn-temp-pass-up");

  const scrTempDrDown = document.getElementById("scr-temp-dr-down");
  const scrTempDrUp = document.getElementById("scr-temp-dr-up");
  const scrTempPsDown = document.getElementById("scr-temp-ps-down");
  const scrTempPsUp = document.getElementById("scr-temp-ps-up");

  const adjustTemp = (zone, delta) => {
    if (!liveVehicleState) return;
    const key = zone === "driver" ? "driver_temp_setting" : "passenger_temp_setting";
    const cur = liveVehicleState.climate_state?.[key] || (zone === "driver" ? 21.0 : 21.5);
    const next = Math.max(16.0, Math.min(28.0, Math.round((cur + delta) * 10) / 10));
    updateLiveVehicleState({ climate_state: { [key]: next } });
  };

  if (btnTempDriverDown) btnTempDriverDown.addEventListener("click", () => adjustTemp("driver", -0.5));
  if (btnTempDriverUp) btnTempDriverUp.addEventListener("click", () => adjustTemp("driver", 0.5));
  if (btnTempPassDown) btnTempPassDown.addEventListener("click", () => adjustTemp("passenger", -0.5));
  if (btnTempPassUp) btnTempPassUp.addEventListener("click", () => adjustTemp("passenger", 0.5));

  if (scrTempDrDown) scrTempDrDown.addEventListener("click", () => adjustTemp("driver", -0.5));
  if (scrTempDrUp) scrTempDrUp.addEventListener("click", () => adjustTemp("driver", 0.5));
  if (scrTempPsDown) scrTempPsDown.addEventListener("click", () => adjustTemp("passenger", -0.5));
  if (scrTempPsUp) scrTempPsUp.addEventListener("click", () => adjustTemp("passenger", 0.5));

  // Screen [C] Quick Seat Heaters
  const scrSeatFl = document.getElementById("scr-btn-seat-fl");
  const scrSeatFr = document.getElementById("scr-btn-seat-fr");
  if (scrSeatFl) {
    scrSeatFl.addEventListener("click", () => {
      if (!liveVehicleState) return;
      const cur = liveVehicleState.climate_state?.seat_heater_left || 0;
      updateLiveVehicleState({ climate_state: { seat_heater_left: (cur + 1) % 4 } });
    });
  }
  if (scrSeatFr) {
    scrSeatFr.addEventListener("click", () => {
      if (!liveVehicleState) return;
      const cur = liveVehicleState.climate_state?.seat_heater_right || 0;
      updateLiveVehicleState({ climate_state: { seat_heater_right: (cur + 1) % 4 } });
    });
  }

  // Passenger Glovebox Electronic Release
  const btnGlovebox = document.getElementById("btn-open-glovebox");
  let gloveboxOpen = false;
  if (btnGlovebox) {
    btnGlovebox.addEventListener("click", () => {
      gloveboxOpen = !gloveboxOpen;
      const txt = document.getElementById("txt-glovebox");
      if (txt) txt.innerText = gloveboxOpen ? "[Abierta 🔓]" : "[Cerrar]";
      btnGlovebox.classList.toggle("btn-active", gloveboxOpen);
    });
  }

  // Screen [D] Barra Infantil Button
  const btnKids = document.getElementById("btn-dock-kids");
  let kidsModeActive = false;
  if (btnKids) {
    btnKids.addEventListener("click", () => {
      kidsModeActive = !kidsModeActive;
      btnKids.classList.toggle("active", kidsModeActive);
      btnKids.style.color = kidsModeActive ? "#38bdf8" : "";
    });
  }

  // Fan speed buttons
  const fanButtons = document.querySelectorAll(".fan-spd-btn");
  fanButtons.forEach(btn => {
    btn.addEventListener("click", () => {
      const spd = parseInt(btn.getAttribute("data-spd") || "0", 10);
      updateLiveVehicleState({ climate_state: { fan_status: spd, is_climate_on: spd > 0 } });
    });
  });

  // Climate On/Off Toggle
  const btnClimate = document.getElementById("btn-toggle-climate");
  if (btnClimate) {
    btnClimate.addEventListener("click", () => {
      if (!liveVehicleState) return;
      const cur = !!liveVehicleState.climate_state?.is_climate_on;
      updateLiveVehicleState({ climate_state: { is_climate_on: !cur, fan_status: !cur ? 3 : 0 } });
    });
  }

  // Keeper Mode buttons
  const keeperButtons = document.querySelectorAll(".keeper-btn");
  keeperButtons.forEach(btn => {
    btn.addEventListener("click", () => {
      const mode = btn.getAttribute("data-mode") || "off";
      updateLiveVehicleState({ climate_state: { climate_keeper_mode: mode } });
    });
  });

  // Lock Toggle
  const btnLock = document.getElementById("btn-toggle-lock");
  if (btnLock) {
    btnLock.addEventListener("click", () => {
      if (!liveVehicleState) return;
      const isLocked = !!liveVehicleState.vehicle_state?.locked;
      updateLiveVehicleState({ vehicle_state: { locked: !isLocked } });
    });
  }

  // Sentry Toggle
  const btnSentry = document.getElementById("btn-toggle-sentry");
  if (btnSentry) {
    btnSentry.addEventListener("click", () => {
      if (!liveVehicleState) return;
      const isSentry = !!liveVehicleState.vehicle_state?.sentry_mode;
      updateLiveVehicleState({ vehicle_state: { sentry_mode: !isSentry } });
    });
  }

  // Closures toggles (Frunk, Trunk, Doors, Charge Port)
  const closureButtons = [
    { id: "btn-toggle-frunk", key: "ft" },
    { id: "btn-toggle-trunk", key: "rt" },
    { id: "btn-toggle-df", key: "df" },
    { id: "btn-toggle-pf", key: "pf" },
    { id: "btn-toggle-dr", key: "dr" },
    { id: "btn-toggle-pr", key: "pr" },
  ];

  closureButtons.forEach(({ id, key }) => {
    const btn = document.getElementById(id);
    if (btn) {
      btn.addEventListener("click", () => {
        if (!liveVehicleState) return;
        const curVal = liveVehicleState.vehicle_state?.[key] || 0;
        updateLiveVehicleState({ vehicle_state: { [key]: curVal > 0 ? 0 : 1 } });
      });
    }
  });

  const btnPort = document.getElementById("btn-toggle-charge-port");
  if (btnPort) {
    btnPort.addEventListener("click", () => {
      if (!liveVehicleState) return;
      const cur = !!liveVehicleState.charge_state?.charge_port_door_open;
      updateLiveVehicleState({ charge_state: { charge_port_door_open: !cur } });
    });
  }

  // Windows vent / close
  const btnVent = document.getElementById("btn-vent-windows");
  const btnCloseWin = document.getElementById("btn-close-windows");
  if (btnVent) {
    btnVent.addEventListener("click", () => {
      updateLiveVehicleState({ vehicle_state: { fd_window: 1, fp_window: 1, rd_window: 1, rp_window: 1 } });
    });
  }
  if (btnCloseWin) {
    btnCloseWin.addEventListener("click", () => {
      updateLiveVehicleState({ vehicle_state: { fd_window: 0, fp_window: 0, rd_window: 0, rp_window: 0 } });
    });
  }

  // Simulator buttons
  const simButtons = document.querySelectorAll(".sim-btn");
  simButtons.forEach(btn => {
    btn.addEventListener("click", () => {
      const simType = btn.getAttribute("data-sim");
      handleSimulation(simType);
    });
  });
}

async function loadLiveVehicle(showLoading = true) {
  try {
    const currentVin = document.getElementById("current-vin")?.innerText?.trim();
    const queryVin = (currentVin && !currentVin.includes("Tesla")) ? `?vin=${encodeURIComponent(currentVin)}` : "";
    const res = await fetch(`/api/live/state${queryVin}`);
    if (!res.ok) return;
    const data = await res.json();
    liveVehicleState = data;
    renderLiveVehicle(data);
  } catch (err) {
    console.warn("Error loading live vehicle state:", err);
  }
}

async function updateLiveVehicleState(partialState) {
  try {
    const currentVin = liveVehicleState?.vin || "5YJ3E7EB8NF123456";
    const payload = Object.assign({ vin: currentVin }, partialState);
    const res = await fetch("/api/live/state", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    if (res.ok) {
      const updated = await res.json();
      if (updated.state) {
        liveVehicleState = updated.state;
        renderLiveVehicle(liveVehicleState);
      }
    }
  } catch (err) {
    console.error("Error updating live vehicle state:", err);
  }
}

function handleSimulation(type) {
  if (!liveVehicleState) return;
  if (type === "drive") {
    updateLiveVehicleState({
      drive_state: {
        shift_state: "D",
        speed: 115,
        power: 24,
        heading: 195,
        active_route_destination: "A-6 km 28, Las Rozas de Madrid",
        active_route_traffic_minutes_delay: 2.0
      },
      charge_state: {
        charging_state: "Disconnected",
        charger_power: 0,
        charger_voltage: 0,
        charger_actual_current: 0
      },
      vehicle_state: {
        locked: true,
        is_user_present: true
      },
      climate_state: {
        is_climate_on: true,
        fan_status: 4,
        driver_temp_setting: 20.5
      }
    });
  } else if (type === "supercharge") {
    updateLiveVehicleState({
      drive_state: {
        shift_state: "P",
        speed: 0,
        power: 0
      },
      charge_state: {
        charging_state: "Charging",
        charger_power: 150,
        charger_voltage: 410,
        charger_actual_current: 365,
        charge_port_door_open: true,
        charge_port_latch: "Engaged",
        conn_charge_cable: "CCS Combo 2",
        battery_heater_on: true,
        fast_charger_present: true
      },
      vehicle_state: {
        locked: false
      }
    });
  } else if (type === "park") {
    updateLiveVehicleState({
      drive_state: {
        shift_state: "P",
        speed: 0,
        power: 0
      },
      charge_state: {
        charging_state: "Disconnected",
        charger_power: 0,
        charger_voltage: 0,
        charger_actual_current: 0,
        charge_port_door_open: false,
        charge_port_latch: "Disengaged"
      },
      vehicle_state: {
        locked: true,
        sentry_mode: true,
        df: 0, pf: 0, dr: 0, pr: 0, ft: 0, rt: 0
      }
    });
  } else if (type === "preheat") {
    updateLiveVehicleState({
      climate_state: {
        is_climate_on: true,
        fan_status: 6,
        driver_temp_setting: 22.0,
        passenger_temp_setting: 22.0,
        seat_heater_left: 3,
        seat_heater_right: 3,
        steering_wheel_heater: true,
        defrost_mode: 1
      }
    });
  }
}

function renderLiveVehicle(state) {
  if (!state) return;

  const charge = state.charge_state || {};
  const climate = state.climate_state || {};
  const drive = state.drive_state || {};
  const vehicle = state.vehicle_state || {};
  const fleet = state.fleet_telemetry || {};

  // Header info
  const carName = document.getElementById("live-car-name");
  if (carName) carName.innerText = state.display_name || "Tesla Model 3 / Y Long Range";

  const vinBadge = document.getElementById("live-vin-badge");
  if (vinBadge) vinBadge.innerText = state.vin || "5YJ3E7EB8NF123456";

  const fwBadge = document.getElementById("live-fw-badge");
  if (fwBadge) fwBadge.innerText = `v${vehicle.car_version || "2024.26.8"}`;

  const tsSpan = document.getElementById("live-timestamp");
  if (tsSpan) tsSpan.innerText = formatDate(state.timestamp);

  const odoSpan = document.getElementById("live-odo-km");
  if (odoSpan) odoSpan.innerText = `${(vehicle.odometer || 32750).toLocaleString()} km`;

  // PRND Transmission
  const currentGear = (drive.shift_state || "P").toUpperCase();
  ["p", "r", "n", "d"].forEach(g => {
    const el = document.getElementById(`prnd-${g}`);
    if (el) {
      if (g.toUpperCase() === currentGear) {
        el.classList.add("active");
      } else {
        el.classList.remove("active");
      }
    }
  });

  // Lock status
  const iconLock = document.getElementById("icon-lock");
  const txtLock = document.getElementById("txt-lock");
  if (iconLock && txtLock) {
    if (vehicle.locked) {
      iconLock.innerText = "🔒";
      txtLock.innerText = "Bloqueado";
    } else {
      iconLock.innerText = "🔓";
      txtLock.innerText = "Desbloqueado";
    }
  }

  // Sentry status
  const iconSentry = document.getElementById("icon-sentry");
  const txtSentry = document.getElementById("txt-sentry");
  if (iconSentry && txtSentry) {
    if (vehicle.sentry_mode) {
      iconSentry.innerText = "👁️";
      txtSentry.innerText = "Centinela ON";
    } else {
      iconSentry.innerText = "😴";
      txtSentry.innerText = "Centinela OFF";
    }
  }

  // User presence
  const badgeUser = document.getElementById("badge-user-present");
  if (badgeUser) {
    if (vehicle.is_user_present) {
      badgeUser.innerText = "👤 Conductor a bordo";
      badgeUser.className = "badge badge-presence";
    } else {
      badgeUser.innerText = "🅿️ Vehículo desocupado";
      badgeUser.className = "badge info";
    }
  }

  // Cockpit Seats & Heat
  const renderSeat = (btnId, level) => {
    const btn = document.getElementById(btnId);
    if (btn) {
      btn.className = `seat-btn heat-${level || 0}`;
    }
  };
  renderSeat("seat-fl", climate.seat_heater_left);
  renderSeat("seat-fr", climate.seat_heater_right);
  renderSeat("seat-rl", climate.seat_heater_rear_left);
  renderSeat("seat-rc", climate.seat_heater_rear_center);
  renderSeat("seat-rr", climate.seat_heater_rear_right);

  // Steering wheel
  const btnSteering = document.getElementById("btn-steering-heat");
  if (btnSteering) {
    if (climate.steering_wheel_heater) {
      btnSteering.classList.add("active");
    } else {
      btnSteering.classList.remove("active");
    }
  }

  // Mini Touchscreen
  const tsGear = document.getElementById("ts-gear");
  if (tsGear) tsGear.innerText = currentGear;
  const tsSpeed = document.getElementById("ts-speed");
  if (tsSpeed) tsSpeed.innerText = `${drive.speed || 0} km/h`;
  const tsSoc = document.getElementById("ts-soc");
  if (tsSoc) tsSoc.innerText = `${charge.battery_level || 78}%`;
  const tsNav = document.getElementById("ts-nav-dest");
  if (tsNav) tsNav.innerText = drive.active_route_destination || "P. Castellana 200";
  const tsTempDriver = document.getElementById("ts-temp-driver");
  if (tsTempDriver) tsTempDriver.innerText = `${(climate.driver_temp_setting || 21).toFixed(1)}°`;
  const tsTempPass = document.getElementById("ts-temp-pass");
  if (tsTempPass) tsTempPass.innerText = `${(climate.passenger_temp_setting || 21.5).toFixed(1)}°`;
  const tsFanSpd = document.getElementById("ts-fan-spd");
  if (tsFanSpd) tsFanSpd.innerText = climate.fan_status || 0;

  // Climate Setpoints & Readings
  const dispDriver = document.getElementById("disp-temp-driver");
  if (dispDriver) dispDriver.innerText = `${(climate.driver_temp_setting || 21.0).toFixed(1)}°C`;
  const dispPass = document.getElementById("disp-temp-pass");
  if (dispPass) dispPass.innerText = `${(climate.passenger_temp_setting || 21.5).toFixed(1)}°C`;

  const cabinIn = document.getElementById("live-temp-inside");
  if (cabinIn) cabinIn.innerText = `${(climate.inside_temp || 21.5).toFixed(1)}°C`;
  const cabinOut = document.getElementById("live-temp-outside");
  if (cabinOut) cabinOut.innerText = `${(climate.outside_temp || 17.0).toFixed(1)}°C`;

  const fanLabel = document.getElementById("live-fan-label");
  if (fanLabel) fanLabel.innerText = `Nivel ${climate.fan_status || 0} / 7`;

  // Airflow Animation
  const airflow = document.getElementById("airflow-animation");
  if (airflow) {
    if (climate.is_climate_on && (climate.fan_status || 0) > 0) {
      airflow.style.display = "flex";
    } else {
      airflow.style.display = "none";
    }
  }

  // Fan speed buttons highlight
  document.querySelectorAll(".fan-spd-btn").forEach(btn => {
    const spd = parseInt(btn.getAttribute("data-spd") || "0", 10);
    if (spd === (climate.fan_status || 0)) {
      btn.classList.add("active");
    } else {
      btn.classList.remove("active");
    }
  });

  const txtClimate = document.getElementById("txt-climate-state");
  const badgeClimate = document.getElementById("badge-climate-power");
  if (txtClimate && badgeClimate) {
    if (climate.is_climate_on) {
      txtClimate.innerText = "Encendido";
      badgeClimate.innerText = "A/C ON";
      badgeClimate.className = "badge success";
    } else {
      txtClimate.innerText = "Apagado";
      badgeClimate.innerText = "A/C OFF";
      badgeClimate.className = "badge";
    }
  }

  // Keeper Mode buttons
  const activeMode = (climate.climate_keeper_mode || "off").toLowerCase();
  document.querySelectorAll(".keeper-btn").forEach(btn => {
    const mode = btn.getAttribute("data-mode") || "off";
    if (mode === activeMode) {
      btn.classList.add("active");
    } else {
      btn.classList.remove("active");
    }
  });
  const badgeKeeper = document.getElementById("badge-keeper-mode");
  if (badgeKeeper) {
    const modeLabels = { off: "Modo: Normal", keep: "Modo: Mantener", dog: "Modo: Perro 🐶", camp: "Modo: Acampada ⛺" };
    badgeKeeper.innerText = modeLabels[activeMode] || "Modo: Normal";
  }

  // Chassis Closures (Frunk, Trunk, Doors)
  const renderClosure = (btnId, badgeId, isOpen, labelClosed, labelOpen) => {
    const btn = document.getElementById(btnId);
    const badge = document.getElementById(badgeId);
    if (btn && badge) {
      if (isOpen) {
        btn.classList.add("open");
        badge.innerText = labelOpen || "Abierto";
      } else {
        btn.classList.remove("open");
        badge.innerText = labelClosed || "Cerrado";
      }
    }
  };
  renderClosure("btn-toggle-frunk", "badge-frunk", (vehicle.ft || 0) > 0, "Cerrado", "Abierto");
  renderClosure("btn-toggle-trunk", "badge-trunk", (vehicle.rt || 0) > 0, "Cerrado", "Abierto");
  renderClosure("btn-toggle-df", "badge-df", (vehicle.df || 0) > 0, "Cerrada", "Abierta");
  renderClosure("btn-toggle-pf", "badge-pf", (vehicle.pf || 0) > 0, "Cerrada", "Abierta");
  renderClosure("btn-toggle-dr", "badge-dr", (vehicle.dr || 0) > 0, "Cerrada", "Abierta");
  renderClosure("btn-toggle-pr", "badge-pr", (vehicle.pr || 0) > 0, "Cerrada", "Abierta");
  renderClosure("btn-toggle-charge-port", "badge-charge-port", charge.charge_port_door_open, "Cerrado", "Abierto");

  // TPMS Pressures
  const setTpms = (valId, barVal) => {
    const el = document.getElementById(valId);
    if (el && barVal !== undefined && barVal !== null) {
      el.innerText = `${Number(barVal).toFixed(1)} Bar`;
    }
  };
  setTpms("tpms-fl-val", vehicle.tpms_pressure_fl || 2.9);
  setTpms("tpms-fr-val", vehicle.tpms_pressure_fr || 2.9);
  setTpms("tpms-rl-val", vehicle.tpms_pressure_rl || 2.8);
  setTpms("tpms-rr-val", vehicle.tpms_pressure_rr || 2.8);

  // BMS & High-Voltage Battery
  const bmsSoc = document.getElementById("live-bms-soc");
  if (bmsSoc) bmsSoc.innerText = `${charge.battery_level || 78}%`;
  const usableSoc = document.getElementById("live-usable-soc");
  if (usableSoc) usableSoc.innerText = `${charge.usable_battery_level || 77}%`;
  const chargeLimit = document.getElementById("live-charge-limit");
  if (chargeLimit) chargeLimit.innerText = `${charge.charge_limit_soc || 80}%`;
  const bmsRange = document.getElementById("live-bms-range");
  if (bmsRange) bmsRange.innerText = `${(charge.battery_range || 395.2).toFixed(1)} km`;

  const socBar = document.getElementById("live-soc-bar");
  if (socBar) socBar.style.width = `${charge.battery_level || 78}%`;
  const limitMarker = document.getElementById("live-limit-marker");
  if (limitMarker) limitMarker.style.left = `${charge.charge_limit_soc || 80}%`;

  const chgBadge = document.getElementById("live-charge-state-badge");
  if (chgBadge) {
    chgBadge.innerText = charge.charging_state || "Standby";
    if (charge.charging_state === "Charging") {
      chgBadge.className = "badge warning";
    } else {
      chgBadge.className = "badge success";
    }
  }

  const vEl = document.getElementById("live-charger-voltage");
  if (vEl) vEl.innerText = `${charge.charger_voltage || 0} V`;
  const aEl = document.getElementById("live-charger-current");
  if (aEl) aEl.innerText = `${charge.charger_actual_current || 0} A`;
  const pEl = document.getElementById("live-charger-power");
  if (pEl) pEl.innerText = `${charge.charger_power || 0} kW`;
  const eEl = document.getElementById("live-energy-added");
  if (eEl) eEl.innerText = `${(charge.charge_energy_added || 18.5).toFixed(1)} kWh`;
  const tEl = document.getElementById("live-time-to-full");
  if (tEl) {
    const mins = Math.round((charge.time_to_full_charge || 0) * 60);
    tEl.innerText = mins > 0 ? `${mins} min` : "Completo";
  }
  const hEl = document.getElementById("live-battery-heater");
  if (hEl) hEl.innerText = charge.battery_heater_on ? "🔥 Precalentando" : "Inactivo";

  // Dynamics & Route
  const dynSpeed = document.getElementById("live-dyn-speed");
  if (dynSpeed) dynSpeed.innerHTML = `${drive.speed || 0} <small>km/h</small>`;
  const dynPower = document.getElementById("live-dyn-power");
  if (dynPower) {
    const kw = drive.power || 0;
    dynPower.innerText = `${kw > 0 ? "+" : ""}${kw.toFixed(1)} kW`;
  }
  const compassNeedle = document.getElementById("compass-needle");
  if (compassNeedle) {
    compassNeedle.style.transform = `rotate(${drive.heading || 0}deg)`;
  }
  const dynHeading = document.getElementById("live-dyn-heading");
  if (dynHeading) dynHeading.innerText = `${drive.heading || 0}°`;

  const routeDest = document.getElementById("live-route-dest");
  if (routeDest) routeDest.innerText = drive.active_route_destination || "Sin destino activo";
  const routeSoc = document.getElementById("live-route-arrival-soc");
  if (routeSoc) routeSoc.innerText = `${drive.active_route_energy_at_arrival || 64}%`;
  const routeTraffic = document.getElementById("live-route-traffic");
  if (routeTraffic) routeTraffic.innerText = `+${(drive.active_route_traffic_minutes_delay || 0).toFixed(1)} min`;

  const gpsCoords = document.getElementById("live-gps-coords");
  const mapLink = document.getElementById("live-map-link");
  if (gpsCoords && drive.latitude && drive.longitude) {
    const lat = Number(drive.latitude).toFixed(6);
    const lon = Number(drive.longitude).toFixed(6);
    gpsCoords.innerText = `${lat}, ${lon}`;
    if (mapLink) {
      mapLink.href = `https://www.openstreetmap.org/?mlat=${lat}&mlon=${lon}#map=16/${lat}/${lon}`;
    }
  }

  // Fleet & Cell Diagnostics
  const cellDelta = document.getElementById("live-cell-delta");
  if (cellDelta) cellDelta.innerText = `${(fleet.cell_delta_mv || 4.0).toFixed(1)} mV`;
  const cellV = document.getElementById("live-cell-voltages");
  if (cellV) cellV.innerText = `${fleet.brick_voltage_max || 4.152} V / ${fleet.brick_voltage_min || 4.148} V`;
  const invT = document.getElementById("live-inverter-temps");
  if (invT) invT.innerText = `TR: ${fleet.di_inverter_tr || 34.2}°C / TF: ${fleet.di_inverter_tf || 31.8}°C`;
  const brakeP = document.getElementById("live-brake-pedal");
  if (brakeP) brakeP.innerText = `${(fleet.brake_pedal_pos || 0).toFixed(1)}%`;
  const acE = document.getElementById("live-ac-energy");
  if (acE) acE.innerText = `${(fleet.ac_charging_energy_in || 1450.4).toLocaleString()} kWh`;
  const dcE = document.getElementById("live-dc-energy");
  if (dcE) dcE.innerText = `${(fleet.dc_charging_energy_in || 420.8).toLocaleString()} kWh`;

  // ========================================================
  // Panoramic Tesla Cockpit View Rendering
  // ========================================================
  const panGear = document.getElementById("pan-hud-gear");
  if (panGear) panGear.innerText = currentGear;

  const panWheelGear = document.getElementById("pan-wheel-gear");
  if (panWheelGear) panWheelGear.innerText = currentGear;

  const panSpeed = document.getElementById("pan-hud-speed");
  if (panSpeed) panSpeed.innerText = drive.speed || 0;

  // Steering wheel heat state button
  const btnPanHeat = document.getElementById("btn-pan-wheel-heat");
  const txtPanHeat = document.getElementById("pan-wheel-heat-txt");
  if (btnPanHeat) {
    const isHeatOn = !!climate.steering_wheel_heater;
    btnPanHeat.classList.toggle("active", isHeatOn);
    if (txtPanHeat) txtPanHeat.innerText = isHeatOn ? "Volante Caliente" : "Volante Térmico";
  }

  // Cabin camera surveillance LED
  const cabinLed = document.getElementById("cabin-cam-led");
  if (cabinLed) {
    if (vehicle.is_user_present || vehicle.sentry_mode) {
      cabinLed.style.background = "var(--accent-emerald)";
      cabinLed.style.boxShadow = "0 0 8px var(--accent-emerald)";
    } else {
      cabinLed.style.background = "#64748b";
      cabinLed.style.boxShadow = "none";
    }
  }

  // Screen [B] Navigation & Route
  const panNavNext = document.getElementById("pan-nav-next");
  if (panNavNext) {
    panNavNext.innerText = drive.active_route_destination ? `En ruta hacia ${drive.active_route_destination}` : "A 350 m en Paseo de la Castellana";
  }
  const panNavDest = document.getElementById("pan-nav-dest-full");
  if (panNavDest) {
    panNavDest.innerText = drive.active_route_destination ? `Navegación GPS: ${drive.active_route_destination}` : "Navegación GPS: Standby";
  }
  const panNavArrivalSoc = document.getElementById("pan-nav-arrival-soc");
  if (panNavArrivalSoc) {
    panNavArrivalSoc.innerText = `${drive.active_route_energy_at_arrival || 64}%`;
  }
  const panNavDelay = document.getElementById("pan-nav-delay");
  if (panNavDelay) {
    panNavDelay.innerText = `+${(drive.active_route_traffic_minutes_delay || 0).toFixed(1)} min`;
  }

  // Screen [C] Climate Setpoints & Status
  const scrDispDr = document.getElementById("scr-disp-temp-dr");
  if (scrDispDr) scrDispDr.innerText = `${(climate.driver_temp_setting || 21.0).toFixed(1)}°`;
  const scrDispPs = document.getElementById("scr-disp-temp-ps");
  if (scrDispPs) scrDispPs.innerText = `${(climate.passenger_temp_setting || 21.5).toFixed(1)}°`;

  const scrFlameFl = document.getElementById("scr-flame-fl");
  if (scrFlameFl) {
    const lvl = climate.seat_heater_left || 0;
    scrFlameFl.innerText = lvl > 0 ? `🔥 Nivel ${lvl}` : "Desactivado";
  }
  const scrFlameFr = document.getElementById("scr-flame-fr");
  if (scrFlameFr) {
    const lvl = climate.seat_heater_right || 0;
    scrFlameFr.innerText = lvl > 0 ? `🔥 Nivel ${lvl}` : "Desactivado";
  }

  const scrClimateTxt = document.getElementById("scr-climate-mode-txt");
  if (scrClimateTxt) {
    const acStatus = climate.is_climate_on ? "Automático" : "Apagado";
    scrClimateTxt.innerText = `A/C ${acStatus} • Cabina: ${(climate.inside_temp || 21.5).toFixed(1)}°C • Exterior: ${(climate.outside_temp || 17.0).toFixed(1)}°C`;
  }

  // Continuous Ventilation Stream Animation & Passenger airflow
  const hvacStream = document.getElementById("pan-hvac-stream");
  if (hvacStream) {
    hvacStream.style.display = (climate.is_climate_on && (climate.fan_status || 0) > 0) ? "flex" : "none";
  }
  const passAirflow = document.getElementById("pass-airflow");
  if (passAirflow) {
    passAirflow.style.display = (climate.is_climate_on && (climate.fan_status || 0) > 0) ? "flex" : "none";
  }

  // Qi Wireless Charging Pad
  const phoneDr = document.getElementById("phone-driver-pct");
  const phonePs = document.getElementById("phone-pass-pct");
  if (phoneDr && !phoneDr.dataset.static) {
    phoneDr.innerText = `${Math.min(100, Math.round(75 + (charge.battery_level || 78) * 0.2))}%`;
  }
  if (phonePs && !phonePs.dataset.static) {
    phonePs.innerText = `${Math.min(100, Math.round(82 + (charge.battery_level || 78) * 0.15))}%`;
  }
}

// Zero-dependency Web Audio synthesizer for Tesla horn
function playTeslaHornSound() {
  try {
    const AudioCtx = window.AudioContext || window.webkitAudioContext;
    if (!AudioCtx) return;
    const ctx = new AudioCtx();
    const osc1 = ctx.createOscillator();
    const osc2 = ctx.createOscillator();
    const gain = ctx.createGain();

    osc1.type = "sawtooth";
    osc2.type = "sawtooth";
    osc1.frequency.setValueAtTime(420, ctx.currentTime);
    osc2.frequency.setValueAtTime(505, ctx.currentTime);

    gain.gain.setValueAtTime(0.12, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.35);

    osc1.connect(gain);
    osc2.connect(gain);
    gain.connect(ctx.destination);

    osc1.start();
    osc2.start();
    osc1.stop(ctx.currentTime + 0.35);
    osc2.stop(ctx.currentTime + 0.35);
  } catch (e) {
    // Audio autoplay or permissions handled gracefully
  }
}

