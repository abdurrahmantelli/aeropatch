"""gz_truth_node: Gazebo dunya gercegi -> /ground_truth + RViz patikalari.

sim_node'un Gazebo karsiligi: monitor_node ve controller_node HIC DEGISMEDEN
calisir (ayni /ground_truth arayuzu).

Dinler   : gazebo_ros_state /gazebo/get_entity_state servisi, /odom (encoder DR)
Yayinlar : /ground_truth (PoseStamped, "map"), /reference_path, /truth_path,
           /odom_path (nav_msgs/Path, RViz icin)
"""
from __future__ import annotations

import math

import rclpy
from gazebo_msgs.srv import GetEntityState
from geometry_msgs.msg import PoseStamped
from nav_msgs.msg import Odometry, Path
from visualization_msgs.msg import Marker, MarkerArray
from rclpy.callback_groups import MutuallyExclusiveCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from std_msgs.msg import String

from aeropatch.edge_loader import ensure_edge_modules

ensure_edge_modules()

from aeropatch_msgs.msg import PatchResponse  # noqa: E402
from edge.path_follower import circular_waypoints  # noqa: E402


def _yaw_from_quat(q) -> float:
    siny = 2.0 * (q.w * q.z + q.x * q.y)
    cosy = 1.0 - 2.0 * (q.y * q.y + q.z * q.z)
    return math.atan2(siny, cosy)


