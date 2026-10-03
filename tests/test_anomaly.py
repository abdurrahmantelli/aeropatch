"""Anomali algılayıcı testleri: normal akış, slip tetikleme, cooldown."""
from edge.anomaly import AnomalyConfig, AnomalyDetector
from edge.telemetry import TelemetrySample


def sample(**kw):
    base = dict(t=0.0, x=0.0, y=0.0, theta=0.0, x_odom=0.0, y_odom=0.0,
                theta_odom=0.0, v_odom=0.2, omega_odom=0.0, v_true=0.2,
                omega_true=0.0, cte=0.05, heading_error=0.1)
    base.update(kw)
    return TelemetrySample(**base)


def test_normal_flight_no_alarm():
    """Tutarlı telemetri: skor düşük, alarm yok."""
    d = AnomalyDetector(AnomalyConfig())
    for i in range(200):
        x = i * 0.02 * 0.2
        s = sample(t=i * 0.02, x=x, x_odom=x)
        v = d.update(s, t=i * 0.02)
        assert not v.alarm
    assert v.score < 0.3


def test_slip_triggers_alarm_after_persistence():
    d = AnomalyDetector(AnomalyConfig(threshold=0.6, persistence=5))
    alarmed = False
    for i in range(100):
        s = sample(t=i * 0.02, v_odom=0.2, v_true=0.08,
                   omega_odom=0.0, omega_true=0.7,
                   x_odom=i * 0.004, x=i * 0.0016)
        v = d.update(s, t=i * 0.02)
        if v.alarm:
            alarmed = True
            assert v.event_id and v.event_id.startswith("evt-")
            break
    assert alarmed, "slip anomalisinde alarm tetiklenmeli"


def test_score_below_threshold_is_zero_persistence():
    """Eşik altı tekil tepeler alarm üretmez (persistence)."""
    d = AnomalyDetector(AnomalyConfig(threshold=0.6, persistence=5))
    t = 0.0
    for _ in range(50):
        v = d.update(sample(t=t), t=t)     # skor ~0.1
        t += 0.02
    assert not v.alarm


def test_cooldown_blocks_immediate_realarm():
    d = AnomalyDetector(AnomalyConfig(threshold=0.6, persistence=3,
                                      cooldown_s=4.0))
    alarms = 0
    for i in range(100):
        s = sample(t=i * 0.02, v_odom=0.2, v_true=0.05,
                   omega_odom=0.0, omega_true=0.8)
        v = d.update(s, t=i * 0.02)       # sim süresi 2 s < cooldown 4 s
        if v.alarm:
            alarms += 1
    assert alarms == 1, f"cooldown içinde tek alarm beklenir, {alarms} oldu"


def test_components_reported():
    d = AnomalyDetector()
    v = d.update(sample(v_odom=0.2, v_true=0.0), t=0.0)
    assert v.components["speed_mismatch"] > 1.0
    assert 0.0 < v.components["cte"] < 1.0
