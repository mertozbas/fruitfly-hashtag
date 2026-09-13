> **Yeni dağıtım kullanıcıları:** [Güncel, taşınabilir kurulum ve kullanım rehberi](docs/training.md). Bu dosya ilk yerel geliştirme deneylerinin teknik kaydıdır; kişisel dosya yolları, koşu kimlikleri ve `rtk` komutları son kullanıcı kurulumu için gerekli değildir. Burada belirtilen yerel sonuç dosyaları dağıtıma dahil edilmez.

**Simülasyon ve ilk eğitim deneyi**

Bu ortamda NeuroMechFly gövdesi MuJoCo fiziğiyle yürür. MaleCNS verisinden çıkarılan koku devresinin basitleştirilmiş modeli, iki antenin sentetik koku ölçümünü dönüş komutuna çevirir. Eğitim öncesi ve sonrası aynı hedeflerde karşılaştırılır.

Canlı 3B sineği aç:

```bash
cd /Users/macmert/fruitfly-hashtag
rtk proxy ./sim.sh --policy trained
```

Bu komut macOS için MuJoCo'nun `mjpython` çalıştırıcısını kullanır. Fareyle kamerayı döndür/yakınlaştır. `Space` duraklatır, `R` yeni hedefle sıfırlar; pencereyi kapatmak durdurur. Başarı, devrilme veya dört simülasyon saniyesi sonunda yeni bölüm başlar. Canlı oturum 10 dakika sonra kendiliğinden kapanır; aynı komutla tekrar açılabilir.

Tarayıcıdaki kayıtlar ve karşılaştırma: <http://127.0.0.1:8765/simulation/>. Sunucu kapalıysa `rtk proxy ./run.sh` çalıştır. Bu sayfadaki videolar kayıtlı fizik simülasyonudur; canlı pencere `sim.sh` ile açılır. Videolar 5 kat yavaş oynatılır. Turuncu küre hedef, arena görüntüsü sabit üst kamera, yakın görünüm sineği izleyen kameradır.

**Yeniden öğret ve karşılaştır**

```bash
rtk proxy ./teach.sh --steps 3000 --seed 42
rtk proxy ./sim.sh --policy trained
```

`teach.sh` eğitimi çalıştırır, başlangıç/eğitim sonrası checkpoint'leri kaydeder, altı fizik testi yapar, yeni videoları ve sonuç sayfasını üretir. Önceki checkpoint'ler `models/odor_navigation/history/` altında saklanır. Eğitim adımları 1–10.000 ile sınırlıdır. İlk doğrulanan ayar 3.000 adım, seed 42'dir. Başka bir seed/ayar aynı başarıyı garanti etmez; yeni değerlendirme sonuçlarını kontrol et.

Tek tek komutlar:

```bash
rtk proxy .venv/bin/python odor_brain.py prepare
rtk proxy .venv/bin/python odor_brain.py train --steps 3000 --seed 42
rtk proxy .venv/bin/python evaluate_odor.py
rtk proxy ./sim.sh --policy untrained
rtk proxy ./sim.sh --policy teacher
rtk proxy .venv/bin/python fly_sim.py --policy trained --goal 12 -4 --seconds 2.5
```

Son komut yeni bir kayıt oluşturur; karşılaştırma sayfasının varsayılan videosunun üzerine yazar. Standart karşılaştırmayı yeniden üretmek için `evaluate_odor.py` kullan. Eğitim grafikleri: `rtk proxy .venv/bin/tensorboard --logdir models/odor_navigation/tensorboard --host 127.0.0.1 --port 6006`. Bu sunucuyu `Ctrl+C` ile durdur.

**Neyin eğitildiği**

Veriden seçilen yol:

```text
Sol/sağ antenin sentetik koku yoğunluğu
  → yapay duyusal kodlama
  → 2.228 ORN → 686 ALPN → 4.064 Kenyon hücresi → 97 MBON
  → öğrenilen motor okuma katmanı
  → sol/sağ CPG genliği
  → FlyGym yürüyüş kontrolcüsü → 42 eklem + 6 yapışma aktüatörü
  → MuJoCo gövdesi → yeniden anten ölçümü
```

7.075 nöronun kimlikleri MaleCNS v1.0 anotasyonlarından, ardışık katmanlar arasındaki kenarlar gerçek bağlantı tablosundan gelir. Tarafı bilinmeyen 411 ORN seçimin dışında bırakılır. `rootSide` duyusal kanal eşlemesinde kullanılır; soma konumu yerine geçmez.

İlk iki katmanın anatomik ağırlıkları sabittir. 61.210 mevcut KC→MBON kenarının etkisine pozitif, sınırlı çarpanlar uygulanır; motor çıkış katmanı da eğitilir. Anatomik maske dışına yeni kenar eklenmez. Orijinal Feather verileri ve ilk keşif matrisi değiştirilmez.

İlk doğrulanan koşu (3.000 adım, seed 42, MPS): ayrılmış örneklerde ortalama karesel hata 0,5002 → 0,00537; 57.614 mevcut bağlantının çarpanı değişti. Aynı altı fizik koşulunda başarı eğitim öncesi 0/6, eğitim sonrası 5/6; devrilme 0. Ortalama son hedef mesafesi 20,45 → 4,11 mm. `(10, 5)` mm hedefi, seed 12 koşusunda öğrenilen kontrolcü başarısız oldu. Bu küçük test genel başarı oranı tahmini değildir.

