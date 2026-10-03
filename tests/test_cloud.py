"""Bulut katmanı testleri: mock sözleşme şeması, yama doğruluğu, latency."""
from edge.cloud_bridge import CloudBridge
from edge.mock_cloud import MockCloud
from edge.telemetry import PatchResponse, TelemetryPacket


def _packet(score=1.1):
    tel = []
    for i in range(25):
        tel.append({"t": i * 0.02, "x": 1.0, "y": 1.0, "theta": 0.0,
                    "x_odom": 1.01, "y_odom": 1.0, "theta_odom": 0.0,
                    "v_odom": 0.2, "omega_odom": 0.0,
                    "v_true": 0.09, "omega_true": 0.6,
                    "cte": 0.3, "heading_error": 0.2,
                    "anomaly_score": 0.5})
    return TelemetryPacket(event_id="evt-test-1", score=score,
                           created_at=0.0, region="Kadikoy, Istanbul, TR",
                           pose={"x": 1.0, "y": 1.0, "theta": 0.0},
                           current_gains={"kp": 2.2, "ki": 0.0, "kd": 0.08,
                                          "slip_compensation": 0.0,
                                          "max_speed": 0.22},
                           telemetry=tel)


def test_mock_cloud_returns_full_schema():
    mc = MockCloud(weather="rain", min_latency_ms=1.0, max_latency_ms=2.0)
    out = mc.handle(_packet().to_dict())
    for key in ("event_id", "diagnosis", "weather_summary", "weather_source",
                "patch", "confidence", "model"):
        assert key in out, f"şemada eksik alan: {key}"
    assert "rain" in out["weather_summary"].lower()
    assert out["model"] == "nemo-mock/nemotron-410b"


def test_mock_patch_values_sane():
    mc = MockCloud(weather="rain", min_latency_ms=1.0, max_latency_ms=2.0)
    out = mc.handle(_packet().to_dict())
    p = out["patch"]
    assert 0.0 <= p["heading_pid"]["kp"] <= 6.0
    assert p["slip_compensation"] < 0.0   # omega_odom - omega_true = -0.6
    assert p["max_speed"] <= 0.22
    assert p["odom_resync"] is True


def test_bridge_measures_latency():
    bridge = CloudBridge(mock=True,
                         mock_cloud=MockCloud(min_latency_ms=40.0,
                                               max_latency_ms=60.0))
    resp = bridge.request_patch(_packet())
    assert isinstance(resp, PatchResponse)
    assert resp.latency_ms >= 35.0       # mock gecikmesi ölçülmeli
    assert resp.event_id == "evt-test-1"
    assert resp.patch["heading_pid"]["kp"] > 0


def test_patch_response_from_dict_defaults():
    r = PatchResponse.from_dict({"diagnosis": "x"}, latency_ms=123.0)
    assert r.diagnosis == "x" and r.latency_ms == 123.0
    assert r.patch == {} and r.confidence == 0.0
