import { createBrain } from './brain-view.js';
import { createAnalyses } from './brain-analyses.js';
import { createInspector } from './inspector.js';
import { edgeSignal, modelMatches } from './neural-math.js';
import { behaviorUI } from './flight-ui.js';

const $ = id => document.getElementById(id);
const fmt = (n, digits=2) => Number.isFinite(n) ? n.toFixed(digits) : '—';
const count = n => Number(n).toLocaleString('tr-TR');
let simulation = {}, catalog = {}, selectedModel = null, graph = null, sceneView = null;
let lastSequence = -1, lastModelId = null, selectedNode = null, mode = 'activity', camera = 'body', latestRun = null;
let completedJob = null, paused = false, trainingHistory = [], lastPacketAt = 0;
let toastTimer;
let analyses=null, modelRequest=0;
let inspector=null, selection=null, selectedEdge=-1, pickMode='node';
let behavior=null;
let eyeMode='detection';
const isFlight=()=>simulation.behavior==='flight';
const isRobot=()=>simulation.behavior==='so101';

function selectEntity(next, open=true) {
  selection=next;
  selectedNode=next.kind==='node'?(graph?.nodes.find(n=>n.id===next.id)||sceneView?.neuron(next.id)):null;
  selectedEdge=next.kind==='edge'?graph?.edges.findIndex(e=>graph.nodes[e.a].id===next.source&&graph.nodes[e.b].id===next.target):-1;
  $('inspect-open').classList.remove('hidden');
  if(next.kind==='node'){
    $('node-type').textContent=selectedNode?.group||'NÖRON';
    $('node-title').textContent=selectedNode?.label||next.id;
    $('node-description').textContent=selectedNode?.position?'Soma: '+selectedNode.position.map(x=>fmt(x,1)).join(' / ')+' µm':'Gerçek iskelet / yerel anatomik kayıt';
    $('node-id').textContent=next.id;
    $('node-activity').textContent=fmt(simulation.activity?.[selectedNode?.index],4);
  }else{
    const edge=graph?.edges[selectedEdge];
    $('node-type').textContent='BAĞLANTI';
    $('node-title').textContent=edge?`${graph.nodes[edge.a].group} → ${graph.nodes[edge.b].group}`:'Yönlü anatomik bağlantı';
    $('node-description').textContent=`${next.source} → ${next.target}`;
    $('node-id').textContent='Kaynak → hedef';
    $('node-activity').textContent=edge?fmt(simulation.activity?.[graph.nodes[edge.b].index],4):'—';
  }
  updateSelectionValue();
  sceneView?.update(simulation.activity);
  analyses?.update(simulation);
  if(open)inspector?.show(next,simulation.model||$('model').value);
}

function updateSelectionValue(){
  const edge=selection?.kind==='edge'?graph?.edges[selectedEdge]:null;
  $('node-value-label').textContent=selection?.kind==='edge'?'GİRDİ KATKISI':'AKTİVİTE';
  $('node-activity').textContent=selection?.kind==='edge'?
    (edge&&modelMatches(graph,simulation,selectedModel)?fmt(edgeSignal(graph,edge,simulation.activity,selectedModel.gains[selectedEdge]),5):'—'):
    fmt(simulation.activity?.[selectedNode?.index],4);
  $('node-activity').title=edge?(isRobot()?'Yanıt kazancı × kaynak aktivitesi × mevcut ağırlık / gelen ağırlık toplamı; sigmoid öncesi katkı':'2 × kaynak yanıtı × mevcut ağırlık; hedefin tanh öncesi girdisine katkı'):'Modelin 0–1 arası sürekli yanıtı';
}

