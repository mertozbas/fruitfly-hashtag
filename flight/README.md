> **Yeni dağıtım kullanıcıları:** [Güncel, taşınabilir kurulum ve kullanım rehberi](../docs/installation.md). Bu dosya ilk yerel geliştirme deneylerinin teknik kaydıdır; kişisel dosya yolları, koşu kimlikleri ve `rtk` komutları son kullanıcı kurulumu için gerekli değildir. Burada belirtilen yerel sonuç dosyaları dağıtıma dahil edilmez.

# MaleCNS ile kokulu hedefe uçuş

Neural Lab → **Davranış → Uçuş · beyin bağlı**. Hedef X/Y konumunu mm olarak
ayarla ve **Hedefi uygula** düğmesine bas. Sinek, gerçek anten konumlarından
örneklenen sentetik kokuya göre yönelir. **Gövde / Arena**, mouse ile kamera,
duraklatma, model seçimi, eğitim ve Δ Ağırlık aynı tam ekran UI'dadır.

## Kontrol yolu

```text
Fiziksel anten konumları → sentetik koku
→ ORN → ALPN → Kenyon → MBON (7.075 nöronluk MaleCNS alt ağı)
→ yapay yön okuması → sınırlandırılmış yön hızı
→ çevrimiçi konum/yön referansı → FlyBody hazır kanat politikası
→ kanat torkları + MuJoCo aerodinamiği → yeni anten konumları
```

