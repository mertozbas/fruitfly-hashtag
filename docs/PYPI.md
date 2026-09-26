<p align="center"><img src="https://raw.githubusercontent.com/mertozbas/fruitfly-hashtag/v0.2.1/docs/media/hero.svg" alt="Hashtag Neural Lab — anatomiyi incele, yönelmeyi eğit, davranışı izle" width="1200"></p>

<!-- online-badges -->
<p align="center">
<a href="https://pypi.org/project/fruitfly-hashtag/"><img src="https://img.shields.io/pypi/v/fruitfly-hashtag?color=61cfc0" alt="PyPI sürümü"></a>
<a href="https://github.com/mertozbas/fruitfly-hashtag/actions/workflows/ci.yml"><img src="https://github.com/mertozbas/fruitfly-hashtag/actions/workflows/ci.yml/badge.svg" alt="Paket testleri"></a>
<a href="https://github.com/mertozbas/fruitfly-hashtag/blob/v0.2.1/LICENSE"><img src="https://img.shields.io/badge/kod-MIT-7b9cb8" alt="Kod lisansı MIT"></a>
<a href="https://labs.hashtagworldcompany.com"><img src="https://img.shields.io/badge/Hashtag-Robotics-243d49" alt="Hashtag Robotics"></a>
</p>
<!-- /online-badges -->

# Hashtag Neural Lab

**Meyve sineği konnektomundan görev devrelerine: yönelme, SO-101 robot kontrolü ve öğrenilmiş XOX stratejisi.**

Mert Özbaş · Hashtag World Company · Açık araştırma prototipi · Eylül 2026

