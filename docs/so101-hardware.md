# Gerçek SO-101: bağlantı ve devreye alma

Neural Lab'ın **Gerçek kol ↗** paneli fiziksel SO-101 follower'ı ve USB kameralarını
tanılamaya hazırlar. Motor konumlarını, sıcaklığı, voltajı ve mevcut tork durumunu
okur; kaydedilmiş kalibrasyonu motor belleğiyle karşılaştırır. Bilek ve sabit kamera
için ayrı gerçek RGB önizlemeleri sunar.

**Bağlantı tanılaması salt okunurdur; Kol kalibrasyonu ayrı bir yazma akışıdır.**
Sihirbaz, kol desteklenirken verdiğiniz onayla torku kapatır ve kalibrasyon
ayarlarını yazar. Hedef konumu göndermez, torku açmaz.
Simülasyondaki al ve yerleştir / tic-tac-toe modelleri henüz fiziksel kolda
devreye alınmadı. Donanım panelini açmak, ana ekrandaki beyni gerçek kola bağlamaz;
ana ekran simülasyonun sinir ağı hesabını göstermeye devam eder.

## 1. Kol bağlı değilken hazırlık

Kurulu Neural Lab çalışma dizininde:

```bash
.venv/bin/python tools/setup_so101_hardware.py
```

Komut `.runtime/hardware-venv` adında ayrı bir Python ortamı oluşturur. Bilimsel
`.venv` ortamını, eğitimleri ve modelleri değiştirmez. `uv` ve mevcut Python 3.12
ortamı kullanılır; ilk kurulumda internet gerekir. Bu bilgisayarda kurulum yapıldı.
Farklı bir bilgisayarda aynı komutla tekrarlanabilir. pipx kullanıyorsanız komutu
paketin uygulama ortamında değil, `fruitfly status` ile gördüğünüz **çalışma
dizininde**, bilimsel ortam kurulduktan sonra çalıştırın.

| Bağımlılık | Sabit sürüm | Görev |
| --- | --- | --- |
| pyserial | 3.5 | USB seri haberleşmesi |
| feetech-servo-sdk | 1.0.0 | STS3215 tanılaması ve sınırlı kalibrasyon yazımı |
| opencv-python-headless | 4.13.0.92 | USB görüntüsü, ChArUco lens / pano ölçümü |
| numpy | 2.2.6 | Kamera görüntü dizileri |

UI'da sağ üstten **Gerçek kol** panelini açın. **Sürücü ortamı hazır** ve varsa
yerel kalibrasyon dosyası görünür. **Envanteri yenile** yalnızca işletim sisteminin
USB aygıt listesini okur; seri port veya kamera açmaz.

## 2. Hazır olduğunuzda bağlanacak parçalar

1. SO-101 **follower** kolunu masaya sabitleyin. Hareket alanını boş bırakın.
2. Follower motor kartının USB kablosunu bilgisayara bağlayın. Motorları okumak
   için kolun kendi kitine uygun güç adaptörünü kullanın. Bu bağlantı ekranı
   mevcut tork durumunu değiştirmez; güç verildiğinde kolun fiziksel davranışı
   motorun mevcut ayarlarına bağlıdır.
3. Somun yuvalı adaptördeki **32×32 UVC bilek kameranın USB'sini** bağlayın.
4. Tic-tac-toe tahtasının tamamını ve çalışma alanını gören sabit bir üst / karşı
   kamera kullanın. Bilek kamerasının dar görüşü bütün tahtayı her pozda göremez.

İlk tanılama için leader kol gerekmez. Gerçek hareket aşamasında elle gösterim
toplamak gerekirse leader veya başka bir teleoperasyon aracı ayrıca kullanılabilir.
Kolun portunu başka bir LeRobot / teleoperasyon uygulamasında açık bırakmayın.

