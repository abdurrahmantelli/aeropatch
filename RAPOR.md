# AeroPatch — Kapsamlı Proje Raporu

**Kategori:** Physical AI Track — kenar anomali algılama + bulut tabanlı fiziksel yama
**Yığın:** Saf Python çekirdeği → ROS2 Humble (WSL2) → [Faz 3] Gazebo → [Faz 4] Nebius Serverless (Nemotron + Tavily)
**Rapor tarihi:** 24 Eylül 2026 oturumu (Faz 1 + Faz 2 tamamlanmış ve CANLI doğrulanmış)

---

## İçindekiler

- 0. Yönetici özeti
- 1. Kağıt üzerinde: fizik ve algoritma
- 2. Kapalı çevrim: uçtan uca işleyiş
- 3. Faz 1 — Yazılım mimarisi
- 4. Faz 2 — ROS2 katmanı
- 5. Bulut sözleşmesi (mock = gerçek)
- 6. Doğrulama sonuçları
- 7. WSL oturum notları
- 8. Faz 3 yol haritası (Gazebo)
- 9. Faz 4 — Gerçek Nebius bulutuna geçiş
- 10. Jüri demosu planı

---

## 0. Yönetici özeti

Sahadaki bir robot/dron, yerleşik işlemcisiyle ağır LLM çalıştıramaz; ama fiziksel
bozulmaları (zemin kayması, motor sürüklenmesi, rüzgâr) anlık hissetmek zorundadır.
AeroPatch bu ikilemi **iki katmanlı zekâ bölümü** ile çözer:

1. **Kenar katmanı (robot):** 50 Hz'de çalışan, LLM'siz, **saf matematik** anomali
   algılayıcı. Teker kayması imzasını ~100 ms içinde yakalar, telemetri paketini
   buluta yollar, beklerken güvenli moda geçer.
2. **Bulut katmanı (Nebius Serverless):** Ajan **Tavily** ile bölgenin canlı hava
   durumunu arar ("Kadıköy'de hafif yağmur"), **Nemotron** telemetri + hava verisini
   birleştirip teşhis koyar ("ıslak zemin → traction kaybı") ve robota **sıcak
   uygulanabilir yama** döndürür: yeni PID kazançları + slip feedforward + hız tavanı.

**Ölçülen sonuçlar (canlı):** algılama 0.86–1.2 s, bulut gidiş-dönüş 427–654 ms,
robot yörüngeden maksimum 8 cm saptı ve toparlandı; kuru zeminde yanlış alarm 0.

---

## 1. Kağıt üzerinde: fizik ve algoritma

Bu bölüm, kod yazılmadan ÖNCE kâğıda dökülen modeli anlatır: sistemin neden çalıştığı.

### 1.1 Problem

Devriye turundaki diferansiyel sürüşlü bir robot yağmura yakalanır. Zemin kayganlaşır,
sol teker tutuşunu yitirir. Kritik fiziksel gerçek:

> **Encoder (odometri) motoru okur, zemini değil.** Teker boşa dönerken encoder
> "hızımız iyi" der; robot gerçekten yavaşlar ve gereksiz döner. Klasik PID bu
> yanılsamaya karşı körüdür çünkü hatayı odometriden hesaplar.

Sonuç: odometri tabanlı dead-reckoning (DR) pozu ile harici lokalizasyon (GPS/AMCL)
pozu arasında **innovation** (uyuşmazlık) büyür. Bu büyüme gürültü değil,
**fiziksel sapmanın ta kendisidir** — ve tamamen kenar cihazda, LLM'siz hesaplanabilir.

### 1.2 Robot kinematiği (diferansiyel sürüş)

```
v     = (w_l + w_r) · r / 2          # gövde hızı
omega = (w_r − w_l) · r / W          # gövde dönüş hızı
x'    = v·cos(theta),  y' = v·sin(theta),  theta' = omega
```

- `r = 0.033 m` teker yarıçapı, `W = 0.16 m` teker aralığı (TurtleBot3 ölçüleri)
- Motor cevabı: birinci mertebe gecikme `w' = (w_cmd − w)/tau`, `tau = 0.12 s`

### 1.3 Teker kayması (slip) ve ölçüm yanılsaması

Zemin tutuşu `g ∈ [0,1]` katsayısıyla modellenir (1 = kuru, 0 = tam kayma):

