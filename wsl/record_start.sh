#!/bin/bash
# Kayitciyi arka planda baslatir
source /opt/ros/humble/setup.bash
source ~/aeropatch_ws/install/setup.bash
export AEROPATCH_EDGE_PATH=/mnt/d/.gemini/antigravity-ide/scratch/nebius
S=${1:-40}
nohup python3 /mnt/d/.gemini/antigravity-ide/scratch/nebius/wsl/ros_recorder.py "$S" \
  /mnt/d/.gemini/antigravity-ide/scratch/nebius/wsl/logs/ros_record.jsonl \
  > /mnt/d/.gemini/antigravity-ide/scratch/nebius/wsl/logs/recorder.log 2>&1 &
echo "RECORDER_PID=$!"
sleep 2
cat /mnt/d/.gemini/antigravity-ide/scratch/nebius/wsl/logs/recorder.log
