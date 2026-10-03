"""gz_marker_node: yorunge ve izleri Gazebo 3D sahnesine renkli kureler olarak cizer.

Renk dili (demo_report.png ile ayni, artik Gazebo icinde):
  YESIL   = hedef elips yorunge (bir kez cizilir, sabit)
  KIRMIZI = robotun GERCEK izi  (/ground_truth -> Gazebo dunya gercegi)
  MAVI    = odometrinin IDDIA ettigi iz (/odom -> encoder yalani)

Yontem: gazebo_ros factory /spawn_entity + /delete_entity servisleri ile kucuk
statik kureler dover; izler uzayinca eskileri amortize siler (max_trail).
Kayma oldugunda KIRMIZI ile MAVI arasi acilir -> "encoder yalani" gorunur olur.
"""
from __future__ import annotations

import math

import rclpy
from gazebo_msgs.srv import DeleteEntity, SpawnEntity
from geometry_msgs.msg import PoseStamped
from nav_msgs.msg import Odometry, Path
from rclpy.callback_groups import MutuallyExclusiveCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node

from aeropatch.edge_loader import ensure_edge_modules

ensure_edge_modules()

SPHERE_SDF = """<?xml version="1.0"?>
<sdf version="1.6">
  <model name="%(name)s">
    <static>true</static>
    <pose>%(x).4f %(y).4f %(z).4f 0 0 0</pose>
    <link name="l">
      <visual name="v">
        <geometry><sphere><radius>%(r).3f</radius></sphere></geometry>
        <material>
          <ambient>%(rgba)s</ambient>
          <diffuse>%(rgba)s</diffuse>
        </material>
      </visual>
    </link>
  </model>
</sdf>"""

GREEN = "0.10 0.90 0.20 1"
RED = "0.95 0.10 0.10 1"
BLUE = "0.10 0.35 1.00 1"


