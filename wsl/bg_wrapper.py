#!/usr/bin/env python3
"""Arka plan WSL sarmalayici v2: setsid+nohup ile tam detach.

Kullanim:
  wsl -d Ubuntu-22.04 -- python3 .../bg_wrapper.py <script.sh>
Log: /mnt/d/.../wsl/logs/<script>.log
"""
import os
import subprocess
import sys

WSL_DIR = "/mnt/d/.gemini/antigravity-ide/scratch/nebius/wsl"


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: bg_wrapper.py <script.sh>", flush=True)
        return 2
    script = sys.argv[1]
    src = os.path.join(WSL_DIR, script)
    log_dir = os.path.join(WSL_DIR, "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, script + ".log")
    with open(src, "rb") as f:
        data = f.read().replace(b"\r\n", b"\n")
    tmp = "/tmp/aeropatch_" + script.replace("/", "_")
    with open(tmp, "wb") as f:
        f.write(data)
    cmd = (f"setsid nohup bash {tmp} > {log_path} 2>&1 < /dev/null & "
           f"echo BG_PID=$!; exit 0")
    r = subprocess.run(["bash", "-c", cmd], timeout=20)
    print(f"[bg] launched script={script} log={log_path} rc={r.returncode}",
          flush=True)
    return r.returncode


if __name__ == "__main__":
    sys.exit(main())
