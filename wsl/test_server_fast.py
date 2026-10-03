import json, time, urllib.request

EVENT = {
    "robot_id": "aerobot", "event_id": "srv-test-1", "trigger": "anomaly",
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
    ev = dict(EVENT, event_id=f"srv-test-{i + 1}")
    data = json.dumps(ev).encode()
    req = urllib.request.Request("http://127.0.0.1:8091/", data=data,
                                 headers={"Content-Type": "application/json"})
    t0 = time.perf_counter()
    r = urllib.request.urlopen(req, timeout=60)
    body = json.loads(r.read().decode())
    dt = time.perf_counter() - t0
    pid = body.get("patch", {}).get("heading_pid", {})
    print(f"call {i + 1}: {dt:.1f}s model={body.get('model')} "
          f"kaynak={body.get('kaynak', '-')} kp={pid.get('kp')} "
          f"slip={body.get('patch', {}).get('slip_compensation')} "
          f"err={body.get('cloud_error', '-')}", flush=True)

print("SERVER_FAST_DONE", flush=True)