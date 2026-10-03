#!/bin/bash
# TurtleBot3 burger model odometri kaynagi kontrolu
M=/opt/ros/humble/share/turtlebot3_gazebo/models/turtlebot3_burger/model.sdf
grep -n -iE "odometrySource|odometry_source|diff_drive|updateRate|odometry_frame|publishOdomTF" $M
echo "---"
grep -n -A16 "libgazebo_ros_diff_drive" $M | head -30
echo "MODEL_CHECK_DONE"