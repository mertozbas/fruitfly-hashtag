# Deney kayıtları ve kanıtlar

**Önce koşulu, sonra sonucu okuyun.** Aşağıdaki sayılar küçük sentetik koku
hedef kümelerine aittir. Fizik simülasyonunda ölçülmüştür; biyolojik doğrulama,
farklı ortamlara genelleme veya canlı hayvan deneyi değildir.

[Rehber dizini](README.md) · [Eğitim](training.md) · [Medya kökeni](media/README.md)

## Yeni yürüyüş kaydı — 14 Eylül 2026

![Eğitim öncesi ve sonrası aynı fizik koşulu](media/walking-comparison.gif)

| Koşul | Eğitim öncesi | Eğitim sonrası |
| --- | --- | --- |
| Hedef / fizik tohumu | `(12, 4)` mm / 10 | Aynı |
| Başlangıç uzaklığı | 12,126 mm | 12,126 mm |
| Son uzaklık | 27,596 mm | 1,499 mm |
| Başarı / devrilme | Hayır / hayır | Evet / hayır |
| Fizik süresi | 3,00 s | 1,05 s; başarıda sonlandı |
| Checkpoint SHA256 başlangıcı | `9863d9a5671b` | `a28ea2dd4518` |

Model yeni ve ayrı bir kurulumda **3.000 adım, tohum 42** ile yerelde üretildi.
Video 640×480 kaynaklardan yan yana hazırlanmıştır; güncel UI'nin 1080p render
kalitesini ölçmez. Gösterim 0,2× hızdadır; başarılı taraf son karede bekler.

## Tarihsel altı koşullu yürüyüş testi

| Hedef (mm) | Fizik tohumu | Önce | Sonra |
| --- | --- | --- | --- |
| `(12, 4)` | 10 | Başarısız | Başarılı |
| `(12, −4)` | 11 | Başarısız | Başarılı |
| `(10, 5)` | 12 | Başarısız | **Başarısız** |
| `(10, −5)` | 13 | Başarısız | Başarılı |
| `(14, 3)` | 14 | Başarısız | Başarılı |
| `(14, −3)` | 15 | Başarısız | Başarılı |

Toplam **0/6 → 5/6**, devrilme 0; ortalama son uzaklık **20,453 → 4,113 mm**.
Bu tarihsel rapor checkpoint hash alanı içermiyor. Bu nedenle yeni videonun
hash ile izlenen koşusu ve tarihsel toplu skor ayrı kanıtlar olarak sunulur.

## Yeni uçuş kaydı

[720p uçuş videosu](media/flight.mp4): model `a28ea2dd4518`, hedef `(22, 6)` mm,
fizik tohumu 10. Hedefe **1,996 mm** uzaklıkta başarıyla sonlandı. Video 30 FPS,
her kare arasında 1 ms fizik ilerlemesiyle **0,03×** oynatılır. Canlı UI yaklaşık
0,01× hız hedeflediğinden videonun oynatım hızıyla UI RTF'si aynı değildir.

## Altı uçuş hedefinde eğitim sonrası değerlendirme

3.000 adım / tohum 42 UI eğitimi: **MSE 0,500215 → 0,005367**;
57.614 mevcut KC→MBON çarpanı değişti, yeni anatomik kenar 0.

Checkpoint:

```text
a28ea2dd4518efe4409ee6770bf6e389fb974292bf737770ee77f2aa2cf12af4
```

Hedefler sırasıyla `(22, 6)`, `(22, −6)`, `(28, 9)`, `(28, −9)`, `(24, 10)`,
`(24, −10)` mm; tohumlar 101–106. Sonuç **6/6**, uçuş sınırı ihlali 0,
ortalama son uzaklık **1,993 mm**. Bölümler kısa ve sabit irtifalıdır.

## Beyin komutu etkili mi? Müdahale testi

Bu test **ayrı, 6.000 adımlık** checkpoint'e aittir:

```text
e3928ec2fa60074b1c24dab8b76b46c3723fe7a2d7e8d51fbe1bdf92e8e2d087
```

Altı standart uçuş hedefinde 6/6. İlk iki hedef/tohumda motor politikası,
başlangıç ve fizik aynı tutulup yalnızca yön okumasına müdahale edildi:

| Yön okuması | Sonuç | Anlamı |
| --- | --- | --- |
| Bağlı | 2/2 | Seçili yön komutu bu iki hedefe ulaştırdı |
| Sıfır | 0/2 | Yön komutu kaldırılınca hedefler kaçırıldı |
| Ters | 0/2 | Komut işareti çevrilince hedefler kaçırıldı |

Bu, bu koşullarda komutun etkisini destekler. Biyolojik devrenin doğruluğunu,
başka ağlardan üstünlüğünü veya 3.000 adımlık modelin aynı müdahale testini
geçtiğini göstermez. Yeniden çalıştırma: [Uçuş değerlendirmesi](../flight/README.md).

## Kendi deneyinizi nasıl karşılaştırırsınız?

Hedefi, fizik tohumunu, eğitim tohumu/adımını, davranışı, checkpoint SHA256'sını
ve kaynak sürümünü kaydedin. Önce MSE'yi, sonra ayrı fizik sonuçlarını inceleyin.
Başarısız hedefleri de rapora dahil edin. UI oturum sayacının aynı koşulu tekrar
ettiğini unutmayın. Daha fazla adımın daha iyi sonuç vereceği garanti değildir;
önceki paket doğrulamasındaki 200 adım / tohum 43 yürüyüş koşusu yalnızca 1/6 verdi.

[experiments.json](media/experiments.json) özgün raporların ilgili ölçümlerini,
kaynak dosya özetlerini ve yeni kayıtların model kimliklerini içerir. İzler
kısaltılmıştır; bu dosya checkpoint veya ham bağlantı verisi içermez. Kaynak
raporların tamamı yerel deney dizinlerinde kalır; yeniden üretim kendi raporunuzu
oluşturur. Görsel dosya özetleri [manifestte](media/manifest.json) bulunur.
