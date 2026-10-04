# AeroPatch — Mimari ve Kod Rehberi

> **Fiziksel AI yarışması projesi:** Kenar cihazda hafif matematiksel anomali algılama →
> bulutta Nemotron + Tavily teşhisi → milisaniyeler içinde geri dönen PID yaması.
> Bu doküman **tüm dizin yapısını, her dosyanun görevini ve sınıf diyagramlarını** içerir.

---

## 1. Sistem Bir Bakışta

Hikâye **5 adımda** (numaralar aşağıdaki diyagramla birebir eşleşir):

1. **Controller** robota `(v, ω)` hız komutu verir; robot yörüngede ilerler.
2. **Robot/Dünya** kayabilir (yağmur, rüzgâr, motor sürüklenmesi) — ama tekerlek
   **encoder'ı bunu GÖREMEZ**: tekerlek dönüyordur, robot yerinden oynamamış olabilir.
3. **AnomalyDetector** (saf matematik, ~100 µs/kare) komut ile odometrinin iddiası
   arasındaki uyuşmazlığı skorlar; skor eşiği **5 ardışık kare** aşınca ALARM.
4. **CloudBridge** telemetriyi buluta **asenkron** fırlatır; controller BULUTU
   BEKLEMDEN 0 ms'de **LOCAL FALLBACK**'a geçer (Kp=1.5, Kd=0.22, v_tavan %35) —
   savrulma hemen kesilir. Skor hâlâ S≥0.85 ise 2. alarm **ESKALASYON** (Kp=1.0,
   Kd=0.28, v_max=0.08) — devrilme engellenir, bulut beklemez.
5. **Bulut** (Nebius Serverless): Tavily ile canlı hava (cache TTL 120 s, 401'de
   DDG fallback), Nemotron teşhisi, **PID yaması** (JSON) 5.6–13.8 s içinde iner
   ve LOCAL FALLBACK'in üzerine yazılır. Yamada **garantili odometri resync** var →
   mavi iz sıfırlanır; skor S<0.20'de 10 sn stabil kalırsa **RECOVER → baseline
   restore** (Kp=2.2, Kd=0.08, v_max=0.22). Ayrıntı: aşağıda §5.

Aynı akış, kutu-kutu (ASCII — doğrudan okunur):

```
┌───────────────────────── KENAR CİHAZ (robotun üzerinde) ──────────────────────────┐
│                                                                                    │
│   ┌────────────────────────┐   cmd_vel=(v,ω)   ┌─────────────────────────┐        │
│   │ 1. Controller          │──────────────────▶│ 2. Robot / Gazebo       │        │
│   │ PID + yörünge takipçisi│                   │ fiziksel dünya: KAYABİLİR│        │
│   └───────────▲────────────┘                   └────────┬────────────────┘        │
│               │                                         │                          │
│               │                                         │                    ┌─────▼─────────────┐
│               │                                         │                    │ Encoder odometri  │
│               │                                         │                    │ kaymayı GÖREMEZ   │
│               │                                         │                    └─────┬─────────────┘
│               │                      gerçek durum       │                          │ iddia edilen
│               │                     (sadece simde)      │                          │ hız
│               │                           │             │                          ▼
│               │                           ▼             ▼        ┌──────────────────────────────┐
│               │                        ┌───────────────────────┐ │ 3. AnomalyDetector            │
│               │                        │  (iki besleme burada  └─▶│ saf matematik, ~100 µs/kare  │
│               │                        └───────────────────────┘  │                              │
│               │                                                   └──────────────┬───────────────┘
│               │ 5. PID yaması (~500 ms, sıcak)                        ALARM: skor > eşik
│               │                                                     ┌────────────▼─────────────┐
│               │                                                     │ 4. CloudBridge             │
│               │                                                     │ asenkron, bloklamaz        │
│               │                                                     └────────────┬─────────────┘
└───────────────┼─────────────────────────────────────────────────────┼────────────┘
                │                                                     │ telemetri JSON
                │                                                     ▼
┌─────────────────────────────── BULUT — Nebius Serverless ─────────────────────────────┐
│                                                                                        │
│   ┌────────────────────┐      teşhis      ┌─────────────────┐      hava     ┌─────────┴───┐
│   │ 5. PatchResponse   │◀─────────────────│ Nemotron LLM    │◀──────────────│ Tavily API  │
│   │ kp, kd, slip_comp. │                  │ "kaygan zemin"  │  "yağmur mu?" │ canlı hava  │
│   └────────────────────┘                  └─────────────────┘               └─────────────┘
└──────────────────────────────────────────────────────────────────────────────────────────┘
```