function toast(message) {
  $('toast').textContent = message;
  $('toast').classList.remove('hidden');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => $('toast').classList.add('hidden'), 6000);
}
async function api(path, body) {
  const options = body === undefined ? {} : {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)};
  const response = await fetch('/api/' + path, options);
  const result = await response.json();
  if (!response.ok) throw Error(typeof result.detail === 'string' ? result.detail : 'Giriş değerlerini kontrol et.');
  return result;
}
async function control(body) { return api('control', body); }
function bind(id, action) { $(id).addEventListener('click', async () => {try {await action();} catch(e) {toast(e.message);}}); }
function integer(id,min,max) {
  const value=Number($(id).value);
  if (!Number.isInteger(value) || value<min || value>max) throw Error(`${id==='steps'?'Adım':'Tohum'}: ${min}–${max} arasında bir tam sayı gir.`);
  return value;
}
function goal() {
  const value=[Number($('goal-x').value),Number($('goal-y').value)];
  if(isRobot()){
    if(!value.every(Number.isFinite)||value[0]<125||value[0]>160||value[1]<-180||value[1]>-135)throw Error('Kutu merkezi: X 125–160 mm, Y −180…−135 mm.');
  }else if (value.some(x=>!Number.isFinite(x)||x < -30||x > 30)) throw Error('Hedef -30 ile 30 mm arasında olmalı.');
  return value;
}
async function refreshCatalog() {
  catalog = await api('catalog');
  const task=simulation.behavior||$('experiment').value||'odor';
  $('experiment').replaceChildren(...catalog.experiments.map(e=>{const option=document.createElement('option');option.value=e.id;option.textContent=e.title;return option;}));
  $('experiment').value=task;
  const current=$('model').value;
  $('model').replaceChildren(...catalog.models.map(m=>{const option=document.createElement('option');option.value=m.id;option.textContent=m.name;option.dataset.task=m.task||'odor';return option;}));
  if (catalog.models.some(m=>m.id===current)) $('model').value=current;
  behaviorUI(simulation.behavior||'odor');
}
async function refreshModel(id) {
  const request=++modelRequest, result=await api('model/'+encodeURIComponent(id));
  if(request!==modelRequest)return;
  if(!graph||graph.circuit_identity!==result.circuit_identity){
    const next=await api('graph?model='+encodeURIComponent(id));
    if(request!==modelRequest)return;
    sceneView?.dispose();analyses?.dispose();
    graph=next;selectedNode=selection=null;selectedEdge=-1;
    $('detail-drawer').classList.add('hidden');$('inspect-open').classList.add('hidden');
    $('node-title').textContent='Bir nöron seç';$('node-type').textContent='SEÇİM YOK';
    $('node-id').textContent='—';$('node-description').textContent='Seçili görevdeki bir nörona tıkla.';
    sceneView=createBrain(graph,{getState:()=>({simulation,selectedModel,selectedNode,selectedEdge,selection,mode,pickMode}),onSelect:selectEntity});
    analyses=createAnalyses(graph,{getSelection:()=>selection});
    const short={Photoreceptor:'Foto',Optic_relay:'Optik',Visual_projection:'VP',Descending:'İnen',Touch:'Temas',VNC_relay:'VNC',VNC_premotor:'Ön motor',Motor:'Motor',Kenyon_Cell:'Kenyon'};
    graph.group_ranges.forEach((g,i)=>{const cell=$('layer-'+i).parentElement.parentElement;cell.querySelector('b').textContent=short[g.name]||g.name;cell.querySelector('small').textContent=count(g.count);cell.title=g.name;});
    document.querySelector('[data-brain-focus="circuit"]').textContent='Seçili devre';
    $('connection-density').title=`Sade: 520 temsilci. Tümü: ${count(graph.edges.length)} konumlu bağlantı.`;
    $('odor-neurons').replaceChildren(document.createTextNode(count(graph.total)+' '),Object.assign(document.createElement('em'),{textContent:'model nöronu'}));
    $('scope-model').textContent=`Seçili devre ${count(graph.total)} nöron içerir; ${count(graph.nodes.length)} soma konumu ve ${count(graph.edges.length)} konumlu bağlantı çizilebilir. Katmanlar: ${graph.group_ranges.map(g=>g.name).join(' → ')}. Diğer anatomik iskeletler gri gösterilir.`;
  }
  selectedModel=result;
  graph.input_sums=result.input_sums;
  const trainableLayers=result.robot_adapter?.trainable_anatomical_layers||[2];
  $('odor-weights').replaceChildren(document.createTextNode(count(graph.layer_counts.reduce((n,l,i)=>n+(trainableLayers.includes(i)?l.total:0),0))+' '),Object.assign(document.createElement('em'),{textContent:'eğitilebilir bağlantı'}));
  updateSelectionValue();
  const item=catalog.models?.find(m=>m.id===id);
  const t=selectedModel.training, e=isFlight()?selectedModel.flight_evaluation:selectedModel.walk_evaluation;
  $('benchmark').textContent=e ? `${e.success_count} / ${e.episodes}`:'—';
  $('benchmark').title=e?.criterion||'Seçili modelin kayıtlı fizik değerlendirmesi';
  $('export-model').href='/api/model/'+encodeURIComponent(id)+'/export';
  $('validation-open').disabled=!e;
  $('model-loss').textContent=t ? fmt(t.after_mse,5):'—';
  $('model-loss').title=$('loss-value').title=t?.mse_scope?'Gösterim öğrenme hatası; son konum okuması uyarlamasından önce. Görev başarısı fizik testinde ölçülür.':'Kayıtlı öğrenme doğrulama hatası';
  $('checkpoint').textContent='CHECKPOINT '+selectedModel.sha256.slice(0,12);
  $('brain-model').textContent=item?.name ?? id;
  $('loss-value').textContent=t ? fmt(t.after_mse,5):'—';
  $('loss-change').textContent=t ? `${fmt((t.after_mse/t.before_mse-1)*100,1)}%`:'Başlangıç';
  $('loss-steps').textContent=t ? `${count(t.cumulative_steps??t.steps)} adım`:'Eğitim uygulanmadı';
  $('changed').textContent=t ? `${count(t.changed_existing_synaptic_gains)} bağlantı değişti`:'Ağırlıklar başlangıç halinde';
  trainingHistory=t?.history?.map(p=>[p.step,p.validation_mse]) ?? [];
  if(sceneView){sceneView.update(simulation.activity);sceneView.freshness();}
  analyses?.update(simulation);
  await inspector?.modelChanged(id);
}
function chart(canvas, series, {min=0,max=1}={}) {
  const rect=canvas.getBoundingClientRect(); if (!rect.width || !rect.height) return;
  const dpr=Math.min(devicePixelRatio||1,2), w=rect.width,h=rect.height;
  if(canvas.width!==Math.round(w*dpr)||canvas.height!==Math.round(h*dpr)){canvas.width=Math.round(w*dpr);canvas.height=Math.round(h*dpr);}
  const c=canvas.getContext('2d');c.setTransform(dpr,0,0,dpr,0,0);c.clearRect(0,0,w,h);
  c.strokeStyle='#253746';c.lineWidth=.6;
  for(let i=0;i<4;i++){const y=3+(h-6)*i/3;c.beginPath();c.moveTo(0,y);c.lineTo(w,y);c.stroke();}
  for(let i=0;i<8;i++){const x=w*i/7;c.beginPath();c.moveTo(x,0);c.lineTo(x,h);c.stroke();}
  for(const {values,color} of series){
    if(values.length<2)continue;
    c.beginPath();values.forEach((v,i)=>{const x=i/(values.length-1)*w,y=h-3-(v-min)/Math.max(max-min,1e-8)*(h-6);if(i)c.lineTo(x,y);else c.moveTo(x,y);});c.strokeStyle=color;c.lineWidth=1.6;c.stroke();
  }
}
function updateCharts(job) {
  const h=simulation.history ?? [];
  chart($('signal-chart'),[{values:h.map(x=>x[1]),color:'#62d8d0'},{values:h.map(x=>x[2]),color:'#eaa867'}],{max:simulation.behavior==='vision'?Math.max(.00001,...h.flatMap(x=>[x[1],x[2]])):1});
  const active=['training','evaluating','cancelling'].includes(job?.status);
  const samples=active ? job.history ?? [] : trainingHistory;
  chart($('loss-chart'),[{values:samples.map(p=>p[1]),color:'#62d8d0'}],{min:0,max:Math.max(.01,...samples.map(p=>p[1]))});
  if(active){
    $('loss-source').textContent='YENİ EĞİTİM';
    $('loss-value').textContent=fmt(job.loss,5);
    $('loss-change').textContent='';
    $('loss-steps').textContent=`${count(job.step||0)} / ${count(job.steps)} adım`;
    $('changed').textContent=job.status==='evaluating'?`${job.evaluated||0} / ${job.evaluation_total||6} fizik testi`:'Model eğitiliyor';
  } else $('loss-source').textContent='SEÇİLİ MODEL';
}
async function updateJob(job) {
  const busy=['training','evaluating','cancelling'].includes(job.status);
  $('train').disabled=busy;
  $('cancel').classList.toggle('hidden',!busy);
  $('cancel').disabled=job.status==='cancelling';
  const labels={idle:'Yeni deney hazır',training:'Model eğitiliyor',evaluating:'Fizik testleri çalışıyor',complete:'Deney tamamlandı',failed:'Deney başarısız',cancelled:'Deney durduruldu',cancelling:'Durduruluyor'};
  $('job-state').textContent=labels[job.status]||'Yeni deney hazır';
  const percent=job.status==='complete'?100:job.status==='evaluating'?75+25*(job.evaluated||0)/(job.evaluation_total||6):busy?75*(job.step||0)/(job.steps||1):0;
  $('job-percent').textContent=`${Math.round(percent)}%`;
  $('job-progress').style.width=percent+'%';
  if(job.status==='training') $('job-note').textContent=`${count(job.step||0)} / ${count(job.steps)} adım · Canlı görünüm seçili modelle devam eder.`;
  else if(job.status==='evaluating') $('job-note').textContent=`Test ${job.evaluated||0} / ${job.evaluation_total||6} · ${{trained:'Eğitimli',untrained:'Eğitimsiz',silenced:'Çıkış kapalı'}[job.variant]||'Hedef'}: ${job.success_count||0} başarılı.`;
  else if(job.message&&!isFlight()) $('job-note').textContent=job.message;
  if(job.status==='complete'&&job.id!==completedJob){
    completedJob=latestRun=job.id;
    await refreshCatalog();
    $('load-new').classList.remove('hidden');
    toast('Eğitim ve fizik testleri tamamlandı. Yeni modeli seçerek karşılaştırabilirsin.');
    if(simulation.model)await refreshModel(simulation.model);
  }
  if(['cancelled','failed'].includes(job.status)&&job.id!==completedJob){completedJob=job.id;if(simulation.model)await refreshModel(simulation.model);}
}
function updateSimulation(s) {
  const switching=behavior!==s.behavior;
  if(s.goal_mm&&(!simulation.seq||switching)){$('goal-x').value=s.goal_mm[0];$('goal-y').value=s.goal_mm[1];}
  simulation=s; paused=!!s.paused; lastPacketAt=Date.now();
  if(switching){
    behavior=s.behavior;behaviorUI(behavior);$('experiment').value=behavior;
  }
  camera=s.camera;document.querySelectorAll('[data-camera]').forEach(b=>b.classList.toggle('active',b.dataset.camera===camera));
  $('sim-empty').classList.add('hidden');
  $('fly-image').style.visibility='visible';
  $('fly-image').src='data:image/jpeg;base64,'+s.image;
  updateEyes(s);
  $('render-quality').textContent=s.render?`${s.render.width} × ${s.render.height} · ${s.render.msaa}× MSAA`:'GÖRÜNTÜ AKIŞI';
  $('distance').innerHTML=fmt(s.distance_mm)+'<small> mm</small>';
  $('speed').innerHTML=fmt(s.speed_mm_s,1)+'<small> mm/s</small>';
  $('sim-time').innerHTML=fmt(s.time_s)+'<small> s</small>';
  $('reward').textContent=fmt(s.reward,3);
  $('episode').textContent='BÖLÜM '+String(s.episode).padStart(3,'0');
  $('live-label').innerHTML=`<i></i> ${s.paused?'DURAKLATILDI':s.idle?'BOŞTA':'CANLI FİZİK'}`;
  $('pause').innerHTML=s.paused?'<span>▶</span> Devam et':'<span>Ⅱ</span> Duraklat';
  $('episode-stats').textContent=isRobot()?`Bu oturum: ${s.successes}/${s.completed} yerleştirme · ${s.falls} sınır ihlali`:isFlight()?`Bu oturum: ${s.successes}/${s.completed} hedef · ${s.falls} uçuş sınırı`:`Bu oturum: ${s.successes}/${s.completed} hedef · ${s.falls} devrilme`;
  $('rtf').textContent=fmt(s.rtf,isFlight()?3:2)+' ×';
  $('rtf').title='Simülasyon süresi / gerçek süre';
  $('odor-left').textContent=fmt(s.odor[0],s.behavior==='vision'?5:3);$('odor-right').textContent=fmt(s.odor[1],s.behavior==='vision'?5:3);
  $('steering').textContent=fmt(isFlight()?s.yaw_rate_rad_s:s.steering,3);
  $('contacts').textContent=isFlight()?`Z ${fmt(s.altitude_mm,1)} mm · ${fmt(s.wing_hz,1)} Hz`:s.behavior==='terrain'?`Engel teması: ${count(s.barrier_contacts||0)}`:`Temas: ${s.contacts}`;
  if(isRobot()){
    $('contacts').textContent=`${s.robot.phase} · ${s.robot.holding?'İki çene temaslı':'Kavrayıcı serbest'}`;
    $('odor-left').textContent=fmt(s.robot.cube_height_mm,1);
    $('odor-right').textContent=fmt(s.robot.joints[5],2);
    const target=s.robot.action_mode==='target';
    $('signal-turn-label').textContent=target?'Hedef XYZ':'ΔXYZ';
    $('steering').textContent=(target?s.robot.target_mm:s.robot.action.slice(0,3).map(v=>v*3)).map(v=>fmt(v,1)).join(' / ');
    $('steering').title=target?'Ağın ürettiği uç nokta hedefi, dünya koordinatında mm':'Öğrenilmiş ΔX / ΔY / ΔZ, mm / karar';
  }
  s.layer_means.forEach((v,i)=>{$('layer-'+i).style.width=(v*100)+'%';$('layer-'+i).parentElement.title=`Ortalama aktivite: ${fmt(v,4)}`;});
  $('outcome').classList.toggle('hidden',s.outcome==='running');
  $('outcome').textContent={success:isRobot()?'Küp kutuda · görev tamamlandı':s.behavior==='avoidance'?'Kaynaktan uzaklaşıldı':s.behavior==='terrain'?'Engel geçildi':isFlight()?'Kokulu hedefe ulaşıldı':'Hedefe ulaşıldı',fallen:'Denge kaybı',sensor_stale:'Kamera izini kaybetti · hareket durduruldu',retry_exhausted:'3 girişim tamamlandı · görev durdu',timeout:'Süre doldu',unsafe:isRobot()?'Deney sınır nedeniyle durdu':'Tehlike alanına girildi'}[s.outcome]||'';
  $('footer-status').textContent=isFlight()?'Fizik 0,05 ms · Kanat 0,2 ms · Beyin kararı 10 ms':`Fizik ${fmt(s.physics_dt*1000,1)} ms · Sensör / karar 10 ms · Canlı veri`;
  if(isRobot())$('footer-status').textContent=`Fizik ${fmt(s.physics_dt*1000,1)} ms · Beyin kararı ${fmt(s.control_dt*1000,0)} ms · ${s.robot.sensor_source}`;
  if(isRobot())$('robot-sensor').value=s.robot.sensor_mode||'state';
  $('connection').classList.add('ready');$('connection').innerHTML='<i></i> Yerel bağlantı aktif';
  sceneView?.update(s.activity);
  sceneView?.freshness();
  const matches=graph&&modelMatches(graph,s,selectedModel);
  analyses?.update(matches?s:{...s,activity:null});
  inspector?.tick(matches?s.activity:null,s.model);
  updateSelectionValue();
  if(`${s.behavior}:${s.model}`!==lastModelId){lastModelId=`${s.behavior}:${s.model}`;$('model').value=s.model;refreshModel(s.model).catch(e=>toast(e.message));}
}
function updateEyes(s){
  const robot=s.behavior==='so101',p=s.robot?.perception;
  $('eye-preview').classList.toggle('hidden',robot?!p:s.behavior!=='vision');
  const frame=robot?s.eyes?.[eyeMode]:s.eyes_image;
  if(frame)$('eye-image').src='data:image/jpeg;base64,'+frame;
  else $('eye-image').removeAttribute('src');
  if(!robot||!p)return;
  $('eye-image').alt=eyeMode==='depth'?'Algılama kamerasının 0,2–1 metre derinlik haritası':'Ağın kararına giren kamera karesi'+(eyeMode==='detection'?' ve kırmızı küp işareti':'');
  $('eye-status').textContent=`${p.valid?(p.visible?'KÜP GÖRÜLÜYOR':'KISA SÜRELİ TAHMİN'):'GÖRÜŞ KAYIP'} · ${p.age_s==null?'—':fmt(p.age_s*1000,0)} ms`;
  $('eye-status').classList.toggle('lost',!p.valid);
  const xyz=p.estimated_cube?.map(v=>fmt(v*1000,1)).join(' / ')||'—';
  $('eye-detail').textContent=eyeMode==='depth'?`DERİNLİK · 200–1000 mm · Yakın: açık renk`:`KÜP XYZ · ${xyz} mm`;
  const sameDecision=p.frame_id===s.neural?.sensor_frame_id;
  $('eye-sync').textContent=`KARE ${p.frame_id} · ${fmt(p.sample_time_s,2)} s · ${sameDecision?'Kutu: kalibre':'Karar uygulanmadı'}`;
  $('eye-detail').title=`Kare ${p.frame_id} · ${fmt(p.sample_time_s,3)} s · ${p.width}×${p.height} · ${fmt(1/s.control_dt,0)} Hz karar\nKutu: kalibre edilmiş hedef. ${p.kinematic_prediction?'Kavrama sırasında eklem tahmini ile birleştiriliyor.':'Konum renk ve derinlikten çıkarılıyor.'}`;
  $('eye-image').dataset.frameId=p.frame_id;
  const r=s.robot.recovery;
  $('eye-attempt').textContent=s.outcome==='success'?'YERLEŞTİRME TAMAM':`GİRİŞİM ${r?.attempt||1} / ${r?.max_attempts||3}`;
  $('eye-attempt').title='Aynı sahnede en çok 3 girişim. Yeniden deneme gözetmeni ağın görev belleğini sıfırlar; hareketleri ağ üretir.';
}
async function poll() {
  if(document.hidden){setTimeout(poll,1000);return;}
  try {
    const data=await api('state');
    if(data.simulation.starting){
      simulation={...data.simulation, activity:null};lastPacketAt=0;lastSequence=-1;
      behaviorUI(simulation.behavior);$('experiment').value=simulation.behavior;
      $('fly-image').style.visibility='hidden';$('sim-empty').classList.remove('hidden');
      $('sim-empty').textContent=isFlight()?'FlyBody uçuş politikası hazırlanıyor…':'Görev devresi ve fizik ortamı hazırlanıyor…';
      sceneView?.update(null);sceneView?.freshness();analyses?.update(simulation);
      return;
    }
    await updateJob(data.job);
    if(data.simulation.error) throw Error(data.simulation.error);
    if(!data.alive) throw Error('Simülasyon işlemi durdu. Sunucu kaydını kontrol et.');
    const sequence=`${data.simulation.behavior}:${data.simulation.seq}`;
    if(data.simulation.seq&&sequence!==lastSequence){lastSequence=sequence;updateSimulation(data.simulation);}
    updateCharts(data.job);
    if(lastPacketAt&&Date.now()-lastPacketAt>5000) throw Error('Canlı görüntü gecikti; son veri gösteriliyor.');
  } catch(e) {
    $('connection').classList.remove('ready');$('connection').innerHTML='<i></i> Bağlantı bekleniyor';
    $('footer-status').textContent=e.message;
    $('live-label').innerHTML='<i></i> VERİ BEKLENİYOR';
    sceneView?.freshness(true);analyses?.stale();
    if(!lastPacketAt) $('sim-empty').textContent=e.message;
  } finally {setTimeout(poll,120);}
}


