"""disturbance_node: tek komutla 'yağmur -> kaygan zemin' enjekte eder.

ros2 service call /inject_disturbance aeropatch_msgs/srv/InjectDisturbance \
  "{traction_left: 0.45, traction_right: 1.0, ramp_time: 2.0}"
"""
from __future__ import annotations

import rclpy
from rclpy.node import Node
from std_msgs.msg import Float32MultiArray

from aeropatch_msgs.srv import InjectDisturbance


class DisturbanceNode(Node):
    def __init__(self):
        super().__init__("disturbance_node")
        self.declare_parameters("", [
            ("traction_left", 0.45), ("traction_right", 1.0), ("ramp_time", 2.0),
        ])
        self.pub = self.create_publisher(Float32MultiArray,
                                          "/inject_disturbance", 10)
        self.srv = self.create_service(InjectDisturbance,
                                        "/inject_disturbance", self._handle)
        self.get_logger().info(
            "disturbance_node ready -> call /inject_disturbance service")

    def _handle(self, req, resp):
        left = float(req.traction_left)
        right = float(req.traction_right)
        ramp = float(req.ramp_time)
        msg = Float32MultiArray()
        msg.data = [left, right, ramp]
        self.pub.publish(msg)
        resp.success = True
        resp.message = (f"disturbance published: traction L={left:.2f} "
                        f"R={right:.2f} ramp={ramp:.1f}s")
        self.get_logger().warn(resp.message)
        return resp


def main(args=None):
    rclpy.init(args=args)
    node = DisturbanceNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
