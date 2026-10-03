#!/usr/bin/env python3
"""Handler kesin-donus testi: handler'i 2 kez cagirir, sure + model yazar.

Beklenti: her cagri < 13 sn (thread+join garantisi); NIM yavassa
cloud_error='NIM timeout' + model='fallback-heuristic' ama ZINCIR doner.
Kullanim: wsl -d Ubuntu-22.04 -- python3 -B /mnt/d/.../wsl/test_handler_fast.py
"""
import json
import os
import sys
import time

# secrets.env'yi IMPORT'dan ONCE yukle — handler env'i import aninda okur.
# (Bu yukleme yoksa test sureci anahtarsiz calisir -> NIM 500 'Missing
# Authorization' doner -> YANLIS fallback alarmi. Sunucunun yuklemesiyle ayni.)
def _load_secrets() -> None:
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "..", "cloud", "secrets.env")
    path = os.path.abspath(path)
    if not os.path.exists(path):
        print("UYARI: secrets.env bulunamadi:", path, flush=True)
        return
    with open(path, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            os.environ.setdefault(key.strip(), val.strip().strip("'\""))

_load_secrets()
sys.path.insert(0, "/mnt/d/.gemini/antigravity-ide/scratch/nebius/cloud")

from nebius_handler import handler  # noqa: E402

EVENT = {
    "robot_id": "aerobot", "event_id": "fast-test-1", "trigger": "anomaly",
    "score": 0.87, "region": "Kadikoy, Istanbul, TR",
    "pose": {"x": 1.0, "y": 0.5, "theta": 0.2},
    "current_gains": {"kp": 2.2, "ki": 0.0, "kd": 0.08, "max_speed": 0.22},
    "telemetry": [
        {"x": 1.0, "y": 0.5, "theta": 0.2, "v_odom": 0.22, "v_true": 0.10,
         "omega_odom": 0.3, "omega_true": 0.28, "cte": 0.06},
        {"x": 1.1, "y": 0.5, "theta": 0.2, "v_odom": 0.22, "v_true": 0.09,
         "omega_odom": 0.3, "omega_true": 0.27, "cte": 0.07},
    ],
}

for i in range(2):
    ev = dict(EVENT, event_id=f"fast-test-{i + 1}")
    t0 = time.perf_counter()
    r = handler(ev)
    dt = time.perf_counter() - t0
    print(f"call {i + 1}: {dt:.1f}s model={r.get('model')} "
          f"kp={r['patch']['heading_pid'].get('kp')} "
          f"slip={r['patch'].get('slip_compensation')} "
          f"err={r.get('cloud_error', '-')}", flush=True)

print("HANDLER_FAST_DONE", flush=True)
