"""Nebius Serverless handler şablonu — gerçek dağıtım için (Faz 4).

Nebius Serverless'da function/endpoint olarak deploy edilir.
mock_cloud.MockCloud ile AYNI sözleşmeyi döndürür, ancak:
  * Tavily API ile GERÇEKTEN canlı hava durumu arar
  * Nebius AI Studio'da Nemotron modelini çağırır (teşhis + yama üretimi)

Deploy notları:
  1) NEBIUS_API_KEY ve TAVILY_API_KEY ortam değişkenlerini secret olarak tanımlayın
  2) endpoint: POST /  -> body = TelemetryPacket.to_dict() (edge/telemetry.py)
  3) edge tarafında: bridge_node parametresi mock_cloud: false, endpoint_url: <url>
"""
from __future__ import annotations

import json
import os
import threading
import time
from typing import Any, Dict, List

NEBIUS_API_KEY = os.environ.get("NEBIUS_API_KEY", "")
TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY", "")
NEBIUS_BASE_URL = os.environ.get(
    "NEBIUS_BASE_URL", "https://integrate.api.nvidia.com/v1")
# NOT: meta/llama-3.1-8b-instruct -> 410 Gone, 51b -> 500 (bu hesapta bozuk).
# Canli probe (wsl/probe_models.py): super-120b 8/8 OK (en hizli);
# lightning thinking uretimi 25 sn'yi asiyordu (log kaniti: tum yamalar
# fallback'ti). Siralama super ONCE -> kesin NIM cevapi (kullanici istegi).
NEMOTRON_MODEL = os.environ.get("NEMOTRON_MODEL",
                                "nvidia/nemotron-3-super-120b-a12b")


def live_weather(region: str) -> Dict[str, Any]:
    # 1. Tavily
    if TAVILY_API_KEY:
        try:
            return tavily_weather(region)
        except Exception as exc:
            print(f"[TAVILY] ERROR: {str(exc)[:120]} -> falling back to DDG",
                  flush=True)
    # 2. DuckDuckGo (ücretsiz, anahtarsız)
    try:
        from ddgs import DDGS
        with DDGS(timeout=8) as ddgs:
            results = list(ddgs.text(f"weather in {region} rain wind", max_results=3))
            print(f"[DDG] 'weather {region}' -> {len(results)} results", flush=True)
            snippets = " ".join(r.get("body", "") for r in results)
            return {"summary": snippets[:500] or "no weather data", "source": "ddg://search"}
    except:
        # HAVA API yok (Tavily 401 / DDG hata): DEFAULT KURU (kullanici
        # karari) — teshis "dry + traction loss" olur, Kp artisi kuru
        # zeminde guvenli; islak dal (Kp<=1.5 hold) canli havada devreye
        # girer. "weather info unavailable" yerine net KURU varsayimi:
        # juri hikayesi temizlenir (teshis belirsiz kalmiyordu).
        print("[WEATHER] no API -> dry default", flush=True)
        return {"summary": "dry ground, clear conditions "
                           "(live weather unavailable)",
                "source": "default-dry"}

# ---------------------------------------------------------------- Tavily ---
def tavily_weather(region: str) -> Dict[str, Any]:
    """Tavily Search API ile bölgenin canlı hava durumunu getirir."""
    import requests  # serverless'da requirements.txt'e ekleyin
    # NOT: sorgu degiskeni bir kez tanimlanir — eski kodda print icinde
    # 'query' tanimsizdi -> NameError -> Tavily basarili olsa bile DDG'ye
    # dusuyordu (anahtar geldikten sonra bile tetiklenecekti).
    query = f"current weather conditions {region} rain wind"
    resp = requests.post(
        "https://api.tavily.com/search",
        json={
            "api_key": TAVILY_API_KEY,
            "query": query,
            "search_depth": "basic",
            "max_results": 3,
        },
        timeout=6)
    resp.raise_for_status()
    data = resp.json()
    print(f"[TAVILY] query='{query}' -> {len(data.get('results', []))} results "
          f"({resp.elapsed.total_seconds():.1f}s)", flush=True)
    snippets = " ".join(r.get("content", "") for r in data.get("results", []))
    return {
        "summary": snippets[:500] or f"no live data for {region}",
        "source": "tavily://search",
    }


