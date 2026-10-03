# BUILD NOTLARI — WSL Derleme Sorunları ve Çözümleri

> Bu döküman, Faz 2.5 (gerçek NVIDIA NIM bulutu) testine hazırlık sırasında
> yaşanan derleme/komut sorunlarını ve kanıtlanmış çözümlerini toplar.
> `MANUAL_TEST.md`'nin tamamlayıcısıdır; oradaki sistem testlerini bozmaz.

---

## 1) Kopya workspace tuzağı (EN ÖNEMLİ)

**Sorun:** WSL'deki `~/aeropatch_ws` D: sürücüsündeki `ros_ws/`'nin bir **KOPYA**sıdır.
Windows tarafında yaptığınız her kod değişikliği (`setup.py`, node dosyaları, config)
WSL'ye **otomatik gitmez** — eski kod derlenir, yeni özellikler kurulumda görünmez.

**Belirti:** `install/aeropatch/lib/aeropatch/` listesinde yeni eklenen executable yok
(örn. `ekf_node` listede çıkmadı).

**Çözüm (derlemeden ÖNCE her zaman çalıştır):**

```bash
wsl -d Ubuntu-22.04 -- bash -c "rm -rf ~/aeropatch_ws/src && cp -r /mnt/d/.gemini/antigravity-ide/scratch/nebius/ros_ws/src ~/aeropatch_ws/src"
```

Sonra `ls ~/aeropatch_ws/src/aeropatch/aeropatch/` ile node listesini doğrulayın.

---

## 2) colcon build 30 sn timeout'u

**Sorun:** Araç katmanı 30 sn'de komutu öldürür; colcon tam build 1-2 dk sürer.
Doğrudan çalıştırma `Command timed out after 30000ms` verir ve **inner bash de ölür**
(colcon yarıda kalır, hiçbir şey derlenmez).

**Kanıt:** İlk denemede colcon hiç başlamadı (pgrep: 0 süreç, log yok).

**Çözüm — 3 parça:**

a) Betik **kendi çıktısını loga yazsın** (`exec > "$OUT" 2>&1`), Windows tarafında
   `> dosya` redirect'i gerekmesin → `wsl/build_full2.sh` bu kalıbı kullanır.

b) Windows tarafından **tırnaksız, ayrık** başlat (yolda boşluk yoksa tırnak gerekmez):

```
start /b wsl -d Ubuntu-22.04 -- bash /mnt/d/.gemini/antigravity-ide/scratch/nebius/wsl/build_full2.sh
```

c) **Yokla:** `wsl/poll_full.sh` logun son 12 satırını + colcon'un çalışıp
   çalışmadığını gösterir. `BUILD_DONE` görünene kadar bekle.

**Başarı kanıtı:** `Summary: 2 packages finished [1min 59s]` + `BUILD_RC=0`.

---

## 3) CRLF tuzağı (her yeni .sh dosyasında)

**Sorun:** Windows'ta oluşturulan `.sh` dosyaları CRLF satır sonu taşır → WSL'de
`bad interpreter` / `unexpected EOF` hataları.

**Çözüm:** Betikleri çalıştırmadan önce her zaman:

```bash
wsl -d Ubuntu-22.04 -- python3 /mnt/d/.gemini/antigravity-ide/scratch/nebius/wsl/fix_crlf.py
```

Çıktıda `fixed:` görünen dosyalar düzeltilmiştir; `ok:` olanlara dokunulmaz.

---

## 4) Windows → WSL alıntı sorunu

**Sorun:** `wsl -- bash -c "içeride 'tırnak' ve 2>/dev/null"` kalıbı araç katmanında
kırılır → `-af: -c: line 1: unexpected EOF while looking for matching '"`.

**Kural:**
- İçinde tırnak/redirect olmayan kısa kontroller → doğrudan `wsl -- komut`
- Karmaşık komutlar → **asla `bash -c` ile satır içi yazma**; `.sh` dosyasına yazıp
  `wsl -- bash /mnt/d/.../script.sh` olarak çalıştır (dosyalar `wsl/` altında).

---

## 5) start /b cmd /c kaçış sorunu

**Sorun:** `start /b cmd /c \"komut\"` — `\"` kaçışı cmd.exe'ye ham olarak gider:
`'\"wsl ...\"' is not recognized as an internal or external command`.

**Çözüm:** `cmd /c` katmanını ve tırnakları tamamen at:

