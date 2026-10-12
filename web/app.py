"""Flask dashboard with SQLite for local development and Azure SQL for deployment."""
import os
import sqlite3
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path

from flask import Flask, abort, flash, redirect, render_template_string, request, url_for

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "local-only-change-me")
DEVICE_ID = os.getenv("DEVICE_ID", "raspberrypi-01")
SQL_CONNECTION_STRING = os.getenv("SQL_CONNECTION_STRING", "").strip()
DB_PATH = Path(__file__).with_name("iotmonitor.db")

HTML = r"""
<!doctype html>
<html lang="fi">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Raspberry Pi IoT Monitor</title>
<style>
:root{font-family:system-ui,-apple-system,Segoe UI,sans-serif;color:#172033;background:#f4f6fa}
body{margin:0}.wrap{max-width:1050px;margin:auto;padding:28px 18px}
header{display:flex;justify-content:space-between;align-items:center;gap:16px;flex-wrap:wrap}
h1{font-size:1.7rem;margin:0} .muted{color:#5e6b80}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:14px;margin:22px 0}
.card,section{background:white;border:1px solid #e1e6ef;border-radius:14px;padding:18px;box-shadow:0 2px 8px #17203308}
.metric{font-size:2rem;font-weight:700;margin-top:8px}.two{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:14px}
label{display:block;font-size:.9rem;margin:12px 0 5px}input{width:100%;box-sizing:border-box;padding:10px;border:1px solid #cbd3df;border-radius:8px}
button{background:#2157c5;color:white;border:0;border-radius:8px;padding:10px 14px;margin-top:12px;cursor:pointer}
table{width:100%;border-collapse:collapse;margin-top:10px}th,td{text-align:left;padding:10px 8px;border-bottom:1px solid #e7ebf2;font-size:.9rem}
.tablewrap{overflow-x:auto}.notice{padding:10px 12px;background:#eaf4ff;border-radius:8px;margin:12px 0}.footer{margin-top:22px;font-size:.85rem}
</style></head><body><div class="wrap">
<header><div><h1>Raspberry Pi IoT Monitor</h1><div class="muted">Lämpötila- ja kosteusmittaukset</div></div>
<div class="muted">Laite: {{ device.name }} · {{ device.device_id }}</div></header>
{% for message in messages %}<div class="notice">{{ message }}</div>{% endfor %}
<div class="grid">
<div class="card"><div class="muted">Viimeisin lämpötila</div><div class="metric">{{ latest.temperature if latest and latest.temperature is not none else '—' }}{% if latest and latest.temperature is not none %} °C{% endif %}</div></div>
<div class="card"><div class="muted">Viimeisin kosteus</div><div class="metric">{{ latest.humidity if latest and latest.humidity is not none else '—' }}{% if latest and latest.humidity is not none %} %{% endif %}</div></div>
<div class="card"><div class="muted">Viimeisin mittaus</div><div style="font-weight:600;margin-top:12px">{{ latest.measured_at if latest else 'Ei mittauksia' }}</div><div class="muted">{{ latest.source if latest else '' }}</div></div>
</div>
<div class="two">
<section><h2>Kirjaa mittaus</h2><form method="post" action="{{ url_for('manual') }}">
<label for="temperature">Lämpötila (°C), valinnainen</label><input id="temperature" name="temperature" type="number" step="0.1" min="-50" max="100">
<label for="humidity">Suhteellinen kosteus (%), valinnainen</label><input id="humidity" name="humidity" type="number" step="0.1" min="0" max="100">
<button type="submit">Tallenna mittaus</button></form></section>
<section><h2>Laitteen asetukset</h2><form method="post" action="{{ url_for('settings') }}">
<label for="name">Laitteen nimi</label><input id="name" name="name" maxlength="200" required value="{{ device.name }}">
<label for="interval">Mittausväli (sekuntia, 5–86400)</label><input id="interval" name="interval" type="number" min="5" max="86400" required value="{{ device.interval }}">
<label for="retention">Säilytys (päivää, 1–3650)</label><input id="retention" name="retention" type="number" min="1" max="3650" required value="{{ device.retention }}">
<button type="submit">Tallenna asetukset</button></form>
<p class="muted">Asetukset tallentuvat tietokantaan. Mittausväli ei vielä päivity automaattisesti käynnissä olevaan Raspberry Pi -ohjelmaan.</p></section>
</div>
<section style="margin-top:14px"><h2>Viimeisimmät mittaukset</h2><div class="tablewrap"><table><thead><tr><th>Aika (UTC)</th><th>Lämpötila</th><th>Kosteus</th><th>Lähde</th></tr></thead><tbody>
{% for m in measurements %}<tr><td>{{ m.measured_at }}</td><td>{{ m.temperature if m.temperature is not none else '—' }}{% if m.temperature is not none %} °C{% endif %}</td><td>{{ m.humidity if m.humidity is not none else '—' }}{% if m.humidity is not none %} %{% endif %}</td><td>{{ m.source }}</td></tr>{% else %}<tr><td colspan="4">Mittauksia ei vielä ole.</td></tr>{% endfor %}
</tbody></table></div></section>
<div class="footer muted">Kehitysversion käyttöliittymä. Ota alustan kirjautuminen käyttöön ennen internet-julkaisua.</div>
</div></body></html>
"""


