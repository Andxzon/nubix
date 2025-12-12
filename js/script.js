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

// ---------------- SERVICE WORKER Y PUSH NOTIFICATIONS ----------------

let swRegistration = null;
let pushSubscription = null;

function urlBase64ToUint8Array(base64String) {
  const padding = '='.repeat((4 - base64String.length % 4) % 4);
  const base64 = (base64String + padding)
    .replace(/-/g, '+')
    .replace(/_/g, '/');
  const rawData = window.atob(base64);
  const outputArray = new Uint8Array(rawData.length);
  for (let i = 0; i < rawData.length; ++i) {
    outputArray[i] = rawData.charCodeAt(i);
  }
  return outputArray;
}

async function registerServiceWorker() {
  if (!('serviceWorker' in navigator)) {
    console.warn('Service Worker no soportado');
    return null;
  }
  
  try {
    const registration = await navigator.serviceWorker.register('/sw.js');
    console.log('✅ Service Worker registrado:', registration.scope);
    swRegistration = registration;
    return registration;
  } catch (error) {
    console.error('Error registrando Service Worker:', error);
    return null;
  }
}

async function checkSubscriptionStatus() {
  const subscribeBtn = document.getElementById('subscribe-btn');
  
  if (!('serviceWorker' in navigator) || !('PushManager' in window)) {
    subscribeBtn.textContent = 'No soportado';
    subscribeBtn.disabled = true;
    console.warn('Push notifications no soportadas en este navegador');
    return;
  }
  
  await registerServiceWorker();
  
  if (swRegistration) {
    try {
      pushSubscription = await swRegistration.pushManager.getSubscription();
      if (pushSubscription) {
        subscribeBtn.textContent = 'Suscrito ✓';
        localStorage.setItem('isSubscribed', 'true');
      } else {
        subscribeBtn.textContent = 'Suscribirse';
        localStorage.setItem('isSubscribed', 'false');
      }
    } catch (error) {
      console.error('Error verificando suscripción:', error);
    }
  }
}

async function subscribeToPush() {
  if (!swRegistration) {
    await registerServiceWorker();
  }
  
  if (!swRegistration) {
    alert('Error: No se pudo registrar el Service Worker');
    return null;
  }
  
  try {
    const permission = await Notification.requestPermission();
    if (permission !== 'granted') {
      alert('Debes permitir las notificaciones para suscribirte');
      return null;
    }
    
    let vapidKey = VAPID_PUBLIC_KEY;
    if (!vapidKey) {
      const response = await fetch(`${API_URL}/vapid-public-key`);
      if (response.ok) {
        const data = await response.json();
        vapidKey = data.publicKey;
      }
    }
    
    if (!vapidKey) {
      alert('Error: No se pudo obtener la clave VAPID del servidor');
      return null;
    }
    
    const subscription = await swRegistration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(vapidKey)
    });
    
    const response = await fetch(`${API_URL}/push-subscribe`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(subscription.toJSON())
    });
    
    if (!response.ok) {
      throw new Error('Error guardando suscripción en servidor');
    }
    
    pushSubscription = subscription;
    console.log('✅ Suscrito a push notifications');
    return subscription;
  } catch (error) {
    console.error('Error suscribiendo a push:', error);
    alert('Error al suscribirse: ' + error.message);
    return null;
  }
}

async function unsubscribeFromPush() {
  if (!pushSubscription) {
    return;
  }
  
  try {
    await fetch(`${API_URL}/push-unsubscribe`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ endpoint: pushSubscription.endpoint })
    });
    
    await pushSubscription.unsubscribe();
    pushSubscription = null;
    console.log('✅ Desuscrito de push notifications');
  } catch (error) {
    console.error('Error desuscribiendo:', error);
  }
}

async function toggleSubscription() {
  const subscribeBtn = document.getElementById('subscribe-btn');
  subscribeBtn.disabled = true;
  subscribeBtn.textContent = 'Cargando...';
  
  try {
    if (localStorage.getItem('isSubscribed') === 'true' && pushSubscription) {
      await unsubscribeFromPush();
      localStorage.setItem('isSubscribed', 'false');
      subscribeBtn.textContent = 'Suscribirse';
    } else {
      const subscription = await subscribeToPush();
      if (subscription) {
        localStorage.setItem('isSubscribed', 'true');
        subscribeBtn.textContent = 'Suscrito ✓';
      } else {
        subscribeBtn.textContent = 'Suscribirse';
      }
    }
  } catch (error) {
    console.error('Error en toggle subscription:', error);
    subscribeBtn.textContent = 'Error';
  } finally {
    subscribeBtn.disabled = false;
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
    sendSeismicAlert(magnitude);
    lastAlertTimestamp = now;
  }
}

async function sendSeismicAlert(magnitude) {
  try {
    await fetch(`${API_URL}/push-seismic-alert`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ magnitude })
    });
    console.log('Alerta sísmica enviada al servidor');
  } catch (error) {
    console.error('Error enviando alerta sísmica:', error);
  }
}

document.addEventListener('DOMContentLoaded', checkSubscriptionStatus);
document.getElementById('subscribe-btn').addEventListener('click', toggleSubscription);
