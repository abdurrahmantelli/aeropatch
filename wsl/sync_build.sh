#!/bin/bash
# sync_build: D: kaynaklarini WSL'e kopyala + colcon build (tek beton)
OUT=/mnt/d/.gemini/antigravity-ide/scratch/nebius/wsl/logs/sync_build.log
exec > "$OUT" 2>&1
echo "=== SYNC ==="
rm -rf ~/aeropatch_ws/src
cp -r /mnt/d/.gemini/antigravity-ide/scratch/nebius/ros_ws/src ~/aeropatch_ws/src
python3 /mnt/d/.gemini/antigravity-ide/scratch/nebius/wsl/fix_crlf.py > /dev/null 2>&1
grep -c "cx=2.2" ~/aeropatch_ws/src/aeropatch/aeropatch/controller_node.py && echo SYNC_OK || echo SYNC_FAIL
echo "=== BUILD ==="
source /opt/ros/humble/setup.bash
cd ~/aeropatch_ws
colcon build --symlink-install > /tmp/colcon_full.log 2>&1
echo "BUILD_RC=$?"
tail -6 /tmp/colcon_full.log
ls install/aeropatch/lib/aeropatch/ 2>/dev/null
echo "BUILD_DONE"