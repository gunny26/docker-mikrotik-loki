#!/usr/bin/python3
import calendar
import collections
import datetime
import json
import random
import requests
import time
# non std modules
# pip install librouteros
# from routeros_api import RouterOsApiPool
import routeros_api
from routeros_api.api_structure import StringField


# --- KONFIGURATION ---
LOKI_URL = "http://10.0.0.1:3100/loki/api/v1/push"
TARGET_HOST = "mikrotik_router" # Label für den Router-Hostnamen
TARGET_JOB = "python_mikrotik" # Label für den Job-Namen

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
        print(f"FEHLER: Das Datumsformat '{date_string}' ist ungültig. Erwartet: YYYY-MM-DD HH:MM:SS. Fehler: {e}")
        # Rückgabe des aktuellen Zeitstempels als Fallback
        return generate_loki_timestamp()

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

    print(f"Sende {len(log_data)} Logs an Loki unter {LOKI_URL}...")
    
    try:
        response = requests.post(LOKI_URL, headers=headers, data=json.dumps(payload))
        
        if response.status_code == 204:
            print("Erfolgreich an Loki gesendet (Status 204 No Content).")
        elif response.status_code == 400:
             # Loki gibt oft 400 zurück, wenn Zeitstempel zu alt/neu sind
             print(f"FEHLER: Loki lehnte die Anfrage ab (Status 400 Bad Request). Antwort: {response.text}")
        else:
            print(f"FEHLER: Unerwarteter Statuscode {response.status_code}. Antwort: {response.text}")

    except requests.exceptions.ConnectionError:
        print(f"FEHLER: Verbindung zu Loki unter {LOKI_URL} fehlgeschlagen. Ist der Server erreichbar?")
    except Exception as e:
        print(f"Ein unbekannter Fehler ist aufgetreten: {e}")


def get_mikrotik_logs(ip, username, password):

    connection = routeros_api.RouterOsApiPool(ip, username=username, password=password, plaintext_login=True)
    api = connection.get_api()
    # This part here is important:
    default_structure = collections.defaultdict(lambda: StringField(encoding='windows-1250'))
    api.get_resource('/system/identity', structure=default_structure).get()

    logs = api.get_resource('/log').call('print', {})
    
    log_data = []

    newest_time_ns = int(time.time() * 1_000_000_000)
    oldest_time_ns = int((time.time() - 60 * 59) * 1_000_000_000)

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
        print(log_entry)

        timestamp_ns = convert_to_loki_timestamp(log_entry["time"])
        print(f"{oldest_time_ns} < {timestamp_ns} < {newest_time_ns}")
        if timestamp_ns < oldest_time_ns:
            print("ERROR: log entry is to old, skipping")
            continue
        
        # Formatieren der Log-Zeile aus den Log-Feldern des Routers
        message = f"[{log_entry.get('topics', 'system')}] {log_entry.get('message', 'N/A')}"
        
        print(message)
        log_data.append((str(timestamp_ns), message))
        
    return log_data


# --- HAUPTPROGRAMM ---

def main():
    # 1. Stellen Sie sicher, dass die 'requests'-Bibliothek installiert ist: pip install requests
    
    # 2. Logs vom Router abrufen (simuliert)
    # logs = simulate_mikrotik_log_fetch()
    logs = get_mikrotik_logs("mikrotik", "apiuser", "some_random_password")
    
    # 3. Logs an Loki senden
    send_to_loki(logs)

if __name__ == '__main__':
    main()


