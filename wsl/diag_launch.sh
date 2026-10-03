#!/bin/bash
# gz_launch.log tesjisi: hangi dugumler hazir, hangisi oldugunu gosterir
LOG=/mnt/d/.gemini/antigravity-ide/scratch/nebius/wsl/logs/gz_launch.log
echo "=== ready satirlari ==="
grep -E "ready" "$LOG" | tail -12
echo "=== olum/hata satirlari ==="
grep -iE "died|error|traceback|exception" "$LOG" | tail -8
echo "=== monitor satirlari ==="
grep -E "monitor_node" "$LOG" | tail -8
echo "=== controller satirlari ==="
grep -E "controller_node" "$LOG" | tail -8
echo "=== gz_truth satirlari ==="
grep -E "gz_truth" "$LOG" | tail -8
echo "=== DIAG_DONE ==="