**Anlatının kalbi:** encoder tabanlı odometri kaymayı *göremez* (tekerlekler dönüyordur ama
robot kaymıştır). Monitor, "odometrinin iddiası" ile "dünya gerçeği"ni karşılaştırır;
sapma → alarm → bulut → yama döngüsü robotu kurtarır.

## 2. İki Katmanlı Zekâ (Ödül Stratejisi)

| Katman | Nerede | Ne yapar | Maliyet |
|---|---|---|---|
| **Refleks** | Kenar, saf Python | Anomali skorlama + alarm (LLM yok!) | ~100 µs/kare, 50 Hz |
| **Teşhis** | Bulut, Nemotron | Semantik yorum: hava + telemetri → yeni parametreler | ~500 ms, yalnız alarm anında |

Kenar asla bulutu beklemez: alarm çağrısı **asenkron** fırlatılır, robot bu arada
güvenli (SAFE) modda yavaşlamayı sürdürür. Bulut cevabı gelirse PID kazançları
**çalışırken** (hot-swap) değişir — integral birikimi korunur, sıfırdan başlanmaz.

---

## 3. Dizin Yapısı

```
nebius/
├── README.md                 # Kurulum + kullanım + yol haritası (başlangıç noktası)
├── MANUAL_TEST.md            # Elle deneme kitabı (Windows + WSL testleri, beklentiler)
├── RAPOR.md                  # Derin teknik rapor (formüller, ölçümler, jüri demosu)
├── MIMARI.md                 # BU DOKÜMAN: dizin + sınıf diyagramları
├── requirements.txt          # Windows tarafı bağımlılıkları (numpy, matplotlib, requests, pytest)
├── plot_ros_record.py        # ROS kayıt dosyası (jsonl) → grafik rapor (Windows'ta çizer)
├── demo_report.png           # Faz-1 demo çıktısı (matplotlib, 6 panel)
├── ros_demo_report.png       # Faz-2 ROS2 kaydından çizilen rapor
│
├── edge/                     # ★ ÇEKİRDEK — saf Python, ROS'a bağımlı DEĞİL
│   ├── pid.py                #   PID: anti-windup + çalışırken kazanç değiştirme (hot-swap)
│   ├── robot_physics.py      #   DiffDriveRobot: diferansiyel sürüş + slip + motor gecikmesi
│   │                         #        + odometri modeli (encoder kaymayı GÖREMEZ)
│   ├── path_follower.py      #   WaypointPath + PathFollower: CTE → (v, ω) komutu
│   ├── anomaly.py            #   AnomalyDetector: 5 bileşenli skor + histerezisli alarm
│   ├── telemetry.py          #   TelemetrySample/Packet + PatchResponse (bulut sözleşmesi)
│   ├── cloud_bridge.py       #   CloudBridge: async HTTP, retry/timeout, mock↔gerçek geçişi
│   ├── mock_cloud.py         #   MockCloud: Nemotron+Tavily davranışının yerel simülasyonu
│   ├── demo_runner.py        #   DemoRunner: Faz-1 uçtan uca senaryo motoru
│   ├── report.py             #   report(): 6 panelli PNG üretir
│   └── run_demo.py           #   CLI: python -m edge.run_demo --mock ...
│
├── tests/                    # 22 birim/entegrasyon testi (pytest, Windows'ta koşar)
│   ├── conftest.py           #   edge/ yolunu import edilebilir yapar
│   ├── test_pid.py           #   PID + hot-swap + anti-windup testleri
│   ├── test_physics.py       #   fizik + odometri yanılsaması testleri
│   ├── test_anomaly.py       #   skor/alarm + kuru zeminde yanlış alarm YOK testi
│   ├── test_cloud.py         #   mock bulut sözleşmesi + bridge testleri
│   └── test_demo_e2e.py      #   uçtan uca: alarm→yama→toparlanma iddiası
│
├── ros_ws/src/               # ★ FAZ 2-3 — ROS2 Humble paketleri (WSL'de derlenir)
│   ├── aeropatch_msgs/       #   CMake paketi: mesaj/servis tanımları
│   │   ├── msg/PatchRequest.msg      #   kenar → bulut telemetri paketi
│   │   ├── msg/PatchResponse.msg     #   bulut → kenar yama (kp, kd, slip_comp, teşhis)
│   │   └── srv/InjectDisturbance.srv #   "yağmur kayması enjekte et" servisi
│   │
│   └── aeropatch/            #   Python (ament_python) paketi: 9 düğüm
│       ├── edge_loader.py    #     edge/ çekirdeğini ROS düğümlerine yükler (tek doğruluk kaynağı)
│       ├── sim_node.py       #     [FAZ 2] DiffDriveRobot'u /odom + /ground_truth olarak yayınlar
│       ├── monitor_node.py   #     [FAZ 2+3] AnomalyDetector'i ROS'a bağlar → /patch/request
│       ├── bridge_node.py    #     [FAZ 2+3] PatchRequest → CloudBridge → /patch/response
│       ├── controller_node.py#     [FAZ 2+3] PathFollower+PID; yamayı sıcak uygular
│       ├── disturbance_node.py#    [FAZ 2] sim_node'a slip enjekte eder
│       ├── gz_truth_node.py  #     [FAZ 3] Gazebo /gazebo/get_entity_state → /ground_truth
│       ├── gz_disturbance_node.py# [FAZ 3] Gazebo'da FİZİKSEL yan kayma uygular
│       ├── gz_viz_node.py    #     [FAZ 3] Gazebo sahnesine iz/yörünge çizer (marker)
│       ├── gz_marker_node.py#     [FAZ 3] elips hedef yörünge + mezar taşları dekoru
│       ├── launch/sim_launch.py    #     Faz-2: 5 düğüm tek komutla
│       ├── launch/gazebo_launch.py#     Faz-3: Gazebo + spawn + RViz + 6 düğüm
│       ├── config/params.yaml       #     tüm eşikler/kazançlar (tek ayar dosyası)
│       ├── worlds/aero_world.sdf    #     8x8 arena + gazebo_ros_state plugin'i
│       └── rviz/aero_demo.rviz      #     önceden ayarlanmış RViz görünümü (3 iz)
│
├── cloud/                    # ★ FAZ 4 — gerçek Nebius Serverless handler şablonu
│   └── nebius_handler.py     #   Tavily araması + Nemotron prompt → PatchResponse JSON
│
└── wsl/                      # Operasyon betikleri (Windows→WSL köprüsü)
    ├── gz_demo_start.sh      #   Gazebo demoyu arka planda başlat (GUI+RViz WSLg'de açılır)
    ├── gz_inject.sh          #   kayma enjekte et: bash gz_inject.sh 0.3 0.3 2.0
    ├── gz_status.sh / gz_stop.sh  #   canlılık kontrolü / tam durdurma
    ├── build_v2.sh           #   ros_ws'i native fs'e kopyalayıp colcon build
    ├── gz_install.sh         #   Gazebo11 + turtlebot3 kurulumu (OSRF deposu)
    ├── fix_crlf.py           #   .sh dosyalarındaki Windows satır sonlarını temizler
    ├── bg_wrapper.py / wrapper.py  #  uzun işlemleri arka plana alıp log tutar
    ├── ros_*.sh              #   Faz-2 karşılıkları (sim demosu)
    └── ros_recorder.py       #   ROS oturumunu jsonl'ye kaydeder (plot_ros_record.py ile çizilir)
```

