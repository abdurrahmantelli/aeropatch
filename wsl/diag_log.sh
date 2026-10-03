#!/bin/bash
# gz_launch.log teshisi: monitor/controller olum mu, ready var mi?
LOG=/mnt/d/.gemini/antigravity-ide/scratch/nebius/wsl/logs/gz_launch.log
echo "=== 1) ready satirlari ==="
grep -i "ready" $LOG | head -12
echo "=== 2) process has died ==="
grep -i "process has died" $LOG | head -6
echo "=== 2b) entity does not exist SAYISI ==="
grep -c "does not exist" $LOG
echo "=== 2c) gz_truth basarisiz SAYISI ==="
grep -c "basarisiz" $LOG
echo "=== 2d) safe-mode/YAMA satirlari ==="
grep -iE "safe-mode|YAMA|MODE=" $LOG | head -8
echo "=== 3) python hatalari ==="
grep -iE "Traceback|ImportError|AttributeError|ModuleNotFoundError|Error" $LOG | head -8
echo "=== 4) monitor/controller satirlari ==="
grep -iE "monitor_node-|controller_node-" $LOG | head -10
echo "=== 5) gz_truth satirlari ==="
grep -iE "gz_truth" $LOG | head -8
echo "=== 6) log ilk 20 satir ==="
head -20 $LOG
echo "DIAG_DONE"