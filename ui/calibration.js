import * as THREE from 'three';
import {OrbitControls} from 'three/addons/controls/OrbitControls.js';

const names={shoulder_pan:'Taban',shoulder_lift:'Omuz',elbow_flex:'Dirsek',wrist_flex:'Bilek eğimi',wrist_roll:'Bilek dönüşü',gripper:'Kıskaç'};
const stages={connecting:'Bağlanıyor',backup:'Yedek hazır',reference:'Orta konum',ranges:'Hareket aralıkları',review:'Sonuçları incele',saved:'Kaydedildi',cancelled:'İptal edildi',failed:'Kontrol gerekli',restore_review:'Yedeği incele',restored:'Yedek geri yüklendi'};
export function setupCalibration({dialog,action,message,options,getState}){
  const $=id=>document.getElementById(id);
  dialog.querySelector('.hw-tabs').insertAdjacentHTML('beforeend','<button id="hw-motor-calibration-tab" aria-pressed="false">Kol kalibrasyonu</button><button id="hw-camera-calibration-tab" aria-pressed="false">Kamera kalibrasyonu</button>');
  dialog.querySelector('.hw-left').insertAdjacentHTML('beforeend',`
  <div id="hw-motor-calibration" class="hw-tab-content hidden">
    <div class="hw-section-title"><h3>Kalibrasyon sihirbazı</h3><span id="mc-stage" class="hw-badge">BAĞLANTISIZ</span></div>
    <div class="cal-steps" aria-label="Kalibrasyon adımları"><span>1 Yedek</span><span>2 Orta konum</span><span>3 Aralık</span><span>4 Kaydet</span></div>
    <div id="mc-idle"><label for="mc-port">Follower USB portu</label><select id="mc-port"></select><div class="cal-two"><div><label for="mc-profile">Kalibrasyon profili</label><select id="mc-profile"></select></div><div><label for="mc-name">Kol adı</label><input id="mc-name" value="so101_follower" maxlength="64"></div></div><p class="hw-small">İlk adım motor ayarlarını ve dosyayı yedekler. Tork bırakma işlemi bir sonraki ekranda onaylanır.</p><button id="mc-start" class="primary wide" disabled>Yedekle ve başla</button><div class="cal-history"><label for="mc-history">Önceki yedekler</label><select id="mc-history"></select><button id="mc-restore" class="secondary" disabled>Seçili yedeğe dön</button><span id="mc-history-note" class="hw-small"></span></div></div>
    <div id="mc-guide" class="hidden"><p id="mc-instruction" class="cal-instruction"></p><div id="mc-reference"><canvas id="mc-reference-canvas" aria-label="SO-101 şematik orta konum rehberi"></canvas><span>3D orta konum rehberi · Şematik, canlı ölçüm değil<br>Mouse: döndür / yakınlaştır</span></div><div id="mc-ranges"></div><div id="mc-result"></div><label id="mc-ack-label" class="cal-ack"><input id="mc-ack" type="checkbox"><span id="mc-ack-text"></span></label><div class="cal-buttons"><button id="mc-next" class="primary">Devam</button><button id="mc-cancel">İptal et ve ayarları geri al</button></div><a id="mc-report" class="cal-report" target="_blank" rel="noopener">Yedek ve sonuç raporu ↗</a></div>
    <p id="mc-warning" class="cal-warning" role="status"></p><p class="hw-small cal-safety">Tork bırakıldığında kolu destekle. Kalibrasyon sonunda tork kapalı kalır. USB koparsa veya geri yükleme başarısızsa otomatik harekete geçilmez.</p>
  </div>
  <div id="hw-camera-calibration" class="hw-tab-content hidden">
    <div class="hw-section-title"><h3>Kamera ölçüm istasyonu</h3><a href="/assets/calibration-board.svg" download="neural-lab-charuco-a4.svg" class="text-button">A4 pano indir ↓</a></div>
    <div class="cal-two"><div><label for="cc-role">Kamera</label><select id="cc-role"><option value="wrist">Bilek · UVC</option><option value="top">Üst / karşı</option></select></div><div><label for="cc-label">Fiziksel kamera adı</label><input id="cc-label" maxlength="64" value="UVC bilek"></div></div>
    <div id="cc-identity-controls"><label class="cal-ack"><input id="cc-identity" type="checkbox"><span>Önizlemeden doğru kamerayı doğruladım; lens / odak ayarını sabit tutacağım.</span></label>
    <div class="cal-profile"><select id="cc-profile" aria-label="Kaydedilmiş kamera profili"></select><button id="cc-load">Profille aç</button><button id="cc-enable">Panoyu algıla</button></div></div>
    <nav class="cal-subtabs"><button id="cc-lens-tab" class="active">Lens ölçümü</button><button id="cc-workspace-tab">Masa / robot referansı</button></nav>
    <div id="cc-lens"><p class="hw-small">6×8 ChArUco · 20 mm kare. Panoyu %100 boyutta bas ve 50 mm çizgiyi cetvelle kontrol et. En az 18 net kare: görüntünün farklı bölgeleri ve iki eksende farklı eğimler.</p><div class="cal-camera-metrics"><div><span>KÖŞE</span><b id="cc-corners">—</b></div><div><span>KARE</span><b id="cc-count">0 / 18</b></div><div><span>RMS / AYRI KARE</span><b id="cc-error">—</b></div></div><div id="cc-samples" class="cal-samples" aria-label="Toplanan kalibrasyon kareleri"></div><div class="cal-buttons"><button id="cc-capture">Kareyi al</button><button id="cc-solve">Hesapla</button><button id="cc-reset">Ölçümü sıfırla</button></div><div id="cc-result" class="hw-small"></div><label class="cal-ack"><input id="cc-save-ack" type="checkbox"><span>Pano ölçeğini ve sonuçları kontrol ettim.</span></label><button id="cc-save" class="primary wide">Lens profilini kaydet</button></div>
    <div id="cc-workspace" class="hidden"><p class="hw-small">Kaydedilmiş lens profiliyle pano masada sabitken pozu ölç. O: panonun sol üst dış köşesi; X sağa, Y aşağı. Önizlemede eksenler görünür. Bu kayıt nesne yüksekliği / derinlik sensörü değildir.</p><label class="cal-ack"><input id="cc-base" type="checkbox"><span>Panonun robot tabanına göre ölçülmüş pozunu gireceğim.</span></label><div id="cc-base-inputs" class="cal-pose hidden">${['X mm','Y mm','Z mm','Roll °','Pitch °','Yaw °'].map((label,i)=>`<label>${label}<input id="cc-pose-${i}" type="number" step="any" placeholder="Ölçüm"></label>`).join('')}</div><p class="hw-small">Dönüş sırası: Rz(yaw) · Ry(pitch) · Rx(roll). Taban ölçümü girilmezse yalnız pano–kamera dönüşümü kaydedilir.</p><label class="cal-ack"><input id="cc-plane-ack" type="checkbox"><span>Pano ölçüsü doğru, pano masaya sabit ve bu karedeki yerleşimi doğruladım.</span></label><button id="cc-workspace-save" class="primary wide">Güncel pano pozunu kaydet</button><div id="cc-workspace-result" class="hw-small"></div><p class="cal-warning">Bilek hareket edince kamera pozu değişir. Bu kayıt el–göz montaj kalibrasyonu değildir; güncel pano görünmeden bilek pozu kullanılamaz.</p></div>
    <p id="cc-warning" class="cal-warning" role="status">Önce sağdaki önizlemede kamerayı aç.</p><a id="cc-report" class="cal-report hidden" target="_blank" rel="noopener">Kamera / masa kaydını aç ↗</a>
  </div>`);
  let lastRevision=null,selectedOnce=false,reference=null,activeTab='diagnostics';
  function update(state){
    const s=state.calibration_session||{},terminal=['saved','cancelled','failed','restored'].includes(s.stage),idle=!s.stage;
    options('mc-port',state.inventory.ports.map(p=>({id:p.device,label:p.device})),'Bağlı USB kol yok');
    options('mc-profile',[...state.calibrations.map(r=>({id:r.id,label:r.name})),{id:'',label:'Yeni profil oluştur'}],'Yeni profil');
    if(!selectedOnce&&state.calibrations.length){$('mc-profile').value=state.calibrations[0].id;selectedOnce=true;profileChanged();}
    options('mc-history',(state.calibration_history||[]).map(r=>({id:r.id,label:`${r.target} · ${new Date(r.created*1000).toLocaleString('tr-TR')}${r.recovery_needed?' · KURTARMA GEREKLİ':''}`})),'Henüz yedek yok');
    $('mc-start').disabled=!state.environment_ready||!$('mc-port').value;
    $('mc-restore').disabled=$('mc-start').disabled||!$('mc-history').value;
    $('mc-stage').textContent=stages[s.stage]||'BAĞLANTI BEKLİYOR';$('mc-idle').classList.toggle('hidden',!idle);$('mc-guide').classList.toggle('hidden',idle);
    if(s.revision!==lastRevision){$('mc-ack').checked=false;lastRevision=s.revision;}
    const copy={backup:['Yedek diske kaydedildi. Kol boş ve destekli olduğunda motor torkunu bırak.','Kolu destekliyorum; üzerinde yük yok. Torkun kapanmasını onaylıyorum.','Torku bırak','release'],reference:['Kolu, eklemlerin hareket aralıklarının ortasına elle getir. 3D rehber yaklaşık orta konumu gösterir.','Bütün eklemler orta konumda; kolu sabit tutuyorum.','Orta konumu kaydet','reference'],ranges:[`${names[s.joint]||''}: iki mekanik ucu zorlamadan, yavaşça elle tara. Bilek dönüşü 0–4095 olarak alınır; kablosunu dolama.`, 'Bu eklemin iki ucunu da ölçtüm; mekanik sınırlara zorlamadım.','Bu eklemi tamamla','next'],review:['Ölçülen sınırlar ve offsetler aşağıda. Kaydetmeden önce değerleri ve profil adını incele.','Sonuçları inceledim; motorlara ve profil dosyasına uygulanmasını onaylıyorum.','Doğrula ve kaydet','save'],restore_review:['Seçilen yedek bu kol ve profil ile eşleşti. Geri yükleme torku açmaz.','Seçili yedeğin geri yüklenmesini onaylıyorum.','Yedeği geri yükle','restore']};
    const step=copy[s.stage];$('mc-instruction').textContent=step?.[0]||s.warning||'Bağlantı ve yedek hazırlanıyor…';$('mc-ack-text').textContent=step?.[1]||'';
    $('mc-ack-label').classList.toggle('hidden',!step);$('mc-next').textContent=terminal?'Yeni oturum':step?.[2]||'Bekleniyor…';$('mc-next').dataset.op=step?.[3]||'';
    $('mc-next').disabled=terminal?false:!step||!s.fresh||!$('mc-ack').checked;
    $('mc-cancel').classList.toggle('hidden',terminal);$('mc-cancel').disabled=!s.running;
    $('mc-reference').classList.toggle('hidden',!['backup','reference'].includes(s.stage));
    if(activeTab==='motor-calibration'&&!$('mc-reference').classList.contains('hidden'))ensureReference();
    $('mc-ranges').replaceChildren();
    if(s.stage==='ranges')for(const [name,label] of Object.entries(names)){
      const r=s.ranges?.[name],row=document.createElement('div');row.className='cal-range'+(name===s.joint?' current':'');
      const text=document.createElement('span');text.textContent=label;const bar=document.createElement('div');const fill=document.createElement('i');
      fill.style.left=`${(r?.min||0)/4095*100}%`;fill.style.width=`${r?(r.max-r.min)/4095*100:0}%`;bar.append(fill);
      const value=document.createElement('b');value.textContent=name==='wrist_roll'?'0–4095 · sabit':r?`${r.min}–${r.max} · ${r.samples} örnek`:'Sırada';
      row.append(text,bar,value);$('mc-ranges').append(row);
    }
    $('mc-result').replaceChildren();
    if(['review','restore_review','saved','restored'].includes(s.stage)&&s.candidate){
      const table=document.createElement('table');table.className='hw-motors';table.innerHTML='<thead><tr><th>Eklem</th><th>Min</th><th>Max</th><th>Offset</th></tr></thead>';const body=document.createElement('tbody');
      for(const [name,m] of Object.entries(s.candidate)){const row=document.createElement('tr');for(const v of [names[name],m.range_min,m.range_max,m.homing_offset]){const cell=document.createElement('td');cell.textContent=v;row.append(cell);}body.append(row);}table.append(body);$('mc-result').append(table);
    }
    $('mc-warning').textContent=[...(s.errors||[]),s.warning].filter(Boolean).join(' · ');
    $('mc-report').classList.toggle('hidden',!s.backup_id);$('mc-report').href=`/api/hardware/calibration/report?kind=motor&record_id=${encodeURIComponent(s.backup_id||'')}`;
    updateCamera(state);
    dialog.querySelector('.hw-heading-actions .hw-badge').textContent=state.mode==='calibration'?'KALİBRASYON OTURUMU':'SALT OKUMA';
  }
  function profileChanged(){const value=$('mc-profile').value,record=getState()?.calibrations.find(r=>r.id===value);$('mc-name').disabled=Boolean(record);if(record)$('mc-name').value=record.name;}
  $('mc-profile').onchange=profileChanged;
  function begin(restore=false){action('calibration/start',{port:$('mc-port').value,robot_id:$('mc-name').value,calibration_id:$('mc-profile').value||null,backup_id:restore?$('mc-history').value:null},'Kol bilgileri okunuyor; yedek tamamlanınca devam adımı açılacak.');}
  $('mc-start').onclick=()=>begin();$('mc-restore').onclick=()=>begin(true);
  $('mc-ack').onchange=()=>{if(getState())update(getState());};
  $('mc-next').onclick=()=>{
    const s=getState()?.calibration_session;if(!s)return;
    if(['saved','cancelled','failed','restored'].includes(s.stage)){action('disconnect',{},'Önceki oturum kapatıldı; yedekler korunuyor.');return;}
    action('calibration/command',{session:s.session,revision:s.revision,op:$('mc-next').dataset.op,supported:$('mc-ack').checked,range_confirmed:$('mc-ack').checked,confirmed:$('mc-ack').checked},'Kalibrasyon adımı işleniyor…');
  };
  $('mc-cancel').onclick=()=>{const s=getState()?.calibration_session;if(s)action('calibration/command',{session:s.session,revision:s.revision,op:'cancel'},'İptal ve geri yükleme sonucu bekleniyor…');};
  function cameraState(){return getState()?.cameras[$('cc-role').value]||{};}
  function cameraAction(op,extra={}){const camera=cameraState();if(!camera.session){message('Önce seçili kameranın önizlemesini aç.',true);return;}action('camera/calibration',{session:camera.session,role:$('cc-role').value,op,...extra},'Kamera ölçüm işlemi gönderildi.');}
  function updateCamera(state){
    const role=$('cc-role').value,c=state.cameras[role]||{},s=c.calibration||{},identity=$('cc-identity').checked;
    options('cc-profile',(state.camera_profiles||[]).filter(p=>p.role===role).map(p=>({id:p.id,label:`${p.device_label} · ${p.size.join('×')} · ${p.rms_px.toFixed(2)} px`})),'Kaydedilmiş lens profili yok');
    $('cc-enable').disabled=!c.fresh||!identity||!$('cc-label').value.trim();$('cc-load').disabled=!identity||!$('cc-profile').value;
    $('cc-corners').textContent=s.detected_corners||'—';$('cc-count').textContent=`${s.sample_count||0} / 18`;
    const result=s.candidate||s.saved;$('cc-error').textContent=result?`${result.rms_px.toFixed(2)} / ${Math.max(...result.holdout_rms_px).toFixed(2)} px`:'—';
    $('cc-samples').replaceChildren(...Array.from({length:30},(_,i)=>{const cell=document.createElement('i');cell.className=i<(s.sample_count||0)?'collected':'';return cell;}));
    $('cc-capture').disabled=!c.fresh||!s.enabled||s.detected_corners<12||Boolean(s.candidate);
    $('cc-solve').disabled=!c.fresh||s.sample_count<18||Boolean(s.candidate);
    $('cc-reset').disabled=!c.fresh||!s.enabled;
    $('cc-save').disabled=!c.fresh||!s.candidate||!$('cc-save-ack').checked;
    $('cc-workspace-save').disabled=!c.fresh||!s.saved||!s.live_pose||!$('cc-plane-ack').checked;
    $('cc-result').textContent=result?`fx ${result.camera_matrix[0][0].toFixed(1)} · fy ${result.camera_matrix[1][1].toFixed(1)} · ${result.training_samples} hesap / ${result.holdout_samples} ayrı doğrulama karesi. ${s.saved?'Profil kaydedildi.':'Sonuç kaydedilmeyi bekliyor.'}`:'';
    $('cc-warning').textContent=s.warning||(c.fresh?(s.enabled?'Pano algılaması açık. Lens / çözünürlük değişirse kalibrasyonu yenile.':'Kamera kimliğini doğrula ve pano algılamasını aç.'):'Önce sağdaki önizlemede bu kamerayı aç.');
    $('cc-workspace-result').textContent=s.workspace?`Pano pozu kaydedildi · ${s.workspace.reprojection_px.toFixed(2)} px. ${s.workspace.base_from_camera?'Taban dönüşümü girilen ölçümlerden hesaplandı; fiziksel doğrulama bekliyor.':'Robot tabanı ölçüsü girilmedi.'}`:'';
    $('cc-report').classList.toggle('hidden',!s.saved);$('cc-report').href=`/api/hardware/calibration/report?kind=camera&record_id=${encodeURIComponent(role+'/'+(s.workspace?s.session:s.saved?.session||''))}`;
  }
  $('cc-role').onchange=()=>{$('cc-identity').checked=false;$('cc-save-ack').checked=false;$('cc-plane-ack').checked=false;$('cc-label').value=$('cc-role').value==='wrist'?'UVC bilek':'Üst kamera';if(getState())updateCamera(getState());};
  for(const id of ['cc-identity','cc-save-ack','cc-plane-ack'])$(id).onchange=()=>{if(getState())updateCamera(getState());};
  $('cc-label').oninput=()=>{if(getState())updateCamera(getState());};
  $('cc-enable').onclick=()=>cameraAction('enable',{device_label:$('cc-label').value,confirmed:$('cc-identity').checked});
  for(const op of ['capture','solve','reset'])$(`cc-${op}`).onclick=()=>cameraAction(op);
  $('cc-save').onclick=()=>cameraAction('save',{confirmed:$('cc-save-ack').checked});
  $('cc-load').onclick=async()=>{
    const role=$('cc-role').value,raw=$(`hw-${role}-index`).value,index=Number(raw),profile_id=$('cc-profile').value;
    if(!raw||!Number.isInteger(index)||index<0||index>15){message('Önizleme bölümünde kamera indeksini gir.',true);return;}
    if(!await action('camera/stop',{role},'Önceki önizleme kapatıldı.'))return;
    if(await action('camera',{role,index,profile_id,device_verified:$('cc-identity').checked},'Profil seçilen kamera için açılıyor; çözünürlük kontrol edilecek.')){
      const profile=getState()?.camera_profiles?.find(p=>p.id===profile_id);if(profile)$('cc-label').value=profile.device_label;
    }
  };
  $('cc-base').onchange=()=>$('cc-base-inputs').classList.toggle('hidden',!$('cc-base').checked);
  $('cc-workspace-save').onclick=()=>{
    let base_pose=null;
    if($('cc-base').checked){const raw=Array.from({length:6},(_,i)=>$(`cc-pose-${i}`).value);if(raw.some(v=>!v.trim()||!Number.isFinite(Number(v)))){message('Altı poz alanını ölçülmüş değerlerle doldur.',true);return;}base_pose=raw.map(Number);}
    cameraAction('workspace',{confirmed:$('cc-plane-ack').checked,base_pose});
  };
  for(const tab of ['lens','workspace'])$(`cc-${tab}-tab`).onclick=()=>{for(const name of ['lens','workspace']){$(`cc-${name}`).classList.toggle('hidden',name!==tab);$(`cc-${name}-tab`).classList.toggle('active',name===tab);}$('cc-identity-controls').classList.toggle('hidden',tab==='workspace');};
  async function ensureReference(){
    if(reference)return;reference={loading:true};
    try{
      const data=await fetch('/assets/calibration-reference.json').then(r=>r.json()),canvas=$('mc-reference-canvas');
      const renderer=new THREE.WebGLRenderer({canvas,antialias:true,alpha:true});renderer.setPixelRatio(Math.min(devicePixelRatio,2));
      const scene=new THREE.Scene(),camera=new THREE.PerspectiveCamera(35,1,.001,4);camera.up.set(0,0,1);camera.position.set(.45,-.55,.35);
      const controls=new OrbitControls(camera,canvas);controls.target.set(0,0,.15);controls.minDistance=.2;controls.maxDistance=1.4;controls.enablePan=false;controls.update();
      scene.add(new THREE.HemisphereLight(0xc7eeff,0x243442,3));const light=new THREE.DirectionalLight(0xffffff,3);light.position.set(1,-1,2);scene.add(light);
      const points=[new THREE.Vector3(0,0,.01),...data.points.map(p=>new THREE.Vector3(...p.position))];
      for(let i=0;i<points.length;i++){
        const joint=new THREE.Mesh(new THREE.SphereGeometry(.013,16,12),new THREE.MeshStandardMaterial({color:0x7fe3cf,roughness:.5}));joint.position.copy(points[i]);scene.add(joint);
        if(i){const direction=points[i].clone().sub(points[i-1]),link=new THREE.Mesh(new THREE.CylinderGeometry(.011,.014,direction.length(),12),new THREE.MeshStandardMaterial({color:0x718b9c,metalness:.25,roughness:.5}));link.position.copy(points[i]).add(points[i-1]).multiplyScalar(.5);link.quaternion.setFromUnitVectors(new THREE.Vector3(0,1,0),direction.normalize());scene.add(link);}
      }
      const base=new THREE.Mesh(new THREE.BoxGeometry(.09,.09,.012),new THREE.MeshStandardMaterial({color:0x344b5e}));scene.add(base);
      function draw(){if(!dialog.open||activeTab!=='motor-calibration'||$('mc-reference').classList.contains('hidden'))return;const rect=canvas.getBoundingClientRect();if(!rect.width||!rect.height)return;renderer.setSize(rect.width,rect.height,false);camera.aspect=rect.width/rect.height;camera.updateProjectionMatrix();renderer.render(scene,camera);}
      controls.addEventListener('change',draw);new ResizeObserver(draw).observe(canvas);reference={draw};draw();
    }catch(error){$('mc-reference').querySelector('span').textContent='3D rehber yüklenemedi; eklemleri mekanik aralıklarının ortasına getir.';}
  }
  return {update,show(tab){activeTab=tab;if(tab==='motor-calibration'){ensureReference();requestAnimationFrame(()=>reference?.draw?.());}}};
}
