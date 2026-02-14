"""
Módulo de Análisis Estadístico para IoT
========================================
Este módulo realiza TODOS los cálculos estadísticos en el backend.
El LLM NO debe recibir datos crudos ni realizar cálculos.
"""

from datetime import datetime, timezone, timedelta
from typing import Optional
import statistics
import math
import io
import base64
import pandas as pd
import seaborn as sns
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

def generate_scatter_plot_img(readings: list[dict]):
    """
    Genera una nube de puntos profesional usando Seaborn (Estático).
    Optimizado para fondo oscuro y legibilidad científica.
    """
    if not readings or len(readings) < 5:
        return None
    
    try:
        # Preparación científica
        df = pd.DataFrame(readings)
        df = df.dropna(subset=['temperatura', 'humedad', 'luz']).copy()
        df['temperatura'] = df['temperatura'].astype(float)
        df['humedad'] = df['humedad'].astype(float)
        df['luz'] = df['luz'].astype(float)
        
        # Categorización
        def categorize_env(lux):
            if lux < 100: return 'Baja Luz/Noche'
            if lux < 2000: return 'Ambiente Interior'
            return 'Exposición Exterior'
        df['Entorno'] = df['luz'].apply(categorize_env)

        # Configuración global de estilo ANTES de crear la figura
        sns.set_theme(style="whitegrid", rc={
            "axes.facecolor": "#0f172a",
            "figure.facecolor": "#0f172a",
            "grid.color": "#1e293b",
            "text.color": "#f8fafc",
            "axes.labelcolor": "#94a3b8",
            "xtick.color": "#64748b",
            "ytick.color": "#64748b",
            "axes.edgecolor": "#1e293b",
            "patch.edgecolor": "#1e293b"
        })

        plt.figure(figsize=(8, 4.5), facecolor='#0f172a')
        
        # Paleta sobria
        paleta = {"Baja Luz/Noche": "#475569", "Ambiente Interior": "#3b82f6", "Exposición Exterior": "#f59e0b"}
        
        plot = sns.scatterplot(
            data=df, x='temperatura', y='humedad', 
            hue='Entorno', style='Entorno',
            palette=paleta, alpha=0.9, s=180,
            edgecolor='#ffffff', linewidth=1.2
        )
        
        # Tendencia suave
        sns.regplot(data=df, x='temperatura', y='humedad', scatter=False, color="#ffffff", 
                    line_kws={"alpha":0.15, "linestyle":"--", "linewidth": 1}, truncate=False)

        plot.set_title("Nube de Dispersión Termo-Higrométrica", fontsize=16, pad=30, weight='bold', color='#f1f5f9')
        plot.set_xlabel("Temperatura Ambiental (°C)", fontsize=12, labelpad=15)
        plot.set_ylabel("Humedad Relativa (%)", fontsize=12, labelpad=15)
        
        # Leyenda premium
        legend = plt.legend(title="Condición de Campo", title_fontsize='11', fontsize='10', 
                            loc='upper right', frameon=True, facecolor='#1e293b', edgecolor='#334155')
        plt.setp(legend.get_texts(), color='#cbd5e1')
        plt.setp(legend.get_title(), color='#f1f5f9')

        plt.tight_layout()
        
        buf = io.BytesIO()
        # LA CLAVE: Usar transparent=True o facecolor coincidente con CSS
        plt.savefig(buf, format='png', bbox_inches='tight', facecolor='#0f172a', transparent=False, dpi=140)
        plt.close()
        
        buf.seek(0)
        return f"data:image/png;base64,{base64.b64encode(buf.getvalue()).decode('utf-8')}"
    except Exception as e:
        print(f"Error Seaborn Refinado: {e}")
        return None


