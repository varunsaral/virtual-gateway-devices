import pytest
from device_simulator import (
    HVACTemperatureController,
    MainEnergyMeter,
    VirtualDevice,
    create_server_context,
)


def test_virtual_device_float_packing():
    dev = VirtualDevice(slave_id=10)
    dev.write_floats(0, [230.5, 42.125])
    floats = dev.read_floats(0, count=2)
    assert pytest.approx(floats[0], rel=1e-3) == 230.5
    assert pytest.approx(floats[1], rel=1e-3) == 42.125


def test_virtual_device_coil_operations():
    dev = VirtualDevice(slave_id=10)
    dev.write_coils(0, [True, False, True])
    coils = dev.read_coils(0, count=3)
    assert coils == [True, False, True]


def test_energy_meter_step():
    meter = MainEnergyMeter(slave_id=1)
    voltage, active_kw, current_a, freq, total_kwh = meter.step(t=0)
    assert 225.0 <= voltage <= 235.0
    assert 15.0 <= active_kw <= 35.0
    assert current_a > 0.0
    assert 49.5 <= freq <= 50.5
    assert total_kwh > 0.0

    # Read back from registers to verify packing
    readings = meter.read_floats(0, count=5)
    assert pytest.approx(readings[0], rel=1e-3) == voltage
    assert pytest.approx(readings[1], rel=1e-3) == active_kw
    assert pytest.approx(readings[2], rel=1e-3) == current_a
    assert pytest.approx(readings[3], rel=1e-3) == freq
    assert pytest.approx(readings[4], rel=1e-3) == total_kwh


def test_hvac_cooling_and_heating():
    hvac = HVACTemperatureController(slave_id=2, initial_temp=28.0)

    # Fan OFF -> should heat up
    hvac.write_coils(0, [False])
    fan_is_on, temp = hvac.step()
    assert not fan_is_on
    assert temp == 28.8

    # Fan ON -> should cool down
    hvac.write_coils(0, [True])
    fan_is_on, temp = hvac.step()
    assert fan_is_on
    assert pytest.approx(temp, rel=1e-3) == 27.6


def test_create_server_context():
    meter = MainEnergyMeter(slave_id=1)
    hvac = HVACTemperatureController(slave_id=2)
    context = create_server_context([meter, hvac])

    # Context should contain both slaves
    assert 1 in context
    assert 2 in context


def test_device_get_readings():
    meter = MainEnergyMeter(slave_id=1)
    meter.step(t=0)
    data = meter.get_readings()
    assert data["slave_id"] == 1
    assert "voltage" in data
    assert "power_kw" in data
    assert "current_a" in data
    assert "freq_hz" in data
    assert "total_kwh" in data

    hvac = HVACTemperatureController(slave_id=2, initial_temp=25.0, target_setpoint=21.0)
    hvac_data = hvac.get_readings()
    assert hvac_data["slave_id"] == 2
    assert hvac_data["temperature"] == 25.0
    assert hvac_data["target_setpoint"] == 21.0
    assert hvac_data["fan_relay"] is False
    assert hvac_data["mode"] == "HEATING"


def test_hvac_control_methods():
    hvac = HVACTemperatureController(slave_id=2, initial_temp=25.0, target_setpoint=21.0)
    hvac.set_fan(True)
    assert hvac.read_coils(0, count=1) == [True]
    assert hvac.get_readings()["fan_relay"] is True
    assert hvac.get_readings()["mode"] == "COOLING"

    hvac.set_target(24.5)
    assert pytest.approx(hvac.read_floats(2, count=1)[0], rel=1e-3) == 24.5
    assert hvac.get_readings()["target_setpoint"] == 24.5


