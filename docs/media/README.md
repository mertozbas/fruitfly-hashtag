# Görseller, videolar ve kökenleri

**Buradaki UI ve sinek görüntüleri gerçek uygulama / fizik çıktılarıdır.**
İlk ekranlar 14 Eylül 2026'da, aşağıda belirtilen araştırma ekranları 26 Eylül
2026'da Chrome sekmelerinden alındı. Görüntülere sonradan
sonuç, nöron, sayı veya model aktivitesi eklenmedi. Hero ve akış çizimi açıklayıcı
SVG şemalarıdır; anatomik ölçüm gibi sunulmaz.

[Rehber dizini](../README.md) · [Deney sonuçları](../experiments.md) · [Lisans bildirimleri](../../THIRD_PARTY_NOTICES.md)

| Dosya | Kaynak ve gösterdiği şey |
| --- | --- |
| [hero.svg](hero.svg) | Repo için çizilmiş tipografik kapak ve temsili devre noktaları; anatomi değil |
| [pipeline.svg](pipeline.svg) | Kaynak → devre → eğitim → fizik ilişkisini gösteren şema |
| [neural-lab.jpg](neural-lab.jpg) | Yerel 8766 UI; yürüyüş, anatomik konum ve model analizleri |
| [anatomy-atlas.jpg](anatomy-atlas.jpg) | Yerel 8765 keşif sayfası; MaleCNS 28 SWC + JRCFIB2022M yüzeyi, kimlik renkleri |
| [flight-lab.jpg](flight-lab.jpg) | Ayrı 8772 UI; yerelde oluşturulmuş başlangıç modeliyle uçuş |
| [learning-delta.jpg](learning-delta.jpg) | Aynı oturum; Δ Ağırlık ve kaydedilmiş öğrenme eğrisi |
| [neuron-inspector.jpg](neuron-inspector.jpg) | DNa02 / body 523769 anatomik kaydı; çalışan alt devrenin dışında |
| [walking-comparison.mp4](walking-comparison.mp4) / [GIF](walking-comparison.gif) | Yeni gerçek yürüyüş kayıtları; solda önce, sağda sonra, 0,2× hız |
| [flight.mp4](flight.mp4) / [GIF](flight.gif) | Yeni gerçek beyne bağlı uçuş; 720p kaynak, 0,03× hız |
| [experiments.json](experiments.json) | Kısaltılmış ölçüm raporları ve kaynak / checkpoint SHA256 kayıtları |
| [manifest.json](manifest.json) | Görsel dosyaların boyutları ve SHA256 özetleri |

## Video işlemleri

Yürüyüşte iki 640×480 arena kaydı 384×288'e ölçeklenip yan yana birleştirildi.
Başarılı koşu sonlandıktan sonra sağdaki son kare tutulur; soldaki kayıt sürer.
GIF 10 FPS'e indirildi. Uçuş MP4'ü 1280×720 / 30 FPS; GIF 640×360 / 8 FPS.
GIF'lerde palet azaltımı uygulanır. Fizik sonucu veya model hesabı değiştirilmez.
Tam kaynak kayıtları çalışma dizinindedir; küçük gösterim dosyaları repodadır.

## Tekrar üretim

