# Gerçek SO-101: bağlantı ve devreye alma

Neural Lab'ın **Gerçek kol ↗** paneli fiziksel SO-101 follower'ı ve USB kameralarını
tanılamaya hazırlar. Motor konumlarını, sıcaklığı, voltajı ve mevcut tork durumunu
okur; kaydedilmiş kalibrasyonu motor belleğiyle karşılaştırır. Bilek ve sabit kamera
için ayrı gerçek RGB önizlemeleri sunar.

**Bu sürüm salt okuma aşamasındadır.** Fiziksel kola hedef, tork veya kalibrasyon
yazmaz. Simülasyondaki al ve yerleştir / tic-tac-toe modelleri henüz fiziksel kolda
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
| feetech-servo-sdk | 1.0.0 | STS3215 kayıtlarının okunması |
| opencv-python-headless | 4.13.0.92 | USB kamera görüntüsü |
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
kamerayı kapatır. Panel kapandığında da bağlantılar bırakılır. UI'dan 15 saniye
güncelleme gelmezse oturumlar otomatik kapanır; her oturum en fazla 10 dakikadır.
Bağlantıyı kapatmak **acil durdurma veya tork kapatma komutu değildir**. Uygulama
torku açmadığı gibi kapatmaz; fiziksel güç kesme imkânı ayrı tutulmalıdır.

## 5. Simülasyondan gerçek harekete kalan işler

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

Testler sahte seri taşıma / süreçler kullanır; fiziksel motoru veya kamerayı açmaz.
Kurulu Feetech SDK'sının yazma çağrılarının seri sınıra ulaşmadan reddedildiği de
sınanır. Standart LeRobot `connect(calibrate=False)` çağrısı yapılandırma / tork
yazabildiğinden bu tanılama yolunda kullanılmaz. Seri sınır yalnızca altı motor
ID'sine PING ve sınırlı READ paketlerine izin verir.

[← SO-101 simülasyonu](so101-local.md) · [Tic-tac-toe](tictactoe-local.md) · [Rehber dizini](README.md)