def generate_plotly_data(readings: list[dict]):
    """
    Prepara la configuración para Plotly.js (Interactivo).
    Permite exploración profunda con hover y zoom.
    """
    if not readings or len(readings) < 2:
        return None
    
    try:
        df = pd.DataFrame(readings)
        df = df.dropna(subset=['temperatura', 'humedad', 'luz', 'presion']).copy()
        
        # Convertir a tipos nativos para JSON
        df['temperatura'] = df['temperatura'].astype(float)
        df['humedad'] = df['humedad'].astype(float)
        df['luz'] = df['luz'].astype(float)
        df['presion'] = df['presion'].astype(float)
        df['vibracion'] = df['vibracion'].astype(float)
        df['time_str'] = df['timestamp'].apply(lambda x: x.strftime('%H:%M:%S') if hasattr(x, 'strftime') else str(x))

        # Categorizar para el color en Plotly
        def categorize_env(lux):
            if lux < 100: return 'Penumbra'
            if lux < 2000: return 'Normal'
            return 'Directo'
        df['Entorno'] = df['luz'].apply(categorize_env)

        # Generar "Traces" para Plotly
        traces = []
        colors = {'Penumbra': '#636efa', 'Normal': '#00cc96', 'Directo': '#ab63fa'}
        
        for entorno in df['Entorno'].unique():
            dff = df[df['Entorno'] == entorno]
            traces.append({
                'x': dff['temperatura'].tolist(),
                'y': dff['humedad'].tolist(),
                'name': entorno,
                'mode': 'markers',
                'marker': {'size': 10, 'color': colors.get(entorno, '#ef553b'), 'opacity': 0.7, 'line': {'width': 1, 'color': 'white'}},
                'text': [f"Tiempo: {t}<br>Luz: {l} lux<br>Presión: {p} hPa<br>Vib: {v} g" 
                         for t, l, p, v in zip(dff['time_str'], dff['luz'], dff['presion'], dff['vibracion'])],
                'hoverinfo': 'text+x+y'
            })
            
        return traces
    except Exception as e:
        print(f"Error Plotly Data: {e}")
        return None

def calculate_trend(values: list[float]) -> dict:
    """
    Calcula tendencia usando regresión lineal simple.
    Retorna pendiente, dirección y magnitud.
    """
    if len(values) < 2:
        return {"slope": 0.0, "direction": "sin_datos", "magnitude": "nula"}
    
    n = len(values)
    x = list(range(n))
    
    mean_x = sum(x) / n
    mean_y = sum(values) / n
    
    numerator = sum((x[i] - mean_x) * (values[i] - mean_y) for i in range(n))
    denominator = sum((x[i] - mean_x) ** 2 for i in range(n))
    
    slope = numerator / denominator if denominator != 0 else 0.0
    
    if abs(slope) < 0.01:
        direction = "estable"
        magnitude = "nula"
    elif slope > 0:
        direction = "ascendente"
        magnitude = "alta" if slope > 0.5 else ("media" if slope > 0.1 else "baja")
    else:
        direction = "descendente"
        magnitude = "alta" if slope < -0.5 else ("media" if slope < -0.1 else "baja")
    
    return {
        "slope": round(slope, 4),
        "direction": direction,
        "magnitude": magnitude
    }


def calculate_pearson_correlation(x: list[float], y: list[float]) -> Optional[float]:
    """Calcula correlación de Pearson entre dos series."""
    if len(x) != len(y) or len(x) < 3:
        return None
    
    n = len(x)
    mean_x = sum(x) / n
    mean_y = sum(y) / n
    
    numerator = sum((x[i] - mean_x) * (y[i] - mean_y) for i in range(n))
    
    std_x = math.sqrt(sum((xi - mean_x) ** 2 for xi in x) / n)
    std_y = math.sqrt(sum((yi - mean_y) ** 2 for yi in y) / n)
    
    if std_x == 0 or std_y == 0:
        return None
    
    correlation = numerator / (n * std_x * std_y)
    return round(correlation, 3)


def detect_anomalies(values: list[float], timestamps: list[datetime], 
                     threshold_std: float = 2.5) -> list[dict]:
    """
    Detecta anomalías usando método de desviación estándar.
    """
    if len(values) < 5:
        return []
    
    mean = statistics.mean(values)
    std = statistics.stdev(values)
    
    if std == 0:
        return []
    
    anomalies = []
    for i, (value, ts) in enumerate(zip(values, timestamps)):
        z_score = abs(value - mean) / std
        if z_score > threshold_std:
            anomalies.append({
                "timestamp": ts.strftime("%H:%M") if isinstance(ts, datetime) else str(ts),
                "value": round(value, 2),
                "z_score": round(z_score, 2),
                "type": "extremo_alto" if value > mean else "extremo_bajo",
                "severity": "alta" if z_score > 3.5 else ("media" if z_score > 3.0 else "baja")
            })
    
    return anomalies


def calculate_variable_stats(values: list[float], timestamps: list[datetime] = None) -> dict:
    """Calcula estadísticas completas para una variable."""
    if not values:
        return None
    
    clean_values = [v for v in values if v is not None]
    
    if not clean_values:
        return None
    
    result = {
        "count": len(clean_values),
        "avg": round(statistics.mean(clean_values), 2),
        "min": round(min(clean_values), 2),
        "max": round(max(clean_values), 2),
        "range": round(max(clean_values) - min(clean_values), 2),
        "std_dev": round(statistics.stdev(clean_values), 2) if len(clean_values) > 1 else 0.0,
        "variance": round(statistics.variance(clean_values), 4) if len(clean_values) > 1 else 0.0,
        "rate_of_change": calculate_rate_of_change(clean_values),
        "stability": calculate_stability_index(clean_values),
        "trend": calculate_trend(clean_values)
    }
    
    if timestamps:
        anomalies = detect_anomalies(clean_values, timestamps)
        result["anomalies"] = anomalies
        result["anomaly_count"] = len(anomalies)
    
    return result


