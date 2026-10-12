import importlib.util
from pathlib import Path


def test_read_sensor_returns_plausible_values():
    path = Path(__file__).parents[1] / "device" / "send_telemetry.py"
    spec = importlib.util.spec_from_file_location("send_telemetry", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    temperature, humidity = module.read_sensor()
    assert -50 <= temperature <= 100
    assert 0 <= humidity <= 100
