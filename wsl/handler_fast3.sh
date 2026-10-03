#!/bin/bash
# NIM canli test - internet dondu, gercek model yaniti bekleniyor
# python'u python3 ile calistirir (bg_wrapper .sh icin)
cd /mnt/d/.gemini/antigravity-ide/scratch/nebius
python3 -B wsl/test_handler_fast.py > wsl/logs/handler_fast3.log 2>&1
echo HANDLER_FAST3_DONE >> wsl/logs/handler_fast3.log