---
## 4. Sınıf ve Akış Diyagramları (ASCII)

> Bu bölümdeki diyagramlar **düz metindir (ASCII)** — her editörde, her önizlemede
> olduğu gibi okunur; eklenti gerekmez. Ayrıntı için her bölümdeki
> **"Kim kimdir?" tablosu** tek başına yeterlidir.

### 4.1 Edge çekirdeği (`edge/`) — Windows'ta saf Python

**Kim kimdir?**

| Sınıf | Kim? | Neden var? |
|---|---|---|
| `PID` | refleks kutusu | `set_gains()` ile çalışırken kazanç değişir; **integral korunur** (robot durmaz) |
| `RobotState` | durum paketi (dataclass) | `x, y, theta` + tekerlek hızları tek pakette |
| `RobotPhysics` | dijital ikiz | diferansiyel sürüş kinematiği + slip + **encoder yanılsaması** |
| `WaypointPath` | rotanın verisi | segment listesi, lookahead noktası, cross-track error |
| `FollowerParams` | ayar kartı (dataclass) | `lookahead`, `max_v/max_w`, hedef toleransı |
| `PathFollower` | pilot | içindeki **iki PID** ile CTE'yi `(v, w)` komutuna çevirir; `apply_patch()` bulut yamasını sıcak uygular |
| `AnomalyDetector` | sinyalci | 5 bileşenli skor; eşik + histerezis (5 kare) → alarm; `extend_grace()` yama sonrası sakinleşme |
| `TelemetryPacket` | zarf | bir kare telemetri → `to_dict()` ile JSON hazır |
| `PatchResponse` | sözleşme | teşhis + pid_patch + slip_compensation — **mock ve Nebius aynı şemayı konuşur** |
| `CloudBridge` | postacı | async HTTP; `mock_mode=True` ise `MockCloudAgent`'a düşer |
| `MockCloudAgent` | bulutun ikizi | Nemotron+Tavily davranışını lokalde taklit eder (~500 ms gecikme dahil) |
| `DemoRunner` | orkestra şefi | Faz-1 öyküsünü adım adım koşar, `RunReport` üretir |

