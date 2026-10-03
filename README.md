# AeroPatch — Edge Anomaly Detection + Cloud (Nemotron/Tavily) Patching

**Physical AI Track** projesi: Kenar cihazda çalışan hafif matematiksel anomali algılayıcı,
fiziksel sapma (teker kayması / traction kaybı) tespit edince telemetriyi Nebius
Serverless üzerindeki ajanına fırlatır. Ajan **Tavily** ile bölgenin canlı hava
durumunu arar, **Nemotron** ile teşhis koyar ve robota yeni **PID kazançları +
slip telafi faktörü** içeren yamayı milisaniyeler içinde geri yollar.

> **Elle denemek için:** [`MANUAL_TEST.md`](MANUAL_TEST.md) — adım adım komutlar,
> beklenen çıktılar ve kabul kriterleri.

## Senaryo (demo anlatısı)

```
Robot devriye turunda → yağmur başlar (zemin kayganlaşır)
  → sol teker traction 1.00 → 0.45 (slip enjeksiyonu)
  → odometri "mutlu", robot gerçekten sapıyor (encoder kaymayı göremez!)
  → kenar algılayıcı 100ms içinde ALARM (saf matematik, LLM yok)
  → telemetri paketi buluta (son ~0.5s veri)
  → Tavily: "Kadıköy'de hafif yağmur" → Nemotron: "ıslak zemin, traction kaybı"
  → yama: Kp↑, Kd↑, slip feedforward, hız tavanı %35, odometri resync
  → robot toparlanır → yeni alarm gelene kadar döngü
```

## Mimari

```
┌─────────────────────── KENAR (robot / Jetson / edge CPU) ───────────────────────┐
│  fizik motoru (dijital ikiz)  →  PID yörünge takip  →  /cmd_vel               │
│        ↑                            ↑ hot-swap                                  │
│  anomali algılayıcı (saf matematik, ~100ms)  ←  yama uygula                    │
└──────────────────────────────┬─────────────────────────────────────────────────┘
                     telemetri │ ↑ yama (ms'ler içinde)
┌──────────────────────────────▼─────────────────────────────────────────────────┐
│  NEBIUS SERVERLESS:  ajan = Nemotron (teşhis) + Tavily (canlı hava araması)     │
└─────────────────────────────────────────────────────────────────────────────────┘
```

## Dosya yapısı

```
edge/                      Faz 1: platformdan bağımsız saf Python çekirdek
  pid.py                   hot-swap PID (anti-windup)
  robot_physics.py         diferansiyel sürüş + teker kayması + odometri modeli
  path_follower.py         yörünge takip + bulut yamasını sıcak uygular
  anomaly.py               anomali skoru (hız/dönüş/pozisyon uyuşmazlığı)
  telemetry.py             TelemetryPacket / PatchResponse sözleşmesi
  mock_cloud.py            Nemotron+Tavily bulut simülatörü (aynı JSON şeması)
  cloud_bridge.py          mock/gerçek bulut geçişi (retry'li HTTP)
  demo_runner.py           uçtan uca demo akışı
  report.py                6 panelli demo raporu (demo_report.png)
  run_demo.py              CLI
tests/                     22 test (pytest) — hepsi geçiyor
ros_ws/src/                Faz 2: ROS2 paketleri
  aeropatch_msgs/          PatchRequest.msg, PatchResponse.msg, InjectDisturbance.srv
  aeropatch/               sim/monitor/bridge/controller/disturbance düğümleri + launch
cloud/                     Faz 4: Nebius serverless handler şablonu
```

## Kurulum (Windows / kenar geliştirme)

```bat
pip install -r requirements.txt
python -m pytest tests/ -q            :: 22 testin tamamı geçmeli
python -m edge.run_demo --mock        :: ana demo + demo_report.png
```

Yararlı varyasyonlar:

```bat
python -m edge.run_demo --mock --slip 0.7 --weather storm
python -m edge.run_demo --mock --realtime          :: jüri canlı videosu (45s)
python -m edge.run_demo --real --endpoint https://<nebius-endpoint> --api-key <key>
```

Birim alt sistemler:

```bat
python -m pytest tests/test_pid.py tests/test_physics.py -q
```

## Faz 2: ROS2 (WSL2 Ubuntu 22.04 / Humble)

```bash
# 1) edge modüllerini ROS'a göster
export AEROPATCH_EDGE_PATH=/mnt/d/.gemini/antigravity-ide/scratch/nebius

# 2) derle
cd ~/aeropatch_ws          # ros_ws içeriğini buraya kopyalayın veya bağlayın
colcon build --symlink-install
source install/setup.bash

# 3) tam sistemi başlat (5 düğüm tek komutla)
ros2 launch aeropatch sim_launch.py

# 4) başka terminalde: yağmuru "başlat" — kaygan zemini enjekte et
ros2 service call /inject_disturbance aeropatch_msgs/srv/InjectDisturbance \
  "{traction_left: 0.45, traction_right: 1.0, ramp_time: 2.0}"

# 5) izle
ros2 topic echo /anomaly_score
ros2 topic echo /patch/response
```