class GzTruthNode(Node):
    def __init__(self):
        super().__init__("gz_truth_node")
        self.declare_parameters("", [
            ("entity_name", "aerobot"),
            ("get_service", "/gazebo/get_entity_state"),
            ("get_service_fallback", "/demo/get_entity_state"),
            ("publish_hz", 50.0),
        ])
        self.entity = str(self.get_parameter("entity_name").value)
        # GRUPLAR ONCE OLUSUR -> create_client'a PARAMETRE olarak verilir.
        # (Client yaratiktan SONRA client.callback_group atamak rclpy
        #  executor'inda assertion crash yaratir — canli testle kanitlandi.)
        self.timer_cb = MutuallyExclusiveCallbackGroup()
        self.sub_cb = MutuallyExclusiveCallbackGroup()
        self.cli_cb = MutuallyExclusiveCallbackGroup()

        main_srv = str(self.get_parameter("get_service").value)
        fb_srv = str(self.get_parameter("get_service_fallback").value)
        self.cli = self.create_client(GetEntityState, main_srv,
                                      callback_group=self.cli_cb)
        self.cli_fb = self.create_client(GetEntityState, fb_srv,
                                         callback_group=self.cli_cb)
        if not self.cli.wait_for_service(timeout_sec=10.0):
            self.get_logger().info(
                f"{main_srv} not up yet (Gazebo starting?), fallback: {fb_srv}")

        hz = float(self.get_parameter("publish_hz").value)

        self.gt_pub = self.create_publisher(PoseStamped, "/ground_truth", 10)
        self.ref_pub = self.create_publisher(Path, "/reference_path", 1)
        self.truth_path_pub = self.create_publisher(Path, "/truth_path", 10)
        self.odom_path_pub = self.create_publisher(Path, "/odom_path", 10)
        self.slip_pub = self.create_publisher(MarkerArray, "/slip_markers", 10)
        self.create_subscription(Odometry, "/odom", self._on_odom, 10,
                                  callback_group=self.sub_cb)
        # /odom_corrected: monitor_node'un resync'li odometrisi — mavi iz +
        # SLIP_GAP bunu okur. Yama geldiginde resync izi sifirlar:
        # toparlanma RViz'de net gorunur (ham odom'da kayma birikmeye
        # devam ediyordu — "yama gelse de kayma artiyor" kok nedeni).
        self.create_subscription(PoseStamped, "/odom_corrected",
                                  self._on_odom_corr, 10,
                                  callback_group=self.sub_cb)
        # Bulut/durum loglamasi: controller_node'un durum satirlari robotun
        # uzerinde TEXT marker olarak RViz'e basilir (ayni /slip_markers
        # dizisine gider -> RViz config degisikligi gerekmez)
        self.create_subscription(String, "/aeropatch/status", self._on_status,
                                  10, callback_group=self.sub_cb)
        # Bulut/Tavily loglamasi: yama geldiginde hava kaynagi (TAVILY/DDG)
        # + model + hava ozeti RViz'e TEXT marker olarak basilir — juri
        # demosunda "bulut gercekten Tavily ile hava aradi" kaniti ekranda.
        self.create_subscription(PatchResponse, "/patch/response",
                                  self._on_cloud, 10,
                                  callback_group=self.sub_cb)
        self.odom_pose = None
        self.odom_corr = None   # resync'li odometri (monitor_node'dan)
        self._status_text = ""
        self._cloud_text = ""

        self.truth_path = Path()
        self.truth_path.header.frame_id = "map"
        self.odom_path = Path()
        self.odom_path.header.frame_id = "map"
        self._ref_path = self._build_reference()
        self._last_odom_t = 0.0
        self._last_truth_t = 0.0
        self._last_ref_t = -10.0
        self._last_slip_t = 0.0
        self._pending = None       # async get_entity_state Future tutucusu
        self._truth_ok = False     # ilk basarili truth okumasi loglandi mi
        self._last_gaplog_t = 0.0  # SLIP_GAP periyodik log tutucusu

        self.timer = self.create_timer(1.0 / hz, self._tick,
                                       callback_group=self.timer_cb)
        self.get_logger().info(
            f"gz_truth_node ready: entity={self.entity} "
            f"srv={self.cli.srv_name} hz={hz:.0f}")

    def _build_reference(self) -> Path:
        # controller_node ile AYNI yorunge (referans path = kontrol yorungesi):
        # robotun spawn noktasi (0,0) uzerinden baslar, n=36 akici daire.
        wps = circular_waypoints(cx=2.2, cy=0.0, rx=2.2, ry=1.5, n=36,
                                 phase=math.pi)
        path = Path()
        path.header.frame_id = "map"
        for (x, y) in wps:
            ps = PoseStamped()
            ps.header.frame_id = "map"
            ps.pose.position.x = float(x)
            ps.pose.position.y = float(y)
            ps.pose.orientation.w = 1.0
            path.poses.append(ps)
        return path

    def _on_status(self, msg: String):
        self._status_text = msg.data

    def _on_cloud(self, msg: PatchResponse):
        # Bulut yamasi RViz'de ALT ALTA satirlar halinde — tek satirda
        # karisiyordu (kullanici istegi: bir satir hiz, bir satir slip...):
        #   BULUT[model] kaynak (lat ..s)
        #   teshis: ...
        #   kp=.. kd=..
        #   hiz_max=.. m/s
        #   patinaj telafisi: .. m/s
        #   resync: EVET/HAYIR
        #   hava[kaynak]: ozet
        src = (msg.weather_source or "?")
        src = src.replace("tavily://", "TAVILY ").replace("ddg://", "DDG ")
        # Kullanici istegi: satirlar KISA olsun (uzun satir ekranin disina
        # tasiyordu) — teshis 40, hava 40 karakterle sinirli:
        lines = [
            "CLOUD[%s] %s (%.1fs)" % ((msg.model or "?")[:20], src,
                                      msg.latency_ms / 1000.0),
            "diagnosis: %s" % (msg.diagnosis or "?")[:40],
            "kp=%.2f kd=%.3f" % (msg.kp, msg.kd),
            "v_max=%.2f m/s conf=%.0f%%" % (msg.max_speed,
                                            (msg.confidence or 0.0) * 100.0),
            "slip comp: %.3f m/s" % msg.slip_compensation,
            "resync: %s" % ("YES" if msg.odom_resync else "NO"),
        ]
        if msg.weather_summary:
            lines.append("weather[%s]: %s" % (src.strip() or "?",
                                           msg.weather_summary[:40]))
        self._cloud_text = "\n".join(lines)

    def _on_odom(self, msg: Odometry):
        # Ham odometri (encoder DR): yalnizca sakla — mavi iz artik
        # resync'li /odom_corrected kopyasindan cizilir (asagida)
        self.odom_pose = msg.pose.pose

    def _on_odom_corr(self, msg: PoseStamped):
        # Yama resync atlmasi: izdeki son noktadan >1 m sifirlama -> eski
        # kayma izini temizle (atama cizgisi ellipse carpar, goruntu karisir;
        # SLIP_GAP yazisi 4m -> 0m dususu zaten sifirlamayi gosterir)
        pos = msg.pose.position
        if self.odom_path.poses:
            last = self.odom_path.poses[-1].pose.position
            if math.hypot(pos.x - last.x, pos.y - last.y) > 1.0:
                self.odom_path.poses = []
        self.odom_corr = msg.pose  # PoseStamped.pose -> Pose (msg.pose.pose YANLIS: Pose'un .pose'u yok)
        now = self.get_clock().now().nanoseconds * 1e-9
        if now - self._last_odom_t < 0.5:
            return
        self._last_odom_t = now
        self.odom_path.poses.append(msg)
        self.odom_path.poses = self.odom_path.poses[-2000:]
        self.odom_path.header.stamp = self.get_clock().now().to_msg()
        self.odom_path_pub.publish(self.odom_path)

    def _tick(self):
        # ASYNC servis cagrisi: sync cli.call() MultiThreadedExecutor'da
        # tum thread'leri bloklayip surgune yol acar (canli testte kaniti:
        # 1 "basarisiz" uyarisi sonra sessizlik, sifir /ground_truth ->
        # monitor hic degerlendiremedi -> alarm yok). call_async bloklamaz;
        # cevap sonraki tick'te (20 ms sonra) okunur.
        if self._pending is not None and self._pending.done():
            resp = self._pending.result()
            self._pending = None
            if resp is not None and resp.success:
                self._handle_state(resp.state, self.get_clock().now())
            else:
                self.get_logger().warn(
                    f"get_entity_state failed (entity={self.entity})",
                    throttle_duration_sec=10.0)
        if self._pending is None:
            cli = None
            if self.cli.service_is_ready():
                cli = self.cli
            elif self.cli_fb.service_is_ready():
                cli = self.cli_fb
            if cli is not None:
                req = GetEntityState.Request()
                req.name = self.entity
                req.reference_frame = "world"
                self._pending = cli.call_async(req)

    def _handle_state(self, state, now):
        if not self._truth_ok:
            self._truth_ok = True
            self.get_logger().info(
                "TRUTH_OK: first true pose received -> /ground_truth streaming")
        now_s = now.nanoseconds * 1e-9

        gt = PoseStamped()
        gt.header.frame_id = "map"
        gt.header.stamp = now.to_msg()
        gt.pose = state.pose
        self.gt_pub.publish(gt)

        if now_s - self._last_truth_t >= 0.5:
            self._last_truth_t = now_s
            self.truth_path.poses.append(gt)
            self.truth_path.poses = self.truth_path.poses[-2000:]
            self.truth_path.header.stamp = gt.header.stamp
            self.truth_path_pub.publish(self.truth_path)
        if now_s - self._last_ref_t >= 2.0:
            self._last_ref_t = now_s
            self._ref_path.header.stamp = gt.header.stamp
            self.ref_pub.publish(self._ref_path)
        if now_s - self._last_slip_t >= 0.5:
            self._last_slip_t = now_s
            self._publish_slip(state.pose, now)


    def _publish_slip(self, true_pose, now):
        """Kaymayi RViz'de gorunur kilar: odom (robotun iddiasi) -> gercek
        konum oku + robotun uzerinde canli SLIP yazisi. Ok uzadikca kayma
        buyur; sari->kirmizi renk gecisi siddeti gosterir."""
        # Once resync'li odometri (monitor_node /odom_corrected) — yama
        # geldiginde gap ~0'a duser (toparlanma gorunur); monitor yoksa
        # ham odom'a dus (robustluk)
        odom = self.odom_corr if self.odom_corr is not None else self.odom_pose
        arr = MarkerArray()
        gap = None
        if odom is not None:
            gap = math.hypot(true_pose.position.x - odom.position.x,
                             true_pose.position.y - odom.position.y)
            if gap > 0.03:
                m = Marker()
                m.header.frame_id = "map"
                m.header.stamp = now.to_msg()
                m.ns = "slip_arrow"
                m.id = 0
                m.type = Marker.ARROW
                m.action = Marker.ADD
                m.pose.orientation.w = 1.0
                m.scale.x = 0.025
                m.scale.y = 0.05
                m.scale.z = 0.05
                m.points = [odom.position, true_pose.position]
                m.color.r = min(1.0, 0.45 + gap * 2.0)
                m.color.g = max(0.0, 0.9 - gap * 2.0)
                m.color.b = 0.05
                m.color.a = 1.0
                arr.markers.append(m)
            else:
                # Toparlanma: eski ok RViz'de kalmasin (DELETE aksiyonu) —
                # aksi halde kayma bitse bile ok ekranda asili kalir
                d = Marker()
                d.header.frame_id = "map"
                d.header.stamp = now.to_msg()
                d.ns = "slip_arrow"
                d.id = 0
                d.action = Marker.DELETE
                arr.markers.append(d)
        t = Marker()
        t.header.frame_id = "map"
        t.header.stamp = now.to_msg()
        t.ns = "slip_text"
        t.id = 1
        t.type = Marker.TEXT_VIEW_FACING
        t.action = Marker.ADD
        t.pose.position.x = true_pose.position.x
        t.pose.position.y = true_pose.position.y
        t.pose.position.z = 0.75
        t.scale.z = 0.18
        t.color.r = 1.0
        t.color.g = 0.85
        t.color.b = 0.2
        t.color.a = 1.0
        t.text = "SLIP %.2f m" % gap if gap is not None else "SLIP ?"
        arr.markers.append(t)
        # Bulut/durum loglamasi: controller_node durum satirlari robotun
        # uzerinde renk kodlu TEXT marker olarak basilir (demo videosu icin):
        #   MODE=SAFE -> kirmizi (bulut bekleniyor, yavaslama)
        #   YAMA      -> sari (yama geldi: kazanc + model + gecikme + teshis)
        #   MODE=OK   -> yesil (yorunge takibi)
        if self._status_text:
            s = Marker()
            s.header.frame_id = "map"
            s.header.stamp = now.to_msg()
            s.ns = "status_text"
            s.id = 2
            s.type = Marker.TEXT_VIEW_FACING
            s.action = Marker.ADD
            s.pose.position.x = true_pose.position.x
            s.pose.position.y = true_pose.position.y
            s.pose.position.z = 1.00
            s.scale.z = 0.16
            txt = self._status_text
            if txt.startswith("MODE=SAFE"):
                s.color.r, s.color.g, s.color.b = 1.0, 0.15, 0.10
            elif txt.startswith("MODE=ESCALATED"):
                s.color.r, s.color.g, s.color.b = 1.0, 0.45, 0.05
            elif txt.startswith("MODE=PATCH"):
                s.color.r, s.color.g, s.color.b = 1.0, 0.85, 0.20
            else:
                s.color.r, s.color.g, s.color.b = 0.20, 1.0, 0.30
            s.color.a = 1.0
            s.text = txt
            arr.markers.append(s)
        # Bulut/Tavily satiri (camgobek): durum yazisinin ustunde —
        # "BULUT[model] TAVILY : hava ozeti" yama geldiginde ekranda belirir
        if self._cloud_text:
            c = Marker()
            c.header.frame_id = "map"
            c.header.stamp = now.to_msg()
            c.ns = "cloud_text"
            c.id = 3
            c.type = Marker.TEXT_VIEW_FACING
            c.action = Marker.ADD
            c.pose.position.x = true_pose.position.x
            c.pose.position.y = true_pose.position.y
            c.pose.position.z = 1.50
            c.scale.z = 0.15
            c.color.r = 0.35
            c.color.g = 0.85
            c.color.b = 1.0
            c.color.a = 1.0
            c.text = self._cloud_text
            arr.markers.append(c)
        self.slip_pub.publish(arr)
        now_s = now.nanoseconds * 1e-9
        if gap is not None and now_s - self._last_gaplog_t >= 5.0:
            self._last_gaplog_t = now_s
            self.get_logger().info(
                "SLIP_GAP=%.3f m (odom_corrected vs truth) %s" % (
                    gap, "SLIPPING" if gap > 0.05 else "normal"))


def main(args=None):
    rclpy.init(args=args)
    node = GzTruthNode()
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