def check_thresholds(stats: dict, thresholds: dict) -> list[dict]:
    """
    Verifica umbrales y genera alertas.
    thresholds = {"min": valor, "max": valor, "variable": "nombre"}
    """
    alerts = []
    
    if stats is None:
        return alerts
    
    variable = thresholds.get("variable", "desconocido")
    
    if "min" in thresholds and stats["min"] < thresholds["min"]:
        alerts.append({
            "type": "umbral_minimo",
            "variable": variable,
            "threshold": thresholds["min"],
            "actual": stats["min"],
            "severity": "alta" if stats["min"] < thresholds["min"] * 0.8 else "media"
        })
    
    if "max" in thresholds and stats["max"] > thresholds["max"]:
        alerts.append({
            "type": "umbral_maximo",
            "variable": variable,
            "threshold": thresholds["max"],
            "actual": stats["max"],
            "severity": "alta" if stats["max"] > thresholds["max"] * 1.2 else "media"
        })
    
    return alerts


def calculate_data_quality(readings: list[dict], expected_interval_seconds: int = 10) -> dict:
    """
    Evalúa la calidad de los datos recibidos.
    """
    if not readings:
        return {
            "completeness": 0,
            "continuity": 0,
            "reliability": "sin_datos",
            "issues": ["Sin lecturas disponibles"],
            "total_readings": 0
        }
    
    total = len(readings)
    
    sensors = ["temperatura", "presion", "humedad", "humedad_suelo", "luz", "vibracion"]
    null_counts = {s: 0 for s in sensors}
    problematic_sensors = []
    
    for reading in readings:
        for sensor in sensors:
            if reading.get(sensor) is None:
                null_counts[sensor] += 1
    
    for sensor, count in null_counts.items():
        null_percent = (count / total) * 100
        if null_percent > 20:
            problematic_sensors.append({
                "sensor": sensor,
                "null_percent": round(null_percent, 1)
            })
    
    total_possible = total * len(sensors)
    total_nulls = sum(null_counts.values())
    completeness = round(((total_possible - total_nulls) / total_possible) * 100, 1)
    
    gaps = 0
    if total > 1:
        for i in range(1, len(readings)):
            ts1 = readings[i-1].get("timestamp")
            ts2 = readings[i].get("timestamp")
            if isinstance(ts1, datetime) and isinstance(ts2, datetime):
                diff = (ts2 - ts1).total_seconds()
                if diff > expected_interval_seconds * 3:
                    gaps += 1
    
    continuity = round(100 - (gaps / max(total - 1, 1)) * 100, 1)
    
    if completeness >= 90 and continuity >= 90:
        reliability = "alta"
    elif completeness >= 70 and continuity >= 70:
        reliability = "media"
    else:
        reliability = "baja"
    
    issues = []
    if completeness < 80:
        issues.append(f"Completitud baja: {completeness}%")
    if continuity < 80:
        issues.append(f"Continuidad afectada: {gaps} interrupciones detectadas")
    for ps in problematic_sensors:
        issues.append(f"Sensor {ps['sensor']}: {ps['null_percent']}% nulos")
    
    return {
        "completeness": completeness,
        "continuity": continuity,
        "reliability": reliability,
        "gaps_detected": gaps,
        "problematic_sensors": [ps["sensor"] for ps in problematic_sensors],
        "issues": issues if issues else ["Sin problemas detectados"],
        "total_readings": total
    }


def calculate_stability_index(values: list[float]) -> dict:
    """
    Calcula un índice de estabilidad basado en la varianza y desviaciones.
    """
    if len(values) < 5:
        return {"value": 100.0, "status": "estable_por_pocos_datos"}
    
    std = statistics.stdev(values)
    mean = statistics.mean(values)
    
    # Coeficiente de variación (CV)
    cv = (std / mean) * 100 if mean != 0 else 0
    
    if cv < 2:
        status = "ultra_estable"
    elif cv < 5:
        status = "estable"
    elif cv < 15:
        status = "fluctuante"
    else:
        status = "volatil"
        
    return {
        "stability_index": round(100 - min(cv * 4, 100), 2),
        "volatility": round(cv, 2),
        "status": status
    }

