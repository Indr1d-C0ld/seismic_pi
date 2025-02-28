from flask import Flask, render_template, jsonify, request, Response, redirect, url_for
import sqlite3
import csv
import io
import requests

app = Flask(__name__)
DB_PATH = "sismografo.db"

def query_db(query, args=(), one=False):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(query, args)
    rv = cur.fetchall()
    conn.close()
    return (rv[0] if rv else None) if one else rv

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

# Rotta per aggiornare la configurazione (Admin)
@app.route('/admin', methods=['GET', 'POST'])
def admin():
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
        
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("""
            UPDATE config 
            SET accel_threshold = ?, gyro_threshold = ?, sample_interval = ?, visualization_mode = ?, chart_buffer = ?, data_retention = ?, telegram_bot_token = ?, telegram_chat_id = ?, notifiche_abilitate = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = 1
        """, (accel_threshold, gyro_threshold, sample_interval, visualization_mode, chart_buffer, data_retention, telegram_bot_token, telegram_chat_id, notifiche_abilitate))
        conn.commit()
        conn.close()
        return redirect(url_for('admin'))
    else:
        config = query_db("SELECT * FROM config WHERE id = 1", one=True)
        config = dict(config) if config else {}
        return render_template('admin.html', config=config)

# Rotta per testare la notifica Telegram
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

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)

