import threading
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

def start_logger():
    from backend import logger
    logger.main()

def start_weather_agent():
    from backend import weather_agent
    weather_agent.scheduler_thread = threading.Thread(target=weather_agent.run_scheduler, daemon=True)
    weather_agent.scheduler_thread.start()
    weather_agent.app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)

def main():
    print("=" * 50)
    print("Iniciando servicios del backend IoT...")
    print("=" * 50)
    
    logger_thread = threading.Thread(target=start_logger, daemon=True)
    logger_thread.start()
    print("✅ Logger MQTT iniciado")
    
    print("✅ Weather Agent (Flask) iniciando en puerto 5000...")
    start_weather_agent()

if __name__ == '__main__':
    main()
