/**
 * LaVera ChartMini - Zero-dependency offline Canvas charting library
 */

const ChartMini = {
  renderLineChart(canvasId, labels, data, options = {}) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    
    // High-DPI scaling
    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();
    canvas.width = rect.width * dpr;
    canvas.height = rect.height * dpr;
    ctx.scale(dpr, dpr);

    const width = rect.width;
    const height = rect.height;
    ctx.clearRect(0, 0, width, height);

    if (!data || data.length === 0) {
      ctx.fillStyle = "#8e9bb2";
      ctx.font = "14px sans-serif";
      ctx.textAlign = "center";
      ctx.fillText("Sin datos registrados", width / 2, height / 2);
      return;
    }

    const padding = { top: 30, right: 30, bottom: 40, left: 50 };
    const chartW = width - padding.left - padding.right;
    const chartH = height - padding.top - padding.bottom;

    const minVal = options.min !== undefined ? options.min : Math.min(...data) * 0.95;
    const maxVal = options.max !== undefined ? options.max : Math.max(...data) * 1.05;
    const valRange = (maxVal - minVal) || 1;

    // Gridlines
    ctx.strokeStyle = "rgba(255, 255, 255, 0.05)";
    ctx.lineWidth = 1;
    const gridRows = 4;
    for (let i = 0; i <= gridRows; i++) {
      const y = padding.top + (chartH / gridRows) * i;
      ctx.beginPath();
      ctx.moveTo(padding.left, y);
      ctx.lineTo(width - padding.right, y);
      ctx.stroke();

      // Y-axis label
      const val = maxVal - (valRange / gridRows) * i;
      ctx.fillStyle = "#5c677d";
      ctx.font = "10px sans-serif";
      ctx.textAlign = "right";
      ctx.fillText(val.toFixed(1) + (options.unit ? " " + options.unit : ""), padding.left - 8, y + 3);
    }

    // Points calculation
    const points = data.map((val, idx) => {
      const x = padding.left + (idx / Math.max(data.length - 1, 1)) * chartW;
      const y = padding.top + chartH - ((val - minVal) / valRange) * chartH;
      return { x, y, val };
    });

    // Fill Gradient under line
    const gradient = ctx.createLinearGradient(0, padding.top, 0, height - padding.bottom);
    gradient.addColorStop(0, options.fillColor || "rgba(0, 210, 255, 0.25)");
    gradient.addColorStop(1, "rgba(0, 210, 255, 0.0)");

    ctx.beginPath();
    ctx.moveTo(points[0].x, points[0].y);
    for (let i = 1; i < points.length; i++) {
      ctx.lineTo(points[i].x, points[i].y);
    }
    ctx.lineTo(points[points.length - 1].x, height - padding.bottom);
    ctx.lineTo(points[0].x, height - padding.bottom);
    ctx.closePath();
    ctx.fillStyle = gradient;
    ctx.fill();

    // Draw Line
    ctx.beginPath();
    ctx.moveTo(points[0].x, points[0].y);
    for (let i = 1; i < points.length; i++) {
      ctx.lineTo(points[i].x, points[i].y);
    }
    ctx.strokeStyle = options.lineColor || "#00d2ff";
    ctx.lineWidth = 2.5;
    ctx.stroke();

    // Draw Circles for points if count is low
    if (points.length <= 40) {
      points.forEach(p => {
        ctx.beginPath();
        ctx.arc(p.x, p.y, 3, 0, Math.PI * 2);
        ctx.fillStyle = "#fff";
        ctx.fill();
        ctx.strokeStyle = options.lineColor || "#00d2ff";
        ctx.lineWidth = 2;
        ctx.stroke();
      });
    }

    // X-axis label samples
    if (labels && labels.length > 0) {
      ctx.fillStyle = "#5c677d";
      ctx.font = "10px sans-serif";
      ctx.textAlign = "center";
      const step = Math.ceil(labels.length / 5);
      for (let i = 0; i < labels.length; i += step) {
        const x = padding.left + (i / Math.max(labels.length - 1, 1)) * chartW;
        ctx.fillText(labels[i], x, height - padding.bottom + 18);
      }
    }
  },

  renderGauge(canvasId, value, min = 0, max = 100, options = {}) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    const ctx = canvas.getContext("2d");

    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();
    canvas.width = rect.width * dpr;
    canvas.height = rect.height * dpr;
    ctx.scale(dpr, dpr);

    const width = rect.width;
    const height = rect.height;
    ctx.clearRect(0, 0, width, height);

    const centerX = width / 2;
    const centerY = height * 0.7;
    const radius = Math.min(centerX, centerY) * 0.85;

    const startAngle = Math.PI * 0.8;
    const endAngle = Math.PI * 2.2;
    const totalAngle = endAngle - startAngle;

    // Track Background
    ctx.beginPath();
    ctx.arc(centerX, centerY, radius, startAngle, endAngle);
    ctx.strokeStyle = "rgba(255, 255, 255, 0.08)";
    ctx.lineWidth = 14;
    ctx.lineCap = "round";
    ctx.stroke();

    // Value Arc
    const valRatio = Math.max(0, Math.min(1, (value - min) / (max - min)));
    const currentAngle = startAngle + totalAngle * valRatio;

    const gradient = ctx.createLinearGradient(0, centerY, width, centerY);
    gradient.addColorStop(0, "#00d2ff");
    gradient.addColorStop(0.5, "#00e676");
    gradient.addColorStop(1, "#3a7bd5");

    ctx.beginPath();
    ctx.arc(centerX, centerY, radius, startAngle, currentAngle);
    ctx.strokeStyle = gradient;
    ctx.lineWidth = 14;
    ctx.lineCap = "round";
    ctx.stroke();

    // Central Value Text
    ctx.fillStyle = "#f0f4fc";
    ctx.font = "bold 28px sans-serif";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(`${Math.round(value)}${options.unit || "%"}`, centerX, centerY - 10);

    // Label Text
    ctx.fillStyle = "#8e9bb2";
    ctx.font = "12px sans-serif";
    ctx.fillText(options.label || "State of Charge", centerX, centerY + 18);
  }
};