Montaj, follower / leader farkları ve kit kurulumu için
[resmî LeRobot SO-101 rehberi](https://huggingface.co/docs/lerobot/en/so101) kaynak
alınır. Çalışan, kalibre edilmiş bir kol için motor ID kurulumunu baştan çalıştırmayın.

## 3. Motorları yalnızca oku

1. Panelde **Envanteri yenile** düğmesine basın; follower'ın USB portunu seçin.
2. Kola ait kalibrasyon dosyasını seçin. Dosya adı ve SHA-256 özeti görünür.
3. **Motorları oku** düğmesine basın. Altı motorun ID 1–6 ve model kodu STS3215
   olarak okunması beklenir. Uyuşmazlıkta tanılama hata gösterir.
4. Konum, sıcaklık, voltaj ve mevcut tork durumunu inceleyin. Satırın üzerine
   geldiğinizde teknik eklem adı, ham enkoder, ham yük ve çalışma modu görünür.
5. **Devreye alma** sekmesinde dosya / motor kalibrasyonu karşılaştırmasını görün.

Kalibrasyon dosyaları şu yerlerde aranır:

```text
~/.cache/huggingface/lerobot/calibration/robots/so_follower/*.json
~/.cache/huggingface/lerobot/calibration/robots/so101_follower/*.json
```

Dosya geçerli olsa bile doğru kola ait olduğu henüz kanıtlanmış değildir. Kontrol;
motor ID, kayıtlı alt / üst limit ve homing offset eşleşmesini kapsar. Follower
kimliği, mekanik dişli oranı ve simülasyonla yön eşleşmesi ayrı ölçümlerdir.
Dosyaya veya motor belleğine otomatik düzeltme yazılmaz.

İlk beş eklemin konumu LeRobot derece ölçeği, gripper konumu yüzde ölçeğidir.
Homing offset motor tarafından uygulanır; yazılımda ikinci kez çıkarılmaz.
Dosya / motor eşleşmiyorsa UI derece yerine ham enkoder sayımını gösterir.
Aralık dışındaki değerler kırpılmaz. **Bu değerler doğrudan MuJoCo radyanlarına
çevrilip hareket komutu yapılamaz:** sıfır noktası ve yön eşleştirmesi gerekir.

## 4. Kameraları gör

Her kamera için bir aygıt indeksi seçip **Görüntüyü aç** düğmesine basın.
İndeksler işletim sistemine ve takılı aygıtlara göre değişir; `0` her zaman bilek
kamerası değildir. Görüntüden doğru aygıtı kontrol edin. Aynı indeks iki rol için
aynı anda açılamaz. macOS kamera izni isterse Python'u başlatan uygulamanın
kamera erişimini sistem ayarlarından açın.

1280×720 istenir; kamera farklı çözünürlük verirse **gerçekte alınan çözünürlük**
panelde yazılır. İşçi en fazla 8 kare/saniye üretir, panel yaklaşık 4 kez/saniye
yenilenir; cihaz ve işlem süresi bunu düşürebilir. Son kare 2 saniyeden eskiyse
canlı kabul edilmez. UVC'den derinlik görüntüsü uydurulmaz.
Paneldeki `ms` değeri son mesajın sunucuya gelişinden itibaren yaşıdır;
kameranın pozlama zamanını veya uçtan uca kontrol gecikmesini ölçmez.

**Durdur** seçilen kamerayı; **Tüm bağlantıları kapat** motor tanılamasını ve iki
kamerayı kapatır. Aktif motor kalibrasyonu varsa önce iptal / geri yükleme denenir.
Panel kapandığında da bağlantılar bırakılır. UI'dan 15 saniye
güncelleme gelmezse oturumlar otomatik kapanır; her oturum en fazla 10 dakikadır.
Bağlantıyı kapatmak **acil durdurma veya tork kapatma komutu değildir**. Uygulama
salt okuma sırasında torku değiştirmez; sihirbazda bırakılmış torku yeniden açmaz.
Fiziksel güç kesme imkânı ayrı tutulmalıdır.

## 5. UI üzerinden kol kalibrasyonu

Bu işlem standart SO-101 follower, ID 1–6 ve STS3215 içindir. Motor ID kurulumu,
dişli oranı değişikliği veya otomatik kol hareketi yapmaz. Başka bir uygulamanın
seri bağlantısını kapatın. Kol masaya sabit, kıskaç boş olmalı; tork bırakırken
kolu elinizle destekleyin. Bu fiziksel adımlar ekran başındaki operatör tarafından
yapılır; sihirbaz mekanik durakları kendiliğinden aramaz.

1. **Gerçek kol → Kol kalibrasyonu** sekmesini açın. USB portunu ve mevcut
   profili seçin; yeni kolsa **Yeni profil oluştur** ve bir kol adı kullanın.
2. **Yedekle ve başla** düğmesine basın. Altı motorun model ve ayarları okunur;
   orijinal dosyanın birebir içeriği, SHA-256 özeti, USB kimliği ve motor belleği
   diske kaydedilir. Yedek tamamlanmadan hiçbir motor yazımı yapılmaz.
3. Kolu destekleyin, üzerindeki yükü alın ve kutucuğu işaretleyip **Torku bırak**
   düğmesine basın. Motorlar serbest kalır; düşmesine izin vermeyin.
4. Eklemleri elle hareket aralıklarının ortasına getirin. 3D rehber nominal bir
   şemadır; canlı eklem pozu veya mekanik uygunluk kanıtı değildir. Kolu sabit
   tutup **Orta konumu kaydet** ile referansı ölçün.
5. Sırayla **taban, omuz, dirsek, bilek eğimi ve kıskaç** için iki hareket ucunu
   yavaşça elle tarayın. Mekanik durakları zorlamayın. Ekran alt / üst enkoder
   değerini ve örnek sayısını gösterir; iki ucun ölçüldüğünü her eklemde onaylayın.
   **Bilek dönüşü elle tam tur taranmaz:** LeRobot yaklaşımıyla 0–4095 kullanılır.
   Kamera kablosunu dolamayın.
6. Altı eklemin sonuç tablosunu inceleyin. **Doğrula ve kaydet** motor ayarlarını
   yazar, geri okuyup karşılaştırır, ardından profil dosyasını atomik olarak
   değiştirir. **Tork kapalı kalır.** Yeni oturum açıp **Motorları oku** ile dosya
   / motor eşleşmesini tekrar kontrol edin.

Her ölçülen eklem için en az 12 örnek, 300 sayımlık açıklık ve referansın iki
yönünde en az 50 sayım gerekir. Bunlar eksik ölçümü yakalayan yazılım eşikleridir;
mekanik hareket sınırlarını doğru taradığınızın otomatik kanıtı değildir.
Enkoder sarımı veya kararsız referans algılanırsa ilerleme engellenir.
LeRobot ile uyumlu referans sayımı 2047'dir; homing offset motorun içinde uygulanır.

### İptal, yedek ve kurtarma

**İptal et ve ayarları geri al**, bu oturum başlamadan önceki motor kalibrasyonunu
geri yükler; torku açmaz. Kaydetme, seri haberleşme veya dosya hatasında da aynı
geri yükleme yolu denenir. Dışarıdan değiştirilmiş profilin üzerine yazılmaz.
UI bağlantısı kaybolursa 15 saniyelik süre dolunca; süreç normal kapatılırsa veya
10 dakikalık oturum sınırı dolarsa da geri yükleme denenir.

USB kablosu çekilmişse veya güç kesilmişse motorlara geri yazmak mümkün olmayabilir.
**KURTARMA GEREKLİ** durumunda kolu destekleyip gücü güvenle kesin; bağlantıyı
düzelttikten sonra **Önceki yedekler → Seçili yedeğe dön** akışını kullanın.
Önce mevcut durum tekrar yedeklenir, sonra tork bırakma ve geri yükleme onayı alınır.
Yedek yalnızca aynı USB kimliği ve profil yoluyla eşleşirse kabul edilir.
USB kimliği kartı tanımlar; motorların başka kola taşınmadığını kendiliğinden kanıtlamaz.

Yedek ve sonuçlar yereldir:

```text
.runtime/hardware/motors/<oturum>/backup.json
.runtime/hardware/motors/<oturum>/status.json
.runtime/hardware/motors/<oturum>/candidate.json
```

**Yedek ve sonuç raporu** bağlantısı bu kayıtları açar. Yedek dosyası orijinal
kalibrasyonu birebir içerir; silmeyin. Tamamlanmış bir kaydı değiştirmek için yeni
oturum açılır. Geçmiş kayıtlar Git / dağıtım paketine dahil edilmez.

## 6. Kamera lensi ve masa referansı

### Lens ölçümü

1. Sağdaki önizlemeden doğru USB kamerayı açın. **Kamera kalibrasyonu** sekmesinde
   bilek / üst rolünü ve fiziksel kameraya vereceğiniz adı seçin. Görüntüden kimliği
   doğrulayın; odak ve lens ayarını sabitleyin.
2. **A4 pano indir** ile ChArUco SVG dosyasını indirin. A4'e **%100 / gerçek boyut**
   ile basın; "sayfaya sığdır" kullanmayın. Cetvelle 50 mm kontrol çizgisini ölçün.
   Pano 6×8 kare, kareler 20 mm, işaretler 14 mm ve sözlük `DICT_4X4_50`'dir.
   Panoyu düz, bükülmeyen bir yüzeye sabitleyin.
3. **Panoyu algıla** düğmesine basın. Algılanan köşeler gerçek önizlemede işaretlenir.
4. Panoyu farklı yatay / dikey konumlarda ve iki eksende farklı eğimlerde gösterin;
   her net pozda **Kareyi al** ile en az 18, en fazla 30 kare toplayın.
   Bulanık, küçük, eski veya önceki poza çok benzeyen kare reddedilir.
5. **Hesapla** ile lens matrisi ve bozulma katsayılarını hesaplayın. Her altıncı
   kare hesaplamanın dışında tutulup ayrı doğrulamada kullanılır. 18 karede
   15 hesap + 3 doğrulama; 24 karede 20 + 4 kullanılır.
6. RMS en fazla 0,8 px, ayrı kare hatalarının her biri en fazla 1,2 px olmalı;
   görüş alanı kapsamı, eğim çeşitliliği ve matris sınırları da kontrol edilir.
   Sonuçları / baskı ölçeğini doğrulayıp **Lens profilini kaydet** düğmesine basın.

Bu eşikler geçse bile baskı ölçeği ve doğru kamera seçimi operatörün doğrulamasına
bağlıdır. Lens / odak / görüntü çözünürlüğü değişirse ölçümü yenileyin.
Önceki profili **Profille aç** ile yüklemek, fiziksel kamera kimliği onayı ister;
çözünürlük uyuşmazsa geometri kullanılmaz. Kamera indeksi kalıcı cihaz kimliği değildir.

### Masa / robot referansı

Kaydedilmiş lens profili varken panoyu masaya sabitleyin. Önizlemede güncel pano
köşeleri ve koordinat eksenleri görünmelidir. **Masa / robot referansı** sekmesinde
güncel pano–kamera pozunu kaydedin. Pano koordinatı: başlangıç sol üst dış köşe,
X sağa, Y aşağı, Z bu ikisiyle sağ el sistemi oluşturur.

Robot tabanına göre pano pozunu gerçekten ölçtüyseniz ilgili kutuyu seçip
X / Y / Z'yi **mm**, roll / pitch / yaw değerlerini **derece** olarak girin.
Dönüş sırası `Rz(yaw) · Ry(pitch) · Rx(roll)`'dur. Altı alan da doldurulmalıdır;
ölçmediğiniz değerleri sıfır varsaymayın. Taban ölçümü olmadan yalnız pano–kamera
dönüşümü kaydedilir. Matrisler kayıt içinde metre kullanır:

```text
base_from_camera = base_from_board × inverse(camera_from_board)
```

**Bilek kamerası hareket edince bu pozu sabit dönüşüm olarak kullanamazsınız.**
Güncel pano görünürlüğü veya ayrıca doğrulanmış el–göz montaj kalibrasyonu gerekir.
Bu akış lensi ve görünen pano pozunu ölçer; `hand_eye_calibrated` ve
`physical_alignment_verified` alanlarını **false** bırakır. Robotun gerçek eklem
kinematiğiyle eşleştirme tamamlanmadan hareket izni verilmez. Üst kamera / pano
yerinden oynarsa onun pozu da yeniden ölçülmelidir.

RGB pano ölçümü bir derinlik sensörü değildir; küpün yüksekliği, kavrama ve düşme
algısı ayrıca doğrulanır. Lens kayıtları `.runtime/hardware/cameras/<rol>/<oturum>/`
altında `calibration.json`, köşe gözlemleri `observations.json`, masa kaydı
`workspace.json` olarak tutulur. Tam kamera kareleri bu ölçüm akışında diske kaydedilmez.

## 7. Simülasyondan gerçek harekete kalan işler

Bağlantı tanılamasından sonra gerçek koldan ölçüm alarak şu aşamalar tamamlanır:

| Aşama | Ölçüm / kabul koşulu |
| --- | --- |
| Eklem eşleştirmesi | Follower kimliği, eklem sırası, yön, sıfır, birim, hareket ve hız sınırları |
| Kamera geometrisi | Bilek / üst kamera kimliği, lens kalibrasyonu, kamera–robot ve masa koordinatları |
| Gerçek görsel gözlem | RGB'den kalibre edilmiş masa / nesne geometrisi; simülasyonun derinlik ve nesne konumu bilgisine bağımlılık kaldırılır |
| Kavrama / düşme | Görüntü ve ölçülen motor geri bildirimiyle güvenilir doğrulama; ham servo yükü tek başına başarı kanıtı sayılmaz |
| Kontrollü hareket | Zaman damgası, gecikme, hız / adım / çalışma alanı sınırları, gözlem kaybında durma, operatörün güç kesmesi |
| Görev doğrulaması | Önce kısa boşta hareket, sonra tek küp ve tek hücre; ardından düşme kurtarma ve tam oyun |

Bu dört son kontrol UI'da bilinçli olarak **bekliyor** görünür. Bunları tamamlandı
diye işaretleyen bir ayar yoktur; fiziksel gözlem adaptörü ve sınırlı motor yürütücüsü
gerçek ölçümlerle uygulanıp doğrulanmalıdır. `/api/hardware/motion` bu sürümde
daima `423` döndürür ve hedef kabul etmez.

Öğrenilmiş tic-tac-toe hamle ağı, doğrulanmış tahta gözlemi sağlandığında tekrar
kullanılabilir. Motor okuması simülasyonda öğrenildi: fiziksel deneme kaydı ve
gerektiğinde yeniden eğitim gerekir. Simülasyondaki başarı sayıları gerçek
kolun başarı sayıları değildir. Sineğe özgü koku, yürüme ve uçuş görevleri de
bir robot koluna doğrudan aynı hareket olarak aktarılamaz.

## Bağlantısız doğrulama

```bash
.venv/bin/python -m unittest discover -s tests -p test_hardware.py -v
.venv/bin/python -m unittest discover -s tests/scientific -p test_hardware_api.py -v
.runtime/hardware-venv/bin/python -m unittest discover -s tests/hardware -v
```

Testler sahte seri taşıma / süreçler ve bilinen kamera projeksiyonları kullanır;
fiziksel motoru veya kamerayı açmaz. Kurulu Feetech SDK'sıyla tam ölçüm / kayıt /
geri yükleme, yarım kalan EEPROM yazımı, dosya hatası, eski komutlar, bağlantı
kaybı ve 15 saniyelik gözetim süresi sınanır. Kamera testleri bilinen lens matrisini
geri elde etmeyi, ayrı kare hatalarını, pano köşelerini ve dönüşüm yönünü kontrol eder.
Tarayıcı kontrolü tüm donanım uçlarını sahte yanıtlarla değiştirir:

```bash
.runtime/dev-venv/bin/python tools/check_calibration_ui.py --base http://127.0.0.1:8772
```

Bu komut Playwright ve Chrome bulunan geliştirme ortamı ile ayrı bir test sunucusu
bekler; fiziksel kalibrasyon yapmaz. Standart LeRobot `connect(calibrate=False)`
çağrısı yapılandırma / tork yazabildiğinden kullanılmaz. Salt okuma yolu yalnızca
PING ve sınırlı READ; sihirbaz yolu ise açık adım onayıyla tork **kapatma**, mod,
EEPROM kilidi ve kalibrasyon kayıtlarına tek kullanımlık yazma izni verir.
Hedef konum, tork açma, ID değiştirme ve toplu motor yazımı seri sınırda reddedilir.

Yöntem kaynakları: [LeRobot SO-101 kalibrasyonu](https://huggingface.co/docs/lerobot/en/so101#calibrate),
[OpenCV lens kalibrasyonu](https://docs.opencv.org/4.13.0/dc/dbb/tutorial_py_calibration.html),
[ChArUco algılama](https://docs.opencv.org/4.13.0/df/d4a/tutorial_charuco_detection.html).

[← SO-101 simülasyonu](so101-local.md) · [Tic-tac-toe](tictactoe-local.md) · [Rehber dizini](README.md)
