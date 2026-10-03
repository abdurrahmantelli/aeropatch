#!/bin/bash
# CALISAN sunucuyu (port 8091) test eder - gercek deployment yolu
# (import edilen handler degil, HTTP POST). NIM satirlari cloud_server.log'a.
cd /mnt/d/.gemini/antigravity-ide/scratch/nebius
python3 -B wsl/test_server_fast.py > wsl/logs/server_fast.log 2>&1
echo SERVER_FAST_DONE >> wsl/logs/server_fast.log