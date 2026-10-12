# Virtual Gateway Devices

A lightweight, edge-ready **Modbus TCP multi-device simulator and IoT gateway emulator** built with Python, FastAPI, and `pymodbus`.

It acts as an active industrial gateway on edge hardware or local development environments, simulating real sensor physics, exposing standard Modbus TCP registers, and streaming formatted telemetry to cloud and edge ingestion platforms.

---

## 🚀 Why is it Useful?

Testing edge telemetry pipelines, SCADA systems, PLC pollers, and cloud time-series ingestion normally requires physical hardware (smart energy meters, HVAC controllers, modems, PLCs) that are expensive, cumbersome to set up, and difficult to test under edge-case conditions.

**Virtual Gateway Devices** solves this by providing a complete, turnkey simulation and gateway bridge:

### 1. 🌐 Acts as an Edge IoT Gateway & Modbus Server
- Runs on edge devices (Raspberry Pi, industrial IPCs, edge routers, or local dev machines) alongside gateway collection software.
- Listens on standard **Modbus TCP** (port `5020`) so local gateway daemons, Telegraf, Node-RED, or custom polling scripts can interact with it exactly like physical hardware.
- Simultaneously exposes a **FastAPI REST API and Web Dashboard** (port `8080`) for real-time monitoring and headless integration.

### 2. ➕ Add & Remove Simulated Devices on the Fly
- You are not limited to fixed, hardcoded devices.
- Add new devices at runtime directly from the Web UI (**"➕ Add Device"** modal) or programmatically via `POST /api/devices`.
- Automatically assigns the next available Slave ID (1..247) or accepts custom IDs.
- Asynchronously launches independent physics simulation loops for newly added devices without requiring a server restart.
- Remove devices cleanly with a single click or API call.

### 3. 🎛️ Interactive Custom Device Cards
- Each simulated device gets its own dedicated faceplate card in the Web UI:
  - **⚡ Energy Meter**: High-contrast LCD faceplate showing Live Voltage, Active Power, Current, Grid Frequency, an animated odometer for cumulative kWh, and threshold alert banners.
  - **❄️ HVAC Thermostat**: Circular thermostat dial showing ambient temperature, target setpoint, animated fan state, cooling fan toggle switch, and increment/decrement buttons.
- Real-time two-way control: Toggle coils (fan relays) or adjust holding registers (temperature setpoints) directly through the card UI or over Modbus TCP write commands.

### 4. 📡 Configurable Stream Point Paths
- In modern IoT platforms, data is digested using hierarchical point paths (e.g., `/gateway-01/device-01/Current` or `/plant-north/meter-42/Voltage`).
- Each device card includes an editable **Point Path** input field (e.g., `/gateway-01/meter-01`).
- Custom paths automatically propagate to all underlying metrics for that device, enabling instant mapping to whatever schema your ingestion pipeline expects.

### 5. 📦 Standard Ingestion Payload Format & Live Preview
- Prepares telemetry directly in the standard nested-array stream format:
  ```json
  {
    "/gateway-01/meter-01/Voltage": [[230.2]],
    "/gateway-01/meter-01/ActivePower": [[3.45]],
    "/gateway-01/meter-01/Current": [[15.01]],
    "/gateway-01/meter-01/Frequency": [[50.01]],
    "/gateway-01/meter-01/TotalEnergy": [[12.345]],
    "/gateway-01/hvac-02/Temperature": [[24.5]],
    "/gateway-01/hvac-02/TargetSetpoint": [[22.0]],
    "/gateway-01/hvac-02/FanRelay": [[false]],
    "/gateway-01/hvac-02/Mode": [["HEATING"]],
    "url": "https://your-platform.com/api/v1/telemetry",
    "key": "your-api-key"
  }
  ```
- **Live Outgoing Telemetry Packet**: The dashboard displays a scrollable preview of the current second's packet, updating in real time without cluttering or overflowing the screen.

### 6. ⏱️ Configurable Cloud / Edge Platform Sync
- Push data directly to your ingestion endpoint with a target HTTPS URL and Access Key.
- Custom sync interval (in seconds) with convenient presets (**1s, 2s, 5s, 10s, 30s, 60s / 1 min, 120s / 2 min, 300s / 5 min**).
- When syncing is active, the simulator buffers readings and transmits batch arrays (`[[val1], [val2], ...]`) over the specified sync window.

