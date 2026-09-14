# Kaynaklar ve lisans bildirimleri

Neural Lab bağımsız bir Hashtag projesidir; aşağıdaki projelerle resmi bağlantı
veya onların onayı iddia edilmez. Uygulamanın MIT lisansı dış veri/politikaları kapsamaz.

| Kaynak | Lisans / atıf | Dağıtım şekli |
| --- | --- | --- |
| MaleCNS v1.0 | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/); FlyEM/HHMI Janelia, Cambridge, MRC LMB, Google Research; [resmi veri sayfası](https://male-cns.janelia.org/download/) | Kullanıcı resmi depodan indirir; burada kaynak URL/hash'leri vardır |
| FlyGym / NeuroMechFly | [Resmi kaynak ve lisans](https://github.com/NeLy-EPFL/flygym); [proje / bilimsel atıflar](https://neuromechfly.org/) | Ayrı bilimsel ortamda bağımlılık; HD mesh kaynak paketinin indirme mekanizmasıyla alınır |
| FlyBody | [Apache 2.0](https://github.com/TuragaLab/flybody/blob/d015e9bfe441bd90ae431bac24c55cb74bdbce26/LICENSE), TuragaLab; [resmi repo](https://github.com/TuragaLab/flybody) | Sabit commit `d015e9bfe441bd90ae431bac24c55cb74bdbce26`; wheel'e dahil değildir |
| FlyBody politika ve veri arşivleri | [GPL 3.0+](https://www.gnu.org/licenses/gpl-3.0.html), Figshare kaydının lisansı; [Whole-body physics simulation of fruit fly locomotion destek verisi, v4](https://doi.org/10.25378/janelia.25309105.v4) | Kullanıcı indirir; yerel manifeste kaynak ve hash yazılır; wheel/Git içinde yoktur |
| flybrains / JRCFIB2022M | [Resmi paket, kaynak ve varlık bildirimleri](https://github.com/navis-org/navis-flybrains) | Harici bağımlılık ve anatomi yüzeyi; upstream veri bildirimleri geçerlidir |
| MuJoCo | [Apache 2.0 kaynak](https://github.com/google-deepmind/mujoco) | Ayrı ortam bağımlılığı |
| SO-101 UVC somun yuvalı kamera adaptörü | [TheRobotStudio / SO-ARM100](https://github.com/TheRobotStudio/SO-ARM100/tree/main/Optional/SO101_Wrist_Cam_Hex-Nut_Mount_32x32_UVC_Module), Apache 2.0; [yerel lisans](so101/assets/SO-ARM100-LICENSE) | Değiştirilmemiş STL, `63eede5a636e548eb8f2854e558bd343c21db9f7` revizyonundan; `so101/assets/README.md` kaynak ve mekanik eşlemeyi içerir |
| Tic-tac-toe tahta ve X/O parçaları | Hashtag Robotics / Mert Özbaş, `Hashtag-Robotics/so101-tic-tac-toe`; [CERN-OHL-P-2.0 lisansı](tictactoe/assets/LICENSE) | `73292400ad72ea895db233715e3a093e491563f9` revizyonu; kaynak SCAD, özgün STL ve SHA-256 kayıtları `tictactoe/assets/` içindedir |
| Three.js 0.180.0 / OrbitControls | MIT; Three.js authors; [yerel lisans](ui/vendor/THREE-LICENSE.txt), [kaynak](https://github.com/mrdoob/three.js/tree/r180) | UI JavaScript dosyaları lisansı ve checksum manifestiyle paketlenir |
| uv | [MIT veya Apache 2.0](https://github.com/astral-sh/uv) | Hafif başlatıcı bağımlılığı; kendi paket lisanslarıyla kurulur |

Torch, TensorFlow, NumPy, SciPy, NAVis ve diğer geçişli bağımlılıklar kendi
lisanslarıyla ayrı ortamlara kurulur; kilit dosyalarında sürümleri bulunur.
İndirilen veri/politikaları başka bir ürünle yeniden dağıtırken ilgili kaynak
lisansını, bildirimleri ve atıf gereksinimlerini ayrıca koruyun.

Anatomiden üretilen model bir mühendislik türevidir: pozitif normalize edilmiş
ileri besleme, sentetik anten kodlaması, öğrenilmiş kenar çarpanları ve yapay
motor eşlemesi içerir. Veri sağlayıcılarının biyolojik olarak doğruladığı bir
öğrenme veya tam beyin emülasyonu değildir.
