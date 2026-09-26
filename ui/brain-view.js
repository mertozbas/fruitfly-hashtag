import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { edgeSignal, modelMatches, displayEdgeIndices } from './neural-math.js';
const $ = id => document.getElementById(id);
const count = n => Number(n).toLocaleString('tr-TR');
export function createBrain(data, {getState, onSelect}) {
  const lifecycle=new AbortController();
  const listen=(target,event,handler)=>target.addEventListener(event,handler,{signal:lifecycle.signal});
  let atlas=[], focus='circuit', focusId=null, displayKey='', candidateEdges=[], visibleEdges=[];
  const nodeIds=new Set(data.nodes.map(n=>n.id));
  const brightnessInput=$('brain-brightness'), brightnessKey='neural-lab.brain-brightness';
  try {
    const saved=localStorage.getItem(brightnessKey);
    if(saved!==null&&saved.trim()!==''&&Number.isFinite(Number(saved)))brightnessInput.value=String(Math.max(0,Math.min(100,Number(saved))));
  } catch { /* Rendering remains available when browser storage is disabled. */ }
  const host=$('brain-canvas'), scene=new THREE.Scene();
  const renderer=new THREE.WebGLRenderer({alpha:true,antialias:true});
  renderer.setPixelRatio(Math.min(devicePixelRatio,2));host.appendChild(renderer.domElement);
  const cam=new THREE.PerspectiveCamera(35,1,.1,10000), group=new THREE.Group();scene.add(group);
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
  const drawnIndices=new Uint32Array(data.edges.length*2);
  edgeGeometry.setIndex(new THREE.BufferAttribute(drawnIndices,1));edgeGeometry.setDrawRange(0,0);
  const selectedGeometry=new THREE.BufferGeometry();selectedGeometry.setAttribute('position',new THREE.BufferAttribute(new Float32Array(6),3));
  const selectedLine=new THREE.LineSegments(selectedGeometry,new THREE.LineBasicMaterial({color:0xffd799,transparent:true,opacity:.95,depthWrite:false}));
  selectedLine.visible=false;selectedLine.renderOrder=2;group.add(selectedLine);
  function applyBrightness(){
    const level=Number(brightnessInput.value)/100;
    // Readable base strokes remain when activity emphasis is turned down.
    points.material.opacity=.7+.25*level;
    lines.material.opacity=(getState().mode==='delta'?.4:.23)+.15*level;
    for(const obj of atlas)obj.material.opacity=obj.userData.selected ? .95 : .045+(obj.userData.displayOpacity??.14)*level;
    $('brain-brightness-value').textContent=`${Math.round(level*100)}%`;
    brightnessInput.setAttribute('aria-valuetext',`%${Math.round(level*100)}`);
  }
  listen(brightnessInput,'input',()=>{
    update(getState().simulation.activity);
    try {localStorage.setItem(brightnessKey,brightnessInput.value);} catch { /* Optional preference. */ }
  });
  applyBrightness();
  const controls=new OrbitControls(cam,renderer.domElement);
  controls.enableDamping=true;controls.dampingFactor=.12;controls.rotateSpeed=.5;controls.panSpeed=.75;controls.zoomSpeed=.7;
  controls.screenSpacePanning=true;controls.minPolarAngle=.06;controls.maxPolarAngle=Math.PI-.06;
  controls.minDistance=70;controls.maxDistance=6000;
  controls.mouseButtons={LEFT:THREE.MOUSE.ROTATE,MIDDLE:THREE.MOUSE.DOLLY,RIGHT:THREE.MOUSE.PAN};
  function home(){
    const box=focus==='all'?new THREE.Box3().setFromBufferAttribute(meshGeometry.attributes.position):pointsGeometry.boundingBox;
    const target=box.getCenter(new THREE.Vector3()).sub(center), size=box.getSize(new THREE.Vector3());
    const d=Math.max(size.x/Math.max(cam.aspect,.5),size.z,size.y)*.6/Math.tan(THREE.MathUtils.degToRad(cam.fov/2));
    controls.enableDamping=false;controls.update();controls.target.copy(target);cam.position.copy(target).add(new THREE.Vector3(0,-d,-d*.12));controls.update();controls.enableDamping=true;
  }
  home();
  const resize=()=>{const w=host.clientWidth,h=host.clientHeight;if(!w||!h)return;renderer.setSize(w,h,false);cam.aspect=w/h;cam.updateProjectionMatrix();};const observer=new ResizeObserver(resize);observer.observe(host);resize();
  const ray=new THREE.Raycaster(), tooltip=$('brain-tooltip');
  function pick(event){
    const r=renderer.domElement.getBoundingClientRect();
    const unit=2*cam.position.distanceTo(controls.target)*Math.tan(THREE.MathUtils.degToRad(cam.fov/2))/r.height;
    ray.params.Points.threshold=unit*6;ray.params.Line.threshold=unit*4;
    ray.setFromCamera(new THREE.Vector2((event.clientX-r.left)/r.width*2-1,-(event.clientY-r.top)/r.height*2+1),cam);
    group.updateMatrixWorld(true);
    if(getState().pickMode==='node'){
      const hits=ray.intersectObject(points);
      let best=null,score=36;
      for(const h of hits){const n=data.nodes[h.index],p=new THREE.Vector3(...n.position).applyMatrix4(group.matrixWorld).project(cam);
        const d=((p.x+1)*r.width/2-(event.clientX-r.left))**2+((1-p.y)*r.height/2-(event.clientY-r.top))**2;
        if(d<score){score=d;best={kind:'node',id:n.id,node:n};}}
      if(best)return best;
      const skeletonHits=ray.intersectObjects(atlas.filter(o=>o.visible));
      if(skeletonHits.length){const n=skeletonHits[0].object.userData;return {kind:'node',id:n.id,node:n};}
    }
      if(lines.visible){
        const hits=ray.intersectObject(lines);
        for(const hit of hits){
          const index=visibleEdges[Math.floor(hit.index/2)],e=data.edges[index],k=index*6;
          if(e&&edgeColors[k]+edgeColors[k+1]+edgeColors[k+2]>0)return {kind:'edge',source:data.nodes[e.a].id,target:data.nodes[e.b].id,edgeIndex:index};
        }
      }
    return null;
  }
  let down=null, lastHover=0;
  listen(renderer.domElement,'pointerdown',e=>{down=e.button===0&&!e.shiftKey&&!e.ctrlKey&&!e.metaKey?[e.clientX,e.clientY]:null;tooltip.classList.add('hidden');});
  listen(renderer.domElement,'pointercancel',()=>{down=null;});
  listen(renderer.domElement,'pointerleave',()=>tooltip.classList.add('hidden'));
  listen(renderer.domElement,'pointermove',e=>{
    if(e.buttons){tooltip.classList.add('hidden');return;}
    if(performance.now()-lastHover<100)return;lastHover=performance.now();
    const hit=pick(e);renderer.domElement.style.cursor=hit?'pointer':'grab';
    tooltip.classList.toggle('hidden',!hit);if(!hit)return;
    const r=host.getBoundingClientRect();tooltip.style.left=Math.min(e.clientX-r.left+12,r.width-270)+'px';tooltip.style.top=Math.max(12,e.clientY-r.top-30)+'px';
    tooltip.textContent=hit.kind==='node'?`${hit.node.label} · ${hit.id}`:`${data.nodes[data.edges[hit.edgeIndex].a].label} → ${data.nodes[data.edges[hit.edgeIndex].b].label}`;
  });
  listen(renderer.domElement,'pointerup',e=>{
    const start=down;down=null;
    if(!start||Math.hypot(e.clientX-start[0],e.clientY-start[1])>4)return;
    const hit=pick(e);if(hit)onSelect(hit);
  });
  function update(activity) {
    const state=getState(), {mode,selectedModel,selectedNode,selectedEdge,simulation}=state;
    const ready=modelMatches(data,simulation,selectedModel);
    const color=new THREE.Color(), threshold=Number($('flow-floor').value), brightness=Number(brightnessInput.value)/100;
    const density=$('connection-density').value;
    if(state.selection?.kind==='node')focusId=nodeIds.has(state.selection.id)?state.selection.id:null;
    const key=JSON.stringify([density,mode,ready?selectedModel.sha256:null,focusId,selectedEdge]);
    if(key!==displayKey){
      candidateEdges=displayEdgeIndices(data,{density,mode,gains:ready?selectedModel.gains:[],focusId,selectedEdge});
      displayKey=key;
    }
    let activeNodes=0, activeEdges=0, changed=0;
    data.nodes.forEach((n,i)=>{
      const value=activity?.[n.index], v=Number.isFinite(value)?Math.max(0,Math.min(1,value)):0;
      if(v>.01)activeNodes++;
      if(mode==='delta')color.setRGB(.07,.15,.18);
      else responseColor(color,v,brightness);
      if(n===selectedNode||(selectedEdge>=0&&(i===data.edges[selectedEdge]?.a||i===data.edges[selectedEdge]?.b)))color.setRGB(1,1,1);
      color.toArray(colors,i*3);
    });
    data.edges.forEach((e,i)=>{
      const gain=ready?selectedModel.gains[i]:1;
      const delta=Math.abs(Math.log(gain));
      if(Math.abs(gain-1)>.01)changed++;
      const signal=ready?edgeSignal(data,e,activity,gain):0;
      if(signal>threshold)activeEdges++;
      // Fixed logarithmic scale, shared across frames and models: 0..1 input contribution.
      const v=mode==='delta'?Math.min(1,delta/1.5):Math.log1p(99*Math.min(1,signal))/Math.log(100);
      if(!ready)color.setRGB(.08,.13,.18);
      else if(mode==='activity'&&signal<=threshold)color.setRGB(.035,.06,.085);
      else if(mode==='delta'){
        const emphasis=v*(.4+.6*brightness);
        if(gain>1)color.setRGB(.18+.7*emphasis,.35+.2*emphasis,.16);else color.setRGB(.08,.3+.3*emphasis,.5+.35*emphasis);
      }else color.setRGB(.1+.3*v*brightness,.3+.4*v*brightness,.4+.38*v*brightness);
      if(i===selectedEdge)color.setRGB(1,.85,.4);
      color.toArray(edgeColors,i*6);color.toArray(edgeColors,i*6+3);
    });
    for(const obj of atlas){
      const index=obj.userData.index, v=Number.isInteger(index)?activity?.[index]:null;
      if(Number.isFinite(v)&&mode==='activity'){responseColor(obj.material.color,v,brightness);obj.material.opacity=.08+.35*v;}
      else {obj.material.color.setHex(0x567086);obj.material.opacity=.14;}
      obj.userData.selected=state.selection?.kind==='node'&&state.selection.id===obj.userData.id;
      if(obj.userData.selected){obj.material.color.setHex(0xffffff);obj.material.opacity=.95;}
      obj.userData.displayOpacity=obj.material.opacity;
    }
    let drawn=0;
    for(const index of candidateEdges){
      const e=data.edges[index];
      if(index!==selectedEdge&&mode==='activity'&&threshold>0&&(!ready||edgeSignal(data,e,activity,selectedModel.gains[index])<=threshold))continue;
      drawnIndices[drawn++]=index*2;drawnIndices[drawn++]=index*2+1;
    }
    // Raycaster reports index-buffer offsets, not source vertex ids.
    visibleEdges=Array.from(drawnIndices.subarray(0,drawn)).filter((_,i)=>i%2===0).map(i=>i/2);
    edgeGeometry.index.needsUpdate=true;edgeGeometry.setDrawRange(0,drawn);
    selectedLine.visible=$('edges').checked&&selectedEdge>=0;
    if(selectedLine.visible){
      selectedGeometry.attributes.position.array.set(edgeGeometry.attributes.position.array.subarray(selectedEdge*6,selectedEdge*6+6));
      selectedGeometry.attributes.position.needsUpdate=true;selectedGeometry.computeBoundingSphere();
    }
    pointsGeometry.attributes.color.needsUpdate=true;edgeGeometry.attributes.color.needsUpdate=true;
    applyBrightness();
    $('flow-value').textContent=threshold.toFixed(3);
    const context=density==='neuron'?(focusId?`Body ${focusId} giriş / çıkışları`:'Bağları görmek için bir soma seç'):mode==='delta'&&density==='overview'?'En çok değişen bağlar':density==='overview'?'Sade anatomik görünüm':'Tüm konumlu bağlar';
    $('brain-hint').textContent=`${context} · ${count(drawn/2)} / ${count(data.edges.length)} çizgi`;
    $('brain-hint').title=ready?(mode==='delta'?`${count(changed)} bağda >%1 değişim. Yeni anatomik bağ: 0.`:`${count(activeNodes)} nöron yanıtı >0,01; tüm havuzda ${count(activeEdges)} bağ sinyal eşiği üstünde.`):'Model ve canlı veri eşleştiriliyor…';
  }
  function freshness(stale=false){
    const {simulation:s,selectedModel:m}=getState(), ok=modelMatches(data,s,m);
    if(s.physical){
      $('brain-live').textContent=(stale?'AKIŞ KESİLDİ':!ok?'MODEL EŞLEŞTİRİLİYOR':s.neural?.decision_applied?'FİZİKSEL MOTOR HESABI':'CANLI BEYİN · HAREKET BEKLİYOR')+` · #${s.seq}`;
      $('brain-live').classList.toggle('stale',stale||!ok);
      return;
    }
    $('brain-live').textContent=stale?'AKIŞ KESİLDİ · SON KARE':!ok?'MODEL EŞLEŞTİRİLİYOR':`${s.behavior==='tictactoe'?(s.neural?.displayed_pass==='motor'?'MOTOR HESABI':s.game?.waiting_for_human?'TAHTA ANALİZİ · SENİN SIRAN':s.neural?.decision_applied?'HAMLE KARARI':'SON KARAR'):s.neural?.decision_applied===false?'BAŞLANGIÇ · HENÜZ MOTOR ADIMI YOK':s.paused?'DURAKLATILDI':s.idle?'BOŞTA':'CANLI HESAP'} · ${Number(s.neural?.sample_time_s??s.time_s).toFixed(2)} s · #${s.seq}`;
    $('brain-live').classList.toggle('stale',stale||!ok||s.paused||s.idle);
  }
  async function loadAtlas(){
    try{
      const [meta,buffer]=await Promise.all([fetch('/api/anatomy').then(r=>{if(!r.ok)throw Error(r.status);return r.json();}),fetch('/api/anatomy/segments').then(r=>{if(!r.ok)throw Error(r.status);return r.arrayBuffer();})]);
      if(lifecycle.signal.aborted)return;
      const values=new Float32Array(buffer);
      if(values.length!==meta.segments*6)throw Error('Anatomi boyutu eşleşmiyor');
      for(const record of meta.skeletons){
        const g=new THREE.BufferGeometry();g.setAttribute('position',new THREE.BufferAttribute(values.subarray(record.start*6,(record.start+record.count)*6),3));
        const obj=new THREE.LineSegments(g,new THREE.LineBasicMaterial({color:0x567086,transparent:true,opacity:.14,depthWrite:false}));
        record.index=data.model_index?.[record.id]??null;
        obj.userData=record;obj.visible=$('anatomy').checked;atlas.push(obj);group.add(obj);
      }
      $('atlas-status').textContent=`${meta.skeletons.length} gerçek SWC · Gri: model dışında`;
      update(getState().simulation.activity);
    }catch(e){$('atlas-status').textContent='Anatomi yüklenemedi: '+e.message;}
  }
  let lastDraw=0;
  function animate(now){if(lifecycle.signal.aborted)return;requestAnimationFrame(animate);if(document.hidden||now-lastDraw<30)return;controls.update();renderer.render(scene,cam);lastDraw=now;}requestAnimationFrame(animate);
  listen($('brain-home'),'click',home);
  listen($('edges'),'change',()=>{lines.visible=$('edges').checked;selectedLine.visible=$('edges').checked&&getState().selectedEdge>=0;});
  $('located').textContent=`${count(data.nodes.length)} / ${count(data.total)} soma konumu`;
  listen($('anatomy'),'change',()=>{atlas.forEach(o=>o.visible=$('anatomy').checked);});
  document.querySelectorAll('[data-brain-focus]').forEach(b=>listen(b,'click',()=>{focus=b.dataset.brainFocus;document.querySelectorAll('[data-brain-focus]').forEach(x=>x.classList.toggle('active',x===b));home();}));
  listen($('flow-floor'),'input',()=>update(getState().simulation.activity));
  listen($('connection-density'),'change',()=>update(getState().simulation.activity));
  loadAtlas();
  return {update,freshness,dispose(){lifecycle.abort();observer.disconnect();controls.dispose();scene.traverse(o=>{o.geometry?.dispose();o.material?.dispose();});renderer.dispose();renderer.domElement.remove();},neuron:id=>atlas.find(o=>o.userData.id===id)?.userData};
}

function responseColor(color,v,brightness){
  v=Math.max(0,Math.min(1,v));
  color.setRGB(.04+.78*v*brightness,.12+.6*v*brightness,.18+.43*v*brightness);
}