Düğümler: `sim_node` (fizik, Gazebo'suz dijital ikiz) → `controller_node` (PID) →
`monitor_node` (anomali) → `bridge_node` (bulut) → `disturbance_node` (test tetiği).

## ✅ Faz 2 Doğrulaması — Canlı ROS2 Sonuçları (24 Eylül oturumu)

Sistem WSL2 Ubuntu-22.04 + ROS2 Humble üzerinde **canlı çalıştırıldı ve 15+ dakika
kesintisiz kapalı döngüde kaldı**. Gerçek launch logundan satırlar:

```
[INFO] [launch]: All log files ... 2026-09-24-23-34-26 ... 
[sim_node-1]        sim_node ready (50 Hz physics, wheel-slip disturbance model)
[monitor_node-3]    monitor_node ready (pure-math anomaly detector)
[bridge_node-4]     bridge_node ready (MOCK cloud (nemotron+tavily sim))

# --- Yağmur enjeksiyonu (servis çağrısı) ---
[sim_node-1]        DISTURBANCE injected: traction L=0.40 R=1.00 (ramp 1.5s)
# --- 0.86 saniye sonra: kenar algılayıcı alarmı ---
[monitor_node-3]    ALARM score=0.67 -> telemetry dispatched to cloud (evt-...)
[controller_node-2] safe-mode ON (waiting for cloud patch)
[bridge_node-4]     telemetry evt-... -> cloud agent...
# --- 516 ms sonra: Nemotron+Tavily yaması geri döner ---
[bridge_node-4]     PATCH back in 516 ms: Traction loss detected: odometry
                    reports 0.023 m/s more ground speed than actual...
[controller_node-2] PATCH applied: Kp=2.34 Kd=0.22 slip_comp=-0.232 v_max=0.16
# --- Slip sürdüğü sürece bulut sürekli adapte eder (6s hold-off) ---
[monitor_node-3]    ALARM score=1.14 ... [bridge_node-4] PATCH back in 427 ms
[controller_node-2] PATCH applied: Kp=2.76 Kd=0.22 slip_comp=-0.340
[monitor_node-3]    ALARM score=1.43 ... [bridge_node-4] PATCH back in 654 ms
[controller_node-2] PATCH applied: Kp=2.77 Kd=0.22 slip_comp=-0.679
```

**Kuru zemine dönüş testi** (`traction 1.0/1.0` servisi ile):

```
=== kuru zemine don (traction 1.0 / 1.0) ===
response: success=True, message='disturbance published: traction L=1.00 R=1.00'
=== anomaly score ===
1.35  →  0.47  →  0.51   (eşik 0.60 altına iner → alarm zinciri durur)
```

Robot tüm süre boyunca devriye elipsinde kaldı (normalize yörünge hatası ~0.87-0.88,
yörüngede = 1.0 referansına yakın) ve yamalı hız tavanıyla (0.16 m/s) seyrine devam etti.

### ROS2 oturumunda ölçülen metrikler

| Metrik | Değer | Not |
|---|---|---|
| Algılama gecikmesi (ROS) | **0.86 s** | Servis çağrısı → ALARM logu |
| Bulut round-trip (ROS) | **427–654 ms** | 10+ çevrim, mock Nemotron+Tavily |
| Alarm→yama→uygulama | **~1.4 s** | Safe-mode + hot-swap PID dahil |
| Uzun süre kararlılığı | **15+ dk** | Kesintisiz kapalı döngü, 10+ yama |
| Toparlanma kanıtı | skor 1.35→0.47 | Kuru zemin dönüşünde alarm zinciri durdu |

### `wsl/` yardımcı script'leri (bu oturumda yazıldı ve kullanıldı)

```bash
# Windows terminalinden tek komutla:
wsl -d Ubuntu-22.04 -- bash /mnt/d/.gemini/antigravity-ide/scratch/nebius/wsl/ros_start.sh    # sistemi başlat
wsl -d Ubuntu-22.04 -- bash .../wsl/ros_inject.sh     # yağmur enjekte et + skoru göster
wsl -d Ubuntu-22.04 -- bash .../wsl/ros_restore.sh    # kuru zemine dön + skoru göster
wsl -d Ubuntu-22.04 -- bash .../wsl/ros_status.sh     # canlı skor/poz/cmd_vel örnekleri
wsl -d Ubuntu-22.04 -- bash .../wsl/tail_launch.sh    # launch logundan kanıt satırları
wsl -d Ubuntu-22.04 -- bash .../wsl/kill_all.sh      # her şeyi durdur
wsl -d Ubuntu-22.04 -- python3 .../wsl/fix_crlf.py    # editör CRLF -> LF düzeltici
```

### WSL tuzakları (bu oturumda çözüldü — not edin)

1. **WSL boşta kalınca VM kapanıyor** → arka plan build'leri ölüyor. Çözüm: kalıcı bir
   keeper süreci: `start /b wsl -d Ubuntu-22.04 -- sleep 14400`
2. **Editör CRLF yazıyor** → `.sh` dosyaları bash'te çalışmıyor
   (`setup.bash\r: No such file or directory`). Çözüm: `fix_crlf.py` (sed ile `s/\r//g`
   yapmayın — ters tepip **tüm 'r' harflerini yiyor**; Python byte-level güvenli).
3. **cmd.exe boru (`|`) ve tırnak işaretlerini yutuyor** → karmaşık komutları doğrudan
   yazmayın; `.sh` dosyasına koyup `bash dosya.sh` ile çalıştırın.


## Faz 3: Gazebo (yol haritası)

1. `sim_node`'un yerine TurtleBot3 Gazebo simülasyonu (`turtlebot3_gazebo`).
2. Fiziksel kaygan zemin: Gazebo'da friction katsayısını dinamik değiştiren
   küçük bir world plugin veya `gazebo_ros` üzerinden `set_physics_properties`.
3. `/odom` gerçek Gazebo odometrisi; `/ground_truth` yerine AMCL veya GPS.
4. Bozulma tetiği: aynı `/inject_disturbance` servisi world'e bağlanır.

## Faz 4: Gerçek Nebius bulutu

`cloud/nebius_handler.py` şablonu ile:
1. Nebius Serverless'da function/endpoint oluşturun,
2. `NEBIUS_API_KEY` ve `TAVILY_API_KEY` ortam değişkenlerini verin,
3. `bridge_node` parametrelerinde `mock_cloud: false` + `endpoint_url` yapın.

## Jüri sunumu için ölçümler

- Algılama gecikmesi: bozulma → alarm (hedef <2s, ölçülen ~1.2s)
- Bulut gidiş-geliş: `latency_ms` (mock ~500ms; gerçekçisi ölçülecek)
- Toparlanma: alarm → CTE < 0.15m süresi
- Yanlış alarm oranı: `test_end_to_end_no_false_alarm_on_dry_ground`

## Doğrulama Sonuçları (canlı çalıştırılmış)

### Birim + entegrasyon testleri

```
$ python -m pytest tests/ -q
......................                                                       [100%]
22 passed in 1.16s
```

Kapsam: PID yakınsaması / hot-swap / anti-windup, fizik motoru (kuru zeminde
odometri=gerçek, kaygan zeminde slip imzası), anomali tetikleme + cooldown +
yanlış alarm yok, mock bulut şema sözleşmesi, uçtan uca alarm→yama→toparlanma.

### Uçtan uca demo çıktısı (mock bulut)

```
AeroPatch — Edge anomaly detection -> Nebius/Nemotron + Tavily patch
  mode        : MOCK CLOUD (nemotron+tavily simulation)
  disturbance : left traction 0.45 @ t=8.0s
  region      : Kadikoy, Istanbul, TR (Tavily will fetch live weather)
====================================================================
  !! DISTURBANCE at t=8.0s: left wheel traction dropped to 0.45 (wet surface)
  >> ALARM: physical deviation! Dispatching telemetry to cloud...
  .. waiting for cloud patch (extending simulation)
  >> PATCH in 497 ms: Traction loss detected: odometry reports 0.025 m/s
     more ground speed than actual motion...
  >> PATCH in 421 ms  (2. yamada Kp 2.2 -> 2.89, slip_comp -0.745)
  >> PATCH in 645 ms  (3. yamada Kp -> 3.54, slip_comp -0.759)
--------------------------------------------------------------------
EVENT TIMELINE:
  t=   8.00s  DISTURBANCE    left traction -> 0.45
  t=   9.20s  ALARM          score=0.64 event=evt-...
  t=  20.32s  PATCH_APPLIED  latency_ms=497 kp=2.351 slip_comp=-0.313
  t=  21.46s  ALARM          score=1.01 event=evt-...
  t=  21.86s  PATCH_APPLIED  latency_ms=421 kp=2.886 slip_comp=-0.745
  t=  25.56s  ALARM          score=1.33 event=evt-...
  t=  26.16s  PATCH_APPLIED  latency_ms=645 kp=3.543 slip_comp=-0.759
--------------------------------------------------------------------
alarms=3  patches=3  recovery=0.52s  max_cte=0.08m  final_cte=0.04m
[report] saved -> demo_report.png
```

### Öne çıkan metrikler

| Metrik | Değer | Not |
|---|---|---|
| Algılama gecikmesi | **1.2 s** (bozulma→alarm) | %55 slip, 2s rampa dahil |
| Bulut round-trip | **420–650 ms** (mock) | Gerçek Nebius'ta ölçülecek |
| Max sapma | **0.08 m** CTE | Yamalar art arda gelirken |
| Final CTE | **0.04 m** | Tam toparlanma |
| Yanlış alarm | **0** | 14 s kuru zemin testi |

Not: sim hızlı akarken bulut çağrısı gerçek-zaman gecikmesiyle döner; runner
"grace extension" ile simüloyu yama gelene kadar yaşatır. `--realtime`
modunda tüm zaman çizelgesi gerçek zamana oturur (jüri videosu için ideal).
