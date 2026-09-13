MaleCNS v1.0 verisiyle yerel keşif ortamı kuruldu. Dosyalar `data/male-cns-v1.0/`, bağımlılıklar bu projeye özel `.venv/` içinde. Python 3.12 ve paket sürümleri `pyproject.toml` / `uv.lock` ile sabitlendi.

**Neural Lab arayüzü:** `rtk proxy ./ui.sh` → <http://127.0.0.1:8766/>. Aynı ekranda canlı MuJoCo gövdesi, gerçek soma konumlarında model aktivitesi, bağlantı ağırlığı karşılaştırması ve eğitim kontrolleri. [Arayüz kullanımı ve deney durumları](LAB.md).

**Yeni: yürüyen sinek ve ilk koku eğitimi.** Canlı açılış: `rtk proxy ./sim.sh --policy trained`. Yeniden eğitim: `rtk proxy ./teach.sh`. [Simülasyon ve eğitim rehberi](SIMULATION.md), [eğitim öncesi/sonrası videolar](http://127.0.0.1:8765/simulation/). Bu deney, MaleCNS'ten çıkarılan 7.075 nöronluk basitleştirilmiş alt devreyi kullanır; tam beyin emülasyonu değildir.

**Görünümleri açmak**

```bash
cd /Users/macmert/fruitfly-hashtag
rtk proxy ./run.sh
```

Tarayıcıdan <http://127.0.0.1:8765> adresini aç. Sunucu yalnızca bu bilgisayardaki `127.0.0.1` adresini dinler ve `artifacts/` klasörünü sunar. Terminalde `Ctrl+C` ile durur. Port zaten kullanılıyorsa ikinci kopyayı başlatmak yerine mevcut adresi aç.

- **Nöronlar:** 28 gerçek SWC iskeleti, beyin ve VNC yüzeyiyle birlikte.
- **Tüm hücre gövdeleri:** soma konumu bulunan 139.662 kayıt. Noktalar nöron dalları değildir.
- **Tek nöron çifti:** DNge104 sağ/sol; ayrıntılı ve yakın inceleme için.
- **Bağlantılar:** sınıflar arası temas sayıları ve 12781'in en güçlü giriş/çıkış ortakları.

Sürükleyerek döndür, tekerlekle yakınlaş. Sağdaki etiketlere tıklayarak nöronları/sınıfları gizle; çift tıklayarak birini ayır. Kamera simgesi PNG dışa aktarır. HTML dosyalarının her biri Plotly kodunu içerir; sunucu olmadan dosyaya çift tıklayarak ve internet olmadan da açılabilir. Alt kısımdaki resmî atlas bağlantısı internet kullanır.

**Veriyle çalışmak**

```bash
cd /Users/macmert/fruitfly-hashtag
rtk proxy ./lab.sh
```

JupyterLab başlangıç defterini açar. Hücreleri `Shift+Enter` ile çalıştır. Jupyter'nin yerel oturum bağlantısını kullan; `Ctrl+C` ile sunucuyu durdur. Yeni oturumda deftere güvenme bildirimi çıkarsa kendi yerel `baslangic.ipynb` dosyan olduğunu doğrulayarak aç. Defterin beş kod hücresi kurulum sırasında hatasız çalıştırıldı.

Python örnekleri:

```python
from brain import find_neurons, partners, plot_neurons, graph

find_neurons("DNge104")
partners(12781, direction="in", limit=15)
partners(12781, direction="out", limit=15)
fig = plot_neurons([12781, 556329], context=False)
fig.show()
```

Yeni bodyId seçildiğinde `plot_neurons` eksik SWC dosyasını resmî depodan indirir, nesne sürümünü sabitler, CRC32C ile doğrular ve önbelleğe alır. Çok sayıda nöronu tek grafikte çizmek tarayıcıyı yavaşlatabilir; küçük devrelerle başla.

**İndirilenler ve boyut**

Ana bağlantı dosyası yaklaşık 1,05 GB, anotasyon dosyası 14,5 MB, hücre düzeyindeki nörotransmiter tablosu 43,3 MB. Ayrıca 28 seçilmiş nöronun iskeleti ve `flybrains` paketinin JRCFIB2022M anatomi yüzeyi yerelde. Türetilen sparse bağlantı matrisi ve dört HTML görünümü de hazır. Simülasyon/eğitim paketleriyle birlikte ortam ve dosyalar yaklaşık 2,9 GiB disk alanı kullanır; `uv`'nin paylaşılan paket önbelleği bu toplama dahil değildir.

Tek bir eğitilmiş “3 GB beyin modeli” indirilmedi. [Resmî indirme listesinde](https://male-cns.janelia.org/download/) yaklaşık 2,7 GB'lık `tbar-neurotransmitters` tablosu da var; bu sinaps düzeyinde tahmin verisi. Şimdiki anatomi/bağlantı incelemesi için hücre düzeyindeki tablo yeterli olduğundan bu dosya, ham elektron mikroskobu hacmi ve bütün nöronların geometrileri indirilmedi. Tüm geometriyi çevrimiçi Neuroglancer atlasından seçerek görüntüleyebilirsin.

Kurulu anatomi araçları: NAVis 1.12.0, flybrains 0.6.3, Plotly 7.0.0, JupyterLab 4.6.3, neuprint-python 0.6.3, Neuroglancer 2.41.2, Brian2 2.10.1, PyArrow 25.0.1 ve SciPy 1.18.1. Yerel örnekler neuPrint hesabı veya token istemez. Brian2 kurulumu tek bir sentetik nöronla kontrol edildi. Sonradan eklenen PyTorch/FlyGym koku deneyi için [SIMULATION.md](SIMULATION.md) dosyasına bak; bu deney ayrıntılı bir Brian2 tam beyin simülasyonu değildir.

**Veriyi doğru yorumlamak**

- Ham bağlantı tablosunda 151.856.684 satır bulunur; tüm uçlar sınıflandırılmış nöron değildir.
- Yerel keşif matrisi `superclass` alanı dolu 166.700 kaydı ve iki ucu da bu kümede olan bağlantıları tutar: 25.582.938 yönlü kenar, 124.177.617 sinaptik temas. Bu filtre makalenin 166.691 nöronluk sayımını birebir yeniden üretmez.
- Matris satırı kaynak/presynaptic, sütunu hedef/postsynaptic nörondur. Ağırlıklar pozitif anatomik temas sayısıdır; fizyolojik işaret, bağlantı gecikmesi, reseptör dinamiği veya öğrenilmiş parametre değildir.
- 27.038 kayıtta soma konumu yok; nokta görünümüne dahil edilmez. SWC dosyalarında birden fazla kök bileşeni bulunabilir; aralarına yapay bağlantı eklenmez.
- SWC ve soma koordinatları 8 nm biriminden, flybrains yüzeyi nm biriminden µm'ye dönüştürülür. Görüntüleme için z ekseninin yönü ters çevrilir; kayıtlı koordinatlar değiştirilmez.
- Görüntü, anatomiyi gösterir; elektriksel aktiviteyi, öğrenmeyi veya yaşayan sineğin davranışını göstermez. Bir dinamik model ayrıca seçilip sınanmalıdır.

**Doğrulama ve yeniden üretme**

Orijinal dosyaların SHA256 ve sunucu CRC32C kontrolleri geçti. 28 SWC dosyasında düğüm/ebeveyn ilişkileri ve sayısal koordinatlar kontrol edildi. Örnek 12781 nöronunun 1.751 giriş ve 1.426 çıkış ortağı, sparse matris ile ham Feather dosyası arasında birebir eşleşti. Dört yerel görünüm HTTP üzerinden açıldı; Jupyter defteri çalıştırıldı. Kayıtlar: `data/male-cns-v1.0/validation.json`, `derived/runtime-checks.json`, `skeleton-manifests/` ve `artifacts/validation.json`.

```bash
rtk proxy uv sync --locked
rtk proxy .venv/bin/python prepare.py
```

`prepare.py` mevcut doğrulanmış SWC'leri ve bağlantı önbelleğini kullanır; HTML görünümleri yeniden üretir. Mevcut başlangıç defterini değiştirmez. Temel üç Feather dosyasının zaten yerelde bulunmasını bekler; kaynak adresleri ve nesne sürümleri `data/male-cns-v1.0/manifest.json` içinde kayıtlıdır.

Araştırma notları ve bilimsel sınırlar: [arastirma.md](arastirma.md). Resmî kaynaklar: [MaleCNS](https://male-cns.janelia.org/download/), [NAVis](https://navis-org.github.io/navis/stable/), [flybrains](https://github.com/navis-org/navis-flybrains).