Yürüyüş ve uçuş aynı `odor_policy.Policy` kodunu ve gerçek checkpoint'i kullanır.
Mevcut ağ `odor_brain` üzerinden de aynı isimlerle erişilebilir. Beyin uçuşun yönünü
seçer; kanat dengesi ve irtifa takibini [FlyBody kontrolcüsü](https://github.com/TuragaLab/flybody)
sağlar. Yön hedefi doğrudan hedef açısını gören başka bir kontrolcüden gelmez.
Sineğin qpos/qvel değerleri reset sonrasında elle taşınmaz; güncellenen şey
motor politikasına verilen referanstır. Dışarıdan uygulanan gövde kuvveti yoktur.

Nötr kalibrasyon: aynı checkpoint'in eşit koku girdisindeki okuması çıkarılır.
`yaw = clip(60 × clip(readout − neutral, −1, 1), −8, 8)` rad/s.
Bu yapay motor adaptörü, bir anatomik MBON→kanat bağlantısı keşfi değildir.
Girdi sentetik iki kanallı kokudur; reseptör/odor kimliği ya da fizyolojik spike
modeli değildir. Tam beyin veya biyolojik uçuş devresi emülasyonu yapılmaz.

## Fizik ve canlı veri

- FlyBody CGS birimleri cm/gram/s; UI konumu ve hızı mm'ye çevirir.
- Sabit referans ileri hızı 10 cm/s, irtifa 10 mm. Başlangıç havadadır;
  yerden kalkış, irtifa seçimi ve iniş bu deneyin kapsamında değildir.
- Hedef başarısı: XY uzaklığı <2 mm, geçerli uçuş durumu. Bölüm üst sınırı
  0,45 s; yere yaklaşma veya referanstan aşırı sapma sonlandırır.
- Fizik 0,05 ms, kanat kontrolü 0,2 ms, beyin/anten örnekleme 10 ms.
  Yaklaşık 218 Hz kanat hareketi yavaş çekimde gösterilir. Hedef oynatım 0,01×;
  gerçek oran RTF alanındadır. İzlenmeyen veya duraklatılan fizik ilerlemez.
- Canlı karede beyin checkpoint SHA-256'sı, devre kimliği, 7.075 hesaplanan yanıt,
  gerçek anten örnek konumları, beyin örnek zamanı, ham/nötr/uygulanmış okuma,
  yön hızı, motor politika kimliği ve kanat eylemi bulunur.
- Beyin paneli son fizik adımında kullanılan kararı gösterir; beyin örneği
  gövde zamanından en fazla 10 ms geridedir. Reset'in ilk karesinde karar hazır
  olabilir; `applied_to_physics=false` bunu ayırır. Sahte aktivite üretilmez.
- 4.826 konumlu soma ve 82.747 model bağlantısı aynı anatomik haritada kalır.
  Modele dahil olmayan iskeletler gri kalır. Eğitim yeni anatomik kenar oluşturmaz.
- Full HD 1920×1080, 4× MSAA; kamera, fizik duraklatılmışken de çalışır.
- Yürüyüş ve uçuş ayrı Python süreçlerindedir; yalnızca seçili davranış ilerler.
  Davranış değişimi önceki modeli, hedefi, fizik durumunu ve kamerayı korur.

## Eğitim

Uçuş seçiliyken **Yönelme ağını eğit** yeni bir anatomik alt ağ checkpoint'i
üretir ve altı uçuş hedefinde değerlendirir. Sentetik koku-yön örneklerinden
mevcut KC→MBON bağlantı çarpanları ve yapay yön okuması gözetimli öğrenilir.
Kanat politikası değişmez. Eğitim seçili checkpoint'in devamı değildir; aynı
anatomik başlangıçtan yeni deneydir. Eski kayıtlar korunur.

Tamamlanınca **Yeni modeli simülasyona al** ile uçuşa uygula; **Δ Ağırlık** ile
anatomik başlangıca göre değişimleri incele. Aynı model yürüyüşte de seçilebilir;
fizik testleri davranışa göre ayrı gösterilir. Test edilmemiş davranışın puanı
boş kalır. Tek eğitim işi ve 600 s üst sınır vardır. Uçuş değerlendirmesi aynı
işlem kimliğine `exec` ile geçer; iptal/zaman sınırı değerlendirmeyi de kapsar.

Doğrulanan yeni eğitim: `run-20260913T222316229102`, 3.000 adım, seed 42,
MSE 0,500215 → 0,005367; 57.614 mevcut bağlantı katsayısı değişti, yeni kenar 0;
altı uçuş hedefi 6/6, uçuş sınırı ihlali 0. Önceden bulunan 34 NPZ dosyası değişmedi.

## Kurulum ve test

```sh
rtk proxy uv sync --project flight --locked
rtk proxy .venv/bin/python flight/download_assets.py
rtk proxy ./ui.sh
# Kokuya yönelme seçili, eğitim işi boşta iken:
rtk proxy .venv/bin/python validate_flight_ui.py
# Canlı beyin bağlı uçuş sürerken:
rtk proxy .venv/bin/python validate_live_brain.py
# Belirtilen checkpoint'in uçuş ve nedensellik testleri:
rtk proxy flight/.venv/bin/python flight/evaluate_navigation.py --model models/odor_navigation/trained.npz --causal
```

NumPy/TensorFlow bağımlılıkları ayrı Python 3.11 ortamındadır; FlyBody Git sürümü
ve bağımlılıklar `uv.lock` ile sabitlenir. İndirilen grafik/ağırlıklar değiştirilmez.
TFP 0.16'nın eski Independent TypeSpec adı, 0.23'ün uyumlu çözücüsüne eşlenir.
Politikanın dağılım ortalaması kanonik eylemden yerel aktüatör sınırlarına çevrilir.

[Resmi Figshare v4](https://doi.org/10.25378/janelia.25309105.v4) kaynaklı iki arşiv
19,4 MB'dir. `data/flybody/manifest.json` dosya boyutlarını ve SHA-256 kayıtlarını
korur. Model, veri, ortam ve üretilen doğrulama dosyaları Git dışında kalır.

## Kanıtlar ve sınırlar

- `artifacts/lab/flight/checkpoints/e3928ec2fa60074b1c24dab8b76b46c3723fe7a2d7e8d51fbe1bdf92e8e2d087.json`:
  mevcut 6.000 adımlık ağ, altı önceden ayrılmış hedefte 6/6. Aynı iki hedef ve
  tohumda çıkış kapalıyken 0/2, ters çevrildiğinde 0/2. Diğer tüm kontrol ve fizik
  koşulları aynıdır. Beyin komutunun etkisi bu müdahalelerle doğrulanır.
- `models/lab_runs/run-20260913T222316229102/evaluation.json`:
  UI API'sinden başlatılan yeni eğitimin altı gerçek fizik değerlendirmesi.
- `artifacts/lab/flight/training-ui-validation.json`: eğitim, checkpoint yükleme,
  bağlantı değişimleri ve eski dosyaların korunması.
- `artifacts/lab/flight/ui-validation.json`: 11 API/fizik kontrolü; hedef/model
  değiştirme, duraklatma, üç mouse kamera hareketi ve yürüyüş durumunun korunması.
- `artifacts/lab/flight/live-brain-validation.json`: 20 veri kontrolü; tüm 7.075
  yanıt, konumlu bağlantılar, ağırlıklar, anatomik segmentler, zamanlar ve uygulanan
  yön komutu. İki NumPy/BLAS ortamındaki FP32 yeniden hesaplama için 1e-5 okuma
  toleransı kullanılır; yayımlanan motor eşlemesi kendi içinde 1e-12 ile sınanır.
  Tarayıcı görsel testi yapılmadı.

Bu küçük, kontrollü hedef kümesi genel uçuş başarısı ölçümü değildir. Yeni hedef,
hız, irtifa, türbülans veya tüm MaleCNS ağı için genelleme iddia edilmez.
Önceki hazır rota demosu `flight/validate.py` ile tekrar çalıştırılabilir;
`validation.json` ve başarısız #48 rota araştırması eski kanıt olarak korunur.
Çalışma günlüğü: `.runtime/flight-worker.log`.
