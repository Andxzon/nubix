import os
import sys
import json
import time
import threading
import ssl
from datetime import datetime, timezone, timedelta
from pathlib import Path

import secrets
import openai
import paho.mqtt.client as mqtt
import urllib.request
from flask import Flask, jsonify, send_from_directory, send_file, request, make_response
from flask_cors import CORS
from flask_socketio import SocketIO, emit
from dotenv import load_dotenv
import mysql.connector
from mysql.connector import Error
from pywebpush import webpush, WebPushException
from werkzeug.security import check_password_hash, generate_password_hash

from analytics import analyze_readings

class ReportGenerationError(Exception):
    """Excepcion personalizada para errores en la generacion de informes."""
    pass


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

# MySQL Auth
DB_AUTH_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': int(os.getenv('DB_PORT', 3306)),
    'user': os.getenv('DB_USER', 'root'),
    'password': os.getenv('DB_PASSWORD', ''),
    'database': os.getenv('DB_NAME_AUTH', 'accounts')
}

# MQTT
MQTT_HOST = os.getenv('MQTT_HOST', 'broker.emqx.io')
MQTT_PORT = int(os.getenv('MQTT_PORT', 8084))
MQTT_USER = os.getenv('MQTT_USER')
MQTT_PASSWORD = os.getenv('MQTT_PASSWORD')

# Web Push VAPID
VAPID_PUBLIC_KEY = os.getenv('VAPID_PUBLIC_KEY', '')
VAPID_PRIVATE_KEY = os.getenv('VAPID_PRIVATE_KEY', '')
VAPID_CLAIMS = {"sub": "mailto:admin@example.com"}

# Cloudflare Turnstile
TURNSTILE_SECRET_KEY = os.getenv('TURNSTILE_SECRET_KEY', '1x0000000000000000000000000000000AA')

# Configuración de sesiones
SESSION_DURATION_HOURS = 8
SESSION_COOKIE_NAME    = 'miot_sid'
IS_PRODUCTION = os.getenv('RENDER', '') != '' or os.getenv('FLASK_ENV', '') == 'production'

# Rate limiting: intentos fallidos antes de bloqueo y duración del bloqueo
MAX_FAILED_ATTEMPTS = 3
LOCKOUT_MINUTES     = 5

# Almacén en memoria de suscripciones push (en producción usa base de datos)
push_subscriptions = {}

# Sensores
SENSORS = [
    {'id': 'tempChart',  'label': 'Temperatura',   'unit': '°C',  'topic': 'clima/temperatura'},
    {'id': 'presChart',  'label': 'Presión',       'unit': 'hPa', 'topic': 'clima/presion'},
    {'id': 'humChart',   'label': 'Humedad',       'unit': '%',   'topic': 'clima/humedad'},
    {'id': 'soilChart',  'label': 'Humedad suelo', 'unit': '%',   'topic': 'clima/humedad_suelo'},
    {'id': 'lightChart', 'label': 'Luz',           'unit': 'lux', 'topic': 'clima/lux'},
    {'id': 'vibrChart',  'label': 'Vibración',     'unit': 'g',  'topic': 'clima/vibracion'}
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

def get_auth_connection():
    try:
        conn = mysql.connector.connect(**DB_AUTH_CONFIG)
        return conn
    except Error as e:
        print(f"Error conectando a MySQL Auth: {e}")
        return None

def init_database():
    # Inicializar tablas de seguridad (sesiones y rate limit)
    init_auth_database()
    
    try:
        config_without_db = {k: v for k, v in DB_CONFIG.items() if k != 'database'}
        conn = mysql.connector.connect(**config_without_db)
        cursor = conn.cursor()
        
        cursor.execute(f"CREATE DATABASE IF NOT EXISTS {DB_CONFIG['database']}")
        cursor.execute(f"USE {DB_CONFIG['database']}")
        
        # Verificar si necesitamos migrar el schema (tabla reports antigua)
        cursor.execute("SHOW TABLES LIKE 'reports'")
        reports_exists = cursor.fetchone() is not None
        
        if reports_exists:
            # Verificar si tiene el schema nuevo (columna analysis_json)
            cursor.execute("SHOW COLUMNS FROM reports LIKE 'analysis_json'")
            has_new_schema = cursor.fetchone() is not None
            
            if not has_new_schema:
                print(" Detectado schema antiguo. Migrando tablas...")
                cursor.execute("DROP TABLE IF EXISTS reports_ia")
                cursor.execute("DROP TABLE IF EXISTS reports")
                print("   Tablas antiguas eliminadas. Creando nuevas...")
        
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
        
        # Tabla reports: Solo análisis estadístico del backend (sin IA)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS reports (
                id INT AUTO_INCREMENT PRIMARY KEY,
                fecha DATE NOT NULL,
                time_range_start TIME,
                time_range_end TIME,
                duration_minutes INT,
                total_readings INT NOT NULL,
                condicion_general VARCHAR(50) NOT NULL,
                
                -- Métricas clave (calculadas por backend)
                temp_avg DECIMAL(5,2),
                temp_min DECIMAL(5,2),
                temp_max DECIMAL(5,2),
                humidity_avg DECIMAL(5,2),
                pressure_avg DECIMAL(7,2),
                soil_humidity_avg DECIMAL(5,2),
                light_avg DECIMAL(10,2),
                comfort_index INT,
                
                -- Alertas
                total_alerts INT DEFAULT 0,
                critical_alerts INT DEFAULT 0,
                
                -- Calidad de datos
                data_quality_score DECIMAL(5,2),
                data_reliability VARCHAR(20),
                
                -- JSON completo del análisis backend
                analysis_json JSON NOT NULL,
                
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                
                INDEX idx_fecha (fecha),
                INDEX idx_condicion (condicion_general)
            )
        ''')
        
        # Tabla reports_ia: Reporte final procesado y mejorado por IA
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS reports_ia (
                id INT AUTO_INCREMENT PRIMARY KEY,
                report_id INT NOT NULL,
                fecha DATE NOT NULL,
                
                -- Textos generados por IA
                executive_summary TEXT NOT NULL,
                interpretation TEXT,
                recommendations JSON,
                observations TEXT,
                alert_explanations JSON,
                correlation_insights JSON,
                
                -- Metadatos IA
                llm_model VARCHAR(50) NOT NULL,
                llm_tokens_used INT,
                llm_response_time_ms INT,
                
                -- JSON completo de respuesta IA
                full_response JSON NOT NULL,
                
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                
                INDEX idx_fecha (fecha),
                INDEX idx_report_id (report_id),
                FOREIGN KEY (report_id) REFERENCES reports(id) ON DELETE CASCADE
            )
        ''')
        
        # Actualización de schema para weather_status
        cursor.execute("SHOW COLUMNS FROM reports_ia LIKE 'weather_status'")
        if not cursor.fetchone():
            print("   Actualizando tabla reports_ia (agregando weather_status)...")
            cursor.execute("ALTER TABLE reports_ia ADD COLUMN weather_status VARCHAR(100) AFTER fecha")

        conn.commit()

        cursor.close()
        conn.close()
        print("Base de datos inicializada correctamente")
        return True
    except Error as e:
        print(f"Error inicializando base de datos: {e}")
        return False

