# Veriler ve modeller

## “Beyni indirmek” ne demek?

Tek bir 3 GB hazır beyin checkpoint'i indirilmez. Önce MaleCNS'in **anatomik
bağlantı verisi** alınır; sonra bu veriden basitleştirilmiş devre oluşturulup
yönelme katsayıları yerelde eğitilir. FlyBody uçuş için ayrıca hazır motor
politikası indirir. Bu üç kavramı ayrı düşünün: **anatomi / yönelme modeli / gövde politikası**.

## Neler indirilir?

| Kaynak | Boyut | Kullanımı |
| --- | --- | --- |
| `body-annotations-male-cns-v1.0-minconf-0.5.feather` | 14.483.314 bayt | Nöron kimlikleri, sınıflar ve konumlar |
| `body-neurotransmitters-male-cns-v1.0.feather` | 43.282.834 bayt | Hücre düzeyi nörotransmiter anotasyonu; bu model fizyolojik işaret kullanmaz |
| `connectome-weights-male-cns-v1.0-minconf-0.5.feather` | 1.051.241.946 bayt | Anatomik temas sayıları |
| 28 SWC + JRCFIB2022M yüzeyi | Seçime bağlı ek geometri | Gerçek anatomi görünümü |
| FlyGym HD mesh | Ek render varlıkları | 1920×1080 ayrıntılı gövde |
| FlyBody `trained-fly-policies.zip` | 6.537.720 bayt | Hazır uçuş motor politikası; arşiv başka resmi politikalar da içerir |
| FlyBody `datasets_flight-imitation.zip` | 12.880.076 bayt | Uçuş referansları ve kanat örüntüsü |

Boyutlar sıkıştırılmış kaynak dosyaları içindir. Python, TensorFlow, Torch,
bilimsel paketler, çıkarılan arşivler, türetilen matrisler ve `uv` ortak önbelleği
bunlara **ek** yer kaplar. Yaklaşık 3 GB'lık resmi yürüyüş kümesi, 2,7 GB sinaps
nörotransmiter tablosu ve ham elektron mikroskobu hacimleri indirilmez.

MaleCNS indirme URL'leri, nesne generation numaraları, boyutlar ve SHA256 değerleri
pakette `fruitfly_lab/sources.json`, kaynak repoda `src/fruitfly_lab/sources.json`
içindedir. İndirilince `data/male-cns-v1.0/manifest.json` yazılır. Kaynaklar
[resmi MaleCNS indirme sayfasındandır](https://male-cns.janelia.org/download/).
SWC dosyaları indirildikleri nesne sürümüne sabitlenir, CRC32C/SHA256 doğrulanır.

FlyBody varlıkları [Figshare v4](https://doi.org/10.25378/janelia.25309105.v4)
dosya kimlikleri 44815195 / 51196859 ile alınır. Boyut, sabit SHA256, varsa kaynak
MD5 ve ZIP bütünlüğü kontrol edilir; çıkarma yolları arşiv dışına çıkamaz.
Kayıt `data/flybody/manifest.json` içindedir.

## Türetilenler

Ham tabloda 151.856.684 satır vardır. Keşif filtresi `superclass` dolu 166.700 kayıt
ve her iki ucu bu kümede olan 25.582.938 yönlü kenarı tutar. Bu, makaledeki sayımı
birebir yeniden üretme iddiası değildir. Sparse matris satırı kaynak, sütunu hedeftir.
Pozitif anatomik temas sayısı fizyolojik uyarıcı/baskılayıcı işaret değildir.

Yönelme alt devresi: 2.228 ORN, 686 ALPN, 4.064 Kenyon, 97 MBON. Devre kimliği ve
katman hash'leri checkpoint yüklerken doğrulanır. UI'nin konumsuz nöronlar ve
temsili bağlantı çizimi sınırları [kullanım rehberindedir](usage.md).

## Depolama ve gizlilik

`data/`, `models/`, `artifacts/`, ortamlar ve günlükler kişisel çalışma dizinindedir.
Bunlar Git ve Python wheel/sdist paketine dahil edilmez. İndirme dış sunuculara
standart HTTP istekleri yapar; kişisel model/eğitim yükleme veya telemetri servisi yoktur.
UI yalnızca `127.0.0.1` dinler; kimlik doğrulamalı çok kullanıcılı bir servis değildir.
LAN'a veya internete açmak bu dağıtımın hazır bir özelliği değildir.