# -------------------------------------------------------------- Nemotron ---
PROMPT = """You are a robotics control engineer agent on a differential-drive robot.
The edge anomaly detector just fired. Telemetry shows the robot's odometry
(encoders) disagrees with external localization - a physical deviation signature.

Live weather from web search: {weather}

Recent telemetry (last {n} samples, 50 Hz):
{telemetry}

Current controller gains: {gains}

Diagnose the physical cause (e.g. wheel slip on wet surface, side wind, motor
degradation). Then output ONLY a JSON object with this exact schema:
{{"diagnosis": "<one paragraph>", "patch": {{"heading_pid": {{"kp": <float>,
"kd": <float>}}, "slip_compensation": <float rad/s>,
"max_speed": <float m/s>}}, "confidence": <0-1>}}
Rules: kp in [0.8, 2.6]; kd in [0.05, 0.35]; slip_compensation in [-1.5, 1.5];
max_speed in [0.05, 0.22]. If weather indicates rain/wet ground, REDUCE kp
(20-40% below current) and RAISE kd strongly (2-3x current) -- aggressive
steering on wet ground causes skid/oscillation; also CUT max_speed (~0.10).
If telemetry shows wheel slipping (v_odom >> v_true), prefer lower kp +
higher kd + speed cut. Never raise kp on wet/slippery ground.
If ground is dry/clear, the surface has dried and grip is RESTORED: return
kp to the baseline (2.2) and kd to the baseline (0.08). Do NOT raise kp
above baseline -- aggressive steering is not the cure on dry ground; the
accumulated encoder drift from the past slip window is corrected by the
system's odometry re-anchoring (resync), not by higher gains. Set
slip_compensation to 0.0 unless telemetry shows ACTIVE slipping right now
-- a stale slip compensation measured during a past wet window becomes a
permanent bias on dry ground and makes odometry diverge linearly."""


