from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    default_params = PathJoinSubstitution(
        [FindPackageShare("aeropatch"), "config", "params.yaml"])
    params_arg = DeclareLaunchArgument(
        "params_file", default_value=default_params,
        description="Aeropatch parameter file")
    params = LaunchConfiguration("params_file")
    return LaunchDescription([
        params_arg,
        Node(package="aeropatch", executable="sim_node", name="sim_node",
             parameters=[params], output="screen"),
        Node(package="aeropatch", executable="controller_node",
             name="controller_node", parameters=[params], output="screen"),
        Node(package="aeropatch", executable="monitor_node",
             name="monitor_node", parameters=[params], output="screen"),
        Node(package="aeropatch", executable="bridge_node",
             name="bridge_node", parameters=[params], output="screen"),
        Node(package="aeropatch", executable="disturbance_node",
             name="disturbance_node", parameters=[params], output="screen"),
    ])
