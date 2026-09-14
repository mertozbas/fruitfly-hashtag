# UI kullanımı

![Canlı fizik ve devreyi aynı ekranda inceleyin](media/neural-lab.jpg)

[Rehber dizini](README.md) · [Kurulum](installation.md) · [Kullanım](usage.md) · [Eğitim](training.md)

Sağ üstte **⛶** tam ekranı açar. **Rehber** ayrı sekmede çevrimdışı kılavuzu açar.
Masaüstü düzeni tek ekran için tasarlanmıştır.

## Deney seçimi

**Davranış** menüsünde kokuya yönelme, kaçınma, görsel yönelme, deneysel engel
aşma ve kuruluysa beyne bağlı uçuş aktiftir. [Yerel görevler](local-tasks.md) yeni
devreleri, sınırlarını ve karşılaştırma sonuçlarını açıklar.
**Simülasyondaki model** hangi kayıtlı ağın çalıştığını gösterir; seçim eğitim başlatmaz.

**Hedef X/Y** milimetredir, sınırı ±30 mm. **Hedefi uygula** yeni bölüm başlatır.
Her serbest hedefte başarı garanti edilmez; kısa uçuşta gerideki hedefe erişilemeyebilir.

## Simülasyon ve mouse

| İşlem | Kontrol |
| --- | --- |
| Döndür | Sol tuşla sürükle |
| Kaydır | Sağ tuş veya Shift + sol tuşla sürükle |
| Yakınlaş/uzaklaş | Tekerlek / trackpad kaydırma |
| Sineğe odaklan | Gövde kamera seçeneği |
| Hedefi ve ortamı gör | Arena kamera seçeneği |
| Anı incele | Duraklat; kamerayı kullanmaya devam et |

Görüntü MuJoCo'da 1920×1080 üretilir; tarayıcı paneli daha küçük olabilir.
HD gerçek zamanlı hız garantisi değildir. Uçuş yavaş çekimdir; **simülasyon zamanı**
duvar saatinden farklı ilerler. Kanat hareketi hazır FlyBody politikasından gelir.

## Beyni okumak

**Aktivite**, son beyin kararındaki hesaplanan nöron yanıtıdır; biyolojik ölçüm
değildir. Duraklatınca son değerler sabit kalır. Devre görevle değişir. Koku
devresinde 7.075 yanıt hesaplanır; 4.826 soma 3B'de çizilir. Diğer görevlerin
sayıları başlıkta ve katman çubuğunda gösterilir. Eksik konumlar uydurulmaz.

**Sade** 520 temsilci bağ, **Nöronun bağları** seçili nöronun bağları,
**Tüm bağlar** seçili devrenin konumlu bağlarını gösterir (koku devresinde 82.747).
Parlaklık ve sinyal eşiği yalnızca görünümü değiştirir, çalışan ağı değiştirmez.

Düz çizgiler soma–soma bağlantı gösterimidir, akson geometrisi değildir.
Arka plandaki 28 dallanan SWC gerçek anatomidir; yalnızca seçili devreye dahil
olanları aktivite alır (koku devresinde üçü). Hesaplanmayan iskeletler gri kalır.

Nörona/bağa tıklayın: bodyId, sınıf, kaynak anotasyonları, temaslar ve seçili
modeldeki katsayılar ayrıntı panelinde açılır. JSON indirme seçili kaydı dışa
aktarır; bütün checkpoint'i indirmez. Soldaki **Modeli indir** ise devreyi,
ağırlıkları ve taşınabilir çıkarım kodunu ZIP olarak verir. **Test karşılaştırması**
yeni görevlerde eğitim öncesi/sonrası ve motor çıkışı kapalı sonuçları gösterir.

**Δ Ağırlık** anatomik başlangıca göre katsayı değişimidir; iki eğitimin birbirine
farkı değildir. İki modelde aynı bağlantıyı ayrı ayrı seçerek karşılaştırabilirsiniz.

## Metrikler

| Gösterge | Anlamı |
| --- | --- |
| Hedef uzaklığı | Hedefe uzaklık (mm) |
| Hız | Gövde hızı (mm/s) |
| Simülasyon zamanı | Fizikte geçen süre |
| Ödül | Görevde raporlanan ilerleme; bu sürümde eğitim algoritmasının ödül fonksiyonu değildir |
| Sol/sağ koku | Gerçek anten konumlarından sentetik alanda alınan yoğunluk |
| Motor komutu | Yürüyüşte CPG sürüşü, uçuşta sınırlanmış yön hızı |
| Doğrulama MSE | Ayrı örneklerde öğretmen yön komutuyla model çıktısının ortalama kare farkı |
| Fizik testi | Seçili görevin son testindeki başarı sayısı; sonuç yoksa boş |
| İrtifa / kanat frekansı | Uçuş fiziği; ayrı öğrenilmiş beyin çıktıları değildir |
| Aktivite haritası | X/Z izdüşümünde model yanıtı; sıcaklık ölçümü değildir |
| Saydam kesit | Gerçek konumların Y dilimi; X-ray veya tıbbi tarama değildir |

ORN / ALPN / Kenyon / MBON hücre grupları ve hesaplama aşamalarıdır; anatomik
bölge sınırlarının segmentasyonu olarak yorumlamayın.

## Bir kaydı inceleyin

![Nöron ayrıntıları ve model üyeliği](media/neuron-inspector.jpg)

**Nöron seç / Bağlantı seç** yoğun bölgelerde seçim türünü belirler. Özet,
bağlantılar ve kaynak alanları aynı panelde açılır. Model dışındaki hücre için
aktivite hesaplanmaz. Uzun kayıt panelin içinde kayar; ana laboratuvar sabit kalır.

[Laboratuvar turu](../LAB.md) · [Ölçümleri yorumlama](experiments.md)
