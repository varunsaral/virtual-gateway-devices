import asyncio
import logging
from typing import Tuple

from device_simulator.base_device import VirtualDevice

log = logging.getLogger(__name__)


class HVACTemperatureController(VirtualDevice):
    """Simulates an HVAC Temperature Controller (Slave ID 2 by default).
    
    Register Map:
        Coils (FC 1 / FC 5):
            Address 0: Fan relay switch (True = ON / Cool, False = OFF / Heat)
        Holding Registers (FC 3):
            Address 0-1: Current Temperature (°C) [Float32]
            Address 2-3: Target Setpoint (°C) [Float32]
    """

    device_type: str = "hvac"

    def __init__(
        self,
        slave_id: int = 2,
        initial_temp: float = 28.0,
        target_setpoint: float = 22.0,
        interval_sec: float = 1.0,
        stream_path: str = "/gateway-01/device-02",
    ):
        super().__init__(slave_id=slave_id, stream_path=stream_path)
        self.temp = float(initial_temp)
        self.target_setpoint = float(target_setpoint)
        self.interval_sec = interval_sec
        self.min_temp = 16.0
        self.max_temp = 50.0

        # Initialize holding registers
        self.write_floats(0, [self.temp, self.target_setpoint])

    def step(self) -> Tuple[bool, float]:
        """Perform a single HVAC simulation step."""
        # Read Coil 0 (Fan Relay Switch)
        fan_is_on = self.read_coils(0, count=1)[0]

        # Read setpoint from registers in case external client or API changed it
        setpoints = self.read_floats(2, count=1)
        if setpoints:
            self.target_setpoint = setpoints[0]

        # Physics: Cool down if fan is on, heat up if fan is off
        if fan_is_on:
            self.temp -= 1.2
        else:
            self.temp += 0.8

        # Clamp temperature to realistic bounds
        self.temp = max(self.min_temp, min(self.temp, self.max_temp))

        # Write Temperature to Address 0, Setpoint to Address 2
        self.write_floats(0, [self.temp, self.target_setpoint])

        return fan_is_on, self.temp

    def get_readings(self) -> dict:
        """Read current telemetry directly from registers."""
        floats = self.read_floats(0, count=2)
        temp = floats[0] if len(floats) >= 1 else self.temp
        setpoint = floats[1] if len(floats) >= 2 else self.target_setpoint
        coils = self.read_coils(0, count=1)
        fan_on = coils[0] if coils else False
        mode = "COOLING" if fan_on else "HEATING"
        base = self.stream_path.rstrip("/") if self.stream_path else f"/gateway-01/device-{self.slave_id:02d}"
        return {
            "slave_id": self.slave_id,
            "stream_path": self.stream_path,
            "temperature": round(temp, 1),
            "target_setpoint": round(setpoint, 1),
            "fan_relay": fan_on,
            "mode": mode,
            "points": {
                f"{base}/Temperature": round(temp, 1),
                f"{base}/TargetSetpoint": round(setpoint, 1),
                f"{base}/FanRelay": fan_on,
                f"{base}/Mode": mode,
            },
        }

    def set_fan(self, state: bool) -> None:
        """Update fan relay coil 0."""
        self.write_coils(0, [bool(state)])

    def set_target(self, target: float) -> None:
        """Update target setpoint in holding registers 2-3."""
        self.target_setpoint = float(target)
        self.write_floats(2, [self.target_setpoint])

    async def run_simulation(self) -> None:
        """Continuous simulation loop."""
        log.info("Started physics loop for HVAC Controller (Slave %d)", self.slave_id)
        try:
            while True:
                fan_is_on, current_temp = self.step()
                log.info(
                    "❄️ [HVAC  Slave %d] Temp: %.2f°C (Setpoint: %.1f°C) | Fan: %s",
                    self.slave_id,
                    current_temp,
                    self.target_setpoint,
                    "ON (Cooling)" if fan_is_on else "OFF (Heating)",
                )
                await asyncio.sleep(self.interval_sec)
        except asyncio.CancelledError:
            log.info("Stopped simulation for HVAC Controller (Slave %d)", self.slave_id)
            raise
