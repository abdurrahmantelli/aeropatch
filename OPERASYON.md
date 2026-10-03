# OPERASYON KİTABI — Tekrarlanan Komutlar (Kopyala-Yapıştır)

> Sorun/çözüm ayrıntıları `BUILD_NOTLARI.md`'de; bu kitap **sadece komutlar**.
> Tüm yollar: `d:\.gemini\antigravity-ide\scratch\nebius\` (WSL'de `/mnt/d/...`)

## 0) ALTIN KURAL — 30 sn araç timeout'u

30 saniyeden uzun süren **her** WSL komutu (build, demo, curl retry) aracı
katmanında ölür. Kural:

- **Hızlı kontrol (<10 sn):** doğrudan `wsl -d Ubuntu-22.04 -- komut` (tırnaksız)
- **Uzun iş (>25 sn):** `start /b` ile arka planda başlat → logu Windows'tan `type` ile yokla
- **Bekleme:** `ping -n 25 127.0.0.1 >nul` (25 sn; `-n 40` yapma — 30 sn limiti aşar)

## 1) ARKA PLANDA ÇALIŞTIRMA (start /b deseni)

```bat
:: Uzun süren betiği arka planda başlat (hemen döner):
start /b wsl -d Ubuntu-22.04 -- bash /mnt/d/.gemini/antigravity-ide/scratch/nebius/wsl/sync_build.sh

:: 25 sn bekle, sonra logu Windows'tan oku (WSL'e girmeden — timeout riski YOK):
ping -n 25 127.0.0.1 >nul
type wsl\logs\sync_build.log
```

**Yasak:** `start /b cmd /c "wsl ..."` — `\"` kaçışı cmd'ye ham gider, komut tanınmaz.
**Yasak:** `wsl -- bash -c "içinde tırnak"` — satır içi karmaşık komut kırılır; `.sh` dosyasına yaz.

## 2) DETACHED ÇALIŞTIRMA (pencereler AÇIK kalır)

```bat
:: Demo tam detach (setsid+nohup): Gazebo+RViz konsol ölse bile KALIR:
start /b wsl -d Ubuntu-22.04 -- bash /mnt/d/.gemini/antigravity-ide/scratch/nebius/wsl/start_detached.sh
```

`start_detached.sh` içeride: eski demo instance'ını pkill'ler → `setsid nohup`
ile başlatır → `DETACHED_OK` yazar. Demo kendi oturumunda yaşar.
(`start_detached.sh` yerine doğrudan `gz_demo_real.sh` çalıştırırsan WSL
kapanınca/demo scripti bitince pencereler düşer.)

Durdurma: `wsl -d Ubuntu-22.04 -- bash /mnt/d/.../wsl/gz_stop.sh` (veya `kill_all.sh`)

## 3) TEK-SHOT BETİK — bg_wrapper.py (CRLF fix + log otomatik)

Windows'ta yeni yazılan `.sh` CRLF taşır; bg_wrapper kopyayı /tmp'ye alıp
CRLF'i düzeltir, logu otomatik `wsl/logs/<ad>.log`'a yazar:

```bat
start /b wsl -d Ubuntu-22.04 -- python3 /mnt/d/.gemini/antigravity-ide/scratch/nebius/wsl/bg_wrapper.py diag_all.sh
ping -n 15 127.0.0.1 >nul
type wsl\logs\diag_all.sh.log
```

## 4) BUILD AKIŞI (kod değişikliği sonrası — sırayla)

```bat
:: 1) Windows tarafında hızlı doğrulama:
python -m py_compile ros_ws\src\aeropatch\aeropatch\gz_truth_node.py && echo SYNTAX_OK
python -m pytest tests/ -q          :: 22 passed beklenir

:: 2) Build (senkron D:→WSL + colcon, arka planda, ~2 dk):
start /b wsl -d Ubuntu-22.04 -- bash /mnt/d/.gemini/antigravity-ide/scratch/nebius/wsl/sync_build.sh
ping -n 25 127.0.0.1 >nul
type wsl\logs\sync_build.log        :: SYNC_OK + BUILD_RC=0 beklenir

:: 3) Yeni node kuruldu mu (executable listesi):
wsl -d Ubuntu-22.04 -- ls /home/apo/aeropatch_ws/install/aeropatch/lib/aeropatch/
```

