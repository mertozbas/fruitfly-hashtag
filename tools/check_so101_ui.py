"""Real Chrome smoke checks against a running local SO-101 laboratory.

Optional development dependency: playwright==1.62.0; uses installed Chrome.
No physical robot or external service is contacted.
"""
import argparse
import json
from pathlib import Path
import time
import urllib.request
from playwright.sync_api import sync_playwright


def check(base,output,train_cancel=False):
    output=Path(output);output.mkdir(parents=True,exist_ok=True);checks={};errors=[]
    def state():
        with urllib.request.urlopen(base+'/api/state',timeout=10) as r:return json.load(r)
    def until(predicate,seconds=12):
        deadline=time.monotonic()+seconds
        while time.monotonic()<deadline:
            value=state()
            if predicate(value):return value
            time.sleep(.1)
        raise AssertionError('Timed out waiting for live state')
    with sync_playwright() as p:
        browser=p.chromium.launch(channel='chrome',headless=True)
        page=browser.new_page(viewport=dict(width=1728,height=1050),device_scale_factor=1)
        page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto(base)
        page.wait_for_function("document.querySelector('#experiment').value==='so101'")
        page.wait_for_function("document.querySelector('#fly-image').naturalWidth===1920")
        current=state()['simulation'];prefix=current['model_sha256'][:12]
        page.wait_for_function('(sha)=>document.querySelector("#checkpoint").textContent.includes(sha)',arg=prefix)
        checks['displayed_checkpoint_matches_live_robot']=True
        checks['robot_neuron_count']='3.488' in page.locator('#odor-neurons').inner_text()
        checks['all_trainable_connections']='81.104' in page.locator('#odor-weights').inner_text()
        checks['full_hd']=True
        checks['task_option']=page.locator('#experiment').input_value()=='so101'
        for width,height in [(1728,1050),(1440,900),(1280,800)]:
            page.set_viewport_size(dict(width=width,height=height));page.wait_for_timeout(150)
            checks[f'no_page_scroll_{width}x{height}']=page.evaluate('document.documentElement.scrollHeight<=innerHeight && document.documentElement.scrollWidth<=innerWidth')
        page.set_viewport_size(dict(width=1728,height=1050))
        if not state()['simulation']['paused']:page.locator('#pause').click()
        paused=until(lambda s:s['simulation']['paused'])['simulation'];time.sleep(.3)
        checks['pause_stops_physics']=state()['simulation']['time_s']==paused['time_s']
        before=paused['camera_pose']['azimuth'];box=page.locator('#fly-image').bounding_box()
        page.mouse.move(box['x']+box['width']*.55,box['y']+box['height']*.45)
        page.mouse.down();page.mouse.move(box['x']+box['width']*.65,box['y']+box['height']*.50,steps=8);page.mouse.up()
        until(lambda s:abs(s['simulation']['camera_pose']['azimuth']-before)>1)
        checks['mouse_camera']=True
        page.locator('#sim-home').click()
        page.locator('#robot-sensor').select_option('camera')
        camera=until(lambda s:s['simulation'].get('robot',{}).get('sensor_mode')=='camera')['simulation']
        checks['camera_observation']=bool(camera['robot']['perception'])
        page.locator('#robot-sensor').select_option('state')
        until(lambda s:s['simulation'].get('robot',{}).get('sensor_mode')=='state')
        page.locator('#analyses-tab').click();page.screenshot(path=str(output/'analyses.png'))
        checks['analyses_visible']=page.locator('#heat-map').is_visible() and page.locator('#xray-map').is_visible()
        page.locator('#metrics-tab').click();page.locator('#delta-mode').click()
        checks['weight_delta_mode']='BAĞLANTI' in page.locator('#scale-title').inner_text()
        page.locator('#activity-mode').click()
        page.locator('#brain-brightness').focus();page.keyboard.press('Home')
        checks['brightness_zero']=page.locator('#brain-brightness').input_value()=='0'
        page.keyboard.press('ArrowRight')
        # Locate a visible soma through the actual pointer/tooltip path.
        box=page.locator('#brain-canvas').bounding_box();selected=False
        for fy in (.75,.65,.55,.45,.35,.85,.25):
            for fx in (.5,.45,.55,.4,.6,.35,.65):
                page.mouse.move(box['x']+box['width']*fx,box['y']+box['height']*fy);page.wait_for_timeout(25)
                if page.locator('#brain-tooltip').is_visible():
                    page.mouse.click(box['x']+box['width']*fx,box['y']+box['height']*fy)
                    if page.locator('#inspect-open').is_visible():selected=True;break
            if selected:break
        checks['neuron_pick']=selected
        if selected:
            if not page.locator('#detail-drawer').is_visible():page.locator('#inspect-open').click()
            page.screenshot(path=str(output/'neuron-details.png'))
            checks['neuron_details']=page.locator('#detail-drawer').is_visible()
            page.locator('#detail-close').click()
        page.locator('#validation-open').click()
        checks['validation_modal']=page.locator('#validation-dialog').is_visible()
        page.locator('#validation-close').click()
        if train_cancel:
            before=state()['simulation']['model_sha256']
            page.locator('#steps').fill('200');page.locator('#seed').fill('987')
            page.locator('#train').click();page.locator('#cancel').wait_for(state='visible')
            page.locator('#cancel').click();until(lambda s:s['job'].get('status')=='cancelled',30)
            checks['training_cancel_preserves_model']=state()['simulation']['model_sha256']==before
        page.screenshot(path=str(output/'laboratory.png'))
        checks['no_javascript_errors']=not errors
        (output/'report.json').write_text(json.dumps(dict(checks=checks,errors=errors),indent=2))
        browser.close()
    if not all(checks.values()):raise AssertionError(checks)
    return checks

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--base',default='http://127.0.0.1:8772');p.add_argument('--output',default='artifacts/so101/ui-qa');p.add_argument('--train-cancel',action='store_true')
    a=p.parse_args();print(json.dumps(check(a.base,a.output,a.train_cancel),indent=2))