[tools/record_media.py](../../tools/record_media.py) kurulu bilimsel ortamın
kendi modelini okur; checkpoint yazmaz. Yürüyüşte iki modeli aynı hedefte çalıştırır,
uçuşta kullanılan motor adaptörüyle gerçek MuJoCo kareleri üretir. Komutlar ve
FFmpeg birleştirmesi [geliştirici rehberindedir](../development.md#medya-uretimi).

UI görüntüleri programatik olarak çizilmiş taklitler değil, tarayıcı ekran
kayıtlarıdır. Farklı donanım, kamera, paket veya hedef aynı piksel çıktısını garanti
etmez. Görsellerdeki MSE eğitim ölçümüdür; başlıkta görülen canlı oturum sayısı
çok hedefli benchmark değildir. İlk başlangıç modelinin test skoru boş olabilir.

## Atıf ve lisans

UI ve özgün şemalar Hashtag Neural Lab projesinden, MIT lisanslıdır. Anatomik
görünümler [MaleCNS v1.0](https://male-cns.janelia.org/download/) verisinden
uyarlanmıştır (**CC BY 4.0**); yüzey kaynağı
[navis-flybrains / JRCFIB2022M](https://github.com/navis-org/navis-flybrains).
Yürüyüş gövdesi [NeuroMechFly / FlyGym](https://neuromechfly.org/), uçuş gövdesi ve
politikası [FlyBody](https://github.com/TuragaLab/flybody) kaynaklıdır. Render
alınması dış kaynakları projenin MIT lisansına dönüştürmez. İlgili kod, veri ve
politika lisansları [üçüncü taraf bildirimlerinde](../../THIRD_PARTY_NOTICES.md)
ayrı belirtilmiştir. Araştırma ekipleri bu proje için onay veya ortaklık vermiş
olarak gösterilmez.

## Yerel SO-101 görüntüsü

`so101-lab.jpg`, yerel MuJoCo ve tarayıcı arayüzünden alınmış gerçek ekran
görüntüsüdür. Model `31ed4107db97…`, tohum 9000; robot hedef konumunu
anatomik ağın öğrenilmiş okuması üretir. Nesne temasla taşınır. Bu görüntü
fiziksel robot kaydı değildir. Ayrıntılar: [SO-101 rehberi](../so101-local.md).

`so101-wrist.png`, aynı yerel laboratuvarın bilek kamerası ve **Tekrarla**
kontrolünü gösteren değiştirilmemiş tarayıcı ekran görüntüsüdür. Model
`cd1d23a81c54…`; resmî 32×32 UVC somun yuvalı adaptör modelidir. Küçük pencere
hareketli bilek gözünün karar karesidir, büyük
pencere bağımsız seyirci kamerasıdır. Görüntü duraklatılmış başlangıç durumunu
gösterir; yerleştirme başarısı ayrı fizik testleriyle ölçülür.

`tictactoe-lab.png`, aynı gün 8766 adresindeki Chrome arayüzünden alınmış,
1728×1050 boyutunda değiştirilmemiş ekran görüntüsüdür. Model `cd704b86be32…`;
SO-101 X işaretli 30 mm eğitim küpünü taşıyor. Bilek penceresi motor girdisinin
kamera karesi, sağdaki aktivite aynı checkpoint'in motor ileri hesabıdır.
Orijinal 240 mm tahta korunur; O sanal rakiptir. Kayıt gerçek donanım videosu değildir.

## SO-101 / XOX araştırma yayını · 26 Eylül 2026

Yeni ekranlar gerçek `http://127.0.0.1:8766/` arayüzünden, `local-tictactoe-robot-seed53`
modeliyle alındı. Checkpoint SHA256:
`cd704b86be32b9090222ffc9c5f2b57fd2982540b226633d002cfb2eeed11395`.
Mevcut model yeni bir yerel **simülasyon gösteriminde** açıldı; yeniden eğitim yapılmadı.
Simülasyon 10,55 saniyede, ilk küpün kavrama aşamasında duraklatıldı.
Değerlendirme penceresindeki sayılar modelin kayıtlı deney raporundandır.
Aynı strateji sonuçları 26 Eylül'de ayrıca çevrimdışı yeniden değerlendirildi.

| Dosya | Kaynak ve kapsam |
| --- | --- |
| [XOX ve metrikler](research/xox-live-metrics.jpg) | MuJoCo sahnesi, motor hesabı, telemetri ve kayıtlı öğrenme eğrisi |
| [Beyin analizleri](research/xox-brain-analysis.jpg) | Aynı duraklatılmış sahnede anatomik konum, aktivite haritası ve kesit |
| [XOX değerlendirmesi](research/xox-evaluation.jpg) | Tahta durumları, rakipler ve nöron susturma sonuçlarını gösteren UI penceresi |
| [Fiziksel sahne](research/physical-scene.png) | 16 Eylül gerçek üst/bilek kamera karelerinin rapordaki yan yana düzeni; algılanan etiketler işaretlidir |
| [Fiziksel hareket](research/physical-base-motion.png) | 16 Eylül logundan hedef ve ölçülen taban açısı; sonlu tek hareket segmenti |

Üç yeni UI ekranı kırpılmamış ve değiştirilmemiş tarayıcı görüntüleridir. Son iki
şekil 16 Eylül teknik raporundan aynen alınmıştır; 26 Eylül'de donanım çalıştırılmadı.
Kamera şekli gerçek kurulumu, zaman serisi ise hareketi belgeler; ikisi de fiziksel
XOX oyunu veya otonom kavrama sonucu değildir. Sıfır/sabit hareketli denemeler ve
başarısızlıklar [kanıt paketinde](../research/README.md) korunur.

Yeni varlıkların tarih, boyut, SHA256 ve kaynak bilgileri
[araştırma medya manifestinde](research/provenance.json), bütün medya hash'leri
[genel manifestte](manifest.json) bulunur.
