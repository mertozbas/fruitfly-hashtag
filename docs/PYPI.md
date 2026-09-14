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

**Gerçek sinek anatomisinden çıkarılan bir devreyi eğitin; yön kararını, canlı nöron yanıtlarını ve fizik simülasyonunu tek ekranda inceleyin.**

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
> **7.075 nöronluk basitleştirilmiş yönelme ağıdır**. Renkler hesaplanan model
> yanıtıdır. Bacakları FlyGym, kanatları FlyBody'nin hazır motor kontrolcüleri
> yönetir. Öğrenilen şey yön kararıdır. [Bilimsel kapsam](https://github.com/mertozbas/fruitfly-hashtag/blob/v0.2.1/docs/training.md#bilimsel-kapsam).

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
eğitme bu sürümde yoktur. Koku yönelmesi dışındaki “hazırlık” seçenekleri de
uygulanmış eğitimler değildir. [Uçuş kontrol yolu ve kullanım](https://github.com/mertozbas/fruitfly-hashtag/blob/v0.2.1/flight/README.md).

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
