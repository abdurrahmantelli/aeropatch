"""ROS2 canli kaydindan (ros_record.jsonl) demo raporu uretir.

Kullanim:  python plot_ros_record.py [jsonl] [out.png]
"""
import json
import math
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

JSONL = sys.argv[1] if len(sys.argv) > 1 else \
    "wsl/logs/ros_record.jsonl"
OUT = sys.argv[2] if len(sys.argv) > 2 else "ros_demo_report.png"

gt, odom, score, patches = [], [], [], []
with open(JSONL, encoding="utf-8") as f:
    for line in f:
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        k = d.get("kind")
        if k == "gt":
            gt.append((d["t"], d["x"], d["y"], d["theta"]))
        elif k == "odom":
            odom.append((d["t"], d["x"], d["y"], d["theta"], d["v"], d["w"]))
        elif k == "score":
            score.append((d["t"], d["score"]))
        elif k == "patch":
            patches.append(d)

print(f"records: gt={len(gt)} odom={len(odom)} score={len(score)} patches={len(patches)}")
if not gt:
    sys.exit("no ground truth records")

# Gercek hizi gt pozisyon farklarindan turet (slip imzasi)
v_true = []
for i in range(1, len(gt)):
    dt = gt[i][0] - gt[i - 1][0]
    if dt > 0.001:
        dist = math.hypot(gt[i][1] - gt[i - 1][1], gt[i][2] - gt[i - 1][2])
        v_true.append((gt[i][0], dist / dt))

fig, axes = plt.subplots(2, 2, figsize=(14, 10))
fig.suptitle("AeroPatch — LIVE ROS2 (Humble) demo: wheel-slip -> edge alarm -> "
             "cloud (Nemotron+Tavily) patch", fontsize=13, fontweight="bold")
(a0, a1), (a2, a3) = axes

# (0,0) trayektori
if odom:
    a0.plot([o[1] for o in odom], [o[2] for o in odom], "g:", lw=1,
            alpha=0.8, label="odometry (DR, blind to slip)")
a0.plot([g[1] for g in gt], [g[2] for g in gt], "b-", lw=1.6,
        label="ground truth (external loc.)")
a0.plot(gt[0][1], gt[0][2], "ks", ms=8, label="start")
for i, p in enumerate(patches):
    if i == 0 and gt:
        tt = p.get("t", 0)
        nearest = min(gt, key=lambda g: abs(g[0] - tt))
        a0.plot(nearest[1], nearest[2], "rX", ms=13, label="first cloud patch")
a0.set_title("Trajectory under wet-ground disturbance")
a0.set_xlabel("x [m]"); a0.set_ylabel("y [m]"); a0.axis("equal"); a0.grid(True)
a0.legend(fontsize=8)

# (0,1) anomali skoru
if score:
    a1.plot([s[0] for s in score], [s[1] for s in score], "m-", lw=1)
a1.axhline(0.60, color="r", ls=":", lw=1.2, label="alarm threshold (0.6)")
for p in patches:
    a1.axvline(p.get("t", 0), color="seagreen", ls="--", alpha=0.6)
a1.set_title("Edge anomaly score (pure math, on-board)")
a1.set_xlabel("t [s]"); a1.set_ylabel("score"); a1.grid(True); a1.legend(fontsize=8)

# (1,0) hiz uyusmazligi
if odom:
    a2.plot([o[0] for o in odom], [o[4] for o in odom], "g-", lw=1,
            label="v_odom (encoders)")
if v_true:
    a2.plot([v[0] for v in v_true], [v[1] for v in v_true], "b-", lw=1,
            label="v_true (derived from ext. loc.)")
for p in patches:
    a2.axvline(p.get("t", 0), color="seagreen", ls="--", alpha=0.6)
a2.set_title("Slip signature: encoder speed vs true ground speed")
a2.set_xlabel("t [s]"); a2.set_ylabel("v [m/s]"); a2.grid(True); a2.legend(fontsize=8)

# (1,1) bulut gecikmeleri + yamalar
if patches:
    lats = [p.get("latency_ms", 0) for p in patches]
    xs = list(range(1, len(patches) + 1))
    a3.bar(xs, lats, color="seagreen", alpha=0.8)
    a3.axhline(sum(lats) / len(lats), color="navy", ls=":",
               label=f"mean {sum(lats)/len(lats):.0f} ms")
    a3.set_xticks(xs)
    a3.set_xticklabels([p.get("event_id", "")[-6:] for p in patches],
                       rotation=45, fontsize=7)
    a3.set_title("Cloud patch round-trip latency (Nemotron + Tavily)")
    a3.set_xlabel("patch event"); a3.set_ylabel("latency [ms]")
    a3.grid(True, axis="y"); a3.legend(fontsize=8)
    info = (f"diagnosis: {patches[0].get('diagnosis', '')[:180]}...\n"
            f"weather: {patches[0].get('weather', '')[:80]}")
    a3.text(0.02, 0.60, info, transform=a3.transAxes, fontsize=7.5, va="top",
            bbox=dict(boxstyle="round", fc="lightyellow", alpha=0.95))

fig.tight_layout(rect=(0, 0, 1, 0.95))
fig.savefig(OUT, dpi=120)
print(f"saved -> {OUT}")
