"""AeroPatch CLI demo.

Örnekler:
  python -m edge.run_demo --mock
  python -m edge.run_demo --mock --realtime --show      # jüri canlı videosu
  python -m edge.run_demo --real --endpoint https://... --api-key ...
"""
from __future__ import annotations

import argparse

from edge.demo_runner import DemoConfig, DemoRunner
from edge.report import plot_report


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="aeropatch-demo",
        description="Edge anomaly detection + cloud (Nemotron/Tavily) patch demo")
    p.add_argument("--mock", action="store_true", default=True,
                   help="mock bulut kullan (Nebius simülasyonu)")
    p.add_argument("--real", action="store_true",
                   help="gerçek Nebius endpoint kullan (mock kapatır)")
    p.add_argument("--endpoint", default="", help="Nebius endpoint URL")
    p.add_argument("--api-key", default="", help="Nebius API anahtarı")
    p.add_argument("--slip", type=float, default=0.55,
                   help="sol teker traction kaybı (0-1)")
    p.add_argument("--slip-at", type=float, default=12.0,
                   help="bozulmanın başladığı simülasyon zamanı (s)")
    p.add_argument("--duration", type=float, default=45.0)
    p.add_argument("--dt", type=float, default=0.02)
    p.add_argument("--weather", default="rain", choices=["rain", "storm", "clear"])
    p.add_argument("--region", default="Kadikoy, Istanbul, TR")
    p.add_argument("--threshold", type=float, default=0.60)
    p.add_argument("--realtime", action="store_true",
                   help="gerçek zamanlı oynat (jüri canlı demosu)")
    p.add_argument("--report", default="demo_report.png")
    p.add_argument("--show", action="store_true", help="grafiği ekranda aç")
    p.add_argument("--quiet", action="store_true")
    return p


def main(argv=None) -> int:
    args = build_arg_parser().parse_args(argv)
    cfg = DemoConfig(
        slip=args.slip, slip_at=args.slip_at, duration=args.duration, dt=args.dt,
        realtime=args.realtime, mock=(not args.real),
        endpoint_url=args.endpoint, api_key=args.api_key,
        weather=args.weather, region=args.region, threshold=args.threshold,
        verbose=(not args.quiet))
    print("=" * 68)
    print("AeroPatch — Edge anomaly detection -> Nebius/Nemotron + Tavily patch")
    print(f"  mode        : {'MOCK CLOUD (nemotron+tavily simulation)' if cfg.mock else 'REAL Nebius endpoint'}")
    print(f"  disturbance : left traction {1 - cfg.slip:.2f} @ t={cfg.slip_at}s")
    print(f"  region      : {cfg.region} (Tavily will fetch live weather)")
    print("=" * 68)
    runner = DemoRunner(cfg)
    result = runner.run()
    stats = result.stats
    print("-" * 68)
    print("EVENT TIMELINE:")
    for e in result.events:
        print(f"  t={e['t']:7.2f}s  {e['type']:<14} {e['info']}")
    print("-" * 68)
    print(f"alarms={stats['alarms']}  patches={stats['patches_applied']}  "
          f"recovery={stats['recovery_duration_s']}s  "
          f"max_cte={stats['max_cte']:.2f}m  final_cte={stats['final_cte']:.2f}m")
    if not cfg.realtime:
        plot_report(result, runner.wps, out_path=args.report,
                    show=args.show, stats=stats)
    print("DONE.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
