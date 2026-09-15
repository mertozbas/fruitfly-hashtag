"""Browser checks with every hardware endpoint mocked; no physical writes."""
import argparse
import base64
import json
from pathlib import Path
import sys
import urllib.request
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from so101.hardware_contract import JOINTS,readiness


def check(base,output):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    with urllib.request.urlopen(base+'/api/hardware/state',timeout=10) as r:fixture=json.load(r)
    fixture.update(calibration_session={},calibration_history=[],camera_profiles=[],mode='read_only')
    fixture['inventory']['ports']=[dict(device='/dev/qa',description='OFFLINE FIXTURE')]
    fixture['calibrations']=[dict(id='so_follower/qa.json',name='qa',path='offline',sha256='0'*64,valid=True,errors=[])]
    fixture['selected_calibration']='so_follower/qa.json'
    fixture['arm']=dict(connected=True,fresh=True,running=True,age_ms=10,calibration_match=True,calibration_mismatches=[],
        motors=[dict(name=n,id=i+1,position_raw=3100,value=10.,unit='°',temperature_c=35,voltage_v=12.4,
        torque_enabled=False,in_calibrated_range=i!=2,load_raw=0,operating_mode=0) for i,n in enumerate(JOINTS)])
    image=base64.b64encode((ROOT/'docs/media/so101-lab.jpg').read_bytes()).decode()
    fixture['cameras']={r:dict(session=r,fresh=True,running=True,index=i,sequence=7,image=image,width=1280,height=720,age_ms=10,
        calibration={},perception=dict(frame_sequence=7,cube_visible=True,bin_visible=False)) for r,i in [('top',0),('wrist',1)]}
    fixture['checks']=readiness(dict(valid=True),fixture['arm'],fixture['cameras'])
    calls=[];errors=[];checks={}
    def handle(route):
        if route.request.method=='POST':calls.append(route.request.url.split('/api/hardware/')[1])
        route.fulfill(json=fixture)
    with sync_playwright() as p:
        browser=p.chromium.launch(channel='chrome',headless=True)
        page=browser.new_page(viewport=dict(width=1280,height=800))
        page.route('**/api/hardware/**',handle);page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto(base);page.locator('#hardware-open').click()
        page.wait_for_function("document.querySelector('#hw-wrist-index').value==='1'")
        checks['live_camera_indices']=page.locator('#hw-top-index').input_value()=='0'
        checks['cube_visible_bin_unreadable']='Küp 200: görülüyor · Kap: yok / belirsiz' in page.locator('#hw-top-vision').inner_text()
        checks['no_metric_pose_claim']='3B konum doğrulanmadı' in page.locator('#hw-top-vision').inner_text()
        checks['joint_limit_warning']='Dirsek (3100 ham)' in page.locator('#hw-arm-detail').inner_text()
        fixture['arm']['motors'][1]['torque_enabled']=True
        page.wait_for_function("document.querySelector('#hw-arm-detail').textContent.includes('paneli kapatmak torku kapatmaz')")
        checks['live_torque_warning']=True
        page.locator('#hw-readiness-tab').click()
        checks['twelve_checks']=page.locator('#hw-checks li').count()==12
        for width,height in [(1280,800),(1440,900),(1728,1050)]:
            page.set_viewport_size(dict(width=width,height=height));page.wait_for_timeout(150)
            checks[f'fits_{width}']=page.locator('#hw-readiness').evaluate('(e)=>e.scrollHeight<=e.clientHeight') and page.evaluate('document.documentElement.scrollHeight<=innerHeight')
        fixture['cameras']['top']['perception'].update(container_visible=True,container=dict(id=206,object='drawer_tray'),tray_visible=True)
        page.wait_for_function("document.querySelector('#hw-top-vision').textContent.includes('Kap: Tepsi 206')")
        checks['tray_identity_not_sort_bin']='Kutu 211' not in page.locator('#hw-top-vision').inner_text()
        fixture['cameras']['top']['perception'].update(container_visible=False,container=None,bin_visible=True,unknown_ids=[201])
        page.wait_for_function("document.querySelector('#hw-top-vision').textContent.includes('yok / belirsiz')")
        checks['ambiguous_goal_not_selected']='Kutu 211' not in page.locator('#hw-top-vision').inner_text()
        checks['unsupported_id_visible']='Tanımsız işaret: 201' in page.locator('#hw-top-vision').inner_text()
        fixture['cameras']['top']['sequence']=8
        page.wait_for_function("document.querySelector('#hw-top-vision').textContent==='Canlı nesne ölçümü yok'")
        checks['mismatched_frame_hidden']=True
        fixture['cameras']['wrist']['fresh']=False
        page.wait_for_function("document.querySelector('#hw-wrist-image').hidden")
        checks['stale_measurement_hidden']=page.locator('#hw-wrist-vision').inner_text()=='Canlı nesne ölçümü yok'
        page.screenshot(path=str(output/'readiness-offline-fixture.png'))
        page.keyboard.press('Escape');page.wait_for_timeout(150)
        checks['only_disconnect_post']=calls==['disconnect'];checks['no_js_errors']=not errors
        browser.close()
    result=dict(passed=all(checks.values()),checks=checks,errors=errors,evidence='Hardware routes mocked; no physical actuation.')
    (output/'checks.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
    if not result['passed']:raise AssertionError('Hardware vision UI check failed')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--base',default='http://127.0.0.1:8766')
    parser.add_argument('--output',default='artifacts/so101-rgb-preflight/ui');args=parser.parse_args();check(args.base,args.output)