def calculate_rate_of_change(values: list[float]) -> float:
    """Calcula la velocidad de cambio entre el primer y último punto."""
    if len(values) < 2:
        return 0.0
    return round((values[-1] - values[0]) / len(values), 4)



def calculate_soil_status(humidity_avg: float, humidity_trend: str) -> dict:
    """Determina estado del suelo basado en humedad."""
    if humidity_avg is None:
        return {"status": "sin_datos", "needs_irrigation": None}
    
    if humidity_avg >= 80:
        status = "saturado"
        needs_irrigation = False
    elif humidity_avg >= 50:
        status = "optimo"
        needs_irrigation = False
    elif humidity_avg >= 30:
        status = "seco"
        needs_irrigation = True
    else:
        status = "muy_seco"
        needs_irrigation = True
    
    urgency = "ninguna"
    if needs_irrigation:
        if humidity_avg < 20:
            urgency = "critica"
        elif humidity_avg < 30:
            urgency = "alta"
        else:
            urgency = "normal"
    
    return {
        "status": status,
        "needs_irrigation": needs_irrigation,
        "irrigation_urgency": urgency
    }


def calculate_pressure_forecast(pressure_avg: float, pressure_trend: dict) -> str:
    """Genera pronóstico basado en presión atmosférica."""
    if pressure_avg is None:
        return "sin_datos"
    
    direction = pressure_trend.get("direction", "estable")
    magnitude = pressure_trend.get("magnitude", "nula")
    
    if pressure_avg < 1005:
        base = "baja_presion"
    elif pressure_avg > 1020:
        base = "alta_presion"
    else:
        base = "presion_normal"
    
    if direction == "descendente" and magnitude in ["media", "alta"]:
        return "deterioro_probable"
    elif direction == "ascendente" and magnitude in ["media", "alta"]:
        return "mejora_probable"
    elif base == "baja_presion":
        return "inestabilidad_posible"
    elif base == "alta_presion":
        return "estabilidad_esperada"
    else:
        return "sin_cambios_significativos"


