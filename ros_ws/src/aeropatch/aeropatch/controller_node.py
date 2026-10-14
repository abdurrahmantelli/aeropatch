"""controller_node: yörünge takibi + bulut yamasını PID'ye sıcak uygular.

Dinler  : /ground_truth (kontrol), /patch/request (safe-mode),
          /patch/response (yama), /inject_disturbance (odometri resync tetiği)
Yayınlar: /cmd_vel
"""
from __future__ import annotations

import math

import rclpy
from geometry_msgs.msg import PoseStamped, Twist
from rclpy.node import Node
from std_msgs.msg import Float32, String

from aeropatch.edge_loader import ensure_edge_modules

ensure_edge_modules()

from aeropatch_msgs.msg import PatchRequest, PatchResponse  # noqa: E402
from edge.path_follower import (FollowerParams, PathFollower, WaypointPath,  # noqa: E402
                                circular_waypoints)


def yaw_from_quat(q) -> float:
    """Kuaterniyon -> yaw (Gazebo gercek kuaterniyon gonderir)."""
    siny = 2.0 * (q.w * q.z + q.x * q.y)
    cosy = 1.0 - 2.0 * (q.y * q.y + q.z * q.z)
    return math.atan2(siny, cosy)


class ControllerNode(Node):
    def __init__(self):
        super().__init__("controller_node")
        self.declare_parameters("", [
            ("kp", 2.2), ("ki", 0.0), ("kd", 0.08), ("max_speed", 0.22),
            # LOCAL FAST FALLBACK (0 ms): ilk alarm aninda bulutu beklemeden
            # uygulanan guvenli kazanc (islak: Kp dusur, Kd yukselt)
            ("local_kp", 1.5), ("local_kd", 0.22),
            # 2. ALARM ESKALASYONU (S>=0.85): bulut BEKLENMEZ, devrilme
            # engellenir — daha agresif lokal kazanc (Kp=1.0, Kd=0.28)
            ("escalate_kp", 1.0), ("escalate_kd", 0.28),
        ])
        # Elips robotun spawn noktasi (0,0) uzerinden baslar (phase=pi ->
        # (0,0) = aci 180 noktasi). Yoksa pure-pursuit baslangicta ilk
        # hedefe DUZ CIZGI cizer — Gazebo demo'sunda "algo sacmaliyor"
        # gorunurdu (gerekce: (0,0) eski elipsin DIStayndaydi). n=36 ->
        # waypoint arasi ~0.32 m -> akici daire, cokgen degil.
        wps = circular_waypoints(cx=2.2, cy=0.0, rx=2.2, ry=1.5, n=36,
                                 phase=math.pi)
        self.path = WaypointPath(wps, goal_radius=0.30)
        p = FollowerParams(
            kp=float(self.get_parameter("kp").value),
            ki=float(self.get_parameter("ki").value),
            kd=float(self.get_parameter("kd").value),
            max_speed=float(self.get_parameter("max_speed").value))
        self.follower = PathFollower(self.path, p)
        self.dt = 0.02
        self.last_pose = None
        self.pub = self.create_publisher(Twist, "/cmd_vel", 10)
        # RViz loglamasi: durum satirlari gz_truth_node tarafindan robotun
        # uzerinde TEXT marker olarak gosterilir (SAFE=yesil..kirmizi kodlu)
        self.status_pub = self.create_publisher(String, "/aeropatch/status", 10)
        self.create_subscription(PoseStamped, "/ground_truth", self._on_pose, 10)
        # Anomali skoru: 2. alarm eskalasyonu icin (S>=0.85 -> agresif lokal)
        self.create_subscription(Float32, "/anomaly_score", self._on_score, 10)
        self.create_subscription(PatchRequest, "/patch/request",
                                  self._on_request, 10)
        self.create_subscription(PatchResponse, "/patch/response",
                                  self._on_response, 10)
        self._escalated = False
        self.timer = self.create_timer(self.dt, self._tick)
        self.get_logger().info("controller_node ready (PID path follower)")
        self._status("MODE=OK tracking path")

    def _status(self, text: str) -> None:
        """Durum satirini /aeropatch/status uzerinden RViz'e logla."""
        m = String()
        m.data = text
        self.status_pub.publish(m)

    def _on_pose(self, msg: PoseStamped):
        self.last_pose = (msg.pose.position.x, msg.pose.position.y,
                          yaw_from_quat(msg.pose.orientation))

    def _on_score(self, msg: Float32):
        """2. alarm eskalasyonu (edge, 0 ms): bulut BEKLENMEZ.

        S >= 0.85: ilk yama yetersiz kaldi demektir — daha agresif lokal
        kazanca gec (Kp DUSER 1.0, Kd YUKSELIR 0.28; devrilme engellenir).
        Histeresis: cikis S < 0.60 (giris 0.85 -> chattering olmaz).
        Bulut kotasindan bagimsiz: fiziksel mudahale asla kilitlenmez.
        """
        s = float(msg.data)
        if s >= 0.85 and not self._escalated:
            self._escalated = True
            ek = float(self.get_parameter("escalate_kp").value)
            ekd = float(self.get_parameter("escalate_kd").value)
            self.follower.apply_patch({"heading_pid": {"kp": ek, "kd": ekd}})
            self._status("MODE=ESCALATED: Kp=%.2f Kd=%.2f (anti-tip guard)"
                         % (ek, ekd))
            self.get_logger().warn(
                f"ESCALATION (2nd alarm, 0ms): Kp={ek:.2f} Kd={ekd:.2f} "
                "— no cloud wait, tip-over prevented")
        elif s < 0.60 and self._escalated:
            self._escalated = False

    def _on_request(self, msg: PatchRequest):
        if msg.trigger == "recover":
            self._status("RECOVER: awaiting baseline restore")
            self.get_logger().info(
                "recover request sent to cloud (awaiting baseline restore)")
            return
        # --- LOCAL FAST FALLBACK (0 ms latency) ---
        # Islak zeminin ilk tespitinde bulut BEKLENMEZ: lokal guvenli
        # parametrelere gec — Kp DUSER (tork yumusar, patinaj buyumez),
        # Kd YUKSELIR (savrulma bastirilir); safe-mode hiz tavanini %35
        # keser. Buluttan (NIM/Tavily) hassas yama gelince _on_response
        # uzerine yazar (0 ms lokal -> 8-35 sn bulut ince ayari).
        lk = float(self.get_parameter("local_kp").value)
        lkd = float(self.get_parameter("local_kd").value)
        self.follower.apply_patch({"heading_pid": {"kp": lk, "kd": lkd}})
        self.follower.set_safe_mode(True)
        self._status("MODE=SAFE local: Kp=%.2f Kd=%.2f (awaiting cloud)" % (lk, lkd))
        self.get_logger().warn(
            f"LOCAL FALLBACK (0ms): Kp={lk:.2f} Kd={lkd:.2f} "
            f"v_cap=35% -> awaiting cloud patch")

    def _on_response(self, msg: PatchResponse):
        self.follower.apply_patch({
            "heading_pid": {"kp": msg.kp, "ki": msg.ki, "kd": msg.kd},
            "slip_compensation": msg.slip_compensation,
            "max_speed": msg.max_speed,
        })
        self.follower.set_safe_mode(False)
        self._status(
            "MODE=PATCH: Kp=%.2f v=%.2f | %s | %.1fs" % (
                msg.kp, msg.max_speed, msg.model or "?",
                msg.latency_ms / 1000.0))
        self.get_logger().info(
            f"PATCH applied: Kp={msg.kp:.2f} Kd={msg.kd:.2f} "
            f"slip_comp={msg.slip_compensation:+.3f} v_max={msg.max_speed:.2f}")

    def _tick(self):
        if self.last_pose is None:
            return
        x, y, theta = self.last_pose
        v, omega, tx, ty, he = self.follower.compute_cmd(x, y, theta, self.dt)
        cmd = Twist()
        cmd.linear.x = float(v)
        cmd.angular.z = float(omega)
        self.pub.publish(cmd)


def main(args=None):
    rclpy.init(args=args)
    node = ControllerNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
