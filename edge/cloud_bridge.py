"""Kenar->bulut köprüsü: telemetri paketini yollar, yamayı geri getirir.

mock=True iken MockCloud'u kullanır (Nebius+Nemotron+Tavily simülasyonu);
mock=False iken Nebius Serverless Endpoint'ine HTTP POST atar.
"""
from __future__ import annotations

import time
from typing import Optional

from edge.mock_cloud import MockCloud
from edge.telemetry import PatchResponse, TelemetryPacket


class CloudBridgeError(RuntimeError):
    pass


class CloudBridge:
    def __init__(self, mock: bool = True, endpoint_url: str = "",
                 api_key: str = "", timeout_s: float = 8.0, retries: int = 2,
                 mock_cloud: Optional[MockCloud] = None):
        self.mock = bool(mock)
        self.endpoint_url = endpoint_url
        self.api_key = api_key
        self.timeout_s = float(timeout_s)
        self.retries = max(int(retries), 0)
        self.mock_cloud = mock_cloud or MockCloud()

    def request_patch(self, packet: TelemetryPacket) -> PatchResponse:
        t0 = time.perf_counter()
        payload = packet.to_dict()
        if self.mock:
            data = self.mock_cloud.handle(payload)
        else:
            data = self._post_with_retry(payload)
        latency_ms = (time.perf_counter() - t0) * 1000.0
        return PatchResponse.from_dict(data, latency_ms=latency_ms)

    def _headers(self) -> dict:
        h = {"Content-Type": "application/json"}
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        return h

    def _post_with_retry(self, payload: dict) -> dict:
        import requests  # lazy import: yalnızca gerçek bulut modunda gerekir
        last_error: Optional[Exception] = None
        for attempt in range(self.retries + 1):
            try:
                resp = requests.post(self.endpoint_url, json=payload,
                                     headers=self._headers(),
                                     timeout=self.timeout_s)
                if resp.status_code == 200:
                    return resp.json()
                last_error = CloudBridgeError(
                    f"HTTP {resp.status_code}: {resp.text[:200]}")
            except Exception as e:
                last_error = CloudBridgeError(f"cloud request failed: {e}")
            if attempt < self.retries:
                time.sleep(0.2 * (2 ** attempt))
        raise last_error or CloudBridgeError("unknown cloud error")
