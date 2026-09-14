# Sorun giderme, bakım ve yedekleme

Önce çalışan terminalin günlüğünü ve `fruitfly doctor` çıktısını inceleyin.
Aşağıdaki işlemlerde uygulama sürümü ile kişisel veri dizinini ayrı tutun.

[Rehber dizini](README.md) · [Kurulum](installation.md) · [Kullanım](usage.md) · [Eğitim](training.md)

## Komut bulunamıyor

`fruitfly: command not found`: `pipx ensurepath` çalıştırıp terminali yeniden açın.
`pipx list` içinde `fruitfly-hashtag` görünmeli. `pipx install` hatası için Python
sürümünü kontrol edin; Python 3.11+ gerekir. Paket PyPI'de bulunmuyorsa README'deki
GitHub veya yerel wheel yolunu kullanın.

## Port veya çalışma dizini meşgul

8766 doluysa ikinci sunucu mevcut oturumu durdurmaz. Yeni dizinde yeni port seçin:
`fruitfly --home ~/neural-lab-second ui --port 8770`. Aynı veri dizini kilitliyse
önce o dizini kullanan terminalde `Ctrl+C` ile durdurun. Kilit dosyasını silmek
gerekmez; işletim sistemi süreç bitince kilidi bırakır.

## İndirme kesildi / hash hatası

İnternet ve boş diski kontrol edip aynı kurulum düğmesini tekrar kullanın.
MaleCNS yarım indirmeleri mümkünse devam eder. Tam dosya SHA256 uyuşmuyorsa hata
konumunu gösterir; uygulama üzerine yazmaz. O dosyayı yedek bir konuma taşıyıp
kurulumu tekrar başlatın. Manifest hash'ini dosyaya uydurmak için değiştirmeyin.
Nesne generation kaynaktan kaldırıldıysa geliştiricinin kaynak manifestini güncellemesi
gerekir; program sessizce başka veri sürümüne geçmez.

## Siyah görüntü / OpenGL / EGL hatası

Önce terminal ve `.runtime/setup.log` içindeki son hata; uçuşta ayrıca
`.runtime/flight-worker.log`. macOS'ta masaüstü oturumu ve Apple Silicon doğrulanan
yoldur. Linux otomatik `MUJOCO_GL=egl` kullanır; uygun sistem sürücüleri gerekir.
Yazılımsal render isteyen Linux kurulumunda OSMesa sistem kütüphanesi kuruluysa
`MUJOCO_GL=osmesa fruitfly ui` denenebilir. Bunlar Linux'ta doğrulanmış performans
vaadi değildir. Tarayıcı WebGL kapalıysa beyin paneli de çizilemez.

## Kurulum bitti ama UI açılmadı

`fruitfly doctor` ile eksikleri görün. Bu yalnızca varlık kontrolüdür; çalışma
başarısını kanıtlamaz. Terminaldeki Python/render hatasını düzeltin, sonra
`fruitfly ui --setup` içinden kurulum düğmesini yeniden kullanın. Tam dosyalar
doğrulanır ve mevcut başlangıç modeli yeniden eğitilmeden korunur.

## Uçuş açılamıyor

Önce `fruitfly setup walking`, sonra `fruitfly setup flight`. Git'in kurulu
olduğunu kontrol edin. Python 3.11 uçuş ortamıyla Python 3.12 yürüyüş ortamını
karıştırmayın; birine elle farklı NumPy/TensorFlow sürümü kurmayın. Intel Mac
uçuşu desteklenmez. Hazır politika yükleme kontrolü kanat eğitimi değildir.

## Eğitim başarısız / listede yeni model yok

UI işinin son durumunu ve `models/lab_runs/<koşu>/training.log` dosyasını okuyun.
`complete` olmadan yeni model başarılı sonuç olarak sunulmaz. 600 saniye sınırında
yavaş cihazda daha az adım deneyin. Bellek yetersizse başka ağır uygulamaları
kapatın. Önceki başarılı model menüde kalır; yarım koşu kaldığı adımdan devam etmez.

## Güncelleme

Önce bütün Neural Lab oturumlarını ve eğitimleri durdurun; aşağıdaki yollardan
kurduğunuz kaynağa uygun olanı kullanın:

```bash
pipx upgrade fruitfly-hashtag
```

Klonlanmış repo için `git pull`, sonra repo içinde `pipx install --force .`.
Kaynak değiştirmek için `pipx install --force git+https://github.com/mertozbas/fruitfly-hashtag.git`.
Ardından `fruitfly ui --setup` ile ortamların kilitli sürümlerini tekrar eşitleyin.
Yönetilen kod güncellenir; `data/`, `models/`, kişisel değerlendirmeler silinmez.
Yönetilen bir kod dosyasını elle değiştirdiyseniz üzerine yazmak yerine hata verir;
değişikliği yedekleyin veya yeni `--home` seçin.

## Yedekleme ve geri dönme

UI kapalıyken tüm `~/.fruitfly-hashtag/` klasörünü başka diske kopyalamak en kolay
yedektir. En az `models/`, `data/` manifestleri, `.fruitfly-bundle.json` ve ilgili
`artifacts/` sonuçlarını koruyun. Farklı bilgisayara taşırken `.venv` klasörlerini
taşımak yerine yeni makinede kurulumu yeniden yapın. Koşu klasörlerini bütün taşıyın.

Eski uygulama sürümüne dönmek için kayıtlı wheel'inizi `pipx install --force
./fruitfly_hashtag-0.2.1-py3-none-any.whl` biçiminde kurun. Gelecekte devre şeması
değişirse checkpoint uyumluluğunu ayrıca kontrol edin; eski veri dizinini yedekte tutun.

## Kaldırma

```bash
pipx uninstall fruitfly-hashtag
```

Bu komut çalışma dizininizi silmez. Verileri kaldırmak isterseniz önce eğitimleri
yedekleyin, sonra seçtiğiniz `--home` klasörünü dosya yöneticisinden kaldırın.
`uv` ortak önbelleği başka projelerce kullanılabilir; tüm önbelleği gelişigüzel silmeyin.
