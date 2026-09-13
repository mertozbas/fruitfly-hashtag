> **Yeni dağıtım kullanıcıları:** [Güncel, taşınabilir kurulum ve kullanım rehberi](docs/usage.md). Bu dosya ilk yerel geliştirme deneylerinin teknik kaydıdır; kişisel dosya yolları, koşu kimlikleri ve `rtk` komutları son kullanıcı kurulumu için gerekli değildir. Burada belirtilen yerel sonuç dosyaları dağıtıma dahil edilmez.

Neural Lab, mevcut yerel MaleCNS/FlyGym ortamının çalışma arayüzüdür.

```bash
cd /Users/macmert/fruitfly-hashtag
rtk proxy ./ui.sh
```

Adres: <http://127.0.0.1:8766/>. Sağ üstteki tam ekran düğmesini kullan; `Esc` tam ekrandan çıkar. Ana ekran sabit panellerden oluşur ve sayfa kaydırması yoktur. Masaüstü kullanımına göre tasarlandı (en az 1200×720 önerilir). Çok dar ekranlarda masaüstü çalışma alanının tamamı sığmayabilir.

**Beyin ile uçuş:** **Davranış → Uçuş · beyin bağlı** seç. İki fiziksel anten konumundaki sentetik koku aynı 7.075 nöronluk alt ağa girer. Ağın yön kararı FlyBody'nin kanat kontrolcüsüne referans olur; sağdaki nöronlar ve bağlar son kullanılan beyin hesabını gösterir. **Hedefi uygula**, model seçimi, **Yönelme ağını eğit**, yeni modeli yükleme ve Δ Ağırlık çalışır. Eğitim sonrası altı uçuş hedefi değerlendirilir. Kanat politikası sabit kalır; bu, tam biyolojik beyin uçuş emülasyonu veya yerden kalkış eğitimi değildir. [Kontrol yolu, eğitim ve kanıtlar](flight/README.md).

Koku deneyinde, sol panelden hedef koordinatlarını değiştirip **Hedefi uygula** ile yeni bir bölüm başlat. **Duraklat / Devam et** fizik zamanını durdurur. Gövde/Arena kamera seçimleri ve gövde kamerası döndürme/yakınlaştırma kontrolleri gerçek MuJoCo render'ını değiştirir. Başarı, 1,5 mm hedef mesafesidir; başarı veya 3 saniye sonunda aynı hedef ve tohumla yeni bölüm başlar. Bu oturum sayacı tekrarlanan aynı koşulun sayacıdır; altı hedefli değerlendirme skorundan ayrıdır.

Her iki 3B görünümde sol tuşla sürükleme döndürür; sağ tuş veya Shift + sol sürükleme kaydırır; tekerlek yakınlaştırır. Canlı görüntüye çift tıklama veya ⌖ düğmesi kamerayı sıfırlar. Beynin dikey ekseni kontrolcü kurulmadan önce sabitlenir; kutuplarda ters dönme engellenir. Kamera hareketi fizik duraklatılmışken de çalışır.

Canlı gövde 1920×1080, 4× MSAA ve JPEG kalite 96 (4:4:4) ile üretilir. Ayrıca FlyGym'in `neuromechfly_fullsize_meshes_20260623a` özgün yüzeyleri kullanılır; 40 dosya yaklaşık 14 MB, resmî FlyGym önbelleğinde tutulur. Ayrıntılı model yalnızca çizim içindir: gövde pozları doğrulanmış fizik modelinden alınır, ayrıntılı model fizik adımı çalıştırmaz. Böylece görüntü kalitesi artırılırken kontrolcü ve çarpışma fiziği korunur. Çizim kare hızı cihaz yüküne bağlıdır; 1080p çözünürlük 60 FPS taahhüdü değildir. Kullanılan geometri dosyaları ve SHA-256 özetleri `artifacts/lab/render-assets.json` içindedir.

**Eğitimi başlat** seçili modeli değiştirmeden yeni bir koku deneyi başlatır. Adım sayısı 200–10.000, tohum 0–1.000.000 aralığındadır. Bu sürümde eğitim, sıfırdan başlatılan aynı anatomik devre üzerinde gözetimli taklittir; seçili checkpoint'i kaldığı yerden eğitmez. Eğitim sonrasında seçilen davranışa ait altı fizik koşulu otomatik değerlendirilir. Bir koşu en fazla 10 dakika çalışır; **Eğitimi durdur** ile erken sonlandırılabilir. Başarısız veya iptal edilmiş modeller seçilebilir listesine eklenmez.