```
w_ground = w_motor · g         # zeminle temas eden GERÇEK hız
v_odom   = f(w_motor)          # encoder'ın okuduğu (yanılsamalı) hız
v_true   = f(w_ground)         # GPS/AMCL'den görünen gerçek hız
```

Yağmur anında değil kademeli gelir: `g` hedefine ~2 s rampayla iner (fiziksel gerçekçilik).
**Odometri `w_motor`'u entegre eder** → DR pozu, gerçekten sapan robottan kopar.
Bu kopma, anomali skorunun en güçlü bileşenidir.

### 1.4 Anomali skorlaması (kenar, saf matematik, ~100 ms)

Her 50 Hz örneğinde 5 normalize bileşen ağırlıklı toplanır:

```
s_v   = |v_odom − v_true| / 0.06      (ağırlık 0.40)  → slip imzası
s_w   = |w_odom − w_true| / 0.30      (ağırlık 0.30)  → dönüş sürüklenmesi
s_p   = ||p_true − p_DR|| / 0.25       (ağırlık 0.30)  → lokalizasyon innovation'u
s_cte = |CTE| / 0.35                   (ağırlık 0.15)  → yörünge sapması
s_h   = |heading_err| / 0.60           (ağırlık 0.10)

score = Σ ağırlık · min(bileşen, 1.5)
```

