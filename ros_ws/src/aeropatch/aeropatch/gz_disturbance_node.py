"""gz_disturbance_node: 'yagmur -> kaygan zemin' kaymasini Gazebo'da fiziksel uygular.

Arayuz sim demo ile AYNI: /inject_disturbance (aeropatch_msgs/srv/InjectDisturbance)
Eylem: gazebo_ros_state set_entity_state ile rampali yan kayma (slip).
  - traction ortalamasi dustukce kayma buyur: shove_scale * (1 - ort_traction)
  - asimetrik traction -> yon sapmasi (yaw kick)
Kritik: diff_drive odometrisi bu kaymayi GOREMEZ (encoder tabanli) ->
monitor komut-olcum uyumsuzlugu + CTE sicramasi ile alarm uretir.
"""
from __future__ import annotations

import math

import rclpy
from aeropatch_msgs.srv import InjectDisturbance
from gazebo_msgs.srv import GetEntityState, SetEntityState
from rclpy.callback_groups import MutuallyExclusiveCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node


class GzDisturbanceNode(Node):
    def __init__(self):
        super().__init__("gz_disturbance_node")
        self.declare_parameters("", [
            ("entity_name", "aerobot"),
            ("get_service", "/gazebo/get_entity_state"),
            ("set_service", "/gazebo/set_entity_state"),
            ("get_service_fallback", "/demo/get_entity_state"),
            ("set_service_fallback", "/demo/set_entity_state"),
            ("shove_scale", 1.0),    # traction=0.25 -> 38 cm yan kayma
            ("yaw_kick", 0.30),      # tam asimetri -> 0.3 rad yon sapmasi
            ("shove_period", 0.05),
        ])
        self.entity = str(self.get_parameter("entity_name").value)
        self.shove_scale = float(self.get_parameter("shove_scale").value)
        self.yaw_kick = float(self.get_parameter("yaw_kick").value)
        period = float(self.get_parameter("shove_period").value)

        # GRUPLAR ONCE OLUSUR -> create_client'a PARAMETRE olarak verilir.
        # (Client yaratiktan SONRA client.callback_group atamak rclpy
        #  executor assertion crash yaratir.)
        self.cb_timer = MutuallyExclusiveCallbackGroup()
        self.cb_srv = MutuallyExclusiveCallbackGroup()
        self.cb_cli = MutuallyExclusiveCallbackGroup()

        gsrv = str(self.get_parameter("get_service").value)
        ssrv = str(self.get_parameter("set_service").value)
        gfb = str(self.get_parameter("get_service_fallback").value)
        sfb = str(self.get_parameter("set_service_fallback").value)
        self.get_cli = self.create_client(GetEntityState, gsrv,
                                          callback_group=self.cb_cli)
        self.set_cli = self.create_client(SetEntityState, ssrv,
                                          callback_group=self.cb_cli)
        self.get_cli_fb = self.create_client(GetEntityState, gfb,
                                             callback_group=self.cb_cli)
        self.set_cli_fb = self.create_client(SetEntityState, sfb,
                                             callback_group=self.cb_cli)
        if not self.get_cli.wait_for_service(timeout_sec=10.0):
            self.get_logger().info(
                f"{gsrv} henuz yok (Gazebo aciliyor?), fallback: {gfb}")

        self.srv = self.create_service(InjectDisturbance, "/inject_disturbance",
                                       self._handle, callback_group=self.cb_srv)
        self.slide = None
        self.timer = self.create_timer(period, self._slide_tick,
                                       callback_group=self.cb_timer)
        self.get_logger().info(
            "gz_disturbance_node ready -> /inject_disturbance "
            "(Gazebo fiziksel kayma, odometri yaniltici)")

    @staticmethod
    def _yaw(pose) -> float:
        q = pose.orientation
        return math.atan2(2.0 * (q.w * q.z + q.x * q.y),
                          1.0 - 2.0 * (q.y * q.y + q.z * q.z))

    def _pick_clients(self):
        """Hazir (get,set) istemci ciftini dondurur; hicbiri yoksa (None, None)."""
        if (self.get_cli.service_is_ready()
                and self.set_cli.service_is_ready()):
            return self.get_cli, self.set_cli
        if (self.get_cli_fb.service_is_ready()
                and self.set_cli_fb.service_is_ready()):
            return self.get_cli_fb, self.set_cli_fb
        return None, None

    def _get_state(self, get_cli):
        req = GetEntityState.Request()
        req.name = self.entity
        req.reference_frame = "world"
        resp = get_cli.call(req)
        if resp is None or not resp.success:
            return None
        return resp.state

    def _handle(self, req, resp):
        get_cli, set_cli = self._pick_clients()
        if get_cli is None:
            resp.success = False
            resp.message = "Gazebo state servisi hazir degil"
            return resp
        st = self._get_state(get_cli)
        if st is None:
            resp.success = False
            resp.message = f"entity '{self.entity}' bulunamadi (spawn oldu mu?)"
            self.get_logger().error(resp.message)
            return resp
        tl = max(0.0, min(1.0, float(req.traction_left)))
        tr = max(0.0, min(1.0, float(req.traction_right)))
        ramp = max(0.2, min(10.0, float(req.ramp_time)))
        slip = 1.0 - (tl + tr) / 2.0
        total_lat = slip * self.shove_scale
        total_yaw = (tr - tl) * self.yaw_kick
        yaw0 = self._yaw(st.pose)
        # birim yan yon (robotun sagi): cos/sin ile (sola kayma negatif)
        lat_dir = (-math.sin(yaw0), math.cos(yaw0))
        self.slide = {
            "t0": self.get_clock().now().nanoseconds * 1e-9,
            "dur": ramp,
            "dx_total": total_lat,
            "lat_dir": lat_dir,
            "dth_total": total_yaw,
            "prev_ease": 0.0,
        }
        resp.success = True
        resp.message = (f"RAIN SLIDE: yan={total_lat * 100:.0f}cm "
                        f"yaw={math.degrees(total_yaw):.0f}deg "
                        f"sure={ramp:.1f}s (odometri gormez!)")
        self.get_logger().warn(resp.message)
        return resp

    def _slide_tick(self):
        s = self.slide
        if s is None:
            return
        get_cli, set_cli = self._pick_clients()
        if get_cli is None:
            return
        cur = self._get_state(get_cli)
        if cur is None:
            return
        now = self.get_clock().now().nanoseconds * 1e-9
        frac = min(1.0, (now - s["t0"]) / s["dur"])
        ease = frac * frac * (3.0 - 2.0 * frac)      # smoothstep ramp
        de = ease - s["prev_ease"]                   # bu tikin artisi
        if de <= 0.0 and frac < 1.0:
            return
        s["prev_ease"] = ease

        # ARTIMLI kayma: robotun kendi surusunu KORUR, ustune kucuk nudge ekler.
        # (Mutlak x0+hedef her tikte surusu geri iter -> kontrolcuyle bogusur.)
        yaw = self._yaw(cur.pose)
        lat_d = s["lat_dir"]                          # (dx, dy) birim yan yon
        nx = cur.pose.position.x + (s["dx_total"] * de) * lat_d[0]
        ny = cur.pose.position.y + (s["dx_total"] * de) * lat_d[1]
        nth = yaw + s["dth_total"] * de
        req = SetEntityState.Request()
        req.state.name = self.entity
        req.state.reference_frame = "world"
        req.state.pose.position.x = nx
        req.state.pose.position.y = ny
        req.state.pose.position.z = cur.pose.position.z
        req.state.pose.orientation.z = math.sin(nth / 2.0)
        req.state.pose.orientation.w = math.cos(nth / 2.0)
        req.state.twist = cur.twist  # hizi koru: kayarken ilerlemeye devam
        set_cli.call(req)
        if frac >= 1.0:
            self.slide = None
            self.get_logger().warn(
                "RAIN SLIDE tamamlandi -> odometri sapmasi birikti, "
                "monitor alarm uretmeli")


def main(args=None):
    rclpy.init(args=args)
    node = GzDisturbanceNode()
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