def auth_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        production = os.getenv("APP_ENV", "development").lower() == "production"
        auth_enabled = os.getenv("AUTH_ENABLED", "false").lower() == "true"
        if production and not auth_enabled:
            abort(503, description="Set AUTH_ENABLED=true and configure App Service Authentication.")
        if production and not request.headers.get("X-MS-CLIENT-PRINCIPAL"):
            abort(401, description="Sign in through App Service Authentication.")
        return view(*args, **kwargs)
    return wrapped


def local_connection():
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def init_sqlite():
    with local_connection() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS Devices (
            DeviceId TEXT PRIMARY KEY, Name TEXT NOT NULL, Enabled INTEGER NOT NULL DEFAULT 1,
            SamplingIntervalSeconds INTEGER NOT NULL DEFAULT 60, RetentionDays INTEGER NOT NULL DEFAULT 90,
            LastSeenAt TEXT, CreatedAt TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS Measurements (
            Id INTEGER PRIMARY KEY AUTOINCREMENT, DeviceId TEXT NOT NULL,
            TemperatureC REAL, HumidityPercent REAL, MeasuredAt TEXT NOT NULL,
            ReceivedAt TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, Source TEXT NOT NULL DEFAULT 'sensor',
            CHECK (TemperatureC IS NOT NULL OR HumidityPercent IS NOT NULL),
            CHECK (TemperatureC IS NULL OR TemperatureC BETWEEN -50 AND 100),
            CHECK (HumidityPercent IS NULL OR HumidityPercent BETWEEN 0 AND 100),
            CHECK (Source IN ('sensor','manual'))
        );
        CREATE INDEX IF NOT EXISTS IX_Measurements_Device_MeasuredAt ON Measurements(DeviceId, MeasuredAt DESC);
        """)
        con.execute(
            "INSERT OR IGNORE INTO Devices(DeviceId, Name) VALUES (?, ?)",
            (DEVICE_ID, "Raspberry Pi 1"),
        )


def get_device():
    if SQL_CONNECTION_STRING:
        import pyodbc
        with pyodbc.connect(SQL_CONNECTION_STRING, timeout=10) as con:
            row = con.cursor().execute(
                "SELECT DeviceId, Name, SamplingIntervalSeconds, RetentionDays FROM dbo.Devices WHERE DeviceId = ?",
                DEVICE_ID).fetchone()
            if row is None:
                con.cursor().execute("INSERT INTO dbo.Devices (DeviceId, Name) VALUES (?, ?)", DEVICE_ID, "Raspberry Pi 1")
                con.commit()
                return {"device_id": DEVICE_ID, "name": "Raspberry Pi 1", "interval": 60, "retention": 90}
            return {"device_id": row[0], "name": row[1], "interval": row[2], "retention": row[3]}
    with local_connection() as con:
        row = con.execute("SELECT * FROM Devices WHERE DeviceId=?", (DEVICE_ID,)).fetchone()
        return {"device_id": row["DeviceId"], "name": row["Name"], "interval": row["SamplingIntervalSeconds"], "retention": row["RetentionDays"]}


def get_measurements(limit=100):
    if SQL_CONNECTION_STRING:
        import pyodbc
        with pyodbc.connect(SQL_CONNECTION_STRING, timeout=10) as con:
            rows = con.cursor().execute(
                """SELECT TOP (?) TemperatureC, HumidityPercent, MeasuredAt, Source
                   FROM dbo.Measurements WHERE DeviceId=? ORDER BY MeasuredAt DESC""",
                limit, DEVICE_ID).fetchall()
    else:
        with local_connection() as con:
            rows = con.execute(
                """SELECT TemperatureC, HumidityPercent, MeasuredAt, Source FROM Measurements
                   WHERE DeviceId=? ORDER BY MeasuredAt DESC LIMIT ?""", (DEVICE_ID, limit)).fetchall()
    return [{"temperature": row[0], "humidity": row[1], "measured_at": str(row[2]), "source": row[3]} for row in rows]


def insert_measurement(temperature, humidity, source):
    measured_at = datetime.now(timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds")
    if SQL_CONNECTION_STRING:
        import pyodbc
        with pyodbc.connect(SQL_CONNECTION_STRING, timeout=10) as con:
            cur = con.cursor()
            cur.execute("IF NOT EXISTS (SELECT 1 FROM dbo.Devices WHERE DeviceId=?) INSERT INTO dbo.Devices (DeviceId, Name) VALUES (?, ?)",
                        DEVICE_ID, DEVICE_ID, "Raspberry Pi 1")
            cur.execute("""INSERT INTO dbo.Measurements(DeviceId, TemperatureC, HumidityPercent, MeasuredAt, Source)
                           VALUES (?, ?, ?, ?, ?)""", DEVICE_ID, temperature, humidity, measured_at, source)
            con.commit()
    else:
        with local_connection() as con:
            con.execute("INSERT OR IGNORE INTO Devices(DeviceId, Name) VALUES (?, ?)", (DEVICE_ID, "Raspberry Pi 1"))
            con.execute("""INSERT INTO Measurements(DeviceId, TemperatureC, HumidityPercent, MeasuredAt, Source)
                            VALUES (?, ?, ?, ?, ?)""", (DEVICE_ID, temperature, humidity, measured_at, source))


def update_settings(name, interval, retention):
    if SQL_CONNECTION_STRING:
        import pyodbc
        with pyodbc.connect(SQL_CONNECTION_STRING, timeout=10) as con:
            con.cursor().execute("""IF NOT EXISTS (SELECT 1 FROM dbo.Devices WHERE DeviceId=?)
                INSERT INTO dbo.Devices (DeviceId, Name) VALUES (?, ?);
                UPDATE dbo.Devices SET Name=?, SamplingIntervalSeconds=?, RetentionDays=? WHERE DeviceId=?""",
                DEVICE_ID, DEVICE_ID, name, name, interval, retention, DEVICE_ID)
            con.commit()
    else:
        with local_connection() as con:
            con.execute("""INSERT OR IGNORE INTO Devices(DeviceId, Name) VALUES (?, ?)""", (DEVICE_ID, name))
            con.execute("""UPDATE Devices SET Name=?, SamplingIntervalSeconds=?, RetentionDays=? WHERE DeviceId=?""",
                        (name, interval, retention, DEVICE_ID))


@app.route("/", methods=["GET"])
@auth_required
def index():
    device = get_device()
    measurements = get_measurements()
    messages = request.args.getlist("message")
    return render_template_string(HTML, device=device, measurements=measurements,
                                  latest=measurements[0] if measurements else None, messages=messages)


@app.route("/manual", methods=["POST"])
@auth_required
def manual():
    try:
        temp_raw = request.form.get("temperature", "").strip()
        humidity_raw = request.form.get("humidity", "").strip()
        temperature = float(temp_raw) if temp_raw else None
        humidity = float(humidity_raw) if humidity_raw else None
        if temperature is None and humidity is None:
            raise ValueError("Anna vähintään lämpötila tai kosteus.")
        if temperature is not None and not -50 <= temperature <= 100:
            raise ValueError("Lämpötilan pitää olla välillä -50–100 °C.")
        if humidity is not None and not 0 <= humidity <= 100:
            raise ValueError("Kosteuden pitää olla välillä 0–100 %.")
        insert_measurement(temperature, humidity, "manual")
        message = "Mittaus tallennettiin."
    except (ValueError, TypeError) as exc:
        message = str(exc) or "Virheellinen mittaus."
    return redirect(url_for("index", message=message))


@app.route("/settings", methods=["POST"])
@auth_required
def settings():
    try:
        name = request.form.get("name", "").strip()
        interval = int(request.form.get("interval", "60"))
        retention = int(request.form.get("retention", "90"))
        if not name or len(name) > 200:
            raise ValueError("Anna laitteen nimi (enintään 200 merkkiä).")
        if not 5 <= interval <= 86400:
            raise ValueError("Mittausvälin pitää olla 5–86400 sekuntia.")
        if not 1 <= retention <= 3650:
            raise ValueError("Säilytysajan pitää olla 1–3650 päivää.")
        update_settings(name, interval, retention)
        message = "Asetukset tallennettiin."
    except (ValueError, TypeError) as exc:
        message = str(exc) or "Virheelliset asetukset."
    return redirect(url_for("index", message=message))


init_sqlite()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.getenv("PORT", "5000")), debug=False)