**Oklar nasıl okunur?** `*--` = "sahi̇plenir" (composition), `o--` = "kullanır" (aggregation),
`..>` = "üretir/çağırır" (bağımlılık). Etiket ilişkinin adıdır.

```
*-- = sahiplenir (composition)   o-- = kullanır (aggregation)   ..> = çağırır/üretir

 ┌──────────────┐
 │ PID          │  anti-windup, hot-swap set_gains()  (integral korunur)
 └──────▲───────┘
        │ *--  linear_pid + angular_pid
 ┌──────┴───────────────┐   o--   ┌────────────────┐        ..>   ┌────────────────┐
 │ PathFollower         │────────▶│ WaypointPath   │  apply_patch │ PatchResponse  │
 │ compute(pose)→(v,w)  │         │ lookahead, CTE │◀─────────────│ kp,kd,slip_comp│
 │ apply_patch()        │         └────────────────┘              └────────────────┘
 └──────┬───────────────┘
        │ *--  ┌────────────────┐
        └─────▶│ FollowerParams │  lookahead, max_v/max_w, goal_tol
               └────────────────┘

 ┌──────────────┐ besler ┌───────────────────┐ skor üretir ┌──────────────────┐
 │ RobotPhysics │───────▶│ AnomalyDetector   │────────────▶│ TelemetryPacket  │
 │ dif. sürüş+  │        │ eşik+histerezis,  │             │ → to_dict() (JSON│
 │ slip+encoder │        │ extend_grace()    │             └──────────────────┘
 │ yanılsaması  │        └───────────────────┘
 └──────────────┘

 ┌──────────────┐ mock_mode ┌───────────────┐  üretir  ┌───────────────┐
 │ CloudBridge  │──────────▶│ MockCloudAgent│─────────▶│ PatchResponse │
 │ async HTTP,  │           │ Nemotron+     │          └───────────────┘
 │ retry/timeout│           │ Tavily sim    │
 └──────┬───────┘           └───────────────┘          ┌───────────────┐
        │ ..> gönderir ───────────────────────────────▶│ PatchRequest  │
        │   (robot_id + telemetri)                     └───────────────┘
```

