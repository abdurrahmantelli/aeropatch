"""Gazebo demo launch: TurtleBot3 Burger + AeroPatch kenar/bulut yigini + RViz.

sim_launch.py'nin Gazebo karsiligi — monitor/controller/bridge DEGISMEZ,
sim_node'un yerine Gazebo + gz_truth_node gecer.

ros2 launch aeropatch gazebo_launch.py
ros2 launch aeropatch gazebo_launch.py gui:=false rviz:=false
"""
from __future__ import annotations

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import (DeclareLaunchArgument, ExecuteProcess,
                            GroupAction, TimerAction)
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    gui = LaunchConfiguration("gui")
    rviz = LaunchConfiguration("rviz")
    params = LaunchConfiguration("params_file")
    aero = get_package_share_directory("aeropatch")
    tb3 = get_package_share_directory("turtlebot3_gazebo")
    tb3_models = os.path.join(tb3, "models")
    model_sdf = os.path.join(tb3_models, "turtlebot3_burger", "model.sdf")
    world_sdf = os.path.join(aero, "worlds", "aero_world.sdf")
    rviz_cfg = os.path.join(aero, "rviz", "aero_demo.rviz")

    gz_env = dict(os.environ)
    gz_env.setdefault("DISPLAY", ":0")
    gz_env.setdefault("WAYLAND_DISPLAY", "wayland-0")
    # sun + ground_plane yereli (gazebo-11) ve turtlebot3 modelleri ONCE:
    # yoksa Gazebo bunlari internette arar -> yavas/acilis patlamasi
    gz_env["GAZEBO_MODEL_PATH"] = (
        tb3_models + ":/usr/share/gazebo-11/models:"
        + gz_env.get("GAZEBO_MODEL_PATH", ""))
    # sim zaman + klasik gazebo env
    gz_env.setdefault("LIBGL_ALWAYS_SOFTWARE", "1")
    # FastDDS SHM kapali: WSL2'de /dev/shm fastrtps port kilidi cakismasi
    # ("open_and_lock_file failed") servis kesfini bozuyor — spawn_entity
    # 30s timeout'unun kok nedeni. Sadece UDPv4 discovery.
    fdds = os.path.join(aero, "config", "fastdds_udp.xml")
    if os.path.exists(fdds):
        gz_env["FASTRTPS_DEFAULT_PROFILES_FILE"] = fdds

    edge_nodes = [
        Node(package="aeropatch", executable="gz_truth_node",
             name="gz_truth_node", output="screen",
             parameters=[params, {"use_sim_time": True}]),
        Node(package="aeropatch", executable="gz_disturbance_node",
             name="gz_disturbance_node", output="screen",
             parameters=[params, {"use_sim_time": True}]),
        Node(package="aeropatch", executable="gz_viz_node",
             name="gz_viz_node", output="screen",
             parameters=[params, {"use_sim_time": True}]),
        Node(package="aeropatch", executable="controller_node",
             name="controller_node", output="screen",
             parameters=[params, {"use_sim_time": True}]),
        Node(package="aeropatch", executable="monitor_node",
             name="monitor_node", output="screen",
             parameters=[params, {"use_sim_time": True}]),
        Node(package="aeropatch", executable="bridge_node",
             name="bridge_node", output="screen",
             parameters=[params, {"use_sim_time": True}]),
        Node(package="tf2_ros", executable="static_transform_publisher",
             name="map_to_odom", output="screen",
             arguments=["--x", "0", "--y", "0", "--z", "0", "--qx", "0",
                        "--qy", "0", "--qz", "0", "--qw", "1",
                        "--frame-id", "map", "--child-frame-id", "odom"]),
    ]

    return LaunchDescription([
        DeclareLaunchArgument("gui", default_value="true"),
        DeclareLaunchArgument("rviz", default_value="true"),
        DeclareLaunchArgument(
            "params_file",
            default_value=PathJoinSubstitution(
                [FindPackageShare("aeropatch"), "config", "params.yaml"])),
        # 1) Gazebo sunucu + istemci (WSLg uzerinden Windows'ta gorunur)
        ExecuteProcess(cmd=["gzserver", "--verbose", "-s",
                            "libgazebo_ros_init.so", "-s",
                            "libgazebo_ros_factory.so", world_sdf],
                       env=gz_env, output="screen"),
        ExecuteProcess(cmd=["gzclient"], env=gz_env, output="screen",
                       condition=IfCondition(gui)),
        # 2) TurtleBot3 Burger'i bizim dunyaya dog (gazebo_ros_factory servisi)
        #    gzserver world yuklemeyi soguk baslista 60-90s surebiliyor ->
        #    spawn 15s'de baslar, -timeout 120 ile bekler (30s default
        #    yetismiyordu: "Service /spawn_entity unavailable" -> robot yok)
        TimerAction(period=15.0, actions=[
            ExecuteProcess(cmd=["ros2", "run", "gazebo_ros", "spawn_entity.py",
                                 "-entity", "aerobot", "-file", model_sdf,
                                 "-timeout", "120",
                                 "-x", "0.0", "-y", "0.0", "-z", "0.05"],
                           env=gz_env, output="screen"),
        ]),
        # 3) AeroPatch kenar yigini (eski dugumler, use_sim_time ile)
        TimerAction(period=5.0, actions=[GroupAction(actions=edge_nodes)]),
        # 4) RViz: yorunge + gercek iz + odometri yalani yan yana
        TimerAction(period=8.0, actions=[
            Node(package="rviz2", executable="rviz2", name="aero_rviz",
                 output="screen", condition=IfCondition(rviz),
                 arguments=["-d", rviz_cfg]),
        ]),
    ])
