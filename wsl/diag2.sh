#!/bin/bash
# Hizli teshis: enjeksiyon kaniti + burger odometri kaynagi.
OUT=/mnt/d/.gemini/antigravity-ide/scratch/nebius/wsl/logs/diag2.log
exec > "$OUT" 2>&1
echo "=== 1) RAIN SLIDE kaniti (gz_demo_real_out.log) ==="
grep -i "rain" /mnt/d/.gemini/antigravity-ide/scratch/nebius/wsl/logs/gz_demo_real_out.log 2>/dev/null | head -4
echo "=== 2) burger model: odometry kaynagi ==="
grep -i -B1 -A1 "odometry" /opt/ros/humble/share/turtlebot3_gazebo/models/turtlebot3_burger/model.sdf 2>/dev/null | head -8
echo "=== 3) gz_launch.log: son ALARM/PATCH ==="
grep -iE "alarm|patch applied" /mnt/d/.gemini/antigravity-ide/scratch/nebius/wsl/logs/gz_launch.log 2>/dev/null | tail -4
echo "DIAG2_DONE"