def init_auth_database():
    """
    Inicializa las tablas de seguridad en la base de datos de autenticación:
      - sessions:       sesiones persistentes con IP y país
      - login_attempts: rate limiting por IP y usuario
    """
    conn = get_auth_connection()
    if not conn:
        print("No se pudo conectar a la BD de auth para inicializar tablas de seguridad")
        return False
    try:
        cursor = conn.cursor()

        # Tabla de sesiones activas
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sessions (
                token        VARCHAR(128)  NOT NULL PRIMARY KEY,
                user_id      INT           NOT NULL,
                username     VARCHAR(100)  NOT NULL,
                email        VARCHAR(255),
                ip_address   VARCHAR(45)   NOT NULL,
                country_code VARCHAR(3),
                country_name VARCHAR(100),
                user_agent   VARCHAR(512),
                created_at   DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
                expires_at   DATETIME      NOT NULL,
                INDEX idx_user_id  (user_id),
                INDEX idx_expires  (expires_at)
            )
        ''')

        # Tabla de intentos fallidos (rate limiting)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS login_attempts (
                id              INT AUTO_INCREMENT PRIMARY KEY,
                ip_address      VARCHAR(45)  NOT NULL,
                username        VARCHAR(100) NOT NULL,
                failed_count    INT          NOT NULL DEFAULT 0,
                last_attempt_at DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
                locked_until    DATETIME,
                INDEX idx_ip_user (ip_address, username),
                INDEX idx_locked  (locked_until)
            )
        ''')

        conn.commit()
        cursor.close()
        conn.close()
        print("Tablas de seguridad (sessions, login_attempts) inicializadas correctamente")
        return True
    except Error as e:
        print(f"Error inicializando tablas de seguridad: {e}")
        return False


# ==================== GEO-IP ====================

def get_ip_geo(ip: str) -> dict:
    """
    Obtiene el país e información geográfica de una IP usando ip-api.com (gratuito, sin clave).
    Devuelve dict con country_code y country_name, o valores vacíos si falla.
    IPs locales (127.x, 192.168.x, 10.x) retornan 'LOCAL'.
    """
    # IPs privadas/locales → marcar como LOCAL
    import ipaddress
    try:
        ip_obj = ipaddress.ip_address(ip)
        if ip_obj.is_private or ip_obj.is_loopback:
            return {'country_code': 'LOCAL', 'country_name': 'Red local'}
    except ValueError:
        pass

    try:
        url = f'http://ip-api.com/json/{ip}?fields=status,country,countryCode'
        req = urllib.request.Request(url, headers={'User-Agent': 'MeteoIoT/1.0'})
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode('utf-8'))
        if data.get('status') == 'success':
            return {
                'country_code': data.get('countryCode', 'XX'),
                'country_name': data.get('country', 'Desconocido'),
            }
    except Exception as e:
        print(f"[GeoIP] Error consultando ip-api.com para {ip}: {e}")

    return {'country_code': 'XX', 'country_name': 'Desconocido'}


# ==================== SESIONES EN BASE DE DATOS ====================

