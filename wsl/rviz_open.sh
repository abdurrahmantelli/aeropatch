#!/bin/bash
# Kayitli aero_demo.rviz config'i ile RViz2'yi TAM BAGIMSIZ (setsid) baslatir.
# Neden: demo scripti OZET sonrasi RViz'i acik birakmiyor; kullanici kayitli
# gorunumu (yesil path / mavi odom / kirmizi truth / SLIP marker) istiyor.
#   wsl -d Ubuntu-22.04 -- python3 /mnt/d/.../wsl/bg_wrapper.py rviz_open.sh
BASE=/mnt/d/.gemini/antigravity-ide/scratch/nebius
pkill -9 -f rviz2 2>/dev/null
sleep 1
export DISPLAY=${DISPLAY:-:0}
export XDG_RUNTIME_DIR=${XDG_RUNTIME_DIR:-/run/user/$(id -u)}
source /opt/ros/humble/setup.bash
source /home/apo/aeropatch_ws/install/setup.bash
CFG=/home/apo/aeropatch_ws/install/aeropatch/share/aeropatch/rviz/aero_demo.rviz
[ -f "$CFG" ] || CFG=$BASE/ros_ws/src/aeropatch/rviz/aero_demo.rviz
setsid nohup rviz2 -d "$CFG" > /tmp/rviz_open.log 2>&1 < /dev/null &
sleep 5
if pgrep -c rviz2 > /dev/null; then
  echo "RVIZ_OPEN_OK config=$CFG"
else
  echo "RVIZ_OPEN_FAIL"; tail -6 /tmp/rviz_open.log
fi