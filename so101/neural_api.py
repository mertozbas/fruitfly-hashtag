"""Same-origin adapter from the established lab UI to the physical worker."""
import json
from typing import Literal
import urllib.error
import urllib.request

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict


class NeuralCommand(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    op:Literal['hold','run','stop','cameras','teach_start','teach_stop','joints','gripper_open']
    session:str|None=None
    preview:str|None=None
    confirmed:bool=False
    target:list[int]|None=None
    thermal_pause_review:str|None=None
    empty_gripper:bool=False


def router():
    api=APIRouter(prefix='/api/physical')
    worker='http://127.0.0.1:8767'
    def invoke(path,session=None,body=None):
        headers={'Origin':worker,'Content-Type':'application/json'}
        if session:headers['X-Neural-Session']=session
        request=urllib.request.Request(worker+path,headers=headers,
            data=None if body is None else json.dumps(body).encode())
        try:
            with urllib.request.urlopen(request,timeout=.7) as response:return json.load(response)
        except urllib.error.HTTPError as exc:
            result=json.load(exc)
            raise HTTPException(exc.code,result.get('error','Fiziksel kontrol isteği reddedildi')) from exc
        except (OSError,ValueError) as exc:
            raise HTTPException(503,'Fiziksel beyin servisine bağlanılamadı. neural.sh ile başlat.') from exc

    @api.get('/state')
    def state(request:Request):
        return invoke('/state',session=request.headers.get('X-Neural-Session'))

    @api.post('/command')
    def command(request:NeuralCommand):
        return invoke('/command',body=request.model_dump())

    return api
