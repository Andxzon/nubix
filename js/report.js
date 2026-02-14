document.addEventListener('DOMContentLoaded', () => {
    const reportsContainer = document.getElementById('reports-container');
    const dateRangeSelect = document.getElementById('date-range');

    const createReportElement = (data) => {
        const fecha = data.fecha || 'Fecha desconocida';
        const div = document.createElement('div');
        div.className = 'report-item';

        const condicionClass = {
            'Sistema Estable': 'status-optimal',
            'Operación Normal': 'status-stable',
            'Fluctuación Detectada': 'status-variable',
            'Inestabilidad Atmosférica': 'status-alert',
            'Fenómeno Extremo': 'status-critical'
        }[data.condicion_general] || 'status-stable';

        const reportId = data.id || Math.floor(Math.random() * 1000000);
        const plotlyId = `plotly-scatter-${reportId}`;
        const radarId = `radarChart-${reportId}`;

        div.innerHTML = `
            <div class="report-header">
                <div class="header-main">
                    <h2>📊 Informe de Análisis Ambiental - ${fecha}</h2>
                    <span class="report-badge ${data.condicion_general?.toLowerCase().includes('estable') ? 'badge-ok' : 'badge-warn'}">
                        ${data.condicion_general || 'Estado Analizado'}
                    </span>
                </div>
                <div class="header-meta">
                    <span>🕐 ${data.hora_inicio || '--:--'} - ${data.hora_fin || '--:--'}</span>
                    <span>⏱️ ${data.duracion_monitoreo || '0h 0m'}</span>
                    <span>📈 ${data.total_lecturas || 0} muestras</span>
                </div>
            </div>

            <section class="report-section">
                <h3>📝 Resumen Técnico Ejecutivo</h3>
                <p class="executive-summary">${data.resumen_ejecutivo || 'No disponible.'}</p>
            </section>

            <section class="report-section">
                <h3>🌌 Análisis Multivariante Avanzado</h3>
                <div class="charts-grid">
                    <div class="chart-box">
                        <span class="chart-label">Distribución Estática (Seaborn Premium)</span>
                        <div class="chart-container-inner">
                            ${data.scatter_plot_img ?
                `<img src="${data.scatter_plot_img}" class="seaborn-img" alt="Seaborn Statistics">` :
                `<div class="no-data-msg">Procesando imagen estadística...</div>`
            }
                        </div>
                    </div>
                    <div class="chart-box">
                        <span class="chart-label">Exploración Interactiva (Plotly Dynamic)</span>
                        <div id="${plotlyId}" class="plotly-container"></div>
                    </div>
                </div>
                
                <div class="charts-grid-single" style="margin-top:20px;">
                    <div class="chart-box">
                        <span class="chart-label">Balance de Estabilidad Energética (Radar)</span>
                        <div class="radar-container">
                            <canvas id="${radarId}"></canvas>
                        </div>
                    </div>
                </div>
            </section>

            <section class="report-section">
                <h3>📊 Métricas Estadísticas de Alta Precisión</h3>
                <div class="variables-grid">
                    ${createVariableCard('🌡️', 'Temperatura', data.variables?.temperatura)}
                    ${createVariableCard('📊', 'Presión', data.variables?.presion)}
                    ${createVariableCard('💧', 'Humedad Relativa', data.variables?.humedad)}
                    ${createVariableCard('☀️', 'Luminosidad', data.variables?.luz)}
                    ${createVariableCard('🌱', 'Humedad Suelo', data.variables?.humedad_suelo)}
                    ${createVariableCard('📳', 'Vibración', data.variables?.vibracion)}
                </div>
            </section>

            ${data.correlaciones && data.correlaciones.length > 0 ? `
            <section class="report-section">
                <h3>🔗 Análisis de Correlaciones Detectadas</h3>
                <ul class="correlations-list">
                    ${data.correlaciones.map(c => `<li>${c}</li>`).join('')}
                </ul>
            </section>
            ` : ''}

            ${data.alertas && data.alertas.length > 0 ? `
            <section class="report-section alerts-section">
                <h3>🚨 Detección de Fenómenos y Anomalías</h3>
                ${data.alertas.map(a => `
                    <div class="alert-item">
                        <strong>${a.tipo}:</strong> ${a.mensaje}
                        ${a.accion_recomendada ? `<p class="alert-action">➡️ Recomendación Técnica: ${a.accion_recomendada}</p>` : ''}
                    </div>
                `).join('')}
            </section>
            ` : ''}

            <section class="report-section">
                <h3>💡 Interpretación y Pronóstico</h3>
                <div class="interpretations">
                    <div class="inter-box">
                        <h4>Análisis Predictivo</h4>
                        <p>${data.interpretacion || 'No disponible.'}</p>
                    </div>
                    <div class="inter-box">
                        <h4>Observaciones de Estabilidad</h4>
                        <p style="font-style: italic;">${data.observaciones || 'No disponible.'}</p>
                    </div>
                </div>
            </section>

            <section class="report-section quality-section">
                <h3>📈 Integridad y Confiabilidad</h3>
                <div class="quality-info">
                    <span>Completitud de Muestra: ${data.calidad_datos?.completitud || '0%'}</span>
                    <span>Confiabilidad del Sensor: ${data.calidad_datos?.confiabilidad || 'Desconocida'}</span>
                </div>
            </section>
        `;

        // Initialize Charts after adding to DOM
        setTimeout(() => {
            if (data.plotly_scatter_data) {
                initPlotlyScatter(plotlyId, data.plotly_scatter_data);
            }

            if (data.radar_estabilidad) {
                initRadarChart(radarId, data.radar_estabilidad);
            }
        }, 100);


        return div;
    };

    const getStabilityColor = (val) => {
        if (val > 80) return '#10b981';
        if (val > 60) return '#3b82f6';
        if (val > 40) return '#f59e0b';
        return '#ef4444';
    };

    const initRadarChart = (canvasId, radarData) => {
        const ctx = document.getElementById(canvasId).getContext('2d');
        new Chart(ctx, {
            type: 'radar',
            data: {
                labels: radarData.labels,
                datasets: [{
                    label: 'Índice de Estabilidad (%)',
                    data: radarData.values,
                    backgroundColor: 'rgba(96, 165, 250, 0.2)',
                    borderColor: '#60a5fa',
                    borderWidth: 2,
                    pointBackgroundColor: '#fff'
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    r: {
                        angleLines: { color: 'rgba(255,255,255,0.1)' },
                        grid: { color: 'rgba(255,255,255,0.1)' },
                        pointLabels: { color: '#94a3b8', font: { size: 11 } },
                        ticks: { display: false, stepSize: 20 },
                        suggestedMin: 0,
                        suggestedMax: 100
                    }
                },
                plugins: {
                    legend: { labels: { color: '#fff' } }
                }
            }
        });
    };

    const initScatterChart = (canvasId, points) => {
        const ctx = document.getElementById(canvasId).getContext('2d');
        new Chart(ctx, {
            type: 'scatter',
            data: {
                datasets: [{
                    label: 'Puntos de Muestreo (Temp vs Hum)',
                    data: points,
                    backgroundColor: 'rgba(96, 165, 250, 0.5)',
                    borderColor: '#60a5fa',
                    borderWidth: 1,
                    pointRadius: 4,
                    pointHoverRadius: 6
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    x: {
                        title: { display: true, text: 'Temperatura (°C)', color: '#94a3b8' },
                        grid: { color: 'rgba(255,255,255,0.05)' },
                        ticks: { color: '#64748b' }
                    },
                    y: {
                        title: { display: true, text: 'Humedad (%)', color: '#94a3b8' },
                        grid: { color: 'rgba(255,255,255,0.05)' },
                        ticks: { color: '#64748b' }
                    }
                },
                plugins: {
                    legend: { labels: { color: '#94a3b8' } },
                    tooltip: {
                        callbacks: {
                            label: (context) => `Temp: ${context.raw.x}°C, Hum: ${context.raw.y}%, Pres: ${context.raw.p}hPa (${context.raw.t})`
                        }
                    }
                }
            }
        });
    };

    const initPlotlyScatter = (containerId, traces) => {
        const container = document.getElementById(containerId);
        if (!container || !traces) return;

        const layout = {
            paper_bgcolor: 'rgba(0,0,0,0)',
            plot_bgcolor: 'rgba(0,0,0,0)',
            font: { color: '#94a3b8', size: 11 },
            margin: { l: 50, r: 20, t: 40, b: 50 },
            showlegend: true,
            legend: {
                x: 1,
                xanchor: 'right',
                y: 1,
                bgcolor: 'rgba(15,23,42,0.8)',
                font: { size: 10 }
            },
            xaxis: {
                title: 'Temperatura (°C)',
                gridcolor: 'rgba(255,255,255,0.05)',
                zeroline: false,
                linecolor: '#1e293b'
            },
            yaxis: {
                title: 'Humedad (%)',
                gridcolor: 'rgba(255,255,255,0.05)',
                zeroline: false,
                linecolor: '#1e293b'
            },
            hovermode: 'closest',
            autosize: true
        };

        const config = {
            responsive: true,
            displayModeBar: false
        };

        Plotly.newPlot(containerId, traces, layout, config);
    };

    const createVariableCard = (icon, name, variable) => {
        if (!variable) {
            return `
                <div class="variable-card no-data">
                    <h4>${icon} ${name}</h4>
                    <p>Sin datos</p>
                </div>
            `;
        }

        const trendIcon = {
            'en aumento': '📈',
            'en descenso': '📉',
            'estable': '➡️',
            'sin datos': '❓'
        }[variable.tendencia] || '📊';

        return `
            <div class="variable-card">
                <h4>${icon} ${name}</h4>
                <div class="variable-stats">
                    <div class="stat">
                        <span class="stat-label">Promedio</span>
                        <span class="stat-value">${variable.promedio ?? 'N/A'}</span>
                    </div>
                    <div class="stat">
                        <span class="stat-label">σ (Desv)</span>
                        <span class="stat-value">${variable.desviacion ?? 'N/A'}</span>
                    </div>
                    <div class="stat">
                        <span class="stat-label">Rango</span>
                        <span class="stat-value">${variable.amplitud ?? 'N/A'}</span>
                    </div>
                </div>
                <div class="variable-trend" style="font-size: 0.75rem; margin-top: 10px; color: #94a3b8;">
                    Tendencia: ${trendIcon} ${variable.tendencia || 'N/A'}
                </div>
                ${variable.pronostico ? `<p class="variable-forecast" style="color: #60a5fa; font-size: 0.8rem; margin-top: 5px;">🔮 ${variable.pronostico}</p>` : ''}
            </div>
        `;
    };

    const loadReports = async () => {
        reportsContainer.innerHTML = '<div class="loader"></div><p style="text-align:center; color:#94a3b8;">Sincronizando modelos predictivos...</p>';

        const storedReport = localStorage.getItem('reportData');
        if (storedReport) {
            try {
                const data = JSON.parse(storedReport);
                reportsContainer.innerHTML = '';
                reportsContainer.appendChild(createReportElement(data));
                localStorage.removeItem('reportData');
                return;
            } catch (e) {
                console.error('Error parseando reporte guardado:', e);
            }
        }

        try {
            const response = await fetch(`${API_URL}/latest-report`);
            if (!response.ok) {
                throw new Error('No hay reportes disponibles');
            }
            const data = await response.json();
            reportsContainer.innerHTML = '';
            reportsContainer.appendChild(createReportElement(data));
        } catch (error) {
            console.error('Error cargando reportes:', error);
            reportsContainer.innerHTML = '<div style="text-align:center; padding:50px; color:#64748b;"><h3>No se encontraron reportes previos</h3><p>Genera un análisis desde el dashboard principal.</p></div>';
        }
    };

    dateRangeSelect.addEventListener('change', () => {
        loadReports();
    });

    loadReports();
});
