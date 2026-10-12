import asyncio
import logging
from typing import Dict, List, Optional, Sequence, Type

from pymodbus.datastore import ModbusServerContext

from device_simulator.base_device import VirtualDevice
from device_simulator.energy_meter import MainEnergyMeter
from device_simulator.hvac import HVACTemperatureController

log = logging.getLogger(__name__)

DEVICE_REGISTRY: Dict[str, Type[VirtualDevice]] = {
    "energy_meter": MainEnergyMeter,
    "hvac": HVACTemperatureController,
    "hvac_controller": HVACTemperatureController,
}

AVAILABLE_DEVICE_TYPES = [
    {
        "type": "energy_meter",
        "name": "⚡ Electrical Energy Meter",
        "description": "3-phase power, voltage, current, frequency, and cumulative energy consumption (Holding Registers 0-9)",
        "default_prefix": "/gateway-01/meter",
    },
    {
        "type": "hvac",
        "name": "❄️ HVAC Temperature Controller",
        "description": "Room temperature thermostat with cooling fan relay coil and target setpoint (Coil 0, Holding Registers 0-3)",
        "default_prefix": "/gateway-01/hvac",
    },
]


class DeviceManager:
    """Manages virtual devices, their Modbus server datastores, and physics tasks."""

    def __init__(self, devices: Sequence[VirtualDevice], context: ModbusServerContext):
        self.devices: List[VirtualDevice] = list(devices)
        self.context = context
        self.tasks: Dict[int, asyncio.Task] = {}

    def start_all(self) -> None:
        """Start physics loops for all devices."""
        try:
            loop = asyncio.get_running_loop()
            for dev in self.devices:
                if dev.slave_id not in self.tasks:
                    self.tasks[dev.slave_id] = loop.create_task(dev.run_simulation())
        except RuntimeError:
            pass

    def get_next_slave_id(self) -> int:
        """Return the lowest available Slave ID (1..247)."""
        existing = {dev.slave_id for dev in self.devices}
        for sid in range(1, 248):
            if sid not in existing:
                return sid
        raise ValueError("Maximum number of Modbus slaves reached (247)")

    def add_device(
        self,
        device_type: str,
        slave_id: Optional[int] = None,
        stream_path: Optional[str] = None,
        **kwargs,
    ) -> VirtualDevice:
        """Dynamically add and start a new device at runtime."""
        cls = DEVICE_REGISTRY.get(device_type.lower())
        if not cls:
            raise ValueError(
                f"Unknown device type '{device_type}'. Available: {list(DEVICE_REGISTRY.keys())}"
            )

        if slave_id is None:
            slave_id = self.get_next_slave_id()
        else:
            slave_id = int(slave_id)
            if any(d.slave_id == slave_id for d in self.devices):
                raise ValueError(f"Slave ID {slave_id} is already in use")

        if not stream_path:
            prefix = "meter" if cls is MainEnergyMeter else "hvac"
            stream_path = f"/gateway-01/{prefix}-{slave_id:02d}"

        # Instantiate device
        dev = cls(slave_id=slave_id, stream_path=stream_path, **kwargs)

        # Wire into Modbus Server Context
        self.context[dev.slave_id] = dev.store
        self.devices.append(dev)

        # Start simulation loop in background if event loop is running
        try:
            loop = asyncio.get_running_loop()
            self.tasks[dev.slave_id] = loop.create_task(dev.run_simulation())
        except RuntimeError:
            pass

        log.info(
            "➕ Added dynamic device: %s (Slave ID: %d, Path: %s)",
            dev.__class__.__name__,
            dev.slave_id,
            dev.stream_path,
        )
        return dev

    def remove_device(self, slave_id: int) -> bool:
        """Remove a device and stop its simulation task."""
        dev = next((d for d in self.devices if d.slave_id == slave_id), None)
        if not dev:
            return False

        # Cancel background task
        task = self.tasks.pop(slave_id, None)
        if task:
            task.cancel()

        # Remove from Modbus context
        self.context._slaves.pop(slave_id, None)
        self.devices.remove(dev)
        log.info("➖ Removed device Slave ID %d (%s)", slave_id, dev.__class__.__name__)
        return True

    def get_all_readings(self) -> Dict:
        """Get readings and metadata for all active devices."""
        device_list = []
        for dev in self.devices:
            readings = dev.get_readings()
            device_list.append(
                {
                    "slave_id": dev.slave_id,
                    "device_type": dev.device_type,
                    "name": (
                        f"⚡ Energy Meter #{dev.slave_id}"
                        if dev.device_type == "energy_meter"
                        else f"❄️ HVAC Thermostat #{dev.slave_id}"
                    ),
                    "stream_path": dev.stream_path,
                    "readings": readings,
                }
            )

        # Assemble full telemetry payload
        telemetry = {"devices": device_list}
        # Backward compatibility for first meter and hvac
        meter = next((d for d in self.devices if d.device_type == "energy_meter"), None)
        hvac = next((d for d in self.devices if d.device_type == "hvac"), None)
        if meter:
            telemetry["energy_meter"] = meter.get_readings()
        if hvac:
            telemetry["hvac_controller"] = hvac.get_readings()
        return telemetry

    def get_all_streams(
        self, batch: bool = True, url: str = "", key: str = ""
    ) -> Dict:
        """Gather flattened stream mapping across all devices."""
        streams = {}
        for dev in self.devices:
            readings = dev.get_readings()
            if "points" in readings:
                for path, val in readings["points"].items():
                    streams[path] = [[val]] if batch else val
        streams["url"] = url
        streams["key"] = key
        return streams

    def stop_all(self) -> None:
        """Cancel all running simulation tasks."""
        for task in self.tasks.values():
            task.cancel()