Tamamlanınca **Yeni modeli simülasyona al** düğmesini kullan veya model listesinden seç. Eğitim öncesi model, ilk doğrulanmış model ve yeni koşular arasında geçiş yapabilirsin. Model değişimi yeni bölüm başlatır. Canlı görüntü, o anda seçilmiş kaydın politikasını kullanır; devam eden eğitimin ara ağırlıkları canlıya otomatik uygulanmaz.

Yeni model ve loglar `models/lab_runs/run-*/` altında tutulur. Her koşu kendi devre dosyaları, eğitim öncesi/sonrası checkpoint'i, `training.json`, TensorBoard verileri, `training.log`, `evaluation.json` ve `run.json` kaydına sahiptir. İlk `models/odor_navigation/` checkpoint'leri UI eğitimiyle değiştirilmez. `teach.sh` eski CLI akışını korur; onu ayrıca kullanırsan açık UI sunucusunu yeniden başlat.

Beyin paneli:

- Toplam 7.075 nöronun 4.826'sının soma konumu biliniyor ve gerçek MaleCNS koordinatında çiziliyor. 2.228 ORN dahil konumsuz nöronlar için sahte konum üretilmez; aktiviteleri katman göstergelerine dahil edilir.
- **Aktivite** rengi, aynı politika ileri geçişinden çıkan normalize etkinliktir. Sensörler ve motor kararı ile beraber güncellenir. Uçuşta son 10 ms beyin kararının örnek zamanı gösterilir; bu karar 0,2 ms aralıklı kanat politikasına yön referansı verir. Bu değer biyolojik spike veya voltaj değildir.
- **Δ Ağırlık**, kaydedilmiş modelin anatomik başlangıca göre bağlantı çarpanlarını gösterir. İlk iki katman sabittir; KC→MBON bağlantıları değişebilir. Konumu bilinen uçlara sahip 82.747 bağlantı verisi erişilebilirdir (22.063 ALPN→KC, 60.684 KC→MBON). Varsayılan **Sade · 520** görünümü önceki sürümdeki gibi her katmanın en güçlü 260 anatomik bağını çizer. Δ Ağırlık modunda en çok değişen 520 bağ seçilir. **Nöronun bağları**, son seçilen konumlu nöronun tüm giriş ve çıkışlarını; **Tüm bağlar**, tüm konumlu bağlantıları gösterir. Seçili bağlantı her görünümde ayrıca korunur ve sarı vurgulanır. Yeni anatomik bağlantı yaratılmaz. Sayaç, bu konumlu bağlantılarda %1 üzerinde değişen çarpanları sayar; eğitim raporundaki tüm KC→MBON değişim sayısından farklı olabilir. Çizgiler soma-to-soma gösterimidir, gerçek akson güzergâhı değildir.
- Bağlantı parlaklığı, hedefin `tanh` öncesi girdisine gerçek katkı olan `2 × kaynak yanıtı × mevcut ağırlık` değerinden gelir. Ölçek kareler ve modeller arasında sabittir: `log(1 + 99 × min(1, katkı)) / log(100)`. **Sinyal eşiği** yalnızca görünümü filtreler; nöronlara, fizik hesabına veya eğitime müdahale etmez. Sıfır katkılı bağlar soluk temel çizgi olarak kalır; sıfırdan büyük sinyal eşiği altındakileri gizler. Çizgiler ve küçük nöron noktaları normal alfa karışımıyla çizilir; üst üste ışık toplayan parlama ve geniş nokta haleleri kaldırılmıştır. Nöronlar 0–1 sürekli model yanıtına göre parlar; görselde yapay spike veya zamana bağlı rastgele yanıp sönme yoktur.
- **Parlaklık**, canlı aktivitenin renk vurgusunu %0–100 arasında ayarlar; varsayılan %30. En düşük ayarda bile temel bağlantı çizgileri ve seçili bağlantı görünür kalır. Aktivite ve Δ Ağırlık görünümlerinde çalışır. Seçim tarayıcıda saklanır; model hesabı, bağlantı ağırlıkları ve sinyal eşiği değişmez.
- **Anatomi**, `8765/index.html` haritasındaki aynı 28 doğrulanmış SWC iskeletini ve CNS yüzeyini kullanır. **Koku devresi / Tüm CNS** kamera kapsamını değiştirir. Bu 28 iskeletin üçü çalışan modele dahildir; diğerleri gri gösterilir ve aktivitesi hesaplanmaz. Model üyesi iskelet tek nöron yanıtıyla renklenir; bu renk akson boyunca ölçülmüş yayılım değildir. İskeletlere tıklayarak kayıtları açabilirsin.
- Her canlı kare model ID, checkpoint SHA-256, devre kimliği, fizik zamanı ve kare numarası taşır. Ağırlıklar bu kimliklerle eşleşmeden bağlantı parlaması yapılmaz. Duraklama ve kesilen akış ayrıca etiketlenir; kesilen akışta son kare korunur.
- Bir noktaya tıkla: gerçek body ID, hücre tipi, soma koordinatı ve güncel aktiviteyi incele.
- Nörona veya bağlantıya tıklamak ayrıntı panelini açar. Yoğun bölgelerde **Nöron seç / Bağlantı seç** ile seçim türünü belirle. Ana sayfa sabit kalır, uzun kayıtlar yalnızca bu panelin içinde kayar.
- Nöron ayrıntıları 38 anotasyon alanını, bütün hücre düzeyi nörotransmiter tahmin alanlarını, taraf/konum bilgilerini ve gelen/giden partner ile temas sayılarını gösterir. **Bağlantılar** sekmesinde bütün yerel partnerler 12'li sayfalar halinde incelenebilir; partner veya bağlantı kaydına geçilebilir. Konumu bilinmeyen partnerin verisi açılır ancak 3B konumu uydurulmaz.
- Bağlantı ayrıntıları kaynak → hedef yönünü, anatomik temas sayısını, seçili modeldeki normalize başlangıç/güncel ağırlığını ve öğrenme çarpanını gösterir. **Kaynak alanları** sekmesi orijinal veri adlarını korur; boş alanlar “Veri yok” olarak gösterilir. ↓ ile açılan kayıt JSON olarak indirilebilir. Anatomi ve öğrenilmiş model ağırlığı ayrı niceliklerdir.
- Yüzey JRCFIB2022M anatomisidir. Brain paneli tam MaleCNS ağ dinamiği simülasyonu değildir; [model sınırları](SIMULATION.md) geçerlidir.

