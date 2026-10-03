#!/bin/bash
# Gazebo demo sureclerini tamamen durdur
pkill -f "ros2 launch" 2>/dev/null
pkill -x gzclient 2>/dev/null
pkill -x gzserver 2>/dev/null
pkill -x rviz2 2>/dev/null
pkill -x gz_truth_node 2>/dev/null; pkill -f gz_disturbance_node 2>/dev/null
pkill -x controller_node 2>/dev/null; pkill -x monitor_node 2>/dev/null
pkill -x bridge_node 2>/dev/null
sleep 1
pgrep -x gzserver >/dev/null && echo "HALEN_CALISIYOR" || echo "DURDURULDU"
