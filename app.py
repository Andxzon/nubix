import os
import sys
import json
import time
import threading
import ssl
from datetime import datetime, timezone, timedelta
from pathlib import Path

import openai
import paho.mqtt.client as mqtt
from flask import Flask, jsonify, send_from_directory, send_file
from flask_cors import CORS
from flask_socketio import SocketIO, emit
from dotenv import load_dotenv
import schedule
import mysql.connector
from mysql.connector import Error

# Cargar variables de entorno
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / '.env')

# ==================== CONFIGURACIÓN ====================

# MySQL
DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': int(os.getenv('DB_PORT', 3306)),
    'user': os.getenv('DB_USER', 'root'),
    'password': os.getenv('DB_PASSWORD', ''),
    'database': os.getenv('DB_NAME', 'iot_clima')
}

# MQTT
MQTT_HOST = os.getenv('MQTT_HOST', 'broker.emqx.io')
MQTT_PORT = int(os.getenv('MQTT_PORT', 8084))
MQTT_USER = os.getenv('MQTT_USER')
MQTT_PASSWORD = os.getenv('MQTT_PASSWORD')

# Sensores
SENSORS = [
    {'id': 'tempChart',  'label': 'Temperatura',   'unit': '°C',  'topic': 'clima/temperatura'},
    {'id': 'presChart',  'label': 'Presión',       'unit': 'hPa', 'topic': 'clima/presion'},
    {'id': 'humChart',   'label': 'Humedad',       'unit': '%',   'topic': 'clima/humedad'},
    {'id': 'soilChart',  'label': 'Humedad suelo', 'unit': '%',   'topic': 'clima/humedad_suelo'},
    {'id': 'lightChart', 'label': 'Luz',           'unit': 'lux', 'topic': 'clima/lux'},
    {'id': 'vibrChart',  'label': 'Vibración',     'unit': 'Hz',  'topic': 'clima/vibracion'}
]

# ==================== FLASK APP ====================

app = Flask(__name__)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# ==================== DATABASE ====================

def get_connection():
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        return conn
    except Error as e:
        print(f"Error conectando a MySQL: {e}")
        return None

