import {groupActivity, activityGrid} from './neural-math.js';
const $=id=>document.getElementById(id);
const names={ORN:'ORN',ALPN:'ALPN',Kenyon_Cell:'Kenyon',MBON:'MBON'};
const count=n=>Number(n).toLocaleString('tr-TR');
export function createAnalyses(graph,{getSelection}){
  let current={}, visible=false, disconnected=false;
  const nodes=graph.nodes, byId=new Map(nodes.map(n=>[n.id,n]));
  const bounds=extents(nodes.map(n=>n.position));
  const surface=[];for(let i=0;i<graph.vertices.length;i+=3)surface.push(graph.vertices.slice(i,i+3));
  const allBounds=extents(surface);
  const rows=graph.group_ranges.map(g=>{
    const row=document.createElement('div');row.className='region-row';
    const name=document.createElement('span');name.textContent=names[g.name]||g.name;
    const bar=document.createElement('i'),fill=document.createElement('b'),value=document.createElement('span');
    bar.append(fill);row.append(name,bar,value);$('region-values').append(row);return {row,fill,value};
  });
  function tab(active){
    visible=active;
    for(const id of ['metrics','analyses']){
      const selected=(id==='analyses')===active,b=$(`${id}-tab`);
      b.classList.toggle('active',selected);b.setAttribute('aria-selected',String(selected));b.tabIndex=selected?0:-1;
      $(`${id}-view`).classList.toggle('hidden',!selected);
    }
    draw();
  }
  $('metrics-tab').addEventListener('click',()=>tab(false));$('analyses-tab').addEventListener('click',()=>tab(true));
  for(const id of ['metrics-tab','analyses-tab'])$(id).addEventListener('keydown',e=>{
    if(['ArrowLeft','ArrowRight','Home','End'].includes(e.key)){e.preventDefault();tab(e.key==='Home'?false:e.key==='End'?true:!visible);$(visible?'analyses-tab':'metrics-tab').focus();}
  });
  $('slice-depth').addEventListener('input',draw);$('slice-width').addEventListener('change',draw);
  new ResizeObserver(()=>{if(visible)draw();}).observe($('analyses-view'));
  function update(s){current=s;disconnected=false;status();if(visible)draw();}
  function status(){
    $('analysis-frame').textContent=disconnected?'AKIŞ KESİLDİ · SON KARE':current.seq?`${current.paused?'DURAKLATILDI':current.idle?'BOŞTA':'CANLI'} · #${current.seq} · ${Number(current.time_s).toFixed(2)} s`:'CANLI VERİ BEKLENİYOR';
  }
  function draw(){
    if(!visible||!current.activity)return;
    const selected=getSelection(),selectedNode=selected?.kind==='node'?byId.get(selected.id):selected?.kind==='edge'?byId.get(selected.target):null;
    const activity=current.activity;
    groupActivity(graph,activity).forEach((g,i)=>{
      rows[i].fill.style.width=(g.mean*100)+'%';rows[i].value.textContent=g.mean.toFixed(3);
      rows[i].row.title=`${count(g.count)} model nöronu · ${count(g.located)} soma konumu · ${count(g.active)} yanıt >0,01. Ortalama tüm gruptan hesaplanır.`;
    });
    $('region-name').textContent=selectedNode?.region||'KOKU DEVRESİ';
    $('region-selection').textContent=selectedNode?`${selectedNode.label} · ${selectedNode.region||'Bölge anotasyonu yok'}`:selected?.id?`Body ${selected.id} · konumlu devre dışında`:'Çerçeve: konumlu koku devresi';
    $('region-selection').title=$('region-selection').textContent;
    const drive=current.neural?.cpg_drive;
    $('motor-drive').textContent=drive?`CPG ${drive[0].toFixed(2)} / ${drive[1].toFixed(2)}`:'CPG henüz sürülmedi';
    const region=setup($('region-map'),allBounds);
    if(region){
      background(region,surface,allBounds);
      region.c.strokeStyle='#66c8c9';region.c.lineWidth=.8;
      const a=region.point([bounds.minX,0,bounds.minZ]),b=region.point([bounds.maxX,0,bounds.maxZ]);
      region.c.fillStyle='#54c0c418';region.c.fillRect(a[0],a[1],b[0]-a[0],b[1]-a[1]);region.c.strokeRect(a[0],a[1],b[0]-a[0],b[1]-a[1]);
      if(selectedNode){const p=region.point(selectedNode.position);region.c.fillStyle='#ffda95';region.c.beginPath();region.c.arc(...p,3,0,Math.PI*2);region.c.fill();}
    }
    const heat=setup($('heat-map'),bounds);
    if(heat){
      const grid=activityGrid(nodes,activity,bounds), {c}=heat;
      for(let z=0;z<grid.height;z++)for(let x=0;x<grid.width;x++){
        const i=z*grid.width+x;if(!grid.counts[i])continue;
        const value=grid.sums[i]/grid.counts[i],p=heat.point([bounds.minX+x*(bounds.maxX-bounds.minX)/grid.width,0,bounds.minZ+z*(bounds.maxZ-bounds.minZ)/grid.height]);
        c.fillStyle=heatColor(value);c.fillRect(p[0],p[1],heat.scale*(bounds.maxX-bounds.minX)/grid.width+.2,heat.scale*(bounds.maxZ-bounds.minZ)/grid.height+.2);
      }
      axes(heat,'X → · Z ↓ · µm');
    }
    const xray=setup($('xray-map'),bounds);
    const y=bounds.minY+(bounds.maxY-bounds.minY)*Number($('slice-depth').value)/100;
    const thickness=$('slice-width').value==='all'?Infinity:Number($('slice-width').value);
    $('slice-depth').disabled=!Number.isFinite(thickness);
    $('slice-value').textContent=Number.isFinite(thickness)?`${y.toFixed(0)} µm`:'tümü';
    if(xray){
      background(xray,surface,bounds);
      const {c}=xray;let inside=0;
      for(const n of nodes){
        const value=activity[n.index]??0,inSlice=Math.abs(n.position[1]-y)<=thickness/2;
        const p=xray.point(n.position);c.fillStyle=inSlice?heatColor(value):'#416078';c.globalAlpha=inSlice?.16+.72*value:.025;
        c.beginPath();c.arc(...p,inSlice?1.1:.5,0,Math.PI*2);c.fill();if(inSlice)inside++;
      }
      c.globalAlpha=1;axes(xray,`${count(inside)} soma · X/Z`);
      if(selectedNode&&Math.abs(selectedNode.position[1]-y)<=thickness/2){const p=xray.point(selectedNode.position);c.strokeStyle='#fff1ce';c.beginPath();c.arc(...p,3,0,Math.PI*2);c.stroke();}
    }
  }
  return {update,stale(){disconnected=true;status();}};
}
function extents(points){
  const b={minX:Infinity,maxX:-Infinity,minY:Infinity,maxY:-Infinity,minZ:Infinity,maxZ:-Infinity};
  for(const [x,y,z] of points){b.minX=Math.min(b.minX,x);b.maxX=Math.max(b.maxX,x);b.minY=Math.min(b.minY,y);b.maxY=Math.max(b.maxY,y);b.minZ=Math.min(b.minZ,z);b.maxZ=Math.max(b.maxZ,z);}return b;
}
function setup(canvas,bounds){
  const rect=canvas.getBoundingClientRect(),w=rect.width,h=rect.height;
  if(w<1||h<1)return null;
  const dpr=Math.min(devicePixelRatio||1,2);
  if(canvas.width!==Math.round(w*dpr)||canvas.height!==Math.round(h*dpr)){canvas.width=Math.round(w*dpr);canvas.height=Math.round(h*dpr);}
  const c=canvas.getContext('2d');c.setTransform(dpr,0,0,dpr,0,0);c.clearRect(0,0,w,h);
  const scale=Math.max(.001,Math.min((w-18)/(bounds.maxX-bounds.minX),(h-14)/(bounds.maxZ-bounds.minZ)));
  const dx=(w-(bounds.maxX-bounds.minX)*scale)/2,dz=(h-(bounds.maxZ-bounds.minZ)*scale)/2;
  return {c,w,h,scale,point:p=>[dx+(p[0]-bounds.minX)*scale,dz+(p[2]-bounds.minZ)*scale]};
}
function background(view,vertices,bounds){
  const {c}=view;c.fillStyle='#48677c';c.globalAlpha=.15;
  for(let i=0;i<vertices.length;i+=4){const p=vertices[i];if(p[0]<bounds.minX||p[0]>bounds.maxX||p[2]<bounds.minZ||p[2]>bounds.maxZ)continue;const xy=view.point(p);c.fillRect(xy[0],xy[1],.7,.7);}
  c.globalAlpha=1;
}
function heatColor(value){const v=Math.max(0,Math.min(1,value));return `rgb(${Math.round(13+230*v*v)} ${Math.round(31+181*v)} ${Math.round(45+137*v)})`;}
function axes({c,h},text){c.fillStyle='#7894a8';c.font='8px monospace';c.fillText(text,2,h-2);}
