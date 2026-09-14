// Game instruments reuse the existing fullscreen lab and neural inspector.
const $=id=>document.getElementById(id);
let current=null,pending=false,lastConfiguration=null;
export function bindGame(api,toast){
  $('game-board').replaceChildren(...Array.from({length:9},(_,cell)=>{
    const b=document.createElement('button');b.type='button';b.setAttribute('aria-label',`Kare ${cell+1}`);
    b.addEventListener('click',async()=>{
      if(pending||!current)return;pending=true;
      try{await api('tictactoe/move',{cell,episode:current.episode,board:current.game.board});}
      catch(e){toast(e.message);}finally{pending=false;}
    });return b;
  }));
  $('game-start').addEventListener('click',async()=>{
    try{await api('tictactoe/settings',{opponent:$('game-opponent').value,agent:Number($('game-side').value),execution:$('game-execution').value});}
    catch(e){toast(e.message);}
  });
  $('game-execution').addEventListener('change',()=>{
    const robot=$('game-execution').value==='robot';if(robot)$('game-side').value='1';$('game-side').disabled=robot;
  });
}

export function gameUI(active){
  for(const id of ['game-controls','game-overlay'])$(id).classList.toggle('hidden',!active);
  const pair=$('goal-x').closest('.input-pair');pair.classList.toggle('hidden',active);
  pair.previousElementSibling.classList.toggle('hidden',active);$('apply-goal').classList.toggle('hidden',active);
  $('model-loss').previousElementSibling.textContent=active?'Hamle kaybı':'Doğrulama MSE';
  if(!active){
    document.querySelector('[data-eye="rgb"]').textContent='Renk';
    document.querySelector('[data-eye="depth"]').textContent='Derinlik';return;
  }
  $('session-title').textContent='SO-101 · Tic-tac-toe';
  $('steps').value='6000';$('seed').value='51';
  $('sim-engine').textContent='MUJOCO / SANAL TAHTA';
  $('benchmark-label').textContent='Minimax · kaybetmeme';
  $('model-loss').previousElementSibling.textContent='Hamle kaybı';
  $('signal-title').textContent='Oyun / karar telemetrisi';
  $('signal-left-label').textContent='Giriş aktivitesi';$('signal-right-label').textContent='Motor aktivitesi';
  $('signal-turn-label').textContent='Ağın seçimi';$('signal-unit').textContent='RGB tahta → anatomik alt ağ → kare';
  $('loss-unit').textContent='OPTİMAL HAMLE KAYBI';
  $('distance-label').textContent='BOŞ KARE';
  $('footer-scope').textContent='Öğrenilmiş strateji · Sanal yerleştirme · Motor testi ayrı';
  $('experiment-note').textContent='Hamleleri sinir ağı seçer · Canlı minimax yok';
  $('job-note').textContent='Ayrı strateji modeli eğitilir. Önce ayrı tutulan tahtalar, sonra tüm geçerli durumlar ve rakipler sınanır.';
  $('train').innerHTML='<span>▶</span> Stratejiyi eğit';
  $('robot-loop-label').classList.remove('hidden');
  $('eye-preview').classList.add('robot-eye');
  $('eye-title').textContent='ROBOTUN GÖZLERİ';
  for(const id of ['eye-tabs','eye-expand','eye-status','eye-detail','eye-sync'])$(id).classList.remove('hidden');
  document.querySelector('[data-eye="rgb"]').textContent='Bilek';
  document.querySelector('[data-eye="depth"]').textContent='Üst kamera';
  document.querySelector('[data-camera="body"]').textContent='Perspektif';
  document.querySelector('[data-camera="arena"]').textContent='Üstten';
}