[Research note (English)](https://github.com/mertozbas/fruitfly-hashtag/blob/v0.2.1/docs/research/research-note.md) · [Deney verileri](https://github.com/mertozbas/fruitfly-hashtag/blob/v0.2.1/docs/research/README.md) · [Atıf](https://github.com/mertozbas/fruitfly-hashtag/blob/v0.2.1/CITATION.cff)

Neural Lab, bilgisayarınızda çalışan bir deney laboratuvarıdır. Solda deneyi kurar,
ortada sineğin yürüyüşünü veya uçuşunu izler, sağda o hareket için kullanılan
hesabı incelersiniz. Yeni eğitim ayrı kaydedilir; eski ve yeni modeli aynı hedefte
karşılaştırabilirsiniz. Büyük veri ve modeller uygulama paketinden ayrı indirilir.
API anahtarı gerekmez; eğitimleriniz bilgisayarınızda kalır.

[Başla](https://github.com/mertozbas/fruitfly-hashtag/blob/v0.2.1/README.md#basla) · [Anatomiyi keşfet](https://github.com/mertozbas/fruitfly-hashtag/blob/v0.2.1/README.md#anatomi) · [Eğit](https://github.com/mertozbas/fruitfly-hashtag/blob/v0.2.1/README.md#egitim) · [Uçuşu izle](https://github.com/mertozbas/fruitfly-hashtag/blob/v0.2.1/README.md#ucus) · [Kanıtlar](https://github.com/mertozbas/fruitfly-hashtag/blob/v0.2.1/README.md#kanitlar) · [Rehber dizini](https://github.com/mertozbas/fruitfly-hashtag/blob/v0.2.1/docs/README.md)

![Canlı yürüyüş, kullanılan devre ve üç beyin analiz paneli](https://raw.githubusercontent.com/mertozbas/fruitfly-hashtag/v0.2.1/docs/media/neural-lab.jpg)

*Gerçek UI kaydı: HD fizik, hesaplanan model aktivitesi, anatomik konum, aktivite
haritası ve saydam kesit. Ekrandaki oturum sayacı aynı koşulun tekrarlarıdır;
çok hedefli başarı testi değildir.*

> Bu proje **tam beyin emülasyonu değildir**. MaleCNS anatomisinden türetilmiş
> **basitleştirilmiş görev alt ağları** kullanır; koku devresi 7.075 nörondur. Renkler hesaplanan model
> yanıtıdır. Bacakları FlyGym, kanatları FlyBody'nin hazır motor kontrolcüleri
> yönetir. Öğrenilen şey yön kararı veya motor düzeltme kazancıdır. [Bilimsel kapsam](https://github.com/mertozbas/fruitfly-hashtag/blob/v0.2.1/docs/training.md#bilimsel-kapsam).

## Araştırma güncellemesi · SO-101 ve XOX

MaleCNS anatomisinden seçtiğimiz bağlantı yapısını koruyup görev kodlayıcılarını,
mevcut bağlantıların kazançlarını ve çıkış okumalarını eğittik. Böylece özgün sinek
laboratuvarını **robot simülasyonu, XOX karar verme ve sınırlı fiziksel hareket**
deneyleriyle genişlettik. Çalışma hakem değerlendirmesinden geçmemiş bir mühendislik
araştırmasıdır; tam beyin emülasyonu, biyolojik zekâ veya genel amaçlı model iddiası taşımaz.

**Gerçek SO-101 üzerinde test yaptık ve sinir ağına bağlı, enkoderle ölçülmüş
fiziksel taban hareketi elde ettik.** XOX stratejisi ve küp yerleştirme sonuçları ise
ayrı sanal tahta / MuJoCo deneyleridir. Fiziksel kolda otonom kavrama ve tam XOX
oyunu henüz doğrulanmadı.

| Deney ve koşul | Kaydedilen sonuç | Ne gösterir? |
| --- | --- | --- |
| XOX · ayrı tutulan 125 simetri grubu | **%96,8 optimal hamle** | İlk eğitim aşamasının ayrılmış doğrulaması |
| XOX · son model, tüm geçerli karar durumları | **4.520 / 4.520 optimal hamle** | Son model tüm bu gruplarla eğitildi; görülmemiş veri başarısı değildir |
| XOX · rastgele rakip, iki rol, 400 oyun | **352 galibiyet / 48 beraberlik / 0 yenilgi** | Sanal tahta stratejisi |
| XOX · minimax rakip, iki rol, 400 oyun | **400 beraberlik / 0 yenilgi** | Canlı hamleleri ağ seçer; minimax test rakibidir |
| XOX · MuJoCo, 30 mm eğitim küpleri | **9/9 hedef**, beş robot hamleli tam oyun | X taşları temas fiziğiyle taşınır; O sanal rakiptir |
| SO-101 · ayrı 100 simülasyon başlangıcı | **94/100 başarı**, 0 sınır ihlali | Belirtilen checkpoint ve başlangıç dağılımı |
| Gerçek SO-101 · görsel devre → taban | **160 enkoder sayımı ≈ 14,07°**, 85 hedef güncellemesi | Tek robotta sınırlı fiziksel hareket; görev başarı oranı değildir |

Kaynaklar, checkpoint SHA256 değerleri, kontrol deneyleri ve başarısız koşullar
[araştırma notunda](https://github.com/mertozbas/fruitfly-hashtag/blob/v0.2.1/docs/research/research-note.md) ve
[makinece okunabilir kanıt paketinde](https://github.com/mertozbas/fruitfly-hashtag/blob/v0.2.1/docs/research/README.md) bulunur.
Bunlar 14–16 Eylül kayıtlarıdır; 26 Eylül'de yayına hazırlanırken yeni fiziksel
deney yapılmadı. Yazılım testleri fiziksel görev doğrulamasının yerine geçmez.

### XOX: tahta görüntüsünden öğrenilmiş hamleye

![Gerçek Neural Lab ekranı: XOX, robot simülasyonu, canlı motor hesabı ve öğrenme eğrisi](https://raw.githubusercontent.com/mertozbas/fruitfly-hashtag/v0.2.1/docs/media/research/xox-live-metrics.jpg)

*26 Eylül 2026 tarayıcı kaydı; `cd704b86be32…` checkpoint'i, duraklatılmış MuJoCo
kavrama aşaması. Bu ekran tek bir gösterim anıdır; çok koşullu başarı ölçümü değildir.*

**3.488 nöron / 81.104 bağlantı** içeren Touch → VNC → Motor alt grafiğine
27 öğeli tahta kodlaması ve dokuz hamle çıkışı bağlandı. Minimax eğitim etiketlerini
ve değerlendirme rakibini sağlar; canlı çıkarımda arama veya hamle tablosu yoktur.
Yasal hamle maskesi ve oyun kuralları deterministiktir.
Motor yürütme ayrıca öğrenilmiş okuma ve mühendislik ürünü aşama gözetimi kullanır.

![XOX sonuç tablosu: eğitim öncesi, öğrenilmiş strateji ve nöron susturma kontrolü](https://raw.githubusercontent.com/mertozbas/fruitfly-hashtag/v0.2.1/docs/media/research/xox-evaluation.jpg)

*Nöronlar susturulduğunda rastgele rakibe karşı 267/400 yenilgi; eğitim öncesinde
197/400 yenilgi kaydedildi. Bu kontrol ağ etkinliğine bağımlılığı sınar;
anatomik yapının eş boyutlu yapay ağlardan üstün olduğunu kanıtlamaz.*

![Anatomik konum, aktivite haritası ve saydam kesit panelleri](https://raw.githubusercontent.com/mertozbas/fruitfly-hashtag/v0.2.1/docs/media/research/xox-brain-analysis.jpg)

*Renkler modelin hesaplanan yanıtlarıdır; canlı hayvandan ölçüm değildir.
Konumu bilinen 1.623/3.488 nöron çizilir; eksik konumlar uydurulmaz.*

[Oyun, eğitim ve motor deneyini yeniden üretme](https://github.com/mertozbas/fruitfly-hashtag/blob/v0.2.1/docs/tictactoe-local.md) ·
[SO-101 simülasyon yöntemleri ve dayanıklılık sınırları](https://github.com/mertozbas/fruitfly-hashtag/blob/v0.2.1/docs/so101-local.md)

### Gerçek robot: kamera → görsel devre → sınırlı taban hareketi

![Gerçek SO-101 deney düzeni: sabit kamera ve bilek kamerası](https://raw.githubusercontent.com/mertozbas/fruitfly-hashtag/v0.2.1/docs/media/research/physical-scene.png)

*16 Eylül oturumundan kamera kareleri; nesne etiketleri algı katmanının çıktısıdır.
Bu görüntü kavrama başarısını göstermez.*

Fiziksel deney, XOX alt ağından **ayrı bir görsel devre** kullanır:
**4.387 nöron / 23.327 mevcut bağlantı**. Kırmızı uyaranın iki görüntü yarısındaki
ölçümleri sinir ağına girer; çıkış yön/genlik üretir. Deterministik adaptör taban
eklemini seçer, hız/süre/hareket sınırlarını uygular ve telemetriyi denetler.

![Gerçek taban hareketinde gönderilen hedef ve enkoder ölçümü](https://raw.githubusercontent.com/mertozbas/fruitfly-hashtag/v0.2.1/docs/media/research/physical-base-motion.png)

*Kaydedilmiş hareket segmenti: 170 sayımlık gönderilen hedefe karşı 160 sayım
ölçüm; yaklaşık 0,88° son fark. Devre çıkışı bu segmentte −1'de doygundur.
Grafik geçmiş telemetriden üretilmiştir; yön değiştirme veya görsel takip
kararlılığına ilişkin kapsamlı bir test değildir.*

Diğer gövde konumlandırmaları ve boş kıskaç açma deterministik denemelerdir.
Kavrama tamamlanmadı; takip durmaları ve aralıklı sıcaklık okumaları açık
bulgulardır. Fiziksel sonuçların sınırları ve başarısız denemeler
[araştırma notunda](https://github.com/mertozbas/fruitfly-hashtag/blob/v0.2.1/docs/research/research-note.md), yürütme sözleşmeleri
[donanım rehberinde](https://github.com/mertozbas/fruitfly-hashtag/blob/v0.2.1/docs/so101-hardware.md) yer alır.

### Coming soon · bu devreyi LLM benzeri bir arayüzle kullanmak

Sonraki araştırma yönümüz, konnektomdan türetilen hesaplama çekirdeğini metinle
etkileşilebilen ve görevler arasında değerlendirilebilen bir arayüz arkasında
kullanmayı incelemek. Girdi/çıktı kodlama, durum/bellek, öğrenme ve çıkarım
sözleşmeleri; küçük görevlerden başlayarak doğruluk, genelleme, gecikme ve
maliyet ölçümleri araştırılacak.

**Bu bir yol haritasıdır.** Mevcut model dil üretmez, LLM değildir ve genel amaçlı
akıl yürütme başarısı gösterilmedi. Önce uygun karşılaştırma modelleri ve
ölçülebilir kabul kriterleri kurulacak. Fiziksel tarafta sonraki adım leader ile
senkronize gösterim toplamak ve gerçek kavramayı ayrıca doğrulamaktır.

### Kaynak sürümü ve hazır paket

Bu GitHub güncellemesi araştırma kodunu, seçilmiş kanıtları ve ekran görüntülerini
paylaşır. **PyPI'deki mevcut sürüm ayrı bir yayındır; bu güncelleme PyPI yayını değildir.**
Eğitilmiş kişisel checkpoint'ler, büyük MaleCNS indirmeleri ve ham cihaz/oturum
arşivleri repoya dahil değildir. Yeni klonda aynı hazır model menüsünü beklemeyin;
[araştırma notundaki önkoşullar ve komutlarla](https://github.com/mertozbas/fruitfly-hashtag/blob/v0.2.1/docs/research/research-note.md)
yerel model oluşturulur. Sayısal kanıt paketi robot veya bilimsel veri indirmeden incelenebilir:

```bash
python3 docs/research/verify_evidence.py
```

Sinek laboratuvarının kurulumunu, yürüyüş/uçuş deneylerini ve önceki medyasını
aşağıda koruyoruz. Ek duyusal deneylerde kaçınma **6/6**, görsel yönelme **6/6**,
engel **2/6**; engel eğitiminde başarı artışı gösterilmedi.
[Yöntem ve kontrol deneyleri](https://github.com/mertozbas/fruitfly-hashtag/blob/v0.2.1/docs/local-tasks.md).

## Bir anatomik haritadan çalışan deneye

Başlangıç sorusu basitti: “İndirilen sinir sistemi verisinden bir devre seçip,
onun parametrelerini değiştirince davranıştaki farkı görebilir miyiz?”
Bu repo o sorunun izlenebilir bir prototipidir: anatomi → devre → eğitim → fizik.
Her aşamanın kaynağı, modeli ve ölçümü ayrı tutulur.

![Resmi veriden yerel eğitime, motor kontrolcülerine ve yeni anten ölçümüne akış](https://raw.githubusercontent.com/mertozbas/fruitfly-hashtag/v0.2.1/docs/media/pipeline.svg)

<a id="basla"></a>
## 01 — Kendi laboratuvarını aç

Doğrulanan tam platform **Apple Silicon macOS**; Linux bilimsel kurulumu deneysel,
Windows yerel simülasyonu desteklenmiyor. Python **3.11+**, **pipx** ve uçuş için
**Git** gerekir. **15 GiB boş disk**, en az **16 GB RAM**, tercihen **32 GB RAM**
ile planlayın. RAM rakamları kapasite önerisidir; 16 GB cihazda performans ölçümü
anlamına gelmez. [Platform ve donanım ayrıntıları](https://github.com/mertozbas/fruitfly-hashtag/blob/v0.2.1/docs/installation.md).

macOS'ta pipx yoksa:

```bash
brew install pipx git
pipx ensurepath
```

Terminali yeniden açıp PyPI'den kurun:

```bash
pipx install fruitfly-hashtag
fruitfly ui
```

Kaynak kodla başlamak isterseniz bunun yerine:

```bash
git clone https://github.com/mertozbas/fruitfly-hashtag.git
cd fruitfly-hashtag
pipx install .
fruitfly ui
```

**http://127.0.0.1:8766/** açılır. Terminal açık kalır; `Ctrl+C` sunucuyu durdurur.

| İlk açılış | Bilgisayarınızda yapılan işlem |
| --- | --- |
| **Beyni indir ve kur** | Python 3.12 ortamı, yaklaşık **1,11 GB** resmi MaleCNS tablosu, seçilmiş geometriler, yerelde 3.000 adımlık ilk model ve kısa HD fizik kontrolü |
| **Uçuşu kur** — isteğe bağlı | Ayrı Python 3.11 / TensorFlow ortamı ve **19,4 MB** FlyBody politika/referans arşivi; Python paketleri ayrıca yer kaplar |
| **Laboratuvarı aç** | Aynı adreste canlı simülasyon ve devre inceleme UI'ı |
| Sonraki açılış | `fruitfly ui`; yeniden veri indirme gerekmez |

İndirmeler SHA256 ile doğrulanır. Başlangıç kontrolü altı hedefli başarı testi
olmadığı için ilk modelin fizik skoru boş görünebilir. Tam kaynaklar kurulduktan
sonra mevcut görevler internetsiz çalışır. **Rehber** düğmesi veya `fruitfly docs`
paketle gelen yerel kılavuzu açar.

<a id="anatomi"></a>
## 02 — Haritayı ve çalışan devreyi ayır

![MaleCNS atlasından gerçek beyin ve VNC yüzeyi üzerinde 28 seçilmiş nöron](https://raw.githubusercontent.com/mertozbas/fruitfly-hashtag/v0.2.1/docs/media/anatomy-atlas.jpg)

*İlk keşif atlasından gerçek ekran görüntüsü. Buradaki renkler hücre kimliğidir;
elektriksel aktivite değildir. Uzun alt yapı ventral sinir kordonudur (VNC).*

[MaleCNS v1.0](https://male-cns.janelia.org/download/) anotasyonları ve bağlantı
tabloları kaynak anatomiyi sağlar. UI bu veriden seçilmiş devreyi gerçek soma
konumlarına yerleştirir. Konumu eksik nöronlar için yapay koordinat üretmez.

| İncelediğiniz katman | Kapsam |
| --- | --- |
| Hesaplanan devre | **2.228 ORN → 686 ALPN → 4.064 Kenyon → 97 MBON** |
| Gerçek konumda çizilen model nöronları | **4.826 / 7.075**; diğerlerinin yanıtları katman metriklerine dahildir |
| Uçları konumlu model bağlantıları | **82.747**; varsayılan görünüm okunabilirlik için 520 temsilci çizgi |
| Dallanan anatomik iskeletler | **28 gerçek SWC**; üçü çalışan alt devrenin üyesi |
| Eğitimde değişebilen mevcut bağlantılar | **61.210 KC→MBON** bağlantısının çarpanları; yeni anatomik kenar eklenmez |

Bir nörona veya bağlantıya tıklayın: gerçek body ID, hücre tipi, taraf, kaynak
anotasyonları, anatomik temaslar ve varsa seçili modeldeki değerleri açılır.
Düz bağlantı çizgileri soma–soma ilişkisidir; aksonun gerçek güzergâhı değildir.

![Nöronun kaynak kimliği, anatomik bağlantıları ve model üyeliği](https://raw.githubusercontent.com/mertozbas/fruitfly-hashtag/v0.2.1/docs/media/neuron-inspector.jpg)

*DNa02 kaydı çalışan yönelme devresinin dışındadır. UI bu nedenle canlı aktivite
uydurmak yerine “Devre dışında” gösterir. [Kontroller ve metrikler](https://github.com/mertozbas/fruitfly-hashtag/blob/v0.2.1/docs/usage.md).*

<a id="egitim"></a>
## 03 — Yönelmeyi eğit, değişimi gör

İlk deney **kokulu hedefe yönelme**. Fizikteki iki antenin konumunda sentetik koku
örneklenir. Model yalnızca bu iki yoğunluğu alır; hedef koordinatları karar
vericiye doğrudan verilmez. Eğitim, sentetik örneklerde bir referans yön
kontrolcüsünün cevabını taklit eder.

1. **Davranış → Kokuya yönelme** seçin; hedefi **X=12, Y=4 mm** yapın.
2. **Adım=3000, Tohum=42** ile **Eğitimi başlat** düğmesine basın.
3. Öğrenme ve ardından **altı fizik koşulunun** değerlendirilmesini bekleyin.
4. **Yeni modeli simülasyona al** ile kaydı çalıştırın.
5. **Δ Ağırlık** görünümünü açın; değişen mevcut bağlantıları inceleyin.
6. Eski ve yeni modeli aynı hedefte karşılaştırın. MSE ile fizik başarısını birlikte okuyun.

![Kaydedilmiş öğrenme eğrisi ve anatomik başlangıca göre bağlantı değişimleri](https://raw.githubusercontent.com/mertozbas/fruitfly-hashtag/v0.2.1/docs/media/learning-delta.jpg)

**Her eğitim aynı anatomik başlangıçtan yeni bir deneydir.** Seçili checkpoint'in
kaldığı yerden devam etmez. Hedef X/Y canlı değerlendirmeyi değiştirir; eğitim
örneklerini değiştirmez. İlk iki anatomik katman sabittir; KC→MBON çarpanları ve
yapay motor okuması öğrenilir. [Adım adım eğitim rehberi](https://github.com/mertozbas/fruitfly-hashtag/blob/v0.2.1/docs/training.md).

### Aynı hedef, iki model

![Solda eğitim öncesi, sağda eğitim sonrası gerçek MuJoCo yürüyüşü](https://raw.githubusercontent.com/mertozbas/fruitfly-hashtag/v0.2.1/docs/media/walking-comparison.gif)

**Sol: eğitim öncesi. Sağ: 3.000 adım / tohum 42 sonrası.** Hedef `(12, 4)` mm,
fizik tohumu 10. Yeni kayıt: son mesafe **27,60 → 1,50 mm**, devrilme yok.
İki kayıt 5× yavaşlatılmıştır; sağ taraf hedefe ulaştıktan sonra son karede kalır.
Bu tek koşulun gösterimidir. [MP4 kaydı](https://github.com/mertozbas/fruitfly-hashtag/blob/v0.2.1/docs/media/walking-comparison.mp4) · [Kayıt ve test kanıtları](https://github.com/mertozbas/fruitfly-hashtag/blob/v0.2.1/docs/experiments.md).

<a id="ucus"></a>
## 04 — Aynı yönelme ağını uçuşta kullan

![MaleCNS yön kararıyla çalışan FlyBody uçuş kaydı](https://raw.githubusercontent.com/mertozbas/fruitfly-hashtag/v0.2.1/docs/media/flight.gif)

*Gerçek MuJoCo / FlyBody kaydı, hedef `(22, 6)` mm. 0,03× oynatım; kanatları
incelemek için yavaşlatılmıştır. [720p MP4](https://github.com/mertozbas/fruitfly-hashtag/blob/v0.2.1/docs/media/flight.mp4).*

Uçuş kurulduğunda **Davranış → Uçuş · beyin bağlı** seçin. Aynı MaleCNS alt ağı
kokuya göre yön komutu üretir; sınırlandırılmış komut FlyBody'nin hazır kanat
politikasına referans olur. Beyin paneli o anda kullanılan hesabı gösterir.

![Uçuş fiziği, canlı devre ve anatomik analizler aynı ekranda](https://raw.githubusercontent.com/mertozbas/fruitfly-hashtag/v0.2.1/docs/media/flight-lab.jpg)

Uçuş seçiliyken **Yönelme ağını eğit**, yeni ağı altı uçuş hedefinde de sınar.
**Sinek havada başlar.** Kalkış, iniş, irtifa öğrenimi ve kanat politikasını yeniden
eğitme bu sürümde yoktur. Kaçınma, görme ve engel görevleri yerel çalışma
kopyasında geliştirilip bu GitHub kaynak sürümünde paylaşılmıştır; mevcut PyPI sürümü ayrıdır. [Yerel görevler ve sonuçlar](https://github.com/mertozbas/fruitfly-hashtag/blob/v0.2.1/docs/local-tasks.md). [Uçuş kontrol yolu ve kullanım](https://github.com/mertozbas/fruitfly-hashtag/blob/v0.2.1/flight/README.md).

<a id="kanitlar"></a>
## 05 — Sonucu neyle doğruluyoruz?

| Deney | Gözlenen sonuç | Yorum |
| --- | --- | --- |
| İlk kontrollü yürüyüş testi | Eğitim öncesi **0/6**, sonrası **5/6**; 0 devrilme | Altı sabit hedef/tohum; bir başarısız koşul dahil |
| 3.000 adım / 42 uçuş testi | **6/6**, 0 uçuş sınırı ihlali | Kısa, sabit irtifalı altı hedef |
| Ayrı 6.000 adımlık uçuş modelinde müdahale | Aynı iki koşulda bağlı **2/2**, çıkış sıfır **0/2**, ters **0/2** | O modelin yön komutunun etkisini sınar |
| Yeni medya kayıtları | Yürüyüşte önce/sonra farkı ve beyne bağlı uçuş | Gösterim koşulları; geniş kapsamlı benchmark değil |

Bu sayılar genel başarı oranı veya biyolojik doğruluk iddiası değildir. Kayıt
kaynakları, checkpoint özetleri, başarısızlıklar ve yeniden üretme komutları
[deney kayıtlarında](https://github.com/mertozbas/fruitfly-hashtag/blob/v0.2.1/docs/experiments.md) bulunur. Paket CI'ı macOS/Linux'ta
kurulumu ve rehberi sınar; bilimsel Linux doğrulaması yerine geçmez.

## Rehberler ve depo haritası

| Başlamak istediğiniz yer | Belge |
| --- | --- |
| Tüm belgelerin başlangıç noktası | [Rehber dizini](https://github.com/mertozbas/fruitfly-hashtag/blob/v0.2.1/docs/README.md) |
| pipx, indirme, disk, platformlar ve ilk açılış | [Kurulum](https://github.com/mertozbas/fruitfly-hashtag/blob/v0.2.1/docs/installation.md) |
| Mouse, parlaklık, seçim ve metrikler | [UI kullanımı](https://github.com/mertozbas/fruitfly-hashtag/blob/v0.2.1/docs/usage.md) · [Laboratuvar turu](https://github.com/mertozbas/fruitfly-hashtag/blob/v0.2.1/LAB.md) |
| Eğitim, kayıt, karşılaştırma, bilimsel kapsam | [Eğitim](https://github.com/mertozbas/fruitfly-hashtag/blob/v0.2.1/docs/training.md) |
| Fizik ve videolar | [Yürüyüş](https://github.com/mertozbas/fruitfly-hashtag/blob/v0.2.1/SIMULATION.md) · [Uçuş](https://github.com/mertozbas/fruitfly-hashtag/blob/v0.2.1/flight/README.md) |
| Kaynak URL'leri, dosyalar ve SHA256 | [Veriler ve modeller](https://github.com/mertozbas/fruitfly-hashtag/blob/v0.2.1/docs/data.md) |
| SO-101 / XOX araştırması, kanıt ve sınırlılıklar | [Research note](https://github.com/mertozbas/fruitfly-hashtag/blob/v0.2.1/docs/research/research-note.md) · [Kanıt paketi](https://github.com/mertozbas/fruitfly-hashtag/blob/v0.2.1/docs/research/README.md) |
| Gerçek ölçümler ve görsel kökeni | [Deneyler](https://github.com/mertozbas/fruitfly-hashtag/blob/v0.2.1/docs/experiments.md) · [Medya dizini](https://github.com/mertozbas/fruitfly-hashtag/blob/v0.2.1/docs/media/README.md) |
| Güncelleme, yedekleme, sorunlar | [Sorun giderme](https://github.com/mertozbas/fruitfly-hashtag/blob/v0.2.1/docs/troubleshooting.md) |
| Kod, build, test ve yayın | [Geliştirici rehberi](https://github.com/mertozbas/fruitfly-hashtag/blob/v0.2.1/docs/development.md) |

```text
src/fruitfly_lab/       Hafif CLI, kurulum ekranı ve kaynak manifesti
ui/                    Tam ekran laboratuvar; Three.js + statik JavaScript
lab_*.py               FastAPI, canlı fizik, beyin geometrisi ve eğitim işleri
odor_policy.py         Yürüyüş ve uçuşun ortak devre hesabı
flight/                Ayrı TensorFlow ortamı ve uçuş motor adaptörü
environments/walking/  Kilitli bilimsel Python ortamı
docs/                  Çevrimdışı rehber, görüntüler, videolar ve kanıtlar
```

Veriler ve kişisel eğitimler varsayılan **`~/.fruitfly-hashtag/`** altında, repo ve
pipx ortamından ayrı tutulur. `data/` resmi indirmeleri, `models/lab_runs/` kişisel
koşuları, `artifacts/` türetilmiş çıktıları içerir. Paket yükseltmesi eğitimleri
silmez. Başka disk için her komutta komut adından önce aynı `--home` kullanın:

```bash
fruitfly --home /Volumes/LabDisk/neural-lab ui
fruitfly --home /Volumes/LabDisk/neural-lab doctor
```

## Kaynaklar ve teşekkür

Bu laboratuvar [MaleCNS](https://male-cns.janelia.org/download/),
[NeuroMechFly / FlyGym](https://neuromechfly.org/),
[FlyBody](https://github.com/TuragaLab/flybody), MuJoCo ve Three.js üzerine kuruludur.
Gövde, anatomi ve motor politikaları farklı araştırma kaynaklarından gelir;
birleştirilmiş sistem taranan bireyin dijital ikizi değildir.

Orijinal kod **[MIT](https://github.com/mertozbas/fruitfly-hashtag/blob/v0.2.1/LICENSE)**. MaleCNS verisi **CC BY 4.0**, FlyBody kodu
**Apache 2.0**, Figshare politika/veri arşivleri **GPL 3.0+**, Three.js **MIT**.
Dış kaynaklar uygulamanın MIT lisansına dönüşmez. Görsellerin kaynakları ve
uyarlamaları [medya bildiriminde](https://github.com/mertozbas/fruitfly-hashtag/blob/v0.2.1/docs/media/README.md), tam atıflar
[THIRD_PARTY_NOTICES.md](https://github.com/mertozbas/fruitfly-hashtag/blob/v0.2.1/THIRD_PARTY_NOTICES.md) dosyasında bulunur.

[Mert Özbaş](https://github.com/mertozbas) · [Hashtag World Company](https://hashtagworldcompany.com) · [Hashtag Robotics](https://labs.hashtagworldcompany.com)
