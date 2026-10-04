# AeroPatch — Manuel Test Kitabı

> **Bu kitap ne için:** Sistemi *kendiniz* deneyin. Her adımda bir **✅ Beklenen** bloğu
> var; gördüğünüz çıktı oraya uyuyorsa yolundasınız. Uymazsa **Sorun Giderme** bölümüne bakın.
> Toplam süre ~20 dk · Test 1: 5 dk · Test 2: 10–15 dk.

---

## 0) Sistem 30 saniyede ne yapıyor?

```
Robot elips yörüngede devriye geziyor (PID + odometri, Kp=2.2 baseline)
  → zemin ıslanır: teker patinaj yapar → ENCODER BUNU GÖREMEZ, robot savrulur
  → Kenar algılayıcı (saf matematik, LLM yok) ~1 sn'de fark eder → ALARM (S > 0.45)
  → 15 ms SONRA (bulutu beklemeden): LOCAL FALLBACK — Kp↓1.5, Kd↑0.22, hız %35
  → Aynı anda telemetri buluta gider (Nemotron + Tavily hava araması)
  → Nemotron teşhis → yama 5–14 s'te döner (ince ayar) → üzerine yazılır + RESYNC
  → (mavi iz sıfırlanır: mavi≡kırmızı, SLIP_GAP ~0 — RViz'de toparlanma görünür)
  → Skor tekrar S≥0.85 çıkarsa: ESKALASYON (0 ms, Kp↓1.0) — devrilme engellenir
  → Skor S<0.20'de 10 sn stabil kalırsa: RECOVER → baseline restore (Kp=2.2)
```

İki katmanı karıştırmayın:

| Katman | Ne çalışır | Ne zaman |
|---|---|---|
| **Kenar (edge)** | Saf matematik + PID — çok hafif, milisaniyeler | her zaman, 50 Hz |
| **Bulut** | Nemotron + Tavily — ağır LLM | yalnızca ALARM anında |

---

## TEST 1 — Faz 1: Windows'ta saf Python demosu (5 dk, WSL gerekmez)

### 1.1 Hazırlık

Windows terminalinde (PowerShell/cmd), proje klasöründe:

```
cd d:\.gemini\antigravity-ide\scratch\nebius
python --version                   ← 3.10+ olmalı
pip install -r requirements.txt    ← kuruluysa saniyeler içinde geçer
```

### 1.2 Birim testleri

```
python -m pytest tests/ -q
```

✅ **Beklenen:** ~30 sn içinde `22 passed` özeti (asıl kriter: **0 failed**).

Neler test ediliyor: PID hot-swap, fizik motoru (kayma→savrulma), anomali algılayıcı
(kaymada alarm ÜRETİR, kuru zeminde ÜRETMEZ — yanlış alarm testi), mock bulut
sözleşmesi, uçtan-uca akış.

### 1.3 Ana demo

```
python -m edge.run_demo --mock --duration 20 --slip-at 8 --report demo_report.png
```

**Nasıl çalışır:** 20 sn'lik fizik saniyeler içinde hesaplanır ama her bulut çağrısı
GERÇEKTEN 350–800 ms uyur (gerçekçi gecikme) → toplam ~15–30 sn sürer.

