# Hashtag Neural Lab

**Sinek simülasyonu, canlı nöron aktivitesi ve yönelme eğitimi için yerel laboratuvar.**

Tek ekranda HD MuJoCo simülasyonu, MaleCNS anatomisinden türetilen devre,
bağlantı inceleme, eğitim ilerlemesi ve fizik testleri. Nörona veya bağlantıya
tıklayın; kaynağını ve modeldeki değerlerini görün. Eğitiminizi ayrı kaydedip
seçtiğiniz modeli yürüyüşte veya uçuşta çalıştırın.

Bu repo **büyük beyin verilerini, kişisel eğitimleri ve Python ortamlarını içermez**.
Küçük uygulama paketi dağıtılır. İlk açılış ekranı ortamları kurar, verileri resmi
kaynaklardan indirir ve ilk modeli sizin bilgisayarınızda eğitir. API anahtarı
gerekmez; kişisel eğitimler internete yüklenmez.

> Tam beyin emülasyonu değildir. MaleCNS'ten türetilen **7.075 nöronluk basitleştirilmiş
> yönelme ağıdır**. Yürüyüşte FlyGym bacak kontrolcüsü, uçuşta FlyBody hazır kanat
> politikası kullanılır. Eğitim yön kararını değiştirir; biyolojik öğrenme veya
> kanat eğitimi değildir. [Bilimsel kapsam](docs/training.md#bilimsel-kapsam).

## Hızlı başlangıç

Doğrulanan tam platform **Apple Silicon macOS**. Linux deneysel; Windows yerel
simülasyonu desteklenmez. Python **3.11+**, **pipx** ve uçuş için **Git** gerekir.
Bilimsel kurulum için **15 GiB boş disk**, en az **16 GB RAM**, tercihen **32 GB RAM**
ile planlayın. Bunlar kapasite önerileridir; 16 GB cihaz performansı ölçülmüş değildir.
[Ayrıntılı gereksinimler ve Linux notları](docs/installation.md).

macOS'ta Homebrew kullanıyorsanız:

```bash
brew install pipx git
pipx ensurepath
```

Terminali yeniden açın. Sonra aşağıdaki yollardan **birini** seçin.

### A — Repoyu klonlayın

```bash
git clone https://github.com/mertozbas/fruitfly-hashtag.git
cd fruitfly-hashtag
pipx install .
fruitfly ui
```

### B — GitHub'dan doğrudan pipx ile

```bash
pipx install git+https://github.com/mertozbas/fruitfly-hashtag.git
fruitfly ui
```

### C — PyPI sürümüyle

PyPI yayını tamamlandıktan sonra aynı paket aşağıdaki şekilde kurulur. Paket
bulunamazsa GitHub yolunu kullanın; GitHub ve PyPI yayını ayrı işlemlerdir.

```bash
pipx install fruitfly-hashtag
fruitfly ui
```

Tarayıcıda **http://127.0.0.1:8766/** açılır. Açılmazsa adresi kendiniz girin.
Terminali açık tutun; `Ctrl+C` ile durdurun.

1. **Beyni indir ve kur** düğmesine basın. Python 3.12, bilimsel paketler,
   yaklaşık **1,11 GB** MaleCNS tablosu ve seçilmiş geometriler hazırlanır.
   İndirmeler SHA256 ile doğrulanır. İlk 3.000 adımlık model yerelde eğitilir;
   kısa bir gerçek fizik / HD render kontrolü yapılır. Bu, başarı oranı testi değildir.
2. İsterseniz **Uçuşu kur** seçin. Ayrı Python 3.11 / TensorFlow ortamı ve yaklaşık
   **19,4 MB** resmi FlyBody arşivi indirilir. Python paketleri ayrıca yer kaplar.
3. **Laboratuvarı aç** düğmesine basın. Aynı adres canlı UI'a dönüşür.
4. **Davranış** ve **Simülasyondaki model** seçin; hedefi değiştirip izleyin.
   Üstteki **Rehber** bağlantısı kılavuzu çevrimdışı açar.

Sonraki açılışlarda `fruitfly ui` yeterlidir. Kurulum ekranına dönmek için önce
`Ctrl+C`, sonra `fruitfly ui --setup` çalıştırın.

## İlk eğitiminizi yapın

1. **Davranış → Kokuya yönelme** seçin.
2. Hedefi **X=12, Y=4 mm** yapıp **Hedefi uygula** düğmesine basın.
3. **Adım=3000**, **Tohum=42** ile başlayın. Adım ağırlık güncelleme sayısıdır;
   tohum tekrarlanabilir rastgele başlangıcı belirler.
4. **Eğitimi başlat** seçin. Önceki model ayrı korunur; canlı simülasyon eğitim
   boyunca seçili modeli kullanmaya devam eder.
5. Öğrenme kaybı ve ardından **6 fizik koşulundaki** test hesaplanır. Tamamlanmasını
   bekleyin; düşük kayıp tek başına başarılı hareket demek değildir.
6. **Yeni modeli simülasyona al** düğmesine basın.
7. Beyin panelinde **Δ Ağırlık** seçin. Mevcut bağlantıların anatomik başlangıca
   göre değişen çarpanlarını görün. **Yeni anatomik bağlantı üretilmez.**
8. Model menüsünden eski ve yeni koşuları aynı hedefte karşılaştırın.

Her yeni eğitim aynı anatomik başlangıçtan başlar; seçili modelin kaldığı yerden
devam etmez. Hedef X/Y canlı değerlendirme içindir; eğitim veri kümesini değiştirmez.
Yeni koku türü, serbest ödül fonksiyonu veya kullanıcı veri kümesi tanımlama henüz yoktur.

Uçuş kuruluysa **Uçuş · beyin bağlı** seçip aynı akışı kullanın. Eğitim sonrası bu
kez uçuş hedefleri değerlendirilir. Sinek havada başlar; kalkış, iniş ve irtifa
öğrenimi bu sürümün kapsamı dışındadır. [Tam eğitim rehberi](docs/training.md).

## Rehber dizini

| Konu | Kılavuz |
| --- | --- |
| Gereksinimler, pipx, ilk kurulum, disk ve port | [Kurulum](docs/installation.md) |
| Mouse, metrikler, nöron ve bağlantılar | [UI kullanımı](docs/usage.md) |
| Eğitim, uçuş, karşılaştırma ve bilimsel sınırlar | [Eğitim](docs/training.md) |
| URL'ler, boyutlar, doğrulama, veri dosyaları | [Veriler ve modeller](docs/data.md) |
| Hatalar, güncelleme, yedekleme, kaldırma | [Sorun giderme](docs/troubleshooting.md) |
| Geliştirme, build ve yayın | [Geliştirici rehberi](docs/development.md) |
| Kaynaklar ve ayrı lisanslar | [Üçüncü taraf bildirimleri](THIRD_PARTY_NOTICES.md) |

Kılavuz paketin içindedir: **`fruitfly docs`**. Mevcut görevler tüm kaynaklar ve
ortamlar hazırlandıktan sonra internetsiz çalışır; yeni indirme/güncelleme internet ister.

## Veriler nerede?

Varsayılan **`~/.fruitfly-hashtag/`** dizini repo ve pipx ortamından ayrıdır:

```text
~/.fruitfly-hashtag/
├── docs/                   # Çevrimdışı rehber ve Markdown
├── data/                   # Resmi MaleCNS ve FlyBody indirmeleri
├── models/odor_navigation/ # Yerelde oluşturulan başlangıç devresi/modeli
├── models/lab_runs/         # Her kişisel eğitim ayrı klasör
├── artifacts/              # Türetilen geometri ve değerlendirme çıktıları
├── .venv/                  # Python 3.12: yürüyüş/eğitim
├── flight/.venv/           # Python 3.11: isteğe bağlı uçuş
└── .runtime/               # Kurulum ve çalışma günlükleri
```

Farklı disk için **her komutta aynı `--home` değerini, komut adından önce** yazın.
Git deposunu veri dizini olarak vermeyin.

```bash
fruitfly --home /Volumes/LabDisk/neural-lab ui
fruitfly --home /Volumes/LabDisk/neural-lab doctor
```

Paket kaldırılınca veya yükseltilince kişisel eğitimler silinmez.
[Yedekleme ve güncelleme](docs/troubleshooting.md).

## Lisans ve kaynaklar

Orijinal kod [MIT](LICENSE). MaleCNS verisi **CC BY 4.0**, FlyBody kodu **Apache 2.0**,
Figshare politika/veri arşivleri **GPL 3.0+**, vendored Three.js **MIT** lisansındadır.
Dış veriler uygulamanın MIT lisansına dönüşmez; veri ve politikalar wheel'e dahil
edilmez. Atıflar: [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

[MaleCNS](https://male-cns.janelia.org/download/) · [FlyGym](https://neuromechfly.org/)
· [FlyBody](https://github.com/TuragaLab/flybody)
· [Politika/veri arşivleri](https://doi.org/10.25378/janelia.25309105.v4)