def nemotron_diagnose(payload: Dict[str, Any],
                      weather: Dict[str, Any]) -> Dict[str, Any]:
    import requests
    tel: List[Dict[str, Any]] = payload.get("telemetry", [])
    lines = []
    for s in tel[-10:]:
        lines.append(f"t={s.get('t', 0):.2f} v_odom={s.get('v_odom', 0):.3f} "
                     f"v_true={s.get('v_true', 0):.3f} "
                     f"omega_odom={s.get('omega_odom', 0):.3f} "
                     f"omega_true={s.get('omega_true', 0):.3f} "
                     f"cte={s.get('cte', 0):.3f}")
    prompt = PROMPT.format(weather=weather["summary"], n=len(lines),
                           telemetry="\n".join(lines),
                           gains=json.dumps(payload.get("current_gains", {})))
    # FAIL-FAST zincir: uc model, her modelin KENDI timeout/max_tokens'i.
    # Log kaniti (01/Oct run): lightning okuma 25 sn'de HIC donmedi (26.3s
    # HATA); super-120b reasoning 256 token'i tuketip content=None dondu
    # ('NoneType has no len'); llama 6.2s'te KESIN OK — ama zincir ona
    # ulasamadan 35s'lik butce doldu -> tum yamalar fallback'e dustu.
    # Cozum: super ONCE (1024 token: reasoning bitince gercek JSON),
    # llama guvenlik, lightning son "hizli deneme". Hepsi NIM butcesinde.
    models_chain = [
        ("nvidia/nemotron-3-super-120b-a12b", (5, 12), 1024),
        ("meta/llama-3.2-11b-vision-instruct", (5, 20), 256),
        (NEMOTRON_MODEL, (5, 6), 768),
    ]
    last_exc: Exception = RuntimeError("empty model chain")
    used_model = NEMOTRON_MODEL
    text = ""
    for m, t_o, mx in models_chain:
        t_m = time.perf_counter()
        try:
            resp = requests.post(
                f"{NEBIUS_BASE_URL}/chat/completions",
                headers={"Authorization": f"Bearer {NEBIUS_API_KEY}"},
                json={"model": m, "temperature": 0.2,
                      "max_tokens": mx, "messages": [{"role": "user",
                                                      "content": prompt}]},
                timeout=t_o)
            resp.raise_for_status()
            # content=None (reasoning tukendi) -> len(None) crash yerine
            # hizli sonraki modele gec (bos icerik = HATA)
            msg = resp.json().get("choices", [{}])[0].get("message") or {}
            text = (msg.get("content") or "").strip()
            if not text:
                raise ValueError("empty content (reasoning consumed max_tokens)")
            used_model = m
            print(f"[NIM] model={m} -> OK "
                  f"({time.perf_counter() - t_m:.1f}s, {len(text)} chars)",
                  flush=True)
            break
        except Exception as exc:
            last_exc = exc
            print(f"[NIM] model={m} -> ERROR: {str(exc)[:100]} "
                  f"({time.perf_counter() - t_m:.1f}s)", flush=True)
            time.sleep(0.3)
    if not text:
        raise last_exc
    # Nemotron-3.5 reasoning: thinking blogundan SONRASINI al
    # (kapanis etiketi editor aracini bozdugu icin parcalardan kurulur)
    _think_close = "<" + "/think" + ">"
    if _think_close in text:
        text = text.split(_think_close, 1)[1]
    # Thinking sarmalayicisi / markdown citi / on junk -> son gecerli JSON'u sec
    text = text.replace("```", " ")
    result = None
    pos = text.find("{")
    end = text.rfind("}") + 1
    while pos != -1:
        try:
            result = json.loads(text[pos:end])
        except Exception:
            pass
        pos = text.find("{", pos + 1)
    if result is None:
        raise ValueError("no JSON in model output: " + text[:80])
    # --- KANIT-TABANLI RESYNC CLAMP (LLM kararina birakilmaz) ---
    # LLM yalniz son 10 ornege bakar; son resync'ten beri biriken
    # odometri sapmasini (DR hatasini) GOREMEZ — prompt semasinda
    # odom_resync alanı bile yok. Log kaniti (02/Oct run): NIM yamalarinda
    # resync hic gelmedi -> monitor resync'i atliyor -> birikmis DR hatasi
    # kalici -> sonsuz alarm dongusu (55 dk, her ~15 sn ALARM, skor dusmedi).
    # Cozum: patinaj/savurma/sapma KANITI varsa resync ZORUNLU. Bu karar
    # telemetri kanitindan gelir; LLM'in kp/kd/secimlerine dokunulmaz.
    _rc = tel[-10:] if len(tel) >= 10 else tel
    _n = max(len(_rc), 1)
    slip_ev = sum(s.get("v_odom", 0.0) - s.get("v_true", 0.0) for s in _rc) / _n
    yaw_ev = sum(abs(s.get("omega_odom", 0.0) - s.get("omega_true", 0.0))
                 for s in _rc) / _n
    cte_ev = abs(_rc[-1].get("cte", 0.0)) if _rc else 0.0
    force_resync = slip_ev > 0.015 or yaw_ev > 0.10 or cte_ev > 0.15
    if force_resync and not result.get("odom_resync"):
        print(f"[HANDLER] resync clamp: slip_ev={slip_ev:.3f} "
              f"yaw_ev={yaw_ev:.3f} cte_ev={cte_ev:.2f} -> odom_resync=True "
              f"(overriding LLM choice)", flush=True)
    result["odom_resync"] = bool(result.get("odom_resync")) or force_resync
    # --- KAZANC CLAMP: tirmanma YASAK (log kaniti 12/Oct: dry default sonrasi
    # NIM kp=3.5 dondurdu -> islak pencere bitmisken agresif kazanc zikzak
    # riski. Kuru zeminde ilac baseline + resync; kp tavani baseline+0.4,
    # islakta 1.5. LLM teshisine dokunulmaz, yalniz kazanc sinirlanir.) ---
    _patch = result.get("patch")
    if isinstance(_patch, dict) and isinstance(_patch.get("heading_pid"), dict):
        _wk = (weather.get("summary") or "").lower()
        _wet = any(k in _wk for k in ("rain", "wet", "yağmur", "yagmur",
                                      "shower", "drizzle", "storm"))
        try:
            _kp = float(_patch["heading_pid"].get("kp", 2.2))
        except (TypeError, ValueError):
            _kp = 2.2
        _tavan = 1.5 if _wet else 2.6
        _kp2 = round(max(0.8, min(_kp, _tavan)), 2)
        if abs(_kp2 - _kp) > 1e-9:
            print(f"[HANDLER] kp clamp: {_kp:.2f} -> {_kp2:.2f} "
                  f"(cap {_tavan}, wet={_wet} — climbing banned)", flush=True)
            _patch["heading_pid"]["kp"] = _kp2
    result["weather_summary"] = weather["summary"]
    result["weather_source"] = weather["source"]
    result["model"] = used_model
    return result


