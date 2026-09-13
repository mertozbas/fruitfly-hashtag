# Kurulum

<a id="gereksinimler"></a>
## Gereksinimler

İlk aşama küçük UI/başlatıcı paketi, ikinci aşama bilimsel ortamdır.
`pipx install` yalnızca ilk aşamayı yapar; beyin verisi indirmez.

| Bileşen | Gereksinim |
| --- | --- |
| Başlatıcı | Python 3.11+ ve pipx |
| Doğrulanan platform | Apple Silicon macOS; geliştirme doğrulaması M4 Max üzerinde |
| Linux | Deneysel; x86_64, OpenGL/EGL veya OSMesa sürücüleri gerekir; tam Linux testi yapılmadı |
| Intel Mac | Yürüyüş doğrulanmadı; mevcut TensorFlow uçuş kilidi desteklenmiyor |
| Windows | Yerel bilimsel kurulum desteklenmez; WSL2/Linux deneysel, HD render garantisi yok |
| RAM | En az 16 GB ile planlayın, 32 GB önerilir; tam bağlantı matrisi hazırlanır |
| Disk | En az 15 GiB boş alanla başlayın; uv önbelleği ve eğitimler ek alan kullanır |
| İnternet | İlk kurulum, güncelleme ve yeni kaynak indirme için |
| Tarayıcı | WebGL destekli güncel masaüstü tarayıcı |
| Git | Klonlama ve uçuş ortamındaki sabitlenmiş FlyBody kaynağı için |

Python 3.12/3.11'i ayrı ayrı elle kurmanız gerekmez. Paketle gelen `uv` gerekirse
bunları indirir; sistem Python'unuzu değiştirmez.
[uv Python yönetimi](https://docs.astral.sh/uv/guides/install-python/).
Yönelme eğitimi Apple Silicon'da MPS, diğer ortamlarda CPU kullanır. GPU zorunlu
değildir; otomatik CUDA eğitim yolu yoktur. Uçuş ayrı TensorFlow ortamındadır.

## 1. pipx'i hazırlayın

macOS/Homebrew:

```bash
brew install pipx git
pipx ensurepath
```

Ubuntu/Debian:

```bash
sudo apt update
sudo apt install pipx git
pipx ensurepath
```

Terminali yeniden açın; `pipx --version` çalışmalı. Eski Python seçilirse kuruluma
`--python python3.12` ekleyin. [pipx rehberi](https://pipx.pypa.io/latest/how-to/install-pipx.html).
`sudo pip install` gerekmez; uygulama kullanıcı hesabında çalışır.

## 2. Uygulamayı kurun

```bash
pipx install git+https://github.com/mertozbas/fruitfly-hashtag.git
fruitfly --version
fruitfly ui
```

Klonlanmış repoda `pipx install .` kullanın. PyPI sürümü yayımlandığında
`pipx install fruitfly-hashtag` aynı işi yapar. İndirilen wheel de kurulabilir:
`pipx install ./fruitfly_hashtag-0.2.0-py3-none-any.whl`.

http://127.0.0.1:8766/ açılır. İlk açılışta kurulum ekranı gelir; veri olmadan
çalışır. Büyük indirme düğmeye bastıktan sonra başlar. Terminali açık tutun.

## 3. Beyni ve yürüyüşü kurun

**Beyni indir ve kur** sırasıyla:

1. Kilitli Python 3.12 paketlerini ayrı `.venv` içine kurar.
2. MaleCNS v1.0 anotasyon, nörotransmiter ve bağlantı tablolarını indirir.
3. Sabit kaynak sürümü, boyut ve SHA256 özetlerini doğrular.
4. Keşif matrisini, 28 seçilmiş SWC iskeletini ve anatomi yüzeyini hazırlar.
5. ORN → ALPN → Kenyon → MBON devresini oluşturur.
6. Başlangıç modeli yoksa 3.000 adım / tohum 42 ile yerelde eğitir.
7. UI geometrisini üretir; kısa gerçek fizik ve 1920×1080 render kontrolü yapar.

Bu başlangıç kontrolü altı hedeflik başarı testi değildir. İlk modelde fizik
skoru henüz boş olabilir; UI'dan yeni eğitim başlatınca görev testi de yapılır.

Günlük ekranda ve `.runtime/setup.log` içinde görünür. İndirme bittikten sonra
matris hazırlığı CPU/RAM kullanmaya devam eder; süre donanıma ve internete bağlıdır.
Bağlantı kesilirse aynı düğmeyle tekrar deneyin. MaleCNS `.part` dosyaları mümkünse
HTTP Range ile sürdürülür. Tam dosyalar yeniden indirilmeden doğrulanır. Bozuk
tamamlanmış dosyanın üzerine sessizce yazılmaz; hata konumunu gösterir.

## 4. İsteğe bağlı uçuş

Ana kurulum bitince **Uçuşu kur** düğmesi açılır. Python 3.11 / TensorFlow 2.15.1
ayrı `flight/.venv` içine kurulur. FlyBody'nin sabit commit'i GitHub'dan, politika
ve referans arşivleri Figshare'den alınır. Politika yüklenir ve kısa fizik kontrolü
yapılır. Yürüyüş ortamı değişmez; kanat çırpmayı yeniden eğitmezsiniz.
Yaklaşık 3 GB'lık resmi yürüyüş veri kümesi bu uçuş kurulumu için gerekmez.

## 5. Laboratuvar ve sonraki açılışlar

**Laboratuvarı aç** aynı adresi canlı UI'a dönüştürür. Sonraki oturum: `fruitfly ui`.
Otomatik tarayıcı istemiyorsanız `fruitfly ui --no-browser`; port doluysa
`fruitfly ui --port 8770`. Kurulum yöneticisine dönmek için `Ctrl+C`, sonra
`fruitfly ui --setup`. Aynı dizinde ikinci bir UI/kurulum eşzamanlı başlatılamaz.

## Terminalden kurulum

```bash
fruitfly setup walking
fruitfly setup flight
fruitfly doctor
fruitfly ui
```

Birlikte: `fruitfly setup all`. Durdurmak: `Ctrl+C`. `doctor` dosya/ortam varlığını
kontrol eder; bilimsel geçerlilik testi yapmaz.

```bash
fruitfly --home /Volumes/LabDisk/neural-lab setup all
fruitfly --home /Volumes/LabDisk/neural-lab ui --port 8770
```

Tüm komutlarda aynı veri dizinini kullanın. Alternatif `FRUITFLY_HOME` ortam
değişkenidir. Sistem `HOME` değerini değiştirmeyin. Veri dizini Git deposu olmamalı;
yönetilen kod buraya sürüm güncellemelerinde yerleştirilir, veriler korunur.
