"""Uçtan uca demo akışı: fizik -> algılama -> (mock/gerçek) bulut -> yama.

Bulut çağrısı arka planda (worker thread) yapılır; robot simülasyonu
beklerken aksamaya devam eder - gerçek sahada olduğu gibi.
"""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from edge.anomaly import AnomalyConfig, AnomalyDetector
from edge.cloud_bridge import CloudBridge
from edge.mock_cloud import MockCloud
from edge.path_follower import (FollowerParams, PathFollower, WaypointPath,
                                circular_waypoints, cross_track_error)
from edge.robot_physics import DiffDriveRobot
from edge.telemetry import TelemetryPacket, TelemetrySample

TELEMETRY_WINDOW = 25  # bulota giden son N örnek (~0.5 s)


@dataclass
class DemoConfig:
    slip: float = 0.55                 # sol teker traction kaybı (1-slip)
    slip_at: float = 12.0              # bozulma anı (s)
    duration: float = 45.0
    dt: float = 0.02
    realtime: bool = False            # jüri canlı izlemesi için gerçek zamanlı mod
    mock: bool = True
    endpoint_url: str = ""
    api_key: str = ""
    weather: str = "rain"
    region: str = "Kadikoy, Istanbul, TR"
    seed: int = 7
    mock_min_latency_ms: float = 350.0
    mock_max_latency_ms: float = 800.0
    threshold: float = 0.60
    kp: float = 2.2
    kd: float = 0.08
    max_speed: float = 0.22
    grace_s: float = 6.0    # bulut yaması için ek bekleme (sim süresi uzar)
    verbose: bool = True


@dataclass
class DemoResult:
    events: List[Dict[str, Any]] = field(default_factory=list)
    history: List[TelemetrySample] = field(default_factory=list)
    stats: Dict[str, Any] = field(default_factory=dict)


