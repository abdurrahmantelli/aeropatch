"""monitor_node: odometri + harici lokalizasyonu izler, anomali algılar.

Dinler  : /odom, /ground_truth, /slip_state
Yayınlar: /patch/request (aeropatch_msgs/PatchRequest)  <- alarm anında
          /anomaly_score (std_msgs/Float32)             <- canlı izleme
"""
from __future__ import annotations

import math

import rclpy
from geometry_msgs.msg import PoseStamped
from nav_msgs.msg import Odometry
from rclpy.node import Node
from std_msgs.msg import Float32

from aeropatch.edge_loader import ensure_edge_modules

ensure_edge_modules()

from aeropatch_msgs.msg import PatchRequest, PatchResponse  # noqa: E402
from edge.anomaly import AnomalyConfig, AnomalyDetector  # noqa: E402
from edge.path_follower import circular_waypoints, cross_track_error  # noqa: E402
from edge.robot_physics import wrap_angle  # noqa: E402
from edge.telemetry import TelemetrySample, new_event_id  # noqa: E402


def yaw_from_quat(q) -> float:
    """Kuaterniyon -> yaw (Gazebo gercek kuaterniyon gonderir)."""
    siny = 2.0 * (q.w * q.z + q.x * q.y)
    cosy = 1.0 - 2.0 * (q.y * q.y + q.z * q.z)
    return math.atan2(siny, cosy)


