"""bridge_node: /patch/request'i buluta yollar, /patch/response yayınlar.

Bulut çağrısı worker thread'de yapılır (rclpy spin'i bloklanmaz);
mock=True iken edge.mock_cloud (Nemotron+Tavily simülasyonu) kullanılır,
mock=False iken Nebius Serverless Endpoint'ine HTTP POST atılır.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import rclpy
from rclpy.node import Node

from aeropatch.edge_loader import ensure_edge_modules

ensure_edge_modules()

from aeropatch_msgs.msg import PatchRequest, PatchResponse  # noqa: E402
from edge.cloud_bridge import CloudBridge  # noqa: E402
from edge.mock_cloud import MockCloud  # noqa: E402
from edge.telemetry import TelemetryPacket  # noqa: E402


class BridgeNode(Node):
    def __init__(self):
        super().__init__("bridge_node")
        self.declare_parameters("", [
            ("mock_cloud", True), ("endpoint_url", ""), ("api_key", ""),
            ("timeout_s", 8.0), ("weather", "rain"),
            ("region", "Kadikoy, Istanbul, TR"),
            ("mock_min_latency_ms", 350.0), ("mock_max_latency_ms", 800.0),
        ])
        mock = bool(self.get_parameter("mock_cloud").value)
        mock_cloud = MockCloud(
            weather=str(self.get_parameter("weather").value),
            min_latency_ms=float(self.get_parameter("mock_min_latency_ms").value),
            max_latency_ms=float(self.get_parameter("mock_max_latency_ms").value),
        ) if mock else None
        self.bridge = CloudBridge(
            mock=mock,
            endpoint_url=str(self.get_parameter("endpoint_url").value),
            api_key=str(self.get_parameter("api_key").value),
            timeout_s=float(self.get_parameter("timeout_s").value),
            mock_cloud=mock_cloud)
        self.pool = ThreadPoolExecutor(max_workers=1)   # NOT: 'executor' adı rclpy ile çakışır!
        self.pending = None
        self.create_subscription(PatchRequest, "/patch/request",
                                  self._on_request, 10)
        self.pub = self.create_publisher(PatchResponse, "/patch/response", 10)
        self.timer = self.create_timer(0.02, self._poll)
        self.get_logger().info(
            f"bridge_node ready ({'MOCK cloud (nemotron+tavily sim)' if mock else 'REAL Nebius endpoint'})")

    def _on_request(self, msg: PatchRequest):
        if self.pending is not None:
            self.get_logger().warn("patch already in flight, ignoring")
            return
        n = 8
        rec = list(msg.recent_telemetry)
        rows = [rec[i:i + n] for i in range(0, len(rec) - n + 1, n)]
        tel = [{"x": r[0], "y": r[1], "theta": r[2], "v_odom": r[3],
                "v_true": r[4], "omega_odom": r[5], "omega_true": r[6],
                "cte": r[7]} for r in rows]
        packet = TelemetryPacket(
            robot_id=msg.robot_id, event_id=msg.event_id, trigger=msg.trigger,
            score=msg.score, created_at=msg.stamp.sec + msg.stamp.nanosec * 1e-9,
            region=msg.region, mission=msg.mission,
            pose={"x": msg.x, "y": msg.y, "theta": msg.theta},
            current_gains={"kp": 2.2, "ki": 0.0, "kd": 0.08, "max_speed": 0.22},
            telemetry=tel)
        self.pending = {"event_id": msg.event_id,
                        "future": self.pool.submit(
                            self.bridge.request_patch, packet)}
        self.get_logger().info(f"telemetry {msg.event_id} -> cloud agent...")

    def _poll(self):
        if self.pending is None or not self.pending["future"].done():
            return
        fut = self.pending["future"]
        self.pending = None
        try:
            resp = fut.result()
        except Exception as e:
            self.get_logger().error(f"cloud error: {e}")
            return
        out = PatchResponse()
        out.stamp = self.get_clock().now().to_msg()
        out.event_id = resp.event_id
        out.diagnosis = resp.diagnosis
        out.weather_summary = resp.weather_summary
        out.weather_source = resp.weather_source
        out.latency_ms = float(resp.latency_ms)
        out.confidence = float(resp.confidence)
        p = resp.patch
        hp = p.get("heading_pid", {})
        out.kp = float(hp.get("kp", 2.2))
        out.ki = float(hp.get("ki", 0.0))
        out.kd = float(hp.get("kd", 0.08))
        out.slip_compensation = float(p.get("slip_compensation", 0.0))
        out.max_speed = float(p.get("max_speed", 0.22))
        out.odom_resync = bool(p.get("odom_resync", False))
        out.model = str(p.get("model", ""))
        self.pub.publish(out)
        self.get_logger().info(
            f"PATCH back in {resp.latency_ms:.0f} ms [model={out.model or '?'} "
            f"resync={out.odom_resync}]: {resp.diagnosis[:80]}...")


def main(args=None):
    rclpy.init(args=args)
    node = BridgeNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
