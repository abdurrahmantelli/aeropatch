#!/bin/bash
# NIM 500 hatasi tani - body + models listesi
cd /mnt/d/.gemini/antigravity-ide/scratch/nebius
python3 -B wsl/nim_diag.py > wsl/logs/nim_diag.log 2>&1
echo NIM_DIAG_SH_DONE >> wsl/logs/nim_diag.log