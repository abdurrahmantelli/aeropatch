"""gz_viz_node: Yorunge ve izleri GAZEBO SAHNESININ icine cizer.

RViz'e gerek kalmaz — gzclient penceresinde gorunur:
  - yesil diskler  : hedef yorunge (controller'in 12 hedef noktasi)
  - kirmizi kureler: robotun GERCEK izi (/ground_truth)
  - mavi kureler   : odometrinin iddia ettigi iz (/odom) — kayma aninda
                     kirmizidan ayrilir (encoder yanilsamasi!)
Teknik: 'breadcrumb' numarasi — visual-only static modeller once zamanin
altina (z=-10) dogurulur, sonra SetEntityState ile tek tek yol uzerine
islenir. Fizik maliyeti sifir (collision yok, robot uzerinden gecebilir).
"""
from __future__ import annotations

import rclpy
from gazebo_msgs.srv import SetEntityState, SpawnEntity
from geometry_msgs.msg import Pose, PoseStamped
from nav_msgs.msg import Odometry
from rclpy.callback_groups import MutuallyExclusiveCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node

from aeropatch.edge_loader import ensure_edge_modules

ensure_edge_modules()

from edge.path_follower import circular_waypoints  # noqa: E402

WP_R, WP_H = 0.07, 0.015     # hedef diski
BC_R = 0.06                  # breadcrumb kure yariapapi (net gorunur)
N_BC = 30                    # her iz icin kure sayisi (sonra recycle)
HIDDEN_Z = -10.0

PUCK_SDF = """<?xml version="1.0"?>
<sdf version="1.6">
  <model name="{name}">
    <static>true</static>
    <pose>{x} {y} {z} 0 0 0</pose>
    <link name="link">
      <visual name="v">
        <geometry><cylinder><radius>{r}</radius><length>{h}</length></cylinder></geometry>
        <material><ambient>{cr} {cg} {cb} 1</ambient><diffuse>{cr} {cg} {cb} 1</diffuse></material>
      </visual>
    </link>
  </model>
</sdf>"""

BALL_SDF = """<?xml version="1.0"?>
<sdf version="1.6">
  <model name="{name}">
    <static>true</static>
    <pose>{x} {y} {z} 0 0 0</pose>
    <link name="link">
      <visual name="v">
        <geometry><sphere><radius>{r}</radius></sphere></geometry>
        <material><ambient>{cr} {cg} {cb} 1</ambient><diffuse>{cr} {cg} {cb} 1</diffuse></material>
      </visual>
    </link>
  </model>
</sdf>"""

GREEN = (0.1, 0.85, 0.15)
RED = (1.0, 0.12, 0.10)
BLUE = (0.10, 0.35, 1.0)


