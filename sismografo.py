import smbus
import time
import sqlite3
import math

# Indirizzo I2C del MPU-6050
MPU_ADDRESS = 0x68
bus = smbus.SMBus(1)  # Se necessario, usa smbus.SMBus(0)

# Risveglia il sensore MPU-6050
bus.write_byte_data(MPU_ADDRESS, 0x6B, 0)

# Connessione al database SQLite
conn = sqlite3.connect("sismografo.db", check_same_thread=False)
cursor = conn.cursor()

# Tabella dei dati raw
cursor.execute("""
    CREATE TABLE IF NOT EXISTS dati_grezzi (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        accel_x REAL, accel_y REAL, accel_z REAL,
        gyro_x REAL, gyro_y REAL, gyro_z REAL
    )
""")

# Tabella degli eventi anomali
cursor.execute("""
    CREATE TABLE IF NOT EXISTS eventi_anomali (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        tipo TEXT,
        valore REAL,
        descrizione TEXT,
        notified INTEGER DEFAULT 0
    )
""")

# Tabella per salvare gli snapshot degli eventi
cursor.execute("""
    CREATE TABLE IF NOT EXISTS event_snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_id INTEGER,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        svg_data TEXT
    )
""")

# Tabella di configurazione (inclusi offset di calibrazione e password admin)
cursor.execute("""
    CREATE TABLE IF NOT EXISTS config (
        id INTEGER PRIMARY KEY,
        accel_threshold REAL DEFAULT 2.0,
        gyro_threshold REAL DEFAULT 70.0,
        sample_interval REAL DEFAULT 0.1,
        visualization_mode TEXT DEFAULT 'triple',
        chart_buffer REAL DEFAULT 300,
        data_retention REAL DEFAULT 300,
        telegram_bot_token TEXT DEFAULT '',
        telegram_chat_id TEXT DEFAULT '',
        notifiche_abilitate INTEGER DEFAULT 1,
        admin_password TEXT DEFAULT 'admin',
        offset_accel_x REAL DEFAULT 0,
        offset_accel_y REAL DEFAULT 0,
        offset_accel_z REAL DEFAULT 0,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
""")
conn.commit()

# Inserisce la configurazione di default se non esiste
cursor.execute("SELECT COUNT(*) FROM config")
if cursor.fetchone()[0] == 0:
    cursor.execute("""
        INSERT INTO config 
        (accel_threshold, gyro_threshold, sample_interval, visualization_mode, chart_buffer, data_retention, telegram_bot_token, telegram_chat_id, notifiche_abilitate, admin_password, offset_accel_x, offset_accel_y, offset_accel_z)
        VALUES (2.0, 70.0, 0.1, 'triple', 300, 300, '', '', 1, 'admin', 0, 0, 0)
    """)
    conn.commit()

def get_config():
    """Recupera la configurazione dal database, inclusi gli offset."""
    cursor.execute("""
        SELECT accel_threshold, gyro_threshold, sample_interval, visualization_mode, chart_buffer, data_retention, offset_accel_x, offset_accel_y, offset_accel_z
        FROM config WHERE id = 1
    """)
    row = cursor.fetchone()
    if row:
        return {
            "accel_threshold": row[0],
            "gyro_threshold": row[1],
            "sample_interval": row[2],
            "visualization_mode": row[3],
            "chart_buffer": row[4],
            "data_retention": row[5],
            "offset_accel_x": row[6],
            "offset_accel_y": row[7],
            "offset_accel_z": row[8]
        }
    return {"accel_threshold": 2.0, "gyro_threshold": 70.0, "sample_interval": 0.1, "visualization_mode": "triple", "chart_buffer": 300, "data_retention":300, "offset_accel_x": 0, "offset_accel_y": 0, "offset_accel_z": 0}

