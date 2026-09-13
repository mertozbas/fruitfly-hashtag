Neural Lab, mevcut yerel MaleCNS/FlyGym ortamının çalışma arayüzüdür.

```bash
cd /Users/macmert/fruitfly-hashtag
rtk proxy ./ui.sh
```

Adres: <http://127.0.0.1:8766/>. Sağ üstteki tam ekran düğmesini kullan; `Esc` tam ekrandan çıkar. Ana ekran sabit panellerden oluşur ve sayfa kaydırması yoktur. Masaüstü kullanımına göre tasarlandı (en az 1200×720 önerilir). Çok dar ekranlarda masaüstü çalışma alanının tamamı sığmayabilir.

Sol panelden hedef koordinatlarını değiştirip **Hedefi uygula** ile yeni bir bölüm başlat. **Duraklat / Devam et** fizik zamanını durdurur. Gövde/Arena kamera seçimleri ve gövde kamerası döndürme/yakınlaştırma kontrolleri gerçek MuJoCo render'ını değiştirir. Başarı, 1,5 mm hedef mesafesidir; başarı veya 3 saniye sonunda aynı hedef ve tohumla yeni bölüm başlar. Bu oturum sayacı tekrarlanan aynı koşulun sayacıdır; altı hedefli değerlendirme skorundan ayrıdır.

Her iki 3B görünümde sol tuşla sürükleme döndürür; sağ tuş veya Shift + sol sürükleme kaydırır; tekerlek yakınlaştırır. Canlı görüntüye çift tıklama veya ⌖ düğmesi kamerayı sıfırlar. Beynin dikey ekseni kontrolcü kurulmadan önce sabitlenir; kutuplarda ters dönme engellenir. Kamera hareketi fizik duraklatılmışken de çalışır.

Canlı gövde 1920×1080, 4× MSAA ve JPEG kalite 96 (4:4:4) ile üretilir. Ayrıca FlyGym'in `neuromechfly_fullsize_meshes_20260623a` özgün yüzeyleri kullanılır; 40 dosya yaklaşık 14 MB, resmî FlyGym önbelleğinde tutulur. Ayrıntılı model yalnızca çizim içindir: gövde pozları doğrulanmış fizik modelinden alınır, ayrıntılı model fizik adımı çalıştırmaz. Böylece görüntü kalitesi artırılırken kontrolcü ve çarpışma fiziği korunur. Çizim kare hızı cihaz yüküne bağlıdır; 1080p çözünürlük 60 FPS taahhüdü değildir. Kullanılan geometri dosyaları ve SHA-256 özetleri `artifacts/lab/render-assets.json` içindedir.

**Eğitimi başlat** seçili modeli değiştirmeden yeni bir koku deneyi başlatır. Adım sayısı 200–10.000, tohum 0–1.000.000 aralığındadır. Bu sürümde eğitim, sıfırdan başlatılan aynı anatomik devre üzerinde gözetimli taklittir; seçili checkpoint'i kaldığı yerden eğitmez. Eğitim sonrasında altı fizik koşulu otomatik değerlendirilir. Bir koşu en fazla 10 dakika çalışır; **Eğitimi durdur** ile erken sonlandırılabilir. Başarısız veya iptal edilmiş modeller seçilebilir listesine eklenmez.

Tamamlanınca **Yeni modeli simülasyona al** düğmesini kullan veya model listesinden seç. Eğitim öncesi model, ilk doğrulanmış model ve yeni koşular arasında geçiş yapabilirsin. Model değişimi yeni bölüm başlatır. Canlı görüntü, o anda seçilmiş kaydın politikasını kullanır; devam eden eğitimin ara ağırlıkları canlıya otomatik uygulanmaz.

Yeni model ve loglar `models/lab_runs/run-*/` altında tutulur. Her koşu kendi devre dosyaları, eğitim öncesi/sonrası checkpoint'i, `training.json`, TensorBoard verileri, `training.log`, `evaluation.json` ve `run.json` kaydına sahiptir. İlk `models/odor_navigation/` checkpoint'leri UI eğitimiyle değiştirilmez. `teach.sh` eski CLI akışını korur; onu ayrıca kullanırsan açık UI sunucusunu yeniden başlat.

Beyin paneli:

