#!/bin/bash
# Gazebo demo canlilik kontrolu
source /opt/ros/humble/setup.bash
source ~/aeropatch_ws/install/setup.bash
export AEROPATCH_EDGE_PATH=/mnt/d/.gemini/antigravity-ide/scratch/nebius
echo "=== processes ==="
pgrep -x gzserver >/dev/null && echo "gzserver: RUNNING" || echo "gzserver: NOT RUNNING"
pgrep -x gzclient >/dev/null && echo "gzclient (GUI): RUNNING" || echo "gzclient (GUI): NOT RUNNING"
pgrep -x rviz2 >/dev/null && echo "rviz2: RUNNING" || echo "rviz2: NOT RUNNING"
for n in gz_truth_node gz_disturbance_node gz_viz_node controller_node monitor_node bridge_node; do
  pgrep -f $n >/dev/null && echo "$n: RUNNING" || echo "$n: NOT RUNNING"
done
echo "=== topic frequencies (3s sample) ==="
timeout 3 ros2 topic hz /ground_truth 2>/dev/null | head -2 || echo "/ground_truth: NOT FOUND"
timeout 3 ros2 topic hz /odom 2>/dev/null | head -2 || echo "/odom: NOT FOUND"
echo "=== gazebo services ==="
ros2 service list 2>/dev/null | grep -E "entity_state|inject" || echo "no services found"
