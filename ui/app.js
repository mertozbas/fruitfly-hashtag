import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { createInspector } from './inspector.js';

const $ = id => document.getElementById(id);
const fmt = (n, digits=2) => Number.isFinite(n) ? n.toFixed(digits) : '—';
const count = n => Number(n).toLocaleString('tr-TR');
let simulation = {}, catalog = {}, selectedModel = null, graph = null, sceneView = null;
let lastSequence = -1, lastModelId = null, selectedNode = null, mode = 'activity', camera = 'body', latestRun = null;
let completedJob = null, paused = false, trainingHistory = [], lastPacketAt = 0;
let toastTimer;
let inspector=null, selection=null, selectedEdge=-1, pickMode='node';

function selectEntity(next, open=true) {
  selection=next;
  selectedNode=next.kind==='node'?graph?.nodes.find(n=>n.id===next.id):null;
  selectedEdge=next.kind==='edge'?graph?.edges.findIndex(e=>graph.nodes[e.a].id===next.source&&graph.nodes[e.b].id===next.target):-1;
  $('inspect-open').classList.remove('hidden');
  if(next.kind==='node'){
    $('node-type').textContent=selectedNode?.group||'NÖRON';
    $('node-title').textContent=selectedNode?.label||next.id;
    $('node-description').textContent=selectedNode?'Soma: '+selectedNode.position.map(x=>fmt(x,1)).join(' / ')+' µm':'Yerel anatomik kayıt';
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
  sceneView?.update(simulation.activity);
  if(open)inspector?.show(next,simulation.model||$('model').value);
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
}
async function refreshModel(id) {
  selectedModel=await api('model/'+encodeURIComponent(id));
  const item=catalog.models?.find(m=>m.id===id);
  const t=selectedModel.training, e=selectedModel.evaluation;
  $('benchmark').textContent=e ? `${e.success_count} / ${e.episodes}`:'—';
  $('model-loss').textContent=t ? fmt(t.after_mse,5):'—';
  $('checkpoint').textContent='CHECKPOINT '+selectedModel.sha256.slice(0,12);
  $('brain-model').textContent=item?.name ?? id;
  $('loss-value').textContent=t ? fmt(t.after_mse,5):'—';
  $('loss-change').textContent=t ? `${fmt((t.after_mse/t.before_mse-1)*100,1)}%`:'Başlangıç';
  $('loss-steps').textContent=t ? `${count(t.steps)} adım`:'Eğitim uygulanmadı';
  $('changed').textContent=t ? `${count(t.changed_existing_synaptic_gains)} bağlantı değişti`:'Ağırlıklar başlangıç halinde';
  trainingHistory=t?.history?.map(p=>[p.step,p.validation_mse]) ?? [];
  if(sceneView) sceneView.update(simulation.activity);
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
  $('train').disabled=busy || $('experiment').value!=='odor';
  $('cancel').classList.toggle('hidden',!busy);
  $('cancel').disabled=job.status==='cancelling';
  const labels={idle:'Yeni deney hazır',training:'Model eğitiliyor',evaluating:'Fizik testleri çalışıyor',complete:'Deney tamamlandı',failed:'Deney başarısız',cancelled:'Deney durduruldu',cancelling:'Durduruluyor'};
  $('job-state').textContent=labels[job.status]||'Yeni deney hazır';
  const percent=job.status==='complete'?100:job.status==='evaluating'?75+25*(job.evaluated||0)/6:busy?75*(job.step||0)/(job.steps||1):0;
  $('job-percent').textContent=`${Math.round(percent)}%`;
  $('job-progress').style.width=percent+'%';
  if(job.status==='training') $('job-note').textContent=`${count(job.step||0)} / ${count(job.steps)} adım · Canlı görünüm seçili modelle devam eder.`;
  else if(job.status==='evaluating') $('job-note').textContent=`Hedef ${job.evaluated||0} / 6 · ${job.success_count||0} başarılı. Yeni model henüz seçilmedi.`;
  else if(job.message) $('job-note').textContent=job.message;
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
  simulation=s; paused=!!s.paused; lastPacketAt=Date.now();
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
  $('episode-stats').textContent=`Bu oturum: ${s.successes}/${s.completed} hedef · ${s.falls} devrilme`;
  $('rtf').textContent=fmt(s.rtf,2)+' ×';
  $('rtf').title='Simülasyon süresi / gerçek süre';
  $('odor-left').textContent=fmt(s.odor[0],3);$('odor-right').textContent=fmt(s.odor[1],3);
  $('steering').textContent=fmt(s.steering,3);
  $('contacts').textContent=`Temas: ${s.contacts}`;
  s.layer_means.forEach((v,i)=>{$('layer-'+i).style.width=(v*100)+'%';$('layer-'+i).parentElement.title=`Ortalama aktivite: ${fmt(v,4)}`;});
  $('outcome').classList.toggle('hidden',s.outcome==='running');
  $('outcome').textContent={success:'Hedefe ulaşıldı',fallen:'Denge kaybı',timeout:'Süre doldu'}[s.outcome]||'';
  $('footer-status').textContent=`Fizik ${fmt(s.physics_dt*1000,1)} ms · Sensör / karar 10 ms · Canlı veri`;
  $('connection').classList.add('ready');$('connection').innerHTML='<i></i> Yerel bağlantı aktif';
  sceneView?.update(s.activity);
  inspector?.tick(s.activity);
  if(selectedNode) $('node-activity').textContent=fmt(s.activity[selectedNode.index],4);
  if(s.model!==lastModelId){lastModelId=s.model;$('model').value=s.model;refreshModel(s.model).catch(e=>toast(e.message));}
}
async function poll() {
  if(document.hidden){setTimeout(poll,1000);return;}
  try {
    const data=await api('state');
    await updateJob(data.job);
    if(data.simulation.error) throw Error(data.simulation.error);
    if(!data.alive) throw Error('Simülasyon işlemi durdu. Sunucu kaydını kontrol et.');
    if(data.simulation.seq&&data.simulation.seq!==lastSequence){lastSequence=data.simulation.seq;updateSimulation(data.simulation);}
    updateCharts(data.job);
    if(lastPacketAt&&Date.now()-lastPacketAt>5000) throw Error('Canlı görüntü gecikti; son veri gösteriliyor.');
  } catch(e) {
    $('connection').classList.remove('ready');$('connection').innerHTML='<i></i> Bağlantı bekleniyor';
    $('footer-status').textContent=e.message;
    $('live-label').innerHTML='<i></i> VERİ BEKLENİYOR';
    if(!lastPacketAt) $('sim-empty').textContent=e.message;
  } finally {setTimeout(poll,120);}
}

function createBrain(data) {
  const host=$('brain-canvas'), scene=new THREE.Scene();
  const renderer=new THREE.WebGLRenderer({alpha:true,antialias:true});
  renderer.setPixelRatio(Math.min(devicePixelRatio,2));host.appendChild(renderer.domElement);
  const cam=new THREE.PerspectiveCamera(35,1,.1,5000), group=new THREE.Group();scene.add(group);
  // OrbitControls caches the up-vector transform in its constructor.
  cam.up.set(0,0,-1);
  const positions=data.nodes.flatMap(n=>n.position);
  const pointsGeometry=new THREE.BufferGeometry();pointsGeometry.setAttribute('position',new THREE.Float32BufferAttribute(positions,3));
  const colors=new Float32Array(positions.length);colors.fill(.3);pointsGeometry.setAttribute('color',new THREE.BufferAttribute(colors,3));
  pointsGeometry.computeBoundingBox();
  const center=pointsGeometry.boundingBox.getCenter(new THREE.Vector3());
  group.position.copy(center).negate();
  const points=new THREE.Points(pointsGeometry,new THREE.PointsMaterial({size:2.2,vertexColors:true,transparent:true,opacity:.95,sizeAttenuation:true,depthWrite:false}));group.add(points);
  const meshGeometry=new THREE.BufferGeometry();meshGeometry.setAttribute('position',new THREE.Float32BufferAttribute(data.vertices,3));meshGeometry.setIndex(data.faces);meshGeometry.computeVertexNormals();
  const surface=new THREE.Mesh(meshGeometry,new THREE.MeshPhongMaterial({color:0x375e78,transparent:true,opacity:.09,side:THREE.DoubleSide,depthWrite:false,shininess:25}));group.add(surface);
  scene.add(new THREE.AmbientLight(0x98cfe7,2));
  const light=new THREE.DirectionalLight(0x9ad0e9,3);light.position.set(200,-200,600);scene.add(light);
  const edgePositions=data.edges.flatMap(e=>[...data.nodes[e.a].position,...data.nodes[e.b].position]);
  const edgeGeometry=new THREE.BufferGeometry();edgeGeometry.setAttribute('position',new THREE.Float32BufferAttribute(edgePositions,3));
  const edgeColors=new Float32Array(edgePositions.length);edgeColors.fill(.25);edgeGeometry.setAttribute('color',new THREE.BufferAttribute(edgeColors,3));
  const lines=new THREE.LineSegments(edgeGeometry,new THREE.LineBasicMaterial({vertexColors:true,transparent:true,opacity:.23,depthWrite:false}));group.add(lines);
  const extent=pointsGeometry.boundingBox.getSize(new THREE.Vector3());
  const distance=Math.max(extent.x,extent.y,extent.z)*1.65;
  const controls=new OrbitControls(cam,renderer.domElement);
  controls.enableDamping=true;controls.dampingFactor=.12;controls.rotateSpeed=.5;controls.panSpeed=.75;controls.zoomSpeed=.7;
  controls.screenSpacePanning=true;controls.minPolarAngle=.06;controls.maxPolarAngle=Math.PI-.06;
  controls.minDistance=70;controls.maxDistance=2200;
  controls.mouseButtons={LEFT:THREE.MOUSE.ROTATE,MIDDLE:THREE.MOUSE.DOLLY,RIGHT:THREE.MOUSE.PAN};
  function home(){controls.enableDamping=false;controls.update();cam.position.set(0,-distance,-distance*.12);controls.target.set(0,0,0);controls.update();controls.enableDamping=true;}
  home();
  const resize=()=>{const w=host.clientWidth,h=host.clientHeight;if(!w||!h)return;renderer.setSize(w,h,false);cam.aspect=w/h;cam.updateProjectionMatrix();};new ResizeObserver(resize).observe(host);resize();
  const ray=new THREE.Raycaster(), tooltip=$('brain-tooltip');
  function pick(event){
    const r=renderer.domElement.getBoundingClientRect();
    const unit=2*cam.position.distanceTo(controls.target)*Math.tan(THREE.MathUtils.degToRad(cam.fov/2))/r.height;
    ray.params.Points.threshold=unit*6;ray.params.Line.threshold=unit*4;
    ray.setFromCamera(new THREE.Vector2((event.clientX-r.left)/r.width*2-1,-(event.clientY-r.top)/r.height*2+1),cam);
    group.updateMatrixWorld(true);
    if(pickMode==='node'){
      const hits=ray.intersectObject(points);
      let best=null,score=36;
      for(const h of hits){const n=data.nodes[h.index],p=new THREE.Vector3(...n.position).applyMatrix4(group.matrixWorld).project(cam);
        const d=((p.x+1)*r.width/2-(event.clientX-r.left))**2+((1-p.y)*r.height/2-(event.clientY-r.top))**2;
        if(d<score){score=d;best={kind:'node',id:n.id,node:n};}}
      if(best)return best;
    }
    if(lines.visible){const hits=ray.intersectObject(lines);if(hits.length){const index=Math.floor(hits[0].index/2),e=data.edges[index];if(e)return {kind:'edge',source:data.nodes[e.a].id,target:data.nodes[e.b].id,edgeIndex:index};}}
    return null;
  }
  let down=null;
  renderer.domElement.addEventListener('pointerdown',e=>{down=e.button===0&&!e.shiftKey&&!e.ctrlKey&&!e.metaKey?[e.clientX,e.clientY]:null;tooltip.classList.add('hidden');});
  renderer.domElement.addEventListener('pointercancel',()=>{down=null;});
  renderer.domElement.addEventListener('pointerleave',()=>tooltip.classList.add('hidden'));
  renderer.domElement.addEventListener('pointermove',e=>{
    if(e.buttons){tooltip.classList.add('hidden');return;}
    const hit=pick(e);renderer.domElement.style.cursor=hit?'pointer':'grab';
    tooltip.classList.toggle('hidden',!hit);if(!hit)return;
    const r=host.getBoundingClientRect();tooltip.style.left=Math.min(e.clientX-r.left+12,r.width-270)+'px';tooltip.style.top=Math.max(12,e.clientY-r.top-30)+'px';
    tooltip.textContent=hit.kind==='node'?`${hit.node.label} · ${hit.id}`:`${data.nodes[data.edges[hit.edgeIndex].a].label} → ${data.nodes[data.edges[hit.edgeIndex].b].label}`;
  });
  renderer.domElement.addEventListener('pointerup',e=>{
    const start=down;down=null;
    if(!start||Math.hypot(e.clientX-start[0],e.clientY-start[1])>4)return;
    const hit=pick(e);if(hit)selectEntity(hit);
  });
  function update(activity) {
    if(!activity)return;
    const color=new THREE.Color();
    data.nodes.forEach((n,i)=>{const v=activity[n.index]||0;
      if(mode==='delta') color.setRGB(.2,.42,.52);
      else {color.setRGB(.08+.78*v,.24+.6*v,.35+.43*v);if(n.group==='MBON')color.setRGB(.55+.45*v,.3+.4*v,.13+.3*v);}
      if(n===selectedNode||(selectedEdge>=0&&(i===data.edges[selectedEdge]?.a||i===data.edges[selectedEdge]?.b)))color.setRGB(1,1,1);
      color.toArray(colors,i*3);
    });
    data.edges.forEach((e,i)=>{
      const gain=selectedModel?.gains[i]??1;
      if(mode==='delta'){
        const v=Math.min(1,Math.abs(Math.log(gain))/1.5);
        if(gain>1)color.setRGB(.35+.6*v,.4+.25*v,.2);else color.setRGB(.12,.35+.4*v,.55+.35*v);
      } else {const v=activity[data.nodes[e.b].index]||0;color.setRGB(.1+.3*v,.3+.4*v,.4+.38*v);}
      if(i===selectedEdge)color.setRGB(1,.9,.5);
      color.toArray(edgeColors,i*6);color.toArray(edgeColors,i*6+3);
    });
    pointsGeometry.attributes.color.needsUpdate=true;edgeGeometry.attributes.color.needsUpdate=true;
    lines.material.opacity=mode==='delta'?.65:.23;
  }
  let lastDraw=0;
  function animate(now){requestAnimationFrame(animate);if(document.hidden||now-lastDraw<30)return;controls.update();renderer.render(scene,cam);lastDraw=now;}requestAnimationFrame(animate);
  $('brain-home').addEventListener('click',home);
  $('edges').addEventListener('change',()=>{lines.visible=$('edges').checked;});
  $('located').textContent=`${count(data.nodes.length)} / ${count(data.total)} soma konumu`;
  $('brain-hint').textContent=`µm · ${count(data.edges.length)} bağlantı çiziliyor · konumsuz nöronlar gizli`;
  return {update};
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
$('experiment').addEventListener('change',()=>{const e=catalog.experiments?.find(x=>x.id===$('experiment').value);if(!e)return;$('experiment-note').textContent=e.id==='odor'?'Doğrulanmış görev · taklit öğrenmesi':e.detail;$('train').disabled=e.id!=='odor';if(e.id!=='odor')toast(e.detail+' Canlı görünüm koku deneyiyle devam ediyor.');});
bind('train',async()=>{if($('experiment').value!=='odor')return;const steps=integer('steps',200,10000),seed=integer('seed',0,1000000);$('train').disabled=true;await api('train',{steps,seed});$('load-new').classList.add('hidden');toast('Yeni eğitim başladı. Mevcut model korunuyor.');});
bind('cancel',()=>api('train/cancel',{}));
bind('load-new',async()=>{if(latestRun){await control({op:'model',model:latestRun});$('model').value=latestRun;}});
function setMode(value){mode=value;$('activity-mode').classList.toggle('active',value==='activity');$('delta-mode').classList.toggle('active',value==='delta');$('scale-title').textContent=value==='activity'?'MODEL AKTİVİTESİ':'BAĞLANTI ÇARPANI';$('scale-low').textContent=value==='activity'?'0':'0.22×';$('scale-high').textContent=value==='activity'?'1':'4.48×';sceneView?.update(simulation.activity);}
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
  sceneView=createBrain(graph);
  await refreshModel(simulation.model || 'trained');
} catch(e){toast(e.message);$('brain-hint').textContent='Beyin görünümü yüklenemedi: '+e.message;}
