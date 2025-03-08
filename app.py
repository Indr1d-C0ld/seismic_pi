from flask import Flask, render_template, jsonify, request, Response, redirect, url_for, session
import sqlite3
import csv
import io
import requests
import subprocess
import smbus
from datetime import datetime
import os
import socket

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'  # Sostituisci con una stringa sicura!
DB_PATH = "sismografo.db"

def query_db(query, args=(), one=False):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(query, args)
    rv = cur.fetchall()
    conn.close()
    return (rv[0] if rv else None) if one else rv

# Inizializza la tabella access_log se non esiste
def init_access_log():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS access_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            ip_address TEXT,
            user_agent TEXT
        )
    """)
    conn.commit()
    conn.close()

init_access_log()

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        password = request.form.get('password')
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("SELECT admin_password FROM config WHERE id = 1")
        row = cur.fetchone()
        conn.close()
        admin_password = row["admin_password"] if row else "admin"
        if password == admin_password:
            session['logged_in'] = True
            # Registra l'accesso usando X-Forwarded-For se presente
            ip_address = request.headers.get('X-Forwarded-For', request.remote_addr)
            user_agent = request.headers.get('User-Agent')
            conn = sqlite3.connect(DB_PATH)
            cur = conn.cursor()
            cur.execute("INSERT INTO access_log (ip_address, user_agent) VALUES (?, ?)", (ip_address, user_agent))
            conn.commit()
            conn.close()
            return redirect(url_for('admin'))
        else:
            return render_template('login.html', error="Password errata.")
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('login'))

@app.route('/')
def index():
    config = query_db("SELECT * FROM config WHERE id = 1", one=True)
    config = dict(config) if config else {}
    return render_template('dashboard.html', config=config)

@app.route('/historico')
def historico():
    config = query_db("SELECT * FROM config WHERE id = 1", one=True)
    config = dict(config) if config else {}
    return render_template('historico.html', config=config)

@app.route('/diagnostics')
def diagnostics():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    diagnostics = {}
    # Temperatura CPU
    try:
        with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
            temp = float(f.read().strip()) / 1000.0
            diagnostics["CPU Temperature (°C)"] = temp
    except:
        diagnostics["CPU Temperature (°C)"] = "N/D"
    # Uptime
    try:
        with open("/proc/uptime", "r") as f:
            uptime_seconds = float(f.read().split()[0])
            diagnostics["Uptime (s)"] = uptime_seconds
    except:
        diagnostics["Uptime (s)"] = "N/D"
    # RAM
    try:
        meminfo = {}
        with open("/proc/meminfo", "r") as f:
            for line in f:
                parts = line.split(":")
                if len(parts) == 2:
                    meminfo[parts[0].strip()] = parts[1].strip()
        diagnostics["MemTotal"] = meminfo.get("MemTotal", "N/D")
        diagnostics["MemFree"] = meminfo.get("MemFree", "N/D")
    except:
        diagnostics["Memoria"] = "N/D"
    # Spazio disco
    try:
        result = subprocess.run(["df", "-h", "/"], stdout=subprocess.PIPE, text=True)
        diagnostics["Disk Usage"] = result.stdout
    except:
        diagnostics["Disk Usage"] = "N/D"
    # Indirizzo IP locale (usando un socket UDP)
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        diagnostics["Local IP"] = local_ip
    except:
        diagnostics["Local IP"] = "N/D"
    # Indirizzo IP esterno usando ipinfo.io
    try:
        r = requests.get("https://ipinfo.io/json", timeout=5)
        external_ip = r.json().get("ip", "N/D")
        diagnostics["External IP"] = external_ip
    except:
        diagnostics["External IP"] = "N/D"
    return render_template('diagnostics.html', diagnostics=diagnostics)

@app.route('/admin', methods=['GET', 'POST'])
def admin():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    if request.method == 'POST':
        accel_threshold = request.form.get('accel_threshold')
        gyro_threshold = request.form.get('gyro_threshold')
        sample_interval = request.form.get('sample_interval')
        visualization_mode = request.form.get('visualization_mode')
        chart_buffer = request.form.get('chart_buffer')
        data_retention = request.form.get('data_retention')
        telegram_bot_token = request.form.get('telegram_bot_token')
        telegram_chat_id = request.form.get('telegram_chat_id')
        notifiche_abilitate = 1 if request.form.get('notifiche_abilitate') == 'on' else 0
        admin_password = request.form.get('admin_password')
        
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("""
            UPDATE config 
            SET accel_threshold = ?, gyro_threshold = ?, sample_interval = ?, visualization_mode = ?, chart_buffer = ?, data_retention = ?, telegram_bot_token = ?, telegram_chat_id = ?, notifiche_abilitate = ?, admin_password = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = 1
        """, (accel_threshold, gyro_threshold, sample_interval, visualization_mode, chart_buffer, data_retention, telegram_bot_token, telegram_chat_id, notifiche_abilitate, admin_password))
        conn.commit()
        conn.close()
        return redirect(url_for('admin'))
    else:
        config = query_db("SELECT * FROM config WHERE id = 1", one=True)
        config = dict(config) if config else {}
        return render_template('admin.html', config=config)

@app.route('/admin/calibrate', methods=['POST'])
def calibrate():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    try:
        bus = smbus.SMBus(1)
        MPU_ADDRESS = 0x68
        bus.write_byte_data(MPU_ADDRESS, 0x6B, 0)
        data = bus.read_i2c_block_data(MPU_ADDRESS, 0x3B, 14)
        def convert(value):
            if value > 32767:
                value -= 65536
            return value
        accel_x = convert(data[0] << 8 | data[1]) / 16384.0
        accel_y = convert(data[2] << 8 | data[3]) / 16384.0
        accel_z = convert(data[4] << 8 | data[5]) / 16384.0
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("""
            UPDATE config
            SET offset_accel_x = ?, offset_accel_y = ?, offset_accel_z = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = 1
        """, (accel_x, accel_y, accel_z))
        conn.commit()
        conn.close()
        return "Calibrazione eseguita. Offset aggiornati."
    except Exception as e:
        return f"Errore durante la calibrazione: {str(e)}"

@app.route('/admin/clear_calibration', methods=['POST'])
def clear_calibration():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("""
            UPDATE config
            SET offset_accel_x = 0, offset_accel_y = 0, offset_accel_z = 0, updated_at = CURRENT_TIMESTAMP
            WHERE id = 1
        """)
        conn.commit()
        conn.close()
        return "Calibrazione resettata con successo."
    except Exception as e:
        return f"Errore durante il reset della calibrazione: {str(e)}"

@app.route('/admin/access_log')
def access_log():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    logs = query_db("SELECT * FROM access_log ORDER BY id DESC")
    logs = [dict(row) for row in logs]
    return render_template('access_log.html', logs=logs)

@app.route('/admin/whois')
def whois_lookup():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    ip = request.args.get('ip')
    if not ip:
        return "IP mancante."
    try:
        result = subprocess.run(["whois", ip], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=10)
        output = result.stdout if result.stdout else result.stderr
        return f"<pre>{output}</pre>"
    except Exception as e:
        return f"Errore nel whois: {str(e)}"

@app.route('/admin/save_snapshot', methods=['POST'])
def save_snapshot():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    svg_data = request.form.get('svg_data')
    event_id = request.form.get('event_id')  # opzionale
    if not svg_data:
        return "Nessun dato SVG ricevuto."
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO event_snapshots (event_id, svg_data)
        VALUES (?, ?)
    """, (event_id if event_id else None, svg_data))
    conn.commit()
    conn.close()
    return "Snapshot salvato con successo."