Karar mantığı (gürültüye dayanıklı, LLM'siz):

- **Eşik:** `score ≥ 0.60`
- **Persistence:** ardışık **5** örnek üst üste (50 Hz'de ~100 ms) → tekil gürültüyü eler
- **Cooldown/hold-off:** alarm sonrası 4–6 s yeni alarm yok → bulut döngüsü nefes alır

Bu, basitleştirilmiş bir **Kalman innovation testidir**: poz/hız uyuşmazlıklarını tek
skora indirger. Gerekirse aynı arayüze tam Kalman innovation χ² testi takılabilir.

### 1.5 Denetim ve yama felsefesi

Yörünge takibi: waypoint kerterizi + hot-swap PID (**integral yamada KORUNUR** —
kontrol sürekliliği bozulmaz, sadece kazançlar değişir). Bulut yaması beş kolla düzeltir:

| Kol | Ne yapar | Neden |
|---|---|---|
| `kp ↑` (2.2 → 2.3–3.5) | yön kazancı | sapma büyürken agresif toparlanma |
| `kd ↑` (0.08 → 0.22) | sönümleme | kaygan zeminde salınımı bastırır |
| `slip_comp` feedforward | ölçülen ω sapmasını doğrudan ekler | PID'nin göremediği sistemli kaymayı telafi eder |
| `v_max 0.22 → 0.16` | hız tavanı | kaygan zeminde kinetik enerjiyi sınırlar |
| `odom_resync` | DR ↔ harici ölçüm senkronu | birikmiş DR hatasını sıfırlar |

Alarm ↔ yama arası robot **safe-mode**'a girer (hız tavanı %35). Bulut düşse bile
robot güvenli bekler: **kenar, buluta muhtaç olacak kadar çaresiz değildir.**

### 1.6 Kenar-bulut işbölümü gerekçesi

| | Kenar (Jetson/edge CPU) | Bulut (Nebius) |
|---|---|---|
| Görev | 50 Hz algılama + güvenli mod | teşhis + bağlam + yama üretimi |
| Gecikme | ~20 ms | 400–800 ms (kabul edilebilir) |
| Maliyet | mW düzeyi | olay-başına (serverless) |
| Zekâ | 30 satır aritmetik | Nemotron (LLM) + Tavily (canlı arama) |

Anahtar içgörü: **fiziksel sapmanın aciliyeti saniyeler ölçeğindedir, milisaniyeler
değil.** 100 ms'de LLM çağırmak gerekmez; ~500 ms'de teşhis + yama gelmesi yeter.

---

## 2. Kapalı çevrim: uçtan uca işleyiş

Sistemin kalp atışı — tek çevrim ~1.4 s (ölçülen):

```
   t=0.00  ZEMİN KAYGANLAŞIR (γ_sol: 1.0 → 0.4, 1.5-2 s rampa)
      │
   t≈0.86  KENAR: score eşik altını 5 örnek üst üste aşar → ALARM
      │    ├── controller: SAFE-MODE (v_max ↓ %35) — robot hâlâ yaşıyor
      │    └── monitor: telemetri paketi (son ~0.5 s, 25 kare) → buluta
      │
   t≈0.90  BULUT (Nebius serverless, olay-başına):
      │    ├── TAVILY: "Kadıköy canlı hava" → "hafif yağmur, 18 km/s rüzgâr"
      │    └── NEMOTRON: telemetri + hava → teşhis + yama hesabı:
      │         slip_oran = |v_odom−v_true|/v_odom
      │         kp_new = min(kp·(1+0.6·slip), 6.0)
      │         slip_comp = clamp(ortalama ω yanlılığı, ±1.2)
      │
   t≈1.38  YAMA ROBOTA DÖNER (427–654 ms round-trip, ölçülen)
      │    └── controller: PID hot-swap (integral korunur) + v_max + safe-mode OFF
      │
   t≈2+    Robot yörüngeye toparlanır (max CTE 0.08 m ölçüldü)
      │
   ...     Slip sürdükçe 6 s hold-off ile döngü TEKRARLANIR (sürekli adaptasyon)
```

**Neden kapalı çevrim?** Tek atımlık yama yetmez: slip oranı zeminle değişir,
lastik ısınır, yağmur şiddetlenir. Sistem her hold-off periyodunda yeniden ölçüp
yeniden yamar — bulut, fiziksel dünyanın değişen koşullarına **sürekli ayak uyduran
denetim danışmanı** gibi çalışır. Jüri demosunda bu, robotun canlı olarak
"yalpalayıp düzelmesini" izlenebilir kılar.

## 3. Faz 1 — Yazılım mimarisi (saf Python çekirdeği)

Platform bağımsız, `numpy` bile gerektirmeyen çekirdek. Tek doğruluk kaynağı:
hem Windows demoları hem ROS2 düğümleri **aynı modülleri** import eder.

```
edge/
├── pid.py             Hot-swap PID: set_gains() integral durumunu KORUR
├── robot_physics.py   Diferansiyel sürüş + traction kaybı + motor gecikmesi
├── path_follower.py   Waypoint kerterizi + CTE + apply_patch() (sıcak yama)
├── anomaly.py         5 bileşenli skor + persistence + cooldown
├── telemetry.py       TelemetryPacket / PatchResponse (bulut sözleşmesi)
├── mock_cloud.py      Nemotron + Tavily simülatörü (aynı JSON şeması)
├── cloud_bridge.py    mock=True|False tek satır geçiş, retry + latency ölçümü
├── demo_runner.py     Uçtan uca senaryo + grace extension + istatistik
├── report.py          6 panelli grafik rapor (demo_report.png)
└── run_demo.py         CLI: --mock/--real, --realtime, --slip, --weather...
```

**Kritik tasarım kararları:**

1. **`PID.set_gains()` integrali sıfırlamaz.** Bulut yaması geldiğinde kontrol
   sürekliliği bozulmaz — kazanç değişimi saniyeler içinde sürüklenme yaratmaz.
2. **Bulut çağrısı asla kontrol döngüsünü bloklamaz.** `demo_runner` ve
   `bridge_node` istemi worker thread'e bırakır; robot beklerken **yaşamaya devam
   eder** (safe-mode ile). Bulut düşerse `CLOUD_TIMEOUT` loglanır, robot güvenli modda tur atar.
3. **Mock = gerçek sözleşme.** `MockCloud.handle()` ile Nebius handler aynı
   JSON'u üretir; tek parametre değişimiyle (`--real`) gerçek buluta geçilir.
4. **Grace extension:** sim süresi dolarken yama yoldaysa sim ~5 s daha yaşar —
   "bulut gecikmesi" ile "sim bitişi" yarışını yama kazanır.

## 4. Faz 2 — ROS2 Humble katmanı (WSL2, CANLI doğrulandı)

### 4.1 Düğüm haritası

```
                        ┌────────────────────────── ROS2 graph ──────────────────────────┐
                        │                                                                  │
 [InjectDisturbance] ──▶│  /inject_disturbance ──▶ sim_node ──▶ /odom (nav_msgs)         │
   srv + topic          │                                       ├──▶ /ground_truth        │
                        │                                       └──▶ /slip_state          │
                        │                                                                  │
                        │  /odom + /ground_truth + /slip_state ──▶ monitor_node            │
                        │      │                                     │                    │
                        │      │                          /patch/request (PatchRequest)      │
                        │      ▼                                     ▼                    │
                        │  controller_node ◀── /patch/response ◀── bridge_node             │
                        │      │                                     │                    │
                        │      └──▶ /cmd_vel ──▶ sim_node    Nebius (mock|gerçek)          │
                        └──────────────────────────────────────────────────────────────────┘
```

### 4.2 Düğümlerin görevi

| Düğüm | Abonelik | Yayın | İş |
|---|---|---|---|
| `sim_node` | `/cmd_vel`, `/inject_disturbance` | `/odom`, `/ground_truth`, `/slip_state` | Faz-1 fizik motorunu 50 Hz entegre eder; **encoder yanılsamasını** bilinçli üretir |
| `monitor_node` | `/odom`, `/ground_truth`, `/slip_state` | `/anomaly_score`, `/patch/request` | Gerçek hızları harici lokalizasyondan türetir, skoru hesaplar, alarmda paketi yollar |
| `bridge_node` | `/patch/request` | `/patch/response` | HTTP çağrısını worker thread'de yapar, latency'yi mesaja yazar |
| `controller_node` | `/ground_truth`, `/patch/request`, `/patch/response` | `/cmd_vel` | Yörünge takibi; alarm → safe-mode, yama → PID hot-swap |
| `disturbance_node` | — | `/inject_disturbance` + srv | Jüri/test tetikleyicisi: "yağmur başlat" komutu |

### 4.3 Keşif: `edge_loader.py`

ROS düğümleri Faz-1 çekirdeğini **kopyalamaz**, `sys.path` keşfiyle yükler:
`AEROPATCH_EDGE_PATH` → kaynak ağaç gerçek yolu → `/mnt/d/...` yedek.
Böylece fizik/algoritma düzeltmeleri **tek yerde** yapılır, ROS paketi otomatik miras alır.

## 5. Bulut sözleşmesi (mock = gerçek)

Kenar → bulut `POST /dispatch` (TelemetryPacket) ve bulut → kenar (PatchResponse).
**Mock ve gerçek Nebius handler birebir aynı şemayı döndürür** — geçiş sıfır kod değişikliği:

```jsonc
// İstek (kenar -> bulut): son ~0.5 s'lik telemetri penceresi + mevcut kazançlar
{
  "robot_id": "aeropatch-01", "event_id": "evt-1695...", "trigger": "physical_deviation",
  "score": 0.87, "region": "Kadikoy, Istanbul, TR", "mission": "perimeter_patrol",
  "pose": {"x": 1.42, "y": 2.31, "theta": 0.77},
  "current_gains": {"kp": 2.2, "ki": 0.0, "kd": 0.08, "max_speed": 0.22},
  "telemetry": [ {"t": ..., "v_odom": 0.21, "v_true": 0.09, "omega_odom": 0.02,
                  "omega_true": 0.71, "cte": 0.28, ...}, ... 25 kare ]
}

// Yanıt (bulut -> kenar): teşhis + bağlam + uygulanabilir yama
{
  "event_id": "evt-1695...", "confidence": 0.88, "model": "nemo-mock/nemotron-410b",
  "weather_summary": "Light rain in Kadikoy (moderate precipitation, wind 18 km/h, 14C)",
  "weather_source": "tavily://search?q=live+weather+Kadikoy",
  "diagnosis": "Traction loss detected: odometry reports 0.120 m/s more ground speed
                than actual motion ... consistent with wheel slip on a wet surface. ...",
  "patch": {
    "heading_pid":   {"kp": 3.04, "ki": 0.0, "kd": 0.22},
    "slip_compensation": -0.68,     // ölçülen dönüş yanlışlığına feedforward
    "max_speed": 0.16,              // hız tavanı
    "odom_resync": true,            // DR pozu harici ölçüme senkronla
    "safety_mode": "hold_line"
  }
}
```

**Yama kollarının fiziksel gerekçesi:** `kp` sapmayla orantılı agresifleşir
(`kp·(1+0.6·slip_oranı)`, tavan 6.0), `kd` kaygan zeminde salınımı söndürür,
`slip_comp` PID'nin göremediği **sistemli** dönüş kaymasını doğrudan ekler,
`max_speed` kinetik enerjiyi sınırlar, `odom_resync` birikmiş DR hatasını sıfırlar.

## 6. Doğrulama sonuçları (canlı çalıştırıldı)

### 6.1 Birim + entegrasyon testleri — 22/22 ✅ (Windows Python 3.13)

```
tests/test_pid.py        5  ✅ yakınsama, hot-swap integral korunumu, anti-windup, limit, reset
tests/test_physics.py    6  ✅ açı sarması, kuru zeminde odom≡truth, slip→hız/dönüş uyuşmazlığı,
                             düz çizgi, odometri resync
tests/test_anomaly.py    5  ✅ normal akışta alarm yok, slip→alarm (persistence), tekil gürültü
                             alarm üretmez, cooldown tek alarm, bileşen raporu
tests/test_cloud.py      4  ✅ mock şema tamlığı, yama değer aralıkları, latency ölçümü, varsayılanlar
tests/test_demo_e2e.py   2  ✅ uçtan uca: DISTURBANCE→ALARM→PATCH→toparlanma;
                             kuru zeminde YANLIŞ ALARM = 0
```

### 6.2 Faz-1 demo (Windows) — ölçülen çıktı

```
DISTURBANCE t=8.00s (sol teker tutuşu 1.0 → 0.45, 2 s rampa)
ALARM       t=9.20s  score=0.64   → algılama +for 1.2 s
PATCH       ~t=9.9s   round-trip 516 ms (mock 350–800 ms bant içi)
recovery    CTE 0.08 m tepe → 0.04 m final  → yörüngeye dönüş
yanlış alarm: 0 (kuru zemin testi)
grafik:      demo_report.png (yörünge, CTE, skor, slip imzası, DR hatası)
```

### 6.3 Faz-2 ROS2 (WSL2 Ubuntu-22.04, ROS2 Humble) — CANLI ✅

- `colcon build` 2 paket (msgs + aeropatch) derlendi; **bulut-öncesi şema hazır**
- 5 düğüm launch ile ayağa kalktı; canlı döngü ölçüldü:
  - `ALARM score=0.64 → telemetry dispatched` (inject'ten ~0.9 s sonra)
  - `PATCH back in 516 ms: Kp=2.75 Kd=0.22 slip_comp=-0.568`
  - hold-off sonrası döngü **10+ kez tekrarlandı** (sürekli adaptasyon)
- Jüri tetikleyicisi çalışıyor:
  `ros2 service call /inject_disturbance aeropatch_msgs/srv/InjectDisturbance
   "{traction_left: 0.45, traction_right: 1.0, ramp_time: 2.0}"`

## 7. WSL oturum notları (entegrasyon dersleri)

Bu bölüm, aynı yolu izleyecekler için çözülmüş tuzaklardır:

1. **WSL VM boşta kalınca kapanıyor → arka plan build'leri ölür.** Çözüm:
   Windows tarafından kalıcı bir "keeper" süreci (`wsl -- sleep 14400`) başlatıp
   VM'i canlı tutmak; uzun işler `wsl/` altındaki wrapper'larla log dosyasına yazılır.
2. **CRLF zehri:** Windows'ta yazılan `.sh` dosyaları `\r` içerir, bash `: No such file` der.
   `wsl/fix_crlf.py` ile tüm scriptler temizlenir.
3. **`bridge_node`'da `self.executor` adı çakışması:** rclpy `Node`'ta `executor`
   bir property'dir; `ThreadPoolExecutor` bu isimle atanınca node spin'e
   `add_node` çağırır. Düzeltme: `self.pool` olarak yeniden adlandırıldı.
4. **QoS uyuşmazlığı:** `sim_node` `/slip_state`'i `BEST_EFFORT` yayınlıyor,
   `monitor_node` varsayılan `RELIABLE` aboneydi → mesaj hiç ulaşmıyordu.
   Düzeltme: abonelik de `qos_profile_sensor_data` oldu.
5. **`/mnt/d` (DrvFs) üzerinde colcon build çok yavaş** → çalışma alanı
   WSL native dosya sistemine (`~/aeropatch_ws`) kopyalanır; kaynak `edge/`
   ise `AEROPATCH_EDGE_PATH` ile `/mnt/d`'den okunmaya devam eder.

## 8. Faz 3 yol haritası — Gazebo fiziksel doğrulama

Hedef: aynı senaryoyu **gerçek fizik motorunda** (Gazebo) göstermek — sim_node'un
yerine TurtleBot3'ün gerçek Gazebo dinamiği geçer, kod hattının geri kalanı **değişmez**:

1. **Kurulum:** WSL2'de `ros-humble-gazebo-ros-pkgs` + `turtlebot3` paketleri
   (TurtleBot3 Burger: `W=0.16 m`, `r=0.033 m` — Faz-1 sabitleriyle zaten eşleşik).
2. **Düğüm değişimi:** `sim_node` kapatılır; TurtleBot3'ün `/odom`'u ve AMCL/ground-truth
   `monitor_node`'a bağlanır. `bridge_node`, `controller_node`, `disturbance_node` aynen kalır.
3. **Kaygan zemin senaryosu:** İki seçenek —
   - Gazebo `friction` parametresini `disturbance_node` servisi üzerinden düşürmek,
   - veya fiziksel cihazda: ıslak mutfak zemini/telfer bandı (her ikisi de kaydedilebilir).
4. **Canlı video (jüri zorunluluğu):** Gazebo penceresi + rqt_plot (CTE + skor) yan yana
   ekran kaydı; `ros2 topic echo /patch/response` terminalde teşhis metnini gösterir.
5. **Kabul kriteri:** algılama ≤ 1.5 s, yama round-trip ≤ 1 s (mock bant),
   toparlanmada max CTE ≤ 0.15 m, yanlış alarm = 0.

## 9. Faz 4 — Gerçek Nebius bulutuna geçiş

Mock'tan gerçek buluta geçiş **tek ortam değişkeni + tek parametre** ile:

1. **API anahtarları:** `NEBIUS_API_KEY` (Nemotron inference) + `TAVILY_API_KEY` (canlı arama).
2. **Nebius Serverless Endpoint/Jobs:** `cloud/nebius_handler.py` şablonu deploy edilir
   (aynı JSON sözleşmesi, bölüm 5). Handler akışı:
   `telemetri → Tavily live weather araması → Nemotron prompt'u (telemetri+hava+mevcut kazançlar)
    → yapılandırılmış yama JSON'u → yanıt`.
3. **Kenar geçişi:** `bridge_node` parametresi `mock_cloud: false` + `endpoint_url`,
   veya Faz-1 CLI: `python -m edge.run_demo --real --endpoint ... --api-key ...`.
   `CloudBridge` retry (üstel geri çekilme) + 8 s timeout ile donmaya karşı dayanıklı.
4. **Prompt mühendisliği notu:** Nemotron'a serbest metin değil, **şemaya bağlı**
   yama ürettirilir; çıktı `patch` alanı kenarda `clamp`'lenir (kp ≤ 6.0, kd ≤ 1.0,
   |slip_comp| ≤ 1.5) — LLM ne derse desin **fiziksel güvenlik sınırları kenarda zorunlu tutulur.**
5. **Ölçülecek metrikler:** gerçek round-trip (hedef < 1 s), teşhis tutarlılığı
   (hava gerçekten yağmurluysa slip teşhisi), API maliyeti/olay.

## 10. Jüri demosu planı (Physical AI Track)

2–3 dakikalık tek çekim:

| An | Ekranda | Anlatı |
|---|---|---|
| 0:00 | `ros2 launch aeropatch sim_launch.py` + rqt_plot (CTE, skor) | "Robot devriye turunda; kenar algılayıcı saf matematikle izliyor" |
| 0:25 | `ros2 service call /inject_disturbance ...` | "Yağmur başladı — sol teker tutuşunu kaybetti" |
| 0:30 | Terminal: `ALARM score=0.64 → telemetry dispatched` | "Kenar ~1 saniyede yakaladı; telemetri buluta uçtu" |
| 0:32 | Terminal: `Light rain in Kadikoy... (Tavily)` + `PATCH back in 516 ms` | "Ajan canlı havayı aradı, Nemotron 'ıslak zemin traction kaybı' dedi" |
| 0:35 | rqt_plot: CTE 0.08 m tepe → 0'a iner | "Yama sıcak uygulandı: robot kendini toparladı" |
| 1:00 | (Faz 3'ten sonra) aynı akış Gazebo TurtleBot3 penceresinde | "Aynı hattın gerçek fizik motorundaki kanıtı" |
| 1:30 | `demo_report.png` + RAPOR.md | "22/22 test, ölçülen gecikmeler, jüriyenin inceleyeceği kanıtlar" |

**Öne çıkan iddia:** kenarda LLM yok (mW'lık aritmetik), bulutta bağlamlı zekâ var;
ikisi arasındaki sözleşme o kadar dar ki robot **bulut düşerse bile güvenli modda
yaşamaya devam eder.** "Milisaniyelerde geri dönüş" hedefi, gerçek bulutta < 1 s
round-trip hedefiyle somutlanır (mock bant 350–800 ms).

---

*Rapor sonu — AeroPatch, d:\\...\\nebius çalışma ağacı.*
