import os
import mysql.connector
from mysql.connector import Error
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / '.env')

DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': int(os.getenv('DB_PORT', 3306)),
    'user': os.getenv('DB_USER', 'root'),
    'password': os.getenv('DB_PASSWORD', ''),
    'database': os.getenv('DB_NAME', 'iot_clima')
}

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
        import json
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

def get_report_by_date(fecha: str) -> dict | None:
    conn = get_connection()
    if not conn:
        return None
    try:
        import json
        cursor = conn.cursor(dictionary=True)
        cursor.execute('SELECT * FROM reports WHERE fecha = %s', (fecha,))
        result = cursor.fetchone()
        cursor.close()
        conn.close()
        if result and result.get('full_report'):
            return json.loads(result['full_report'])
        return result
    except Error as e:
        print(f"Error obteniendo reporte: {e}")
        return None

def get_latest_report() -> dict | None:
    conn = get_connection()
    if not conn:
        return None
    try:
        import json
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

if __name__ == '__main__':
    init_database()
