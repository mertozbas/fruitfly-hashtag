const $=id=>document.getElementById(id);
// Change instrument labels in place; preserve the established fullscreen layout.
export function behaviorUI(flight){
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
  $('flight-session').classList.toggle('hidden',!flight);
  for(const id of ['odor-neurons','odor-weights'])$(id).classList.toggle('hidden',flight);
  for(const id of ['goal-x','goal-y','steps','seed','model','load-new','delta-mode','flow-floor'])$(id).disabled=false;
  $('train').innerHTML=flight?'<span>▶</span> Yönelme ağını eğit':'<span>▶</span> Eğitimi başlat';
  $('apply-goal').textContent='Hedefi uygula ↗';
  $('reset').title=flight?'Aynı kokulu hedefe uçuşu yeniden başlat':'Aynı hedefi yeniden dene';
  $('reset').setAttribute('aria-label',$('reset').title);
  $('experiment-note').textContent=flight?'Beyin yönü seçer · FlyBody kanatları dengeler':'Doğrulanmış görev · taklit öğrenmesi';
  $('job-note').textContent=flight?'Koku yönelme ağı eğitilir; ardından altı uçuş hedefinde test edilir. Kanat politikası sabittir.':'Yeni model ayrı kaydedilir. Eğitim sonrası 6 hedefte otomatik sınanır.';
  $('signal-chart').setAttribute('aria-label','Canlı sol ve sağ anten yoğunlukları');
  $('loss-chart').setAttribute('aria-label','Kaydedilmiş eğitim doğrulama hatası');
  for(const option of $('model').options)option.hidden=option.value==='flight-pretrained';
}
