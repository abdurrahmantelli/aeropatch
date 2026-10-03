"""sim_node: Faz-1 fizik motorunu ROS2'ye bağlar (Gazebo öncesi dijital ikiz).

Yayınlar : /odom (nav_msgs/Odometry, encoder tabanlı DR)
           /ground_truth (geometry_msgs/PoseStamped, harici lokalizasyon)
           /slip_state (std_msgs/Float32MultiArray, [traction_l, traction_r])
Dinler   : /cmd_vel (geometry_msgs/Twist)
           /inject_disturbance (std_msgs/Float32MultiArray)
           [traction_left, traction_right, ramp_time]
"""
from __future__ import annotations

import math

import rclpy
from geometry_msgs.msg import PoseStamped, Twist
from nav_msgs.msg import Odometry
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from std_msgs.msg import Float32MultiArray

from aeropatch.edge_loader import ensure_edge_modules

ensure_edge_modules()

from edge.robot_physics import DiffDriveRobot  # noqa: E402


class SimNode(Node):
    def __init__(self):
        super().__init__("sim_node")
        self.declare_parameters("", [
            ("dt", 0.02), ("track_width", 0.16), ("wheel_radius", 0.033),
            ("motor_tau", 0.12), ("v_limit", 0.22), ("omega_limit", 2.84),
        ])
        dt = float(self.get_parameter("dt").value)
        self.robot = DiffDriveRobot(
            track_width=float(self.get_parameter("track_width").value),
            wheel_radius=float(self.get_parameter("wheel_radius").value),
            motor_tau=float(self.get_parameter("motor_tau").value),
            v_limit=float(self.get_parameter("v_limit").value),
            omega_limit=float(self.get_parameter("omega_limit").value))
        self.dt = dt
        self.odom_pub = self.create_publisher(Odometry, "/odom", 10)
        self.gt_pub = self.create_publisher(PoseStamped, "/ground_truth", 10)
        self.slip_pub = self.create_publisher(Float32MultiArray, "/slip_state",
                                              qos_profile_sensor_data)
        self.create_subscription(Twist, "/cmd_vel", self._on_cmd, 10)
        self.create_subscription(Float32MultiArray, "/inject_disturbance",
                                  self._on_disturbance, 10)
        self.timer = self.create_timer(dt, self._tick)
        self.get_logger().info("sim_node ready (50 Hz physics, "
                               "wheel-slip disturbance model)")

    def _on_cmd(self, msg: Twist):
        self.robot.set_cmd(msg.linear.x, msg.angular.z)

    def _on_disturbance(self, msg: Float32MultiArray):
        if len(msg.data) >= 2:
            ramp = float(msg.data[2]) if len(msg.data) > 2 else 2.0
            self.robot.set_traction(float(msg.data[0]), float(msg.data[1]), ramp)
            self.get_logger().warn(
                f"DISTURBANCE injected: traction L={msg.data[0]:.2f} "
                f"R={msg.data[1]:.2f} (ramp {ramp:.1f}s)")

    def _tick(self):
        st = self.robot.step(self.dt)
        now = self.get_clock().now().to_msg()
        odom = Odometry()
        odom.header.stamp = now
        odom.header.frame_id = "odom"
        odom.child_frame_id = "base_footprint"
        odom.pose.pose.position.x = st.x_odom
        odom.pose.pose.position.y = st.y_odom
        # Gazebo sozlesmesi: duzgun kuaterniyon yay (tuketiciler yaw'a cevirir)
        odom.pose.pose.orientation.z = math.sin(st.theta_odom / 2.0)
        odom.pose.pose.orientation.w = math.cos(st.theta_odom / 2.0)
        odom.twist.twist.linear.x = st.v_odom
        odom.twist.twist.angular.z = st.omega_odom
        self.odom_pub.publish(odom)
        gt = PoseStamped()
        gt.header.stamp = now
        gt.header.frame_id = "map"
        gt.pose.position.x = st.x
        gt.pose.position.y = st.y
        gt.pose.orientation.z = math.sin(st.theta / 2.0)
        gt.pose.orientation.w = math.cos(st.theta / 2.0)
        self.gt_pub.publish(gt)
        slip = Float32MultiArray()
        slip.data = [st.traction_left, st.traction_right, st.v_true,
                     st.omega_true]
        self.slip_pub.publish(slip)


def main(args=None):
    rclpy.init(args=args)
    node = SimNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
