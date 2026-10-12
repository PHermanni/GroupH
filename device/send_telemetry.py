"""Send simulated telemetry to Azure IoT Hub. Replace read_sensor() for real hardware."""
import json
import logging
import os
import random
import time
from datetime import datetime, timezone

from azure.iot.device import IoTHubDeviceClient, Message

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("iot-device")


def read_sensor():
    """Return simulated readings; replace with BME280 or another sensor when ready."""
    return round(random.uniform(19.0, 26.0), 2), round(random.uniform(30.0, 65.0), 2)


def main():
    connection_string = os.getenv("IOTHUB_DEVICE_CONNECTION_STRING")
    if not connection_string:
        raise SystemExit("Set IOTHUB_DEVICE_CONNECTION_STRING before running.")
    device_id = os.getenv("DEVICE_ID", "raspberrypi-01")
    interval = max(5, int(os.getenv("SAMPLE_INTERVAL_SECONDS", "60")))
    client = IoTHubDeviceClient.create_from_connection_string(connection_string)

    try:
        client.connect()
        log.info("Connected as %s; sending simulated readings every %s seconds.", device_id, interval)
        while True:
            temperature, humidity = read_sensor()
            payload = {
                "device_id": device_id,
                "temperature_c": temperature,
                "humidity_percent": humidity,
                "measured_at": datetime.now(timezone.utc).isoformat(),
            }
            message = Message(json.dumps(payload))
            message.content_type = "application/json"
            message.content_encoding = "utf-8"
            client.send_message(message)
            log.info("Telemetry sent: temperature=%s C humidity=%s %%", temperature, humidity)
            time.sleep(interval)
    except KeyboardInterrupt:
        log.info("Stopped by user.")
    finally:
        client.shutdown()


if __name__ == "__main__":
    main()
