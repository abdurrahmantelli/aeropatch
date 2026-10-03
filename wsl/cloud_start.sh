#!/bin/bash
# NVIDIA NIM bulut sunucusunu WSL ICINDE baslatir (port 8091).
# Neden WSL? NAT modunda WSL icindeki 127.0.0.1 Windows'a ulasmaz;
# sunucu WSL'de oldugu surece bridge_node'un endpoint'i dogrudan calisir.
# secrets.env sunucu tarafindan otomatik yuklenir (NIM anahtari dahil).
export CLOUD_PORT=8091
LOG=/mnt/d/.gemini/antigravity-ide/scratch/nebius/wsl/logs/cloud_server.log
pkill -f local_cloud_server.py 2>/dev/null
sleep 1
setsid nohup python3 /mnt/d/.gemini/antigravity-ide/scratch/nebius/cloud/local_cloud_server.py > "$LOG" 2>&1 < /dev/null &
echo "CLOUD_PID=$!"
# Import yavasligi tuzaği: numpy/requests import'u ilk calistirmada 5-15 sn
# surebilir — 2 sn'lik tek health check yeterli degildi (CLOUD_HEALTH_FAIL
# yanlis alarmi). 10x2 sn'lik retry dongusu kesin sonuc verir.
HEALTH_OK=0
for i in $(seq 1 10); do
  sleep 2
  curl -s -m 3 http://127.0.0.1:8091/health > /dev/null 2>&1 && { HEALTH_OK=1; break; }
done
curl -s -m 3 http://127.0.0.1:8091/health && echo " <- CLOUD_HEALTH_OK" || echo "CLOUD_HEALTH_FAIL (import >20s?)"
echo "--- sunucu logu ---"
tail -3 "$LOG"