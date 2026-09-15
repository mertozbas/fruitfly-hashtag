import {setupCalibration} from './calibration.js';
// Physical commissioning is separate from the simulation's controls and brain feed.
const openButton=document.createElement('button');
openButton.id='hardware-open';openButton.className='text-button';openButton.textContent='Gerçek kol ↗';
document.querySelector('.top-actions').prepend(openButton);
const dialog=document.createElement('dialog');
dialog.id='hardware-dialog';dialog.setAttribute('aria-labelledby','hardware-title');
dialog.innerHTML=`
<header class="hw-heading"><div><span class="tiny">SO-101 · DONANIM LABORATUVARI</span><h2 id="hardware-title">Gerçek kol bağlantısı</h2></div><div class="hw-heading-actions"><span class="hw-badge">SALT OKUMA</span><button id="hardware-close" class="icon-button" aria-label="Donanım panelini kapat">×</button></div></header>
<div class="hw-context">Ana ekrandaki beyin ve hareket simülasyona bağlı. Bu panel gerçek USB aygıtları ve kalibrasyon içindir; otonom hareket kapalıdır.</div>
<div class="hw-body"><section class="hw-left">
<nav class="hw-tabs" aria-label="Donanım paneli sekmeleri"><button id="hw-diagnostics-tab" class="active" aria-pressed="true">Bağlantı ve motorlar</button><button id="hw-readiness-tab" aria-pressed="false">Devreye alma <span id="hw-check-count">—</span></button></nav>
<div id="hw-diagnostics" class="hw-tab-content">
<div class="hw-section-title"><h3>Follower · 6 × STS3215</h3><button id="hw-refresh" class="text-button">Envanteri yenile ↻</button></div>
<label for="hw-port">USB motor kartı</label><select id="hw-port"><option value="">Bağlı USB kol yok</option></select>
<label for="hw-calibration">Kaydedilmiş kalibrasyon</label><select id="hw-calibration"><option value="">Aranıyor…</option></select>
<div id="hw-calibration-note" class="hw-small">Dosyalar okunur; üzerine yazılmaz.</div>
<div class="hw-actions"><button id="hw-connect" class="primary" disabled>Motorları oku</button><button id="hw-disconnect">Tüm bağlantıları kapat</button></div>
<div class="hw-section-title"><h3>Eklem telemetrisi</h3><span id="hw-arm-status" class="hw-small">Bağlantı yok</span></div>
<table class="hw-motors"><thead><tr><th>Eklem / ID</th><th>Konum</th><th>°C / V</th><th>Tork</th></tr></thead><tbody id="hw-motors"></tbody></table>
<p class="hw-small">Konumlar LeRobot derece / gripper yüzde ölçeğindedir. Simülasyonun radyan ve sıfır noktalarıyla eşleşme henüz ölçülmedi.</p>
<div id="hw-arm-detail" class="hw-small">Bu tanılama yalnızca okur. Ayar değişiklikleri Kol kalibrasyonu sekmesinde onaylanır.</div>
</div>
<div id="hw-readiness" class="hw-tab-content hidden"><div class="hw-section-title"><h3>Ölçüm ve doğrulama</h3><span class="hw-badge pending">HAREKET KAPALI</span></div><ol id="hw-checks"></ol><p class="hw-small">Kamera önizlemesi algı kalibrasyonunu doğrulamaz. UVC kamera RGB üretir; simülasyondaki derinlik ve fizik temas bilgisi gerçek kolda ayrıca çözülecek.</p><a href="/guide/index.html#docs-so101-hardware" target="_blank" rel="noopener">Bağlantı ve devreye alma rehberi ↗</a><div id="hw-event" class="hw-small"></div></div>
</section><section class="hw-cameras" aria-label="Gerçek kamera önizlemeleri">
${[['wrist','Bilek kamera adayı','32×32 UVC · somun yuvalı adaptör'],['top','Üst / karşı kamera adayı','Sabit kamera · tahta ve çalışma alanı']].map(([role,title,note])=>`
<article class="hw-camera"><div class="hw-section-title"><div><h3>${title}</h3><span class="hw-small">${note}</span></div><span id="hw-${role}-status" class="hw-small">Kapalı</span></div><div class="hw-camera-frame"><img id="hw-${role}-image" alt="${title}" hidden><span id="hw-${role}-empty">Kamera kendiliğinden açılmaz.<br>İndeks seçip önizlemeyi başlat.</span></div><div class="hw-camera-controls"><label for="hw-${role}-index">İndeks</label><input id="hw-${role}-index" type="number" min="0" max="15" step="1" placeholder="—"><button id="hw-${role}-start">Görüntüyü aç</button><button id="hw-${role}-stop" disabled>Durdur</button><span class="hw-small">RGB · derinlik yok</span></div></article>`).join('')}
</section></div><footer class="hw-footer"><span id="hw-message" role="status">Kol bağlı olmadan hazırlık bilgilerini inceleyebilirsin.</span><span id="hw-environment">Sürücüler denetleniyor…</span></footer>`;
document.body.append(dialog);
const $=id=>document.getElementById(id);
const jointNames=['shoulder_pan','shoulder_lift','elbow_flex','wrist_flex','wrist_roll','gripper'];
const displayNames=['Taban','Omuz','Dirsek','Bilek eğimi','Bilek dönüşü','Kıskaç'];
let timer=null,busy=false,latest=null,generation=0;
function message(text,error=false){$('hw-message').textContent=text;$('hw-message').classList.toggle('error',error);}
async function request(path,body){
  const response=await fetch(`/api/hardware/${path}`,{method:body===undefined?'GET':'POST',headers:body===undefined?{}:{'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body),signal:AbortSignal.timeout(10000)});
  const data=await response.json();if(!response.ok)throw new Error(typeof data.detail==='string'?data.detail:'Geçersiz donanım isteği');return data;
}
function options(id,records,empty){
  const select=$(id),signature=JSON.stringify(records),selected=select.value;
  if(select.dataset.signature===signature)return;
  select.dataset.signature=signature;select.replaceChildren();
  if(!records.length)select.add(new Option(empty,''));
  for(const row of records){const option=new Option(row.label,row.id);option.disabled=Boolean(row.disabled);select.add(option);}
  if(records.some(row=>row.id===selected))select.value=selected;
}
function selection(){
  const record=latest?.calibrations.find(r=>r.id===$('hw-calibration').value);
  $('hw-calibration-note').textContent=record?(record.valid?`SHA-256 ${record.sha256.slice(0,16)}… · dosya geçerli; kola bağlılığı henüz doğrulanmadı`:record.errors.join(' · ')):'Kalibrasyon bulunamadı; bağlantı rehberindeki dosya konumunu kontrol et.';
  $('hw-calibration-note').title=record?.path||'';
  $('hw-connect').disabled=busy||!latest?.environment_ready||!$('hw-port').value||!record?.valid||Boolean(latest?.arm.running);
}
function render(state){
  latest=state;
  options('hw-port',state.inventory.ports.map(p=>({id:p.device,label:`${p.device} · ${p.description}`})),'Bağlı USB kol yok');
  options('hw-calibration',state.calibrations.map(c=>({id:c.id,label:`${c.name} · ${c.valid?'geçerli dosya':'kontrol gerekli'}`,disabled:!c.valid})),'Kalibrasyon bulunamadı');
  if(state.arm.running&&state.selected_calibration)$('hw-calibration').value=state.selected_calibration;
  selection();
  const arm=state.arm;
  $('hw-arm-status').textContent=arm.fresh?`CANLI · ${arm.age_ms} ms`:arm.error?'Okuma durdu':arm.running?'Okunuyor…':'Bağlantı yok';
  $('hw-motors').replaceChildren(...jointNames.map((name,i)=>{
    const motor=arm.motors?.find(m=>m.name===name),row=document.createElement('tr');
    const position=arm.fresh&&motor?(arm.calibration_match===false?`${motor.position_raw} ham`:`${motor.value.toFixed(1)}${motor.unit}`):'—';
    const values=[`${displayNames[i]} · ${i+1}`,position,arm.fresh&&motor?`${motor.temperature_c} / ${motor.voltage_v.toFixed(1)}`:'—',arm.fresh&&motor?(motor.torque_enabled?'Açık':'Kapalı'):'—'];
    values.forEach(text=>{const cell=document.createElement('td');cell.textContent=text;row.append(cell);});
    if(motor){row.title=`${name} · Ham konum ${motor.position_raw} · Ham yük ${motor.load_raw} · Mod ${motor.operating_mode}`;row.classList.toggle('hw-outside',!motor.in_calibrated_range);}
    return row;
  }));
  $('hw-arm-detail').textContent=arm.error|| (arm.fresh?(arm.calibration_match?'Dosya ve motor kalibrasyonu eşleşti. Tork yalnızca okunuyor.':`Kalibrasyon uyuşmazlığı (${arm.calibration_mismatches.length} ayar). Konum ölçeği doğrulanmadı; Kol kalibrasyonu sekmesini kullan.`):'Bu tanılama yalnızca okur. Ayar değişiklikleri Kol kalibrasyonu sekmesinde onaylanır.');
  const outside=arm.fresh?arm.motors?.filter(m=>m.in_calibrated_range===false)||[]:[];
  if(outside.length)$('hw-arm-detail').textContent=`Aralık dışında: ${outside.map(m=>`${displayNames[jointNames.indexOf(m.name)]} (${m.position_raw} ham)`).join(', ')}. Kalibrasyon eşleşse de hareket doğrulanmış değildir.`;
  if(arm.fresh&&arm.motors?.some(m=>m.torque_enabled))$('hw-arm-detail').textContent+=' Motor torku açık; paneli kapatmak torku kapatmaz.';
  $('hw-arm-detail').title=arm.calibration_mismatches?.join(', ')||'';
  $('hw-check-count').textContent=`${state.checks.filter(c=>c.passed).length}/${state.checks.length}`;
  $('hw-checks').replaceChildren(...state.checks.map(check=>{const item=document.createElement('li');item.className=check.passed?'passed':'pending';const mark=document.createElement('span');mark.textContent=check.passed?'✓':'○';item.append(mark,document.createTextNode(check.label));return item;}));
  for(const role of ['wrist','top']){
    const camera=state.cameras[role],image=$(`hw-${role}-image`),empty=$(`hw-${role}-empty`);
    image.hidden=!camera.fresh;empty.hidden=Boolean(camera.fresh);
    if(camera.fresh&&camera.image)image.src=`data:image/jpeg;base64,${camera.image}`;else image.removeAttribute('src');
    $(`hw-${role}-status`).textContent=camera.fresh?`${camera.width}×${camera.height} · ${camera.age_ms} ms`:camera.running?'Açılıyor…':'Kapalı';
    empty.textContent=camera.error||'Kamera kendiliğinden açılmaz. İndeks seçip önizlemeyi başlat.';
    $(`hw-${role}-start`).disabled=busy||Boolean(camera.running)||!state.environment_ready;
    $(`hw-${role}-stop`).disabled=busy||!camera.running;
    $(`hw-${role}-index`).disabled=busy||Boolean(camera.running);
    if(camera.running&&Number.isInteger(camera.index))$(`hw-${role}-index`).value=camera.index;
    const observation=camera.perception;
    const current=camera.fresh&&observation?.frame_sequence===camera.sequence&&camera.sequence!==undefined;
    const detail=$(`hw-${role}-vision`);
    detail.textContent=current?`Küp 200: ${observation.cube_visible?'görülüyor':'yok'} · Kutu 211: ${observation.bin_visible?'görülüyor':'yok'} · 3B konum doğrulanmadı`:'Canlı nesne ölçümü yok';
    detail.title=current?`Kare ${camera.sequence} · Yalnızca piksel konumu; beyin girdisi henüz hazır değil.`:'';
  }
  commissioningUI.update(state);
  $('hw-environment').textContent=state.environment_ready?'SÜRÜCÜ ORTAMI HAZIR':'SÜRÜCÜ KURULUMU GEREKLİ';
  $('hw-event').textContent=state.events.at(-1)?.note||'Panel kapandığında oturumlar kapanır. En fazla 10 dakika; 15 saniye güncelleme gelmezse bağlantı bırakılır.';
}
async function action(path,body,note){
  if(busy)return false;busy=true;selection();
  try{const state=await request(path,body);if(dialog.open){render(state);message(note);}return true;}
  catch(error){message(error.message,true);return false;}
  finally{busy=false;if(latest&&dialog.open)render(latest);if(!dialog.open)request('disconnect',{}).catch(()=>{});}
}
async function poll(token){
  if(!dialog.open||token!==generation)return;
  try{const state=await request('state');if(dialog.open&&token===generation)render(state);}
  catch(error){if(dialog.open&&token===generation){message(error.message,true);for(const role of ['wrist','top']){$(`hw-${role}-image`).hidden=true;$(`hw-${role}-empty`).hidden=false;$(`hw-${role}-empty`).textContent='Sunucuya ulaşılamıyor; canlı görüntü durdu.';}}}
  if(dialog.open&&token===generation)timer=setTimeout(()=>poll(token),250);
}
const commissioningUI=setupCalibration({dialog,action,message,options,getState:()=>latest});
for(const role of ['wrist','top']){
  const detail=document.createElement('div');detail.id=`hw-${role}-vision`;detail.className='hw-vision hw-small';
  detail.textContent='Canlı nesne ölçümü yok';$(`hw-${role}-image`).closest('.hw-camera-frame').after(detail);
}
openButton.onclick=async()=>{
  dialog.showModal();const token=++generation;message('USB envanteri okunuyor; kamera ve motor bağlantısı açılmıyor.');
  try{const state=await request('inventory');if(dialog.open&&token===generation){render(state);message(state.inventory.error||'Hazır. Kolunu bağladıktan sonra envanteri yenileyebilirsin.',Boolean(state.inventory.error));}}
  catch(error){message(error.message,true);}
  poll(token);
};
$('hardware-close').onclick=()=>dialog.close();
dialog.addEventListener('close',()=>{
  generation++;clearTimeout(timer);
  fetch('/api/hardware/disconnect',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}',keepalive:true}).catch(()=>{});
  for(const role of ['wrist','top'])$(`hw-${role}-image`).removeAttribute('src');
});
$('hw-refresh').onclick=()=>action('inventory',undefined,'Envanter güncellendi. Kamera ve motor bağlantısı açılmadı.');
$('hw-connect').onclick=()=>action('connect',{port:$('hw-port').value,calibration_id:$('hw-calibration').value},'Motorların salt okuma tanılaması başlatıldı.');
$('hw-disconnect').onclick=()=>action('disconnect',{},'Bağlantılar kapatıldı. Kalibrasyon varsa geri yükleme / kayıt sonucunu yedek geçmişinden kontrol et.');
for(const id of ['hw-port','hw-calibration'])$(id).onchange=selection;
for(const role of ['wrist','top']){
  $(`hw-${role}-start`).onclick=()=>{const raw=$(`hw-${role}-index`).value,index=Number(raw);if(!raw||!Number.isInteger(index)||index<0||index>15){message('Kamera için 0–15 arasında bir indeks seç.',true);return;}action('camera',{role,index},'Kamera önizlemesi başlatılıyor. Görüntüden doğru aygıtı doğrula.');};
  $(`hw-${role}-stop`).onclick=()=>action('camera/stop',{role},'Kamera kapatıldı.');
}
for(const tab of ['diagnostics','readiness','motor-calibration','camera-calibration'])$(`hw-${tab}-tab`).onclick=()=>{
  commissioningUI.show(tab);
  for(const name of ['diagnostics','readiness','motor-calibration','camera-calibration']){$(`hw-${name}`).classList.toggle('hidden',name!==tab);$(`hw-${name}-tab`).classList.toggle('active',name===tab);$(`hw-${name}-tab`).setAttribute('aria-pressed',String(name===tab));}
};
