"""AeroPatch veri şemaları (edge <-> cloud sözleşmesi).

Aynı şemayı kenar tarafı, mock bulut ve gerçek Nebius handler paylaştırır.
"""
from __future__ import annotations

import time as _time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List


def new_event_id(prefix: str = "evt") -> str:
    return f"{prefix}-{int(_time.time() * 1000)}"


@dataclass
class TelemetrySample:
    """Tek telemetri karesi (50-100 Hz'de üretilir)."""
    t: float = 0.0
    x: float = 0.0
    y: float = 0.0
    theta: float = 0.0
    x_odom: float = 0.0
    y_odom: float = 0.0
    theta_odom: float = 0.0
    v_odom: float = 0.0
    omega_odom: float = 0.0
    v_true: float = 0.0
    omega_true: float = 0.0
    cte: float = 0.0
    heading_error: float = 0.0
    anomaly_score: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TelemetryPacket:
    """Anomali anında buluta fırlatılan paket."""
    robot_id: str = "aeropatch-01"
    event_id: str = ""
    trigger: str = "physical_deviation"
    score: float = 0.0
    created_at: float = 0.0
    region: str = ""
    mission: str = "perimeter_patrol"
    pose: Dict[str, float] = field(default_factory=dict)
    current_gains: Dict[str, float] = field(default_factory=dict)
    telemetry: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class PatchResponse:
    """Bulut ajanından (Nemotron + Tavily) dönen yama."""
    event_id: str = ""
    diagnosis: str = ""
    weather_summary: str = ""
    weather_source: str = ""
    patch: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0
    latency_ms: float = 0.0

    @classmethod
    def from_dict(cls, data: Dict[str, Any], latency_ms: float = 0.0) -> "PatchResponse":
        patch = data.get("patch") or {}
        if not isinstance(patch, dict):
            patch = {}
        # ÜST SEVİYEDEKİ ALANLARI PATCH'E TAŞI (düşme noktası düzeltmesi):
        # handler odom_resync'i (resync garantisi) ve model'i ÜST seviyede
        # döndürüyor; bridge msg'i patch'ten okuyor — aksi halde DÜŞÜYORDU
        # (log kanıtı: NIM yamalarında resync=HAYIR + BULUT[?], monitor resync
        # atlıyor, sonsuz alarm döngüsü). Bu düşme NIM/fallback'ten bağımsız —
        # iki yol da from_dict'ten geçer (cloud_bridge.py), dolayısıyla
        # düzeltme ikisini de kapsar.
        if "odom_resync" in data and "odom_resync" not in patch:
            patch["odom_resync"] = data["odom_resync"]
        if data.get("model") and "model" not in patch:
            patch["model"] = data["model"]
        return cls(
            event_id=str(data.get("event_id", "")),
            diagnosis=str(data.get("diagnosis", "")),
            weather_summary=str(data.get("weather_summary", "")),
            weather_source=str(data.get("weather_source", "")),
            patch=patch,
            confidence=float(data.get("confidence", 0.0)),
            latency_ms=float(data.get("latency_ms", latency_ms) or latency_ms),
        )
