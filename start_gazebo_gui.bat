@echo off
echo =======================================================
echo AeroPatch Gazebo 3D + RViz2 GUI Launcher
echo =======================================================
echo WSLg ekran surucusu ve GUI pencereleri baslatiliyor...
echo.
wsl.exe -d Ubuntu-22.04 -- bash -c "source /opt/ros/humble/setup.bash && source ~/aeropatch_ws/install/setup.bash && export AEROPATCH_EDGE_PATH=/mnt/d/.gemini/antigravity-ide/scratch/nebius && export LIBGL_ALWAYS_SOFTWARE=1 && export DISPLAY=:0 && export WAYLAND_DISPLAY=wayland-0 && ros2 launch aeropatch gazebo_launch.py"
pause
