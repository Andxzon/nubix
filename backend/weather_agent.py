import os
import json
from datetime import date, datetime, timedelta
import openai
from flask import Flask, jsonify, request
from flask_cors import CORS
from dotenv import load_dotenv
import schedule
import time
import threading
from pathlib import Path
from .database import (
    get_readings_for_period, 
    save_report, 
    clear_old_readings,
    init_database,
    get_latest_report
)

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / '.env')

app = Flask(__name__)
CORS(app)

def format_readings_for_llm(readings: list) -> str:
    if not readings:
        return ""
    
    output_lines = []
    for reading in readings:
        ts = reading['timestamp']
        if isinstance(ts, datetime):
            ts_str = ts.strftime('%Y-%m-%dT%H:%M:%S-05:00')
        else:
            ts_str = str(ts)
        
        line = f"{ts_str}:\n"
        if reading.get('temperatura') is not None:
            line += f"  Temperatura: {reading['temperatura']} °C\n"
        if reading.get('presion') is not None:
            line += f"  Presión: {reading['presion']} hPa\n"
        if reading.get('humedad') is not None:
            line += f"  Humedad: {reading['humedad']} %\n"
        if reading.get('humedad_suelo') is not None:
            line += f"  Humedad suelo: {reading['humedad_suelo']} %\n"
        if reading.get('luz') is not None:
            line += f"  Luz: {reading['luz']} lux\n"
        if reading.get('vibracion') is not None:
            line += f"  Vibración: {reading['vibracion']} Hz\n"
        output_lines.append(line)
    
    return '\n'.join(output_lines)

def analyze_data_with_llm(data: str) -> dict | None:
    print("Enviando datos al LLM para análisis...")
    
    system_prompt = '''Eres un meteorólogo experto y científico de datos ambientales con 20 años de experiencia.
Tu rol es analizar datos de sensores IoT y generar informes profesionales, detallados y accionables.

Características de tu análisis:
- Eres preciso con los cálculos estadísticos
- Identificas patrones y correlaciones entre variables
- Detectas anomalías y explicas sus posibles causas
- Proporcionas recomendaciones prácticas basadas en los datos
- Tu lenguaje es técnico pero accesible
- Consideras el contexto agrícola/ambiental de los sensores

Siempre respondes en JSON válido, sin markdown ni texto adicional.'''

    prompt = f'''Analiza exhaustivamente los siguientes datos de sensores IoT recopilados en las últimas horas.

## DATOS DE SENSORES
{data}

## INSTRUCCIONES DE ANÁLISIS

Genera un informe JSON completo con la siguiente estructura:

{{
    "fecha": "YYYY-MM-DD",
    "hora_inicio": "HH:MM",
    "hora_fin": "HH:MM", 
    "duracion_monitoreo": "X horas Y minutos",
    "total_lecturas": número,
    
    "resumen_ejecutivo": "Párrafo de 3-4 oraciones describiendo las condiciones generales del período, destacando lo más relevante y cualquier situación que requiera atención.",
    
    "condicion_general": "Una de: Óptimo | Estable | Variable | Alerta | Crítico",
    
    "indice_confort": {{
        "valor": número del 1-100,
        "descripcion": "Interpretación del índice basado en temperatura y humedad"
    }},
    
    "variables": {{
        "temperatura": {{
            "promedio": número,
            "max": número,
            "min": número,
            "amplitud_termica": número,
            "tendencia": "en aumento | en descenso | estable | oscilante",
            "interpretacion": "Análisis breve de las condiciones térmicas"
        }},
        "presion": {{
            "promedio": número,
            "max": número,
            "min": número,
            "variacion": número,
            "tendencia": "en aumento | en descenso | estable",
            "pronostico": "Qué indica la presión sobre el clima próximo"
        }},
        "humedad_relativa": {{
            "promedio": número,
            "max": número,
            "min": número,
            "tendencia": "en aumento | en descenso | estable",
            "riesgo_rocio": "alto | medio | bajo | nulo",
            "interpretacion": "Análisis de las condiciones de humedad"
        }},
        "luminosidad": {{
            "promedio": número,
            "max": número,
            "min": número,
            "horas_luz_optima": "Estimación de horas con luz adecuada",
            "tendencia": "Descripción del ciclo lumínico observado"
        }},
        "humedad_suelo": {{
            "promedio": número,
            "max": número,
            "min": número,
            "tendencia": "en aumento | en descenso | estable | errática",
            "estado": "saturado | óptimo | seco | muy seco",
            "necesita_riego": true/false,
            "interpretacion": "Análisis del estado hídrico del suelo"
        }},
        "vibracion": {{
            "promedio": número o null,
            "max": número o null,
            "eventos_detectados": número,
            "interpretacion": "Análisis de actividad vibratoria si hay datos"
        }}
    }},
    
    "correlaciones": [
        "Descripción de relaciones observadas entre variables (ej: 'La temperatura y humedad muestran correlación inversa típica')"
    ],
    
    "anomalias": [
        {{
            "hora": "HH:MM",
            "tipo": "tipo de anomalía",
            "variable": "variable afectada",
            "descripcion": "Descripción detallada",
            "severidad": "baja | media | alta",
            "posible_causa": "Explicación probable"
        }}
    ],
    
    "alertas": [
        {{
            "tipo": "tipo de alerta",
            "mensaje": "Descripción de la alerta",
            "accion_recomendada": "Qué hacer al respecto"
        }}
    ],
    
    "recomendaciones": [
        "Recomendación práctica 1 basada en los datos",
        "Recomendación práctica 2",
        "Recomendación práctica 3"
    ],
    
    "observaciones": "Interpretación final profesional de 2-3 párrafos sobre las condiciones generales, tendencias observadas, y pronóstico a corto plazo basado en los patrones detectados.",
    
    "calidad_datos": {{
        "completitud": "porcentaje estimado de datos válidos",
        "sensores_problematicos": ["lista de sensores con lecturas sospechosas si los hay"],
        "confiabilidad": "alta | media | baja"
    }}
}}

IMPORTANTE: 
- Calcula los valores estadísticos con precisión
- Si un sensor no tiene datos, usa null y menciónalo
- Identifica al menos 2-3 correlaciones si existen patrones
- Sé específico con las horas cuando menciones eventos
- Las recomendaciones deben ser accionables y prácticas'''

    try:
        print("Enviando solicitud a la API de OpenAI...")
        client = openai.OpenAI()
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=4000
        )
        analysis_json = response.choices[0].message.content
        
        if not analysis_json:
            print("Error: La API devolvió una respuesta vacía")
            return None
        
        analysis_json = analysis_json.strip()
        if analysis_json.startswith("```json"):
            analysis_json = analysis_json[7:]
        if analysis_json.startswith("```"):
            analysis_json = analysis_json[3:]
        if analysis_json.endswith("```"):
            analysis_json = analysis_json[:-3]
        analysis_json = analysis_json.strip()
        
        return json.loads(analysis_json)
    except json.JSONDecodeError as e:
        print(f"Error parseando JSON: {e}")
        print(f"Respuesta recibida: {analysis_json[:200] if analysis_json else 'vacía'}...")
        return None
    except Exception as e:
        print(f"Error al contactar o procesar la respuesta del LLM: {e}")
        return None