```
start /b wsl -d Ubuntu-22.04 -- bash /mnt/d/.../script.sh
```

---

## 6) timeout /t N >nul çalışmaz

**Sorun:** `ERROR: Input redirection is not supported, exiting the process immediately.`

**Çözüm:** Bekleme için `ping` kullan:

```
ping -n 26 127.0.0.1 >nul
```

(`-n 26` ≈ 25 saniye.)

---

## 7) bg_wrapper.py sınırı

`bg_wrapper.py` `subprocess.run(..., timeout=20)` kullanır; 20 sn'de `BG_PID` döndürür
ama bazı durumlarda Windows tarafı yine bekleyip 30 sn timeout'a düşebilir.
**Uzun işler (build, oturum) için:** `start /b` + kendi-logluyan betik (`build_full2.sh`
kalıbı) daha güvenilirdir. `bg_wrapper` kısa detach işleri için kalsın.

---

## 8) BİLİNEN AÇIK SORUN: ekf_node kurulmadı

**Durum:** `build_full2.sh` → `BUILD_RC=0`, 9 executable kuruldu
(bridge, controller, disturbance, gz_*, monitor, sim) ama **`ekf_node` listede yok**.

**Şüphe:** WSL'deki `~/aeropatch_ws/src/aeropatch/setup.py` kopyasının eski olması
(D: sürümünde `ekf_node = aeropatch.ekf_node:main` satır 38'de kayıtlı).

**Karar (kullanıcı):** ekf_node **sonra** eklenecek; önce diğer kısımlar test edilecek.

**Çözüm adımları (ileride):**
1. `wsl -- cat /home/apo/aeropatch_ws/src/aeropatch/setup.py` → ekf satırı var mı?
2. Yoksa: bölüm 1'deki senkron komutunu çalıştır (D: → WSL)
3. `build_full2.sh`'yi yeniden başlat → `poll_full.sh` ile `ekf_node`'u listede doğrula

---

## 9) Çalışan uçtan uca akış (kopyala-yapıştır)

```bash
# 0) CRLF + senkron
wsl -d Ubuntu-22.04 -- python3 /mnt/d/.gemini/antigravity-ide/scratch/nebius/wsl/fix_crlf.py
wsl -d Ubuntu-22.04 -- bash -c "rm -rf ~/aeropatch_ws/src && cp -r /mnt/d/.gemini/antigravity-ide/scratch/nebius/ros_ws/src ~/aeropatch_ws/src"

# 1) Derle (arka plan) + yokla
start /b wsl -d Ubuntu-22.04 -- bash /mnt/d/.gemini/antigravity-ide/scratch/nebius/wsl/build_full2.sh
wsl -d Ubuntu-22.04 -- bash /mnt/d/.gemini/antigravity-ide/scratch/nebius/wsl/poll_full.sh

# 2) Bulut sunucusu (WSL icinde, port 8091)
wsl -d Ubuntu-22.04 -- bash /mnt/d/.gemini/antigravity-ide/scratch/nebius/wsl/cloud_start.sh

# 3) NVIDIA NIM'li ROS oturumu (launch + enjeksiyon + zincir dogrulama)
wsl -d Ubuntu-22.04 -- bash /mnt/d/.gemini/antigravity-ide/scratch/nebius/wsl/ros_session_nvidia.sh
```

**Beklenen (adım 3):** `CLOUD_HEALTH_OK → LAUNCH_ALIVE → INJECT → (30 sn izleme)
→ launch logunda alarm/patch satırları → NVIDIA_SESSION_DONE`.
Bridge artık `mock_cloud: false` ile gerçek NVIDIA NIM'e (`127.0.0.1:8091`) gider;
Tavily anahtarı boş olduğu için bulut tarafı hava verisini DuckDuckGo (DDGS) yedeğiyle arar.

---

## 10) Handler takılma tuzağı — NIM timeout'suz çağrı (DÜZELTİLDİ)

**Sorun:** `nemotron_diagnose` 3 modellik zincir + `timeout=6` ile worst-case
**21+ sn** sürüyor (3×(6+1) sn), weather eklenince ~29 sn. NIM yavaş/takılı
olduğunda handler cevabı çok geç döndürür → bridge pes eder (BrokenPipeError)
→ **yama hiç dönmez** → controller SAFE modda asılı kalır → RViz'de eski
halinde takılı kalır ("ilk uyanışta çizime dönmüyor").

**Kanıt (cloud_server.log):** `Exception occurred ... BrokenPipeError: [Errno 32]`
+ 20 dk sonra tekrar denenen istekler.

**Çözüm (kesin-dönüş garantisi) — `nebius_handler.py`:**

a) `_run_with_limit(fn, *args, limit_s)`: çağrıyı **daemon thread + join** ile
   sınırlar. Join dolarsa handler yine de zamanında yamayı yollar
   (thread arkada devam etse bile).

