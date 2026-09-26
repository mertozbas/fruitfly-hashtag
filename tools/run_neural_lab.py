"""Start/reuse the local camera lab and bounded physical neural service."""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import urllib.request
import webbrowser

ROOT=Path(__file__).resolve().parents[1]


def read(url):
    with urllib.request.urlopen(url,timeout=1) as response:return json.load(response)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--serial',default=os.environ.get('FRUITFLY_FOLLOWER_SERIAL'),help='Verified follower USB serial (or FRUITFLY_FOLLOWER_SERIAL).')
    p.add_argument('--calibration',default=os.environ.get('FRUITFLY_FOLLOWER_CALIBRATION'),help='Matching follower calibration JSON (or FRUITFLY_FOLLOWER_CALIBRATION).')
    p.add_argument('--no-open',action='store_true');p.add_argument('--check',action='store_true')
    args=p.parse_args();owned=[];logs=[]
    services=[('lab','http://127.0.0.1:8766/api/health'),('neural','http://127.0.0.1:8767/state')]
    if args.check:
        for name,url in services:
            state=read(url)
            print(name, 'hazır',state.get('stage',state.get('status')),state.get('error') or '')
        return
    if not args.serial or not args.calibration:
        p.error('--serial and --calibration are required to start the physical lab.')
    args.calibration=str(Path(args.calibration).expanduser())
    hardware=ROOT/'.runtime/hardware-venv/bin/python'
    if not hardware.is_file() or not Path(args.calibration).is_file():
        raise SystemExit('Donanım ortamı veya kaydedilmiş follower kalibrasyonu eksik.')
    inventory=json.loads(subprocess.check_output([str(hardware),'-m','so101.hardware_worker','inventory'],cwd=ROOT,text=True))
    ports=[x for x in inventory['ports'] if x.get('serial_number')==args.serial]
    if len(ports)!=1:raise SystemExit('Doğrulanmış USB follower bulunamadı; bağlantıyı kontrol et.')
    commands={'lab':[str(ROOT/'.venv/bin/python'),'lab_server.py'],
              'neural':[str(hardware),'-m','so101.neural_live','--port',ports[0]['device'],
                        '--serial',args.serial,'--calibration',args.calibration]}
    def stop(*_):raise KeyboardInterrupt
    signal.signal(signal.SIGTERM,stop)
    try:
        for name,url in services:
            try:
                state=read(url)
                if name=='lab' and state.get('status')!='ok':raise RuntimeError('Beklenmeyen lab servisi')
                if name=='neural' and not state.get('circuit_sha256'):raise RuntimeError('Beklenmeyen fiziksel servis')
            except OSError:
                log=(ROOT/'.runtime'/f'{name}-physical.log').open('a');logs.append(log)
                env=dict(os.environ,FRUITFLY_DEFAULT_TASK='odor')
                process=subprocess.Popen(commands[name],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
                owned.append(process)
                for _ in range(100):
                    if process.poll() is not None:raise RuntimeError(f'{name} başlamadı; {log.name}')
                    try:read(url);break
                    except OSError:time.sleep(.2)
                else:raise RuntimeError(f'{name} başlangıç süresi doldu')
        url='http://127.0.0.1:8766/?physical=1'
        print(f'Fiziksel Neural Lab: {url}',flush=True)
        print('Başlangıç salt okuma. Mevcut pozu tut → elleri çek → Beyinle yönlendir.',flush=True)
        print('Esc / Durdur: hareketi keser. Ctrl+C: bu komutun açtığı servisleri kapatır; tork açık kalabilir.',flush=True)
        if not args.no_open:webbrowser.open(url)
        while True:
            if any(child.poll() is not None for child in owned):raise RuntimeError('Yerel servis sona erdi; günlükleri kontrol et.')
            time.sleep(.5)
    except KeyboardInterrupt:pass
    finally:
        if owned:
            try:
                request=urllib.request.Request('http://127.0.0.1:8767/command',data=b'{"op":"stop"}',
                    headers={'Content-Type':'application/json','Origin':'http://127.0.0.1:8767'})
                urllib.request.urlopen(request,timeout=1).close()
            except OSError:pass
        for child in reversed(owned):
            if child.poll() is None:
                child.terminate()
                try:child.wait(timeout=8)
                except subprocess.TimeoutExpired:child.kill();child.wait(timeout=3)
        for log in logs:log.close()


if __name__=='__main__':main()
