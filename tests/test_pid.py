"""PID denetleyici testleri: yakınsama, hot-swap, anti-windup."""
from edge.pid import PID


def test_pid_converges_first_order():
    """y' = u sistemi: PID hatayı sıfıra indirir."""
    pid = PID(kp=2.0, ki=0.5, kd=0.05)
    y, setpoint, dt = 0.0, 1.0, 0.01
    for _ in range(4000):
        u = pid.update(setpoint - y, dt)
        y += u * dt
    assert abs(setpoint - y) < 0.01


def test_pid_hot_swap_keeps_integral():
    pid = PID(kp=1.0, ki=1.0, kd=0.0)
    pid.update(5.0, 0.1)
    integral_before = pid.integral
    pid.set_gains(kp=3.0, kd=0.2)
    assert pid.integral == integral_before     # durum korunur
    assert pid.kp == 3.0 and pid.kd == 0.2     # kazançlar değişti


def test_pid_anti_windup():
    pid = PID(kp=1.0, ki=10.0, kd=0.0, out_max=1.0, int_limit=0.5)
    for _ in range(500):
        pid.update(5.0, 0.01)   # sürekli büyük hata -> doyma
    assert pid.integral <= 0.5 + 1e-9


def test_pid_reset():
    pid = PID(kp=1.0, ki=1.0, kd=1.0)
    pid.update(3.0, 0.01)
    pid.reset()
    assert pid.integral == 0.0 and pid._prev_error is None


def test_pid_output_limits():
    pid = PID(kp=100.0, out_min=-2.0, out_max=2.0)
    assert pid.update(10.0, 0.01) == 2.0
    assert pid.update(-10.0, 0.01) == -2.0
