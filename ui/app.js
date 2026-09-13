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
const isFlight=()=>simulation.behavior==='flight';

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
  $('node-activity').title=edge?'2 × kaynak yanıtı × mevcut ağırlık; hedefin tanh öncesi girdisine katkı':'Modelin 0–1 arası sürekli yanıtı';
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
  if (value.some(x=>!Number.isFinite(x)||x < -30||x > 30)) throw Error('Hedef -30 ile 30 mm arasında olmalı.');
  return value;
}
async function refreshCatalog() {
  catalog = await api('catalog');
  const current=$('model').value;
  $('model').replaceChildren(...catalog.models.map(m=>{const option=document.createElement('option');option.value=m.id;option.textContent=m.name;return option;}));
  if (catalog.models.some(m=>m.id===current)) $('model').value=current;
  behaviorUI(isFlight());
}
async function refreshModel(id) {
  const request=++modelRequest, result=await api('model/'+encodeURIComponent(id));
  if(request!==modelRequest)return;
  selectedModel=result;
  updateSelectionValue();
  const item=catalog.models?.find(m=>m.id===id);
  const t=selectedModel.training, e=isFlight()?selectedModel.flight_evaluation:selectedModel.walk_evaluation;
  $('benchmark').textContent=e ? `${e.success_count} / ${e.episodes}`:'—';
  $('model-loss').textContent=t ? fmt(t.after_mse,5):'—';
  $('checkpoint').textContent='CHECKPOINT '+selectedModel.sha256.slice(0,12);
  $('brain-model').textContent=item?.name ?? id;
  $('loss-value').textContent=t ? fmt(t.after_mse,5):'—';
  $('loss-change').textContent=t ? `${fmt((t.after_mse/t.before_mse-1)*100,1)}%`:'Başlangıç';
  $('loss-steps').textContent=t ? `${count(t.steps)} adım`:'Eğitim uygulanmadı';
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
  chart($('signal-chart'),[{values:h.map(x=>x[1]),color:'#62d8d0'},{values:h.map(x=>x[2]),color:'#eaa867'}]);
  const active=['training','evaluating','cancelling'].includes(job?.status);
  const samples=active ? job.history ?? [] : trainingHistory;
  chart($('loss-chart'),[{values:samples.map(p=>p[1]),color:'#62d8d0'}],{min:0,max:Math.max(.01,...samples.map(p=>p[1]))});
  if(active){
    $('loss-source').textContent='YENİ EĞİTİM';
    $('loss-value').textContent=fmt(job.loss,5);
    $('loss-change').textContent='';
    $('loss-steps').textContent=`${count(job.step||0)} / ${count(job.steps)} adım`;
    $('changed').textContent=job.status==='evaluating'?`${job.evaluated||0} / 6 fizik testi`:'Model eğitiliyor';
  } else $('loss-source').textContent='SEÇİLİ MODEL';
}
async function updateJob(job) {
  const busy=['training','evaluating','cancelling'].includes(job.status);
  $('train').disabled=busy || !['odor','flight'].includes($('experiment').value);
  $('cancel').classList.toggle('hidden',!busy);
  $('cancel').disabled=job.status==='cancelling';
  const labels={idle:'Yeni deney hazır',training:'Model eğitiliyor',evaluating:'Fizik testleri çalışıyor',complete:'Deney tamamlandı',failed:'Deney başarısız',cancelled:'Deney durduruldu',cancelling:'Durduruluyor'};
  $('job-state').textContent=labels[job.status]||'Yeni deney hazır';
  const percent=job.status==='complete'?100:job.status==='evaluating'?75+25*(job.evaluated||0)/6:busy?75*(job.step||0)/(job.steps||1):0;
  $('job-percent').textContent=`${Math.round(percent)}%`;
  $('job-progress').style.width=percent+'%';
  if(job.status==='training') $('job-note').textContent=`${count(job.step||0)} / ${count(job.steps)} adım · Canlı görünüm seçili modelle devam eder.`;
  else if(job.status==='evaluating') $('job-note').textContent=`Hedef ${job.evaluated||0} / 6 · ${job.success_count||0} başarılı. Yeni model henüz seçilmedi.`;
  else if(job.message&&!isFlight()) $('job-note').textContent=job.message;
  if(job.status==='complete'&&job.id!==completedJob){
    completedJob=latestRun=job.id;
    await refreshCatalog();
    $('load-new').classList.remove('hidden');
    toast('Eğitim ve fizik testleri tamamlandı. Yeni modeli seçerek karşılaştırabilirsin.');
    await refreshModel(simulation.model || $('model').value);
  }
  if(['cancelled','failed'].includes(job.status)&&job.id!==completedJob){completedJob=job.id;await refreshModel(simulation.model||'trained');}
}
function updateSimulation(s) {
  const switching=behavior!==s.behavior;
  if(s.goal_mm&&(!simulation.seq||switching)){$('goal-x').value=s.goal_mm[0];$('goal-y').value=s.goal_mm[1];}
  simulation=s; paused=!!s.paused; lastPacketAt=Date.now();
  if(switching){
    behavior=s.behavior;behaviorUI(isFlight());$('experiment').value=behavior;
  }
  camera=s.camera;document.querySelectorAll('[data-camera]').forEach(b=>b.classList.toggle('active',b.dataset.camera===camera));
  $('sim-empty').classList.add('hidden');
  $('fly-image').style.visibility='visible';
  $('fly-image').src='data:image/jpeg;base64,'+s.image;
  $('render-quality').textContent=s.render?`${s.render.width} × ${s.render.height} · ${s.render.msaa}× MSAA`:'GÖRÜNTÜ AKIŞI';
  $('distance').innerHTML=fmt(s.distance_mm)+'<small> mm</small>';
  $('speed').innerHTML=fmt(s.speed_mm_s,1)+'<small> mm/s</small>';
  $('sim-time').innerHTML=fmt(s.time_s)+'<small> s</small>';
  $('reward').textContent=fmt(s.reward,3);
  $('episode').textContent='BÖLÜM '+String(s.episode).padStart(3,'0');
  $('live-label').innerHTML=`<i></i> ${s.paused?'DURAKLATILDI':s.idle?'BOŞTA':'CANLI FİZİK'}`;
  $('pause').innerHTML=s.paused?'<span>▶</span> Devam et':'<span>Ⅱ</span> Duraklat';
  $('episode-stats').textContent=isFlight()?`Bu oturum: ${s.successes}/${s.completed} hedef · ${s.falls} uçuş sınırı`:`Bu oturum: ${s.successes}/${s.completed} hedef · ${s.falls} devrilme`;
  $('rtf').textContent=fmt(s.rtf,isFlight()?3:2)+' ×';
  $('rtf').title='Simülasyon süresi / gerçek süre';
  $('odor-left').textContent=fmt(s.odor[0],3);$('odor-right').textContent=fmt(s.odor[1],3);
  $('steering').textContent=fmt(isFlight()?s.yaw_rate_rad_s:s.steering,3);
  $('contacts').textContent=isFlight()?`Z ${fmt(s.altitude_mm,1)} mm · ${fmt(s.wing_hz,1)} Hz`:`Temas: ${s.contacts}`;
  s.layer_means.forEach((v,i)=>{$('layer-'+i).style.width=(v*100)+'%';$('layer-'+i).parentElement.title=`Ortalama aktivite: ${fmt(v,4)}`;});
  $('outcome').classList.toggle('hidden',s.outcome==='running');
  $('outcome').textContent={success:isFlight()?'Kokulu hedefe ulaşıldı':'Hedefe ulaşıldı',fallen:'Denge kaybı',timeout:'Süre doldu'}[s.outcome]||'';
  $('footer-status').textContent=isFlight()?'Fizik 0,05 ms · Kanat 0,2 ms · Beyin kararı 10 ms':`Fizik ${fmt(s.physics_dt*1000,1)} ms · Sensör / karar 10 ms · Canlı veri`;
  $('connection').classList.add('ready');$('connection').innerHTML='<i></i> Yerel bağlantı aktif';
  sceneView?.update(s.activity);
  sceneView?.freshness();
  analyses?.update(s);
  inspector?.tick(s.activity,s.model);
  updateSelectionValue();
  if(`${s.behavior}:${s.model}`!==lastModelId){lastModelId=`${s.behavior}:${s.model}`;$('model').value=s.model;refreshModel(s.model).catch(e=>toast(e.message));}
}
async function poll() {
  if(document.hidden){setTimeout(poll,1000);return;}
  try {
    const data=await api('state');
    if(data.simulation.starting){
      simulation={...data.simulation, activity:null};lastPacketAt=0;lastSequence=-1;
      behaviorUI(isFlight());$('experiment').value=simulation.behavior;
      $('fly-image').style.visibility='hidden';$('sim-empty').classList.remove('hidden');
      $('sim-empty').textContent=isFlight()?'FlyBody uçuş politikası hazırlanıyor…':'Koku simülasyonu sürdürülüyor…';
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
  if(!['odor','flight'].includes(e.id)){toast(e.detail);$('experiment').value=behavior||'odor';return;}
  $('experiment').disabled=true;
  try{await control({op:'behavior',behavior:e.id});lastSequence=-1;}
  catch(error){toast(error.message);$('experiment').value=behavior||'odor';}
  finally{$('experiment').disabled=false;}
});
bind('train',async()=>{if(!['odor','flight'].includes($('experiment').value))return;const steps=integer('steps',200,10000),seed=integer('seed',0,1000000);$('train').disabled=true;await api('train',{steps,seed,task:$('experiment').value});$('load-new').classList.add('hidden');toast('Yeni eğitim başladı. Mevcut model korunuyor.');});
bind('cancel',()=>api('train/cancel',{}));
bind('load-new',async()=>{if(latestRun){await control({op:'model',model:latestRun});$('model').value=latestRun;}});
function setMode(value){mode=value;$('brain-view').classList.toggle('delta-view',value==='delta');$('activity-mode').classList.toggle('active',value==='activity');$('delta-mode').classList.toggle('active',value==='delta');$('scale-title').textContent=value==='activity'?'MODEL AKTİVİTESİ':'BAĞLANTI ÇARPANI';$('scale-low').textContent=value==='activity'?'0':'0.22×';$('scale-high').textContent=value==='activity'?'1':'4.48×';sceneView?.update(simulation.activity);}
bind('activity-mode',()=>setMode('activity'));bind('delta-mode',()=>setMode('delta'));
bind('scope-open',()=>$('scope-dialog').showModal());bind('scope-close',()=>$('scope-dialog').close());
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
  graph=await api('graph');
  sceneView=createBrain(graph,{getState:()=>({simulation,selectedModel,selectedNode,selectedEdge,selection,mode,pickMode}),onSelect:selectEntity});
  analyses=createAnalyses(graph,{getSelection:()=>selection});
  await refreshModel(simulation.model || 'trained');
} catch(e){toast(e.message);$('brain-hint').textContent='Beyin görünümü yüklenemedi: '+e.message;}
