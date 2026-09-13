const el=(tag,text,cls)=>{const e=document.createElement(tag);if(text!==undefined)e.textContent=text;if(cls)e.className=cls;return e;};
const value=v=>v===null||v===undefined||v===''?'Veri yok':typeof v==='object'?JSON.stringify(v):String(v);
const num=(v,d=4)=>Number.isFinite(v)?v.toLocaleString('tr-TR',{maximumFractionDigits:d}):'—';

export function createInspector({api,onSelect}) {
  const host=document.getElementById('detail-drawer'), content=document.getElementById('detail-content');
  let selection=null, data=null, tab='summary', direction='out', page=0, generation=0, renderGeneration=0, model='trained', activity=[];
  const roles={ORN:'İki antenin sentetik koku sinyalini alan giriş katmanı.',ALPN:'Bu modelde ORN girdisini Kenyon hücrelerine aktaran sabit katman.',Kenyon_Cell:'Koku girdisini MBON katmanına iletir. MBON bağlantı çarpanları eğitimde değişebilir.',MBON:'Yapay motor okuma katmanına girdi verir; çıkıştan dönüş komutu hesaplanır.'};
  function facts(rows){const dl=el('dl',undefined,'detail-facts');for(const [k,v] of rows){dl.append(el('dt',k),el('dd',value(v)));}return dl;}
  function section(title,rows){const e=el('section');e.append(el('h3',title),facts(rows));return e;}
  function note(text){return el('p',text,'detail-note');}
  function refreshTabs(){document.querySelectorAll('[data-detail-tab]').forEach(b=>{b.classList.toggle('active',b.dataset.detailTab===tab);b.hidden=selection?.kind==='edge'&&b.dataset.detailTab==='connections';});}
  async function show(next,modelId=model){
    selection=next; data=null;model=modelId;tab='summary';page=0;const token=++generation;
    host.classList.remove('hidden');host.setAttribute('aria-busy','true');content.replaceChildren(note('Kaynak veriler okunuyor…'));
    document.getElementById('detail-kind').textContent=next.kind==='node'?'NÖRON KAYDI':'YÖNLÜ BAĞLANTI';
    document.getElementById('detail-title').textContent=next.kind==='node'?next.id:`${next.source} → ${next.target}`;
    refreshTabs();
    try{
      const result=await api(next.kind==='node'?`neuron/${next.id}`:`connection/${next.source}/${next.target}?model=${encodeURIComponent(model)}`);
      if(token!==generation)return;
      data=result;document.getElementById('detail-title').textContent=next.kind==='node'?(result.type||result.instance||result.id):`${result.source.type||result.source.id} → ${result.target.type||result.target.id}`;
      await render();
    }catch(e){if(token===generation)content.replaceChildren(note(e.message));}
    finally{if(token===generation)host.setAttribute('aria-busy','false');}
  }
  async function render(){
    if(!data)return;
    const renderToken=++renderGeneration;
    refreshTabs();content.replaceChildren();
    if(model==='flight-pretrained')content.append(note('MaleCNS anatomik kaydı. Bu nöron ve bağlantılar FlyBody uçuş politikasına bağlı değil.'));
    if(selection.kind==='edge'){
      const m=data.model;
      if(tab==='metadata'){
        content.append(section('Kaynak ve yorum', [['Veri seti',data.dataset],['Sinaptik işaret','Bu modelde uyarıcı / baskılayıcı işaret kullanılmıyor'],['Geometri','Soma konumları arasındaki çizgi; gerçek akson geometrisi değil']]));
      }else{
        content.append(section('Anatomik bağlantı',[['Kaynak',`${data.source.type||'Tip yok'} · ${data.source.id}`],['Hedef',`${data.target.type||'Tip yok'} · ${data.target.id}`],['Yön','Kaynak → hedef'],['Sinaptik temas',num(data.anatomical_contacts,0)],['Kaynak nörotransmiteri',data.source.neurotransmitter]]));
        const navigation=el('div',undefined,'detail-actions');
        for(const [label,node] of [['Kaynak nöron',data.source],['Hedef nöron',data.target]]){const b=el('button',label,'secondary');b.onclick=()=>{onSelect({kind:'node',id:node.id});show({kind:'node',id:node.id},model);};navigation.append(b);}content.append(navigation);
        content.append(m?section('Seçili modelde',[['Katman',m.layer],['Anatomik başlangıç ağırlığı',num(m.base_weight,8)],['Güncel model ağırlığı',num(m.current_weight,8)],['Eğitim çarpanı',num(m.gain,5)+' ×'],['Değişim',num(m.change_percent,2)+' %'],['Eğitilebilir',m.trainable?'Evet · KC → MBON':'Hayır · sabit katman']]):note('Bu anatomik bağlantı kullanılan ileri beslemeli alt devreye dahil değil.'));
        const live=el('div',undefined,'detail-live');live.id='detail-live';content.append(live);tick(activity);
        content.append(note('Temas sayısı anatomik veridir. Normalize model ağırlığı ve eğitim çarpanı farklı niceliklerdir.'));
      }
    }else if(tab==='metadata'){
      content.append(section('Tüm anotasyon alanları',Object.entries(data.annotations)));
      for(const nt of data.neurotransmitter_predictions)content.append(section('Nörotransmiter tahmin kaydı',Object.entries(nt)));
      content.append(section('Veri kaynakları',data.source_files.map((f,i)=>['Dosya '+(i+1),f])));
    }else if(tab==='connections'){
      const toolbar=el('div',undefined,'detail-actions');
      for(const [dir,title] of [['in','Gelen'],['out','Giden']]){const b=el('button',title,dir===direction?'primary':'secondary');b.onclick=()=>{direction=dir;page=0;render();};toolbar.append(b);}content.append(toolbar);
      const results=el('div');content.append(results);results.textContent='Bağlantılar okunuyor…';
      const token=generation, id=selection.id;
      try{
        const r=await api(`neuron/${id}/connections?direction=${direction}&page=${page}&limit=12`);
        if(token!==generation||renderToken!==renderGeneration||tab!=='connections')return;
        results.replaceChildren(note(`${num(r.total,0)} partner · Anatomik temas sayısına göre sıralı`));
        const table=el('table',undefined,'detail-table');const head=el('thead');const hr=el('tr');['Nöron / tip','Temas','İncele'].forEach(t=>hr.append(el('th',t)));head.append(hr);table.append(head);
        const body=el('tbody');
        for(const item of r.rows){const tr=el('tr');const name=el('td');const b=el('button',item.type||item.id,'text-button');b.onclick=()=>{onSelect({kind:'node',id:item.id});show({kind:'node',id:item.id});};name.append(b,el('small',item.id));const edge=el('td'),open=el('button','Bağlantı →','text-button');open.onclick=()=>{const x={kind:'edge',source:item.source,target:item.target};onSelect(x);show(x);};edge.append(open);tr.append(name,el('td',num(item.contacts,0)),edge);body.append(tr);}table.append(body);results.append(table);
        const paging=el('div',undefined,'detail-actions');const prev=el('button','← Önceki','secondary'),next=el('button','Sonraki →','secondary');prev.disabled=page===0;next.disabled=(page+1)*12>=r.total;prev.onclick=()=>{page--;render();};next.onclick=()=>{page++;render();};paging.append(prev,el('span',`${page+1} / ${Math.max(1,Math.ceil(r.total/12))}`),next);results.append(paging);
        results.append(note('Partner sayıları yerel 166.700 nöronluk anatomik grafiğe aittir; yalnızca çizilen 520 bağlantıyla sınırlı değildir.'));
      }catch(e){results.textContent=e.message;}
    }else{
      content.append(section('Kimlik',[['Body ID',data.id],['Tip',data.type],['Örnek / instance',data.instance],['Sınıf',data.cell_class],['Alt devre',data.circuit?.group||'Bu modelin dışında'],['Soma tarafı',data.annotations.somaSide],['Kök tarafı',data.annotations.rootSide],['Soma konumu (µm)',data.soma_um?.map(x=>num(x,3)).join(' / ')]]));
      const live=el('div',undefined,'detail-live');live.id='detail-live';content.append(live);tick(activity);
      if(data.circuit)content.append(note(roles[data.circuit.group]));
      content.append(section('Anatomik bağlantı özeti',[['Gelen partner',num(data.connectivity.incoming_partners,0)],['Giden partner',num(data.connectivity.outgoing_partners,0)],['Gelen sinaptik temas',num(data.connectivity.incoming_contacts,0)],['Giden sinaptik temas',num(data.connectivity.outgoing_contacts,0)]]));
      content.append(section('Nörotransmiter',[['Konsensüs',data.neurotransmitter],['Tahmin güveni',num(data.annotations.predicted_nt_confidence,5)],['Kaynak',data.dataset]]));
      content.append(note('Tip, sınıf ve tahminler kaynak veri alanlarıdır. Eksik alanlar “Veri yok” olarak gösterilir. Bireye özgü öğrenilmiş bir biyolojik işlev varsayılmaz.'));
    }
  }
  let activityModel=null;
  function tick(values,modelId=activityModel){activity=values||[];activityModel=modelId;const live=document.getElementById('detail-live');if(!live||!data)return;
    if(modelId==='flight-pretrained'){live.textContent='Uçuşta MaleCNS aktivite verisi yok.';return;}
    const text=n=>Number.isInteger(n?.circuit?.activity_index)?num(activity[n.circuit.activity_index],5):'Devre dışında';
    live.textContent=selection.kind==='node'?`Canlı model aktivitesi: ${text(data)}`:`Kaynak aktivitesi: ${text(data.source)} · Hedef: ${text(data.target)}`;
    if(selection.kind==='edge'&&data.model){
      const source=activity[data.source.circuit.activity_index];
      live.textContent+=activityModel===model?` · Girdi katkısı (2 × a × w): ${num(2*source*data.model.current_weight,7)}`:' · Model eşleştiriliyor…';
    }
  }
  document.getElementById('detail-close').onclick=()=>{host.classList.add('hidden');};
  document.querySelectorAll('[data-detail-tab]').forEach(b=>b.onclick=()=>{tab=b.dataset.detailTab;render();});
  document.getElementById('detail-download').onclick=()=>{if(!data)return;const blob=new Blob([JSON.stringify(data,null,2)],{type:'application/json'}),url=URL.createObjectURL(blob),a=el('a');a.href=url;a.download=selection.kind==='node'?`neuron-${selection.id}.json`:`connection-${selection.source}-${selection.target}.json`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};
  addEventListener('keydown',e=>{if(e.key==='Escape')host.classList.add('hidden');});
  return {show,tick,modelChanged:async id=>{model=id;if(selection?.kind==='edge'&&!host.classList.contains('hidden'))await show(selection,id);}};
}
