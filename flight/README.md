# Yerel uçuş görünümü

Neural Lab → **Davranış → Uçuş · hazır politika**. Full HD canlı MuJoCo görüntüsü,
mouse ile kamera, duraklatma, yeniden başlatma ve sonraki referans rota aynı UI'dadır.
Kokuya dönüldüğünde önceki model, hedef, fizik durumu ve kamera korunur.

Uçuşu [resmi FlyBody hazır motor politikası](https://github.com/TuragaLab/flybody)
kontrol eder. MaleCNS koku devresi bu politikaya bağlı değildir; sağ panel anatomiyi
gösterir, uçuş sırasında sinir aktivitesi ve öğrenilmiş bağlantı çarpanı göstermez.
Bu görev havada, referans poz ve hızla başlar; yerden kalkış değildir.

## Kurulum / çalıştırma

Ana FlyGym ortamı değişmez. FlyBody'nin NumPy ve TensorFlow bağımlılıkları ayrı
Python 3.11 ortamındadır; Git kaynak sürümü ve bağımlılıklar `uv.lock` ile sabitlenir.

```sh
rtk proxy uv sync --project flight --locked
rtk proxy .venv/bin/python flight/download_assets.py
rtk proxy ./ui.sh
```

Model ve uçuş referansları [resmi Figshare v4 arşivinden](https://doi.org/10.25378/janelia.25309105.v4)
gelir. İki arşiv toplam 19,4 MB'dir; büyük yürüyüş veri seti indirilmez.
`data/flybody/manifest.json` dosya boyutlarını, mevcut kaynak MD5 bilgisini ve
indirilen dosyaların SHA-256 kayıtlarını tutar. Model/ortam/artifact dosyaları Git'e girmez.

TFP 0.16 ile yayımlanan modeldeki eski `Independent_ACTTypeSpec` adı, TFP 0.23'ün
uyumlu çözücüsüne eşlenir. İndirilen grafik ve ağırlık dosyaları değiştirilmez.
Politikanın dağılım ortalaması deterministik eylem olarak alınır; Acme'nin kanonik
[-1, 1] aralığı yerel eylem sınırlarına ölçeklenir. Acme, Reverb veya CUDA kurulmaz.

## Fizik ve gösterim

- Orijinal FlyBody CGS birimleri: cm, gram, saniye; UI konumu/hızı mm'ye çevirir.
- Fizik adımı 0,05 ms; kontrol adımı 0,2 ms. Kanat frekansı yaklaşık 218 Hz.
- Kanat desen üreteci + öğrenilmiş motor düzeltmeleri + MuJoCo kanat aerodinamiği.
- Kanatları görmek için hedef oynatım 0,01×. Gerçek oran RTF alanındadır;
  Full HD görüntü maliyeti bu bilgisayarda oranı yaklaşık 0,006×'e düşürebilir.
- Referans #18, #57, #20 sırayla oynar. Bölüm tamamlanınca 1,2 s sonra sonraki
  rota başlar; duraklatılmış veya izlenmeyen simülasyon ilerlemez.
- Gerçek sineğin ayrıntılı resmi mesh'i kullanılır. Referans hayalet gövde
  görüntüden çıkarılır; Arena görünümü referans yolunu gösterir.
- İkinci HTTP servisi yoktur. İzole süreçle yalnızca özel stdin/stdout JSON
  kanalları kullanılır. Bir seferde tek davranış ilerler; diğeri duraklatılır.

## Doğrulama

```sh
rtk proxy flight/.venv/bin/python flight/validate.py
# UI açık, Kokuya yönelme seçili ve eğitim işi boşta iken:
rtk proxy .venv/bin/python validate_flight_ui.py
```

`artifacts/lab/flight/validation.json`: seçilmiş üç gösterim rotası tamamlandı.
#18: 0,467 s, ortalama hata 0,216 mm; #57: 0,509 s, 0,472 mm;
#20: 0,098 s, 0,206 mm (tohum 10). Bunlar genel başarı oranı değildir.
Uzun rota araştırmasında #48 irtifa sınırına takıldı; kayıt
`long-route-exploration.json` dosyasında korunur. Yerden kalkış, tüm rotalar,
MaleCNS ile uçuş öğrenmesi veya biyolojik uçuş kontrolü doğrulanmış değildir.

`ui-validation.json`: 11 HTTP/fizik kontrolü; Full HD, gerçek zaman ilerlemesi,
duraklatma, üç mouse kamera hareketi, sonraki rota, model kimliği,
anatomik inceleme ve koku durumunun aynen korunması. Tarayıcı UI testi yapılmadı.
Çalışma günlüğü: `.runtime/flight-worker.log`.
