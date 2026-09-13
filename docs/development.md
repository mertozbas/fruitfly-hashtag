# Geliştirme ve yayın

## Mimari

`src/fruitfly_lab/` hafif CLI ve kurulum ekranıdır; yalnızca `uv` bağımlılığı vardır.
Kök Python dosyaları, mevcut FastAPI + MuJoCo uygulamasıdır. `ui/` vendored Three.js
kullanan statik arayüzdür; Node build adımı gerekmez. `environments/walking/` Python
3.12 bilimsel ortamının ayrı `pyproject.toml` ve `uv.lock` dosyalarını tutar.
`flight/` Python 3.11 ortamıdır; TensorFlow/NumPy uyumluluğu için ayrıdır.

Wheel, bu kaynak dosyalarının **açık izin listesini** `fruitfly_lab/bundle/` içine
yerleştirir. CLI kodu kullanıcı çalışma dizinine kopyalar; bilimsel ortam o dizinde
oluşturulur. Bu yüzden site-packages içine veri/model yazılmaz. Her dosyanın özeti
`.fruitfly-bundle.json` ile izlenir; yerel kod değişiklikleri sessizce ezilmez.

Kurulum ekranı standart Python HTTP sunucusudur; host/origin kontrolü ve tek iş
sınırı vardır. Başlatma düğmesi aynı portu bilimsel FastAPI sunucusuna devreder.
Kurulum 2 saatle, tek alt komut 1 saatle sınırlanır; durdurma alt süreç grubunu
kapatır. Veri ve model işlemleri yereldir. Cloud/LLM/MCP servisi gerekmez.

## Yerel geliştirme

```bash
uv sync --locked --group dev
uv run --no-sync python -m unittest discover -s tests -v
uv run --no-sync python tools/build_docs.py --check
uv build
uv run --no-sync python -m twine check dist/*
```

Kök ortam artık hafif uygulama içindir. Bilimsel bağımlılık için **kaynak repoda
eski doğrudan `uv sync` alışkanlığını kullanmayın**; `fruitfly setup walking` ayrı
çalışma dizinini hazırlar. Paket dışı bilimsel geliştirme gerekiyorsa ortam
manifestini inceleyip izole test dizini kullanın. `ui.sh` eski yerel geliştirici
ortamını açan yardımcıdır; son kullanıcı akışı `fruitfly ui` komutudur.

Doküman Markdown'ını değiştirdikten sonra `uv run python tools/build_docs.py`
çalıştırın. `docs/index.html` çevrimdışı tek sayfa rehberidir; README ve bütün rehber
bölümlerinden üretilir. CI eski kalan HTML'i yakalar.

## Paket doğrulaması

```bash
pipx install ./dist/fruitfly_hashtag-0.2.0-py3-none-any.whl
fruitfly --home /tmp/neural-lab-clean ui --port 8770 --no-browser
```

Boş dizinde `/` kurulum ekranını, `/guide/index.html` kılavuzu, `/api/setup`
hazır olmayan durumu döndürmelidir. Beyin verisi kendiliğinden indirilmemelidir.
Test paketi wheel/sdist'te `data/`, `models/`, `.venv/`, `.runtime/`, anahtar veya
kişisel eğitim bulunmadığını kontrol eder. Ağ indirmeleri ve bilimsel simülasyon
birim testlerinde çalıştırılmaz; ayrıca temiz bilimsel kurulum kontrolü gerekir.

## GitHub / PyPI

GitHub deposu: https://github.com/mertozbas/fruitfly-hashtag
PyPI adı: `fruitfly-hashtag`. Paket build'i PyPI yayını anlamına gelmez.

1. Sürümü `pyproject.toml` ve `src/fruitfly_lab/__init__.py` içinde artırın.
2. Rehberi üretin, test/build/metadata kontrolünü çalıştırın. Arşiv listesini inceleyin.
3. Kaynak değişikliklerini main'e pushlayın; CI sonucunu bekleyin.
4. `v0.2.0` gibi etiket ve GitHub release oluşturun; doğrulanmış wheel/sdist ekleyin.
5. PyPI için aşağıdaki iki yöntemden birini kullanın; kimlik bilgilerini repoya koymayın.

**Trusted Publishing:** PyPI hesabında pending publisher oluşturup owner
`mertozbas`, repo `fruitfly-hashtag`, workflow `publish.yml`, environment `pypi`
tanımlayın. Sonra GitHub Actions'tan yayın işini elle başlatın. Bu işlem otomatik
etiket push'unda yayın yapmaz. [PyPI resmi rehber](https://docs.pypi.org/trusted-publishers/).

**Yerel token:** Ortamda yetkili `TWINE_USERNAME=__token__` ve `TWINE_PASSWORD`
güvenle tanımlıysa `uv run python -m twine upload dist/*` kullanılır. Token'ı
komut satırına, günlük dosyasına veya README'ye yazmayın.

Yayın sonrası `pipx install fruitfly-hashtag==0.2.0` ile **gerçek PyPI kaynağından**
yeni izole kurulum doğrulanmalıdır. Kaynak kod, paket meta verisi ve PyPI hash'leri
uyumlu olmalıdır. PyPI sürümü değiştirilemez; hata düzeltmesi yeni sürüm gerektirir.