@app.route('/admin/event_snapshots')
def event_snapshots():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    snapshots = query_db("SELECT * FROM event_snapshots ORDER BY id DESC")
    snapshots = [dict(row) for row in snapshots]
    return render_template('event_snapshots.html', snapshots=snapshots)

@app.route('/control')
def control():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    return render_template('control.html')

@app.route('/control/start')
def control_start():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    result = subprocess.run(["sudo", "systemctl", "start", "sismografo.service"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return f"Comando Start eseguito. Output: {result.stdout}\nError: {result.stderr}"

@app.route('/control/stop')
def control_stop():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    result = subprocess.run(["sudo", "systemctl", "stop", "sismografo.service"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return f"Comando Stop eseguito. Output: {result.stdout}\nError: {result.stderr}"

@app.route('/control/status')
def control_status():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    result = subprocess.run(["sudo", "systemctl", "status", "sismografo.service"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return f"Status del servizio:\n{result.stdout}"

@app.route('/control/backup')
def control_backup():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    result = subprocess.run(["/usr/bin/python3", "/home/pi/backup.py"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return f"Backup manuale eseguito. Output: {result.stdout}\nError: {result.stderr}"

@app.route('/test_notification')
def test_notification():
    config = query_db("SELECT telegram_bot_token, telegram_chat_id, notifiche_abilitate FROM config WHERE id = 1", one=True)
    if config and config["notifiche_abilitate"]:
        token = config["telegram_bot_token"]
        chat_id = config["telegram_chat_id"]
        if token and chat_id:
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            response = requests.post(url, data={"chat_id": chat_id, "text": "Test Notifica: il sistema sismografo è attivo."})
            if response.status_code == 200:
                return "Notifica di test inviata!"
            else:
                return f"Errore nell'invio della notifica: {response.text}"
        else:
            return "Token o Chat ID non configurati."
    else:
        return "Notifiche automatiche disabilitate."

@app.route('/data')
def data():
    limit = request.args.get('limit', default=100, type=int)
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    query = "SELECT id, timestamp, accel_x, accel_y, accel_z, gyro_x, gyro_y, gyro_z FROM dati_grezzi"
    params = []
    if start_date and end_date:
        query += " WHERE timestamp BETWEEN ? AND ?"
        params.extend([start_date, end_date])
    query += " ORDER BY id ASC LIMIT ?"
    params.append(limit)
    rows = query_db(query, params)
    data = [dict(row) for row in rows]
    return jsonify(data)

@app.route('/events')
def events():
    limit = request.args.get('limit', default=50, type=int)
    event_type = request.args.get('type')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    query = "SELECT timestamp, tipo, valore, descrizione FROM eventi_anomali"
    params = []
    filters = []
    if event_type:
        filters.append("tipo = ?")
        params.append(event_type)
    if start_date and end_date:
        filters.append("timestamp BETWEEN ? AND ?")
        params.extend([start_date, end_date])
    if filters:
        query += " WHERE " + " AND ".join(filters)
    query += " ORDER BY id DESC LIMIT ?"
    params.append(limit)
    rows = query_db(query, params)
    events = [dict(row) for row in rows]
    return jsonify(events)

@app.route('/export/csv')
def export_csv():
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    query = "SELECT * FROM dati_grezzi"
    params = []
    if start_date and end_date:
        query += " WHERE timestamp BETWEEN ? AND ?"
        params.extend([start_date, end_date])
    rows = query_db(query, params)
    
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["id", "timestamp", "accel_x", "accel_y", "accel_z", "gyro_x", "gyro_y", "gyro_z"])
    for row in rows:
        writer.writerow([row["id"], row["timestamp"], row["accel_x"], row["accel_y"], row["accel_z"], row["gyro_x"], row["gyro_y"], row["gyro_z"]])
    output.seek(0)
    
    return Response(output.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment;filename=dati_grezzi.csv"})

@app.route('/export/json')
def export_json():
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    query = "SELECT * FROM dati_grezzi"
    params = []
    if start_date and end_date:
        query += " WHERE timestamp BETWEEN ? AND ?"
        params.extend([start_date, end_date])
    rows = query_db(query, params)
    data = [dict(row) for row in rows]
    return jsonify(data)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)

