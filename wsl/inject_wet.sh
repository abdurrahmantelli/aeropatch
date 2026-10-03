#!/bin/bash
# Bozulma enjekte et (islak zemin, sol teker) + kisa bekleme
source /opt/ros/humble/setup.bash
source ~/aeropatch_ws/install/setup.bash
export AEROPATCH_EDGE_PATH=/mnt/d/.gemini/antigravity-ide/scratch/nebius
sleep "${1:-7}"
echo "=== INJECT: wet ground (left traction 0.45) ==="
ros2 service call /inject_disturbance aeropatch_msgs/srv/InjectDisturbance \
  "{traction_left: 0.45, traction_right: 1.0, ramp_time: 2.0}"