def read_mpu():
    """
    Legge i dati dal sensore MPU-6050, li converte in valori fisici e applica la calibrazione.
    Ritorna: accel_x, accel_y, accel_z, gyro_x, gyro_y, gyro_z
    """
    data = bus.read_i2c_block_data(MPU_ADDRESS, 0x3B, 14)
    def convert(value):
        if value > 32767:
            value -= 65536
        return value
    accel_x = convert(data[0] << 8 | data[1]) / 16384.0
    accel_y = convert(data[2] << 8 | data[3]) / 16384.0
    accel_z = convert(data[4] << 8 | data[5]) / 16384.0

    # Applica gli offset di calibrazione
    config = get_config()
    accel_x -= config.get("offset_accel_x", 0)
    accel_y -= config.get("offset_accel_y", 0)
    accel_z -= config.get("offset_accel_z", 0)

    gyro_x = convert(data[8] << 8 | data[9]) / 131.0
    gyro_y = convert(data[10] << 8 | data[11]) / 131.0
    gyro_z = convert(data[12] << 8 | data[13]) / 131.0

    return accel_x, accel_y, accel_z, gyro_x, gyro_y, gyro_z

def get_description(tipo, valore):
    """
    Restituisce una descrizione qualitativa per l'evento.
    """
    if tipo == "Accelerazione":
        if valore < 2.5:
            return "Scossa lieve"
        elif valore < 3.5:
            return "Scossa moderata"
        else:
            return "Scossa forte"
    elif tipo == "Rotazione":
        if valore < 80:
            return "Rotazione lieve"
        elif valore < 110:
            return "Rotazione moderata"
        else:
            return "Rotazione intensa"
    else:
        return "Evento sconosciuto"

def detect_event(accel_x, accel_y, accel_z, gyro_x, gyro_y, gyro_z, accel_threshold, gyro_threshold):
    """
    Se i valori superano le soglie, registra un evento anomalo.
    """
    accel_magnitude = math.sqrt(accel_x**2 + accel_y**2 + accel_z**2)
    gyro_magnitude = math.sqrt(gyro_x**2 + gyro_y**2 + gyro_z**2)
    event_detected = False
    if accel_magnitude > accel_threshold:
        descr = get_description("Accelerazione", accel_magnitude)
        cursor.execute("""
            INSERT INTO eventi_anomali (tipo, valore, descrizione)
            VALUES (?, ?, ?)
        """, ("Accelerazione", accel_magnitude, descr))
        event_detected = True
        print(f"Evento rilevato! {descr} (Accel: {accel_magnitude:.2f}g)")
    if gyro_magnitude > gyro_threshold:
        descr = get_description("Rotazione", gyro_magnitude)
        cursor.execute("""
            INSERT INTO eventi_anomali (tipo, valore, descrizione)
            VALUES (?, ?, ?)
        """, ("Rotazione", gyro_magnitude, descr))
        event_detected = True
        print(f"Evento rilevato! {descr} (Gyro: {gyro_magnitude:.2f}°/s)")
    if event_detected:
        conn.commit()

def cleanup_old_data(retention):
    """
    Elimina i dati raw più vecchi del periodo di retention (in secondi).
    """
    cursor.execute("DELETE FROM dati_grezzi WHERE timestamp < datetime('now', '-' || ? || ' seconds')", (retention,))
    conn.commit()

def main():
    print("🟢 Avvio monitoraggio sismografico...")
    while True:
        config = get_config()
        accel_threshold = config["accel_threshold"]
        gyro_threshold = config["gyro_threshold"]
        sample_interval = config["sample_interval"]
        data_retention = config["data_retention"]

        # Acquisizione dati dal sensore
        accel_x, accel_y, accel_z, gyro_x, gyro_y, gyro_z = read_mpu()

        # Salvataggio dei dati raw
        cursor.execute("""
            INSERT INTO dati_grezzi (accel_x, accel_y, accel_z, gyro_x, gyro_y, gyro_z)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (accel_x, accel_y, accel_z, gyro_x, gyro_y, gyro_z))
        conn.commit()

        # Eliminazione dei dati vecchi
        cleanup_old_data(data_retention)

        # Rilevamento degli eventi anomali
        detect_event(accel_x, accel_y, accel_z, gyro_x, gyro_y, gyro_z, accel_threshold, gyro_threshold)

        time.sleep(sample_interval)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n🛑 Interruzione manuale. Chiusura database.")
        conn.close()