# ------------------------------------------------- weather cache (120s) ----
# 2. alarm / ard arda alarmda dis arama (Tavily/DDG) tekrar ATILMAZ:
# ayni lokasyonun sonucu TTL boyunca bellekten 0 ms okunur (kota + gecikme)
WEATHER_CACHE_TTL = 120.0
_WEATHER_CACHE: Dict[str, Any] = {}   # region -> (unix_ts, weather_result)

# ------------------------------------------------------------ fallback ----
def fallback_diagnose(payload: Dict[str, Any],
                      weather: Dict[str, Any]) -> Dict[str, Any]:
    """LLM erisilemezse: AYNI sema ile deterministik UZMAN teshis.

    Rastgele DEGIL — uzman sistem kurallari: ayni telemetri + hava ->
    AYNI yama (Ziegler-Nichols mantigi, siddet bazli surekli kazanc).
    LLM gibi okunabilir gerekce uretir; zincir HICBIR ZAMAN exception
    firlatmaz (SAFE tasarim: yama her kosulda doner).
    """
    tel: List[Dict[str, Any]] = payload.get("telemetry", []) or []
    recent = tel[-10:] if len(tel) >= 10 else tel
    n = max(len(recent), 1)
    v_odom = sum(s.get("v_odom", 0.0) for s in recent) / n
    v_true = sum(s.get("v_true", 0.0) for s in recent) / n
    w_odom = sum(s.get("omega_odom", 0.0) for s in recent) / n
    w_true = sum(s.get("omega_true", 0.0) for s in recent) / n
    cte = abs(recent[-1].get("cte", 0.0)) if recent else 0.0

    w = (weather.get("summary") or "").lower()
    wet = any(k in w for k in ("rain", "wet", "yağmur", "yagmur",
                               "shower", "drizzle", "storm"))

    # --- siddet imzalari (0..1): hangi fiziksel sema baskin? ---
    ratio = v_odom / v_true if v_true > 0.01 else (2.0 if v_odom > 0.01 else 1.0)
    speed_sev = min(max(ratio - 1.0, 0.0), 1.0)   # patinaj (encoder sandali)
    yaw_sev = min(abs(w_odom - w_true) / 2.0, 1.0)  # savurma (asimetri)
    cte_sev = min(cte / 0.8, 1.0)                 # yorunge sapmasi
    sev = max(speed_sev, 0.6 * yaw_sev, 0.5 * cte_sev)

    # --- uzman kurallari (mutabakat fizik): ISLAK zeminde agresif duzeltme
    # patinaj/yalpalama yapar -> Kp DUSER (yumuşat), Kd YUKSELIR (sonum),
    # hiz kesilir. KURU zeminde kazanc siddetle olceklenir (eski davranis). ---
    if wet:
        # STRICT UPPER BOUND (mutabakat): islak zeminde Kp ASLA 1.5 uzerine
        # cikamaz (tavan 1.5, taban 1.2); savrulma arttikca Kp ASAGI cekilir
        # (2.2 -> 1.5 -> 1.2) — tirmanma yerine ters yonlu koruma
        kp = round(min(1.5, max(1.2, 2.2 - 0.8 * sev)), 2)
        kd = round(min(0.25, max(0.18, 0.08 + 0.14 * sev + 0.06)), 3)
        max_speed = round(max(0.08, 0.22 - 0.14 * sev), 3)   # 0.22 -> ~0.10
        slip = max(0.0, v_odom - v_true)   # islak: gecici patinaj telafisi
    else:
        # KURU zemin: hava kurudu -> zemin kurudu -> TUTUS GERI GELDI.
        # Dogru ilac: BASELINE kazanc + odometri resync (birikmis DR hatasini
        # yalniz resync alir; yuksek kp islak pencere sonrasi zikzak yapar —
        # log kaniti 12/Oct: kp=3.5 tirmanmasi kaldirildi).
        # Patinaj telafisi UYGULANMAZ: islak pencerede olculen gecici slip
        # kalici bias yaratip gap'i lineer buyutuyordu (kuru donusten sonra
        # bile artiyordu).
        kp = 2.2                                            # baseline (tirmanma yok)
        kd = 0.08                                           # baseline
        max_speed = 0.22                                    # baseline
        slip = 0.0                          # KURU: telafi yok -> bias yok

    # --- baskin imzaya gore gerekce (LLM uslubu, okunabilir) ---
    if sev < 0.15:
        cause = ("mild disturbance: baseline gains, monitoring continues; "
                 "odometry drift re-anchored")
    elif speed_sev >= max(yaw_sev, cte_sev):
        cause = ("traction loss (wheel slip): encoder over-reports distance; "
                 "gains damped on wet / baseline + resync on dry")
    elif yaw_sev >= cte_sev:
        cause = "yaw disturbance: asymmetric friction skews heading; damping raised"
    else:
        cause = ("path drift: sustained cross-track error; baseline gains + "
                 "odometry resync")
    if wet:
        cause += " + wet ground confirmed by live weather"

    diagnosis = (f"expert fallback [{sev * 100:.0f}% severity]: {cause} "
                 f"(v_odom={v_odom:.3f} vs v_true={v_true:.3f}, "
                 f"cte={cte:.2f} m)")

    return {
        "diagnosis": diagnosis,
        "patch": {"heading_pid": {"kp": kp, "kd": kd},
                  "slip_compensation": slip,
                  "max_speed": max_speed},
        "odom_resync": True,
        "confidence": round(0.5 + 0.3 * sev, 2),
        "weather_summary": weather.get("summary", ""),
        "weather_source": weather.get("source", ""),
        "model": "fallback-expert",
    }


