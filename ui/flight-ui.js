const $=id=>document.getElementById(id);
// Change instrument labels in place; preserve the established fullscreen layout.
export function behaviorUI(flight){
  const labels={
    'session-title':['Kokuya yönelme','Uçuş / rota takibi'],
    'sim-engine':['NEUROMECHFLY','FLYBODY'],
    'playback-label':['CANLI FİZİK','YAVAŞ ÇEKİM · HEDEF 0,01×'],
    'distance-label':['HEDEF MESAFESİ','İRTİFA'],
    'benchmark-label':['Fizik testi','Gösterim rotaları'],
    'signal-title':['Duyusal telemetri','Uçuş telemetrisi'],
    'signal-left-label':['Sol anten','İrtifa'],
    'signal-right-label':['Sağ anten','Hata'],
    'signal-turn-label':['Dönüş','Kanat · Hz'],
    'signal-unit':['Normalize koku yoğunluğu','İrtifa / referans hata · mm'],
    'loss-title':['Öğrenme eğrisi','Rota takibi'],
    'loss-unit':['DOĞRULAMA MSE','ANLIK TAKİP ÖDÜLÜ'],
    'footer-scope':['MaleCNS alt devresi · Yapay duyusal / motor eşleme','FlyBody hazır motor politika · MaleCNS uçuşa bağlı değil'],
  };
  for(const [id,values] of Object.entries(labels))$(id).textContent=values[Number(flight)];
  $('flight-session').classList.toggle('hidden',!flight);
  for(const id of ['odor-neurons','odor-weights'])$(id).classList.toggle('hidden',flight);
  for(const id of ['goal-x','goal-y','steps','seed','model','load-new','delta-mode','flow-floor'])$(id).disabled=flight;
  if(flight)$('train').disabled=true;
  $('apply-goal').textContent=flight?'Sonraki uçuş rotası →':'Hedefi uygula ↗';
  $('reset').title=flight?'Bu uçuş rotasını yeniden başlat':'Aynı hedefi yeniden dene';
  $('reset').setAttribute('aria-label',$('reset').title);
  $('experiment-note').textContent=flight?'Hazır politika · havada başlayan uçuş · MaleCNS bağlantısı yok':'Doğrulanmış görev · taklit öğrenmesi';
  $('job-note').textContent=flight?'Uçuş hazır kontrolcüyle çalışır. Bu ekrandaki eğitim koku devresine aittir.':'Yeni model ayrı kaydedilir. Eğitim sonrası 6 hedefte otomatik sınanır.';
  $('signal-chart').setAttribute('aria-label',flight?'Canlı uçuş irtifası ve referans rota hatası':'Canlı sol ve sağ anten yoğunlukları');
  $('loss-chart').setAttribute('aria-label',flight?'Canlı uçuş takip ödülü':'Kaydedilmiş eğitim doğrulama hatası');
  for(const option of $('model').options)option.hidden=flight?option.value!=='flight-pretrained':option.value==='flight-pretrained';
}
