// Reuse the lab's brain renderer, model checks, inspector and camera viewport.
const $=id=>document.getElementById(id);
const fmt=(v,n=2)=>Number.isFinite(v)?v.toFixed(n):'—';

export function createPhysicalUI({toast}){
  let state={},session='',history=[],camera='body',busy=false;
  document.body.classList.add('physical-mode');
  const panel=document.createElement('div');panel.className='physical-controls';
  panel.innerHTML=`<div class="section-label">GERÇEK SO-101 <span>CANLI</span></div>
  <h3>Sinek beyniyle yönlendir</h3><p>Üst kameradaki kırmızı nesnenin tarafı → görsel devre → taban. Başlangıç çevresinde ±15°; en fazla 30 saniye.</p>
  <div class="section-label spaced">KIRMIZI KÜP · ELLE ÖĞRET</div>
  <p>Kolu ve bileği destekle. Kaydı başlatınca altı motor serbest kalır. Kolu yavaşça küpe götür, kıskacı elle kapat ve küpü birkaç santimetre kaldır. En fazla 90 sn.</p>
  <label class="physical-check"><input id="physical-teach-supported" type="checkbox"> Kolu sürekli destekliyorum; motorların serbest kalmasına hazırım.</label>
  <button id="physical-teach_start" class="primary wide" disabled>Serbest bırak ve öğretimi kaydet</button>
  <button id="physical-teach_stop" class="secondary wide" disabled>Gösterimi bitir · kolu desteklemeye devam et</button>
  <div id="physical-teaching" role="status"></div>
  <div class="section-label spaced">POZ TUTMA VE TABAN</div>
  <label class="physical-check"><input id="physical-supported" type="checkbox"> Bileği destekliyorum; taban sabit, kıskaç masadan boşta.</label>
  <button id="physical-hold" class="secondary wide" disabled>Desteklediğim mevcut pozu tut</button>
  <label class="physical-check"><input id="physical-clear" type="checkbox"> Kol kendini tutuyor; ellerim çekildi ve alan boş.</label>
  <button id="physical-run" class="primary wide" disabled>2 · Beyinle yönlendir · 30 sn</button>
  <button id="physical-stop" class="physical-stop wide">HAREKETİ DURDUR · Esc</button>
  <div id="physical-status" role="status"></div><p id="physical-error" role="alert"></p>
  <button id="physical-cameras" class="secondary wide">Kameraları yeniden bağla</button>
  <p class="physical-note">Taban kontrolünde durdurmak gövde torkunu açık tutar. Öğretimde kol serbesttir; kayıt bitince de desteklemeye devam et. Gösterim kaydı kendi başına beyinle küp alma anlamına gelmez.</p>
  <div class="section-label spaced">MOTORLAR</div><div id="physical-motors"></div>
  <p id="physical-motor-warning" class="physical-note"></p>
  <a class="text-button" href="/">Simülasyon konsolu ↗</a>`;
  document.querySelector('.sidebar').prepend(panel);
  async function command(op){
    if(op==='hold'&&!$('physical-supported').checked)throw Error('Önce kolu desteklediğini doğrula.');
    if(op==='run'&&!$('physical-clear').checked)throw Error('Önce hareket alanının boş olduğunu doğrula.');
    if(op==='teach_start'&&!$('physical-teach-supported').checked)throw Error('Kolu desteklediğini ve motorların serbest kalmasına hazır olduğunu doğrula.');
    busy=true;
    try{
      const r=await fetch('/api/physical/command',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({op,session,preview:state.preview,confirmed:true})});
      const d=await r.json();if(!r.ok)throw Error(d.detail||'İşlem reddedildi');
      if(op==='hold')$('physical-supported').checked=false;
      if(op==='run')$('physical-clear').checked=false;
      if(op==='teach_start'){$('physical-teach-supported').checked=false;$('physical-supported').checked=false;$('physical-clear').checked=false;}
    }finally{busy=false;}
  }
  for(const op of ['hold','run','stop','cameras','teach_start','teach_stop'])$('physical-'+op).onclick=()=>command(op).catch(e=>toast(e.message));
  document.addEventListener('keydown',e=>{if(e.key==='Escape')command('stop').catch(()=>{});});
  document.addEventListener('visibilitychange',()=>{if(document.hidden)command('stop').catch(()=>{});});
  addEventListener('pagehide',()=>{navigator.sendBeacon('/api/physical/command',new Blob([JSON.stringify({op:'stop'})],{type:'application/json'}));});
  function configure(){
    $('session-title').textContent='SO-101 · Fiziksel beyin kontrolü';
    document.querySelector('.specimen .panel-header h1').innerHTML='<span class="panel-index">A</span> Canlı robot kameraları';
    document.querySelector('[data-camera="body"]').textContent='Üst kamera';
    document.querySelector('[data-camera="arena"]').textContent='Bilek';
    $('fly-image').alt='Gerçek SO-101 canlı kamera';
    $('eye-preview').classList.add('robot-eye');$('eye-preview').classList.remove('hidden');
    $('eye-title').textContent=camera==='body'?'BİLEK KAMERASI':'ÜST KAMERA · BEYİN GİRDİSİ';
    $('eye-expand').classList.remove('hidden');
    $('signal-title').textContent='Fiziksel duyusal telemetri';
    $('signal-left-label').textContent='Sol kırmızı';$('signal-right-label').textContent='Sağ kırmızı';
    $('signal-turn-label').textContent='Beyin yönü';
    $('signal-unit').textContent='Gerçek RGB → kırmızı belirginliği → anatomik görsel devre';
    $('distance-label').textContent='TABAN ENKODERİ';$('reward-label').textContent='MOTOR KOMUTU';
    const metrics=document.querySelectorAll('.metric-strip>div>span');
    metrics[1].textContent='EN YÜKSEK SICAKLIK';metrics[2].textContent='KALAN SÜRE';
    $('sim-engine').textContent='SO-101 / FİZİKSEL';$('playback-label').textContent='GERÇEK USB RGB';
    $('footer-scope').textContent='MaleCNS görsel alt devresi · Sınırlı taban yönlendirme';
    $('pause').innerHTML='■ Hareketi durdur';$('pause').classList.add('physical-stop');
    $('reset').classList.add('hidden');$('robot-loop-label').classList.add('hidden');
    $('experiment').disabled=true;$('model').disabled=true;
  }
  function render(){
    configure();
    const motorFresh=Date.now()/1000-(state.motor_wall_time??state.wall_time)<.5;
    const cameraFresh=Date.now()/1000-state.camera_wall_time<.4;
    const fresh=motorFresh&&cameraFresh,active=state.stage==='running',teaching=!!state.teaching?.active;
    const positioning=state.controller==='bounded_joint_positioning';
    const gripperOpening=state.controller==='empty_gripper_opening';
    const motors=state.motors||[];
    const jointLabels=['Taban','Omuz','Dirsek','Bilek eğim','Bilek dönüş','Kıskaç'];
    const outside=motors.filter(m=>m.in_range===false).map(m=>jointLabels[m.id-1]);
    const hot=motors.filter(m=>m.temperature_c>=50);
    const lastWarning=state.last_motor_warning;
    $('physical-motor-warning').textContent=!motorFresh?'Motor ölçümü gecikti.':lastWarning?
      `Son sıcaklık eşiği uyarısı · ${new Date(lastWarning.wall_time*1000).toLocaleTimeString('tr-TR')} · ${lastWarning.motors.map(m=>`${jointLabels[m.id-1]} ${m.temperature_c}°C`).join(', ')}`:'';
    const unsafe=motors.some(m=>m.temperature_c>=50||m.voltage_v<6||m.voltage_v>13.2||m.status||Math.abs(m.load)>120||m.operating_mode);
    $('physical-status').textContent=state.message||state.stage||'Bağlanıyor…';
    $('physical-error').textContent=state.action_error||state.error||(!fresh?'Güncel veri bekleniyor…':outside.length?`${outside.join(', ')} hareket sınırında. Kolu destekleyerek eklemleri sınırdan biraz uzaklaştır.`:'');
    if(!state.error&&hot.length)$('physical-error').textContent=hot.map(m=>`${jointLabels[m.id-1]}: ${m.temperature_c}°C ölçüm uyarısı. Poz tutma/hareket kapalı; okuma kaydı kullanılabilir.`).join(' ');
    $('physical-hold').disabled=busy||active||teaching||!fresh||!!state.error||unsafe||motors.some(m=>m.torque||m.in_range===false);
    $('physical-run').disabled=busy||active||teaching||!fresh||!!state.error||unsafe||motors.length!==6||!motors.slice(0,5).every(m=>m.torque);
    $('physical-teach_start').disabled=busy||active||teaching||!fresh||!!state.error||motors.length!==6||outside.length>0;
    $('physical-teach_stop').disabled=busy||!teaching;
    const taught=state.teaching;
    const heat=(taught?.warnings||[]).filter(w=>w.code==='temperature');
    if(teaching&&heat.length)$('physical-error').textContent=heat.map(w=>`${jointLabels[w.motor_id-1]} ${w.value}°C okundu. Kolu dinlendir; ölçüm kaydı sürüyor, motorlar serbest.`).join(' ');
    $('physical-teaching').textContent=teaching?`KAYIT · ${fmt(taught.seconds,1)} sn · ${taught.samples} örnek · KOL SERBEST${taught.outside_execution_limits?.length?' · Sınır dışındaki eklemler: '+taught.outside_execution_limits.join(', '):''}`:
      taught?.valid?`Gösterim kaydedildi · ${taught.samples} örnek · ${fmt(taught.seconds,1)} sn${taught.requires_review?' · Ölçüm uyarıları inceleme bekliyor':''}`:
      taught?.error?`Kayıt kesildi: ${taught.error} · Kolu destekle.`:'';
    $('physical-stop').textContent=teaching?'KAYDI DURDUR · KOL SERBEST · Esc':'HAREKETİ DURDUR · Esc';
    $('physical-motors').replaceChildren(...motors.map(m=>{const row=document.createElement('div');
      row.className='physical-motor';const a=document.createElement('span'),b=document.createElement('b');
      a.textContent=['Taban','Omuz','Dirsek','Bilek eğim','Bilek dönüş','Kıskaç'][m.id-1];
      b.textContent=`${m.position} · ${m.temperature_c}°C · ${m.in_range===false?'SINIR DIŞI':m.torque?'tork açık':'serbest'}`;row.append(a,b);return row;}));
    $('distance').textContent=state.q?.[0]??'—';
    $('speed').textContent=motors.length?Math.max(...motors.map(m=>m.temperature_c))+' °C':'—';
    $('sim-time').textContent=active?fmt(state.seconds_left,1)+' s':'—';
    $('reward').textContent=state.run_commands||0;
    $('episode').textContent='FİZİKSEL SO-101';
    $('live-label').innerHTML='<i></i> '+(!fresh?'KAMERA GECİKTİ':teaching?'ELLE ÖĞRETİM · KOL SERBEST':active?(gripperOpening?'BOŞ KISKAÇ AÇILIYOR':positioning?'GÖVDE KONUMLANDIRMA':'BEYİN → MOTOR'):(motors.some(m=>m.torque)?'GÖZLEM · POZ TUTULUYOR':'GÖZLEM · TORK KAPALI'));
    $('episode-stats').textContent=teaching?'Altı eklem kaydediliyor; motor hedefi gönderilmiyor':active?(gripperOpening?'Düşük torklu açma · Gövde pozu korunuyor':positioning?'Önizlenmiş eklem hedefi · Gövde torku korunuyor':'Canlı kırmızı uyarana göre yönlendirme'):'Hareket bekliyor';
    $('rtf').textContent='±15°';$('rtf').title='Tabanın bu oturumdaki başlangıcına göre sınır';
    $('contacts').textContent=`${state.decision?.visible?'Kırmızı görülüyor':'Kırmızı bekleniyor'} · Hedef ${state.goal??'—'}`;
    $('footer-status').textContent=`Fiziksel kamera #${state.sequence||0} · Kontrol 100 ms · Komut ${state.run_commands||0}`;
    $('render-quality').textContent='1280 × 720 · USB RGB';
    if(!fresh){$('fly-image').removeAttribute('src');$('eye-image').removeAttribute('src');}
  }
  async function poll(){
    const r=await fetch('/api/physical/state',{headers:{'X-Neural-Session':session}});
    const d=await r.json();if(!r.ok)throw Error(d.detail||'Fiziksel servis hazır değil');
    state=d;session=d.session;
    const decision=d.decision||{},layers=decision.layer_activity||[];
    const fresh=Date.now()/1000-(d.camera_wall_time||d.wall_time)<.5&&!d.error;
    history.push([d.sequence,...(decision.sensor_values||[0,0])]);if(history.length>120)history.shift();
    return {alive:true,job:{status:'idle'},simulation:{physical:true,behavior:'vision',seq:d.sequence||1,
      model:'local-vision-seed42',model_sha256:d.model_sha256,circuit_identity:d.circuit_sha256,
      activity:fresh?layers.flat():null,layer_means:layers.map(a=>a.reduce((s,x)=>s+x,0)/a.length),
      image:fresh?d.images?.[camera==='body'?'top':'wrist']:'',eyes_image:fresh?d.images?.[camera==='body'?'wrist':'top']:'',
      camera,odor:decision.sensor_values||[0,0],steering:decision.drive||0,history,
      neural:{source:'physical anatomical vision',decision_applied:d.brain_connected&&d.stage==='running',sample_time_s:d.run_started?Math.max(0,d.wall_time-d.run_started):0},
      time_s:d.run_started?Math.max(0,d.wall_time-d.run_started):0,paused:false,idle:d.stage!=='running',
      outcome:'running',episode:1,successes:0,completed:0,falls:0,contacts:'—',physics_dt:0,control_dt:.1}};
  }
  configure();
  return {poll,render,configure,command,control:async body=>{
    if(body.op==='pause')return command('stop');
    if(body.op==='camera'){if(body.camera)camera=body.camera;return;}
    throw Error('Fiziksel modda soldaki robot kontrollerini kullan.');
  }};
}
