import os
import shutil
import time
from datetime import datetime, timedelta
import sqlite3
import requests

DB_FILE = "sismografo.db"
BACKUP_DIR = "backups"
# Retention dei backup in giorni
BACKUP_RETENTION_DAYS = 30

def create_backup():
    if not os.path.exists(BACKUP_DIR):
        os.makedirs(BACKUP_DIR)
    timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
    backup_filename = f"sismografo_{timestamp}.db"
    backup_path = os.path.join(BACKUP_DIR, backup_filename)
    shutil.copy(DB_FILE, backup_path)
    print(f"Backup creato: {backup_path}")
    return backup_path

def cleanup_backups():
    now = datetime.utcnow()
    for fname in os.listdir(BACKUP_DIR):
        fpath = os.path.join(BACKUP_DIR, fname)
        if not fname.startswith("sismografo_") or not fname.endswith(".db"):
            continue
        try:
            ts_str = fname[len("sismografo_"):-len(".db")]
            file_time = datetime.strptime(ts_str, "%Y%m%dT%H%M%S")
        except Exception:
            continue
        if now - file_time > timedelta(days=BACKUP_RETENTION_DAYS):
            os.remove(fpath)
            print(f"Backup rimosso: {fpath}")

def get_telegram_config():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT telegram_bot_token, telegram_chat_id, notifiche_abilitate FROM config WHERE id = 1")
    row = cur.fetchone()
    conn.close()
    if row:
        return {
            "telegram_bot_token": row["telegram_bot_token"],
            "telegram_chat_id": row["telegram_chat_id"],
            "notifiche_abilitate": row["notifiche_abilitate"]
        }
    return {"telegram_bot_token": "", "telegram_chat_id": "", "notifiche_abilitate": 0}

def send_backup_telegram(backup_path):
    config = get_telegram_config()
    if config["notifiche_abilitate"] and config["telegram_bot_token"] and config["telegram_chat_id"]:
        url = f"https://api.telegram.org/bot{config['telegram_bot_token']}/sendDocument"
        files = {'document': open(backup_path, 'rb')}
        data = {'chat_id': config["telegram_chat_id"], 'caption': f"Backup del database: {os.path.basename(backup_path)}"}
        response = requests.post(url, files=files, data=data)
        if response.status_code == 200:
            print(f"Backup inviato su Telegram: {backup_path}")
        else:
            print(f"Errore nell'invio del backup su Telegram: {response.text}")
    else:
        print("Backup non inviato: notifiche disabilitate o credenziali mancanti.")

def main():
    backup_path = create_backup()
    cleanup_backups()
    send_backup_telegram(backup_path)

if __name__ == "__main__":
    main()