### 7. 🪶 Zero Heavy Overhead & Edge-Friendly
- Built with pure Python, standard FastAPI, and pymodbus.
- No heavy databases, Redis, or Webpack/npm build steps.
- Minimal CPU and memory footprint, making it ideal for low-spec industrial hardware.

---

## 📊 Modbus Register Specifications

All 32-bit floats use standard **Big-Endian byte order** across two consecutive 16-bit registers (`>HH` to `>f`).

### 1. Electrical Energy Meter (Slave ID: 1, 3, ...)
| Register Address | Modbus Type | Data Type | Metric | Description |
| :--- | :--- | :--- | :--- | :--- |
| **Holding Reg 0-1** | FC 03 | `Float32` | Voltage | Line voltage (~230V ± 2V) |
| **Holding Reg 2-3** | FC 03 | `Float32` | Active Power | Active power consumption (kW) |
| **Holding Reg 4-5** | FC 03 | `Float32` | Current | Calculated current load (Amps) |
| **Holding Reg 6-7** | FC 03 | `Float32` | Frequency | Grid frequency (~50.0 Hz) |
| **Holding Reg 8-9** | FC 03 | `Float32` | Total Energy | Cumulative energy odometer (kWh) |

### 2. HVAC Temperature Controller (Slave ID: 2, 4, ...)
| Register Address | Modbus Type | Data Type | Metric | Description |
| :--- | :--- | :--- | :--- | :--- |
| **Coil 0** | FC 01 / FC 05 | `Boolean` | Fan Relay | `1` = ON (Cooling), `0` = OFF (Heating) |
| **Holding Reg 0-1** | FC 03 | `Float32` | Temperature | Current ambient room temperature (°C) |
| **Holding Reg 2-3** | FC 03 / FC 16 | `Float32` | Setpoint | Target temperature setpoint (°C) |

---

## ⚡ Quickstart

### 1. Installation
Requires Python 3.10+:

```bash
# Clone the repository
git clone https://github.com/varunsaral/virtual-gateway-devices.git
cd virtual-gateway-devices

# Set up virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -e ".[dev]"
```

### 2. Run the Simulator
Start the simulator with default bindings (Modbus TCP on `5020`, Web UI on `8080`):

```bash
# Direct module invocation
python -m device_simulator

# Or using the console CLI command with custom flags
device-simulator --host 127.0.0.1 --port 5020 --http-host 127.0.0.1 --http-port 8080 --log-level INFO
```

- **Web Dashboard**: [http://127.0.0.1:8080](http://127.0.0.1:8080)
- **Interactive REST API Docs (Swagger)**: [http://127.0.0.1:8080/api/docs](http://127.0.0.1:8080/api/docs)
- **Modbus TCP Endpoint**: `127.0.0.1:5020`

### 3. Test with a Modbus Client
Run the provided example client script to read registers and toggle coils over Modbus TCP:

```bash
python examples/client_example.py
```

### 4. Run Test Suite
```bash
pytest
```

---

## 🔌 REST API Endpoints

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/api/device-types` | Catalog of available device models that can be added |
| `GET` | `/api/devices` | Live telemetry readings, statuses, and metadata for all active devices |
| `POST` | `/api/devices` | Dynamically create a device (`{"device_type": "energy_meter", "slave_id": 3, "stream_path": "/gateway-01/meter-03"}`) |
| `DELETE` | `/api/devices/{slave_id}` | Dynamically remove a device and unbind its registers |
| `GET` | `/api/streams` | Flattened stream points dictionary formatted for platform ingestion |
| `POST` | `/api/devices/path` | Update base point path prefix for a device |
| `POST` | `/api/hvac/fan` | Toggle HVAC cooling fan coil (`{"slave_id": 2, "fan_on": true}`) |
| `POST` | `/api/hvac/setpoint` | Update HVAC target setpoint (`{"slave_id": 2, "target_setpoint": 21.5}`) |