Alt sırada **Metrikler / Beyin analizleri** sekmeleri aynı alanı paylaşır; ilk açılış mevcut metrik görünümünü korur. Beyin analizlerinde:

- **Anatomik konum:** gerçek CNS yüzeyinin X/Z projeksiyonu ve konumu bilinen devrenin sınır kutusu; seçim yapıldığında nöronun konumu ve varsa kaynak `somaNeuromere` anotasyonu. Dört çubuk anatomik bölge sınırı değil, ORN/ALPN/Kenyon/MBON devre aşamalarının tüm nöronlar üzerinden ortalama yanıtlarıdır. Üzerine gelince konumlu/konumsuz ve yanıt veren nöron sayıları görünür. Yürüyüşte CPG sol/sağ sürüşü, uçuşta uygulanan yön hızı son beyin kararından gelir; bunlar VNC nöron aktivitesi değildir.
- **Aktivite haritası:** 48×32 X/Z hücrelerinde, Y boyunca projekte edilmiş konumlu nöronların ortalama yanıtı. Ölçek sabit 0–1, boş hücre veri yok demektir. Sıcaklık ölçümü veya tüm beynin aktivite haritası değildir.
- **Saydam kesit:** aynı gerçek koordinatlar üzerinde Y ekseninde tüm derinlik ya da 80/30/10 µm kalınlık. Kaydırıcı dilim merkezini değiştirir. Dilim dışındaki noktalar silik referans olarak kalır. Bu anatomik bir projeksiyondur, tıbbi X-ray değildir.

Canlı doğrulama komutu: `rtk proxy .venv/bin/python validate_live_brain.py`. Çalışan checkpoint ile 7.075 yanıt, bütün konumlu bağlantı ağırlıkları/katkıları, 28 iskeletin tüm segmentleri ve gövde ile beyin zaman eşlemesi karşılaştırılır. Sonuç `artifacts/lab/live-brain-validation.json` içine yazılır. Bu kontrol tarayıcı görsel QA'sı değildir.

