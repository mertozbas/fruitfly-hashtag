const $=id=>document.getElementById(id);
// Change instrument labels in place; preserve the established fullscreen layout.
export function behaviorUI(task='odor'){
  const flight=task==='flight';
  const labels={
    'session-title':['Kokuya yönelme','Beyin ile uçuş / kokuya yönelme'],
    'sim-engine':['NEUROMECHFLY','FLYBODY'],
    'playback-label':['CANLI FİZİK','YAVAŞ ÇEKİM · HEDEF 0,01×'],
    'distance-label':['HEDEF MESAFESİ','HEDEF MESAFESİ'],
    'benchmark-label':['Yürüme testi','Uçuş testi'],
    'signal-title':['Duyusal telemetri','Uçuş telemetrisi'],
    'signal-left-label':['Sol anten','Sol anten'],
    'signal-right-label':['Sağ anten','Sağ anten'],
    'signal-turn-label':['Dönüş','Yaw · rad/s'],
    'signal-unit':['Normalize koku yoğunluğu','Normalize koku · beyin yön komutu'],
    'loss-title':['Öğrenme eğrisi','Öğrenme eğrisi'],
    'loss-unit':['DOĞRULAMA MSE','DOĞRULAMA MSE'],
    'footer-scope':['MaleCNS alt devresi · Yapay duyusal / motor eşleme','MaleCNS alt devresi → yön hedefi → FlyBody kanat kontrolü'],
  };
  for(const [id,values] of Object.entries(labels))$(id).textContent=values[Number(flight)];
  const extra={
    avoidance:{title:'Kokudan kaçınma',note:'Koku alt ağı → kaçış yönü',unit:'Koku yoğunluğu · 3 mm tehlike alanı',distance:'KAYNAK MESAFESİ'},
    vision:{title:'Görsel yönelme',note:'Fotoreseptör → optik → inen katman',unit:'Kırmızı hedef belirginliği · grafik otomatik ölçek',left:'Sol göz',right:'Sağ göz'},
    terrain:{title:'Engel aşma · deneysel',note:'Temas → VNC → düzeltme kazancı',unit:'Normalize karşı kuvvet · 100 ms sönüm',left:'Sol temas',right:'Sağ temas',turn:'Kazanç'},
  }[task];
  if(extra){
    $('session-title').textContent=extra.title;
    $('signal-unit').textContent=extra.unit;
    $('signal-left-label').textContent=extra.left||'Sol anten';
    $('signal-right-label').textContent=extra.right||'Sağ anten';
    $('signal-turn-label').textContent=extra.turn||'Dönüş';
    $('distance-label').textContent=extra.distance||'HEDEF MESAFESİ';
  }
  $('flight-session').classList.toggle('hidden',!flight);
  for(const id of ['odor-neurons','odor-weights'])$(id).classList.toggle('hidden',flight);
  for(const id of ['goal-x','goal-y','steps','seed','model','load-new','delta-mode','flow-floor'])$(id).disabled=false;
  for(const id of ['goal-x','goal-y','apply-goal'])$(id).disabled=task==='terrain';
  $('eye-preview').classList.toggle('hidden',task!=='vision');
  $('train').innerHTML=flight?'<span>▶</span> Yönelme ağını eğit':'<span>▶</span> Eğitimi başlat';
  $('apply-goal').textContent='Hedefi uygula ↗';
  $('reset').title=flight?'Aynı kokulu hedefe uçuşu yeniden başlat':'Aynı hedefi yeniden dene';
  $('reset').setAttribute('aria-label',$('reset').title);
  $('experiment-note').textContent=extra?.note||(flight?'Beyin yönü seçer · FlyBody kanatları dengeler':'Koku alt ağı · taklit öğrenmesi');
  $('job-note').textContent=extra?'Yeni model ayrı kaydedilir. 6 koşul × eğitimli / eğitimsiz / çıkış kapalı karşılaştırması yapılır.':flight?'Koku yönelme ağı eğitilir; ardından altı uçuş hedefinde test edilir. Kanat politikası sabittir.':'Yeni model ayrı kaydedilir. Eğitim sonrası 6 hedefte otomatik sınanır.';
  $('signal-chart').setAttribute('aria-label','Canlı sol ve sağ anten yoğunlukları');
  $('loss-chart').setAttribute('aria-label','Kaydedilmiş eğitim doğrulama hatası');
  for(const option of $('model').options){const mt=option.dataset.task||'odor';option.hidden=mt!==task&&!(['odor','flight'].includes(task)&&['odor','flight'].includes(mt));}
}
