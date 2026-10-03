#!/bin/bash
source /opt/ros/humble/setup.bash
ros2 run gazebo_ros spawn_entity.py --help 2>&1 | grep -i timeout
echo HELP_DONE