export function updateGame(s){
  current=s;const g=s.game;if(!g)return;
  const configuration=s.model+':'+s.episode;
  if(configuration!==lastConfiguration){
    $('game-opponent').value=g.opponent;$('game-side').value=String(g.agent);$('game-execution').value=g.execution;
    $('game-side').disabled=g.execution==='robot';lastConfiguration=configuration;
  }
  $('game-execution').querySelector('[value="robot"]').disabled=!g.robot_ready;
  const done=s.outcome!=='running';
  $('game-turn').textContent=g.error&&s.paused?'DENEY DURDU':g.motor_running?'ROBOT TAŞI YERLEŞTİRİYOR':done?{won:'AĞ KAZANDI',lost:'RAKİP KAZANDI',draw:'BERABERE'}[s.outcome]:g.waiting_for_human?'SIRA SENDE · KARE SEÇ':'AĞ HAMLE SEÇİYOR';
  $('game-score').textContent=`${g.wins} galibiyet · ${g.draws} beraberlik · ${g.losses} yenilgi`;
  Array.from($('game-board').children).forEach((b,i)=>{
    b.textContent=g.board[i]===1?'X':g.board[i]===-1?'O':String(i+1);
    b.dataset.symbol=g.board[i]===1?'x':g.board[i]===-1?'o':'';
    b.classList.toggle('suggested',!done&&!g.board[i]&&i===g.decision.chosen_cell);
    b.disabled=!!g.board[i]||!g.waiting_for_human||s.paused||pending||done;
    b.title=`Kare ${i+1} · Ağ olasılığı ${(g.decision.probabilities[i]*100).toFixed(1)}%`;
  });
  $('game-mode-note').textContent=g.error||g.robot_note;
  $('game-source').textContent=`Üst RGB · Kare ${g.observed.frame_id} · ${g.observed.valid?'Tahta okundu':'Görüş belirsiz'}`;
  if(g.motor_running)$('game-source').textContent=`${{approach:'Taşa yaklaşma',lower:'Alçalma',close:'Kavrama',lift:'Kaldırma',transport:'Taşıma',place:'Yerleştirme',release:'Bırakma',retreat:'Geri çekilme',park:'Tahtayı doğrulama'}[g.motor?.phase]||'Motor başlıyor'} · Girişim ${g.motor?.attempt||1}/3`;
  $('distance').textContent=String(g.board.filter(v=>v===0).length);
  $('speed').innerHTML=g.execution==='robot'?`${s.speed_mm_s.toFixed(1)}<small> mm/s</small>`:'—';$('reward').textContent=s.outcome==='won'?'+1':s.outcome==='lost'?'−1':'0';
  $('odor-left').textContent=s.layer_means[0].toFixed(3);$('odor-right').textContent=s.layer_means[3].toFixed(3);
  $('steering').textContent=`Kare ${g.decision.chosen_cell+1}`;
  if(s.neural.displayed_pass==='motor'&&g.motor){
    $('steering').textContent=g.motor.action.slice(0,3).map(v=>(v*1000).toFixed(1)).join(' / ');
    $('signal-turn-label').textContent='Hedef XYZ';
  }else $('signal-turn-label').textContent='Ağın seçimi';
  $('contacts').textContent=g.motor_running?`${g.motor?.holding?'İki çene temaslı':'Kavrayıcı serbest'} · ${g.motor?.placements||0}/5 X yerleşti`:`Ağ ${g.agent===1?'X':'O'} / ${g.opponent==='human'?'Sen':g.opponent==='self'?'Rakip ağ':'Rastgele rakip'} ${g.agent===1?'O':'X'} · Karar ${g.decision_age_s.toFixed(1)} s önce`;
  $('episode-stats').textContent=`${g.wins} G · ${g.draws} B · ${g.losses} M`;
  $('outcome').textContent={won:'Ağ kazandı',lost:'Rakip kazandı',draw:'Berabere'}[s.outcome]||'';
  $('robot-loop').checked=g.loop_enabled;
  $('live-label').innerHTML=`<i></i> ${s.paused?'DURAKLATILDI':g.motor_running?'CANLI MOTOR / FİZİK':g.waiting_for_human?'HAMLE BEKLENİYOR':'CANLI STRATEJİ'}`;
  $('footer-status').textContent=g.execution==='robot'?'Kamera → hamle ağı → motor okuması → SO-101 · O sanal rakip':'Kamera → tahta → öğrenilmiş hamle · Sanal taş yerleştirme';
  $('sim-engine').textContent=g.execution==='robot'?'SO-101 / EĞİTİM KÜPLERİ':'MUJOCO / SANAL TAHTA';
  $('footer-scope').textContent=g.execution==='robot'?'30 mm eğitim küpleri · Gözetimli motor aşamaları · Yalnızca simülasyon':'Öğrenilmiş strateji · Sanal yerleştirme · Motor testi ayrı';
}

export function gameEyes(s,eyeMode){
  $('eye-preview').classList.remove('hidden');
  const frame=s.eyes?.[eyeMode];if(frame)$('eye-image').src='data:image/jpeg;base64,'+frame;
  $('eye-image').alt=eyeMode==='rgb'?'SO-101 bilek kamerası':eyeMode==='depth'?'Üst kamera RGB':'Sinir ağına giren tahta okuması';
  $('eye-status').textContent=s.game.observed.valid?'TAHTA GÖRÜLÜYOR':'GÖRÜŞ BELİRSİZ';
  $('eye-detail').textContent=eyeMode==='rgb'?'BİLEK RGB · motor testinde yakın görüş':'ÜST RGB · stratejinin göz girdisi';
  $('eye-sync').textContent=eyeMode==='rgb'?`CANLI BİLEK · GÖZ ${s.game.live_eye_frame_id}`:`KARARA GİREN KARE ${s.neural.sensor_frame_id}`;
  $('eye-image').dataset.frameId=eyeMode==='rgb'?s.game.live_eye_frame_id:s.neural.sensor_frame_id;
  if(s.neural.displayed_pass==='motor'){
    const prediction=s.game.motor?.prediction;
    $('eye-status').textContent=prediction?'GÖRÜŞ KAPALI · SINIRLI TAHMİN':'TAŞ TAKİBİ · BİLEK + ÜST RGB-D';
    $('eye-detail').textContent=(prediction?'TEMAS / SON KONUM · ':'GÖRÜNTÜDEN XYZ · ')+(s.game.motor?.estimated_token||[]).map(v=>(v*1000).toFixed(1)).join(' / ')+' mm';
    $('eye-sync').textContent=`MOTOR GÖZ KARESİ ${s.neural.sensor_frame_id}`;
    $('eye-image').dataset.frameId=s.neural.sensor_frame_id;
  }
}
