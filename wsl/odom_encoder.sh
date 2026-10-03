#!/bin/bash
# burger model.sdf: diff_drive odometry kaynagi WORLD -> ENCODER.
# Neden: WORLD kaynagi teleport'u odom'a da gosteriyor -> monitor tek-tik'te
# gorup persistence filtresine takiliyor -> ALARM=0 (canli kanit: 12cm
# teleport sonrasi SLIP_GAP=0.004, ALARM=0). ENCODER ile odom kor (gercek
# robot anlatisi: "encoder kaymayi goremez") -> kalici DR kaymasi birikir ->
# monitor alarm uretir -> bulut yamasi -> controller (gt tabanli) toparlar.
M=/opt/ros/humble/share/turtlebot3_gazebo/models/turtlebot3_burger/model.sdf
OUT=/mnt/d/.gemini/antigravity-ide/scratch/nebius/wsl/logs/odom_encoder.log
exec > "$OUT" 2>&1
if grep -q odometry_source "$M"; then
  echo "ZATEN_VAR: odometry_source etiketi mevcut"
else
  cp "$M" "$M.aeropatch.bak"
  sed -i "s|<odometry_topic>odom</odometry_topic>|<odometry_source>ENCODER</odometry_source>\n      <odometry_topic>odom</odometry_topic>|" "$M"
  grep -m1 -A2 odometry_source "$M" && echo "EKLENDI"
fi
echo "ODOM_ENCODER_DONE"