### 4.2 ROS2 düğümleri (`ros_ws/src/aeropatch/`) — Gazebo entegrasyonu

**Kim kimdir?** Her düğüm bir `rclpy.Node` alt sınıfıdır; kalınlığı `edge/` çekirdeğinden gelir
(`edge_loader.py` sayesinde aynı kod — ROS tarafı sadece "topic ↔ sınıf çağrısı" adaptörüdür).

| Düğüm | Ne yapar | Sarıldığı çekirdek |
|---|---|---|
| `controller_node` | PathFollower'ı çalıştırır, `/cmd_vel` basar, yamayı sıcak uygular | `PathFollower` |
| `monitor_node` | `/odom` + `/ground_truth` → skor → `/patch/request` | `AnomalyDetector` |
| `bridge_node` | `/patch/request` → CloudBridge → `/patch/response` | `CloudBridge` |
| `sim_node` | Faz-2: `DiffDriveRobot`'u ROS topic'lerine basar | `RobotPhysics` |
| `gz_truth_node` | Faz-3: Gazebo `get_entity_state` → `/ground_truth` | — |
| `gz_disturbance_node` | Faz-3: `/inject_disturbance` servisi → fiziksel yan kayma | — |
| `gz_viz_node` | RViz sahnesine iz/durum yazısı çizer; mavi iz `/odom_corrected`'dan | — |
| `gz_marker_node` | SLIP oku + referans elips marker'ları | — |
| `ekf_node` | Gürültülü telemetriyi EKF ile füzyonlar (kenar tarafı) | — |

```
                       ┌─────────────────────┐
                       │  rclpy.node.Node    │
                       └──────────┬──────────┘
   kalıtım: ┌──────┬──────┬──────┼──────┬─────────────┬──────────┐
            ▼      ▼      ▼      ▼      ▼             ▼          ▼
   Controller Monitor Bridge  GzTruth GzDisturbance GzVizNode  SimNode
   Node       Node    Node    Node    Node
        │         │       │
        │ *--     │ *--   │ *--   (edge çekirdeği içinde taşınır)
        ▼         ▼       ▼
   PathFollower AnomalyDetector CloudBridge

 Topic akışı:
   GzTruthNode      ── /ground_truth  ─▶ ControllerNode ── /cmd_vel ─▶ Gazebo diff_drive (GzDisturbanceNode)
   MonitorNode      ── /patch/request ─▶ BridgeNode     ── /patch/response ─▶ ControllerNode
```

### 4.3 Çalışma zamanı ileti akışı (sequence)

Zaman soldan sağa değil, **yukarıdan aşağı akar**. Hikâye: normal yörünge → yağmur
enjeksiyonu → encoder "normal" demeye devam ederken alarm → bulut → yama → toparlanma.

```
 Gazebo   gz_truth  controller  monitor    bridge    MockCloud
 (fizik)  node      node        node       node      (Nemotron+Tavily sim)
   │        │          │          │          │            │
   │ gerçek pose (get_entity_state, 50Hz)   │            │
   ├───────▶│          │          │          │            │
   │ /odom (encoder — kaymayı GÖREMEZ)      │            │
   ├────────────────────┼────────▶│          │            │
   │        │/ground_truth        │          │            │
   │        ├─────────▶│          │          │            │
   │        ├────────────────────▶│          │            │
   │  /cmd_vel (PID çıktısı)      │          │            │
   │◀───────────────────┤          │          │            │
═══╡══════════ YAĞMUR ENJEKSİYONU (/inject_disturbance) ══╡
   │ (robot fiziksel olarak kayar)│          │            │
   │        │          │     komut-ölçüm +   │            │
   │        │          │     CTE uyuşmazlığı │            │
   │        │          │     skor>eşik ALARM │            │
   │        │          │          │ /patch/request        │
   │        │          │          ├─────────▶│  HTTP POST │
   │        │          │          │          ├───────────▶│
   │        │          │          │          │   ┌─ Tavily: bölgede yağmur
   │        │          │          │          │   └─ Nemotron: "slip → PID yumuşat + telafi"
   │        │          │          │          │◀───────────┤ PatchResponse
   │        │          │  /patch/response    │            │
   │        │          │◀────────────────────┤            │
   │        │          │ (PID hot-swap,      │            │
   │        │          │  integral korunur)  │            │
   │  /cmd_vel (düzeltilmiş)     │          │            │
   │◀───────────────────┤          │          │            │
═══╡ TOPARLANMA: robot yörüngeye döner; mavi iz (odom) kırmızıdan ayrı kalır ═╡
   │        │          │          │          │            │
```
## 5. Kapalı Çevrim Durum Makinesi (Son Hâl)

