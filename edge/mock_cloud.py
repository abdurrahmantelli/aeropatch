"""Bulut ajanı simülatörü (Nemotron + Tavily davranış taklidi).

Gerçek Nebius endpoint'i ile AYNI JSON sözleşmesini döndürür; böylece
`CloudBridge(mock=True -> False)` tek satırla gerçek buluta geçer.
Bu modül bilinçli olarak 'edge' paketi dışına bağımlı değildir:
gerçek bulut deployment'ında da aynı mantık kullanılabilir.
"""
from __future__ import annotations

import random
import time
from typing import Any, Dict, List


def _clampf(v: float, lo: float, hi: float) -> float:
    return lo if v < lo else hi if v > hi else v


class MockCloud:
    def __init__(self, weather: str = "rain", min_latency_ms: float = 350.0,
                 max_latency_ms: float = 800.0, seed: int = 7):
        self.weather = weather.lower()
        self.min_latency_ms = float(min_latency_ms)
        self.max_latency_ms = float(max_latency_ms)
        self._rng = random.Random(seed)

    # --- sahte Tavily: canlı hava araması ---
    def _tavily_lookup(self, region: str) -> Dict[str, Any]:
        table = {
            "rain": {"condition": "Light rain", "precipitation": "moderate",
                     "wind_kmh": 18, "temperature_c": 14},
            "storm": {"condition": "Heavy rain", "precipitation": "intense",
                      "wind_kmh": 40, "temperature_c": 11},
            "clear": {"condition": "Clear", "precipitation": "none",
                      "wind_kmh": 6, "temperature_c": 22},
        }
        w = dict(table.get(self.weather, table["rain"]))
        w["region"] = region or "unknown region"
        w["source"] = "tavily-mock://search?q=live+weather+" + w["region"].replace(" ", "+")
        w["summary"] = (f"{w['condition']} in {w['region']} "
                        f"({w['precipitation']} precipitation, wind {w['wind_kmh']} km/h, "
                        f"{w['temperature_c']}C)")
        return w

    # --- sahte Nemotron: teşhis + yama üretimi ---
    def _diagnose(self, payload: Dict[str, Any], weather: Dict[str, Any]) -> Dict[str, Any]:
        tel: List[Dict[str, Any]] = payload.get("telemetry") or []
        gains = payload.get("current_gains") or {}
        kp = float(gains.get("kp", 2.2))
        kd = float(gains.get("kd", 0.08))
        max_speed = float(gains.get("max_speed", 0.22))
        n = max(len(tel), 1)
        v_bias = sum(float(r.get("v_odom", 0.0)) - float(r.get("v_true", 0.0))
                     for r in tel) / n
        w_bias = sum(float(r.get("omega_odom", 0.0)) - float(r.get("omega_true", 0.0))
                     for r in tel) / n
        v_ref = max(abs(float(tel[-1].get("v_odom", 0.2))) if tel else 0.2, 0.05)
        slip_ratio = _clampf(abs(v_bias) / v_ref, 0.0, 1.0)
        wet = self.weather in ("rain", "storm")

        kp_new = min(kp * (1.0 + 0.6 * slip_ratio), 6.0) if wet else kp
        kd_new = max(kd, 0.22) if wet else kd
        slip_comp = _clampf(w_bias * 0.8, -1.0, 1.0)
        patch = {
            "heading_pid": {"kp": round(kp_new, 3), "ki": 0.0, "kd": round(kd_new, 3)},
            "slip_compensation": round(slip_comp, 3),
            "max_speed": round(min(max_speed, 0.16), 3),
            "odom_resync": True,
            "safety_mode": "hold_line",
        }
        v_bias_txt = min(abs(v_bias), 0.5)
        w_bias_txt = min(abs(w_bias), 2.0)
        diagnosis = (
            f"Traction loss detected: odometry reports {v_bias_txt:.3f} m/s more ground "
            f"speed than actual motion and {w_bias_txt:.3f} rad/s rotational mismatch - "
            f"consistent with wheel slip on a wet surface. Live weather via Tavily: "
            f"{weather['summary']}. Injecting patch: Kp {kp:.2f}->{kp_new:.2f}, "
            f"Kd {kd:.2f}->{kd_new:.2f}, slip feedforward {slip_comp:+.3f} rad/s, "
            f"speed ceiling {patch['max_speed']} m/s.")
        confidence = min(0.55 + 0.35 * slip_ratio, 0.97) if wet else 0.5
        return {"diagnosis": diagnosis, "patch": patch,
                "confidence": round(confidence, 2)}

    def handle(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        # Gerçekçi bulut round-trip gecikmesi
        time.sleep(self._rng.uniform(self.min_latency_ms,
                                     self.max_latency_ms) / 1000.0)
        region = str(payload.get("region", ""))
        weather = self._tavily_lookup(region)
        result = self._diagnose(payload, weather)
        result.update({
            "event_id": str(payload.get("event_id", "")),
            "weather_summary": weather["summary"],
            "weather_source": weather["source"],
            "model": "nemo-mock/nemotron-410b",
        })
        return result
