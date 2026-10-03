#!/bin/bash
# Canli topic probu: monitor /ground_truth ve /odom aliyor mu?
# ALARM=0 tuzaginin kok nedenini dogrudan gosterir.
source /opt/ros/humble/setup.bash
source ~/aeropatch_ws/install/setup.bash
export FASTRTPS_DEFAULT_PROFILES_FILE=/mnt/d/.gemini/antigravity-ide/scratch/nebius/ros_ws/src/aeropatch/config/fastdds_udp.xml
echo "=== /ground_truth hz (3 sn) ==="
timeout 4 ros2 topic hz /ground_truth --window 20 2>&1 | head -4
echo "=== /odom hz (3 sn) ==="
timeout 4 ros2 topic hz /odom --window 20 2>&1 | head -4
echo "=== /anomaly_score (1 mesaj) ==="
timeout 4 ros2 topic echo /anomaly_score --once 2>&1 | head -2
echo "=== /patch/request (1 mesaj) ==="
timeout 3 ros2 topic echo /patch/request --once 2>&1 | head -2
echo "=== PROBE_DONE ==="