#!/bin/bash
# Gazebo demo canlilik kontrolu
source /opt/ros/humble/setup.bash
source ~/aeropatch_ws/install/setup.bash
export AEROPATCH_EDGE_PATH=/mnt/d/.gemini/antigravity-ide/scratch/nebius
echo "=== surecler ==="
pgrep -x gzserver >/dev/null && echo "gzserver: CALISIYOR" || echo "gzserver: YOK"
pgrep -x gzclient >/dev/null && echo "gzclient (GUI): CALISIYOR" || echo "gzclient (GUI): YOK"
pgrep -x rviz2 >/dev/null && echo "rviz2: CALISIYOR" || echo "rviz2: YOK"
for n in gz_truth_node gz_disturbance_node gz_viz_node controller_node monitor_node bridge_node; do
  pgrep -f $n >/dev/null && echo "$n: CALISIYOR" || echo "$n: YOK"
done
echo "=== topic frekanslari (3 sn orneklem) ==="
timeout 3 ros2 topic hz /ground_truth 2>/dev/null | head -2 || echo "/ground_truth: YOK"
timeout 3 ros2 topic hz /odom 2>/dev/null | head -2 || echo "/odom: YOK"
echo "=== gazebo servisleri ==="
ros2 service list 2>/dev/null | grep -E "entity_state|inject" || echo "servis yok"
