"""Azure Functions Python v2: persist IoT Hub telemetry to Azure SQL."""
import json
import logging
import os
from datetime import datetime, timezone

import azure.functions as func
import pyodbc

app = func.FunctionApp()


def parse_timestamp(value):
    if not value:
        return datetime.now(timezone.utc).replace(tzinfo=None)
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


@app.event_hub_message_trigger(
    arg_name="event",
    event_hub_name="messages/events",
    connection="IOTHUB_EVENTHUB_CONNECTION",
    consumer_group="$Default",
)
def persist_telemetry(event: func.EventHubEvent):
    raw = event.get_body().decode("utf-8")
    try:
        payload = json.loads(raw)
        device_id = str(payload["device_id"])
        temperature = payload.get("temperature_c")
        humidity = payload.get("humidity_percent")
        measured_at = parse_timestamp(payload.get("measured_at"))
        if temperature is None and humidity is None:
            raise ValueError("At least one measurement value is required.")
        if temperature is not None and not -50 <= float(temperature) <= 100:
            raise ValueError("temperature_c is outside the accepted range.")
        if humidity is not None and not 0 <= float(humidity) <= 100:
            raise ValueError("humidity_percent is outside the accepted range.")
    except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        logging.exception("Ignoring invalid telemetry payload: %s", exc)
        return

    connection_string = os.getenv("SQL_CONNECTION_STRING")
    if not connection_string:
        raise RuntimeError("SQL_CONNECTION_STRING application setting is missing.")

    with pyodbc.connect(connection_string, timeout=10) as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            IF NOT EXISTS (SELECT 1 FROM dbo.Devices WHERE DeviceId = ?)
                INSERT INTO dbo.Devices (DeviceId, Name) VALUES (?, ?);
            INSERT INTO dbo.Measurements
                (DeviceId, TemperatureC, HumidityPercent, MeasuredAt, Source)
            VALUES (?, ?, ?, ?, 'sensor');
            UPDATE dbo.Devices SET LastSeenAt = SYSUTCDATETIME() WHERE DeviceId = ?;
            """,
            device_id, device_id, device_id,
            device_id, temperature, humidity, measured_at, device_id,
        )
        connection.commit()
    logging.info("Stored telemetry for device %s", device_id)
