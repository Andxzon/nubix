import sys
import time
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
import paho.mqtt.client as mqtt
import ssl
from dotenv import load_dotenv
from .database import save_sensor_reading, init_database

BASE_DIR = Path(__file__).resolve().parent.parent
env_path = BASE_DIR / '.env'
load_dotenv(env_path)

MQTT_HOST = os.getenv('MQTT_HOST', 'broker.emqx.io')
MQTT_PORT = int(os.getenv('MQTT_PORT', 8084))
MQTT_USER = os.getenv('MQTT_USER')
MQTT_PASSWORD = os.getenv('MQTT_PASSWORD')

RESET_FLAG = '--reset' in sys.argv

SENSORS = [
    {'id': 'tempChart',  'label': 'Temperatura',   'unit': '°C',  'topic': 'clima/temperatura'},
    {'id': 'presChart',  'label': 'Presión',       'unit': 'hPa', 'topic': 'clima/presion'},
    {'id': 'humChart',   'label': 'Humedad',       'unit': '%',   'topic': 'clima/humedad'},
    {'id': 'soilChart',  'label': 'Humedad suelo', 'unit': '%',   'topic': 'clima/humedad_suelo'},
    {'id': 'lightChart', 'label': 'Luz',           'unit': 'lux', 'topic': 'clima/lux'},
    {'id': 'vibrChart',  'label': 'Vibración',     'unit': 'Hz',  'topic': 'clima/vibracion'}
]

last_values = {}
new_data_received = False

def get_timestamp_gmt_minus_5():
    tz = timezone(timedelta(hours=-5))
    now = datetime.now(tz)
    return now

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
    except ValueError:
        pass

def save_data():
    global new_data_received, last_values
    
    if not new_data_received:
        print("Sin datos nuevos del dispositivo, omitiendo guardado...")
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
        else:
            print("Error guardando datos en MySQL")
    
    new_data_received = False
    last_values = {}

def main():
    print("Inicializando base de datos...")
    init_database()
    
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, transport="websockets")
    client.on_connect = on_connect
    client.on_message = on_message
    
    if MQTT_USER and MQTT_PASSWORD:
        client.username_pw_set(MQTT_USER, MQTT_PASSWORD)
    
    client.tls_set(tls_version=ssl.PROTOCOL_TLS)
    client.connect(MQTT_HOST, MQTT_PORT, 60)
    client.loop_start()
    
    print("Logger iniciado. Guardando datos cada 10 segundos en MySQL")
    
    try:
        while True:
            time.sleep(10)
            save_data()
    except KeyboardInterrupt:
        print("\nLogger detenido.")
        client.loop_stop()
        client.disconnect()

if __name__ == '__main__':
    main()