class MonitorNode(Node):
    def __init__(self):
        super().__init__("monitor_node")
        self.declare_parameters("", [
            ("threshold", 0.60), ("persistence", 5), ("cooldown_s", 4.0),
            ("telemetry_window", 25), ("region", "Kadikoy, Istanbul, TR"),
            ("mission", "perimeter_patrol"), ("robot_id", "aeropatch-01"),
            ("patch_grace_s", 6.0),
            # DR runaway guvenlik senkronu esikleri (_evaluate icinde)
            ("dr_guard_m", 0.5), ("dr_guard_s", 10.0), ("dr_guard_rate", 0.05),
            # HISTERESIS (chattering onleyici): alarm ust esigi (threshold)
            # ile recover alt esigi FARKLI — recover icin skor alt esigin
            # altinda recover_hold_s boyunca stabil kalmali. Aksi halde
            # ayni esikte kuru-islak-kuru sonsuz donguye girer (chattering).
            ("recover_score", 0.20), ("recover_hold_s", 10.0),
        ])
        self.detector = AnomalyDetector(AnomalyConfig(
            threshold=float(self.get_parameter("threshold").value),
            persistence=int(self.get_parameter("persistence").value),
            cooldown_s=float(self.get_parameter("cooldown_s").value)))
        self.window = int(self.get_parameter("telemetry_window").value)
        # controller_node ile AYNI yorunge — CTE kontrol yorungesine karsi
        # skorlanmali! Eski cx=1.0/cy=2.2 elipsi YANLISTI: robot dogru
        # yorungede bile ~3 m CTE gorunuyor, skor tabani bozuktu.
        self.wps = circular_waypoints(cx=2.2, cy=0.0, rx=2.2, ry=1.5,
                                      n=36, phase=math.pi)
        self.ring = []
        self.odom = None
        self.gt = None
        self.prev_gt = None
        self.last_t = 0.0
        # HISTERESIS durumu: alarm sonrasi active; skor alt esige dusup
        # hold sureci tamamlaninca recover firlatilir ve state sifirlanir
        self._recover_active = False
        self._recover_since = None
        # Bulut onayli odom resync tutucusu (dx, dy, dyaw): yama anindaki
        # kalici DR kaymasi yeni sifir noktasi olur — aksi halde pos_mismatch
        # bileşeni skoru sonsuza dek yuksek tutar -> alarm dongusu (canli
        # testte kanitlandi: skor 0.90'da takili kaldı).
        self._resync = (0.0, 0.0, 0.0)
        self.patch_pub = self.create_publisher(PatchRequest, "/patch/request", 10)
        self.score_pub = self.create_publisher(Float32, "/anomaly_score", 10)
        # /odom_corrected: resync'li odometri RViz'e — gz_truth_node mavi iz +
        # SLIP_GAP'i buradan okur; yama aninda iz sifirlanir, toparlanma
        # ekranda gorunur (ham odom'da kayma birikmeye devam ederdi:
        # "yama gelse de kayma artiyor" kok nedeni)
        self.odom_corr_pub = self.create_publisher(
            PoseStamped, "/odom_corrected", 10)
        self.create_subscription(Odometry, "/odom", self._on_odom, 10)
        self.create_subscription(PoseStamped, "/ground_truth", self._on_gt, 10)
        self.create_subscription(PatchResponse, "/patch/response",
                                  self._on_patch_response, 10)
        self.timer = self.create_timer(0.02, self._evaluate)
        self.get_logger().info("monitor_node ready (pure-math anomaly detector)")

    def _on_odom(self, msg: Odometry):
        self.odom = msg

    def _on_gt(self, msg: PoseStamped):
        self.gt = msg

    def _on_patch_response(self, msg: PatchResponse):
        """Yama geldi: alarm hold-off + odom resync.

        grace = max(patch_grace_s, bulut gecikmesi + 8s) — gercek LLM yavas
        (10-30 sn) olabilir (kullanici onayi: kabul edilebilir); robot yine
        alarm dongusune dusmesin, yamaya guvenip toparlansin. odom_resync:
        bulut onayli duzeltme anindaki (odom-vs-gercek) kalici kayma yeni
        sifir noktasi olur — bir sonraki kayma yine yakalanir.
        """
        grace = max(float(self.get_parameter("patch_grace_s").value),
                    msg.latency_ms / 1000.0 + 8.0)
        grace = min(grace, 45.0)
        now = self.get_clock().now().nanoseconds * 1e-9
        self.detector.hold(now, grace)
        if msg.odom_resync and self.odom is not None and self.gt is not None:
            op = self.odom.pose.pose.position
            gp = self.gt.pose.position
            self._resync = (op.x - gp.x, op.y - gp.y,
                            yaw_from_quat(self.odom.pose.pose.orientation)
                            - yaw_from_quat(self.gt.pose.orientation))
            self.get_logger().info(
                f"odom resync: persistent DR slip ({self._resync[0]:+.2f}, "
                f"{self._resync[1]:+.2f}) m zeroed (cloud-confirmed)")
        self.get_logger().info(
            f"patch {msg.event_id} received -> alarm hold-off {grace:.0f}s "
            f"(cloud latency {msg.latency_ms / 1000.0:.1f}s)")

    def _evaluate(self):
        if self.odom is None or self.gt is None:
            return
        now_ns = self.gt.header.stamp.sec + self.gt.header.stamp.nanosec * 1e-9
        p = self.gt.pose
        q = self.odom.pose.pose
        tw = self.odom.twist.twist
        gt_yaw = yaw_from_quat(p.orientation)
        # Ilk ornek: yalnizca referans kaydet, skorlama yok
        # (baslangicta dt bilinmediginden yanlis alarm uretilmesin)
        if self.prev_gt is None:
            self.prev_gt = (p.position.x, p.position.y, gt_yaw)
            self.last_t = now_ns
            return
        dt_raw = now_ns - self.last_t
        self.last_t = now_ns
        if dt_raw < 0.005 or dt_raw > 0.5:
            # timestamp titremesi / mesaj sirasi oynamasi: bu ornegi atla
            self.prev_gt = (p.position.x, p.position.y, gt_yaw)
            return
        dt = dt_raw
        # Gerçek hızlar: harici lokalizasyon farkından türetilir (slip görülür)
        v_true = math.hypot(p.position.x - self.prev_gt[0],
                            p.position.y - self.prev_gt[1]) / dt
        dth = gt_yaw - self.prev_gt[2]
        omega_true = ((dth + math.pi) % (2 * math.pi) - math.pi) / dt
        # Fiziksel sansur: outlier dt degerlerinin skoru patlatmasini onler
        v_true = max(0.0, min(v_true, 0.6))
        omega_true = max(-6.0, min(omega_true, 6.0))
        self.prev_gt = (p.position.x, p.position.y, gt_yaw)
        cte = cross_track_error(p.position.x, p.position.y, self.wps)
        # Resync: yama anindaki kalici DR kaymasi cikarilir — boylece
        # pos_mismatch yamadan sonra sifira doner, yeni kayma yakalanir
        x_odom_c = q.position.x - self._resync[0]
        y_odom_c = q.position.y - self._resync[1]
        th_odom_c = wrap_angle(yaw_from_quat(q.orientation) - self._resync[2])
        # /odom_corrected yayini (50 Hz): resync'li pozisyon — yama geldigi
        # anda iz truth'a yapisir (SLIP_GAP ~0 -> toparlanma gorunur)
        corr = PoseStamped()
        corr.header.frame_id = "map"
        corr.header.stamp = self.gt.header.stamp
        corr.pose.position.x = x_odom_c
        corr.pose.position.y = y_odom_c
        corr.pose.orientation.z = math.sin(th_odom_c / 2.0)
        corr.pose.orientation.w = math.cos(th_odom_c / 2.0)
        self.odom_corr_pub.publish(corr)
        sample = TelemetrySample(
            t=now_ns, x=p.position.x, y=p.position.y, theta=gt_yaw,
            x_odom=x_odom_c, y_odom=y_odom_c,
            theta_odom=th_odom_c,
            v_odom=tw.linear.x, omega_odom=tw.angular.z,
            v_true=v_true, omega_true=omega_true, cte=cte, heading_error=0.0)
        verdict = self.detector.update(sample, now_ns)
        sample.anomaly_score = verdict.score
        self.ring.append(sample)
        self.ring = self.ring[-(self.window * 3):]
        self.score_pub.publish(Float32(data=float(verdict.score)))
        if verdict.alarm or float(verdict.score) >= 0.85:
            # Alarm (ust esik): recover hold sayaci sifirlanir — histeresis.
            # ESKALASYON: hold doneminde bile skor >= 0.85 ise alarm ZORUNLU
            # (2. alarm engellenmez — devrilme korumasi, guvenlik kritik)
            self._recover_since = None
            self._recover_active = True
            self._dispatch(sample, verdict.score, verdict.event_id)
            if not verdict.alarm:
                self.get_logger().warn(
                    f"ESCALATION score={float(verdict.score):.2f} >= 0.85 "
                    "(alarm during hold — anti-tip guard)")
        elif self._recover_active:
            # Alarm sonrasi toparlanma izleme: alt esik + hold
            self._recover_tick(float(verdict.score), now_ns)

    def _dispatch(self, sample, score, event_id):
        msg = PatchRequest()
        msg.stamp = self.get_clock().now().to_msg()
        # ESKALASYON GUARD: cooldown/hold sirasinda skor >= 0.85 ile zorlanan
        # alarmda detector event MINT ETMEZ (verdict.event_id=None, anomaly.py
        # satir 75). PatchRequest.event_id str tiplidir -> None gecerse
        # AssertionError: node COKER (canli kanit 2026-10-12 17:23: ikinci
        # alarmda "The 'event_id' field must be of type 'str'" -> process has
        # died -> /odom_corrected dondu, SLIP_GAP 4.3 m'de salindi).
        if not isinstance(event_id, str) or not event_id:
            event_id = new_event_id("evt-esc")
        msg.event_id = event_id
        msg.trigger = "physical_deviation"
        msg.robot_id = str(self.get_parameter("robot_id").value)
        msg.region = str(self.get_parameter("region").value)
        msg.mission = str(self.get_parameter("mission").value)
        msg.score = float(score)
        msg.x, msg.y, msg.theta = sample.x, sample.y, sample.theta
        msg.x_odom, msg.y_odom = sample.x_odom, sample.y_odom
        msg.theta_odom = sample.theta_odom
        msg.v_odom, msg.omega_odom = sample.v_odom, sample.omega_odom
        msg.v_true, msg.omega_true = sample.v_true, sample.omega_true
        msg.cte, msg.heading_error = sample.cte, sample.heading_error
        flat = []
        for s in self.ring[-self.window:]:
            flat += [s.x, s.y, s.theta, s.v_odom, s.v_true,
                     s.omega_odom, s.omega_true, s.cte]
        msg.recent_telemetry = [float(v) for v in flat]
        self.patch_pub.publish(msg)
        self.get_logger().warn(
            f"ALARM score={score:.2f} -> telemetry dispatched to cloud ({event_id})")

    def _recover_tick(self, score: float, now_ns: int) -> None:
        """Alt esik + hold: skor < recover_score iken recover_hold_s boyunca
        stabil kalirsa trigger='recover' (baseline restore) firlatilir.
        Skor esige geri cikarsa hold sayaci sifirlanir (chattering YOK)."""
        rec = float(self.get_parameter("recover_score").value)
        hold = float(self.get_parameter("recover_hold_s").value)
        if score >= rec:
            self._recover_since = None
            return
        if self._recover_since is None:
            self._recover_since = now_ns
            self.get_logger().info(
                f"RECOVER hold: score={score:.2f} < {rec:.2f} -> "
                f"{hold:.0f}s stability required")
            return
        if (now_ns - self._recover_since) / 1e9 >= hold:
            self._recover_since = None
            self._recover_active = False
            self._dispatch_recover(score)

    def _dispatch_recover(self, score: float) -> None:
        """trigger='recover': baseline restore istegi (bulut aninda doner)."""
        msg = PatchRequest()
        msg.stamp = self.get_clock().now().to_msg()
        msg.event_id = new_event_id("evt-rec")
        msg.trigger = "recover"
        msg.robot_id = str(self.get_parameter("robot_id").value)
        msg.region = str(self.get_parameter("region").value)
        msg.mission = str(self.get_parameter("mission").value)
        msg.score = float(score)
        self.patch_pub.publish(msg)
        self.get_logger().warn(
            f"RECOVER triggered (score={score:.2f}) -> baseline restore requested")


def main(args=None):
    rclpy.init(args=args)
    node = MonitorNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
