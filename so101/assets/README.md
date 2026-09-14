# SO-101 bilek kamerası adaptörü

`so101_uvc_hexnut.stl`, TheRobotStudio/SO-ARM100 deposundaki
`Optional/SO101_Wrist_Cam_Hex-Nut_Mount_32x32_UVC_Module/stl/SO-ARM101_camera_wrist_mount.stl`
dosyasının değiştirilmemiş kopyasıdır. Kaynak revizyonu:
`63eede5a636e548eb8f2854e558bd343c21db9f7`. Lisans: Apache 2.0,
`SO-ARM100-LICENSE`. SHA-256:
`e17a626158951ac8cdf8d960962c1a3c8bf23b64635a02f88b62016fe895cef8`.

Kaynak milimetredir. `camera_mount.py`, iki M3 deliğini SO-101
`wrist_roll_follower_so101_v1.stl` üzerindeki somun yuvalarına hizalar.
Kaynak delik eksenleri (-4, -8.15, 10) ve (-4, -8.15, 18.1) mm,
robot mesh eksenleri (-5, -20.718214, 24.35) ve (3.1, -20.718214, 24.35) mm.
4 mm kalınlığındaki adaptör robotun dış montaj yüzeyine oturur.
PCB delikleri 27×27 mm, kart boyutu 32×32 mm; optik eksen kavrayıcıya
doğru 25 derece eğimlidir. Robot CAD ve adaptörün delik eksenleri test edilir.

Kart/lens görünümü temsili, mercek merkezi karttan 16 mm ileride ve dikey
görüş açısı 90 derecedir. Bunlar fiziksel kamera kalibrasyonu değildir.
Adaptör görsel geometridir; gerçek aparat kütlesi ve çarpışma geometrisi
ölçülmediği için fiziksel yük/çarpışma doğrulaması iddia edilmez.
UVC modül yalnızca RGB üretir. Mevcut algılayıcının kullandığı metrik derinlik
MuJoCo simülasyonundandır; gerçek kol için RGB poz kestirimi ayrıca gerekir.

UI'daki `calibration-reference.json` orta konum şeması, aynı deponun
`Simulation/SO101/so101_new_calib.xml` modelinde eklem aralıklarının orta noktaları
için hesaplanan eklem merkezlerinden türetilir. Kaynak dosya özeti JSON içinde
yer alır; Apache 2.0 lisansı geçerlidir. Bu şema canlı motor ölçümü değildir.
