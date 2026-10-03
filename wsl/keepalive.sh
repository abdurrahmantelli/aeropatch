#!/bin/bash
# WSL VM'i uyanik tutar (4 saat). Neden: WSL2 vmIdleTimeout ~60 sn —
# komut bitince VM kapanir, tum Gazebo/RViz/dugum surecleri OLUR
# ("kendiliginden kapandi" tuzağinin kok nedeni). Kullanim:
#   start /b wsl -d Ubuntu-22.04 -- bash /mnt/d/.../wsl/keepalive.sh
# (Windows tarafindan paralel baslatilir; kendisi 4 saat uyur.)
sleep 14400