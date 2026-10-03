"""Uçtan uca akış testi: slip -> alarm -> mock bulut -> yama -> toparlanma."""
from edge.demo_runner import DemoConfig, DemoRunner


def test_end_to_end_alarm_and_patch():
    cfg = DemoConfig(
        slip=0.55, slip_at=4.0, duration=16.0, dt=0.02,
        mock=True, mock_min_latency_ms=20.0, mock_max_latency_ms=40.0,
        verbose=False, seed=3)
    runner = DemoRunner(cfg)
    result = runner.run()
    types = [e["type"] for e in result.events]
    assert "DISTURBANCE" in types
    assert "ALARM" in types, "slip anomalisinde alarm beklenir"
    assert "PATCH_APPLIED" in types, "mock buluttan yama gelmeli"
    # Alarm, bozulmadan sonra gelmeli
    t_dist = next(e["t"] for e in result.events if e["type"] == "DISTURBANCE")
    t_alarm = next(e["t"] for e in result.events if e["type"] == "ALARM")
    assert t_alarm > t_dist
    # Algılama hızı: alarm bozulmadan sonra ~2 saniye içinde (rampa dahil)
    assert t_alarm - t_dist < 3.0
    # Yamada geçerli PID kazancı ve telafi var
    t_patch = next(e["t"] for e in result.events if e["type"] == "PATCH_APPLIED")
    assert t_patch >= t_alarm
    # Toparlanma: sim sonunda CTE tekrar küçük
    stats = result.stats
    assert stats["final_cte"] < 0.35, f"final CTE={stats['final_cte']}"
    assert stats["max_score"] >= 0.6


def test_end_to_end_no_false_alarm_on_dry_ground():
    """Slip yok: alarm tetiklenmemeli."""
    cfg = DemoConfig(slip=0.0, slip_at=5.0, duration=14.0, dt=0.02,
                     mock=True, mock_min_latency_ms=5.0,
                     mock_max_latency_ms=10.0, verbose=False)
    runner = DemoRunner(cfg)
    result = runner.run()
    assert "ALARM" not in [e["type"] for e in result.events]
    assert result.stats["final_cte"] < 0.2
