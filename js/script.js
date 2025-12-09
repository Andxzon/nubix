// ---------------- CONFIG ----------------
const WINDOW_MINUTES = 10;
const now = () => Date.now();

const SENSORS = [
  { id: 'tempChart',  label: 'Temperatura',    unit: '°C',   suggestedMin: 10,  suggestedMax: 50,   color: 'rgba(255,99,71,0.95)' },
  { id: 'presChart',  label: 'Presión',        unit: 'hPa',  suggestedMin: 0,   suggestedMax: 1100, color: 'rgba(54,162,235,0.95)' },
  { id: 'humChart',   label: 'Humedad',        unit: '%',    suggestedMin: 0,   suggestedMax: 85,   color: 'rgba(75,192,192,0.95)' },
  { id: 'soilChart',  label: 'Humedad suelo',  unit: '%',    suggestedMin: 0,   suggestedMax: 100,  color: 'rgba(153,102,255,0.95)' },
  { id: 'lightChart', label: 'Luz',            unit: 'lux',  suggestedMin: 0,   suggestedMax: 5000, color: 'rgba(255,206,86,0.95)' },
  { id: 'vibrChart',  label: 'Vibración',      unit: 'Hz',   suggestedMin: 0,   suggestedMax: 2,    color: 'rgba(255, 159, 64, 0.95)' }
];

const charts = {};

// ---------------- Funciones de almacenamiento ----------------
function saveData(sensorId, dataset) {
  localStorage.setItem(sensorId, JSON.stringify(dataset));
}

function loadData(sensorId) {
  const raw = localStorage.getItem(sensorId);
  if (!raw) return [];
  try {
    return JSON.parse(raw);
  } catch {
    return [];
  }
}

// ---------------- Inicializar gráficas ----------------
SENSORS.forEach(sensor => {
  const ctx = document.getElementById(sensor.id).getContext('2d');

  const cfg = {
    type: 'line',
    data: {
      datasets: [{
        label: `${sensor.label} (${sensor.unit})`,
        data: loadData(sensor.id),
        tension: 0.3,
        borderColor: sensor.color,
        backgroundColor: sensor.color.replace('0.95', '0.12') || 'rgba(0,0,0,0.08)',
        pointRadius: 0,
        fill: true,
      }]
    },
    options: {
      maintainAspectRatio: false,
      animation: false,
      plugins: { 
        legend: { display: true, labels: { color: "white" } },
        title: {
          display: true,
          text: sensor.label,
          color: "white",
          font: { size: 14 }
        }
      },
      scales: {
        x: {
          type: 'time',
          time: { unit: 'minute', displayFormats: { minute: 'HH:mm:ss' } },
          ticks: { maxTicksLimit: 6 },
          grid: { color: 'rgba(255,255,255,0.03)' }
        },
        y: {
          min: sensor.suggestedMin,
          max: sensor.suggestedMax,
          grid: { color: 'rgba(255,255,255,0.03)' }
        }
      }
    }
  };

  charts[sensor.id] = new Chart(ctx, cfg);
});

// ---------------- Conexión WebSocket ----------------
const socket = io();

socket.on("connect", () => {
  console.log("✅ Conectado al servidor WebSocket");
});

socket.on("disconnect", () => {
  console.log("❌ Desconectado del servidor WebSocket");
});

socket.on("sensor_data", (data) => {
  const { sensor_id, label, value, timestamp } = data;
  
  // Verificar alerta sísmica
  if (sensor_id === 'vibrChart' && localStorage.getItem('isSubscribed') === 'true') {
    checkSeismicAlert(value);
  }

  const chart = charts[sensor_id];
  if (!chart) return;

  const dataset = chart.data.datasets[0].data;
  const windowStart = timestamp - WINDOW_MINUTES * 60 * 1000;

  dataset.push({ x: timestamp, y: value });

  while (dataset.length && dataset[0].x < windowStart) {
    dataset.shift();
  }

  chart.options.scales.x.min = windowStart;
  chart.options.scales.x.max = timestamp;

  const MAX_POINTS = 6500;
  if (dataset.length > MAX_POINTS) {
    dataset.splice(0, dataset.length - MAX_POINTS);
  }

  saveData(sensor_id, dataset);
});

// Actualización de gráficos a diferentes intervalos
const standardSensors = SENSORS.filter(s => s.id !== 'vibrChart');
const highFrequencySensors = SENSORS.filter(s => s.id === 'vibrChart');

