# Bilimsel çalışma zamanı kontrolleri

Bu testler paket başlatıcısının hafif ortamından ayrıdır. Kurulu yürüme ortamıyla:

```bash
.venv/bin/python -m unittest discover -s tests/scientific -v
```

İndirilmiş anatomi gerekmez. Yapay küçük devreyle giriş/çıkış sözleşmesi,
checkpoint bütünlüğü, anatomik bağlantı maskesi, kazanç sınırları ve piksel girdisi
sınanır. Bunlar fizik başarısını kanıtlamaz. Fizik karşılaştırması:

```bash
.venv/bin/python lab_tasks.py --task vision --model models/lab_runs/KOŞU_KİMLİĞİ
```

Son komut koşunun `evaluation.json` dosyasını aynı modelle yeniden üretir.
Eski raporu korumak istiyorsanız önce kopyasını alın.