Eğitim **gözetimli taklittir**: elle yazılmış bir referans kontrolcünün, koku farkına verdiği dönüş yanıtlarından öğrenir. 2.048 sentetik örnek eğitimde, farklı rastgele tohumla oluşturulan 512 örnek doğrulamada kullanılır. Fizik testinde hedef koordinatları kontrolcüye verilmez; kontrolcü yalnızca iki koku yoğunluğunu alır. Konum/hedef mesafesi ortamın ödül ve değerlendirme hesabındadır. Altı hedef ve CPG başlangıç tohumları, optimizasyon örneklerine dahil değildir.

Fizik ortamı `gymnasium.Env` arayüzünü sağlar. PyTorch, Stable-Baselines3 ve TensorBoard kurulu; Gymnasium ortam denetimi ve kısa PPO eğitim/checkpoint yükleme kontrolü çalıştırılır. Bu PPO kontrolü ayrı bir küçük MLP'dir; MaleCNS eğitiminin sonucu olarak sunulmaz. Daha sonra ödülle öğrenme çalışmaları için aynı ortam kullanılabilir.

**Bilimsel sınırlar**

Bu ilk prototip, tam MaleCNS beynini veya taranan bireyin birebir dijital ikizini simüle etmez. Beyin verisi ile NeuroMechFly gövdesi farklı kaynaklardan gelir. Gövdeye aktarım, araştırılması gereken bir modelleme seçimidir.

Katmanlar ileri beslemeli, pozitif normalize edilmiş anatomik mesajlarla ve `tanh` etkinliğiyle çalışır. Uyarıcı/baskılayıcı sinaptik işaret, reseptör seçiciliği, gerçek zaman sabiti, spike, gecikme, geri beslemeli beyin devreleri ve nöromodülasyon modellenmez. Koku sinyali bütün aynı taraf ORN'lerine yayılır; farklı moleküller/gerçek reseptör ayarları yoktur. Motor okuma katmanı yapaydır. VNC ve kasların kontrolünü gerçek MaleCNS ağı yerine FlyGym'in hazır CPG/hibrid kontrolcüsü yürütür.

Bu nedenle sonuç, **MaleCNS kaynaklı bir alt ağın parametrelerini eğitip davranış farkını fizik simülasyonunda gösteren bir mühendislik deneyi** olarak yorumlanmalı. Biyolojik sineğin öğrendiği, tüm beyni emüle ettiğimiz veya bu anatomik ağın başka ağlardan üstün olduğu sonucu çıkarılamaz. Böyle bir iddia için fizyolojik dinamikler, biyolojik ödül/plastisite modeli, bağlantıları karıştırılmış kontroller, ek tohumlar ve gerçek deney karşılaştırmaları gerekir.

**Ortam ve kayıtlar**

Python 3.12; FlyGym 2.1.0, MuJoCo 3.9.0, PyTorch 2.14.0, Gymnasium 1.3.0, Stable-Baselines3 2.9.0, TensorBoard 2.21.0. Gerçek kurulu sürümler `uv.lock` ile sabitlenir. Yeni ortamda `rtk proxy uv sync --locked` yeterlidir; MaleCNS ham verisinin de `data/` altında bulunması gerekir.

Bu Mac'te PyTorch MPS kullanılabilir ve ilk alt devre eğitimi Metal üzerinde çalışır. MuJoCo fiziği CPU'da çalışır. CUDA/NVIDIA gerektiren MuJoCo Warp kurulmadı; macOS'ta aynı GPU fizik yolunu desteklediği varsayılmaz. Ücretli bulut, servis veya model çağrısı gerekmez.

- `models/odor_navigation/circuit.json`: veri kaynağı, seçim, kenarlar ve varsayımlar.
- `models/odor_navigation/body_ids.npz`: gerçek nöron kimlikleri.
- `models/odor_navigation/layer*.npz`: anatomiden çıkarılan sabit katmanlar.
- `models/odor_navigation/untrained.npz`, `trained.npz`: başlangıç ve eğitim sonrası modeller.
- `models/odor_navigation/training.json`: adımlar, hata, değişen katsayılar ve cihaz.
- `artifacts/simulation/evaluation.json`: bütün yörüngeler, sensörler, mesafeler ve başarılar.
- `artifacts/simulation/paths.png`: eğitim öncesi/sonrası yol karşılaştırması.
- `egitim.ipynb`: mevcut sonuçları inceleyen ve yeni eğitim başlatmaya örnek veren defter.

Kaynaklar: [FlyGym kurulumu](https://neuromechfly.org/installation/), [resmî dönüş kontrolcüsü](https://neuromechfly.org/tutorials/4d_turning_controller/), [MaleCNS verisi](https://male-cns.janelia.org/download/). FlyGym'in gövde ve CPG araçları NeLy-EPFL tarafından Apache-2.0 lisansıyla yayımlanır.