`sync_build.sh` CRLF fix'i İÇERİDE yapar → ayrı `fix_crlf` komutu gerekmez.
**Uyarı:** WSL'deki `~/aeropatch_ws` D:'nin KOPYAsıdır — build etmeden
senkron etmeden yeni kod GİRMEZ (BUILD_NOTLARI.md bölüm 1).

## 5) LOG OKUMA — Windows'tan `type` (WSL'e GİRMEDEN)

Loglar D: sürücüsünde → WSL komutu gerekmez, timeout riski sıfır:

```bat
type wsl\logs\gz_demo_real_out.log   :: demo özeti + ZINCIR_OK
type wsl\logs\cloud_server.log       :: [TAVILY]/[NIM]/[HANDLER] satırları
type wsl\logs\gz_launch.log          :: düğüm logları (uzun)
```

WSL'den okunacaksa tek satır tırnaksız: `wsl -d Ubuntu-22.04 -- tail -15 /mnt/d/.../wsl/logs/cloud_server.log`

## 6) WSL SOĞUK AÇILIŞ (VM uykudan uyanırken ilk komut takılabilir)

```bat
:: İlk komut 30 sn timeout verdiyse: keepalive başlat, bekle, tekrar dene:
start /b wsl -d Ubuntu-22.04 -- sleep 3600
ping -n 25 127.0.0.1 >nul
wsl -d Ubuntu-22.04 -- echo WSL_HAZIR
```

## 7) KANITLANMIŞ DOĞRULAMA GREP DESENLERİ

| Ne aranır | Desen | Nerede |
|---|---|---|
| Build başarılı | `BUILD_RC=0` / `SYNC_OK` | sync_build.log |
| Demo zinciri tamam | `ZINCIR_OK` / `OZET: TRUTH=` | gz_demo_real_out.log |
| Alarm atıldı | `ALARM score=` | gz_launch.log |
| Yama uygulandı | `PATCH applied:` | gz_launch.log |
| Bulut kaynağı | `kaynak=NIM` (gerçek) / `kaynak=FALLBACK` | cloud_server.log |
| Kayma imzası | `SLIP_GAP=` | gz_launch.log |
| Spawn | `SPAWN_OK` | gz_demo_real_out.log |

## 8) TİPİK GÜN AKIŞI (taze demo + kayıt)

```bat
:: 1) Taze demo (cloud+Gazebo+RViz+enjeksiyon otomatik, AÇIK KALIR):
start /b wsl -d Ubuntu-22.04 -- bash /mnt/d/.gemini/antigravity-ide/scratch/nebius/wsl/start_detached.sh

:: 2) ~20 sn sonra ekran kaydını başlat (Win+G / OBS) — 48 sn'lik pencereyi çek

:: 3) Zinciri izle:
type wsl\logs\gz_demo_real_out.log   :: ZINCIR_OK görünene kadar
type wsl\logs\cloud_server.log       :: bulut terminalini de videoya al

:: 4) Bitince (40 dk açık bırakma — odom sistematik sapması birikir):
wsl -d Ubuntu-22.04 -- bash /mnt/d/.gemini/antigravity-ide/scratch/nebius/wsl/gz_stop.sh
```

## 9)  ekstralar

1. **Model sırası sorunu (sıradaki koşuda düzeltilecek):** handler
   `lightning → super → llama` sırasıyla dener; lightning 25s'te çoğunlukla
   timeout → 35s bütçe tükenir → fallback yarışı kazanır (logda 8/8 OK olan
   `super-120b` 2. sırada bekliyor). Çözüm: hızlı modeli başa al veya
   lightning'e circuit breaker. Beklenen: `kaynak=NIM` çoğunlukta.
2. **secrets.env güvenliği:** `cloud/secrets.env` içinde gerçek anahtarlar
   var — git'e eklenmeyecek (`.gitignore`), jüriye repoda gösterme.
3. **Demo bitince durdur:** dünkü 2.9m sapma, 40 dk açık kalan artık
   oturumun encoder artefaktıydı — koşu sonrası `gz_stop.sh` alışkanlığı.
4. **CRLF'ten korunmanın kalıcı yolu:** yeni .sh dosyalarını her zaman
   bg_wrapper ile çalıştır veya editor'de LF olarak kaydet.
5. **Video planı hazır:** LOG_YORUMU.md bölüm 6 + 7'de zamanlanmış atış
   listesi (enkjeksiyon anı → ALARM → bulut terminali → PATCH → toparlanma).