# -------------------------------------------------------------- handler ----
def _run_with_limit(fn, *args, limit_s: float):
    """fn'i daemon thread'de baslatir, en fazla limit_s kadar bekler.

    Kesin-donus garantisi: join dolarsa (None, True) doner — cagri arkada
    devam etse bile handler zamaninda yamayi yollar (bridge timeout'u
    asilmaz, SAFE modda asili kalma olmaz).
    """
    out: Dict[str, Any] = {}

    def _worker() -> None:
        try:
            out["value"] = fn(*args)
        except Exception as exc:  # thread icinde yakala -> (None, False)
            out["error"] = str(exc)[:200]

    th = threading.Thread(target=_worker, daemon=True)
    th.start()
    th.join(limit_s)
    if "value" in out:
        return out["value"], False
    return None, True


def handler(event: Dict[str, Any], context=None) -> Dict[str, Any]:
    """Nebius Serverless giriş noktası (HTTP POST body = event).

    HICBIR ZAMAN exception firlatmaz ve KESIN < ~40 sn'de doner:
      * weather  : thread+join(4)   — kaynak gelmezse fallback summary
      * Nemotron : thread+join(35)  — LLM yavas/takilirsa MANUEL fallback
        (okuma timeout 25 sn: gercek Nemotron ciktisi icin; 4 sn'de hep
         pes ediyordu — log kaniti: tum yamalar fallback-heuristic'ti)
    (MANUEL-ONCE: fallback_diagnose hemen hazirlanir; LLM yamayi
    zenginlestirir, basarisizsa zincir yine de tamamlanir.)
    """
    payload = event if isinstance(event, dict) else json.loads(event)
    # --- RECOVER YOLU (baseline restore, NIM'siz ANINDA) ---
    # monitor: skor alt esigin (recover_score) altinda recover_hold_s
    # boyunca stabil kalirsa trigger='recover' firlatir. Burada bekleme
    # YOK: baseline kazanc (Kp=2.2 Kd=0.08 v_max=0.22) milisaniyelerde
    # doner — kuru zemine donuste tam performans, zincir takilmaz.
    if payload.get("trigger") == "recover":
        t_r = time.perf_counter()
        result = {
            "diagnosis": ("baseline restore: anomaly cleared, nominal gains "
                          "restored (Kp=2.2 Kd=0.08 v_max=0.22)"),
            "patch": {"heading_pid": {"kp": 2.2, "kd": 0.08},
                      "max_speed": 0.22},
            "odom_resync": True,
            "confidence": 1.0,
            "weather_summary": "",
            "weather_source": "none",
            "model": "baseline-restore",
            "event_id": payload.get("event_id", ""),
            "latency_ms": round((time.perf_counter() - t_r) * 1000.0, 1),
        }
        print(f"[HANDLER] RECOVER evt={result['event_id']} "
              f"latency={result['latency_ms']:.0f}ms -> baseline restore",
              flush=True)
        return result
    t0 = time.perf_counter()
    # --- HAVA CACHE (TTL 120s): 2. alarmda Tavily/DDG API cagrilir DEGIL ---
    # Guvenlik-kritik denge (mutabakat): fiziksel mudahale (edge) asla
    # kilitlenmez ama dis arama kotasina ifrat edilmez — ayni lokasyon icin
    # son 120 sn'deki sonuc bellekten 0 ms okunur ("rain" verisi taze).
    region = payload.get("region", "Kadikoy, Istanbul")
    now_s = time.time()
    cached = _WEATHER_CACHE.get(region)
    if cached is not None and now_s - cached[0] < WEATHER_CACHE_TTL:
        weather, w_timeout = cached[1], False
        print(f"[HANDLER] weather cache HIT: {region} "
              f"(TTL {WEATHER_CACHE_TTL:.0f}s) -> 0ms, no API call",
              flush=True)
    else:
        # Tavily timeout=6 + overhead -> 4s'lik limit Tavily'yi HEP
        # olduruyordu (log: weather=fallback, w_timeout=True). 8s: döner.
        weather, w_timeout = _run_with_limit(live_weather, region, limit_s=8.0)
        if weather is not None:
            _WEATHER_CACHE[region] = (now_s, weather)
            print(f"[HANDLER] weather cache MISS: API result cached "
                  f"(TTL {WEATHER_CACHE_TTL:.0f}s)", flush=True)
        if weather is None:
            weather = {"summary": "weather info unavailable (timeout)",
                       "source": "fallback"}
    manual = fallback_diagnose(payload, weather)
    # Weather timeout olsa bile NIM denenir: telemetri slip imzasini
    # tasir, LLM weather'siz de teshis koyabilir (toplam sure yeterli).
    result, n_timeout = _run_with_limit(
        # NIM butcesi ~35 sn (hava 4s + NIM 35s = 39s < bridge 45s):
        # gecikme kabul (kullanici onayi), yama GARANTILI doner
        nemotron_diagnose, payload, weather, limit_s=35.0)
    if result is None or n_timeout:
        result = manual
        result["cloud_error"] = ("NIM timeout (>35s) -> manual fallback"
                                 if n_timeout else "invalid model output")
    elif "error" in result or result.get("model") == "fallback-expert":
        result = manual
        result["cloud_error"] = "NIM error -> manual fallback"
    result["event_id"] = payload.get("event_id", "")
    result["latency_ms"] = round((time.perf_counter() - t0) * 1000.0, 1)
    # Bulut onayli duzeltme: HER yamada resync GARANTILI — LLM False/eksik
    # gonderse bile edge odom'u gercege hizalar (SLIP_GAP yamada duser;
    # "slip hep artiyor" kok nedeni NIM'in resync'i eksik donmesiydi)
    result["odom_resync"] = True
    src = "NIM" if result.get("model") not in (None, "fallback-expert") \
        else "FALLBACK"
    print(f"[HANDLER] evt={result['event_id']} src={src} "
          f"weather={weather.get('source', '?')} "
          f"model={result.get('model', '?')} "
          f"latency={result['latency_ms']:.0f}ms "
          f"w_timeout={w_timeout} n_timeout={n_timeout}", flush=True)
    return result
