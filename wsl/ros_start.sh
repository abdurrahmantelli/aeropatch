#!/bin/bash
# AeroPatch ROS2 sistemini arka planda baslatir
source /opt/ros/humble/setup.bash
source ~/aeropatch_ws/install/setup.bash
export AEROPATCH_EDGE_PATH=/mnt/d/.gemini/antigravity-ide/scratch/nebius
pkill -f "ros2 launch" 2>/dev/null
pkill -x sim_node 2>/dev/null; pkill -x controller_node 2>/dev/null
pkill -x monitor_node 2>/dev/null; pkill -x bridge_node 2>/dev/null
pkill -x disturbance_node 2>/dev/null
sleep 1
cd ~/aeropatch_ws
setsid nohup ros2 launch aeropatch sim_launch.py > /mnt/d/.gemini/antigravity-ide/scratch/nebius/wsl/logs/ros_launch.log 2>&1 < /dev/null &
echo "LAUNCHED_PID=$!"
sleep 2
pgrep -f "ros2 launch" > /dev/null && echo "LAUNCH_ALIVE" || echo "LAUNCH_DEAD"
