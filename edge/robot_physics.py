"""Diferansiyel sürüş robot fiziği — teker kayması (slip) ve motor gecikmesi dahil.

Ölçüm modeli (jüri anlatısının kalbi):
  * Encoder'lar (odometri) MOTOR hızını okur -> kaymayı göremez.
  * Zemin temas hızları 'traction' katsayısıyla ölçeklenir (yağmur -> düşük traction).
  * 'Ground truth', harici lokalizasyonu (GPS/AMCL) temsil eder.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from edge.pid import clamp


def wrap_angle(a: float) -> float:
    return (a + math.pi) % (2.0 * math.pi) - math.pi


@dataclass
class DiffDriveState:
    x: float = 0.0
    y: float = 0.0
    theta: float = 0.0
    x_odom: float = 0.0
    y_odom: float = 0.0
    theta_odom: float = 0.0
    v_true: float = 0.0
    omega_true: float = 0.0
    v_odom: float = 0.0
    omega_odom: float = 0.0
    wheel_left: float = 0.0
    wheel_right: float = 0.0
    traction_left: float = 1.0
    traction_right: float = 1.0
    time: float = 0.0


class DiffDriveRobot:
    def __init__(self, track_width=0.16, wheel_radius=0.033, motor_tau=0.12,
                 v_limit=0.22, omega_limit=2.84, max_wheel_speed=12.0):
        self.W = float(track_width)
        self.r = float(wheel_radius)
        self.tau = max(float(motor_tau), 1e-3)
        self.v_limit = float(v_limit)
        self.omega_limit = float(omega_limit)
        self.max_wheel_speed = float(max_wheel_speed)
        self._v_cmd = 0.0
        self._omega_cmd = 0.0
        self._wl = 0.0
        self._wr = 0.0
        self._tr_l = 1.0
        self._tr_r = 1.0
        self._tr_l_target = 1.0
        self._tr_r_target = 1.0
        self._tr_ramp = 1.0
        self.state = DiffDriveState()

    def set_cmd(self, v: float, omega: float) -> None:
        self._v_cmd = clamp(float(v), -self.v_limit, self.v_limit)
        self._omega_cmd = clamp(float(omega), -self.omega_limit, self.omega_limit)

    def set_traction(self, left: float, right: float, ramp_time: float = 1.0) -> None:
        """Zemin tutuşunu ayarlar (1.0 = kuru zemin, 0.0 = tam kayma)."""
        self._tr_l_target = clamp(float(left), 0.0, 1.0)
        self._tr_r_target = clamp(float(right), 0.0, 1.0)
        self._tr_ramp = max(float(ramp_time), 1e-3)

    def reset_odometry_to_truth(self) -> None:
        """Lokalizasyon düzeltmesi: DR pozu harici ölçüme senkronlanır."""
        s = self.state
        s.x_odom, s.y_odom, s.theta_odom = s.x, s.y, s.theta

    def _wheel_cmds(self):
        wl = (self._v_cmd - self._omega_cmd * self.W / 2.0) / self.r
        wr = (self._v_cmd + self._omega_cmd * self.W / 2.0) / self.r
        m = max(abs(wl), abs(wr))
        if m > self.max_wheel_speed:
            wl *= self.max_wheel_speed / m
            wr *= self.max_wheel_speed / m
        return wl, wr

    def step(self, dt: float) -> DiffDriveState:
        dt = max(float(dt), 1e-4)
        s = self.state
        s.time += dt
        # Traction rampası (yağmur aniden değil, kademeli kayganlaştırır)
        a = clamp(dt / self._tr_ramp, 0.0, 1.0)
        self._tr_l += (self._tr_l_target - self._tr_l) * a
        self._tr_r += (self._tr_r_target - self._tr_r) * a
        # Motor cevabı: birinci mertebe gecikme
        b = clamp(dt / self.tau, 0.0, 1.0)
        wl_cmd, wr_cmd = self._wheel_cmds()
        self._wl += (wl_cmd - self._wl) * b
        self._wr += (wr_cmd - self._wr) * b
        # Zemin hızları (slip) ve odometri (encoder motor hızını okur)
        wl_g = self._wl * self._tr_l
        wr_g = self._wr * self._tr_r
        v_true = (wl_g + wr_g) * self.r / 2.0
        omega_true = (wr_g - wl_g) * self.r / self.W
        v_odom = (self._wl + self._wr) * self.r / 2.0
        omega_odom = (self._wr - self._wl) * self.r / self.W
        # Gerçek pozisyon
        s.theta = wrap_angle(s.theta + omega_true * dt)
        s.x += v_true * math.cos(s.theta) * dt
        s.y += v_true * math.sin(s.theta) * dt
        # Odometri dead-reckoning (slip'ten habersiz entegre eder)
        s.theta_odom = wrap_angle(s.theta_odom + omega_odom * dt)
        s.x_odom += v_odom * math.cos(s.theta_odom) * dt
        s.y_odom += v_odom * math.sin(s.theta_odom) * dt
        s.v_true = v_true
        s.omega_true = omega_true
        s.v_odom = v_odom
        s.omega_odom = omega_odom
        s.wheel_left = self._wl
        s.wheel_right = self._wr
        s.traction_left = self._tr_l
        s.traction_right = self._tr_r
        return s
