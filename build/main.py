#!/usr/bin/python3
import calendar
import collections
import datetime
import json
import logging
import os
import requests
import time
# non std modules
# pip install librouteros
# from routeros_api import RouterOsApiPool
import routeros_api
from routeros_api.api_structure import StringField


# Configuration from environment
DEBUG_LEVEL = os.environ.get("DEBUG_LEVEL", "INFO")
INTERVAL = int(os.environ.get("INTERVAL", "300"))
LOKI_URL = os.environ.get("LOKI_URL", "http://loki:3100/loki/api/v1/push")
TARGET_HOST = os.environ.get("TARGET_HOST", "mikrotik_router")
TARGET_JOB = os.environ.get("TARGET_JOB", "python_mikrotik")
MIKROTIK_IP = os.environ["MIKROTIK_IP"]  # required
MIKROTIK_USERNAME = os.environ["MIKROTIK_USERNAME"]  # required
MIKROTIK_PASSWORD = os.environ["MIKROTIK_PASSWORD"]  # required

# Setup logging
logging.basicConfig(
    level=getattr(logging, DEBUG_LEVEL),
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# --- HILFSFUNKTIONEN ---

def convert_to_loki_timestamp(date_string):
    """
    Konvertiert einen gegebenen Datums-String ("YYYY-MM-DD HH:MM:SS")
    in einen Nanosekunden-Zeitstempel für Loki.
    
    :param date_string: Der Datums-String, z.B. "2025-11-21 12:41:09"
    :return: Zeitstempel als String in Nanosekunden (19 Stellen)
    """
    # 1. Parsing des Strings in ein datetime-Objekt
    # Wir verwenden strptime, um das genaue Format zu definieren.
    # Da der MikroTik-Log oft keine Zeitzone enthält, behandeln wir ihn als UTC (oder wie der Server ihn ausgibt).
    try:
        dt_object = datetime.datetime.strptime(date_string, "%Y-%m-%d %H:%M:%S")
    except ValueError as e:
        logging.error(f"FEHLER: Das Datumsformat '{date_string}' ist ungültig. Erwartet: YYYY-MM-DD HH:MM:SS. Fehler: {e}")
        # Rückgabe des aktuellen Zeitstempels als Fallback
        return int(time.time() * 1_000_000_000)

    # 2. Umwandlung in Sekunden seit der Unix-Epoch
    # calendar.timegm() ist nützlich, wenn das datetime-Objekt als UTC behandelt wird.
    epoch_seconds = calendar.timegm(dt_object.timetuple())
    
    # 3. Konvertierung in Nanosekunden (Multipliziert mit 1 Milliarde)
    nanoseconds = int(epoch_seconds * 1_000_000_000)
    
    return nanoseconds


def send_to_loki(log_data):
    """
    Sendet die vorbereiteten Logs an den Loki-Endpunkt.
    
    :param log_data: Liste von (Timestamp_ns, Log-Nachricht) Tupeln.
    """
    if not log_data:
        print("Keine Logs zum Senden vorhanden.")
        return

    # Loki erwartet ein JSON-Payload im 'streams' Format
    payload = {
        "streams": [
            {
                # Die Labels definieren den Stream, in dem die Logs gespeichert werden
                "stream": {
                    "job": TARGET_JOB,
                    "host": TARGET_HOST
                },
                # Die eigentlichen Log-Werte: [Timestamp_ns, Log_Zeile]
                "values": log_data 
            }
        ]
    }

    headers = {
        "Content-Type": "application/json"
    }

    logging.info(f"Sende {len(log_data)} Logs an Loki unter {LOKI_URL}...")
    
    try:
        response = requests.post(LOKI_URL, headers=headers, data=json.dumps(payload))
        
        if response.status_code == 204:
            logging.info("Erfolgreich an Loki gesendet (Status 204 No Content).")
        elif response.status_code == 400:
             # Loki gibt oft 400 zurück, wenn Zeitstempel zu alt/neu sind
             logging.error(f"FEHLER: Loki lehnte die Anfrage ab (Status 400 Bad Request). Antwort: {response.text}")
        else:
            logging.error(f"FEHLER: Unerwarteter Statuscode {response.status_code}. Antwort: {response.text}")

    except requests.exceptions.ConnectionError:
        logging.error(f"FEHLER: Verbindung zu Loki unter {LOKI_URL} fehlgeschlagen. Ist der Server erreichbar?")
    except Exception as exc:
        logging.error(f"Ein unbekannter Fehler ist aufgetreten: {exc}")
        logging.exceptio(exc)


def get_mikrotik_logs(ip, username, password):

    connection = routeros_api.RouterOsApiPool(ip, username=username, password=password, plaintext_login=True)
    api = connection.get_api()
    # This part here is important:
    default_structure = collections.defaultdict(lambda: StringField(encoding='windows-1250'))
    api.get_resource('/system/identity', structure=default_structure).get()

    logs = api.get_resource('/log').call('print', {})
    
    log_data = []  # str messages to send to loki

    newest_time_ns = int(time.time() * 1_000_000_000)
    oldest_time_ns = int((time.time() - INTERVAL) * 1_000_000_000)

    for log_entry in logs:
        # MikroTik gibt den Zeitstempel im Format 'Nov/20/2025 20:08:49' zurück.
        # Dieser muss in Nanosekunden seit Epoch konvertiert werden.
        # Da MikroTik keinen Millisekunden-Zeitstempel liefert, 
        # verwenden wir den aktuellen Host-Zeitstempel.
        # example for log message
        # {'id': '*4C53',
        #  'time': '2025-11-21 12:41:09',
        #  'topics': 'system,info,account',
        #  'message': 'user apiuser logged in from 192.168.1.47 via api',
        #  'extra-info': 'app=api duser=apiuser outcome=success src=192.168.1.47'
        # }
        logging.debug(log_entry)

        timestamp_ns = convert_to_loki_timestamp(log_entry["time"])
        logging.debug(f"{oldest_time_ns} < {timestamp_ns} < {newest_time_ns}")

        if timestamp_ns < oldest_time_ns:
            logging.error("ERROR: log entry is to old, skipping")
            continue
        
        # Formatieren der Log-Zeile aus den Log-Feldern des Routers
        message = f"[{log_entry.get('topics', 'system')}] {log_entry.get('message', 'N/A')}"
        
        logging.debug(message)
        log_data.append((str(timestamp_ns), message))
        
    return log_data


# --- HAUPTPROGRAMM ---

def main():

    # get loki logs
    logs = get_mikrotik_logs(MIKROTIK_IP, MIKROTIK_USERNAME, MIKROTIK_PASSWORD)
    # send them
    send_to_loki(logs)
    

if __name__ == '__main__':
    try:
        while True:
            starttime = time.time()

            main()
    
            duration = time.time() - starttime
            logging.info(f"sync took {duration} seconds to finish")
            time_left = max(0, INTERVAL - duration)  # amount of seconds to sleep, at least zero
            logging.info(f"sleeping {time_left} seconds before doing the next loop")
            time.sleep(time_left)

    except Exception as exc:
        logging.exception(exc)
