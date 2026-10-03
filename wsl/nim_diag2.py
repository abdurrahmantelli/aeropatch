import io, sys, json
sys.path.insert(0, "/mnt/d/.gemini/antigravity-ide/scratch/nebius/cloud")
import requests
from nebius_handler import PROMPT, NEBIUS_BASE_URL, NEBIUS_API_KEY

weather = {"summary": "Kadikoy, Istanbul TR: 14C, yagis 2.1mm/son saat, ruzgar 22km/km KD, zemin islak"}
lines = ["t=0.5 v_odom=0.220 v_true=0.215 omega_odom=0.10 omega_true=0.10 cte=0.02",
         "t=1.0 v_odom=0.221 v_true=0.150 omega_odom=0.11 omega_true=0.05 cte=0.09",
         "t=1.5 v_odom=0.219 v_true=0.120 omega_odom=0.12 omega_true=0.03 cte=0.21"]
gains = {"kp": 1.2, "ki": 0.05, "kd": 0.08, "v_max": 0.22}

prompt = PROMPT.format(weather=weather["summary"], n=len(lines),
                       telemetry="\n".join(lines), gains=json.dumps(gains))
print("PROMPT uzunluk:", len(prompt), "kr; karakter seti ornekleri:",
      [c for c in set(prompt) if ord(c) > 127][:10])

for m, mx in [("nvidia/nemotron-3-super-120b-a12b", 1024),
              ("nvidia/nemotron-3-super-120b-a12b", 32),
              ("meta/llama-3.2-11b-vision-instruct", 256)]:
    try:
        r = requests.post(NEBIUS_BASE_URL + "/chat/completions",
            headers={"Authorization": "Bearer " + NEBIUS_API_KEY,
                     "Content-Type": "application/json"},
            json={"model": m, "temperature": 0.2, "max_tokens": mx,
                  "messages": [{"role": "user", "content": prompt}]},
            timeout=(5, 25))
        msg = ""
        if r.status_code == 200:
            msg = (r.json().get("choices", [{}])[0].get("message") or {}).get("content") or ""
        print(f"[{m} mx={mx}] status={r.status_code} content_len={len(msg)}",
              ("" if r.status_code == 200 else "body=" + r.text[:200]))
    except Exception as e:
        print(f"[{m} mx={mx}] HATA:", type(e).__name__, str(e)[:150])
print("NIM_DIAG2_DONE")