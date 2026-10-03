import io, sys
sys.path.insert(0, "/mnt/d/.gemini/antigravity-ide/scratch/nebius/cloud")

base = None
key = None
for line in io.open("/mnt/d/.gemini/antigravity-ide/scratch/nebius/cloud/secrets.env", encoding="utf-8"):
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    k, v = line.split("=", 1)
    v = v.strip().strip('"').strip("'")
    if "KEY" in k.upper() and "TAVILY" not in k.upper():
        key = v
        print("KEY_NAME:", k, "len:", len(v))
    if "BASE" in k.upper() or "URL" in k.upper():
        base = v
        print("BASE:", base)

import requests
if base is None:
    base = "https://integrate.api.nvidia.com/v1"
print("KULLANILAN BASE:", base)

try:
    r = requests.get(base + "/models", headers={"Authorization": "Bearer " + key}, timeout=12)
    print("MODELS_LIST status:", r.status_code)
    if r.status_code == 200:
        ids = [m.get("id", "") for m in r.json().get("data", [])]
        print("NEMOTRON:", [i for i in ids if "nemotron" in i.lower()][:12])
        print("LLAMA:", [i for i in ids if "llama" in i.lower()][:8])
    else:
        print("body:", r.text[:300])
except Exception as e:
    print("MODELS_LIST HATA:", type(e).__name__, str(e)[:200])

model = "nvidia/nemotron-3-super-120b-a12b"
try:
    r = requests.post(base + "/chat/completions",
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
        json={"model": model, "messages": [{"role": "user", "content": "Reply only JSON: {\"ok\": true}"}],
              "max_tokens": 32, "temperature": 0.2}, timeout=25)
    print("CHAT status:", r.status_code)
    print("CHAT body:", r.text[:400])
except Exception as e:
    print("CHAT HATA:", type(e).__name__, str(e)[:200])
print("NIM_DIAG_DONE")