Yerel Git deposu `main` dalındadır; ilk çalışan UI sürümü `32c4a4b` commit'i ile korunur. Remote eklenmedi ve push yapılmadı. Kod, UI, belgeler ve bağımlılık kilidi sürümlenir; büyük anatomi verileri, üretilen görseller, Python ortamı ve `models/` arşivleri Git dışında mevcut klasörlerinde kalır. Git, bu model/veri klasörlerinin yedeği değildir.

Metrikler gerçek simülasyon durumundan gelir: hedef mesafesi (mm), yatay hız (mm/s), fizik zamanı, adım ödülü, sol/sağ normalize koku ölçümü, dönüş komutu, temas sayısı ve gerçek süreye göre fizik hızı (×). Eğitim panelindeki başarı sabit altı hedefli testin sonucudur. Altı koşul genel başarı oranını ölçmek için yeterli değildir.

Arayüzün eğitim hattı 3.000 adım / seed 42 ile çalıştırıldı: yeni model 5/6 başarı, 0 devrilme. Orijinal iki checkpoint'in SHA-256 değeri değişmedi. Canlı API'de duraklatma, dururken hedef sıfırlama, yeni model yükleme, iki kamera, devam etme, girdi sınırları ve farklı origin'den yazmayı engelleme kontrol edildi. Sayısal aktivite kaydı politika çıktısıyla beş sensör koşulunda karşılaştırıldı. Kanıt: `artifacts/lab/validation.json`. İsteğe bağlı WebMCP araçları, destekleyen tarayıcılarda aynı API'yi kullanır; bu ortamda WebMCP yürütmesi ve kapsamlı tarayıcı görsel QA'sı doğrulanmadı.

Servis yalnızca `127.0.0.1:8766` üzerinde çalışır; uzak bağlantı, ücretli servis veya bulut kurulumu içermez. Tek eğitim işi ve aynı anda ilerleyen tek davranış vardır. Yürüyüş ile uçuş ayrı Python süreçlerindedir; seçilmeyen davranış duraklatılarak korunur. Sekme arka planda olduğunda canlı veri sorgulaması durur; 30 saniye istemci kalmazsa fizik boşta bekler. Sunucuyu terminalde `Ctrl+C` ile kapat; simülasyon ve varsa eğitim süreci de sonlandırılır. Yeni kurulumda `rtk proxy uv sync --locked` kullan. Three.js 0.180.0, lisansı ve dosya özetleri `ui/vendor/` içinde yereldir; çalışma anında CDN gerekmez.

Sonraki deneyler, ilk UI değerlendirmesinden sonra ayrı ayrı doğrulanacak:

| Deney | Bugünkü durum | Gerekli sonraki çalışma |
| --- | --- | --- |
| Kokuya yönelme | UI'dan eğitim ve canlı yürütme hazır | Daha fazla tohum, hedef, koku alanı ve karıştırılmış bağlantı kontrolü |
| Kokudan kaçınma | Hazırlık listesi | Kaçınma öğreticisi, uzaklaşma başarı tanımı, ayrı checkpoint |
| Görsel yönelme | Hazırlık listesi | Görme gözlemleri, görsel devre/sensör kodlaması, görsel hedef görevi |
| Engel / arazi | Hazırlık listesi | Arazi ve temas gözlemleri, davranış hedefi, yeni motor değerlendirmesi |
| Uçuş | MaleCNS koku yönü → FlyBody kanat kontrolü; canlı aktivite, eğitim ve 6/6 hedef doğrulandı | Daha geniş hedef/tohum koşulları, irtifa/hız kontrolü ve biyolojik motor devre araştırması |
| Görmeyle uçuş | Kaynak araştırması yapıldı | Görsel politika ve görev entegrasyonu |

[FlyGym](https://neuromechfly.org/) mevcut yürüme, duyusal ve hiyerarşik kontrol altyapısını; [FlyBody](https://github.com/TuragaLab/flybody) uçuş, yürüyüş ve görmeyle uçuş RL görev örneklerini sağlıyor. Görev örneğinin bulunması, MaleCNS alt ağının bu davranışı öğrendiği anlamına gelmez. Hazırlıktaki görevler UI'da eğitimi başlatmaz; o sırada seçili canlı davranış çalışmaya devam eder.
