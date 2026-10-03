#!/bin/bash
# Tanilama: surec durumu + tum kritik log satirlari
P=/mnt/d/.gemini/antigravity-ide/scratch/nebius/wsl/logs
echo "=== SURECLER ==="
echo "gzserver: $(pgrep -c gzserver)"
echo "gzclient: $(pgrep -c gzclient)"
echo "rviz2: $(pgrep -c rviz2)"
echo "cloud: $(pgrep -c -f local_cloud_server)"
echo "ros2: $(pgrep -c -f 'ros2 launch')"
echo ""
echo "=== DEMO OZET ==="
tail -8 $P/gz_demo_real_out.log 2>/dev/null
echo ""
echo "=== ZINCIR (gz_launch) ==="
grep -m 40 -iE "ALARM|PATCH|NIM|TRUTH_OK|SLIP_GAP|resync|odom_corrected" $P/gz_launch.log 2>/dev/null | tail -40
echo ""
echo "=== CLOUD LOG (son 20) ==="
tail -20 $P/cloud_server.log 2>/dev/null