class DemoRunner:
    def __init__(self, config: Optional[DemoConfig] = None):
        self.cfg = config or DemoConfig()
        c = self.cfg
        self.robot = DiffDriveRobot()
        self.wps = circular_waypoints(cx=1.0, cy=2.2, rx=2.2, ry=1.5,
                                      n=12, start=(0.0, 0.0))
        self.path = WaypointPath(self.wps, goal_radius=0.30)
        self.follower = PathFollower(
            self.path, FollowerParams(kp=c.kp, kd=c.kd, max_speed=c.max_speed))
        self.detector = AnomalyDetector(AnomalyConfig(threshold=c.threshold))
        mock_cloud = MockCloud(weather=c.weather,
                               min_latency_ms=c.mock_min_latency_ms,
                               max_latency_ms=c.mock_max_latency_ms,
                               seed=c.seed) if c.mock else None
        self.bridge = CloudBridge(mock=c.mock, endpoint_url=c.endpoint_url,
                                  api_key=c.api_key, mock_cloud=mock_cloud)
        self._pending: Optional[Dict[str, Any]] = None
        self._executor = ThreadPoolExecutor(max_workers=1)
        self._injected = False
        self.grace_s = 8.0  # bulut yaması için ek bekleme (gerçek zaman, s)
        self.result = DemoResult()

    # ------------------------------------------------------------------ run
    def run(self) -> DemoResult:
        c = self.cfg
        n_steps = int(c.duration / c.dt)
        wall = time.perf_counter()
        for step in range(n_steps):
            self._step_once(step * c.dt, wall, step)
        # Bulut yaması yoldaysa: sim bir süre daha yaşar (grace extension)
        if self._pending is not None:
            print("  .. waiting for cloud patch (extending simulation)")
            # Grace GERÇEK zaman bazlıdır: mock bulut 350-800 ms uyur,
            # o yüzden sim adımları arasında gerçek zaman akıtılır.
            # Yama geldikten sonra da sim, toparlanmayı göstersin diye
            # pencere sonuna kadar yaşamaya devam eder.
            deadline = time.perf_counter() + self.grace_s
            t_sim = c.duration
            timed_out = False
            while time.perf_counter() < deadline:
                self._step_once(t_sim, wall, n_steps)
                t_sim += c.dt
                time.sleep(c.dt)   # gerçek zaman akışı (yama yetişsin)
                if self._pending is not None and time.perf_counter() >= deadline:
                    timed_out = True
            if self._pending is not None:
                self._log_event("CLOUD_TIMEOUT", t_sim,
                                "no patch within grace window")
                self._pending = None
                self.follower.set_safe_mode(False)
            elif timed_out:
                pass
        self._finalize()
        return self.result

    def _step_once(self, t: float, wall: float, step: int) -> None:
        c = self.cfg
        if not self._injected and t >= c.slip_at:
            self.robot.set_traction(1.0 - c.slip, 1.0, ramp_time=2.0)
            self._injected = True
            self._log_event("DISTURBANCE", t,
                            f"left traction -> {1.0 - c.slip:.2f}")
            print(f"  !! DISTURBANCE at t={t:.1f}s: left wheel traction "
                  f"dropped to {1.0 - c.slip:.2f} (wet surface)")
        st = self.robot.state
        v_cmd, omega_cmd, tx, ty, he = self.follower.compute_cmd(
            st.x, st.y, st.theta, c.dt)
        self.robot.set_cmd(v_cmd, omega_cmd)
        st = self.robot.step(c.dt)
        cte = cross_track_error(st.x, st.y, self.wps)
        sample = TelemetrySample(
            t=t, x=st.x, y=st.y, theta=st.theta,
            x_odom=st.x_odom, y_odom=st.y_odom, theta_odom=st.theta_odom,
            v_odom=st.v_odom, omega_odom=st.omega_odom,
            v_true=st.v_true, omega_true=st.omega_true,
            cte=cte, heading_error=he)
        verdict = self.detector.update(sample, t)
        sample.anomaly_score = verdict.score
        self.result.history.append(sample)
        if verdict.alarm and self._pending is None:
            self._on_alarm(sample, t, verdict.event_id, verdict.score)
        if self._pending is not None and self._pending["future"].done():
            self._on_patch_applied(t)
        if c.verbose and step % int(1.0 / c.dt) == 0:
            print(f"[t={t:6.2f}s] cte={cte:5.2f} score={verdict.score:4.2f} "
                  f"v={st.v_true:4.2f} "
                  f"mode={'SAFE' if self.follower.safe_mode else 'OK'}")
        if c.realtime:
            d = (wall + (step + 1) * c.dt) - time.perf_counter()
            if d > 0:
                time.sleep(d)

    # --------------------------------------------------------------- events
    def _build_packet(self, sample: TelemetrySample, event_id: str,
                      score: float) -> TelemetryPacket:
        hist = self.result.history[-TELEMETRY_WINDOW:]
        return TelemetryPacket(
            event_id=event_id, score=round(score, 3), created_at=time.time(),
            region=self.cfg.region,
            pose={"x": sample.x, "y": sample.y, "theta": sample.theta},
            current_gains=self.follower.gains,
            telemetry=[s.to_dict() for s in hist])

    def _on_alarm(self, sample: TelemetrySample, t: float,
                  event_id: str, score: float) -> None:
        packet = self._build_packet(sample, event_id, score)
        self.follower.set_safe_mode(True)
        self._pending = {"event_id": packet.event_id,
                         "future": self._executor.submit(
                             self.bridge.request_patch, packet)}
        self._log_event("ALARM", t, f"score={score:.2f} event={packet.event_id}")
        print("  >> ALARM: physical deviation! Dispatching telemetry to cloud...")

    def _on_patch_applied(self, t: float) -> None:
        future = self._pending["future"]
        self._pending = None
        try:
            resp = future.result()
        except Exception as e:
            self._log_event("CLOUD_ERROR", t, str(e))
            print(f"  >> CLOUD ERROR: {e}")
            self.follower.set_safe_mode(False)
            return
        self.follower.apply_patch(resp.patch)
        self.follower.set_safe_mode(False)
        if resp.patch.get("odom_resync"):
            self.robot.reset_odometry_to_truth()
        self._log_event("PATCH_APPLIED", t,
                        f"latency_ms={resp.latency_ms:.0f} "
                        f"kp={resp.patch.get('heading_pid', {}).get('kp')} "
                        f"slip_comp={resp.patch.get('slip_compensation')}")
        print(f"  >> PATCH in {resp.latency_ms:.0f} ms: {resp.diagnosis[:90]}...")

    def _log_event(self, etype: str, t: float, info: str) -> None:
        self.result.events.append({"type": etype, "t": t, "info": info})

    # -------------------------------------------------------------- stats
    def _finalize(self) -> None:
        hist = self.result.history
        alarms = [e for e in self.result.events if e["type"] == "ALARM"]
        patches = [e for e in self.result.events
                   if e["type"] == "PATCH_APPLIED"]
        latencies = []
        for e in patches:
            if "latency_ms=" in e["info"]:
                latencies.append(float(e["info"].split("latency_ms=")[1].split()[0]))
        first_alarm_t = alarms[0]["t"] if alarms else None
        recovery_t = None
        if first_alarm_t is not None and patches:
            for s in hist:
                if s.t > first_alarm_t + 0.5 and abs(s.cte) < 0.15:
                    recovery_t = s.t
                    break
        self.result.stats = {
            "duration_s": self.cfg.duration,
            "steps": len(hist),
            "alarms": len(alarms),
            "patches_applied": len(patches),
            "first_alarm_t": first_alarm_t,
            "recovery_t": recovery_t,
            "recovery_duration_s": (recovery_t - first_alarm_t)
                                   if (recovery_t is not None and first_alarm_t is not None) else None,
            "latencies_ms": latencies,
            "max_cte": max((abs(s.cte) for s in hist), default=0.0),
            "final_cte": abs(hist[-1].cte) if hist else 0.0,
            "max_score": max((s.anomaly_score for s in hist), default=0.0),
        }
