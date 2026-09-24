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

      // Map link & GPX/KML Exporters
      const gmapsDir = `https://www.google.com/maps/dir/?api=1&origin=${encodeURIComponent(startLoc)}&destination=${encodeURIComponent(endLoc)}`;
      const actionsHtml = `
        <div style="display:flex; gap:4px; align-items:center;">
          <a href="${gmapsDir}" target="_blank" class="map-link-btn" title="Abrir en Google Maps">🗺️ Mapa</a>
          <a href="/api/drives/export?id=${d.id}&format=gpx" class="btn btn-xs btn-outline export-btn" download>📥 GPX</a>
          <a href="/api/drives/export?id=${d.id}&format=kml" class="btn btn-xs btn-outline export-btn" download>📥 KML</a>
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
