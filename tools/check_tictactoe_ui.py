"""Bounded browser checks for the local game; no physical hardware access."""
import argparse
import json
from pathlib import Path
import time
import urllib.request
from playwright.sync_api import sync_playwright


def check(base,output):
    output=Path(output);output.mkdir(parents=True,exist_ok=True);checks={};errors=[]
    def api(path,body=None):
        request=urllib.request.Request(base+'/api/'+path,data=None if body is None else json.dumps(body).encode(),headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(request,timeout=15) as r:return json.load(r)
    def state():return api('state')['simulation']
    def until(predicate,seconds=25):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            s=state()
            if predicate(s):return s
            time.sleep(.15)
        raise AssertionError('Timed out waiting for game: '+str({k:s.get(k) for k in ('error','game')}))
    with sync_playwright() as p:
        browser=p.chromium.launch(channel='chrome',headless=True)
        page=browser.new_page(viewport=dict(width=1728,height=1050));page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto(base);page.wait_for_function("document.querySelector('#experiment').value==='tictactoe'")
        page.wait_for_function("document.querySelector('#fly-image').naturalWidth===1920")
        s=state();page.wait_for_function('(sha)=>document.querySelector("#checkpoint").textContent.includes(sha)',arg=s['model_sha256'][:12])
        checks['checkpoint_matches']=True;checks['anatomical_neurons']='3.488' in page.locator('#odor-neurons').inner_text()
        checks['trainable_edges']='81.104' in page.locator('#odor-weights').inner_text()
        for width,height in [(1728,1050),(1440,900),(1280,800)]:
            page.set_viewport_size(dict(width=width,height=height));page.wait_for_timeout(100)
            checks[f'fullscreen_{width}x{height}']=page.evaluate("document.documentElement.scrollHeight<=innerHeight&&document.documentElement.scrollWidth<=innerWidth")
            checks[f'training_controls_visible_{width}x{height}']=page.locator('#train').evaluate('(e)=>e.getBoundingClientRect().bottom<innerHeight-24')
        page.set_viewport_size(dict(width=1728,height=1050))
        api('control',dict(op='pause',paused=False))
        page.locator('#game-execution').select_option('virtual_board')
        page.locator('#game-opponent').select_option('human');page.locator('#game-side').select_option('-1')
        page.wait_for_timeout(1000)
        checks['settings_draft_survives_poll']=page.locator('#game-side').input_value()=='-1' and page.locator('#game-execution').input_value()=='virtual_board'
        page.locator('#game-start').click()
        s=until(lambda s:s['game']['waiting_for_human'] and s['game']['agent']==-1 and sum(abs(v) for v in s['game']['board'])==0)
        page.wait_for_function("!document.querySelector('#game-board button').disabled")
        page.locator('#game-board button').nth(0).click()
        s=until(lambda s:sum(abs(v) for v in s['game']['board'])>=2)
        checks['human_click_and_neural_reply']=s['game']['board'][0]==1 and -1 in s['game']['board']
        checks['camera_confirms_board']=s['game']['observed']['valid'] and s['game']['observed']['board']==s['game']['board']
        checks['no_minimax_live']=all(m['source'] in ('human_virtual_placement','connectome_strategy') for m in s['game']['move_log'])
        for key in ('rgb','depth','detection'):
            page.locator(f'[data-eye="{key}"]').click();page.wait_for_timeout(100)
            checks[f'eye_{key}']=page.locator('#eye-image').evaluate('(e)=>e.naturalWidth===640')
        page.locator('#pause').click();a=until(lambda s:s['paused']);time.sleep(.4);b=state()
        checks['pause_freezes_game']=a['game']['board']==b['game']['board'] and abs(a['time_s']-b['time_s'])<.02
        before=b['camera_pose']['azimuth'];box=page.locator('#fly-image').bounding_box()
        page.mouse.move(box['x']+box['width']*.5,box['y']+box['height']*.6);page.mouse.down();page.mouse.move(box['x']+box['width']*.6,box['y']+box['height']*.65,steps=7);page.mouse.up()
        until(lambda s:abs(s['camera_pose']['azimuth']-before)>1);checks['mouse_orbit']=True
        page.locator('#sim-home').click();page.locator('#pause').click();until(lambda s:not s['paused'])
        api('tictactoe/settings',dict(opponent='self',agent=1));first=until(lambda s:s['game']['opponent']=='self')['episode']
        ended=until(lambda s:s['episode']==first and s['outcome']=='draw',seconds=30)
        checks['self_play_draw']=len(ended['game']['move_log'])==9
        nextgame=until(lambda s:s['episode']>first,seconds=12);checks['automatic_loop']=nextgame['game']['draws']>=1
        api('tictactoe/settings',dict(opponent='human',agent=1));until(lambda s:s['game']['waiting_for_human'] and s['game']['opponent']=='human')
        page.locator('#validation-open').click();checks['strategy_report']=page.locator('#validation-dialog').is_visible() and '4.520' in page.locator('#validation-criterion').inner_text().replace('4520','4.520')
        page.screenshot(path=str(output/'strategy-results.png'));page.locator('#validation-close').click()
        page.locator('#analyses-tab').click();checks['brain_analyses']=page.locator('#heat-map').is_visible() and page.locator('#xray-map').is_visible()
        page.screenshot(path=str(output/'game-brain-analyses.png'));page.locator('#metrics-tab').click()
        page.locator('#delta-mode').click();checks['synaptic_delta']=page.locator('#scale-title').inner_text()=='BAĞLANTI ÇARPANI';page.locator('#activity-mode').click()
        page.screenshot(path=str(output/'game-lab.png'))
        checks['no_browser_errors']=not errors;browser.close()
    report=dict(checks=checks,passed=all(checks.values()),errors=errors);(output/'ui-check.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
    if not report['passed']:raise AssertionError('UI checks failed')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--base',default='http://127.0.0.1:8772');p.add_argument('--output',default='artifacts/tictactoe/ui');a=p.parse_args();check(a.base,a.output)