Sistem artık **çift yönlü**: ıslak zeminde sönümle, kararlı durumda baseline'a dön.
Dört durum + geçiş kuralları:

```
             skor S > 0.45 (5 ardışık kare)
    ┌──────────────────────────────────────┐
    │                                      ▼
 [MODE=OK]  ◀── RECOVER ────  [LOCAL FALLBACK] ──S≥0.85──▶ [ESKALASYON]
  Kp=2.2      S<0.20 + 10s     Kp=1.5, Kd=0.22            Kp=1.0, Kd=0.28
  Kd=0.08     stabil           v_max=0.12 (%35)            v_max=0.08 (0ms)
  v_max=0.22  ▲                bulut beklemez              (tekrar S<0.20'ye
              │                ◀── NIM yaması ──┘           inerse RECOVER'a)
              └── restore yaması  (üzerine yazılır)
```

### 5.1 Geçiş kuralları (kod karşılıkları)

| Geçiş | Kural | Nerede |
|---|---|---|
| OK → LOCAL FALLBACK | S > 0.45, 5 ardışık kare (persistence) | `monitor_node` skor döngüsü |
| FALLBACK → ESKALASYON | S ≥ 0.85 (2. alarm — bulut beklemez, devrilme engellenir) | `controller_node` skor işleyişi |
| FALLBACK/ESK. → OK (yama) | Bulut yaması geldi: hot-swap + garantili resync | `controller_node._on_patch` |
| herhangi → RECOVER sayacı | S < 0.20 **10 sn stabil** (histeresis alt eşiği) | `monitor_node` hold sayacı |
| RECOVER → baseline | Restore yaması: Kp=2.2, Kd=0.08, v_max=0.22 (yumuşak ramping) | `nebius_handler` / `mock_cloud` |

### 5.2 Neden histeresis şart?

Alarm eşiği (0.45) ile recovery eşiği (0.20) **farklı** olmalı — ikisi de aynı olsaydı:
robot yavaşlar → skor 0.44'e düşer → anında recover tetiği → Kp yükselir → tekrar
patinaj → skor 0.71 → sonsuz "kuru-ıslak-kuru" döngüsü (chattering).
**S < 0.20 + 10 sn stabil** kuralı bu döngüyü keser; ama güvenlik kritik bir nokta var:
skor hâlâ S≥0.85 ise ESKALASYON **asla engellenmez** (cooldown robotu devrilme riskine atar).

### 5.3 Neden LOCAL FALLBACK şart?

Bulut gecikmesi (gerçekte 5–14 s) boyunca robot savrulmaya devam ederdi — yoldan çıkardı.
Alarm anında controller **0 ms'de** güvenli parametrelere geçer (Kp↓ 1.5, Kd↑ 0.22,
v_max↓ %35); bulutun hassas yaması (NIM teşhisi + slip feedforward + resync) gelince
**üzerine yazılır**. Böylece fiziksel müdahale (kenar) ile bulut araması (Tavily kotası)
birbirinden ayrılır: robot devrilmez, bulut dakikada 5 kere sorgu almaz (cache TTL 120 s).


