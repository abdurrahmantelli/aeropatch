#!/bin/bash
# Tum ROS sureclerini oldurur ve dogrular
pkill -f "ros2 launch" 2>/dev/null
pkill -f sim_node 2>/dev/null
pkill -f controller_node 2>/dev/null
pkill -f monitor_node 2>/dev/null
pkill -f bridge_node 2>/dev/null
pkill -f disturbance_node 2>/dev/null
pkill -f aeropatch_recorder 2>/dev/null
pkill -f ros_session.sh 2>/dev/null
sleep 2
echo "=== kalan surecler ==="
ps aux | grep -E "ros2|_node" | grep -v grep || echo "(temiz - ros sureci yok)"