b) Süre bütçesi: weather **join(4)** + Nemotron **join(8)** → worst-case
   **~12.5 sn** < bridge `timeout_s: 30.0` (params_nvidia.yaml) →
   **patch her koşulda döner, SAFE asılı kalamaz.**

c) LLM başarısızsa **MANUEL fallback** (fallback_diagnose): deterministik
   buluşsal teşhis + yama (kp/slip_compensation/max_speed) — zincir kopmaz.

d) `requests.post(..., timeout=(2, 4))`: connect/read timeout'ları düşürüldü
   (model zinciri artık join ile sınırlı, zincir içi timeout kritik değil).

**Canlı doğrulama (test_handler_fast.py):**
```
call 1: 12.0s model=fallback-heuristic kp=2.2 slip=0.125 err=NIM timeout (>8s) -> manual fallback
call 2: 8.7s model=fallback-heuristic kp=3.0 slip=0.125 err=NIM timeout (>8s) -> manual fallback
HANDLER_FAST_DONE
```
→ NIM yavaşken bile yama < 13 sn'de döndü (2/2).

---

## 11) HIZLI BUILD AKIŞI (tek komut, kopyala-yapıştır)

Eski sorunların HEPSİ çözülmüş tek akış — artık 3 ayrı komutla uğraşmayın:

```bash
# Senkron (D: -> WSL) + colcon build — kendi loguna yazar, arka planda:
start /b wsl -d Ubuntu-22.04 -- bash /mnt/d/.gemini/antigravity-ide/scratch/nebius/wsl/sync_build.sh

# Yokla (BUILD_DONE görünene kadar ~2 dk):
type wsl\logs\sync_build.log
```

`sync_build.sh` içerik özeti: `rm -rf ~/aeropatch_ws/src` → D:'den kopya →
`fix_crlf.py` → `colcon build --symlink-install` → `BUILD_RC` + executable listesi.
CRLF fix içeride yapıldığı için **ayrı fix_crlf komutu gerekmez**.

Sonra demo (cloud + Gazebo + RViz + enjeksiyon hepsi otomatik):

```bash
start /b wsl -d Ubuntu-22.04 -- bash /mnt/d/.gemini/antigravity-ide/scratch/nebius/wsl/gz_demo_real.sh
```

İzleme: `type wsl\logs\gz_demo_real_out.log` → `ZINCIR_OK` görünene kadar.
`gz_demo_real.sh` artık en sonda **14 sn bekleyip** ALARM/PATCH/SLIP sayaçlarını
yazar; yama döndüyse `ZINCIR_OK`, dönmediyse `cloud_server.log` kuyruğunu basar.

---

## 12) KALAN YARDIMCI BETİKLER (temizlendi — sadece aktifler)

`wsl/` altında artık yalnızca bunlar durur:

| Betik | Görev |
|---|---|
| `sync_build.sh` | D:→WSL senkron + colcon build (tek beton) |
| `gz_demo_real.sh` | Tam otomatik demo: cloud+Gazebo+RViz+enjeksiyon+doğrulama |
| `cloud_start.sh` / `cloud_stop.sh` | NIM sunucusu (pkill+start içeride — çakışmasız) |
| `gz_status.sh` / `gz_stop.sh` | Süreç sayaçları / tam durdurma |
| `gz_inject.sh` / `inject_wet.sh` | Manuel enjeksiyon |
| `ros_start.sh` | Faz 2 ROS2 oturumu (Gazebo'suz) |
| `kill_all.sh` | Her şeyi öldür |
| `record_start.sh` + `ros_recorder.py` | Demo kaydı (jsonl) |
| `test_handler_fast.py` | Handler kesin-dönüş testi (bölüm 10) |
| `bg_wrapper.py` / `fix_crlf.py` | Arka plan sarmalayıcı / CRLF düzeltici |