def analyze_readings(readings: list[dict]) -> dict:
    """
    Función principal: Analiza todas las lecturas y genera JSON estructurado.
    Este JSON es lo ÚNICO que se envía al LLM.
    """
    if not readings:
        return {"error": "sin_lecturas", "analysis": None}
    
    tz = timezone(timedelta(hours=-5))
    now = datetime.now(tz)
    
    timestamps = []
    temp_values, pres_values, hum_values = [], [], []
    soil_values, light_values, vib_values = [], [], []
    
    for r in readings:
        ts = r.get("timestamp")
        if ts:
            timestamps.append(ts)
        
        if r.get("temperatura") is not None:
            temp_values.append(float(r["temperatura"]))
        if r.get("presion") is not None:
            pres_values.append(float(r["presion"]))
        if r.get("humedad") is not None:
            hum_values.append(float(r["humedad"]))
        if r.get("humedad_suelo") is not None:
            soil_values.append(float(r["humedad_suelo"]))
        if r.get("luz") is not None:
            light_values.append(float(r["luz"]))
        if r.get("vibracion") is not None:
            vib_values.append(float(r["vibracion"]))
    
    temp_stats = calculate_variable_stats(temp_values, timestamps)
    pres_stats = calculate_variable_stats(pres_values, timestamps)
    hum_stats = calculate_variable_stats(hum_values, timestamps)
    soil_stats = calculate_variable_stats(soil_values, timestamps)
    light_stats = calculate_variable_stats(light_values, timestamps)
    vib_stats = calculate_variable_stats(vib_values, timestamps)
    
    alerts = []
    
    alerts.extend(check_thresholds(temp_stats, {"min": 5, "max": 40, "variable": "temperatura"}))
    alerts.extend(check_thresholds(hum_stats, {"min": 20, "max": 95, "variable": "humedad"}))
    alerts.extend(check_thresholds(soil_stats, {"min": 25, "max": 90, "variable": "humedad_suelo"}))
    alerts.extend(check_thresholds(light_stats, {"min": 100, "max": 100000, "variable": "luz"}))
    alerts.extend(check_thresholds(vib_stats, {"min": 1.0, "max": 1.060, "variable": "vibracion"}))
    
    correlations = []
    
    if len(temp_values) == len(hum_values) and len(temp_values) >= 3:
        corr = calculate_pearson_correlation(temp_values, hum_values)
        if corr is not None:
            correlations.append({
                "variables": ["temperatura", "humedad"],
                "coefficient": corr,
                "strength": "fuerte" if abs(corr) > 0.7 else ("moderada" if abs(corr) > 0.4 else "debil"),
                "type": "positiva" if corr > 0 else "negativa"
            })
    
    if len(temp_values) == len(pres_values) and len(temp_values) >= 3:
        corr = calculate_pearson_correlation(temp_values, pres_values)
        if corr is not None:
            correlations.append({
                "variables": ["temperatura", "presion"],
                "coefficient": corr,
                "strength": "fuerte" if abs(corr) > 0.7 else ("moderada" if abs(corr) > 0.4 else "debil"),
                "type": "positiva" if corr > 0 else "negativa"
            })
    
    if len(hum_values) == len(soil_values) and len(hum_values) >= 3:
        corr = calculate_pearson_correlation(hum_values, soil_values)
        if corr is not None:
            correlations.append({
                "variables": ["humedad_aire", "humedad_suelo"],
                "coefficient": corr,
                "strength": "fuerte" if abs(corr) > 0.7 else ("moderada" if abs(corr) > 0.4 else "debil"),
                "type": "positiva" if corr > 0 else "negativa"
            })
    
    radar_data = {
        "labels": ["Temperatura", "Presion", "Humedad Aire", "Luz", "Humedad Suelo", "Vibracion"],
        "values": [
            float(temp_stats.get("stability", {}).get("stability_index", 100)) if temp_stats else 100,
            float(pres_stats.get("stability", {}).get("stability_index", 100)) if pres_stats else 100,
            float(hum_stats.get("stability", {}).get("stability_index", 100)) if hum_stats else 100,
            float(light_stats.get("stability", {}).get("stability_index", 100)) if light_stats else 100,
            float(soil_stats.get("stability", {}).get("stability_index", 100)) if soil_stats else 100,
            float(vib_stats.get("stability", {}).get("stability_index", 100)) if vib_stats else 100
        ]
    }
    
    analysis_stability = {
        "overall": calculate_stability_index(temp_values),
        "radar": radar_data,
        "details": {
            "temp": temp_stats.get("stability") if temp_stats else None,
            "pres": pres_stats.get("stability") if pres_stats else None
        }
    }
    
    soil_status = calculate_soil_status(
        soil_stats["avg"] if soil_stats else None,
        soil_stats["trend"]["direction"] if soil_stats else "sin_datos"
    )
    
    pressure_forecast = calculate_pressure_forecast(
        pres_stats["avg"] if pres_stats else None,
        pres_stats["trend"] if pres_stats else {}
    )
    
    data_quality = calculate_data_quality(readings)
    
    time_range_start = min(timestamps).strftime("%H:%M") if timestamps else None
    time_range_end = max(timestamps).strftime("%H:%M") if timestamps else None
    
    if timestamps and len(timestamps) >= 2:
        duration_minutes = int((max(timestamps) - min(timestamps)).total_seconds() / 60)
        duration_str = f"{duration_minutes // 60}h {duration_minutes % 60}m"
    else:
        duration_str = "0h 0m"
    
    total_alerts = len(alerts)
    critical_alerts = len([a for a in alerts if a.get("severity") == "alta"])
    
    if critical_alerts > 0:
        general_condition = "critico"
    elif total_alerts > 2:
        general_condition = "alerta"
    elif total_alerts > 0:
        general_condition = "variable"
    elif data_quality["reliability"] == "alta":
        general_condition = "optimo"
    else:
        general_condition = "estable"
    
    analysis = {
        "scatter_plot_img": generate_scatter_plot_img(readings),
        "plotly_scatter_data": generate_plotly_data(readings),
        "metadata": {
            "generated_at": now.isoformat(),
            "date": now.strftime("%Y-%m-%d"),
            "time_range": {
                "start": time_range_start,
                "end": time_range_end,
                "duration": duration_str
            },
            "total_readings": len(readings)
        },
        "general_condition": general_condition,
        "environmental_stability": analysis_stability,
        "variables": {
            "temperatura": temp_stats,
            "presion": pres_stats,
            "humedad": hum_stats,
            "humedad_suelo": soil_stats,
            "luz": light_stats,
            "vibracion": vib_stats
        },
        "derived_analysis": {
            "soil_status": soil_status,
            "pressure_forecast": pressure_forecast
        },
        "correlations": correlations,
        "alerts": alerts,
        "alerts_summary": {
            "total": total_alerts,
            "critical": critical_alerts,
            "has_critical": critical_alerts > 0
        },
        "data_quality": data_quality
    }
    
    return analysis
