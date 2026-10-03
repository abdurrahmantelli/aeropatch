"""Yörünge takip denetleyicisi — bulut yaması kazançlarını sıcak uygular.

Kontrol, harici lokalizasyon (ground truth) pozisyonuyla yapılır;
odometri yalnızca hız ölçümü ve anomali karşılaştırması içindir.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

from edge.pid import PID, clamp
from edge.robot_physics import wrap_angle


def circular_waypoints(cx: float = 1.0, cy: float = 2.2, rx: float = 2.2,
                       ry: float = 1.5, n: int = 12,
                       start: Optional[Tuple[float, float]] = None,
                       phase: float = 0.0) -> List[Tuple[float, float]]:
    """Kapali elips devriyesi. phase: ilk waypoint'in acisi (radyan).
    Roborun spawn konumu/yonu ile hizalamak icin kullanilir — robot
    yorunge UZERINDE baslarsa pure-pursuit baslangicta duz cizgi cizmez."""
    pts: List[Tuple[float, float]] = []
    if start is not None:
        pts.append((float(start[0]), float(start[1])))
    for i in range(n):
        a = phase + 2.0 * math.pi * i / n
        pts.append((cx + rx * math.cos(a), cy + ry * math.sin(a)))
    return pts


class WaypointPath:
    """Kapalı devriye turu: sona gelince başa döner."""

    def __init__(self, waypoints: Sequence[Tuple[float, float]], goal_radius: float = 0.30):
        self.wps = [(float(p[0]), float(p[1])) for p in waypoints]
        self.goal_radius = float(goal_radius)
        self._idx = 0

    def current_target(self, x: float, y: float) -> Tuple[float, float]:
        while True:
            tx, ty = self.wps[self._idx]
            if math.hypot(tx - x, ty - y) <= self.goal_radius:
                self._idx = (self._idx + 1) % len(self.wps)
                continue
            break
        return self.wps[self._idx]

    @property
    def waypoints(self) -> List[Tuple[float, float]]:
        return list(self.wps)


def cross_track_error(x: float, y: float, wps: List[Tuple[float, float]]) -> float:
    """Noktanın yörüngeye (tüm segmentlere) en kısa mesafesi."""
    best = float("inf")
    n = len(wps)
    if n < 2:
        return 0.0
    for i in range(n):
        ax, ay = wps[i]
        bx, by = wps[(i + 1) % n]
        abx, aby = bx - ax, by - ay
        l2 = abx * abx + aby * aby
        if l2 < 1e-9:
            d = math.hypot(x - ax, y - ay)
        else:
            t = clamp(((x - ax) * abx + (y - ay) * aby) / l2, 0.0, 1.0)
            d = math.hypot(x - (ax + t * abx), y - (ay + t * aby))
        best = min(best, d)
    return best


@dataclass
class FollowerParams:
    kp: float = 2.2
    ki: float = 0.0
    kd: float = 0.08
    kp_max: float = 6.0
    kd_max: float = 1.0
    max_speed: float = 0.22
    goal_radius: float = 0.30
    omega_limit: float = 2.84


class PathFollower:
    def __init__(self, path: WaypointPath, params: Optional[FollowerParams] = None):
        self.params = params or FollowerParams()
        self.path = path
        p = self.params
        self.heading_pid = PID(p.kp, p.ki, p.kd,
                              out_min=-p.omega_limit, out_max=p.omega_limit,
                              int_limit=0.6)
        self.slip_comp = 0.0
        self.max_speed = p.max_speed
        self._base_max_speed = p.max_speed
        self._safe_mode = False

    def compute_cmd(self, x: float, y: float, theta: float, dt: float):
        tx, ty = self.path.current_target(x, y)
        bearing = math.atan2(ty - y, tx - x)
        heading_error = wrap_angle(bearing - theta)
        u = self.heading_pid.update(heading_error, dt)
        omega_cmd = clamp(u + self.slip_comp,
                          -self.params.omega_limit, self.params.omega_limit)
        dist = math.hypot(tx - x, ty - y)
        speed_factor = clamp(math.cos(heading_error), 0.0, 1.0)
        slow = 0.5 if dist < self.params.goal_radius * 2.0 else 1.0
        v_ceiling = self.max_speed * (0.35 if self._safe_mode else 1.0)
        v_cmd = clamp(v_ceiling * speed_factor * slow, 0.0, self._base_max_speed)
        return v_cmd, omega_cmd, tx, ty, heading_error

    def set_safe_mode(self, on: bool) -> None:
        """Alarm->yama arası: hız tavanı %35'e düşer (bulut 'hold_line' modu)."""
        self._safe_mode = bool(on)

    @property
    def safe_mode(self) -> bool:
        return self._safe_mode

    @property
    def gains(self) -> dict:
        g = self.heading_pid.gains
        g.update({"slip_compensation": self.slip_comp,
                  "max_speed": self.max_speed})
        return g

    def apply_patch(self, patch: dict) -> None:
        """Bulut yamasını sıcak uygula (PID integrali korunur)."""
        hp = patch.get("heading_pid") or {}
        kp = float(hp.get("kp", self.heading_pid.kp))
        kd = float(hp.get("kd", self.heading_pid.kd))
        self.heading_pid.set_gains(
            kp=clamp(kp, 0.0, self.params.kp_max),
            ki=float(hp.get("ki", self.heading_pid.ki)),
            kd=clamp(kd, 0.0, self.params.kd_max))
        if patch.get("slip_compensation") is not None:
            self.slip_comp = clamp(float(patch["slip_compensation"]), -1.5, 1.5)
        if patch.get("max_speed") is not None:
            self.max_speed = clamp(float(patch["max_speed"]),
                                   0.02, self._base_max_speed)
