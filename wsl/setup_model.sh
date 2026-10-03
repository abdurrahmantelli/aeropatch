#!/bin/bash
# TurtleBot3 burger modelini ENCODER odometri kaynagiyla kopyalar.
# KOK NEDEN: stok model.sdf'te <odometry_source> yok -> varsayilan WORLD
# (dunya pozu) -> /odom = gercek poz -> teleport odom'a da yansir ->
# gap hep 0 -> SLIP 0.00 -> ALARM imkansiz. ENCODER: odom tekerlek
# enkoderinden gelir -> kayma/teleport odom'a gorunmez -> gap buyur.
DEST=~/aeropatch_ws/models/turtlebot3_burger_enc
SRC=/opt/ros/humble/share/turtlebot3_gazebo/models/turtlebot3_burger
rm -rf $DEST
cp -r $SRC $DEST
# <odometry_source>encoder</odometry_source> ekle (plugin icine, output blokinden once)
sed -i "s|<publish_odom>true</publish_odom>|<odometry_source>encoder</odometry_source>\n      <publish_odom>true</publish_odom>|" $DEST/model.sdf
echo "=== kontrol ==="
grep -n -E "odometry_source" $DEST/model.sdf
ls $DEST
echo "MODEL_ENC_DONE"