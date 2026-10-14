#!/bin/bash
# FAZ 3: Gazebo + RViz + NVIDIA NIM bulutu demosi (tam otomatik).
# 1) Bulut sunucusu WSL icinde (port 8091) -> /health kontrolu
# 2) gazebo_launch + params_nvidia.yaml (mock_cloud: false)
# 3) Gazebo ve RViz pencereleri Windows masaustunde acilir (WSLg)
# 4) Otomatik enjeksiyon -> alarm -> NIM tepkisi -> yama -> toparlanma
BASE=/mnt/d/.gemini/antigravity-ide/scratch/nebius
LOG=$BASE/wsl/logs/gz_launch.log
OUT=$BASE/wsl/logs/gz_demo_real_out.log
exec > "$OUT" 2>&1
# WSL VM'i uyanik tut (4 saat): vmIdleTimeout ~60 sn — komut bitince VM
# kapanir ve Gazebo/RViz/dugumler OLUR ("kendiliginden kapandi" kok nedeni).
# setsid+nohup ile bu betikten tam ayrilir, betik bittikten sonra da yasar.
setsid nohup bash $BASE/wsl/keepalive.sh >/dev/null 2>&1 </dev/null &
echo "KEEPALIVE_PID=$!"
echo "=== 1) CLOUD (NVIDIA NIM, port 8091) ==="
bash $BASE/wsl/cloud_start.sh
# Import yavasligina karsi: health'i 8x2 sn'ye kadar yokla (tek curl
# CLOUD_HEALTH_FAIL verebiliyordu)
for i in $(seq 1 8); do
  curl -s -m 3 http://127.0.0.1:8091/health 2>/dev/null | grep -q ok \
    && { echo "CLOUD_READY (attempt $i)"; break; }
  sleep 2
done
echo "=== 2) GAZEBO LAUNCH (params_nvidia.yaml) ==="
source /opt/ros/humble/setup.bash
source ~/aeropatch_ws/install/setup.bash
export AEROPATCH_EDGE_PATH=$BASE
export TURTLEBOT3_MODEL=burger
# ESKI OTURUM KALINTILARI: gzserver/gzclient/rviz2 + TUM ROS dugumleri.
# (pgrep kaniti: iki gz_truth_node ayani yasiyordu -> cift /ground_truth ->
#  bozuk monitor -> alarm uretilmez. install/aeropatch deseni tum dugum
#  sureclerini oldurur ama bu betigi oldurmaz — /tmp/aeropatch_* eslesmez.)
pkill -9 -f gzserver 2>/dev/null; pkill -9 -f gzclient 2>/dev/null
pkill -9 -f rviz2 2>/dev/null
pkill -9 -f "install/aeropatch" 2>/dev/null
pkill -f "ros2 launch" 2>/dev/null; sleep 1
# SHM kilit kalintilari temizle (servis kesfini bozan kok neden)
rm -f /dev/shm/fastrtps_* /dev/shm/fast_datasharing* 2>/dev/null
export FASTRTPS_DEFAULT_PROFILES_FILE=$BASE/ros_ws/src/aeropatch/config/fastdds_udp.xml
cd ~/aeropatch_ws
# KRITIK DUZELTME ("kendiliginden kapandi" kok nedeni #2): launch'i setsid ile
# oturumdan kopar — betik bittiginde wsl.exe oturumu kapanir; setsid'siz
# launch SIGHUP ile OLURDU (gzserver/gzclient/rviz2 hep onun cocugu).
setsid nohup ros2 launch aeropatch gazebo_launch.py params_file:=$BASE/ros_ws/src/aeropatch/config/params_nvidia.yaml > "$LOG" 2>&1 < /dev/null &
disown 2>/dev/null
LAUNCH_PID=$!
echo "=== 3) waiting for robot spawn (max 90s) ==="
SPAWN_OK=0
for i in $(seq 1 30); do
  sleep 3
  R=$(ros2 service call /gazebo/get_entity_state gazebo_msgs/srv/GetEntityState "{name: aerobot, reference_frame: world}" 2>/dev/null | grep -c "success=True" || true)
  if [ "$R" = "1" ]; then SPAWN_OK=1; echo "SPAWN_OK (t=$((i * 3))s)"; break; fi