def run_report_generation():
    print("\n--- Iniciando generación de informe programada ---")
    
    readings = get_readings_for_period(24)
    
    if not readings:
        print("Error: No se pudieron obtener lecturas de la base de datos.")
        return None
    
    history_data = format_readings_for_llm(readings)
    
    if not history_data:
        print("Error: No hay datos para analizar.")
        return None

    analysis_result = analyze_data_with_llm(history_data)
    
    if not analysis_result:
        print("Error: No se pudo obtener el análisis del LLM.")
        return None

    utc_minus_5 = datetime.utcnow() + timedelta(hours=-5)
    analysis_result['fecha'] = utc_minus_5.strftime('%Y-%m-%d')
    
    save_report(analysis_result)
    
    print("--- Generación de informe programada completada. ---")
    return analysis_result

def run_scheduler():
    print("Iniciando el programador de tareas...")
    while True:
        schedule.run_pending()
        time.sleep(60)

@app.route('/generate-report', methods=['POST'])
def handle_generate_report():
    print("\n--- Petición recibida en /generate-report ---")
    analysis_result = run_report_generation()
    
    if analysis_result:
        print("--- Proceso completado. Enviando informe al frontend. ---")
        return jsonify(analysis_result)
    else:
        return jsonify({"error": "No se pudo generar el informe."}), 500

@app.route('/latest-report', methods=['GET'])
def handle_latest_report():
    report = get_latest_report()
    if report:
        if 'created_at' in report and report['created_at']:
            report['created_at'] = report['created_at'].isoformat()
        if 'fecha' in report and report['fecha']:
            report['fecha'] = str(report['fecha'])
        return jsonify(report)
    return jsonify({"error": "No hay reportes disponibles."}), 404

schedule.every().day.at("23:30").do(run_report_generation)
schedule.every().day.at("00:00").do(clear_old_readings, 7)

if __name__ == '__main__':
    print("Inicializando base de datos...")
    init_database()
    
    print("Tareas programadas:")
    print("  - 23:30 → Generar reporte con IA")
    print("  - 00:00 → Limpiar lecturas antiguas (>7 días)")

    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()

    print("Iniciando servidor Flask en http://127.0.0.1:5000")
    print("Presiona CTRL+C para detener el servidor.")
    app.run(host='0.0.0.0', port=5000, debug=False)