def db_create_session(user: dict, ip: str, user_agent: str) -> str | None:
    """Crea una sesión en la BD y devuelve el token seguro."""
    conn = get_auth_connection()
    if not conn:
        return None
    try:
        geo          = get_ip_geo(ip)
        token        = secrets.token_hex(32)
        expires_at   = datetime.now(timezone.utc) + timedelta(hours=SESSION_DURATION_HOURS)
        expires_at_naive = expires_at.replace(tzinfo=None)  # MySQL no zone-aware por defecto

        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO sessions
              (token, user_id, username, email, ip_address,
               country_code, country_name, user_agent, expires_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ''', (
            token,
            user['id'],
            user['username'],
            user.get('email'),
            ip,
            geo['country_code'],
            geo['country_name'],
            user_agent[:512] if user_agent else None,
            expires_at_naive
        ))
        conn.commit()
        cursor.close()
        print(f"[SESSION] Creada para '{user['username']}' — IP: {ip} — País: {geo['country_name']}")
        return token
    except Error as e:
        print(f"[SESSION] Error creando sesión: {e}")
        return None
    finally:
        conn.close()


def db_get_session(token: str, current_ip: str) -> dict | None:
    """
    Valida el token en la BD.
    Comprueba:
      1. Que el token exista y no haya expirado.
      2. Que la IP coincida con la registrada en la sesión.
      3. Que el país del token coincida con el país actual.
    Devuelve los datos del usuario o None si falla alguna verificación.
    """
    conn = get_auth_connection()
    if not conn:
        return None
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute('''
            SELECT * FROM sessions
            WHERE token = %s AND expires_at > NOW()
        ''', (token,))
        session = cursor.fetchone()
        cursor.close()

        if not session:
            return None  # token inválido o expirado

        stored_ip      = session['ip_address']
        stored_country = session['country_code']

        # ── Verificación de IP (exacta) ───────────────────────────────────
        if current_ip != stored_ip:
            current_geo     = get_ip_geo(current_ip)
            stored_geo      = {'country_code': stored_country}

            # Si el país cambió → rechazar la sesión (posible secuestro)
            if current_geo['country_code'] not in ('LOCAL', 'XX') and \
               stored_geo['country_code'] not in ('LOCAL', 'XX') and \
               current_geo['country_code'] != stored_geo['country_code']:
                print(f"[SECURITY] Sesión rechazada — cambio de país detectado "
                      f"({stored_country} → {current_geo['country_code']}) "
                      f"para usuario '{session['username']}'")
                # Invalidar sesión comprometida
                db_delete_session(token)
                return None

            # Cambio de IP dentro del mismo país → advertencia pero permitir
            print(f"[SECURITY] Cambio de IP detectado para '{session['username']}': "
                  f"{stored_ip} → {current_ip} (país: {stored_country})")

        return {
            'id':       session['user_id'],
            'username': session['username'],
            'email':    session['email'],
        }
    except Error as e:
        print(f"[SESSION] Error validando sesión: {e}")
        return None
    finally:
        conn.close()


def db_delete_session(token: str):
    """Elimina una sesión de la BD (logout o revocación por seguridad)."""
    conn = get_auth_connection()
    if not conn:
        return
    try:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM sessions WHERE token = %s', (token,))
        conn.commit()
        cursor.close()
    except Error as e:
        print(f"[SESSION] Error eliminando sesión: {e}")
    finally:
        conn.close()


def db_cleanup_expired_sessions():
    """Limpia sesiones expiradas. Llamar periódicamente (scheduler)."""
    conn = get_auth_connection()
    if not conn:
        return
    try:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM sessions WHERE expires_at <= NOW()')
        deleted = cursor.rowcount
        conn.commit()
        cursor.close()
        if deleted:
            print(f"[SESSION] {deleted} sesiones expiradas eliminadas")
    except Error:
        pass
    finally:
        conn.close()


# ==================== RATE LIMITING ====================

def check_rate_limit(ip: str, username: str) -> tuple[bool, int]:
    """
    Devuelve (bloqueado: bool, segundos_restantes: int).
    Si blocked=True el login debe rechazarse sin verificar credenciales.
    """
    conn = get_auth_connection()
    if not conn:
        return False, 0  # si no hay BD, permitir (fail-open)
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute('''
            SELECT failed_count, locked_until
            FROM   login_attempts
            WHERE  ip_address = %s AND username = %s
        ''', (ip, username.lower()))
        row = cursor.fetchone()
        cursor.close()

        if not row:
            return False, 0

        locked_until = row['locked_until']
        if locked_until:
            now = datetime.now()
            if isinstance(locked_until, datetime):
                locked_until = locked_until.replace(tzinfo=None)
            remaining = int((locked_until - now).total_seconds())
            if remaining > 0:
                return True, remaining  # ✔ bloqueado

        return False, 0
    except Error as e:
        print(f"[RATELIMIT] Error en check_rate_limit: {e}")
        return False, 0
    finally:
        conn.close()


def record_failed_attempt(ip: str, username: str):
    """Registra un intento fallido. Si supera MAX_FAILED_ATTEMPTS, bloquea."""
    conn = get_auth_connection()
    if not conn:
        return
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute('''
            SELECT id, failed_count FROM login_attempts
            WHERE ip_address = %s AND username = %s
        ''', (ip, username.lower()))
        row = cursor.fetchone()

        now = datetime.now()
        if row:
            new_count = row['failed_count'] + 1
            locked_until = None
            if new_count >= MAX_FAILED_ATTEMPTS:
                locked_until = now + timedelta(minutes=LOCKOUT_MINUTES)
                print(f"[RATELIMIT] IP {ip} bloqueada por {LOCKOUT_MINUTES} min "
                      f"(usuario: '{username}', intentos: {new_count})")
            cursor.execute('''
                UPDATE login_attempts
                SET failed_count = %s, last_attempt_at = %s, locked_until = %s
                WHERE id = %s
            ''', (new_count, now, locked_until, row['id']))
        else:
            cursor.execute('''
                INSERT INTO login_attempts
                  (ip_address, username, failed_count, last_attempt_at)
                VALUES (%s, %s, 1, %s)
            ''', (ip, username.lower(), now))

        conn.commit()
        cursor.close()
    except Error as e:
        print(f"[RATELIMIT] Error registrando intento fallido: {e}")
    finally:
        conn.close()


def clear_failed_attempts(ip: str, username: str):
    """Limpia los intentos fallidos tras un login exitoso."""
    conn = get_auth_connection()
    if not conn:
        return
    try:
        cursor = conn.cursor()
        cursor.execute('''
            DELETE FROM login_attempts
            WHERE ip_address = %s AND username = %s
        ''', (ip, username.lower()))
        conn.commit()
        cursor.close()
    except Error:
        pass
    finally:
        conn.close()


def save_sensor_reading(timestamp, readings: dict):
    conn = get_connection()
    if not conn:
        return False
    cursor = None
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
        return True
    except Error as e:
        print(f"Error guardando lectura: {e}")
        return False
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

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

def get_readings_sample_for_range(start_ts, end_ts, limit=100) -> list:
    """Obtiene una muestra de lecturas para un rango de tiempo específico."""
    conn = get_connection()
    if not conn: return []
    try:
        cursor = conn.cursor(dictionary=True)
        # Downsample usando OFFSET o simplemente LIMIT si son pocas
        cursor.execute('''
            SELECT temperatura, humedad, presion, timestamp 
            FROM sensor_readings 
            WHERE timestamp BETWEEN %s AND %s
            ORDER BY id DESC LIMIT %s
        ''', (start_ts, end_ts, limit))
        samples = cursor.fetchall()
        
        return [
            {
                "x": float(s["temperatura"]) if s["temperatura"] is not None else 0, 
                "y": float(s["humedad"]) if s["humedad"] is not None else 0, 
                "p": float(s["presion"]) if s["presion"] is not None else 0, 
                "t": s["timestamp"].strftime("%H:%M:%S") if s["timestamp"] else ""
            }
            for s in samples if s["temperatura"] is not None and s["humedad"] is not None
        ]
    except Exception as e:
        print(f"Error en get_readings_sample: {e}")
        return []
    finally:
        if conn: conn.close()

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
        print(f"{deleted} lecturas antiguas eliminadas")
        return True
    except Error as e:
        print(f"Error limpiando lecturas: {e}")
        return False

def clear_yesterday_readings():
    """Elimina las lecturas del día anterior (para ejecutar a las 00:00)"""
    conn = get_connection()
    if not conn:
        return False
    try:
        cursor = conn.cursor()
        cursor.execute('''
            DELETE FROM sensor_readings 
            WHERE DATE(timestamp) = DATE_SUB(CURDATE(), INTERVAL 1 DAY)
        ''')
        deleted = cursor.rowcount
        conn.commit()
        cursor.close()
        conn.close()
        print(f"{deleted} lecturas del da anterior eliminadas")
        return True
    except Error as e:
        print(f"Error limpiando lecturas del da anterior: {e}")
        return False

def save_backend_report(backend_analysis: dict) -> int | None:
    """
    Guarda el análisis del backend en la tabla reports.
    
    Args:
        backend_analysis: JSON del análisis estadístico del backend
        
    Returns:
        ID del reporte insertado o None si falla
    """
    conn = get_connection()
    if not conn:
        return None
    cursor = None
    try:
        cursor = conn.cursor()
        
        metadata = backend_analysis.get("metadata", {})
        time_range = metadata.get("time_range", {})
        variables = backend_analysis.get("variables", {})
        alerts_summary = backend_analysis.get("alerts_summary", {})
        data_quality = backend_analysis.get("data_quality", {})
        stability = backend_analysis.get("environmental_stability", {}).get("overall", {})

        duration_str = time_range.get("duration", "0h 0m")
        hours, mins = 0, 0
        if "h" in duration_str:
            parts = duration_str.replace("m", "").split("h")
            hours = int(parts[0].strip()) if parts[0].strip() else 0
            mins = int(parts[1].strip()) if len(parts) > 1 and parts[1].strip() else 0
        duration_minutes = hours * 60 + mins
        
        cursor.execute('''
            INSERT INTO reports (
                fecha, time_range_start, time_range_end, duration_minutes,
                total_readings, condicion_general,
                temp_avg, temp_min, temp_max, humidity_avg, pressure_avg,
                soil_humidity_avg, light_avg, comfort_index,
                total_alerts, critical_alerts,
                data_quality_score, data_reliability,
                analysis_json
            ) VALUES (
                %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s
            )
        ''', (
            metadata.get("date"),
            time_range.get("start"),
            time_range.get("end"),
            duration_minutes,
            metadata.get("total_readings", 0),
            backend_analysis.get("general_condition", "desconocido"),
            variables.get("temperatura", {}).get("avg") if variables.get("temperatura") else None,
            variables.get("temperatura", {}).get("min") if variables.get("temperatura") else None,
            variables.get("temperatura", {}).get("max") if variables.get("temperatura") else None,
            variables.get("humedad", {}).get("avg") if variables.get("humedad") else None,
            variables.get("presion", {}).get("avg") if variables.get("presion") else None,
            variables.get("humedad_suelo", {}).get("avg") if variables.get("humedad_suelo") else None,
            variables.get("luz", {}).get("avg") if variables.get("luz") else None,
            stability.get("stability_index"),
            alerts_summary.get("total", 0),
            alerts_summary.get("critical", 0),
            data_quality.get("completeness"),
            data_quality.get("reliability"),
            json.dumps(backend_analysis, ensure_ascii=False)
        ))
        
        report_id = cursor.lastrowid
        conn.commit()
        print(f"Analisis backend guardado (ID: {report_id}) para {metadata.get('date')}")
        return report_id
    except Error as e:
        print(f"Error guardando anlisis backend: {e}")
        return None
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


def save_ia_report(report_id: int, fecha: str, llm_response: dict, llm_metadata: dict) -> bool:
    """
    Guarda el reporte mejorado por IA en la tabla reports_ia.
    
    Args:
        report_id: ID del reporte backend asociado
        fecha: Fecha del reporte
        llm_response: JSON con textos interpretativos del LLM
        llm_metadata: Metadatos de la llamada al LLM
    """
    conn = get_connection()
    if not conn:
        return False
    cursor = None
    try:
        cursor = conn.cursor()
        
        executive_summary = llm_response.get("executive_summary")
        interpretation = llm_response.get("interpretation")
        observations = llm_response.get("observations")
        
        cursor.execute('''
            INSERT INTO reports_ia (
                report_id, fecha, weather_status,
                executive_summary, interpretation, recommendations, observations,
                alert_explanations, correlation_insights,
                llm_model, llm_tokens_used, llm_response_time_ms,
                full_response
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
        ''', (
            report_id,
            fecha,
            llm_response.get("weather_status", "Condición Analizada"),
            executive_summary or "Análisis completado sin resumen disponible.",
            interpretation,
            json.dumps(llm_response.get("recommendations", []), ensure_ascii=False),
            observations or "Sin observaciones adicionales.",
            json.dumps(llm_response.get("alert_explanations", []), ensure_ascii=False),
            json.dumps(llm_response.get("correlation_insights", []), ensure_ascii=False),
            llm_metadata.get("model"),
            llm_metadata.get("tokens_used"),
            llm_metadata.get("response_time_ms"),
            json.dumps(llm_response, ensure_ascii=False)
        ))

        
        conn.commit()
        print(f"Reporte IA guardado para {fecha}")
        return True
    except Error as e:
        print(f"Error guardando reporte IA: {e}")
        return False
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

def transform_variable_for_frontend(var_data: dict | None, var_name: str) -> dict | None:
    """Transforma el formato de variable del backend al formato del frontend."""
    if not var_data:
        return None
    
    trend = var_data.get('trend', {})
    trend_direction = trend.get('direction', 'estable') if isinstance(trend, dict) else 'estable'
    
    trend_map = {
        'ascendente': 'en aumento',
        'descendente': 'en descenso',
        'estable': 'estable',
        'sin_datos': 'sin datos'
    }
    
    return {
        "promedio": float(var_data.get('avg')) if var_data.get('avg') is not None else 0,
        "min": float(var_data.get('min')) if var_data.get('min') is not None else 0,
        "max": float(var_data.get('max')) if var_data.get('max') is not None else 0,
        "amplitud": float(var_data.get('range')) if var_data.get('range') is not None else 0,
        "tendencia": trend_map.get(trend_direction, trend_direction),
        "desviacion": float(var_data.get('std_dev')) if var_data.get('std_dev') is not None else 0
    }



def transform_alert_for_frontend(alert: dict) -> dict:
    """Transforma alerta del backend al formato del frontend."""
    variable = alert.get('variable', 'desconocido')
    threshold = alert.get('threshold')
    actual = alert.get('actual')
    alert_type = alert.get('type')
    
    # Mensajes específicos por variable
    if variable == 'vibracion':
        dir_text = "elevada" if alert_type == 'umbral_maximo' else "anómala"
        mensaje = f"⚠️ Vibración {dir_text} detectada: {actual} g (esperado cerca a 1.0g). Posible actividad sísmica o perturbación."
        accion = "Verificar las condiciones de seguridad en el área física del sensor"
    elif variable == 'temperatura':
        if alert_type == 'umbral_maximo':
            mensaje = f"Temperatura alta: {actual}°C (máximo recomendado: {threshold}°C)"
            accion = "Considerar ventilación o protección solar"
        else:
            mensaje = f"Temperatura baja: {actual}°C (mínimo recomendado: {threshold}°C)"
            accion = "Evaluar protección contra heladas si aplica"
    elif variable == 'humedad_suelo':
        if alert_type == 'umbral_minimo':
            mensaje = f"Bajo nivel de humedad en suelo: {actual}% (umbral: {threshold}%)"
            accion = "No aplicar acciones, solo registrar dato"
        else:
            mensaje = f"Suelo con alta saturación de humedad: {actual}% (máximo: {threshold}%)"
            accion = "Monitorear drenaje natural del terreno"
    else:
        if alert_type == 'umbral_minimo':
            mensaje = f"Valor por debajo del umbral: {actual} (mínimo: {threshold})"
        else:
            mensaje = f"Valor excede el umbral: {actual} (máximo: {threshold})"
        accion = f"Revisar sensor de {variable.replace('_', ' ')}"
    
    return {
        "tipo": variable.replace('_', ' ').title(),
        "mensaje": mensaje,
        "accion_recomendada": accion,
        "severidad": alert.get('severity', 'media')
    }


def transform_correlation_for_frontend(corr: dict) -> str:
    """Transforma correlación del backend a string legible."""
    vars_str = " y ".join(corr.get('variables', []))
    strength = corr.get('strength', 'desconocida')
    corr_type = "positiva" if corr.get('type') == 'positiva' else "negativa"
    coef = corr.get('coefficient', 0)
    
    return f"Correlación {strength} {corr_type} entre {vars_str} (r={coef})"


def format_report_for_frontend(result: dict) -> dict:
    """Helper para transformar un fila de la DB en el formato del frontend."""
    backend_analysis = json.loads(result.get('analysis_json', '{}')) if result.get('analysis_json') else {}
    recommendations = json.loads(result.get('recommendations', '[]')) if result.get('recommendations') else []
    backend_alerts = backend_analysis.get('alerts', [])
    backend_correlations = backend_analysis.get('correlations', [])
    backend_variables = backend_analysis.get('variables', {})
    
    variables_frontend = {
        "temperatura": transform_variable_for_frontend(backend_variables.get('temperatura'), 'temperatura'),
        "presion": transform_variable_for_frontend(backend_variables.get('presion'), 'presion'),
        "humedad": transform_variable_for_frontend(backend_variables.get('humedad'), 'humedad'),
        "luz": transform_variable_for_frontend(backend_variables.get('luz'), 'luz'),
        "humedad_suelo": transform_variable_for_frontend(backend_variables.get('humedad_suelo'), 'humedad_suelo'),
        "vibracion": transform_variable_for_frontend(backend_variables.get('vibracion'), 'vibracion')
    }

    soil_status = backend_analysis.get('derived_analysis', {}).get('soil_status', {})
    if variables_frontend.get('humedad_suelo'):
        variables_frontend['humedad_suelo']['estado'] = soil_status.get('status', '').replace('_', ' ')
        variables_frontend['humedad_suelo']['necesita_intervencion'] = soil_status.get('needs_irrigation', False)
    
    pressure_forecast = backend_analysis.get('derived_analysis', {}).get('pressure_forecast', '')
    if variables_frontend.get('presion'):
        forecast_map = {
            'deterioro_probable': 'Posible deterioro del clima',
            'mejora_probable': 'Probable mejora del clima',
            'inestabilidad_posible': 'Posible inestabilidad atmosférica',
            'estabilidad_esperada': 'Se espera estabilidad',
            'sin_cambios_significativos': 'Sin cambios significativos'
        }
        variables_frontend['presion']['pronostico'] = forecast_map.get(pressure_forecast, '')
    
    alertas_frontend = [transform_alert_for_frontend(a) for a in backend_alerts]
    
    correlation_insights = json.loads(result.get('correlation_insights', '[]')) if result.get('correlation_insights') else []
    if correlation_insights and len(correlation_insights) > 0:
        correlaciones_frontend = correlation_insights
    else:
        correlaciones_frontend = [transform_correlation_for_frontend(c) for c in backend_correlations]
    
    condicion_map = {
        'optimo': 'Atmósfera Estable',
        'estable': 'Condición Normal',
        'variable': 'Fluctuación Atmosférica',
        'alerta': 'Inestabilidad Detectada',
        'critico': 'Anomalía Significativa'
    }

    llm_status = result.get('weather_status')
    condicion = result.get('general_condition', 'estable')
    final_condition = llm_status if llm_status else condicion_map.get(condicion, condicion.title())

    report = {
        "id": result.get('id'),
        "fecha": str(result.get('fecha')),
        "hora_inicio": str(result.get('time_range_start', '')),
        "hora_fin": str(result.get('time_range_end', '')),
        "duracion_monitoreo": f"{result.get('duration_minutes', 0) // 60}h {result.get('duration_minutes', 0) % 60}m",
        "total_lecturas": result.get('total_readings'),
        "condicion_general": final_condition,

        "resumen_ejecutivo": result.get('executive_summary'),
        "estabilidad_ambiental": backend_analysis.get('environmental_stability', {}).get('overall', {}),
        "radar_estabilidad": backend_analysis.get('environmental_stability', {}).get('radar', {}),
        "scatter_plot_img": backend_analysis.get('scatter_plot_img'),
        "plotly_scatter_data": backend_analysis.get('plotly_scatter_data'),
        "hourly_trends": backend_analysis.get('hourly_trends', {}),
        "variables": variables_frontend,
        "correlaciones": correlaciones_frontend,
        "alertas": alertas_frontend,
        "recomendaciones": recommendations,
        "observaciones": result.get('observations'),
        "interpretacion": result.get('interpretation'),
        "calidad_datos": {
            "completitud": f"{float(result.get('data_quality_score', 0))}%",
            "confiabilidad": result.get('data_reliability', '').replace('_', ' ').title() if result.get('data_reliability') else 'Desconocida',
            "sensores_problematicos": backend_analysis.get('data_quality', {}).get('problematic_sensors', [])
        },
        "metadata": {
            "llm_model": result.get('llm_model'),
            "tokens_used": result.get('llm_tokens_used'),
            "generated_at": str(result.get('created_at'))
        }
    }
    
    # Nube de puntos
    try:
        f_date = result.get('fecha')
        t_start = result.get('time_range_start')
        t_end = result.get('time_range_end')
        
        if f_date and t_start and t_end:
            start_ts = f"{str(f_date)} {str(t_start)}"
            end_ts = f"{str(f_date)} {str(t_end)}"
            report["nube_puntos"] = get_readings_sample_for_range(start_ts, end_ts)
        else:
            report["nube_puntos"] = []
    except Exception as e:
        print(f"Error cargando nube de puntos para reporte id {result.get('id')}: {e}")
        report["nube_puntos"] = []
    
    return report

def get_latest_report() -> dict | None:
    """Obtiene el último reporte completo."""
    conn = get_connection()
    if not conn: return None
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute('''
            SELECT r.*, ri.weather_status, ri.executive_summary, ri.interpretation, 
                   ri.recommendations, ri.observations, ri.alert_explanations,
                   ri.correlation_insights, ri.llm_model, ri.llm_tokens_used,
                   ri.llm_response_time_ms
            FROM reports r
            LEFT JOIN reports_ia ri ON r.id = ri.report_id
            ORDER BY r.id DESC LIMIT 1
        ''')
        result = cursor.fetchone()
        if not result: return None
        return format_report_for_frontend(result)
    finally:
        if conn: conn.close()

def get_reports_by_range(days: int | str) -> list[dict]:
    """Obtiene reportes para los últimos N días."""
    conn = get_connection()
    if not conn: return []
    try:
        cursor = conn.cursor(dictionary=True)
        query = '''
            SELECT r.*, ri.weather_status, ri.executive_summary, ri.interpretation, 
                   ri.recommendations, ri.observations, ri.alert_explanations,
                   ri.correlation_insights, ri.llm_model, ri.llm_tokens_used,
                   ri.llm_response_time_ms
            FROM reports r
            LEFT JOIN reports_ia ri ON r.id = ri.report_id
        '''
        if days != 'all':
            try:
                days_int = int(days)
                query += f" WHERE r.fecha >= DATE_SUB(CURDATE(), INTERVAL {days_int} DAY)"
            except ValueError:
                pass # Si no es un nmero, ignorar filtro
        
        query += " ORDER BY r.id DESC"
        
        cursor.execute(query)
        results = cursor.fetchall()
        return [format_report_for_frontend(r) for r in results]
    except Exception as e:
        print(f"Error en get_reports_by_range: {e}")
        return []
    finally:
        if conn: conn.close()


# ==================== MQTT LOGGER ====================

last_values = {}
new_data_received = False
data_lock = threading.Lock()

def get_timestamp_gmt_minus_5():
    tz = timezone(timedelta(hours=-5))
    return datetime.now(tz)

def on_connect(client, userdata, flags, rc, properties=None):
    print("Conectado al broker MQTT para logging")
    for sensor in SENSORS:
        client.subscribe(sensor['topic'])

def on_message(client, userdata, msg):
    global new_data_received
    try:
        value_raw = msg.payload.decode()
        try:
            value = float(value_raw)
        except ValueError:
            return

        sensor = next((s for s in SENSORS if s['topic'] == msg.topic), None)
        if sensor:
            with data_lock:
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
    except Exception as e:
        print(f"Error en MQTT on_message: {e}")


def save_mqtt_data():
    global new_data_received, last_values
    
    with data_lock:
        if not new_data_received:
            return
        # Capturar datos actuales (mantiene los últimos conocidos)
        readings_to_save = last_values.copy()
        new_data_received = False
        # YA NO LIMPIAMOS last_values = {} para mantener el estado persistente

    
    timestamp = get_timestamp_gmt_minus_5()
    
    if readings_to_save:
        if save_sensor_reading(timestamp, readings_to_save):
            print(f"Datos guardados en MySQL: {timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
        else:
            print(f"Fallo al guardar lectura en BD para {timestamp}")


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
        
        print("Logger MQTT iniciado. Guardando datos cada 1 segundos")
        
        while True:
            time.sleep(1)
            save_mqtt_data()
    except Exception as e:
        print(f"Error en MQTT logger: {e}")

# ==================== LLM ANALYSIS (OPTIMIZADO) ====================

LLM_MODEL = "gpt-4o"

def interpret_with_llm(backend_analysis: dict) -> tuple[dict | None, dict]:
    """
    Envía SOLO el JSON resumido al LLM para interpretación.
    El LLM NO recibe datos crudos ni realiza cálculos.
    
    Returns:
        tuple: (llm_response, llm_metadata)
    """
    print("Enviando anlisis al LLM para interpretacin...")
    
    llm_metadata = {
        "model": LLM_MODEL,
        "tokens_used": 0,
        "response_time_ms": 0
    }
    
    system_prompt = '''Eres un meteorólogo experto especializado en interpretación de datos ambientales IoT.

RESTRICCIONES ABSOLUTAS:
- NO puedes realizar cálculos estadísticos
- NO puedes inventar o modificar valores numéricos
- NO puedes repetir los datos que recibes
- NO uses markdown, solo JSON puro
- NO uses lenguaje vago o genérico
- NO menciones plantas, cultivos o agricultura (es una estación AMBIENTAL pura)
- NO menciones riego o sistemas de hidratación vegetal

TU ROL ES EXCLUSIVAMENTE:
1. Interpretar el significado de los análisis estadísticos ya calculados
2. Redactar textos profesionales y contextualizados
3. Generar recomendaciones prácticas y accionables
4. Explicar correlaciones y anomalías en lenguaje técnico accesible
5. Proporcionar observaciones globales sobre el período analizado

Responde SIEMPRE en JSON válido sin ningún texto adicional.'''

    # Crear copia limpia para el LLM sin la imagen base64 ni datos interactivos
    llm_analysis_data = backend_analysis.copy()
    if "scatter_plot_img" in llm_analysis_data:
        del llm_analysis_data["scatter_plot_img"]
    if "plotly_scatter_data" in llm_analysis_data:
        del llm_analysis_data["plotly_scatter_data"]
    
    # Limitar anomalías a 10 por variable para no saturar al LLM
    if "variables" in llm_analysis_data:
        for var_name, var_stats in llm_analysis_data["variables"].items():
            if var_stats and "anomalies" in var_stats:
                var_stats["anomalies"] = var_stats["anomalies"][:10]
                
    if "hourly_trends" in llm_analysis_data:
        del llm_analysis_data["hourly_trends"]

    user_prompt = f'''Analiza los siguientes resultados técnicos obtenidos por nuestra red de sensores meteorológicos:

```json
{json.dumps(llm_analysis_data, ensure_ascii=False, indent=2)}
```

## TU TAREA
Genera un informe meteorológico profesional y detallado. Escribe como un experto en ciencias de la atmósfera que explica a un técnico o analista ambiental. El backend ha generado alertas automáticas, pero tú debes darles el contexto físico adecuado, evitando el lenguaje innecesariamente alarmista.

Responde con este JSON exacto:

{{
    "weather_status": "Un título corto y profesional (ej: 'Estabilidad de Alta Presión', 'Anomalía Térmica Detectada'). Este campo reemplazará el título automático.",
    "executive_summary": "Análisis técnico detallado centrando el protagonismo en las causas físicas de las variaciones detectadas.",
    "interpretation": "Análisis predictivo profundo dividido en párrafos técnicos.",
    "recommendations": [
        "Recomendación técnica 1 con justificación física",
        "Recomendación técnica 2 con justificación física",
        "Recomendación técnica 3 con justificación física"
    ],
    "observations": "Observaciones finales sobre la calidad del aire o estabilidad del sistema.",
    "alert_explanations": ["Explicación científica rigurosa para cada alerta detectada"],
    "correlation_insights": ["Interpretación física de las correlaciones detectadas"]
}}

GUÍAS:
1. Reemplaza el lenguaje alarmista por lenguaje técnico descriptivo.
2. Da prioridad a las causas y efectos físicos por encima de los umbrales estáticos.
3. Sé el protagonista del análisis final.
4. Si no hay alertas, devuelve un array vacío en alert_explanations.
5. No inventes datos, pero interpreta ampliamente los existentes basándote en la meteorología.'''

    start_time = time.time()
    
    try:
        client = openai.OpenAI()
        response = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.4,
            max_tokens=2500
        )
        
        elapsed_ms = int((time.time() - start_time) * 1000)
        
        llm_metadata["tokens_used"] = response.usage.total_tokens if response.usage else 0
        llm_metadata["response_time_ms"] = elapsed_ms
        
        content = response.choices[0].message.content
        
        if not content:
            print("Error: La API devolvi una respuesta vaca")
            return None, llm_metadata
        
        content = content.strip()
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()
        
        llm_response = json.loads(content)
        
        print(f" LLM respondi en {elapsed_ms}ms usando {llm_metadata['tokens_used']} tokens")
        
        return llm_response, llm_metadata
        
    except json.JSONDecodeError as e:
        print(f"Error parseando respuesta JSON del LLM: {e}")
        return None, llm_metadata
    except openai.APIError as e:
        print(f"Error de API OpenAI: {e}")
        return None, llm_metadata
    except Exception as e:
        print(f"Error inesperado al contactar LLM: {e}")
        return None, llm_metadata


def run_report_generation() -> dict | None:
    """
    Flujo completo de generación de informe:
    1. Obtener lecturas de la base de datos
    2. Análisis estadístico en backend (sin IA)
    3. Interpretación con LLM (obligatorio)
    4. Persistencia en base de datos
    5. Notificación
    
    Raises:
        ReportGenerationError: Si la IA no está disponible (obligatoria)
    """
    print("\n" + "="*50)
    print("INICIANDO GENERACIN DE INFORME")
    print("="*50)
    
    # Paso 1: Obtener lecturas
    print("\n[1/5] Obteniendo lecturas de la base de datos...")
    readings = get_readings_for_period(24)
    
    if not readings:
        print(" Error: No hay lecturas disponibles")
        return None
    
    print(f"    {len(readings)} lecturas obtenidas")
    
    # Paso 2: Análisis estadístico en backend
    print("\n[2/5] Ejecutando anlisis estadstico en backend...")
    backend_analysis = analyze_readings(readings)
    
    if backend_analysis.get("error"):
        print(f" Error en anlisis backend: {backend_analysis['error']}")
        return None
    
    print(f"    Anlisis completado")
    print(f"   - Condicin general: {backend_analysis.get('general_condition')}")
    print(f"   - Alertas: {backend_analysis.get('alerts_summary', {}).get('total', 0)}")
    print(f"   - Calidad datos: {backend_analysis.get('data_quality', {}).get('reliability')}")
    
    # Paso 3: Interpretación con LLM (OBLIGATORIO)
    print("\n[3/5] Solicitando interpretacin al LLM...")
    llm_response, llm_metadata = interpret_with_llm(backend_analysis)
    
    if llm_response is None:
        error_msg = "La IA no está disponible. El sistema requiere IA para generar informes."
        print(f" FALLO CRTICO: {error_msg}")
        raise ReportGenerationError(error_msg)
    
    print(f"    Interpretacin recibida ({llm_metadata['tokens_used']} tokens)")
    
    # Paso 4: Persistencia en base de datos (2 tablas)
    print("\n[4/6] Guardando anlisis backend en tabla reports...")
    report_id = save_backend_report(backend_analysis)
    
    if not report_id:
        print(" Advertencia: No se pudo guardar el anlisis backend")
    else:
        print(f"    Anlisis backend guardado (ID: {report_id})")
    
    # Paso 5: Guardar reporte IA
    print("\n[5/6] Guardando reporte IA en tabla reports_ia...")
    fecha = backend_analysis.get("metadata", {}).get("date")
    
    if report_id:
        saved_ia = save_ia_report(report_id, fecha, llm_response, llm_metadata)
        if saved_ia:
            print("    Reporte IA guardado correctamente")
        else:
            print(" Advertencia: No se pudo guardar el reporte IA")
    else:
        print(" Omitiendo guardado de reporte IA (sin report_id)")
    
    # Paso 6: Notificación
    print("\n[6/6] Enviando notificaciones...")
    send_daily_report_notification()
    
    print("\n" + "="*50)
    print("INFORME GENERADO EXITOSAMENTE")
    print("="*50 + "\n")
    
    # Retornar el reporte en formato frontend (usar get_latest_report para consistencia)
    return get_latest_report()

# ==================== SCHEDULER ====================

def get_current_time_gmt_minus_5():
    """Obtiene la hora actual en GMT-5 (América/Bogotá)"""
    tz = timezone(timedelta(hours=-5))
    return datetime.now(tz)

def run_scheduler():
    print("Iniciando el programador de tareas (GMT-5)...")
    
    target_report_time = "23:30"
    target_cleanup_time = "00:00"
    
    last_report_date = None
    last_cleanup_date = None
    
    while True:
        now = get_current_time_gmt_minus_5()
        current_time = now.strftime("%H:%M")
        current_date = now.date()
        
        # Generar informe a las 23:30
        if current_time == target_report_time and last_report_date != current_date:
            print(f"Ejecutando generacin de informe programado ({current_time} GMT-5)")
            run_report_generation()
            last_report_date = current_date
        
        # Limpiar lecturas del día anterior a las 00:00
        if current_time == target_cleanup_time and last_cleanup_date != current_date:
            print(f"Ejecutando limpieza de lecturas del da anterior ({current_time} GMT-5)")
            clear_yesterday_readings()
            last_cleanup_date = current_date
        
        time.sleep(30)

# ==================== CLOUDFLARE TURNSTILE ====================

def verify_turnstile_token(token: str, remote_ip: str = None) -> bool:
    """
    Verifica el token de Cloudflare Turnstile contra la API de Cloudflare.
    
    Args:
        token: Token generado por el widget de Turnstile en el frontend
        remote_ip: IP del cliente (opcional, mejora la seguridad)
    
    Returns:
        True si el token es válido, False en caso contrario
    """
    try:
        payload = f"secret={TURNSTILE_SECRET_KEY}&response={token}"
        if remote_ip:
            payload += f"&remoteip={remote_ip}"
        
        payload_bytes = payload.encode('utf-8')
        
        req = urllib.request.Request(
            'https://challenges.cloudflare.com/turnstile/v0/siteverify',
            data=payload_bytes,
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
            method='POST'
        )
        
        with urllib.request.urlopen(req, timeout=5) as response:
            result = json.loads(response.read().decode('utf-8'))
            
        success = result.get('success', False)
        if not success:
            error_codes = result.get('error-codes', [])
            print(f"Turnstile verificación fallida. Códigos de error: {error_codes}")
        else:
            print(f"Turnstile verificación exitosa para IP: {remote_ip}")
            
        return success
        
    except Exception as e:
        print(f"Error al verificar Turnstile token: {e}")
        # En caso de error de red con la API de Cloudflare, decidir si bloquear o permitir
        # Para producción: return False (más seguro)
        # Para desarrollo/fallback: return True (más permisivo)
        return False  # Bloqueamos si no podemos verificar


# ==================== FLASK ROUTES ====================

@app.route('/')
@app.route('/index.html')
def index():
    return send_file('index.html')

@app.route('/report.html')
def report_page():
    return send_file('report.html')

@app.route('/login.html')
def login_page():
    return send_file('login.html')

@app.route('/admin.html')
def admin_page():
    return send_file('admin.html')

@app.route('/css/<path:filename>')
def serve_css(filename):
    return send_from_directory('css', filename)

@app.route('/js/<path:filename>')
def serve_js(filename):
    return send_from_directory('js', filename)

@app.route('/images/<path:filename>')
def serve_images(filename):
    return send_from_directory('images', filename)

@app.route('/sw.js')
def serve_sw():
    response = send_file('sw.js')
    response.headers['Content-Type'] = 'application/javascript'
    response.headers['Service-Worker-Allowed'] = '/'
    return response

@app.route('/api/login', methods=['POST'])
def login():
    data            = request.json or {}
    username        = data.get('username', '').strip()
    password        = data.get('password', '')
    turnstile_token = data.get('turnstile_token', '')
    client_ip       = request.headers.get('X-Forwarded-For', request.remote_addr).split(',')[0].strip()
    user_agent      = request.headers.get('User-Agent', '')

    if not username or not password:
        return jsonify({'error': 'Faltan credenciales'}), 400

    # ── Verificación Cloudflare Turnstile ──────────────────────────────────
    if not turnstile_token:
        return jsonify({'error': 'Se requiere completar la verificación de seguridad'}), 400
    if not verify_turnstile_token(turnstile_token, client_ip):
        return jsonify({'error': 'Verificación de seguridad fallida. Recarga la página e intenta de nuevo.'}), 403

    # ── Rate Limiting ─────────────────────────────────────────────────
    blocked, remaining = check_rate_limit(client_ip, username)
    if blocked:
        mins = remaining // 60
        secs = remaining % 60
        msg  = f'Demasiados intentos fallidos. Intenta de nuevo en {mins}m {secs}s.'
        return jsonify({'error': msg, 'locked': True, 'retry_after': remaining}), 429

    # ── Verificar credenciales en BD ─────────────────────────────────────────
    conn = get_auth_connection()
    if not conn:
        return jsonify({'error': 'Error de base de datos'}), 500

    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE username = %s OR email = %s", (username, username))
        user = cursor.fetchone()
        cursor.close()
        conn.close()

        if not user:
            record_failed_attempt(client_ip, username)
            return jsonify({'error': 'Credenciales inválidas'}), 401

        db_password = user.get('password') or user.get('password_hash')
        if not db_password:
            return jsonify({'error': 'Error en datos de usuario'}), 500

        if not check_password_hash(db_password, password):
            record_failed_attempt(client_ip, username)
            # Calcular intentos restantes
            blocked2, _ = check_rate_limit(client_ip, username)
            remaining_attempts = MAX_FAILED_ATTEMPTS - (MAX_FAILED_ATTEMPTS if blocked2 else 1)
            extra = '' if blocked2 else f' (te quedan {MAX_FAILED_ATTEMPTS - 1} intentos)'
            return jsonify({'error': f'Credenciales inválidas{extra}'}), 401

        # ── Éxito: crear sesión en BD ────────────────────────────────────────
        user_data = {
            'id':       user['id'],
            'username': user['username'],
            'email':    user.get('email'),
        }
        session_token = db_create_session(user_data, client_ip, user_agent)
        if not session_token:
            return jsonify({'error': 'No se pudo crear la sesión. Intenta de nuevo.'}), 500

        clear_failed_attempts(client_ip, username)   # resetear contador de intentos

        # Actualizar last_login
        conn2 = get_auth_connection()
        if conn2:
            try:
                cur2 = conn2.cursor()
                cur2.execute("UPDATE users SET last_login = %s WHERE id = %s", (datetime.now(), user['id']))
                conn2.commit()
                cur2.close()
            finally:
                conn2.close()

        resp = make_response(jsonify({'message': 'Login exitoso', 'user': user_data}))
        resp.set_cookie(
            SESSION_COOKIE_NAME, session_token,
            httponly = True,
            secure   = IS_PRODUCTION,
            samesite = 'Strict',
            max_age  = SESSION_DURATION_HOURS * 3600,
            path     = '/'
        )
        return resp

    except Error as e:
        print(f'[LOGIN] Error: {e}')
        try: conn.close()
        except: pass
        return jsonify({'error': 'Error de servidor'}), 500


@app.route('/api/me', methods=['GET'])
def api_me():
    """Valida la cookie de sesión contra la BD y verifica IP/país."""
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        return jsonify({'error': 'No autenticado'}), 401

    client_ip = request.headers.get('X-Forwarded-For', request.remote_addr).split(',')[0].strip()
    user_data = db_get_session(token, client_ip)

    if not user_data:
        # Token inválido, expirado o cambio de país → limpiar cookie
        resp = make_response(jsonify({'error': 'Sesión inválida o expirada'}), 401)
        resp.set_cookie(SESSION_COOKIE_NAME, '', max_age=0, path='/')
        return resp

    return jsonify({'user': user_data}), 200


@app.route('/api/logout', methods=['POST'])
def api_logout():
    """Invalida la sesión en BD y borra la cookie."""
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if token:
        db_delete_session(token)

    resp = make_response(jsonify({'message': 'Sesión cerrada'}))
    resp.set_cookie(
        SESSION_COOKIE_NAME, '',
        httponly=True, secure=IS_PRODUCTION, samesite='Strict',
        max_age=0, path='/'
    )
    return resp


@app.route('/manifest.json')
def serve_manifest():
    return send_file('manifest.json', mimetype='application/manifest+json')

@app.route('/generate-report', methods=['POST'])
def handle_generate_report():
    print("\n--- Peticin recibida en /generate-report ---")
    try:
        analysis_result = run_report_generation()
        
        if analysis_result:
            print("--- Proceso completado. Enviando informe al frontend. ---")
            return jsonify(analysis_result)
        else:
            return jsonify({"error": "No se pudo generar el informe."}), 500
    except ReportGenerationError as e:
        return jsonify({"error": str(e), "type": "ai_unavailable"}), 503

@app.route('/latest-report', methods=['GET'])
def handle_latest_report():
    report = get_latest_report()
    if report:
        return jsonify(report)
    return jsonify({"error": "No hay reportes disponibles."}), 404

@app.route('/api/reports', methods=['GET'])
def handle_get_reports():
    days = request.args.get('days', '7')
    reports = get_reports_by_range(days)
    return jsonify(reports)

@app.route('/api/admin/db-info', methods=['GET'])
def get_db_info():
    # Simple check for demo - in prod use better token validation
    auth_header = request.headers.get('Authorization')
    # For now we check the username from a query param or session if we had one
    # But since we use localStorage, we'll expect a header or just a client-side check for now
    # Recommended: Verify user is 'admin' in database
    
    conn = get_connection()
    if not conn:
        return jsonify({'error': 'Error de base de datos'}), 500
        
    try:
        cursor = conn.cursor()
        
        # Get all databases
        cursor.execute("SHOW DATABASES")
        databases = [db[0] for db in cursor.fetchall()]
        
        db_details = {}
        for db in databases:
            if db in ['information_schema', 'mysql', 'performance_schema', 'sys']:
                continue
            cursor.execute(f"USE {db}")
            cursor.execute("SHOW TABLES")
            tables = [table[0] for table in cursor.fetchall()]
            db_details[db] = tables
            
        return jsonify(db_details)
    except Error as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if conn: conn.close()

@app.route('/api/admin/table-data/<db_name>/<table_name>', methods=['GET'])
def get_table_data(db_name, table_name):
    # Security: Verify db_name and table_name are alphanumeric/underscores to prevent injection
    if not db_name.replace('_', '').isalnum() or not table_name.replace('_', '').isalnum():
        return jsonify({'error': 'Nombres invalidos'}), 400

    conn = get_connection()
    if not conn:
        return jsonify({'error': 'Error de base de datos'}), 500
        
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(f"USE {db_name}")
        cursor.execute(f"SELECT * FROM {table_name} LIMIT 100")
        rows = cursor.fetchall()
        
        # Also get column information for the UI
        cursor.execute(f"DESCRIBE {table_name}")
        columns = cursor.fetchall()
        
        return jsonify({'columns': columns, 'rows': rows})
    except Error as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if conn: conn.close()

@app.route('/api/admin/delete-row', methods=['POST'])
def delete_row():
    data = request.json
    db = data.get('db')
    table = data.get('table')
    pk_col = data.get('pk_col')
    pk_val = data.get('pk_val')
    
    # Basic validation
    if not all(x.replace('_', '').isalnum() for x in [db, table, pk_col]):
        return jsonify({'error': 'Nombres invalidos'}), 400

    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(f"USE {db}")
        cursor.execute(f"DELETE FROM {table} WHERE {pk_col} = %s", (pk_val,))
        conn.commit()
        return jsonify({'success': True})
    except Error as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if conn: conn.close()

@app.route('/api/admin/update-row', methods=['POST'])
def update_row():
    data = request.json
    db = data.get('db')
    table = data.get('table')
    pk_col = data.get('pk_col')
    pk_val = data.get('pk_val')
    updates = data.get('updates') # Dict of col: val

    if not updates:
        return jsonify({'error': 'No hay cambios'}), 400
        
    # Basic validation
    if not all(x.replace('_', '').isalnum() for x in [db, table, pk_col] + list(updates.keys())):
        return jsonify({'error': 'Nombres de columna invalidos'}), 400

    cols = ", ".join([f"{k} = %s" for k in updates.keys()])
    vals = list(updates.values()) + [pk_val]

    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(f"USE {db}")
        cursor.execute(f"UPDATE {table} SET {cols} WHERE {pk_col} = %s", vals)
        conn.commit()
        return jsonify({'success': True})
    except Error as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if conn: conn.close()




# ==================== PUSH NOTIFICATIONS ====================

@app.route('/api/admin/add-user', methods=['POST'])
def add_user():
    data = request.json
    username = data.get('username')
    email = data.get('email')
    password = data.get('password')

    if not all([username, email, password]):
        return jsonify({'error': 'Todos los campos son obligatorios'}), 400

    hashed_password = generate_password_hash(password)
    
    conn = get_auth_connection()
    if not conn:
        return jsonify({'error': 'Error de base de datos'}), 500
        
    try:
        cursor = conn.cursor()
        # last_login defaults to NULL, created_at defaults to CURRENT_TIMESTAMP in DB
        cursor.execute(
            "INSERT INTO users (username, email, password, created_at) VALUES (%s, %s, %s, %s)",
            (username, email, hashed_password, datetime.now())
        )
        conn.commit()
        return jsonify({'success': True, 'message': 'Usuario creado correctamente'})
    except Error as e:
        if 'Duplicate entry' in str(e):
            return jsonify({'error': 'El usuario o email ya existe'}), 400
        return jsonify({'error': str(e)}), 500
    finally:
        if conn: conn.close()

def get_vapid_public_key():
    if not VAPID_PUBLIC_KEY:
        return jsonify({"error": "VAPID keys not configured"}), 500
    return jsonify({"publicKey": VAPID_PUBLIC_KEY})

@app.route('/push-subscribe', methods=['POST'])
def push_subscribe():
    subscription = request.get_json()
    if not subscription or 'endpoint' not in subscription:
        return jsonify({"error": "Invalid subscription"}), 400
    
    endpoint = subscription['endpoint']
    push_subscriptions[endpoint] = subscription
    print(f"Nueva suscripcion push: {endpoint[:50]}...")
    return jsonify({"success": True, "message": "Subscribed successfully"})

@app.route('/push-unsubscribe', methods=['POST'])
def push_unsubscribe():
    data = request.get_json()
    endpoint = data.get('endpoint') if data else None
    
    if endpoint and endpoint in push_subscriptions:
        del push_subscriptions[endpoint]
        print(f"Suscripcion eliminada: {endpoint[:50]}...")
    
    return jsonify({"success": True})

@app.route('/push-test', methods=['POST'])
def push_test():
    payload = json.dumps({
        "title": "Notificacion de Prueba",
        "body": "Las notificaciones push estan funcionando correctamente!",
        "icon": "/images/logo_noti.png",
        "badge": "/images/icon.png",
        "tag": "test-notification",
        "data": {"url": "/", "type": "test"}
    })
    
    sent = send_push_to_all(payload)
    return jsonify({"success": True, "subscribers": len(push_subscriptions), "sent": sent})

@app.route('/push-seismic-alert', methods=['POST'])
def push_seismic_alert():
    data = request.get_json()
    magnitude = data.get('magnitude', 0) if data else 0
    
    payload = json.dumps({
        "title": "ALERTA SISMICA",
        "body": f"Vibración detectada: {magnitude:.3f} g\nRevise condiciones en el área.",
        "icon": "/images/alert_noti.png",
        "badge": "/images/icon.png",
        "tag": "seismic-alert",
        "requireInteraction": True,
        "data": {"url": "/", "type": "seismic"}
    })
    
    send_push_to_all(payload)
    return jsonify({"success": True, "subscribers": len(push_subscriptions)})

def send_push_to_all(payload):
    if not VAPID_PRIVATE_KEY or not VAPID_PUBLIC_KEY:
        print(" VAPID keys not configured, skipping push")
        return 0
    
    sent = 0
    failed_endpoints = []
    
    for endpoint, subscription in list(push_subscriptions.items()):
        try:
            webpush(
                subscription_info=subscription,
                data=payload,
                vapid_private_key=VAPID_PRIVATE_KEY,
                vapid_claims=VAPID_CLAIMS
            )
            sent += 1
        except WebPushException as e:
            print(f"Error enviando push a {endpoint[:30]}...: {e}")
            if e.response and e.response.status_code in [404, 410]:
                failed_endpoints.append(endpoint)
        except Exception as e:
            print(f"Error inesperado enviando push: {e}")
    
    for endpoint in failed_endpoints:
        if endpoint in push_subscriptions:
            del push_subscriptions[endpoint]
            print(f"Suscripcion expirada eliminada: {endpoint[:30]}...")
    
    print(f"Push enviado a {sent}/{len(push_subscriptions) + len(failed_endpoints)} suscriptores")
    return sent

def send_daily_report_notification():
    report = get_latest_report()
    if not report:
        return
    
    temp = report.get('variables', {}).get('temperatura', {}).get('avg')
    hum = report.get('variables', {}).get('humedad', {}).get('avg')
    condition = report.get('condicion_general', 'N/A')
    
    temp_str = f"{temp:.1f}" if temp else "N/A"
    hum_str = f"{hum:.1f}" if hum else "N/A"
    
    payload = json.dumps({
        "title": "Reporte Meteorologico Diario",
        "body": f"Temp: {temp_str}C | Humedad: {hum_str}%\nCondicion: {condition}",
        "icon": "/images/logo_noti.png",
        "badge": "/images/icon.png",
        "tag": "daily-report",
        "data": {"url": "/report.html", "type": "report"}
    })
    
    send_push_to_all(payload)

@app.errorhandler(Exception)
def handle_exception(e):
    try:
        error_msg = str(e).encode('ascii', 'ignore').decode('ascii')
        print(f"ERROR GLOBAL: {error_msg}")
    except:
        pass
    return jsonify({"error": "Internal Server Error", "details": str(e), "type": "server_error"}), 500

# ==================== MAIN ====================
# Para ejecutar el sistema, usa: python start.py

if __name__ == '__main__':
    print("=" * 50)
    print("  USO: python start.py")
    print("=" * 50)
    print("\nEste archivo contiene los mdulos del backend.")
    print("Para iniciar el servidor, ejecuta start.py")
    print("\nEjemplo:")
    print("  python start.py")
    print("")
