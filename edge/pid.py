"""Ayarlanabilir (hot-swap) PID denetleyicisi — anti-windup destekli.

Buluttan gelen yama kazançları sıcak olarak bu sınıfa uygulanir;
integral durumu korunur, böylece robotta kontrol sürekliliği bozulmaz.
"""
from __future__ import annotations

from typing import Optional


def clamp(v: float, lo: Optional[float], hi: Optional[float]) -> float:
    if lo is not None and v < lo:
        return lo
    if hi is not None and v > hi:
        return hi
    return v


class PID:
    def __init__(self, kp=1.0, ki=0.0, kd=0.0,
                 out_min: Optional[float] = None,
                 out_max: Optional[float] = None,
                 int_limit: Optional[float] = None):
        self.kp = float(kp)
        self.ki = float(ki)
        self.kd = float(kd)
        self.out_min = out_min
        self.out_max = out_max
        self.int_limit = float(int_limit) if int_limit is not None else None
        self.integral = 0.0
        self._prev_error: Optional[float] = None
        self._d_filtered = 0.0

    # --- hot-swap API (bulut yaması buraya dokunur) ---
    def set_gains(self, kp=None, ki=None, kd=None) -> None:
        if kp is not None:
            self.kp = float(kp)
        if ki is not None:
            self.ki = float(ki)
        if kd is not None:
            self.kd = float(kd)

    @property
    def gains(self) -> dict:
        return {"kp": self.kp, "ki": self.ki, "kd": self.kd}

    def reset(self) -> None:
        self.integral = 0.0
        self._prev_error = None
        self._d_filtered = 0.0

    def _limit(self, u: float) -> float:
        return clamp(u, self.out_min, self.out_max)

    def update(self, error: float, dt: float) -> float:
        if dt <= 0.0:
            return self._limit(self.kp * error)
        # Türev: hafif low-pass filtreli (tümsecim gürültüsüne dayanıklı)
        d_raw = 0.0 if self._prev_error is None else (error - self._prev_error) / dt
        self._d_filtered += 0.3 * (d_raw - self._d_filtered)
        self._prev_error = error
        # Integral: koşullu birikim (anti-windup) + clamp
        candidate = self.integral + self.ki * error * dt
        if self.int_limit is not None:
            candidate = clamp(candidate, -self.int_limit, self.int_limit)
        u = self.kp * error + candidate + self.kd * self._d_filtered
        u_limited = self._limit(u)
        if abs(u_limited - u) <= 1e-12:  # doyma yok -> integral kabul edilir
            self.integral = candidate
        return u_limited
