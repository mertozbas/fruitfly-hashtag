"""Browser commissioning QA. Camera/motor samples are explicitly mocked, never opened."""
import argparse
import base64
import copy
import json
from pathlib import Path
import urllib.request
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]


def check(base,output):
    output=Path(output);output.mkdir(parents=True,exist_ok=True);checks={};errors=[]
    with urllib.request.urlopen(base+'/api/hardware/inventory',timeout=15) as response:offline=json.load(response)
    assert not offline['arm'].get('running') and not any(c.get('running') for c in offline['cameras'].values())
    assert not offline['inventory']['ports'],'This offline QA requires no attached physical arm.'
    with sync_playwright() as playwright:
        browser=playwright.chromium.launch(channel='chrome',headless=True)
        page=browser.new_page(viewport=dict(width=1728,height=1050));page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto(base);page.locator('#hardware-open').click()
        page.wait_for_function("document.querySelector('#hw-environment').textContent==='SÜRÜCÜ ORTAMI HAZIR'")
        checks['offline_connect_disabled']=page.locator('#hw-connect').is_disabled()
        checks['saved_calibration_visible']=all(c['name'] in page.locator('#hw-calibration').inner_text() for c in offline['calibrations'])
        checks['camera_not_opened']=page.locator('#hw-wrist-image').is_hidden() and page.locator('#hw-top-image').is_hidden()
        checks['physical_scope_explicit']='simülasyona bağlı' in page.locator('.hw-context').inner_text()
        for width,height in [(1728,1050),(1440,900),(1280,800)]:
            page.set_viewport_size(dict(width=width,height=height));page.wait_for_timeout(100)
            for tab in ('diagnostics','readiness'):
                page.locator(f'#hw-{tab}-tab').click()
                checks[f'no_scroll_{tab}_{width}']=page.evaluate(f"""()=>{{const d=document.querySelector('#hardware-dialog'),c=document.querySelector('#hw-{tab}');return document.documentElement.scrollHeight<=innerHeight&&document.documentElement.scrollWidth<=innerWidth&&d.scrollHeight<=d.clientHeight&&c.scrollHeight<=c.clientHeight;}}""")
        page.screenshot(path=str(output/'offline-readiness-1280.png'))
        page.set_viewport_size(dict(width=1728,height=1050));page.locator('#hw-diagnostics-tab').click()
        page.screenshot(path=str(output/'offline-diagnostics.png'))
        page.locator('#hw-wrist-start').click()
        checks['empty_camera_index_rejected']='0–15' in page.locator('#hw-message').inner_text()
        page.locator('#hardware-close').click();page.wait_for_timeout(500)

        # Below this boundary every hardware endpoint is mocked in the browser.
        fixture=copy.deepcopy(offline);fixture['inventory']['ports']=[dict(device='/dev/cu.usbQA',description='OFFLINE FIXTURE')]
        fixture['calibrations']=[dict(id='so_follower/qa.json',name='QA fixture',valid=True,sha256='0'*64,path='offline-fixture',errors=[])]
        image=base64.b64encode((ROOT/'docs/media/so101-lab.jpg').read_bytes()).decode()
        requests=[]
        def handle(route):
            path=route.request.url.split('/api/hardware/')[1]
            if route.request.method=='POST':
                body=route.request.post_data_json or {};requests.append(path)
                if path=='camera':fixture['cameras'][body['role']]=dict(running=True,fresh=True,image=image,width=1280,height=720,age_ms=20)
                elif path=='camera/stop':fixture['cameras'][body['role']]={}
                elif path=='connect':fixture['arm']=dict(running=True,fresh=True,age_ms=25,calibration_match=True,motors=[
                    dict(name=name,value=10.5,unit='%' if i==5 else '°',temperature_c=29,voltage_v=7.5,torque_enabled=False,
                         position_raw=2050,load_raw=0,operating_mode=0,in_calibrated_range=True)
                    for i,name in enumerate(('shoulder_pan','shoulder_lift','elbow_flex','wrist_flex','wrist_roll','gripper'))])
                elif path=='disconnect':fixture['arm']={};fixture['cameras']={r:{} for r in ('wrist','top')}
            route.fulfill(json=fixture)
        page.route('**/api/hardware/**',handle)
        page.locator('#hardware-open').click();page.locator('#hw-connect').click()
        page.wait_for_function("document.querySelector('#hw-arm-status').textContent.includes('CANLI')")
        checks['six_motor_rows_and_units']=page.locator('#hw-motors tr').count()==6 and '10.5%' in page.locator('#hw-motors').inner_text()
        page.locator('#hw-wrist-index').fill('0');page.locator('#hw-wrist-start').click()
        page.wait_for_function("document.querySelector('#hw-wrist-image').naturalWidth>0&&!document.querySelector('#hw-wrist-image').hidden")
        checks['camera_preview_fixture']=page.locator('#hw-wrist-start').is_disabled() and '1280×720' in page.locator('#hw-wrist-status').inner_text()
        fixture['cameras']['wrist']=dict(running=False,fresh=False,error='OFFLINE FIXTURE: camera disconnected')
        page.wait_for_function("document.querySelector('#hw-wrist-image').hidden")
        checks['stale_frame_removed']=not page.locator('#hw-wrist-image').get_attribute('src')
        checks['camera_error_visible']='disconnected' in page.locator('#hw-wrist-empty').inner_text()
        page.keyboard.press('Escape');page.wait_for_timeout(500)
        checks['escape_disconnects']='disconnect' in requests and not page.locator('#hardware-dialog').is_visible()
        checks['no_browser_errors']=not errors;browser.close()
    with urllib.request.urlopen(base+'/api/hardware/state',timeout=15) as response:final=json.load(response)
    checks['no_actual_hardware_session']=not final['arm'] and all(not c for c in final['cameras'].values())
    report=dict(checks=checks,passed=all(checks.values()),errors=errors,evidence='Offline UI and mocked hardware samples; no physical execution.')
    (output/'checks.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
    if not report['passed']:raise AssertionError('Hardware UI checks failed')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--base',default='http://127.0.0.1:8772');parser.add_argument('--output',default='artifacts/so101-hardware/ui')
    args=parser.parse_args();check(args.base,args.output)