def init_database():
    try:
        config_without_db = {k: v for k, v in DB_CONFIG.items() if k != 'database'}
        conn = mysql.connector.connect(**config_without_db)
        cursor = conn.cursor()
        
        cursor.execute(f"CREATE DATABASE IF NOT EXISTS {DB_CONFIG['database']}")
        cursor.execute(f"USE {DB_CONFIG['database']}")
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sensor_readings (
                id INT AUTO_INCREMENT PRIMARY KEY,
                timestamp DATETIME NOT NULL,
                temperatura DECIMAL(5,2),
                presion DECIMAL(7,2),
                humedad DECIMAL(5,2),
                humedad_suelo DECIMAL(5,2),
                luz DECIMAL(10,2),
                vibracion DECIMAL(10,2),
                INDEX idx_timestamp (timestamp)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS reports (
                id INT AUTO_INCREMENT PRIMARY KEY,
                fecha DATE NOT NULL UNIQUE,
                condicion_general VARCHAR(100),
                full_report JSON,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.commit()
        cursor.close()
        conn.close()
        print("✅ Base de datos inicializada correctamente")
        return True
    except Error as e:
        print(f"Error inicializando base de datos: {e}")
        return False

def save_sensor_reading(timestamp, readings: dict):
    conn = get_connection()
    if not conn:
        return False
    try:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO sensor_readings 
            (timestamp, temperatura, presion, humedad, humedad_suelo, luz, vibracion)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        ''', (
            timestamp,
            readings.get('Temperatura'),
            readings.get('Presión'),
            readings.get('Humedad'),
            readings.get('Humedad suelo'),
            readings.get('Luz'),
            readings.get('Vibración')
        ))
        conn.commit()
        cursor.close()
        conn.close()
        return True
    except Error as e:
        print(f"Error guardando lectura: {e}")
        return False

def get_readings_for_period(hours: int = 24) -> list:
    conn = get_connection()
    if not conn:
        return []
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute('''
            SELECT * FROM sensor_readings 
            WHERE timestamp >= DATE_SUB(NOW(), INTERVAL %s HOUR)
            ORDER BY timestamp ASC
        ''', (hours,))
        results = cursor.fetchall()
        cursor.close()
        conn.close()
        return results
    except Error as e:
        print(f"Error obteniendo lecturas: {e}")
        return []

def clear_old_readings(days: int = 7):
    conn = get_connection()
    if not conn:
        return False
    try:
        cursor = conn.cursor()
        cursor.execute('''
            DELETE FROM sensor_readings 
            WHERE timestamp < DATE_SUB(NOW(), INTERVAL %s DAY)
        ''', (days,))
        deleted = cursor.rowcount
        conn.commit()
        cursor.close()
        conn.close()
        print(f"✅ {deleted} lecturas antiguas eliminadas")
        return True
    except Error as e:
        print(f"Error limpiando lecturas: {e}")
        return False

def save_report(report_data: dict):
    conn = get_connection()
    if not conn:
        return False
    try:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO reports 
            (fecha, condicion_general, full_report)
            VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE
                condicion_general = VALUES(condicion_general),
                full_report = VALUES(full_report),
                created_at = CURRENT_TIMESTAMP
        ''', (
            report_data.get('fecha'),
            report_data.get('condicion_general'),
            json.dumps(report_data, ensure_ascii=False)
        ))
        conn.commit()
        cursor.close()
        conn.close()
        print(f"✅ Reporte guardado para {report_data.get('fecha')}")
        return True
    except Error as e:
        print(f"Error guardando reporte: {e}")
        return False

def get_latest_report() -> dict | None:
    conn = get_connection()
    if not conn:
        return None
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute('SELECT * FROM reports ORDER BY fecha DESC LIMIT 1')
        result = cursor.fetchone()
        cursor.close()
        conn.close()
        if result and result.get('full_report'):
            return json.loads(result['full_report'])
        return result
    except Error as e:
        print(f"Error obteniendo último reporte: {e}")
        return None

# ==================== MQTT LOGGER ====================

last_values = {}
new_data_received = False

def get_timestamp_gmt_minus_5():
    tz = timezone(timedelta(hours=-5))
    return datetime.now(tz)

def on_connect(client, userdata, flags, rc, properties=None):
    print("✅ Conectado al broker MQTT para logging")
    for sensor in SENSORS:
        client.subscribe(sensor['topic'])

def on_message(client, userdata, msg):
    global new_data_received
    try:
        value = float(msg.payload.decode())
        sensor = next((s for s in SENSORS if s['topic'] == msg.topic), None)
        if sensor:
            last_values[sensor['label']] = value
            new_data_received = True
            
            # Emitir a todos los clientes WebSocket conectados
            socketio.emit('sensor_data', {
                'topic': msg.topic,
                'sensor_id': sensor['id'],
                'label': sensor['label'],
                'value': value,
                'unit': sensor['unit'],
                'timestamp': int(time.time() * 1000)
            })
    except ValueError:
        pass

def save_mqtt_data():
    global new_data_received, last_values
    
    if not new_data_received:
        return
    
    timestamp = get_timestamp_gmt_minus_5()
    
    readings = {}
    for sensor in SENSORS:
        value = last_values.get(sensor['label'])
        if value is not None:
            readings[sensor['label']] = value
    
    if readings:
        if save_sensor_reading(timestamp, readings):
            print(f"Datos guardados en MySQL: {timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
    
    new_data_received = False
    last_values = {}

def run_mqtt_logger():
    print("Iniciando logger MQTT...")
    
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, transport="websockets")
    client.on_connect = on_connect
    client.on_message = on_message
    
    if MQTT_USER and MQTT_PASSWORD:
        client.username_pw_set(MQTT_USER, MQTT_PASSWORD)
    
    client.tls_set(tls_version=ssl.PROTOCOL_TLS)
    
    try:
        client.connect(MQTT_HOST, MQTT_PORT, 60)
        client.loop_start()
        
        print("Logger MQTT iniciado. Guardando datos cada 10 segundos")
        
        while True:
            time.sleep(10)
            save_mqtt_data()
    except Exception as e:
        print(f"Error en MQTT logger: {e}")

# ==================== LLM ANALYSIS ====================

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
        "Descripción de relaciones observadas entre variables"
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
        return None
    except Exception as e:
        print(f"Error al contactar o procesar la respuesta del LLM: {e}")
        return None

def run_report_generation():
    print("\n--- Iniciando generación de informe ---")
    
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
    
    print("--- Generación de informe completada ---")
    return analysis_result

# ==================== SCHEDULER ====================

def run_scheduler():
    print("Iniciando el programador de tareas...")
    schedule.every().day.at("23:30").do(run_report_generation)
    schedule.every().day.at("00:00").do(clear_old_readings, 7)
    
    while True:
        schedule.run_pending()
        time.sleep(60)

# ==================== FLASK ROUTES ====================

@app.route('/')
def index():
    return send_file('index.html')

@app.route('/report.html')
def report_page():
    return send_file('report.html')

@app.route('/css/<path:filename>')
def serve_css(filename):
    return send_from_directory('css', filename)

@app.route('/js/<path:filename>')
def serve_js(filename):
    return send_from_directory('js', filename)

@app.route('/images/<path:filename>')
def serve_images(filename):
    return send_from_directory('images', filename)

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
            report['created_at'] = report['created_at'].isoformat() if hasattr(report['created_at'], 'isoformat') else str(report['created_at'])
        if 'fecha' in report and report['fecha']:
            report['fecha'] = str(report['fecha'])
        return jsonify(report)
    return jsonify({"error": "No hay reportes disponibles."}), 404

# ==================== MAIN ====================

def start_background_services():
    """Inicia los servicios en segundo plano"""
    # Logger MQTT
    mqtt_thread = threading.Thread(target=run_mqtt_logger, daemon=True)
    mqtt_thread.start()
    
    # Scheduler
    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()
    
    print("✅ Servicios en segundo plano iniciados")

if __name__ == '__main__':
    print("=" * 50)
    print("Iniciando IoT Backend...")
    print("=" * 50)
    
    # Inicializar base de datos
    init_database()
    
    # Iniciar servicios en segundo plano
    start_background_services()
    
    # Esperar un momento para que se conecte MQTT
    time.sleep(2)
    
    # Iniciar Flask con SocketIO
    print("Iniciando servidor Flask + WebSocket en http://0.0.0.0:5000")
    socketio.run(app, host='0.0.0.0', port=5000, debug=False, allow_unsafe_werkzeug=True)
