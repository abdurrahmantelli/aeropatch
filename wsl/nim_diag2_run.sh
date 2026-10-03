#!/bin/bash
# Handler birebir istek sekli testi (PROMPT + max_tokens=1024)
cd /mnt/d/.gemini/antigravity-ide/scratch/nebius
python3 -B wsl/nim_diag2.py > wsl/logs/nim_diag2.log 2>&1
echo NIM_DIAG2_SH_DONE >> wsl/logs/nim_diag2.log