class GzVizNode(Node):
    def __init__(self):
        super().__init__("gz_viz_node")
        self.declare_parameters("", [
            ("set_service", "/gazebo/set_entity_state"),
            ("set_service_fallback", "/demo/set_entity_state"),
            ("spawn_service", "/spawn_entity"),
            ("crumb_period", 0.5),
        ])
        self.cb_cli = MutuallyExclusiveCallbackGroup()
        self.cb_sub = MutuallyExclusiveCallbackGroup()
        self.cb_timer = MutuallyExclusiveCallbackGroup()

        ssrv = str(self.get_parameter("set_service").value)
        sfb = str(self.get_parameter("set_service_fallback").value)
        self.set_cli = self.create_client(SetEntityState, ssrv,
                                          callback_group=self.cb_cli)
        self.set_cli_fb = self.create_client(SetEntityState, sfb,
                                             callback_group=self.cb_cli)
        self.spawn_cli = self.create_client(
            SpawnEntity, str(self.get_parameter("spawn_service").value),
            callback_group=self.cb_cli)
        if not self.spawn_cli.wait_for_service(timeout_sec=10.0):
            self.get_logger().warn("waiting for spawn_entity service (gzserver?)")

        self.gt_sub = self.create_subscription(
            PoseStamped, "/ground_truth", self._on_gt, 10,
            callback_group=self.cb_sub)
        self.odom_sub = self.create_subscription(
            Odometry, "/odom", self._on_odom, 10,
            callback_group=self.cb_sub)
        self.gt_pose = None
        self.odom_pose = None
        self.i_t = 0
        self.i_o = 0

        self.decor_done = False
        self.decor_timer = self.create_timer(1.0, self._try_decor,
                                             callback_group=self.cb_timer)
        period = float(self.get_parameter("crumb_period").value)
        self.crumb_timer = self.create_timer(period, self._drop_crumbs,
                                             callback_group=self.cb_timer)
        self.get_logger().info(
            "gz_viz_node ready (yesil=hedef, kirmizi=gercek, mavi=odometri)")

    def _spawn(self, name: str, xml: str, pose: Pose):
        req = SpawnEntity.Request()
        req.name = name
        req.xml = xml
        req.initial_pose = pose
        req.robot_namespace = ""
        resp = self.spawn_cli.call(req)
        if resp is None or not resp.success:
            msg = resp.status_message if resp is not None else "no response"
            self.get_logger().warn(f"spawn failed: {name} ({msg})")

    def _hidden_pose(self) -> Pose:
        p = Pose()
        p.position.z = HIDDEN_Z
        return p

    def _try_decor(self):
        """Sahne dekorunu bir kez kur: hedef diski + gizli breadcrumb havuzu."""
        if self.decor_done or not self.spawn_cli.service_is_ready():
            return
        self.decor_done = True
        self.decor_timer.cancel()
        # controller_node ile AYNI elips (cx=2.2 cy=0 rx=2.2 ry=1.5 n=36) —
        # eski elips (cy=2.2) kalmisti -> yesil diskler yanlis yerdeydi,
        # robot baska elips uzerinde kostu
        wps = circular_waypoints(cx=2.2, cy=0.0, rx=2.2, ry=1.5, n=36)
        for i, (x, y) in enumerate(wps):
            xml = PUCK_SDF.format(name=f"aero_wp_{i:02d}", x=x, y=y,
                                  z=WP_H / 2.0, r=WP_R, h=WP_H,
                                  cr=GREEN[0], cg=GREEN[1], cb=GREEN[2])
            self._spawn(f"aero_wp_{i:02d}", xml, Pose())
        for i in range(N_BC):
            xml = BALL_SDF.format(name=f"aero_bc_t_{i:02d}", x=0.0, y=0.0,
                                  z=HIDDEN_Z, r=BC_R,
                                  cr=RED[0], cg=RED[1], cb=RED[2])
            self._spawn(f"aero_bc_t_{i:02d}", xml, self._hidden_pose())
            xml = BALL_SDF.format(name=f"aero_bc_o_{i:02d}", x=0.0, y=0.0,
                                  z=HIDDEN_Z, r=BC_R,
                                  cr=BLUE[0], cg=BLUE[1], cb=BLUE[2])
            self._spawn(f"aero_bc_o_{i:02d}", xml, self._hidden_pose())
        self.get_logger().info(
            f"scene decor built: {len(wps)} waypoints + {2 * N_BC} breadcrumbs")

    def _on_gt(self, msg: PoseStamped):
        self.gt_pose = msg.pose

    def _on_odom(self, msg: Odometry):
        self.odom_pose = msg.pose.pose

    def _teleport(self, name: str, pose: Pose):
        cli = None
        if self.set_cli.service_is_ready():
            cli = self.set_cli
        elif self.set_cli_fb.service_is_ready():
            cli = self.set_cli_fb
        if cli is None:
            return
        req = SetEntityState.Request()
        req.state.name = name
        req.state.reference_frame = "world"
        req.state.pose = pose
        cli.call(req)

    def _drop_crumbs(self):
        if not self.decor_done:
            return
        if self.gt_pose is not None:
            p = Pose()
            p.position.x = self.gt_pose.position.x
            p.position.y = self.gt_pose.position.y
            p.position.z = BC_R
            self._teleport(f"aero_bc_t_{self.i_t:02d}", p)
            self.i_t = (self.i_t + 1) % N_BC
        if self.odom_pose is not None:
            p = Pose()
            p.position.x = self.odom_pose.position.x
            p.position.y = self.odom_pose.position.y
            p.position.z = BC_R
            self._teleport(f"aero_bc_o_{self.i_o:02d}", p)
            self.i_o = (self.i_o + 1) % N_BC


def main(args=None):
    rclpy.init(args=args)
    node = GzVizNode()
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

