import logging
from pathlib import Path
from typing import Dict, Optional, Sequence, Union

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from device_simulator.base_device import VirtualDevice
from device_simulator.device_manager import AVAILABLE_DEVICE_TYPES, DeviceManager
from device_simulator.hvac import HVACTemperatureController

log = logging.getLogger(__name__)


class FanControlRequest(BaseModel):
    slave_id: Optional[int] = None
    fan_on: bool


class SetpointControlRequest(BaseModel):
    slave_id: Optional[int] = None
    target_setpoint: float


class PathUpdateRequest(BaseModel):
    slave_id: int
    stream_path: str


class CreateDeviceRequest(BaseModel):
    device_type: str
    slave_id: Optional[int] = None
    stream_path: Optional[str] = None


def create_api_app(
    devices_or_manager: Union[Sequence[VirtualDevice], DeviceManager],
    static_dir: Path | None = None,
) -> FastAPI:
    """Create FastAPI application wired directly to virtual Modbus devices."""
    app = FastAPI(title="Edge Device Simulator API", docs_url="/api/docs")

    if static_dir is None:
        static_dir = Path(__file__).resolve().parent.parent.parent / "web"

    # Normalize to DeviceManager instance
    if isinstance(devices_or_manager, DeviceManager):
        manager = devices_or_manager
    else:
        from device_simulator.server import create_server_context

        context = create_server_context(devices_or_manager)
        manager = DeviceManager(devices_or_manager, context)

    @app.get("/api/device-types")
    def get_device_types():
        """Get catalog of available device types that can be created."""
        return AVAILABLE_DEVICE_TYPES

    @app.get("/api/devices")
    def get_devices():
        """Get live telemetry and metadata for all active devices."""
        return manager.get_all_readings()

    @app.post("/api/devices")
    def add_device(req: CreateDeviceRequest):
        """Dynamically add a new device to the simulator and Modbus server."""
        try:
            dev = manager.add_device(
                device_type=req.device_type,
                slave_id=req.slave_id,
                stream_path=req.stream_path,
            )
            return {
                "status": "ok",
                "slave_id": dev.slave_id,
                "device_type": dev.device_type,
                "stream_path": dev.stream_path,
                "device": dev.get_readings(),
            }
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    @app.delete("/api/devices/{slave_id}")
    def delete_device(slave_id: int):
        """Remove a device by Slave ID and unbind its Modbus registers."""
        success = manager.remove_device(slave_id)
        if not success:
            raise HTTPException(
                status_code=404, detail=f"Device with Slave ID {slave_id} not found"
            )
        return {"status": "ok", "removed_slave_id": slave_id}

    @app.get("/api/streams")
    def get_streams(batch: bool = True, url: str = "", key: str = ""):
        """Get stream map matching {"path1": [[value]], ..., url: '', key: ''}."""
        return manager.get_all_streams(batch=batch, url=url, key=key)

    @app.post("/api/devices/path")
    def set_device_path(req: PathUpdateRequest):
        """Update stream base path for a device by slave_id."""
        dev = next((d for d in manager.devices if d.slave_id == req.slave_id), None)
        if not dev:
            raise HTTPException(status_code=404, detail="Device not found")
        dev.stream_path = req.stream_path.strip()
        return {
            "status": "ok",
            "slave_id": dev.slave_id,
            "stream_path": dev.stream_path,
        }

    @app.post("/api/hvac/fan")
    def set_hvac_fan(req: FanControlRequest):
        """Set HVAC fan state (coil 0). Target specific device via slave_id if provided."""
        if req.slave_id is not None:
            hvac_dev = next(
                (
                    d
                    for d in manager.devices
                    if isinstance(d, HVACTemperatureController)
                    and d.slave_id == req.slave_id
                ),
                None,
            )
        else:
            hvac_dev = next(
                (
                    d
                    for d in manager.devices
                    if isinstance(d, HVACTemperatureController)
                ),
                None,
            )

        if not hvac_dev:
            raise HTTPException(status_code=404, detail="HVAC device not found")
        hvac_dev.set_fan(req.fan_on)
        return {
            "status": "ok",
            "slave_id": hvac_dev.slave_id,
            "fan_relay": req.fan_on,
        }

    @app.post("/api/hvac/setpoint")
    def set_hvac_setpoint(req: SetpointControlRequest):
        """Set HVAC target setpoint (holding register 2-3). Target specific device via slave_id."""
        if req.slave_id is not None:
            hvac_dev = next(
                (
                    d
                    for d in manager.devices
                    if isinstance(d, HVACTemperatureController)
                    and d.slave_id == req.slave_id
                ),
                None,
            )
        else:
            hvac_dev = next(
                (
                    d
                    for d in manager.devices
                    if isinstance(d, HVACTemperatureController)
                ),
                None,
            )

        if not hvac_dev:
            raise HTTPException(status_code=404, detail="HVAC device not found")
        hvac_dev.set_target(req.target_setpoint)
        return {
            "status": "ok",
            "slave_id": hvac_dev.slave_id,
            "target_setpoint": req.target_setpoint,
        }

    # Mount static web frontend if directory exists
    if static_dir.exists():
        app.mount(
            "/", StaticFiles(directory=str(static_dir), html=True), name="static"
        )

    return app
