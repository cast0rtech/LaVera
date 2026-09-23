/**
 * LaVera Hub - Frontend Application Logic
 */

document.addEventListener("DOMContentLoaded", () => {
  initTabs();
  initImporter();
  loadAllData();

  // Refresh every 10 seconds
  setInterval(loadStats, 10000);
});

// Tab Navigation
function initTabs() {
  const tabs = document.querySelectorAll(".tab-btn");
  tabs.forEach(btn => {
    btn.addEventListener("click", () => {
      tabs.forEach(t => t.classList.remove("active"));
      document.querySelectorAll(".tab-pane").forEach(p => p.classList.remove("active"));

      btn.classList.add("active");
      const targetId = `tab-${btn.dataset.tab}`;
      const targetPane = document.getElementById(targetId);
      if (targetPane) {
        targetPane.classList.add("active");
      }

      // Re-render chart on tab switch so size is calculated properly
      if (btn.dataset.tab === "overview") {
        setTimeout(loadStats, 50);
      }
    });
  });
}

// Data Fetching
async function loadAllData() {
  await Promise.all([
    loadStats(),
    loadDrives(),
    loadCharges(),
    loadBattery()
  ]);
}

async function loadStats() {
  try {
    const res = await fetch("/api/stats");
    if (!res.ok) return;
    const data = await res.json();

    // KPIs
    if (data.drives) {
      document.getElementById("kpi-distance").innerHTML = `${data.drives.total_distance_km.toLocaleString()} <span class="unit">km</span>`;
      document.getElementById("kpi-odometer").innerText = `Od?metro: ${data.drives.latest_odometer_km.toLocaleString()} km`;
      document.getElementById("kpi-efficiency").innerHTML = `${data.drives.avg_efficiency_wh_km} <span class="unit">Wh/km</span>`;
      document.getElementById("kpi-energy").innerText = `Consumo: ${data.drives.total_energy_kwh.toLocaleString()} kWh`;
    }

    if (data.charges) {
      document.getElementById("kpi-charged").innerHTML = `${data.charges.total_charged_kwh.toLocaleString()} <span class="unit">kWh</span>`;
      document.getElementById("kpi-charges-count").innerText = `${data.charges.total_count} sesiones ($${data.charges.total_cost})`;
    }

    if (data.battery) {
      const soh = (100 - (data.battery.degradation_pct || 0)).toFixed(1);
      document.getElementById("kpi-health").innerHTML = `${soh} <span class="unit">%</span>`;
      document.getElementById("kpi-degradation").innerText = `Degradaci?n: ${data.battery.degradation_pct}% (${data.battery.capacity_kwh} kWh)`;
    }

    // Gauge & Live Telemetry
    const liveSoc = data.live && data.live.soc !== null ? data.live.soc : 75;
    ChartMini.renderGauge("chart-gauge", liveSoc, 0, 100, { label: "State of Charge (SoC)", unit: "%" });

    document.getElementById("gauge-soc-text").innerText = `${liveSoc}%`;
    document.getElementById("gauge-temp-text").innerText = data.live && data.live.battery_temp_c ? `${data.live.battery_temp_c}?C` : "--?C";
    document.getElementById("gauge-power-text").innerText = data.live && data.live.power_kw ? `${data.live.power_kw} kW` : "0.0 kW";

  } catch (err) {
    console.error("Error loading stats:", err);
  }
}

async function loadDrives() {
  try {
    const res = await fetch("/api/drives?limit=50");
    if (!res.ok) return;
    const drives = await res.json();

    const tbody = document.querySelector("#table-drives tbody");
    const countBadge = document.getElementById("drives-count-badge");
    countBadge.innerText = `${drives.length} viajes mostrados`;

    if (drives.length === 0) {
      tbody.innerHTML = `<tr><td colspan="8" class="text-center">No hay registros de conducci?n. Importa datos de Tessie o TeslaFi.</td></tr>`;
      return;
    }

    tbody.innerHTML = drives.map(d => {
      const fromTo = (d.start_location || "Desconocido") + " ? " + (d.end_location || "Desconocido");
      const durationMin = Math.round((d.duration_s || 0) / 60);
      const socChange = `${d.start_soc}% ? ${d.end_soc}%`;
      return `
        <tr>
          <td>${formatDate(d.started_at)}</td>
          <td>${fromTo}</td>
          <td><strong>${d.distance_km} km</strong></td>
          <td>${durationMin} min</td>
          <td>${d.energy_kwh} kWh</td>
          <td>${d.efficiency_wh_km} Wh/km</td>
          <td>${socChange}</td>
          <td><span class="badge info">${d.provider.toUpperCase()}</span></td>
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

    const tbody = document.querySelector("#table-charges tbody");
    const countBadge = document.getElementById("charges-count-badge");
    countBadge.innerText = `${charges.length} cargas mostradas`;

    if (charges.length === 0) {
      tbody.innerHTML = `<tr><td colspan="8" class="text-center">No hay sesiones de carga registradas.</td></tr>`;
      return;
    }

    tbody.innerHTML = charges.map(c => {
      const socChange = `${c.start_soc}% ? ${c.end_soc}%`;
      const isFast = c.is_fast_charge ? '<span class="badge vehicle-badge">R?PIDA / SC</span>' : '<span class="badge">AC LENTA</span>';
      return `
        <tr>
          <td>${formatDate(c.started_at)}</td>
          <td>${c.location || "Punto de Carga"}</td>
          <td><strong>${c.energy_added_kwh} kWh</strong></td>
          <td>+${c.range_added_km} km</td>
          <td>${c.peak_kw ? c.peak_kw + " kW" : "--"}</td>
          <td>${socChange}</td>
          <td>${c.cost ? "$" + c.cost.toFixed(2) : "Gratis / --"}</td>
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
    const history = await res.json();

    const tbody = document.querySelector("#table-battery tbody");
    if (history.length === 0) {
      tbody.innerHTML = `<tr><td colspan="7" class="text-center">Sin m?tricas de bater?a cargadas.</td></tr>`;
      ChartMini.renderLineChart("chart-degradation", [], [], { unit: "kWh" });
      return;
    }

    // Chart rendering
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

// Importer Drag & Drop
function initImporter() {
  const dropZone = document.getElementById("drop-zone");
  const fileInput = document.getElementById("file-input");
  const browseBtn = document.getElementById("btn-browse");
  const statusAlert = document.getElementById("import-status");

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
          errors.push(`${file.name}: ${result.detail || "Error desconocido"}`);
        }
      } catch (err) {
        errors.push(`${file.name}: Error de red`);
      }
    }

    if (errors.length === 0) {
      statusAlert.className = "status-alert success";
      statusAlert.innerText = `??xito! Se han importado correctamente ${totalImported} registros hist?ricos.`;
      loadAllData();
    } else {
      statusAlert.className = "status-alert error";
      statusAlert.innerText = `Importaci?n parcial: ${totalImported} registros importados. Errores: ${errors.join("; ")}`;
      loadAllData();
    }
  }
}

function formatDate(isoStr) {
  if (!isoStr) return "--";
  try {
    const d = new Date(isoStr);
    return d.toLocaleDateString("es-ES", {
      year: "numeric", month: "short", day: "numeric",
      hour: "2-digit", minute: "2-digit"
    });
  } catch (e) {
    return isoStr;
  }
}
