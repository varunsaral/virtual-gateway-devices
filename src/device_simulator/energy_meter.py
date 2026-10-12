import asyncio
import logging
import math
import random
from typing import Tuple

from device_simulator.base_device import VirtualDevice

log = logging.getLogger(__name__)


class MainEnergyMeter(VirtualDevice):
    """Simulates an electrical energy meter (Slave ID 1 by default).
    
    Register Map (Holding Registers / FC 3):
        Address 0-1: Voltage (V) [Float32]
        Address 2-3: Active Power (kW) [Float32]
        Address 4-5: Current (A) [Float32]
        Address 6-7: Frequency (Hz) [Float32]
        Address 8-9: Total Energy (kWh) [Float32]
    """

    device_type: str = "energy_meter"

    def __init__(
        self,
        slave_id: int = 1,
        interval_sec: float = 1.0,
        stream_path: str = "/gateway-01/device-01",
    ):
        super().__init__(slave_id=slave_id, stream_path=stream_path)
        self.interval_sec = interval_sec
        self.total_energy_kwh = 0.0

    def step(self, t: int = 0) -> Tuple[float, float, float, float, float]:
        """Perform a single physics simulation tick."""
        # Grid voltage fluctuates around 230V
        voltage = 230.0 + random.uniform(-2.0, 2.0)
        # Power surges along a sine wave (base 25 kW +/- 5 kW)
        active_kw = max(0.0, 25.0 + math.sin(t / 10.0) * 5.0)
        # Approximate current I = P / V (single phase equivalent in Amps)
        current_a = (active_kw * 1000.0) / voltage if voltage > 0 else 0.0
        # Frequency fluctuates around 50 Hz
        frequency_hz = 50.0 + random.uniform(-0.05, 0.05)
        # Accumulate energy (kWh = kW * hours)
        self.total_energy_kwh += active_kw * (self.interval_sec / 3600.0)

        # Write to Modbus holding registers
        self.write_floats(
            0,
            [voltage, active_kw, current_a, frequency_hz, self.total_energy_kwh],
        )

        return voltage, active_kw, current_a, frequency_hz, self.total_energy_kwh

    def get_readings(self) -> dict:
        """Read current telemetry directly from holding registers."""
        floats = self.read_floats(0, count=5)
        if len(floats) >= 5:
            voltage, active_kw, current_a, freq_hz, total_kwh = floats
        else:
            voltage, active_kw, current_a, freq_hz, total_kwh = 0.0, 0.0, 0.0, 0.0, 0.0
        base = self.stream_path.rstrip("/") if self.stream_path else f"/gateway-01/device-{self.slave_id:02d}"
        return {
            "slave_id": self.slave_id,
            "stream_path": self.stream_path,
            "voltage": round(voltage, 1),
            "power_kw": round(active_kw, 2),
            "current_a": round(current_a, 2),
            "freq_hz": round(freq_hz, 2),
            "total_kwh": round(total_kwh, 4),
            "points": {
                f"{base}/Voltage": round(voltage, 1),
                f"{base}/ActivePower": round(active_kw, 2),
                f"{base}/Current": round(current_a, 2),
                f"{base}/Frequency": round(freq_hz, 2),
                f"{base}/TotalEnergy": round(total_kwh, 4),
            },
        }

    async def run_simulation(self) -> None:
        """Continuous simulation loop."""
        log.info("Started physics loop for MainEnergyMeter (Slave %d)", self.slave_id)
        t = 0
        try:
            while True:
                voltage, active_kw, current_a, freq, total_kwh = self.step(t)
                log.info(
                    "⚡ [Meter Slave %d] Voltage: %.1fV | Power: %.2fkW | Current: %.2fA | Total: %.4fkWh",
                    self.slave_id,
                    voltage,
                    active_kw,
                    current_a,
                    total_kwh,
                )
                t += 1
                await asyncio.sleep(self.interval_sec)
        except asyncio.CancelledError:
            log.info("Stopped simulation for MainEnergyMeter (Slave %d)", self.slave_id)
            raise
