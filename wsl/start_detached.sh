#!/bin/bash
# gz_demo_real.sh'i TAM BAGIMSIZ (setsid) baslatir. Neden: "wsl -- bash -c
# 'setsid ... &'" komutu cmd.exe tirnak bozukluguyla calismiyordu (canli kanit:
# demo hic baslamadi). Bu betik quotesiz cagrilir, 1 sn'de doner; demo kendi
# oturumunda yasar — Windows istemcisi/konsol olse bile Gazebo+RViz KALIR.
#   wsl -d Ubuntu-22.04 -- bash /mnt/d/.../wsl/start_detached.sh
BASE=/mnt/d/.gemini/antigravity-ide/scratch/nebius
pkill -f "wsl/gz_demo_real.sh" 2>/dev/null
sleep 1
setsid nohup bash "$BASE/wsl/gz_demo_real.sh" >/dev/null 2>&1 < /dev/null &
sleep 2
pgrep -f "wsl/gz_demo_real.sh" > /dev/null && echo "DETACHED_OK (demo basladi)" || echo "DETACHED_FAIL"