setInterval(() => {
  standardSensors.forEach(sensor => {
    if (charts[sensor.id]) {
      charts[sensor.id].update('none');
    }
  });
}, 2000);

setInterval(() => {
  highFrequencySensors.forEach(sensor => {
    if (charts[sensor.id]) {
      charts[sensor.id].update('none');
    }
  });
}, 100);

// ---------------- INFORME INTELIGENTE ----------------

document.addEventListener('DOMContentLoaded', () => {
  const generateBtn = document.getElementById('generate-new-report-btn');
  const reportLoader = document.getElementById('report-loader');
  const reportError = document.getElementById('report-error');

  async function fetchAndShowReport(url, options, button) {
    console.log('Loading report...');
    reportLoader.style.display = 'block';
    reportError.style.display = 'none';
    button.disabled = true;
    const originalButtonText = button.textContent;
    button.textContent = 'Cargando...';

    try {
      const response = await fetch(url, options);
      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.error || `Error del servidor: ${response.status}`);
      }
      const data = await response.json();
      
      localStorage.setItem('reportData', JSON.stringify(data));
      window.open('report.html', '_blank');

    } catch (error) {
      console.error("Error al cargar el informe:", error);
      reportError.textContent = `Error: ${error.message}`;
      reportError.style.display = 'block';
    } finally {
      reportLoader.style.display = 'none';
      button.disabled = false;
      button.textContent = originalButtonText;
    }
  }

  generateBtn.addEventListener('click', (e) => {
    e.preventDefault();
    fetchAndShowReport(`${API_URL}/generate-report`, { method: 'POST' }, generateBtn);
  });
});

// ---------------- SUSCRIPCIÓN Y NOTIFICACIONES ----------------
let notificationInterval;

function checkSubscriptionStatus() {
  const subscribeBtn = document.getElementById('subscribe-btn');
  if (localStorage.getItem('isSubscribed') === 'true') {
    subscribeBtn.textContent = 'Suscrito';
    startNotifications();
  }
}

function toggleSubscription() {
  const subscribeBtn = document.getElementById('subscribe-btn');
  if (localStorage.getItem('isSubscribed') === 'true') {
    localStorage.setItem('isSubscribed', 'false');
    subscribeBtn.textContent = 'Suscribirse';
    stopNotifications();
  } else {
    Notification.requestPermission().then(permission => {
      if (permission === 'granted') {
        localStorage.setItem('isSubscribed', 'true');
        subscribeBtn.textContent = 'Suscrito';
        startNotifications();
      }
    });
  }
}

function startNotifications() {
  sendNotification();
  notificationInterval = setInterval(sendNotification, 3600000); // 1 hora
}

function stopNotifications() {
  clearInterval(notificationInterval);
}

async function sendNotification() {
  try {
    const response = await fetch(`${API_URL}/latest-report`);
    if (!response.ok) {
      throw new Error('No se pudo obtener el informe de hoy.');
    }
    const report = await response.json();
    
    const temp = report.variables?.temperatura?.promedio?.toFixed(1) || 'N/A';
    const hum = report.variables?.humedad_relativa?.promedio?.toFixed(1) || 'N/A';
    const summary = (report.resumen_ejecutivo || report.resumen || '').replace(/<br>/g, ' ');

    const notification = new Notification('Reporte Meteorológico', {
      body: `Temperatura: ${temp}°C, Humedad: ${hum}%. ${summary.substring(0, 100)}...`,
      icon: 'images/logo_noti.png' 
    });
  } catch (error) {
    console.error('Error al enviar la notificación:', error);
  }
}

// ---------------- ALERTA SÍSMICA ----------------
let lastAlertTimestamp = 0;
const ALERT_COOLDOWN = 60000;
const SEISMIC_THRESHOLD = 1.060; 

function checkSeismicAlert(magnitude) {
  const now = Date.now();
  if (now - lastAlertTimestamp < ALERT_COOLDOWN) {
    return; 
  }
  
  console.log(`Magnitud de vibración: ${magnitude}`);

  if (magnitude > SEISMIC_THRESHOLD) {
    sendSeismicAlert();
    lastAlertTimestamp = now;
  }
}

function sendSeismicAlert() {
  const notification = new Notification('ALERTA SÍSMICA 🚨', {
    body: 'Se detectó una vibración superior al umbral de seguridad.\nRevise condiciones en el área.',
    icon: 'images/alert_noti.png'
  });
}

document.addEventListener('DOMContentLoaded', checkSubscriptionStatus);
document.getElementById('subscribe-btn').addEventListener('click', toggleSubscription);
