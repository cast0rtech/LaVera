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

async function loadDrives() {
  try {
    const res = await fetch("/api/drives?limit=50");
    if (!res.ok) return;
    const drives = await res.json();

    const t = window.i18n ? window.i18n.t : (k => k);
    const tbody = document.querySelector("#table-drives tbody");
    const countBadge = document.getElementById("drives-count-badge");
    if (countBadge) countBadge.innerText = `${drives.length} ${t("drives_shown")}`;

    if (drives.length === 0) {
      tbody.innerHTML = `<tr><td colspan="9" class="text-center">${t("drives_empty")}</td></tr>`;
      return;
    }

    tbody.innerHTML = drives.map(d => {
      const fromTo = (d.start_location || "Desconocido") + " → " + (d.end_location || "Desconocido");
      const durationMin = Math.round((d.duration_s || 0) / 60);
      const socChange = `${d.start_soc}% → ${d.end_soc}%`;

      const apPct = d.autopilot_pct || 0;
      const apKm = d.autopilot_km || 0;
      const apBadge = (apPct > 0 || apKm > 0)
        ? `<span class="badge vehicle-badge">🤖 ${apPct > 0 ? apPct + '%' : ''} (${apKm} km)</span>`
        : `<span class="badge" style="opacity:0.6;">Manual</span>`;

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
          <td><span class="badge info">${(d.provider || "Auto").toUpperCase()}</span></td>
        </tr>
      `;
    }).join("");
  } catch (err) {
    console.error("Error loading drives:", err);
  }
}

async function loadCharges() {
  try {
    const res = await fetch("/api/charges?limit=50");
    if (!res.ok) return;
    const charges = await res.json();

    const t = window.i18n ? window.i18n.t : (k => k);
    const tbody = document.querySelector("#table-charges tbody");
    const countBadge = document.getElementById("charges-count-badge");
    if (countBadge) countBadge.innerText = `${charges.length} ${t("charges_shown")}`;

    if (charges.length === 0) {
      tbody.innerHTML = `<tr><td colspan="8" class="text-center">${t("charges_empty")}</td></tr>`;
      return;
    }

    tbody.innerHTML = charges.map(c => {
      const socChange = `${c.start_soc}% → ${c.end_soc}%`;
      const isFast = c.is_fast_charge ? `<span class="badge vehicle-badge">${t("fast_charge")}</span>` : `<span class="badge">${t("slow_charge")}</span>`;
      return `
        <tr>
          <td>${formatDate(c.started_at)}</td>
          <td>${c.location || "Punto de Carga"}</td>
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
          if (drivesData && drivesData.length > 0) {
            const origCap = 75.0; // kWh factory capacity
            history = drivesData.slice(0, 30).reverse().map(d => {
              const odo = d.end_odometer_km || d.start_odometer_km || 0;
              const degPct = Math.min(14.0, Math.max(0.8, Number(((odo / 195000) * 8.2).toFixed(1))));
              const currCap = Number((origCap * (1 - degPct / 100.0)).toFixed(1));
              const maxRange = Math.round(450 * (1 - degPct / 100.0));

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
      } catch (e) {}
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
