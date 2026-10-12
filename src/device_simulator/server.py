import argparse
import asyncio
import logging
from typing import List, Optional, Sequence

import uvicorn
from pymodbus.datastore import ModbusServerContext
from pymodbus.server import StartAsyncTcpServer

from device_simulator.base_device import VirtualDevice
from device_simulator.device_manager import DeviceManager
from device_simulator.energy_meter import MainEnergyMeter
from device_simulator.hvac import HVACTemperatureController
from device_simulator.web_api import create_api_app

log = logging.getLogger("Simulator")


def create_server_context(devices: Sequence[VirtualDevice]) -> ModbusServerContext:
    """Map devices by slave_id into a multi-device ModbusServerContext."""
    slaves = {dev.slave_id: dev.store for dev in devices}
    return ModbusServerContext(slaves=slaves, single=False)


async def run_server(
    devices: Optional[Sequence[VirtualDevice]] = None,
    host: str = "127.0.0.1",
    port: int = 5020,
    http_host: str = "127.0.0.1",
    http_port: int = 8080,
    enable_web: bool = True,
) -> None:
    """Run Modbus TCP server and start background simulation tasks for all devices."""
    if devices is None:
        devices = [
            MainEnergyMeter(slave_id=1),
            HVACTemperatureController(slave_id=2),
        ]

    context = create_server_context(devices)
    manager = DeviceManager(devices=devices, context=context)
    manager.start_all()

    http_server: Optional[uvicorn.Server] = None
    http_task: Optional[asyncio.Task] = None
    if enable_web:
        api_app = create_api_app(devices_or_manager=manager)
        config = uvicorn.Config(
            app=api_app,
            host=http_host,
            port=http_port,
            log_level="warning",
        )
        http_server = uvicorn.Server(config)
        http_task = asyncio.create_task(http_server.serve())
        log.info("🌐 Web UI and API running on http://%s:%d (Docs: /api/docs)", http_host, http_port)

    log.info("Starting Multi-Device Modbus Simulator on %s:%d", host, port)
    for dev in manager.devices:
        log.info("Registered device Slave ID %d (%s)", dev.slave_id, dev.__class__.__name__)

    try:
        await StartAsyncTcpServer(context=context, address=(host, port))
    finally:
        manager.stop_all()
        if http_server:
            http_server.should_exit = True
        if http_task:
            http_task.cancel()
            await asyncio.gather(http_task, return_exceptions=True)


def main() -> None:
    """CLI entry point for starting the simulator server."""
    parser = argparse.ArgumentParser(description="Multi-Device Modbus TCP Simulator")
    parser.add_argument("--host", default="127.0.0.1", help="Host interface for Modbus TCP (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=5020, help="Port to bind Modbus TCP (default: 5020)")
    parser.add_argument("--http-host", default="127.0.0.1", help="Host interface for Web UI (default: 127.0.0.1)")
    parser.add_argument("--http-port", type=int, default=8080, help="Port to bind Web UI (default: 8080)")
    parser.add_argument("--no-web", action="store_true", help="Disable the web dashboard and REST API")
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level (default: INFO)",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    try:
        asyncio.run(
            run_server(
                host=args.host,
                port=args.port,
                http_host=args.http_host,
                http_port=args.http_port,
                enable_web=not args.no_web,
            )
        )
    except KeyboardInterrupt:
        log.info("Server terminated by user.")


if __name__ == "__main__":
    main()
