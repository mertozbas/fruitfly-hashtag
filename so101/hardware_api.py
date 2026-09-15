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
    profile_id:str|None=Field(None,max_length=80)
    device_verified:bool=False


class CalibrationStart(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    port:str=Field(min_length=1,max_length=200)
    robot_id:str=Field(pattern=r'^[A-Za-z0-9_-]{1,64}$')
    calibration_id:str|None=Field(None,max_length=200)
    backup_id:str|None=Field(None,pattern=r'^[0-9a-f]{32}$')


class CalibrationCommand(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    session:str=Field(pattern=r'^[0-9a-f]{32}$')
    revision:int=Field(ge=0)
    op:Literal['release','reference','next','save','cancel','restore']
    supported:bool=False
    range_confirmed:bool=False
    confirmed:bool=False


class CameraCalibrationCommand(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    session:str=Field(pattern=r'^[0-9a-f]{32}$')
    role:Literal['wrist','top']
    op:Literal['enable','capture','solve','save','reset','workspace']
    target_medium:Literal['printed','screen']|None=None
    target_square_mm:float|None=Field(default=None,ge=1,le=100,allow_inf_nan=False)
    device_label:str=Field(default='',max_length=64)
    confirmed:bool=False
    base_pose:list[float]|None=Field(default=None,min_length=6,max_length=6)


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
    def camera(request:CameraConnection):return invoke(hardware.camera,request.role,request.index,request.profile_id,request.device_verified)

    @api.post('/calibration/start')
    def calibration_start(request:CalibrationStart):
        return invoke(hardware.commissioning.start,request.port,request.robot_id,request.calibration_id,request.backup_id)

    @api.post('/calibration/command')
    def calibration_command(request:CalibrationCommand):
        return invoke(hardware.commissioning.command,request.session,request.model_dump(exclude={'session'}))

    @api.post('/camera/calibration')
    def camera_calibration(request:CameraCalibrationCommand):
        if request.op=='enable' and (not request.confirmed or not request.device_label.strip()):raise HTTPException(422,'Fiziksel kamera kimliğini doğrula ve bir ad gir')
        if request.base_pose is not None:
            import math
            if not all(math.isfinite(v) for v in request.base_pose):raise HTTPException(422,'Poz değerleri sonlu olmalı')
        return invoke(hardware.commissioning.camera_command,request.role,request.session,request.model_dump(exclude={'session','role'}))

    @api.get('/calibration/report')
    def calibration_report(kind:Literal['motor','camera'],record_id:str):
        return invoke(hardware.commissioning.report,kind,record_id)

    @api.post('/camera/stop')
    def stop(request:CameraStop):
        invoke(hardware.stop_camera,request.role);return hardware.state()

    @api.post('/disconnect')
    def disconnect():
        hardware.disconnect();return hardware.state()

    @api.post('/motion')
    def motion():raise HTTPException(423,'Gerçek motor yürütmesi devreye alınmadı. Eklem, kamera ve kavrama doğrulaması gerekli.')

    return api
