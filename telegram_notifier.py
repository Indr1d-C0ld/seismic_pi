import time
import sqlite3
import requests

DB_PATH = "sismografo.db"
TELEGRAM_API_URL_TEMPLATE = "https://api.telegram.org/bot{token}/sendMessage"

def get_unnotified_events():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT id, timestamp, tipo, valore, descrizione FROM eventi_anomali WHERE notified=0")
    events = cursor.fetchall()
    conn.close()
    return events

def get_telegram_config():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT telegram_bot_token, telegram_chat_id, notifiche_abilitate FROM config WHERE id = 1")
    row = cursor.fetchone()
    conn.close()
    if row:
        return {
            "telegram_bot_token": row["telegram_bot_token"],
            "telegram_chat_id": row["telegram_chat_id"],
            "notifiche_abilitate": row["notifiche_abilitate"]
        }
    return {"telegram_bot_token": "", "telegram_chat_id": "", "notifiche_abilitate": 0}

def mark_event_notified(event_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE eventi_anomali SET notified=1 WHERE id=?", (event_id,))
    conn.commit()
    conn.close()

def send_notification(event):
    config = get_telegram_config()
    if not config["notifiche_abilitate"]:
        print("Notifiche automatiche disabilitate.")
        return
    token = config["telegram_bot_token"]
    chat_id = config["telegram_chat_id"]
    if not token or not chat_id:
        print("Token o Chat ID non configurati.")
        return
    url = TELEGRAM_API_URL_TEMPLATE.format(token=token)
    data = {"chat_id": chat_id, "text": f"Evento Anomalo Rilevato!\nTimestamp: {event['timestamp']}\nTipo: {event['tipo']}\nValore: {event['valore']}\nDescrizione: {event['descrizione']}"}
    response = requests.post(url, data=data)
    if response.status_code == 200:
        mark_event_notified(event["id"])
        print(f"Notifica inviata per evento {event['id']}")
    else:
        print(f"Errore nell'invio per evento {event['id']}: {response.text}")

def main():
    while True:
        events = get_unnotified_events()
        for event in events:
            send_notification(event)
        time.sleep(10)

if __name__ == "__main__":
    main()

