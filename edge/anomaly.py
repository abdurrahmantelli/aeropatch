"""Kenar anomali algılayıcı — saf matematik, LLM gerektirmez.

Skor bileşenleri (sadeleştirilmiş Kalman innovation mantığı):
  * hız uyuşmazlığı |v_odom - v_true| -> teker kayması imzası
  * dönüş uyuşmazlığı |omega_odom - omega_true|
  * pozisyon uyuşmazlığı (harici lokalizasyon vs odometri dead-reckoning)
  * yörünge sapması (CTE) ve başlık hatası
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

from edge.pid import clamp
from edge.robot_physics import wrap_angle
from edge.telemetry import TelemetrySample, new_event_id


@dataclass
class AnomalyConfig:
    threshold: float = 0.60
    persistence: int = 5            # ardışık örnek sayısı (50 Hz'de ~100 ms)
    cooldown_s: float = 4.0
    w_v: float = 0.40
    v_scale: float = 0.06           # 6 cm/s fark -> 1.0 normalize
    w_omega: float = 0.30
    omega_scale: float = 0.30       # 0.30 rad/s fark -> 1.0
    w_pos: float = 0.30
    pos_scale: float = 0.25         # 25 cm DR kayması -> 1.0
    w_cte: float = 0.15
    cte_scale: float = 0.35
    w_head: float = 0.10
    head_scale: float = 0.60


@dataclass
class AnomalyVerdict:
    score: float = 0.0
    alarm: bool = False
    event_id: Optional[str] = None
    components: dict = field(default_factory=dict)


class AnomalyDetector:
    def __init__(self, config: Optional[AnomalyConfig] = None):
        self.cfg = config or AnomalyConfig()
        self._above = 0
        self._cooldown_until = -math.inf
        self.last_score = 0.0
        self.last_components: dict = {}

    def update(self, s: TelemetrySample, t: float) -> AnomalyVerdict:
        c = self.cfg
        dv = abs(s.v_odom - s.v_true)
        dw = abs(wrap_angle(s.omega_odom - s.omega_true))
        dpos = math.hypot(s.x - s.x_odom, s.y - s.y_odom)
        components = {
            "speed_mismatch": min(dv / c.v_scale, 1.5),
            "omega_mismatch": min(dw / c.omega_scale, 1.5),
            "pos_mismatch": min(dpos / c.pos_scale, 1.5),
            "cte": min(abs(s.cte) / c.cte_scale, 1.5),
            "heading": min(abs(wrap_angle(s.heading_error)) / c.head_scale, 1.5),
        }
        score = (c.w_v * components["speed_mismatch"]
                 + c.w_omega * components["omega_mismatch"]
                 + c.w_pos * components["pos_mismatch"]
                 + c.w_cte * components["cte"]
                 + c.w_head * components["heading"])
        self.last_score = score
        self.last_components = components

        if t < self._cooldown_until:            # bekleme süresi: yeni alarm yok
            self._above = 0
            return AnomalyVerdict(score, False, None, components)

        if score >= c.threshold:
            self._above += 1
        else:
            self._above = 0

        if self._above >= c.persistence:
            event_id = new_event_id()
            self._cooldown_until = t + c.cooldown_s
            self._above = 0
            return AnomalyVerdict(score, True, event_id, components)
        return AnomalyVerdict(score, False, None, components)

    def hold(self, t: float, seconds: float) -> None:
        """Yama sonrasi 'yerlesme' süresi: yeni alarmlari baskılar.

        Skorlamaya devam edilir (izleme için), ama alarm üretilmez -
        klasik fault-management hold-off deseni.
        """
        self._cooldown_until = max(self._cooldown_until, t + seconds)
        self._above = 0


def score_of(sample: TelemetrySample, cfg: Optional[AnomalyConfig] = None) -> float:
    """Yardımcı: tek örnek için skoru döndürür (test/günlük için)."""
    return AnomalyDetector(cfg).update(sample, 0.0).score
