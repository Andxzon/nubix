document.addEventListener('DOMContentLoaded', () => {
    const reportsContainer = document.getElementById('reports-container');
    const dateRangeSelect = document.getElementById('date-range');
    // API_URL viene de config.js

    const createReportElement = (data) => {
        const fecha = data.fecha || 'Fecha desconocida';
        const div = document.createElement('div');
        div.className = 'report-item';
        
        const condicionClass = {
            'Óptimo': 'status-optimal',
            'Estable': 'status-stable',
            'Variable': 'status-variable',
            'Alerta': 'status-alert',
            'Crítico': 'status-critical'
        }[data.condicion_general] || 'status-stable';

        div.innerHTML = `
            <div class="report-header">
                <h2>📊 Informe del ${fecha}</h2>
                <span class="status-badge ${condicionClass}">${data.condicion_general || 'Sin datos'}</span>
            </div>
            
            ${data.duracion_monitoreo ? `
            <div class="report-meta">
                <span>🕐 ${data.hora_inicio || '--:--'} - ${data.hora_fin || '--:--'}</span>
                <span>⏱️ ${data.duracion_monitoreo}</span>
                <span>📈 ${data.total_lecturas || 0} lecturas</span>
            </div>
            ` : ''}
            
            <section class="report-section">
                <h3>📝 Resumen Ejecutivo</h3>
                <p class="executive-summary">${data.resumen_ejecutivo || data.resumen || 'No disponible.'}</p>
            </section>
            
            ${data.indice_confort ? `
            <section class="report-section comfort-index">
                <h3>🌡️ Índice de Confort</h3>
                <div class="comfort-meter">
                    <div class="comfort-value">${data.indice_confort.valor}/100</div>
                    <div class="comfort-bar">
                        <div class="comfort-fill" style="width: ${data.indice_confort.valor}%"></div>
                    </div>
                    <p>${data.indice_confort.descripcion}</p>
                </div>
            </section>
            ` : ''}
            
            <section class="report-section">
                <h3>📊 Variables Ambientales</h3>
                <div class="variables-grid">
                    ${createVariableCard('🌡️', 'Temperatura', data.variables?.temperatura)}
                    ${createVariableCard('📊', 'Presión', data.variables?.presion)}
                    ${createVariableCard('💧', 'Humedad Relativa', data.variables?.humedad_relativa)}
                    ${createVariableCard('☀️', 'Luminosidad', data.variables?.luminosidad)}
                    ${createVariableCard('🌱', 'Humedad Suelo', data.variables?.humedad_suelo)}
                    ${createVariableCard('📳', 'Vibración', data.variables?.vibracion)}
                </div>
            </section>
            
            ${data.correlaciones && data.correlaciones.length > 0 ? `
            <section class="report-section">
                <h3>🔗 Correlaciones Detectadas</h3>
                <ul class="correlations-list">
                    ${data.correlaciones.map(c => `<li>${c}</li>`).join('')}
                </ul>
            </section>
            ` : ''}
            
            ${data.anomalias && data.anomalias.length > 0 ? `
            <section class="report-section">
                <h3>⚠️ Anomalías Detectadas</h3>
                <div class="anomalies-list">
                    ${Array.isArray(data.anomalias) ? 
                        (typeof data.anomalias[0] === 'string' ? 
                            data.anomalias.map(a => `<div class="anomaly-item"><p>${a}</p></div>`).join('') :
                            data.anomalias.map(a => `
                                <div class="anomaly-item severity-${a.severidad || 'media'}">
                                    <div class="anomaly-header">
                                        <span class="anomaly-time">${a.hora || '--:--'}</span>
                                        <span class="anomaly-type">${a.tipo || 'Anomalía'}</span>
                                        <span class="anomaly-severity">${a.severidad || 'media'}</span>
                                    </div>
                                    <p><strong>${a.variable}:</strong> ${a.descripcion}</p>
                                    ${a.posible_causa ? `<p class="anomaly-cause">💡 ${a.posible_causa}</p>` : ''}
                                </div>
                            `).join('')
                        ) : ''
                    }
                </div>
            </section>
            ` : ''}
            
            ${data.alertas && data.alertas.length > 0 ? `
            <section class="report-section alerts-section">
                <h3>🚨 Alertas</h3>
                ${data.alertas.map(a => `
                    <div class="alert-item">
                        <strong>${a.tipo}:</strong> ${a.mensaje}
                        ${a.accion_recomendada ? `<p class="alert-action">➡️ ${a.accion_recomendada}</p>` : ''}
                    </div>
                `).join('')}
            </section>
            ` : ''}
            
            ${data.recomendaciones && data.recomendaciones.length > 0 ? `
            <section class="report-section">
                <h3>💡 Recomendaciones</h3>
                <ul class="recommendations-list">
                    ${data.recomendaciones.map(r => `<li>${r}</li>`).join('')}
                </ul>
            </section>
            ` : ''}
            
            <section class="report-section">
                <h3>📋 Observaciones</h3>
                <p class="observations">${data.observaciones || 'No disponible.'}</p>
            </section>
            
            ${data.calidad_datos ? `
            <section class="report-section quality-section">
                <h3>📈 Calidad de Datos</h3>
                <div class="quality-info">
                    <span>Completitud: ${data.calidad_datos.completitud}</span>
                    <span>Confiabilidad: ${data.calidad_datos.confiabilidad}</span>
                    ${data.calidad_datos.sensores_problematicos?.length > 0 ? 
                        `<span class="problematic">⚠️ Sensores con problemas: ${data.calidad_datos.sensores_problematicos.join(', ')}</span>` : 
                        '<span class="ok">✅ Todos los sensores funcionando correctamente</span>'
                    }
                </div>
            </section>
            ` : ''}
        `;
        return div;
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
        
        const tendenciaIcon = {
            'en aumento': '📈',
            'en descenso': '📉',
            'estable': '➡️',
            'oscilante': '📊',
            'errática': '⚡'
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
                        <span class="stat-label">Mín</span>
                        <span class="stat-value">${variable.min ?? 'N/A'}</span>
                    </div>
                    <div class="stat">
                        <span class="stat-label">Máx</span>
                        <span class="stat-value">${variable.max ?? 'N/A'}</span>
                    </div>
                </div>
                <div class="variable-trend">
                    ${tendenciaIcon} ${variable.tendencia || 'sin tendencia'}
                </div>
                ${variable.interpretacion ? `<p class="variable-interpretation">${variable.interpretacion}</p>` : ''}
                ${variable.estado ? `<p class="variable-status">Estado: <strong>${variable.estado}</strong></p>` : ''}
                ${variable.necesita_riego !== undefined ? 
                    `<p class="variable-action">${variable.necesita_riego ? '💧 Necesita riego' : '✅ Riego no necesario'}</p>` : ''
                }
                ${variable.pronostico ? `<p class="variable-forecast">🔮 ${variable.pronostico}</p>` : ''}
            </div>
        `;
    };

    const loadReports = async () => {
        reportsContainer.innerHTML = '<p>Cargando informes...</p>';
        
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
            reportsContainer.innerHTML = '<p>No se encontraron informes. Genera uno desde el dashboard.</p>';
        }
    };

    dateRangeSelect.addEventListener('change', () => {
        loadReports();
    });

    loadReports();
});