bind('fullscreen',async()=>{if(document.fullscreenElement)await document.exitFullscreen();else await document.documentElement.requestFullscreen();});
bind('pause',()=>control({op:'pause',paused:!paused}));
bind('reset',()=>control({op:'reset',goal:goal()}));
bind('apply-goal',async()=>{await control({op:'reset',goal:goal()});toast('Hedef güncellendi. Aynı modelle yeni bölüm başladı.');});
bind('orbit-left',()=>control({op:'camera',camera,orbit:-15}));bind('orbit-right',()=>control({op:'camera',camera,orbit:15}));
bind('zoom-in',()=>control({op:'camera',camera,zoom:-1}));bind('zoom-out',()=>control({op:'camera',camera,zoom:1}));
bind('sim-home',()=>control({op:'camera',camera,reset_view:true}));
// Coalesce high-frequency mouse / trackpad events. At most one HTTP command is in flight.
const gestures=new Map();let gestureTimer=null,gestureBusy=false;
function queueGesture(gesture,dx,dy){
  const key=camera+':'+gesture,prior=gestures.get(key)||{camera,gesture,dx:0,dy:0};
  prior.dx=Math.max(-1,Math.min(1,prior.dx+dx));prior.dy=Math.max(-1,Math.min(1,prior.dy+dy));gestures.set(key,prior);
  if(!gestureTimer&&!gestureBusy)gestureTimer=setTimeout(flushGestures,40);
}
async function flushGestures(){
  gestureTimer=null;if(gestureBusy||!gestures.size)return;
  const [key,g]=gestures.entries().next().value;gestures.delete(key);gestureBusy=true;
  try{await control({op:'camera',...g});}catch(e){gestures.clear();toast(e.message);}finally{gestureBusy=false;if(gestures.size)gestureTimer=setTimeout(flushGestures,40);}
}
const flyImage=$('fly-image');let flyDrag=null;
flyImage.addEventListener('contextmenu',e=>e.preventDefault());flyImage.addEventListener('dragstart',e=>e.preventDefault());
flyImage.addEventListener('pointerdown',e=>{if(e.button>2)return;e.preventDefault();flyImage.setPointerCapture(e.pointerId);flyDrag={id:e.pointerId,x:e.clientX,y:e.clientY,gesture:e.button===2||e.shiftKey||e.ctrlKey||e.metaKey?'pan':e.button===1?'zoom':'rotate'};flyImage.classList.add('dragging');});
flyImage.addEventListener('pointermove',e=>{if(!flyDrag||e.pointerId!==flyDrag.id)return;const h=Math.max(1,flyImage.clientHeight);queueGesture(flyDrag.gesture,(e.clientX-flyDrag.x)/h,(e.clientY-flyDrag.y)/h);flyDrag.x=e.clientX;flyDrag.y=e.clientY;});
function endDrag(e){if(flyDrag?.id===e.pointerId){flyDrag=null;flyImage.classList.remove('dragging');if(flyImage.hasPointerCapture(e.pointerId))flyImage.releasePointerCapture(e.pointerId);}}
flyImage.addEventListener('pointerup',endDrag);flyImage.addEventListener('pointercancel',endDrag);
flyImage.addEventListener('wheel',e=>{e.preventDefault();const units=e.deltaMode===1?16:e.deltaMode===2?flyImage.clientHeight:1;queueGesture('zoom',0,Math.max(-.15,Math.min(.15,e.deltaY*units*.001)));},{passive:false});
flyImage.addEventListener('dblclick',()=>control({op:'camera',camera,reset_view:true}).catch(e=>toast(e.message)));
document.querySelectorAll('[data-camera]').forEach(b=>b.addEventListener('click',async()=>{try{await control({op:'camera',camera:b.dataset.camera});camera=b.dataset.camera;document.querySelectorAll('[data-camera]').forEach(x=>x.classList.toggle('active',x===b));}catch(e){toast(e.message);}}));
$('model').addEventListener('change',async()=>{try{await control({op:'model',model:$('model').value});}catch(e){toast(e.message);$('model').value=simulation.model||'trained';}});
$('experiment').addEventListener('change',async()=>{
  const e=catalog.experiments?.find(x=>x.id===$('experiment').value);if(!e)return;
  $('experiment').disabled=true;
  try{await control({op:'behavior',behavior:e.id});lastSequence=-1;}
  catch(error){toast(error.message);$('experiment').value=behavior||'odor';}
  finally{$('experiment').disabled=false;}
});
bind('train',async()=>{const steps=integer('steps',200,10000),seed=integer('seed',0,1000000);$('train').disabled=true;await api('train',{steps,seed,task:$('experiment').value});$('load-new').classList.add('hidden');toast('Yeni eğitim başladı. Mevcut model korunuyor.');});
bind('cancel',()=>api('train/cancel',{}));
$('robot-sensor').addEventListener('change',async()=>{try{await control({op:'sensor',sensor:$('robot-sensor').value});}catch(e){toast(e.message);}});
document.querySelectorAll('[data-eye]').forEach(button=>button.addEventListener('click',()=>{
  eyeMode=button.dataset.eye;
  document.querySelectorAll('[data-eye]').forEach(b=>{b.classList.toggle('active',b===button);b.setAttribute('aria-pressed',String(b===button));});
  updateEyes(simulation);
}));
bind('eye-expand',()=>{const expanded=$('eye-preview').classList.toggle('expanded');$('eye-expand').setAttribute('aria-expanded',String(expanded));$('eye-expand').title=expanded?'Göz görüntüsünü küçült':'Göz görüntüsünü büyüt';$('eye-expand').setAttribute('aria-label',$('eye-expand').title);});
bind('robot-next',()=>control({op:'next'}));
bind('load-new',async()=>{if(latestRun){const m=catalog.models.find(m=>m.id===latestRun);if(m?.task&&m.task!==simulation.behavior)await control({op:'behavior',behavior:m.task});await control({op:'model',model:latestRun});$('model').value=latestRun;}});
function setMode(value){mode=value;$('brain-view').classList.toggle('delta-view',value==='delta');$('activity-mode').classList.toggle('active',value==='activity');$('delta-mode').classList.toggle('active',value==='delta');$('scale-title').textContent=value==='activity'?'MODEL AKTİVİTESİ':'BAĞLANTI ÇARPANI';$('scale-low').textContent=value==='activity'?'0':'0.22×';$('scale-high').textContent=value==='activity'?'1':'4.48×';sceneView?.update(simulation.activity);}
bind('activity-mode',()=>setMode('activity'));bind('delta-mode',()=>setMode('delta'));
bind('scope-open',()=>$('scope-dialog').showModal());bind('scope-close',()=>$('scope-dialog').close());
bind('validation-open',()=>{
  const e=isFlight()?selectedModel?.flight_evaluation:selectedModel?.walk_evaluation;if(!e)return;
  $('validation-criterion').textContent=e.criterion||simulation.task_contract?.success||'Kayıtlı görev başarı ölçütü';
  const controlNames={silenced:isRobot()?'Nöron aktivitesi sıfır':'Motor çıkışı kapalı',untrained:e.recovery_evaluation?'Önceki model · geliştirme':'Eğitim öncesi',frozen_core:'Sabit anatomik ağırlıklar',mlp:'MLP referansı',camera:'RGB-D kamera'};
  const rows=[[selectedModel.before?'Eğitim öncesi':'Seçili model',e],...Object.entries(e.controls||{}).map(([k,v])=>[controlNames[k]||k,v])];
  if(e.recovery_evaluation)rows.splice(1,0,['Küp düşürme · kamera',e.recovery_evaluation]);
  $('validation-rows').replaceChildren(...rows.map(([label,v])=>{const tr=document.createElement('tr');for(const value of [label,`${v.success_count} / ${v.episodes}`,v.falls??'—',v.unsafe_count??'—']){const td=document.createElement('td');td.textContent=value;tr.append(td);}return tr;}));
  const muted=e.controls?.silenced;
  $('validation-note').textContent=(e.recovery_evaluation&&e.acceptance_passed===false?'Toparlanma kabul eşiği henüz geçilmedi. ':'')+(muted?(e.success_count/e.episodes>muted.success_count/muted.episodes?'Bu koşullarda öğrenilmiş motor çıkışı başarıya katkı sağladı.':'Bu koşullarda ağ çıkışının başarı artışı gösterilemedi.'):'Bu kayıtta çıkış kapatma karşılaştırması yok.');
  $('validation-method').textContent=isRobot()?'Aynı başlangıç tohumları kullanılır. Susturma testinde dört katmandaki nöron yanıtları sıfırlanır; öğrenilmiş çıkış sabitleri, IK ve servolar korunur. Öğretmen değerlendirmede çalışmaz. Başarı temas fiziğinden ölçülür. Kamera testi sentetik RGB-D, eklem ve temas sensörleriyle yapılır; kutu hedefi kalibredir.':'Yeni sinek görevlerinde aynı altı ortam/tohum üç kez çalıştırılır. Çıkış kapatma, modelin motor okumasını sıfırlar; gövde ve hazır kontrolcü çalışmaya devam eder. Eğitim MSE’si ile fiziksel başarı ayrı ölçütlerdir.';
  if(e.recovery_evaluation)$('validation-method').textContent='Normal yerleştirme ve küp düşürme, eğitimden ayrı sahnelerde sınanır. Nöron susturma, normal testin ilk 8 tohumunu kullanır. Önceki model satırı ayrı geliştirme sahneleridir; oranlar doğrudan son testle eşleştirilmez. En çok 3 girişim; sahne sıfırlanmaz. Öğretici değerlendirmede çalışmaz. Kutu hedefi kalibredir.';
  $('validation-sha').textContent='Checkpoint: '+selectedModel.sha256;
  $('validation-dialog').showModal();
});
bind('validation-close',()=>$('validation-dialog').close());
bind('inspect-open',()=>selection&&inspector.show(selection,simulation.model||$('model').value));
function setPickMode(value){pickMode=value;$('pick-node').classList.toggle('active',value==='node');$('pick-edge').classList.toggle('active',value==='edge');}
bind('pick-node',()=>setPickMode('node'));bind('pick-edge',()=>setPickMode('edge'));
inspector=createInspector({api,onSelect:next=>selectEntity(next,false)});

// Optional browser tool contract uses the same validated endpoint as the visible controls.
if(document.modelContext?.registerTool){
  const lifecycle=new AbortController();
  for(const tool of [
    {name:'read_fly_lab_state',description:'Read the live model, telemetry and current training status.',inputSchema:{type:'object',properties:{},additionalProperties:false},annotations:{readOnlyHint:true},execute:async()=>{const d=await api('state');const {image,activity,...s}=d.simulation;return {simulation:s,job:d.job};}},
    {name:'set_fly_simulation_paused',description:'Pause or resume the live MuJoCo simulation.',inputSchema:{type:'object',properties:{paused:{type:'boolean'}},required:['paused'],additionalProperties:false},annotations:{readOnlyHint:false},execute:async input=>{if(typeof input?.paused!=='boolean')throw Error('paused must be boolean');return control({op:'pause',paused:input.paused});}}
  ]) Promise.resolve(document.modelContext.registerTool(tool,{signal:lifecycle.signal})).catch(()=>{});
  addEventListener('pagehide',()=>lifecycle.abort(),{once:true});
}

try {
  await refreshCatalog();
  poll();
} catch(e){toast(e.message);$('brain-hint').textContent='Beyin görünümü yüklenemedi: '+e.message;}
