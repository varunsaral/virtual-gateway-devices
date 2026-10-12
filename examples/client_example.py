"""Example client showing how to read from and write to the Modbus simulator."""

import asyncio
import struct
from pymodbus.client import AsyncModbusTcpClient


def decode_floats(registers):
    """Decode pairs of 16-bit registers into 32-bit floats."""
    floats = []
    for i in range(0, len(registers), 2):
        packed = struct.pack(">HH", registers[i], registers[i + 1])
        floats.append(round(struct.unpack(">f", packed)[0], 2))
    return floats


async def main():
    client = AsyncModbusTcpClient("127.0.0.1", port=5020)
    await client.connect()

    if not client.connected:
        print("❌ Could not connect to Modbus simulator. Is the server running?")
        return

    print(" Connected to Modbus TCP Simulator at 127.0.0.1:5020\n")

    # 1. Read Energy Meter (Slave ID: 1)
    # Reading 10 holding registers starting at address 0 (5 floats: V, kW, A, Hz, kWh)
    res_meter = await client.read_holding_registers(0, count=10, slave=1)
    if not res_meter.isError():
        v, kw, a, hz, kwh = decode_floats(res_meter.registers)
        print("⚡ [Slave 1 - Energy Meter]")
        print(f"   Voltage:      {v} V")
        print(f"   Active Power: {kw} kW")
        print(f"   Current:      {a} A")
        print(f"   Frequency:    {hz} Hz")
        print(f"   Total Energy: {kwh} kWh\n")
    else:
        print(f"❌ Error reading meter: {res_meter}")

    # 2. Read HVAC Controller (Slave ID: 2)
    # Read Coil 0 (Fan Relay) and Holding Registers 0-3 (Temperature, Setpoint)
    res_coil = await client.read_coils(0, count=1, slave=2)
    res_hvac = await client.read_holding_registers(0, count=4, slave=2)

    if not res_coil.isError() and not res_hvac.isError():
        fan_status = "ON (Cooling)" if res_coil.bits[0] else "OFF (Heating)"
        temp, setpoint = decode_floats(res_hvac.registers)
        print("❄️ [Slave 2 - HVAC Controller]")
        print(f"   Fan Relay:    {fan_status}")
        print(f"   Current Temp: {temp} °C")
        print(f"   Setpoint:     {setpoint} °C\n")

        # Example: Toggle the fan coil to show interactive control
        new_fan_state = not res_coil.bits[0]
        print(f"👉 Setting HVAC fan to {'ON' if new_fan_state else 'OFF'}...")
        await client.write_coil(0, new_fan_state, slave=2)
        print("   Done! Check the server logs to watch the temperature adjust.")
    else:
        print(f"❌ Error reading HVAC: {res_hvac}")

    client.close()


if __name__ == "__main__":
    asyncio.run(main())
