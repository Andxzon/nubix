"""
IoT Climate Monitoring System - Punto de Entrada
=================================================
Local:  python start.py
Render: gunicorn --worker-class gevent -w 1 start:app

Servicios que inicia:
1. Servidor Flask + WebSocket
2. Logger MQTT (guarda lecturas cada 1 segundos)
3. Scheduler (genera informe automático a las 23:30 GMT-5)

Los informes se generan:
- Automáticamente: cada día a las 23:30 GMT-5
- Manualmente: POST /generate-report
"""

import os
import sys
import time
import threading
import signal

from app import (
    app,
    socketio,
    init_database,
    run_mqtt_logger,
    run_scheduler
)

IS_RENDER = os.getenv('RENDER', False)
PORT = int(os.getenv('PORT', 5000))


def signal_handler(sig, frame):
    """Manejo de señal para cierre limpio"""
    print("\n\nCerrando servidor...")
    sys.exit(0)


def start_mqtt_service():
    """Inicia el servicio de logging MQTT en segundo plano"""
    print("[MQTT] Iniciando logger MQTT...")
    try:
        run_mqtt_logger()
    except Exception as e:
        print(f"[MQTT] Error critico: {e}")


def start_scheduler_service():
    """Inicia el scheduler para tareas programadas"""
    print("[SCHEDULER] Iniciando programador de tareas...")
    print("[SCHEDULER] -> Informe automatico: 23:30 GMT-5")
    print("[SCHEDULER] -> Limpieza de datos: 00:00 GMT-5")
    try:
        run_scheduler()
    except Exception as e:
        print(f"[SCHEDULER] Error critico: {e}")


def init_services():
    """Inicializa todos los servicios en segundo plano"""
    print("=" * 60)
    print("  IoT CLIMATE MONITORING SYSTEM")
    print("  Backend Server")
    print("=" * 60)
    
    print("\n[1/3] Inicializando base de datos...")
    if init_database():
        print("      - Base de datos lista")
    else:
        print("      - Error en base de datos (continuando...)")
    
    print("\n[2/3] Iniciando servicio MQTT...")
    mqtt_thread = threading.Thread(target=start_mqtt_service, daemon=True)
    mqtt_thread.start()
    print("      - Servicio MQTT iniciado")
    
    print("\n[3/3] Iniciando scheduler...")
    scheduler_thread = threading.Thread(target=start_scheduler_service, daemon=True)
    scheduler_thread.start()
    print("      - Scheduler iniciado")
    
    print(f"  Servidor listo en puerto {PORT}")
    print("=" * 60 + "\n")


def main():
    """Punto de entrada para ejecución local"""
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    print(f"\n  Presiona Ctrl+C para detener el servidor\n")
    
    socketio.run(
        app,
        host='0.0.0.0',
        port=PORT,
        debug=False,
        allow_unsafe_werkzeug=True
    )


if __name__ == '__main__':
    init_services()
    main()