class GzMarkerNode(Node):
    def __init__(self):
        super().__init__("gz_marker_node")
        self.declare_parameters("", [
            ("spawn_service", "/spawn_entity"),
            ("delete_service", "/delete_entity"),
            ("trail_step", 0.40),     # iz kureleri arasi mesafe (m)
            ("max_trail", 150),       # iz basina maks kure
            ("ref_step", 0.20),       # yesil yorunge adimi (m)
            ("marker_radius", 0.035),
            ("ref_radius", 0.05),
        ])
        # GRUPLAR ONCE -> create_client'a PARAMETRE (executor crash dersi)
        self.cb_timer = MutuallyExclusiveCallbackGroup()
        self.cb_sub = MutuallyExclusiveCallbackGroup()
        self.cb_cli = MutuallyExclusiveCallbackGroup()
        ssrv = str(self.get_parameter("spawn_service").value)
        dsrv = str(self.get_parameter("delete_service").value)
        self.spawn_cli = self.create_client(SpawnEntity, ssrv,
                                            callback_group=self.cb_cli)
        self.delete_cli = self.create_client(DeleteEntity, dsrv,
                                             callback_group=self.cb_cli)
        if not self.spawn_cli.wait_for_service(timeout_sec=15.0):
            self.get_logger().warn(f"{ssrv} bekleniyor (Gazebo aciliyor?)")

        self.trail_step = float(self.get_parameter("trail_step").value)
        self.max_trail = int(self.get_parameter("max_trail").value)
        self.ref_step = float(self.get_parameter("ref_step").value)
        self.m_r = float(self.get_parameter("marker_radius").value)
        self.r_r = float(self.get_parameter("ref_radius").value)

        self.create_subscription(PoseStamped, "/ground_truth", self._on_gt, 10,
                                  callback_group=self.cb_sub)
        self.create_subscription(Odometry, "/odom", self._on_odom, 10,
                                  callback_group=self.cb_sub)
        self.create_subscription(Path, "/reference_path", self._on_ref, 5,
                                  callback_group=self.cb_sub)

        self.counter = 0
        self.truth_trail: list[str] = []
        self.odom_trail: list[str] = []
        self.last_truth = None   # (x, y)
        self.last_odom = None    # (x, y)
        self.ref_done = False
        self.stats = {"truth": 0, "odom": 0}
        self.create_timer(0.1, self._housekeeping,
                          callback_group=self.cb_timer)
        self.get_logger().info(
            "gz_marker_node ready: YESIL=yorunge KIRMIZI=gercek MAVI=odom iddiasi")

    def _spawn(self, name: str, x: float, y: float, z: float,
               r: float, rgba: str) -> bool:
        if not self.spawn_cli.service_is_ready():
            return False
        req = SpawnEntity.Request()
        req.name = name
        req.entity_xml = SPHERE_SDF % {"name": name, "x": x, "y": y,
                                       "z": z, "r": r, "rgba": rgba}
        resp = self.spawn_cli.call(req)
        return resp is not None and resp.success

    def _delete(self, name: str) -> None:
        if not self.delete_cli.service_is_ready():
            return
        req = DeleteEntity.Request()
        req.name = name
        self.delete_cli.call(req)

    def _push(self, trail: list, name: str):
        trail.append(name)
        # amortize silme: tick basina 1 eski kure
        if len(trail) > self.max_trail:
            self._delete(trail.pop(0))

    def _on_ref(self, msg: Path):
        if self.ref_done or len(msg.poses) < 2:
            return
        # waypoint listesini ref_step cozunurlugunde ornekleyip yesil kureler
        pts = [(p.pose.position.x, p.pose.position.y) for p in msg.poses]
        pts.append(pts[0])  # dongu kapansin
        for i in range(len(pts) - 1):
            (x0, y0), (x1, y1) = pts[i], pts[i + 1]
            seg = math.hypot(x1 - x0, y1 - y0)
            n = max(1, int(seg / self.ref_step))
            for k in range(n):
                t = k / n
                self.counter += 1
                nm = f"ref_m_{self.counter:05d}"
                if self._spawn(nm, x0 + t * (x1 - x0),
                              y0 + t * (y1 - y0), 0.06, self.r_r, GREEN):
                    self.stats["ref"] = self.stats.get("ref", 0) + 1
        self.get_logger().info(
            f"YESIL yorunge cizildi ({self.stats.get('ref', 0)} kure)")
        self.ref_done = True

    def _on_gt(self, msg: PoseStamped):
        x, y = msg.pose.position.x, msg.pose.position.y
        if self.last_truth is not None:
            if math.hypot(x - self.last_truth[0], y - self.last_truth[1]) \
                    < self.trail_step:
                return
        self.last_truth = (x, y)
        self.counter += 1
        nm = f"truth_m_{self.counter:05d}"
        if self._spawn(nm, x, y, 0.04, self.m_r, RED):
            self.stats["truth"] += 1
            self._push(self.truth_trail, nm)

    def _on_odom(self, msg: Odometry):
        x, y = msg.pose.pose.position.x, msg.pose.pose.position.y
        if self.last_odom is not None:
            if math.hypot(x - self.last_odom[0], y - self.last_odom[1]) \
                    < self.trail_step:
                return
        self.last_odom = (x, y)
        self.counter += 1
        nm = f"odom_m_{self.counter:05d}"
        if self._spawn(nm, x, y, 0.04, self.m_r, BLUE):
            self.stats["odom"] += 1
            self._push(self.odom_trail, nm)

    def _housekeeping(self):
        if self.stats["truth"] % 20 == 1 and self.stats["truth"] > 1:
            self.get_logger().info(
                f"iz: kirmizi={self.stats['truth']} mavi={self.stats['odom']}",
                throttle_duration_sec=15.0)


def main(args=None):
    rclpy.init(args=args)
    node = GzMarkerNode()
    executor = MultiThreadedExecutor()
    executor.add_node(node)
    try:
        executor.spin()
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()