Gerçek çıktı örneği (event_id'ler ve tam sayılar sizde biraz farklı olur):

```
====================================================================
AeroPatch — Edge anomaly detection -> Nebius/Nemotron + Tavily patch
  mode        : MOCK CLOUD (nemotron+tavily simulation)
  disturbance : left traction 0.45 @ t=8.0s
  region      : Kadikoy, Istanbul, TR (Tavily will fetch live weather)
====================================================================
[t=  0.00s] cte= 0.00 score=0.10 v=0.03 mode=OK
[t=  5.00s] cte= 0.03 score=0.01 v=0.22 mode=OK        ← normal devriye
  !! DISTURBANCE at t=8.0s: left wheel traction dropped to 0.45 (wet surface)
  >> ALARM: physical deviation! Dispatching telemetry to cloud...
[t= 10.00s] cte= 0.00 score=0.40 v=0.06 mode=SAFE       ← yama gelene dek yavaş
  .. waiting for cloud patch (extending simulation)
  >> PATCH in 497 ms: Traction loss detected: odometry reports 0.025 m/s more ...
[t= 20.30s] cte= 0.06 score=0.70 v=0.06 mode=OK        ← yama uygulandı
--------------------------------------------------------------------
EVENT TIMELINE:
  t=   8.00s  DISTURBANCE    left traction -> 0.45
  t=   9.20s  ALARM          score=0.64 event=evt-...
  t=  20.30s  PATCH_APPLIED  latency_ms=497 kp=2.351 slip_comp=-0.25
  t=  21.46s  ALARM          score=1.01 event=evt-...   ← slip sürdükçe yeni tur
  t=  21.86s  PATCH_APPLIED  latency_ms=420 kp=2.884 slip_comp=-0.591
  t=  25.56s  ALARM          score=1.35 event=evt-...
  t=  26.18s  PATCH_APPLIED  latency_ms=644 kp=3.542 slip_comp=-0.608
--------------------------------------------------------------------
alarms=3  patches=3  recovery=0.52s  max_cte=0.08m  final_cte=0.06m
[report] saved -> demo_report.png
DONE.
```

**Satır satır ne oluyor:**

- `cte` = yörüngeden sapma [m] · `score` = anomali skoru · `v` = hız
- `!! DISTURBANCE` → sol teker tutuşu 0.45'e düştü (yağmurlu zemin)
- `score` 0.60 eşiğini ardışık 5 örnek geçince → `>> ALARM` (algılama gecikmesi ~1.2 sn)
- `mode=SAFE` → yama beklerken robot 0.05 m/s'a kısılandı (güvenli mod)
- `>> PATCH in 497 ms` → mock bulut teşhis koydu, yeni kazançlar döndü
- **3 alarm/yama turu** görülür — bu tasarım gereği: slip fiziksel olarak sürdükçe
  skor yeniden yükselir, bulut kazançları kademeli sertleştirir (Kp 2.35→2.88→3.54)

✅ **Beklenen:**
- Sıra EVENT TIMELINE'da: `DISTURBANCE → ALARM → PATCH_APPLIED`
- `alarms ≥ 1`, `patches ≥ 1`, **`final_cte < 0.15 m`** (toparlanma kanıtı)
- `demo_report.png` klasörde oluştu

### 1.4 Grafik raporu okuma — `demo_report.png` (6 panel)

| # | Panel | Ne gösterir | Neye dikkat |
|---|---|---|---|
| 1 | Trajectory | Elips referans + gerçek iz + odometri DR | Kırmızı **X** = bozulma noktası; yeşil kesikli çizgi (odom) mavi ize yalpalayınca ayrılır |
| 2 | Cross-track error | Yörüngeden sapma [m] | Kırmızı çizgi sonrası yükselir, yeşil çizgi (yama) sonrası düşer |
| 3 | Anomaly score | Kenar algılayıcı skoru | 0.60 kırmızı kesikli = alarm eşiği |
| 4 | Speed mismatch | v_odom (encoder) vs v_true (yer) | **SLİP İMZASI**: encoder 0.22 m/s derken robot gerçekte yavaş |
| 5 | Rotational mismatch | omega_odom vs omega_true | Kayan tekerin dönme sapması |
| 6 | Localization innovation | \|gerçek − odom DR\| [m] | Ölü hesap hatası kaymayla büyür |

### 1.5 Varyasyonlar — parametreleri anlamanın en hızlı yolu

| Komut (hepsi `python -m edge.run_demo` ile başlar) | Ne değişir | Beklenti |
|---|---|---|
| `--slip 0.9` | Teker neredeyse hiç tutmaz | Daha erken alarm, daha büyük max_cte |
| `--slip 0.2` | Hafif kayma | Alarm hiç gelmeyebilir (eşik altı) — bu İYİ: gereksiz alarm yok |
| `--weather clear` | Bulut "hava açık" görür | Teşhis metni değişir, yama benzer kalır |
| `--threshold 0.9` | Algılayıcı toleranslı | Alarm gecikir veya gelmez |
| `--realtime --show` | Gerçek zamanlı oynatım | Jüri videosu: bozulmayı saniye saniye izlersiniz |

---

## TEST 2 — Faz 2: WSL'de ROS2 dağıtık demo (10–15 dk)

Fark: aynı mantık artık **5 ayrı ROS2 düğümü** olarak topic'ler üzerinden ve
gerçek süreçler halinde çalışıyor (bulut mock ama sözleşme birebir aynı).

### 2.0 WSL penceresi açın ve AÇIK TUTUN ⚠

```
wsl -d Ubuntu-22.04
cd /mnt/d/.gemini/antigravity-ide/scratch/nebius
```

> **Önemli:** Tüm WSL pencereleri kapanırsa VM boşta kalır ve arka plandaki ROS
> süreçlerini öldürür. Test bitene kadar bu pencere açık kalsın.

### 2.1 Sistemi başlatın

```
bash wsl/ros_start.sh
```

✅ **Beklenen:**
```
LAUNCHED_PID=12345
LAUNCH_ALIVE
```

### 2.2 Düğümlerin ayağa kalktığını görün

```
bash wsl/tail_launch.sh
```

✅ **Beklenen** (logda en az bu 4 satır; başlarında zaman damgası olur):
```
[sim_node]: sim_node ready (50 Hz physics, wheel-slip disturbance model)
[controller_node]: controller_node ready (PID path follower)
[monitor_node]: monitor_node ready (pure-math anomaly detector)
[bridge_node]: bridge_node ready (MOCK cloud (nemotron+tavily sim))
```

### 2.3 Topic haritası

```
source /opt/ros/humble/setup.bash
source ~/aeropatch_ws/install/setup.bash
ros2 topic list
```

| Topic | Yayınlayan | İçerik |
|---|---|---|
| `/odom` | sim_node | Encoder odometrisi — **slip'i göremez** |
| `/ground_truth` | sim_node | Gerçek poz (harici lokalizasyon) |
| `/cmd_vel` | controller_node | PID hız komutu |
| `/anomaly_score` | monitor_node | Canlı anomali skoru |
| `/patch/request` | monitor_node | ALARM anında buluta giden telemetri |
| `/patch/response` | bridge_node | Buluttan dönen yama (Kp/Kd/slip_comp…) |
| `/slip_state` | sim_node | Anlık teker tutuş değerleri |

### 2.4 Robotun sağlıklı devriyede olduğunu görün

> Not: eski `ros_status.sh` silindi; artık topic doğrudan dinlenir.

```
source /opt/ros/humble/setup.bash && source ~/aeropatch_ws/install/setup.bash
ros2 topic echo /anomaly_score
```

✅ **Beklenen:** anomaly_score örnekleri **0.0–0.2** arası (eşik 0.45 + histeresis
0.20), pozlar adım adım değişiyor (robot yürüyor), cmd_vel linear.x ≈ 0.22.

### 2.5 Bozulmayı ENJEKTE EDİN — demonun kalbi 💥

İkinci bir WSL sekmesinde:

```
bash wsl/inject_wet.sh 0      # 0 = beklemeden hemen enjekte et
```

İlk pencereye dönüp logları izleyin: `bash wsl/tail_launch.sh`

✅ **Beklenen olay zinciri** (loglarda bu sırayla — yeni kapalı çevrim):

| # | Log satırı | Anlamı |
|---|---|---|
| 1 | `sim_node: DISTURBANCE injected: traction L=0.45 R=1.00 (ramp 2.0s)` | Sol teker kaygan zemine bastı |
| 2 | `monitor_node: ALARM score=0.xx -> telemetry dispatched to cloud` | Kenar algılayıcı tetiklendi (~1–2 sn) |
| 3 | `controller_node: LOCAL FALLBACK (0ms): Kp=1.50 Kd=0.22 v_tavan=%35` | **Bulut beklemeden savrulma kesildi** |
| 4 | `bridge_node: telemetry evt-... -> cloud agent...` | Telemetri buluta gitti (paralel) |
| 5 | `bridge_node: PATCH back in 5–14 s [model=... resync=True]` | **Gerçek Nemotron** teşhis + Tavily hava verisi |
| 6 | `controller_node: PATCH applied: Kp=... slip_comp=... v_max=...` | İnce ayar LOCAL FALLBACK üzerine yazıldı |
| 7 | `monitor_node: odom resync: kalici DR kaymasi ... sifirlandi` | Mavi iz sıfırlandı (mavi≡kırmızı) |
| 8 | `monitor_node: RECOVER hold: score < 0.20 -> 10s stabil gerekli` | Histeresis sayacı başladı (baseline'a dönüş) |
| 9 | *skor S≥0.85'e tırmanırsa:* `controller_node: ESKALASYON (2. alarm, 0ms): Kp=1.00 Kd=0.28` | Devrilme engellendi (bulut beklenmez) |

> Zinciri istediğiniz kadar tekrarlayabilirsiniz: her `inject_wet.sh 0` yeni bir
> bozulma → alarm → yama turu başlatır; ancak Tavily/NIM tarafı cache (TTL 120 s)
> ile aynı hava durumu için tekrar sorgu atmaz.

### 2.6 Yamanın işe yaradığını doğrulayın

```
ros2 topic echo /anomaly_score
```

✅ **Beklenen:** skor pikten düşüşe geçmiş (`RECOVER hold: score < 0.20` satırları);
yama geldiyse `odom resync` ile iz sıfırlanır; robot yörünge çevresinde kalmaya
devam ediyor.

### 2.7 Durdurun

```
bash wsl/kill_all.sh
```

✅ **Beklenen:** `(temiz - ros sureci yok)`

---

## Kabul Kriterleri (tümü ✓ ise PASS)

- [ ] **T1:** `pytest` → 0 failed
- [ ] **T1:** EVENT TIMELINE'da DISTURBANCE → ALARM → PATCH sırası göründü
- [ ] **T1:** `final_cte < 0.15 m` (toparlanma kanıtı)
- [ ] **T1:** 6 panelli `demo_report.png` oluştu; panel 4'te slip imzası seçilir
- [ ] **T2:** 4+ düğüm "ready" logu verdi
- [ ] **T2:** Enjeksiyon sonrası 7 adımlı zincir eksiksiz göründü
- [ ] **T2:** `PATCH back < 1000 ms`
- [ ] **T2:** Yama sonrası skor düştü, robot yörüngede kaldı

---

## Sorun Giderme

| Belirti | Neden | Çözüm |
|---|---|---|
| WSL'de `ros2: command not found` | setup.bash kaynaklanmadı | `source /opt/ros/humble/setup.bash` |
| `LAUNCH_DEAD` | Eski süreçler / derleme yok | `bash wsl/kill_all.sh` → `bash wsl/build_v2.sh` → tekrar |
| Betik `\r` hatası veriyor | CRLF bulaşmış | WSL içinde: `python3 wsl/fix_crlf.py` |
| Enjeksiyondan 30 sn+ hiçbir şey yok | WSL VM uykuda | Pencere açık mı? kill_all → ros_start |
| `package 'aeropatch_msgs' not found` | install/ yok | `bash wsl/build_v2.sh` (~1–2 dk) |
| `PATCH back` hiç gelmiyor | bridge hatası | `wsl/logs/ros_launch.log` → `cloud error` satırı |

---

## Sık Soru: "Gazebo ekleyince simülasyonu RViz ile mi göreceğiz?"

**Kısa cevap: İkisi birlikte kullanılacak — görüntü iki farklı yerde:**

| Araç | Ne gösterir | AeroPatch'teki rolü |
|---|---|---|
| **Gazebo** | 3D **fizik dünyası**: robot modeli, zemin, gerçek sürtünme parametreleri | "Kaygan zemin" gerçek friction değişimi olur; jüri kamerası burada |
| **RViz2** | ROS **verisi**: TF koordinat sistemleri, sürülen/planlanan yol, işaretler | Yörünge izi, odom-vs-gerçek sapma, yama anları haritası |

Gazebo penceresi robotun 3D dünyada **yalpalanışını**; RViz penceresi aynı anda
**verinin hikâyesini** (iz, sapma, yama anları) gösterir. Jüri demosunda ikisi yan
yana açık olacak.

**Bonus — Gazebo'yu beklemeden bile** mevcut Faz 2 simülasyonunu RViz'de
izleyebiliriz: eksik olan tek şey küçük bir `viz_node.py` (TF + Path yayını,
~70 satır). Windows 11 WSLg sayesinde RViz2 penceresi doğrudan Windows masaüstünde
açılır. Elle testi bitirdikten sonra ilk iş bunu ekleyelim — demo böylece **gözle
izlenebilir** olur.


