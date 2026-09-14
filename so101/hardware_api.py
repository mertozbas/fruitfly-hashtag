"""Local commissioning routes. No route accepts actuator targets."""
from typing import Literal
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field


class ArmConnection(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    port:str=Field(min_length=1,max_length=200)
    calibration_id:str=Field(min_length=1,max_length=200)


class CameraConnection(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    role:Literal['wrist','top']
    index:int=Field(ge=0,le=15)


class CameraStop(BaseModel):
    model_config=ConfigDict(extra='forbid')
    role:Literal['wrist','top']


def router(hardware):
    api=APIRouter(prefix='/api/hardware')

    def invoke(function,*args):
        try:return function(*args)
        except (ValueError,OSError) as exc:raise HTTPException(409,str(exc)) from exc

    @api.get('/state')
    def state():return hardware.state()

    @api.get('/inventory')
    def inventory():return hardware.inventory()

    @api.post('/connect')
    def connect(request:ArmConnection):return invoke(hardware.connect,request.port,request.calibration_id)

    @api.post('/camera')
    def camera(request:CameraConnection):return invoke(hardware.camera,request.role,request.index)

    @api.post('/camera/stop')
    def stop(request:CameraStop):
        invoke(hardware.stop_camera,request.role);return hardware.state()

    @api.post('/disconnect')
    def disconnect():
        hardware.disconnect();return hardware.state()

    @api.post('/motion')
    def motion():raise HTTPException(423,'Gerçek motor yürütmesi devreye alınmadı. Eklem, kamera ve kavrama doğrulaması gerekli.')

    return api
