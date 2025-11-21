import requests
import json
import time
import datetime
import random

# --- KONFIGURATION ---
LOKI_URL = "http://10.0.0.1:3100/loki/api/v1/push"
TARGET_HOST = "mikrotik_router" # Label für den Router-Hostnamen
TARGET_JOB = "python_mikrotik" # Label für den Job-Namen

# --- HILFSFUNKTIONEN ---

def generate_loki_timestamp():
    """Erzeugt den Timestamp im Nanosekunden-Format, das Loki erwartet."""
    # time.time() gibt Sekunden seit Epoch zurück
    nanoseconds = int(time.time() * 1_000_000_000)
    return str(nanoseconds)

def simulate_mikrotik_log_fetch():
    """
    SIMULIERT das Abrufen von Logs von einem MikroTik Router.
    
    In einer echten Anwendung würden Sie hier 'librouteros' oder eine ähnliche 
    Bibliothek verwenden, um "/log/print" abzufragen.
    
    Gibt eine Liste von (Timestamp, Log-Nachricht) Tupeln zurück.
    """
    now = datetime.datetime.now().strftime("%b %d %H:%M:%S")
    
    # Simulierte Log-Nachrichten
    logs = [
        (generate_loki_timestamp(), f"{now} event=dhcp_lease_ack user={random.randint(100, 999)} ip=192.168.1.{random.randint(10, 99)}"),
        (generate_loki_timestamp(), f"{now} event=firewall_drop src=10.1.1.5 dst=8.8.8.8 proto=udp"),
        (generate_loki_timestamp(), f"{now} event=system_info message='Router reloaded its configuration.'")
    ]
    return logs

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

# --- HAUPTPROGRAMM ---

def main():
    # 1. Stellen Sie sicher, dass die 'requests'-Bibliothek installiert ist: pip install requests
    
    # 2. Logs vom Router abrufen (simuliert)
    logs = simulate_mikrotik_log_fetch()
    
    # 3. Logs an Loki senden
    send_to_loki(logs)

    # Nächste Schritte:
    print("\n--- NÄCHSTE SCHRITTE ---")
    print("1. Installation: pip install requests")
    print("2. Im Grafana Explorer (Loki Datenquelle) nach den Labels '{job=\"python_mikrotik\"}' suchen.")
    print("3. ECHTER MIKROTIK-ABRUF: Ersetzen Sie 'simulate_mikrotik_log_fetch' durch eine Funktion,")
    print("   die 'librouteros' oder 'routeros-api' verwendet.")

if __name__ == '__main__':
    main()