- Toplam 7.075 nöronun 4.826'sının soma konumu biliniyor ve gerçek MaleCNS koordinatında çiziliyor. 2.228 ORN dahil konumsuz nöronlar için sahte konum üretilmez; aktiviteleri katman göstergelerine dahil edilir.
- **Aktivite** rengi, aynı politika ileri geçişinden çıkan normalize etkinliktir. Sensörler ve motor kararı ile beraber güncellenir. Bu değer biyolojik spike veya voltaj değildir.
- **Δ Ağırlık**, kaydedilmiş modelin anatomik başlangıca göre bağlantı çarpanlarını gösterir. İlk iki katman sabittir; KC→MBON bağlantıları değişebilir. Görüntü yoğunluğunu sınırlamak için konumu bilinen hücreler arasında en güçlü 520 bağlantı çizilir. Çizgiler soma-to-soma gösterimidir, gerçek akson güzergâhı değildir.
- Bir noktaya tıkla: gerçek body ID, hücre tipi, soma koordinatı ve güncel aktiviteyi incele.
- Nörona veya bağlantıya tıklamak ayrıntı panelini açar. Yoğun bölgelerde **Nöron seç / Bağlantı seç** ile seçim türünü belirle. Ana sayfa sabit kalır, uzun kayıtlar yalnızca bu panelin içinde kayar.
- Nöron ayrıntıları 38 anotasyon alanını, bütün hücre düzeyi nörotransmiter tahmin alanlarını, taraf/konum bilgilerini ve gelen/giden partner ile temas sayılarını gösterir. **Bağlantılar** sekmesinde bütün yerel partnerler 12'li sayfalar halinde incelenebilir; partner veya bağlantı kaydına geçilebilir. Konumu bilinmeyen partnerin verisi açılır ancak 3B konumu uydurulmaz.
- Bağlantı ayrıntıları kaynak → hedef yönünü, anatomik temas sayısını, seçili modeldeki normalize başlangıç/güncel ağırlığını ve öğrenme çarpanını gösterir. **Kaynak alanları** sekmesi orijinal veri adlarını korur; boş alanlar “Veri yok” olarak gösterilir. ↓ ile açılan kayıt JSON olarak indirilebilir. Anatomi ve öğrenilmiş model ağırlığı ayrı niceliklerdir.
- Yüzey JRCFIB2022M anatomisidir. Brain paneli tam MaleCNS ağ dinamiği simülasyonu değildir; [model sınırları](SIMULATION.md) geçerlidir.

Metrikler gerçek simülasyon durumundan gelir: hedef mesafesi (mm), yatay hız (mm/s), fizik zamanı, adım ödülü, sol/sağ normalize koku ölçümü, dönüş komutu, temas sayısı ve gerçek süreye göre fizik hızı (×). Eğitim panelindeki başarı sabit altı hedefli testin sonucudur. Altı koşul genel başarı oranını ölçmek için yeterli değildir.

Arayüzün eğitim hattı 3.000 adım / seed 42 ile çalıştırıldı: yeni model 5/6 başarı, 0 devrilme. Orijinal iki checkpoint'in SHA-256 değeri değişmedi. Canlı API'de duraklatma, dururken hedef sıfırlama, yeni model yükleme, iki kamera, devam etme, girdi sınırları ve farklı origin'den yazmayı engelleme kontrol edildi. Sayısal aktivite kaydı politika çıktısıyla beş sensör koşulunda karşılaştırıldı. Kanıt: `artifacts/lab/validation.json`. İsteğe bağlı WebMCP araçları, destekleyen tarayıcılarda aynı API'yi kullanır; bu ortamda WebMCP yürütmesi ve kapsamlı tarayıcı görsel QA'sı doğrulanmadı.

Servis yalnızca `127.0.0.1:8766` üzerinde çalışır; uzak bağlantı, ücretli servis veya bulut kurulumu içermez. Tek fizik süreci ve tek eğitim işi vardır. Sekme arka planda olduğunda canlı veri sorgulaması durur; 30 saniye istemci kalmazsa fizik boşta bekler. Sunucuyu terminalde `Ctrl+C` ile kapat; simülasyon ve varsa eğitim süreci de sonlandırılır. Yeni kurulumda `rtk proxy uv sync --locked` kullan. Three.js 0.180.0, lisansı ve dosya özetleri `ui/vendor/` içinde yereldir; çalışma anında CDN gerekmez.

Sonraki deneyler, ilk UI değerlendirmesinden sonra ayrı ayrı doğrulanacak:

| Deney | Bugünkü durum | Gerekli sonraki çalışma |
| --- | --- | --- |
| Kokuya yönelme | UI'dan eğitim ve canlı yürütme hazır | Daha fazla tohum, hedef, koku alanı ve karıştırılmış bağlantı kontrolü |
| Kokudan kaçınma | Hazırlık listesi | Kaçınma öğreticisi, uzaklaşma başarı tanımı, ayrı checkpoint |
| Görsel yönelme | Hazırlık listesi | Görme gözlemleri, görsel devre/sensör kodlaması, görsel hedef görevi |
| Engel / arazi | Hazırlık listesi | Arazi ve temas gözlemleri, davranış hedefi, yeni motor değerlendirmesi |
| Uçuş / görmeyle uçuş | Kaynak araştırması yapıldı | FlyBody aerodinamik uçuş görevi ve ayrı uçuş politikası; ardından beyin–motor eşlemesi |

[FlyGym](https://neuromechfly.org/) mevcut yürüme, duyusal ve hiyerarşik kontrol altyapısını; [FlyBody](https://github.com/TuragaLab/flybody) uçuş, yürüyüş ve görmeyle uçuş RL görev örneklerini sağlıyor. Görev örneğinin bulunması, MaleCNS alt ağının bu davranışı öğrendiği anlamına gelmez. Hazırlıktaki görevler UI'da eğitimi başlatmaz; o sırada canlı koku deneyi çalışmaya devam eder.
