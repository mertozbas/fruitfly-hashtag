# Yerel duyusal görevler ve taşınabilir modeller

Bu ekleme şu anda yerel çalışma kopyasındadır; GitHub veya PyPI'ye yayımlanmadı.
Yayımlanmış 0.2.1'in ekran görüntüleri önceki koku/uçuş sürümünü gösterir.

## Gerçek bir beyin mi çalışıyor?

Çalışan bir sinir ağı var. Ağın nöron kimlikleri ve seçilmiş yönlü bağlantıları
[MaleCNS v1.0 anatomik verisinden](https://male-cns.janelia.org/) gelir.
Bu, yaşayan sineğin beyni veya bütünüyle doğrulanmış dijital kopyası değildir.
Bağlantı haritası tek başına nöronların bütün çalışma ve öğrenme kurallarını vermez.

Burada nöronları pozitif normalize bağlantılar ve tanh yanıtlarıyla hesaplıyoruz.
Fizyolojik işaretler, spike, gecikme, tekrarlayan devre dinamiği ve biyolojik
plastisite modellenmiyor. Öğretmen kuralından üretilen örnekleri taklit ederek
son anatomik katmanın bağlantı çarpanlarını ve yapay motor okumasını eğitiyoruz.
**Katsayılar gerçekten değişiyor ve kaydediliyor; öğrenme biyolojik olarak doğrulanmış değil.**

Sineğin hareketinde bu ağ etkili. Ancak bacak ritmini FlyGym CPG, uçuşta kanatları
hazır FlyBody politikası üretir. Ağ; göreve göre yönü veya bacak düzeltmesinin
kazancını belirler. Her eklem komutu bütün MaleCNS beyninden hesaplanmıyor.

## Üç yeni görev

| Görev | Girdi → anatomik alt devre | Öğrenilen motor etkisi |
| --- | --- | --- |
| Kokudan kaçınma | İki antenin sentetik kokusu → ORN → ALPN → Kenyon → MBON; 7.075 nöron | Kaynaktan uzağa dönüş; sıkı kaçış için iç bacak ritmi ters dönebilir |
| Görsel yönelme | İki gerçek MuJoCo göz kamerasının RGB görüntüsü → fotoreseptör → optik ara → görsel projeksiyon → inen katman; 4.387 nöron | Görüntüdeki kırmızı hedefe dönüş |
| Engel aşma | MuJoCo bacak temas kuvvetleri → dokunma → VNC ara → VNC ön motor → motor; 3.488 nöron | Hazır takılma / geri çekme düzeltmesinin kazancı |

Görmede kırmızı piksel belirginliği iki gözde ayrı hesaplanır; ağ hedef koordinatını
almaz. Bu görüntü işleme ve sağ/sol havuzlama yapaydır, biyolojik retinotopi veya
fotoreseptör tepkisi değildir. Görme ve temas için koku nöronları kullanılmaz.
Temas kuvveti `tanh(force / 5)` ile normalize edilir; 100 ms sönümlü iz taşır.
Engel fiziksel temas geometrisidir; yalnızca render edilmiş bir nesne değildir.

Görme ve VNC yolları sınıf ve anatomik temas sayısından, sabit hesaplama bütçesiyle
seçilmiştir. Katmanlar ayrıdır; her düğüm girdi–çıktı yolundadır. Bu seçimin
biyolojik görsel yönelme veya tırmanma devresini belirlediği iddia edilmez.
Mevcut bağlantılar eğitilir; yeni anatomik bağlantı eklenmez.

## UI'da kullanma

1. Yerel kaynak klasöründe `./ui.sh` çalıştırın; `http://127.0.0.1:8766` açın.
2. **Davranış** menüsünden görevi seçin. Harita, nöron sayısı, katman adları ve
   canlı aktivite kullanılan devreye geçer. Görmede sol altta göz girdisi görünür.
3. Model listesinden mevcut eğitimli kaydı veya aynı koşunun **eğitim öncesi**
   kaydını seçin. Bir göreve ait model başka duyu devresine uygulanamaz.
4. **Adım=3000, Tohum=42 → Eğitimi başlat**. Önce 2.048 sentetik örnekle eğitim,
   ayrı 512 örnekle doğrulama; ardından 6 fizik koşulunda üçlü karşılaştırma yapılır.
   Mevcut model ve önceki eğitimler korunur.
5. İş bitince **Yeni modeli simülasyona al** seçin. Bu işlem otomatik yapılmaz.
6. **Test karşılaştırması** eğitimli, eğitim öncesi ve motor çıkışı kapalı sonuçları
   gösterir. **Δ Ağırlık** değişen bağlantı katsayılarını gösterir.

Engel görevi sabit bir parkurdur; hedef alanları bu görevde kapalıdır. Diğer
görevlerde serbest hedef, eğitimin sentetik örneklerini veya sabit test listesini
değiştirmez. Bir göreve ilk geçişte o görevin kayıtlı fizik skoru en yüksek modeli
seçilir; sonradan worker'ın seçimi korunur. Bütün tamamlanmış koşular menüde kalır.

**Her yeni eğitim anatomik başlangıçtan ayrı checkpoint üretir.** Koku, kaçınma,
görme ve temas bilgisi şu anda tek modelde birikmez. Birini eğitmek diğerini
güncellemez. Serbestçe oynatmak veya izlemek de ağırlıkları kendiliğinden değiştirmez.

## Bu bilgisayardaki sonuçlar

14 Eylül 2026; 3.000 adım, tohum 42. Aynı altı fizik koşulu üç modelle tekrarlandı.
CPG ve ortam her karşılaştırmada aynıdır. “Çıkış kapalı” koşulunda öğrenilmiş
motor okuması sıfırlanır; hazır yürüme kontrolcüsü çalışmaya devam eder.

| Görev | Eğitim öncesi | Eğitim sonrası | Motor çıkışı kapalı | Yorum |
| --- | --- | --- | --- | --- |
| Kaçınma | 0/6 | 6/6 | 0/6 | Bu altı koşulda ağın motor çıkışı gerekliydi |
| Görsel yönelme | 2/6 | 6/6 | 0/6 | Görüntüden öğrenilen yön çıkışı başarıya katkı sağladı |
| Engel aşma | 2/6 | 2/6 | 2/6 | Ağ hareketi değiştirse de başarı artışı gösterilmedi; deneysel |

Üç karşılaştırmada da devrilme olmadı. Başarısız kaçınma koşulları tehlike alanına
giriş; engel başarısızlıkları verilen süre/koridor ölçütünün karşılanmamasıdır.
Ek UI akış kontrolünde **200 adım / tohum 43 kaçınma 1/6** verdi; bu kayıt da
korunur. Düşük MSE veya “eğitim tamamlandı” tek başına başarı değildir.

Kaçınma motor eşlemesinin ilk denemesinde dönüş yetkisi 0,55 iken 2/6 elde edildi.
Nihai eşlemede 1,1 kullanılır; iç CPG ters yönde çalışabilir. Başarı ölçütü ve
altı ortam değiştirilmeden karşılaştırma yeniden çalıştırıldı. Bu bir gövde
adaptörü düzeltmesidir; biyolojik bir keşif değildir.

| Görev | Sabit test koşulları | Başarı ölçütü |
| --- | --- | --- |
| Kaçınma | `(6,±2)`, `(5,±2)`, `(7,±2)` mm; tohum 10–15 | 3 mm tehlike alanına girmeden başlangıca göre 8 mm uzaklaşma |
| Görme | `(12,±4)`, `(10,±5)`, `(14,±3)` mm; tohum 10–15 | Hedefe <1,5 mm |
| Engel | 5–6,2 mm X aralığında, 20 mm genişliğinde engel; yükseklik 0,25 / 0,35 / 0,45 mm, her birinde iki tohum | Fiziksel temas sonrası gövde X>9,2 mm, mutlak Y<5 mm |

Fizik adımı 0,1 ms, sensör/karar adımı 10 ms; değerlendirme bölümü en fazla
2,5 saniyedir. UI bölümü 3 saniye sürer; serbest oturum sayacı bu sabit benchmark
ile aynı şey değildir. CPU/BLAS/MPS farklılıkları hareket sonucunu değiştirebilir.

Kayıtlar yerelde `models/lab_runs/local-avoidance-seed42`, `local-vision-seed42`,
`local-terrain-seed42` dizinlerindedir. İndirilmiş modeller repoya dahil edilmez.

| Görev | Değişen mevcut bağlantı | Eğitimli checkpoint SHA-256 |
| --- | --- | --- |
| Kaçınma | 57.614 | `a2d3419f030dadb290970bf990a068373d7b88e928564215196565fce9442146` |
| Görme | 7.781 | `26a34b50fd88f257230ee75fcf1edf37cc769de9d65233ea4c59562408d86e3e` |
| Engel | 20.253 | `fa83cffe6da34507b03bf4c0a154b1672e2e16b777c36d537d2353cc460b3822` |

## Başka yerde kullanma

**Modeli indir** seçili modeli ZIP olarak verir: `checkpoint.npz`, üç anatomik
matris, nöron kimlikleri, `circuit.json`, `odor_policy.py`, `infer.py`, hash manifesti
ve Türkçe README. Üç görev için dışa aktarılan paketler ayrı klasörlerde yüklenip
aynı girdiden aynı çıktıyı üreterek doğrulandı. Tam MaleCNS indirmesi çıkarımda gerekmez.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install numpy scipy
python infer.py 0.10 0.12
```

Bu komut iki duyusal değerden bir motor kararını hesaplar. ZIP, FlyGym/FlyBody
gövdesini veya simülasyon kurulumunu içermez. Başka simülasyonda sensör ölçümünü
aynı giriş anlamına ve ağ çıkışını uygun motor komutuna dönüştürmelisiniz.
Bir robotta ayrıca fiziksel doğrulama ve güvenlik sınırları gerekir. Bu model
genel amaçlı, her işi öğrenmiş veya yeni donanımda doğrudan çalışacak bir beyin değildir.

[Eğitim rehberine dön](training.md) · [UI kullanımı](usage.md)
