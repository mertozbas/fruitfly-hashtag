"""Calibration wizard browser tests. Every hardware route is mocked before UI opens."""
import argparse
import base64
import copy
import json
from pathlib import Path
import urllib.request
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]


def check(base,output):
    output=Path(output);output.mkdir(parents=True,exist_ok=True);checks={};errors=[];requests=[]
    with urllib.request.urlopen(base+'/api/hardware/state',timeout=10) as r:fixture=json.load(r)
    fixture.update(environment_ready=True,mode='read_only',arm={},calibration_session={},calibration_history=[],camera_profiles=[],cameras={'wrist':{},'top':{}})
    fixture['inventory']['ports']=[dict(device='/dev/cu.usbQA',description='OFFLINE FIXTURE')]
    fixture['calibrations']=[dict(id='so_follower/qa.json',name='qa',path='offline',sha256='0'*64,valid=True,errors=[])]
    names=['shoulder_pan','shoulder_lift','elbow_flex','wrist_flex','wrist_roll','gripper'];ranged=[n for n in names if n!='wrist_roll']
    candidate={n:dict(id=i+1,drive_mode=0,homing_offset=100,range_min=0 if n=='wrist_roll' else 900,range_max=4095 if n=='wrist_roll' else 3200) for i,n in enumerate(names)}
    sid='a'*32;bid='b'*32;cid='c'*32;image=base64.b64encode((ROOT/'docs/media/so101-lab.jpg').read_bytes()).decode()
    def handle(route):
        path=route.request.url.split('/api/hardware/')[1];body=route.request.post_data_json if route.request.method=='POST' else None
        if body is not None:
            requests.append((path,copy.deepcopy(body)))
            if path=='calibration/start':
                fixture['calibration_session']=dict(stage='backup',session=sid,revision=1,backup_id=bid,restore_mode=bool(body.get('backup_id')),running=True,fresh=True,errors=[],warning=None,candidate=candidate)
                fixture['mode']='calibration'
            elif path=='calibration/command':
                s=fixture['calibration_session'];s['revision']+=1;op=body['op']
                if op=='release':s['stage']='restore_review' if s['restore_mode'] else 'reference'
                elif op=='reference':s.update(stage='ranges',joint=ranged[0],ranges={n:dict(min=900,max=3200,samples=18) for n in ranged})
                elif op=='next':
                    i=ranged.index(s['joint']);s.update(stage='review',joint=None) if i==len(ranged)-1 else s.update(joint=ranged[i+1])
                elif op in ('save','restore','cancel'):
                    s.update(stage={'save':'saved','restore':'restored','cancel':'cancelled'}[op],running=False,fresh=False,warning='OFFLINE FIXTURE · tork kapalı')
                    fixture['mode']='read_only';fixture['calibration_history']=[dict(id=bid,target='qa.json',created=1,stage=s['stage'],recovery_needed=False)]
            elif path=='disconnect':fixture.update(calibration_session={},mode='read_only',cameras=dict(wrist={},top={}))
            elif path=='camera':fixture['cameras'][body['role']]=dict(session=cid,fresh=True,running=True,image=image,width=1280,height=720,age_ms=10,calibration=dict(session=cid,enabled=False,sample_count=0,detected_corners=35))
            elif path=='camera/stop':fixture['cameras'][body['role']]={}
            elif path=='camera/calibration':
                s=fixture['cameras'][body['role']]['calibration'];op=body['op']
                if op=='enable':s.update(enabled=True,device_label=body['device_label'])
                elif op=='capture':s['sample_count']+=1
                elif op=='solve':s['candidate']=dict(session=cid,camera_matrix=[[900,0,640],[0,900,360],[0,0,1]],rms_px=.19,holdout_rms_px=[.25,.30,.2],training_samples=15,holdout_samples=3)
                elif op=='save':
                    s['saved']=copy.deepcopy(s['candidate']);s['live_pose']={'frame_id':20}
                    fixture['camera_profiles']=[dict(id='wrist/'+cid,role='wrist',device_label='OFFLINE UVC',size=[1280,720],rms_px=.19)]
                elif op=='workspace':s['workspace']=dict(reprojection_px=.21,base_from_camera=bool(body.get('base_pose')))
        route.fulfill(json=fixture)
    with sync_playwright() as p:
        browser=p.chromium.launch(channel='chrome',headless=True);page=browser.new_page(viewport=dict(width=1280,height=800))
        page.route('**/api/hardware/**',handle);page.on('pageerror',lambda e:errors.append(str(e)));page.goto(base)
        page.locator('#hardware-open').click();page.locator('#hw-motor-calibration-tab').click()
        page.wait_for_function("!document.querySelector('#mc-start').disabled")
        def fits(label,content):
            checks[label]=page.locator(content).evaluate('(e)=>e.scrollHeight<=e.clientHeight') and page.evaluate('document.documentElement.scrollWidth<=innerWidth&&document.documentElement.scrollHeight<=innerHeight')
        fits('motor_idle_fits','#hw-motor-calibration')
        page.locator('#mc-start').click();page.wait_for_function("document.querySelector('#mc-stage').textContent==='Yedek hazır'")
        checks['release_requires_checkbox']=page.locator('#mc-next').is_disabled();fits('backup_fits','#hw-motor-calibration')
        page.locator('#mc-ack').check();page.locator('#mc-next').click();page.wait_for_function("document.querySelector('#mc-stage').textContent==='Orta konum'")
        checks['ack_reset_between_steps']=not page.locator('#mc-ack').is_checked()
        page.wait_for_timeout(500);checks['reference_3d_canvas']=page.locator('#mc-reference-canvas').evaluate('(c)=>c.width>0&&c.height>0')
        page.screenshot(path=str(output/'motor-reference-fixture.png'))
        page.locator('#mc-ack').check();page.locator('#mc-next').click();page.wait_for_function("document.querySelector('#mc-stage').textContent==='Hareket aralıkları'")
        fits('ranges_fit','#hw-motor-calibration');checks['five_measured_joints_and_wrist_exception']=page.locator('.cal-range').count()==6 and 'sabit' in page.locator('#mc-ranges').inner_text()
        for i in range(5):
            page.locator('#mc-ack').check();page.locator('#mc-next').click();page.wait_for_timeout(350)
        page.wait_for_function("document.querySelector('#mc-stage').textContent==='Sonuçları incele'")
        fits('review_fits','#hw-motor-calibration');checks['review_has_six_settings']=page.locator('#mc-result tbody tr').count()==6
        page.locator('#mc-ack').check();page.locator('#mc-next').click();page.wait_for_function("document.querySelector('#mc-stage').textContent==='Kaydedildi'")
        checks['save_explicit']=next(b for path,b in requests if path=='calibration/command' and b['op']=='save')['confirmed']
        page.locator('#mc-next').click();page.wait_for_function("!document.querySelector('#mc-idle').classList.contains('hidden')")
        page.locator('#mc-restore').click();page.wait_for_function("document.querySelector('#mc-stage').textContent==='Yedek hazır'")
        page.locator('#mc-ack').check();page.locator('#mc-next').click();page.wait_for_function("document.querySelector('#mc-stage').textContent==='Yedeği incele'")
        page.locator('#mc-ack').check();page.locator('#mc-next').click();page.wait_for_function("document.querySelector('#mc-stage').textContent==='Yedek geri yüklendi'")
        checks['restore_roundtrip']=True;page.locator('#mc-next').click();page.wait_for_timeout(350)
        page.locator('#mc-start').click();page.wait_for_timeout(350);page.locator('#mc-cancel').click();page.wait_for_function("document.querySelector('#mc-stage').textContent==='İptal edildi'");checks['cancel_roundtrip']=True
        page.locator('#hw-camera-calibration-tab').click();page.locator('#hw-wrist-index').fill('0');page.locator('#hw-wrist-start').click()
        page.wait_for_timeout(350);checks['camera_identity_required']=page.locator('#cc-enable').is_disabled()
        page.locator('#cc-identity').check();page.locator('#cc-enable').click();page.wait_for_function("!document.querySelector('#cc-capture').disabled")
        fits('lens_fits','#hw-camera-calibration')
        for i in range(18):page.locator('#cc-capture').click();page.wait_for_timeout(90)
        page.wait_for_function("!document.querySelector('#cc-solve').disabled");page.locator('#cc-solve').click();page.wait_for_timeout(350)
        checks['heldout_metrics_visible']='0.19 / 0.30 px' in page.locator('#cc-error').inner_text()
        page.locator('#cc-save-ack').check();page.locator('#cc-save').click();page.wait_for_timeout(350)
        checks['lens_saved']='Profil kaydedildi' in page.locator('#cc-result').inner_text()
        page.locator('#cc-workspace-tab').click();page.locator('#cc-base').check();page.locator('#cc-plane-ack').check()
        fits('workspace_fits','#hw-camera-calibration');before=len(requests);page.locator('#cc-workspace-save').click()
        checks['blank_base_pose_rejected']=len(requests)==before and 'Altı poz alanını' in page.locator('#hw-message').inner_text()
        for i,value in enumerate([125,-170,20,0,0,90]):page.locator(f'#cc-pose-{i}').fill(str(value))
        page.locator('#cc-workspace-save').click();page.wait_for_timeout(350)
        checks['measured_anchor_sent']=requests[-1][1].get('base_pose')==[125,-170,20,0,0,90]
        checks['alignment_still_pending']='fiziksel doğrulama bekliyor' in page.locator('#cc-workspace-result').inner_text()
        fits('saved_workspace_fits','#hw-camera-calibration')
        page.screenshot(path=str(output/'camera-workspace-fixture.png'))
        for width,height in [(1440,900),(1728,1050)]:
            page.set_viewport_size(dict(width=width,height=height));page.wait_for_timeout(100);fits(f'workspace_fits_{width}','#hw-camera-calibration')
        page.keyboard.press('Escape');page.wait_for_timeout(350);checks['close_disconnects']=requests[-1][0]=='disconnect'
        checks['no_browser_errors']=not errors;browser.close()
    report=dict(checks=checks,passed=all(checks.values()),errors=errors,evidence='All hardware endpoints mocked; no physical calibration or camera capture.')
    (output/'checks.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
    if not report['passed']:raise AssertionError('Calibration UI validation failed')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--base',default='http://127.0.0.1:8772');p.add_argument('--output',default='artifacts/so101-calibration/ui');a=p.parse_args();check(a.base,a.output)