def test_fastapi_endpoints():
    from fastapi.testclient import TestClient
    from device_simulator.web_api import create_api_app

    meter = MainEnergyMeter(slave_id=1)
    meter.step(t=0)
    hvac = HVACTemperatureController(slave_id=2, initial_temp=24.0, target_setpoint=20.0)

    app = create_api_app([meter, hvac])
    client = TestClient(app)

    # Test GET /api/devices
    res = client.get("/api/devices")
    assert res.status_code == 200
    telemetry = res.json()
    assert "energy_meter" in telemetry
    assert "hvac_controller" in telemetry
    assert telemetry["energy_meter"]["slave_id"] == 1
    assert telemetry["hvac_controller"]["temperature"] == 24.0

    # Test POST /api/hvac/fan
    res_fan = client.post("/api/hvac/fan", json={"fan_on": True})
    assert res_fan.status_code == 200
    assert res_fan.json()["status"] == "ok"
    assert res_fan.json()["fan_relay"] is True
    assert hvac.get_readings()["fan_relay"] is True

    # Test POST /api/hvac/setpoint
    res_sp = client.post("/api/hvac/setpoint", json={"target_setpoint": 22.5})
    assert res_sp.status_code == 200
    assert res_sp.json()["status"] == "ok"
    assert res_sp.json()["target_setpoint"] == 22.5
    assert hvac.get_readings()["target_setpoint"] == 22.5

    # Verify updated state through /api/devices
    updated = client.get("/api/devices").json()
    assert updated["hvac_controller"]["fan_relay"] is True
    assert updated["hvac_controller"]["target_setpoint"] == 22.5

    # Test GET /api/streams
    res_streams = client.get("/api/streams", params={"url": "https://test.io", "key": "k123"})
    assert res_streams.status_code == 200
    streams = res_streams.json()
    assert "/gateway-01/device-01/Current" in streams
    assert "/gateway-01/device-01/Voltage" in streams
    assert "/gateway-01/device-02/Temperature" in streams
    assert streams["/gateway-01/device-02/TargetSetpoint"] == [[22.5]]
    assert streams["url"] == "https://test.io"
    assert streams["key"] == "k123"

    # Test POST /api/devices/path
    res_path = client.post(
        "/api/devices/path",
        json={"slave_id": 1, "stream_path": "/factory-east/line-1"},
    )
    assert res_path.status_code == 200
    assert res_path.json()["stream_path"] == "/factory-east/line-1"

    # Verify new stream path reflected in /api/streams
    updated_streams = client.get("/api/streams").json()
    assert "/factory-east/line-1/Current" in updated_streams
    assert "/gateway-01/device-01/Current" not in updated_streams


def test_device_manager_and_dynamic_endpoints():
    from fastapi.testclient import TestClient
    from device_simulator.device_manager import DeviceManager
    from device_simulator.server import create_server_context
    from device_simulator.web_api import create_api_app

    meter = MainEnergyMeter(slave_id=1)
    hvac = HVACTemperatureController(slave_id=2)
    context = create_server_context([meter, hvac])
    manager = DeviceManager([meter, hvac], context)

    # Test DeviceManager adding device
    new_meter = manager.add_device("energy_meter", slave_id=3, stream_path="/gateway-01/meter-03")
    assert new_meter.slave_id == 3
    assert 3 in context
    assert len(manager.devices) == 3

    # Test DeviceManager removing device
    assert manager.remove_device(3) is True
    assert 3 not in context
    assert len(manager.devices) == 2

    # Test FastAPI endpoints with DeviceManager
    app = create_api_app(manager)
    client = TestClient(app)

    # 1. GET /api/device-types
    res_types = client.get("/api/device-types")
    assert res_types.status_code == 200
    types = res_types.json()
    assert any(t["type"] == "energy_meter" for t in types)
    assert any(t["type"] == "hvac" for t in types)

    # 2. POST /api/devices (Add new HVAC slave 5)
    res_add = client.post(
        "/api/devices",
        json={"device_type": "hvac", "slave_id": 5, "stream_path": "/gateway-01/hvac-05"},
    )
    assert res_add.status_code == 200
    assert res_add.json()["slave_id"] == 5
    assert 5 in context

    # 3. Verify in GET /api/devices and GET /api/streams
    res_devs = client.get("/api/devices").json()
    assert any(d["slave_id"] == 5 for d in res_devs["devices"])

    streams = client.get("/api/streams").json()
    assert "/gateway-01/hvac-05/Temperature" in streams

    # 4. DELETE /api/devices/5
    res_del = client.delete("/api/devices/5")
    assert res_del.status_code == 200
    assert 5 not in context
    assert not any(d["slave_id"] == 5 for d in client.get("/api/devices").json()["devices"])

    manager.stop_all()