done
if [ "$SPAWN_OK" = "0" ]; then
  echo "SPAWN_FAIL: launch spawn did not complete -> manual spawn (-timeout 120)"
  ros2 run gazebo_ros spawn_entity.py -entity aerobot \
    -file /opt/ros/humble/share/turtlebot3_gazebo/models/turtlebot3_burger/model.sdf \
    -timeout 120 -x 0.0 -y 0.0 -z 0.05
fi
pgrep -f "ros2 launch" > /dev/null && echo "LAUNCH_ALIVE" || { echo "LAUNCH_DEAD"; tail -15 "$LOG"; exit 1; }
echo "=== 4) INJECT (wet ground, left wheel) ==="
# Robot 6 sn hareket etsin: kayma hareket halinde uygulanirsa monitor
# komut-olcum uyumsuzlugunu net gorur (spawn aninda enjekte edilirdi).
sleep 6
echo "--- injection result: ---"
ros2 service call /inject_disturbance aeropatch_msgs/srv/InjectDisturbance \
  "{traction_left: 0.25, traction_right: 1.0, ramp_time: 2.0}" || echo "INJECT_FAIL: service not found (SHM/discovery?)"
echo "=== 5) monitoring 26s (alarm -> NIM(real) -> patch -> recovery) ==="
# 48 -> 26 (kullanici karari: "islaklik enjeksiyonu bittikten sonra slip
# artmamali"): islak pencere t~24 -> t~43'e kisalir; yama sonrasi kuru
# donus gelir, gap artmaz (resync + Kp restore temiz gorunur). NIM soguk
# baslangicta gec donerse zemin kuru olmus olur -> default-dry + slip=0
# -> yine temiz hikaye (gap artmaz).
sleep 26
echo "=== 6) back to dry ground ==="
ros2 service call /inject_disturbance aeropatch_msgs/srv/InjectDisturbance \
  "{traction_left: 1.0, traction_right: 1.0, ramp_time: 1.0}" || true
sleep 2
echo "=== 7) chain verification (did the patch return?) ==="
sleep 45
echo "[GZ_REAL] DRY MONITORING WINDOW COMPLETED (45s - extended for RECOVER restore)"
AL=$(grep -c "ALARM score" "$LOG" 2>/dev/null || true)
PA=$(grep -c "PATCH applied" "$LOG" 2>/dev/null || true)
RA=$(grep -ci "rain slide" "$OUT" 2>/dev/null || true)
TR=$(grep -c "TRUTH_OK" "$LOG" 2>/dev/null || true)
NM=$(grep -c "NIM.*-> OK" "$BASE/wsl/logs/cloud_server.log" 2>/dev/null || true)
echo "SUMMARY: TRUTH=$TR ALARM=$AL PATCH=$PA RAIN=$RA NIM=$NM"
echo "--- cloud diagnosis (last HANDLER lines) ---"
grep "HANDLER" "$BASE/wsl/logs/cloud_server.log" 2>/dev/null | tail -3
grep -iE "ALARM|PATCH applied|cloud error|cloud agent|hold-off|safe-mode|TRUTH_OK|SLIP_GAP|odom resync" "$LOG" 2>/dev/null | tail -20
if [ "$TR" = "0" ]; then
  echo "CHAIN_FAIL: gz_truth did not publish /ground_truth (TRUTH=0)"
elif [ "$PA" -ge 1 ]; then
  echo "CHAIN_OK: patch returned -> controller recovers (watch RViz)"
else
  echo "CHAIN_FAIL: no patch returned -> check cloud_server.log"
  tail -8 "$BASE/wsl/logs/cloud_server.log" 2>/dev/null || true
fi
echo "GZ_REAL_DONE — WINDOWS STAY OPEN (setsid). To stop: bash wsl/gz_stop.sh"