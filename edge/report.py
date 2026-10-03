"""Demo raporu: sapma -> alarm -> bulut yaması -> toparlanma grafikleri."""
from __future__ import annotations

from typing import List

import matplotlib

matplotlib.use("Agg")  # headless güvenli (WSL/sunucuda sorun çıkarmaz)
import matplotlib.pyplot as plt  # noqa: E402

from edge.telemetry import TelemetrySample  # noqa: E402


def _event_lines(events, axes, label_prefix=""):
    for e in events:
        color = {"DISTURBANCE": "tab:red", "ALARM": "darkorange",
                 "PATCH_APPLIED": "seagreen"}.get(e["type"], "gray")
        for ax in axes:
            ax.axvline(e["t"], color=color, linestyle="--", alpha=0.75)
    # tek açıklama için proxy legend
    handles = [plt.Line2D([0], [0], color="tab:red", ls="--"),
               plt.Line2D([0], [0], color="darkorange", ls="--"),
               plt.Line2D([0], [0], color="seagreen", ls="--")]
    return handles


def plot_report(result, waypoints, out_path="demo_report.png",
                show=False, stats=None):
    hist: List[TelemetrySample] = result.history
    events = result.events
    t = [s.t for s in hist]
    fig, axes = plt.subplots(3, 2, figsize=(14, 12))
    fig.suptitle("AeroPatch — Physical Deviation Detection & Cloud Patch Demo",
                 fontsize=15, fontweight="bold")
    (a0, a1), (a2, a3), (a4, a5) = axes
    # (0,0) Yörünge haritası
    wx = [p[0] for p in waypoints] + [waypoints[0][0]]
    wy = [p[1] for p in waypoints] + [waypoints[0][1]]
    a0.plot(wx, wy, "k--", lw=1.5, label="reference path")
    a0.plot([s.x for s in hist], [s.y for s in hist], "b-", lw=1.2, label="ground truth")
    a0.plot([s.x_odom for s in hist], [s.y_odom for s in hist], "g:", lw=1.0,
            alpha=0.8, label="odometry DR")
    a0.plot(hist[0].x, hist[0].y, "ks", ms=8, label="start")
    dist_ev = [e for e in events if e["type"] == "DISTURBANCE"]
    for e in dist_ev:
        i = min(range(len(t)), key=lambda k: abs(t[k] - e["t"]))
        a0.plot(hist[i].x, hist[i].y, "rX", ms=12)
    a0.set_title("Trajectory (patrol route)")
    a0.set_xlabel("x [m]"); a0.set_ylabel("y [m]"); a0.axis("equal"); a0.grid(True)
    a0.legend(fontsize=8)
    # (0,1) CTE
    handles = _event_lines(events, [a1])
    a1.plot(t, [s.cte for s in hist], "b-", lw=1)
    a1.set_title("Cross-track error (deviation)")
    a1.set_xlabel("t [s]"); a1.set_ylabel("CTE [m]"); a1.grid(True)
    a1.legend(handles, ["disturbance", "alarm", "cloud patch"], fontsize=8)
    # (1,0) Anomali skoru
    a2.plot(t, [s.anomaly_score for s in hist], "m-", lw=1)
    a2.axhline(0.60, color="r", ls=":", lw=1, label="threshold")
    a2.set_title("Anomaly score (edge detector, no LLM)")
    a2.set_xlabel("t [s]"); a2.grid(True); a2.legend(fontsize=8)
    # (1,1) Hızlar: odometri vs gerçek (slip imzası)
    a3.plot(t, [s.v_odom for s in hist], "g-", lw=1, label="v_odom (encoders)")
    a3.plot(t, [s.v_true for s in hist], "b-", lw=1, label="v_true (ground)")
    a3.set_title("Speed mismatch — the slip signature")
    a3.set_xlabel("t [s]"); a3.set_ylabel("v [m/s]"); a3.grid(True); a3.legend(fontsize=8)
    # (2,0) Dönüş hızı uyuşmazlığı
    a4.plot(t, [s.omega_odom for s in hist], "g-", lw=1, label="omega_odom")
    a4.plot(t, [s.omega_true for s in hist], "b-", lw=1, label="omega_true")
    a4.set_title("Rotational mismatch (drift)")
    a4.set_xlabel("t [s]"); a4.set_ylabel("omega [rad/s]"); a4.grid(True); a4.legend(fontsize=8)
    # (2,1) Odom DR pozisyon hatası + istatistik
    dpos = [((s.x - s.x_odom) ** 2 + (s.y - s.y_odom) ** 2) ** 0.5 for s in hist]
    a5.plot(t, dpos, "c-", lw=1, label="|truth - odom DR|")
    a5.set_title("Localization innovation (dead-reckoning error)")
    a5.set_xlabel("t [s]"); a5.set_ylabel("error [m]"); a5.grid(True); a5.legend(fontsize=8)
    if stats:
        txt = "\n".join([
            f"alarms: {stats.get('alarms')}",
            f"patches: {stats.get('patches_applied')}",
            f"cloud latency: {stats.get('latencies_ms')}",
            f"recovery: {stats.get('recovery_duration_s') and round(stats['recovery_duration_s'], 2)} s",
            f"max CTE: {stats.get('max_cte') and round(stats['max_cte'], 2)} m",
        ])
        a5.text(0.98, 0.55, txt, transform=a5.transAxes, ha="right",
                va="top", fontsize=9,
                bbox=dict(boxstyle="round", fc="lightyellow", alpha=0.9))
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(out_path, dpi=120)
    print(f"[report] saved -> {out_path}")
    if show:
        plt.show()
    plt.close(fig)
