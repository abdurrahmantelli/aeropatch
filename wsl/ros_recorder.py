"""ROS2 canli kayitci: /ground_truth, /odom, /anomaly_score, /patch/response.

JSONL dosyasina yazar; Windows tarafindaki cizim script'i rapor uretir.
Kullanim:  python3 ros_recorder.py [sure_s] [cikti.jsonl]
"""
import json
import sys
import time

import rclpy
from geometry_msgs.msg import PoseStamped
from nav_msgs.msg import Odometry
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from std_msgs.msg import Float32

from aeropatch_msgs.msg import PatchResponse

DURATION = float(sys.argv[1]) if len(sys.argv) > 1 else 20.0
OUT = (sys.argv[2] if len(sys.argv) > 2 else
       "/mnt/d/.gemini/antigravity-ide/scratch/nebius/wsl/logs/ros_record.jsonl")


class Recorder(Node):
    def __init__(self):
        super().__init__("aeropatch_recorder")
        self.f = open(OUT, "w", buffering=1)
        self.n = 0
        self.t0 = time.time()
        self.create_subscription(PoseStamped, "/ground_truth", self._gt, 10)
        self.create_subscription(Odometry, "/odom", self._odom, 10)
        self.create_subscription(Float32, "/anomaly_score", self._score,
                                 qos_profile_sensor_data)
        self.create_subscription(PatchResponse, "/patch/response", self._patch, 10)
        self.get_logger().info(f"recording {DURATION}s -> {OUT}")

    def _w(self, kind, d):
        d["kind"] = kind
        d["t"] = round(time.time() - self.t0, 3)
        self.f.write(json.dumps(d) + "\n")
        self.n += 1

    def _gt(self, m):
        self._w("gt", {"x": m.pose.position.x, "y": m.pose.position.y,
                        "theta": m.pose.orientation.z})

    def _odom(self, m):
        p = m.pose.pose.position
        self._w("odom", {"x": p.x, "y": p.y,
                         "theta": m.pose.pose.orientation.z,
                         "v": m.twist.twist.linear.x,
                         "w": m.twist.twist.angular.z})

    def _score(self, m):
        self._w("score", {"score": float(m.data)})

    def _patch(self, m):
        self._w("patch", {"event_id": m.event_id, "kp": m.kp, "kd": m.kd,
                          "slip_comp": m.slip_compensation,
                          "latency_ms": m.latency_ms,
                          "diagnosis": m.diagnosis,
                          "weather": m.weather_summary})


def main():
    rclpy.init()
    node = Recorder()
    end = time.time() + DURATION
    while time.time() < end:
        rclpy.spin_once(node, timeout_sec=100)
    node.get_logger().info(f"done: {node.n} records")
    node.f.close()
    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
