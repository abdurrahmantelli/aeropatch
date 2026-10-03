#!/bin/bash
# Gazebo'da 'yagmur kaymasi' enjekte et:
#   bash gz_inject.sh [traction_left] [traction_right] [ramp_s]
# traction=1.0 kuru zemin, 0.0 buz gibi kaygan.
source /opt/ros/humble/setup.bash
source ~/aeropatch_ws/install/setup.bash
export AEROPATCH_EDGE_PATH=/mnt/d/.gemini/antigravity-ide/scratch/nebius
TL=${1:-0.3}; TR=${2:-0.3}; RAMP=${3:-2.0}
echo "=== Gazebo fiziksel kayma enjeksiyonu (L=$TL R=$TR ramp=$RAMP) ==="
timeout 8 ros2 service call /inject_disturbance aeropatch_msgs/srv/InjectDisturbance \
  "{traction_left: $TL, traction_right: $TR, ramp_time: $RAMP}"
echo "=== 18 sn bekle: kayma -> alarm -> bulut yamasi -> toparlanma ==="
sleep 18
echo "=== son anomaly skoru (yama sonrasi dusmesi beklenir) ==="
timeout 5 ros2 topic echo /anomaly_score --once 2>/dev/null | head -3
