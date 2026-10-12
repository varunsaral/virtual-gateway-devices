import logging
import struct
from typing import List, Sequence

from pymodbus.constants import Endian
from pymodbus.datastore import ModbusSequentialDataBlock, ModbusSlaveContext
from pymodbus.payload import BinaryPayloadBuilder

log = logging.getLogger(__name__)


class VirtualDevice:
    """Base class for virtual Modbus TCP devices."""

    device_type: str = "generic"

    def __init__(
        self, slave_id: int, register_count: int = 100, stream_path: str = ""
    ):
        self.slave_id = slave_id
        self.register_count = register_count
        self.stream_path = stream_path or f"/gateway-01/device-{slave_id:02d}"
        self.store = ModbusSlaveContext(
            di=ModbusSequentialDataBlock(0, [0] * register_count),
            co=ModbusSequentialDataBlock(0, [0] * register_count),
            hr=ModbusSequentialDataBlock(0, [0] * register_count),
            ir=ModbusSequentialDataBlock(0, [0] * register_count),
        )

    async def run_simulation(self) -> None:
        """Override this loop in subclasses to provide specific device physics."""
        pass

    def get_readings(self) -> dict:
        """Return dictionary representation of device readings from registers."""
        return {"slave_id": self.slave_id, "stream_path": self.stream_path}

    def write_floats(self, address: int, floats: Sequence[float]) -> None:
        """Pack 32-bit floats into 16-bit holding registers (Big Endian)."""
        builder = BinaryPayloadBuilder(byteorder=Endian.BIG, wordorder=Endian.BIG)
        for f in floats:
            builder.add_32bit_float(float(f))
        # 3 corresponds to holding registers (fc=3)
        self.store.setValues(3, address, builder.to_registers())

    def read_floats(self, address: int, count: int = 1) -> List[float]:
        """Read 32-bit floats from 16-bit holding registers."""
        # Each 32-bit float occupies 2 16-bit registers
        regs = self.store.getValues(3, address, count=count * 2)
        values: List[float] = []
        for i in range(0, len(regs), 2):
            packed = struct.pack(">HH", regs[i], regs[i + 1])
            values.append(struct.unpack(">f", packed)[0])
        return values

    def read_coils(self, address: int, count: int = 1) -> List[bool]:
        """Read boolean values from coil registers (fc=1)."""
        return [bool(v) for v in self.store.getValues(1, address, count=count)]

    def write_coils(self, address: int, values: Sequence[bool]) -> None:
        """Write boolean values to coil registers (fc=1)."""
        self.store.setValues(1, address, [int(v) for v in values])
