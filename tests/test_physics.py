"""Fizik motoru testleri: slip modeli, odometri, açı sarması."""
import math

from edge.robot_physics import DiffDriveRobot, wrap_angle


def test_wrap_angle():
    assert abs(wrap_angle(2 * math.pi + 0.1) - 0.1) < 1e-9
    assert abs(wrap_angle(-2 * math.pi + 0.1) - 0.1) < 1e-9
    assert abs(wrap_angle(math.pi + 0.1) - (-math.pi + 0.1)) < 1e-9


def test_no_slip_odom_matches_truth():
    """Kuru zemin: odometri dead-reckoning gerçek yolu takip eder."""
    r = DiffDriveRobot()
    r.set_cmd(0.2, 0.0)
    for _ in range(300):
        st = r.step(0.02)
    assert abs(st.x - st.x_odom) < 1e-6
    assert abs(st.y - st.y_odom) < 1e-6
    assert abs(st.v_true - st.v_odom) < 1e-6


def test_slip_reduces_true_speed_not_odometry():
    """Kaygan zemin: motor döner (odometri mutlu) ama zemin hızı düşer."""
    r = DiffDriveRobot()
    r.set_cmd(0.2, 0.0)
    for _ in range(200):          # motor yerleşsin
        r.step(0.02)
    r.set_traction(0.4, 1.0, ramp_time=0.01)
    for _ in range(100):
        st = r.step(0.02)
    assert st.v_true < st.v_odom
    assert st.v_odom > 0.15        # encoder kaymayı göremez
    assert st.traction_left < 0.5


def test_slip_causes_rotation_mismatch():
    """Asimetrik traction: robot gerçekten döner, odometri dönmediğini sanır."""
    r = DiffDriveRobot()
    r.set_cmd(0.2, 0.0)
    for _ in range(200):
        r.step(0.02)
    r.set_traction(0.45, 1.0, ramp_time=0.01)
    for _ in range(100):
        st = r.step(0.02)
    assert st.omega_true > st.omega_odom + 0.2


def test_straight_line_motion():
    r = DiffDriveRobot()
    r.set_cmd(0.2, 0.0)
    for _ in range(500):
        st = r.step(0.02)
    assert abs(st.y) < 1e-6
    assert abs(st.theta) < 1e-9
    assert st.x > 0.5


def test_odometry_resync():
    r = DiffDriveRobot()
    r.set_cmd(0.2, 0.3)
    for _ in range(200):
        r.step(0.02)
    r.reset_odometry_to_truth()
    st = r.state
    assert st.x == st.x_odom and st.y == st.y_odom
