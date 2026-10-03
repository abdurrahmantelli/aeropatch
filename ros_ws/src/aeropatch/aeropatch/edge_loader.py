"""`edge` çekirdek modüllerini (tek doğruluk kaynağı) ROS2 düğümlerine bağlar.

Keşif sırası:
  1. zaten import edilebiliyorsa (PYTHONPATH) -> hazır
  2. AEROPATCH_EDGE_PATH ortam değişkeni (edge/ dizininin PARENT klasörü)
  3. kaynak ağaç: ros_ws/src/aeropatch/aeropatch -> 5 seviye yukarı = proje kökü
     (colcon --symlink-install ile realpath kaynakta kalir)
  4. WSL sabit yedek: /mnt/d/.gemini/antigravity-ide/scratch/nebius
"""
from __future__ import annotations

import os
import sys

_FALLBACKS = [
    "/mnt/d/.gemini/antigravity-ide/scratch/nebius",
    "D:/.gemini/antigravity-ide/scratch/nebius",
]


def ensure_edge_modules(edge_path_param: str = "") -> None:
    try:
        import edge  # noqa: F401
        return
    except ImportError:
        pass
    candidates = []
    if edge_path_param:
        candidates.append(edge_path_param)
    env = os.environ.get("AEROPATCH_EDGE_PATH", "")
    if env:
        candidates.append(env)
    here = os.path.dirname(os.path.realpath(__file__))
    candidates.append(os.path.abspath(os.path.join(here, "..", "..", "..", "..", "..")))
    candidates.extend(_FALLBACKS)
    for c in candidates:
        if c and os.path.isdir(os.path.join(c, "edge")):
            sys.path.insert(0, c)
            return
    raise ImportError(
        "edge/ core modules not found. Set AEROPATCH_EDGE_PATH to the project root "
        "(folder containing 'edge/'), e.g. "
        "export AEROPATCH_EDGE_PATH=/mnt/d/.gemini/antigravity-ide/scratch/nebius")
