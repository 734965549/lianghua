"""Mock 模式冒烟：健康检查 + 核心只读 API（阶段 8 自动化验收辅助）。

用法（先启动后端）：
  cd backend
  .\.venv\Scripts\python.exe scripts\acceptance_smoke.py
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone

import httpx

BASE = "http://127.0.0.1:8000/api"


def main() -> int:
    failed = 0
    with httpx.Client(timeout=10.0) as client:
        checks = [
            ("GET", "/health", None),
            ("GET", "/system/status", None),
            ("GET", "/dashboard", None),
            ("GET", "/orders?page=1&page_size=5", None),
            ("GET", "/trades?page=1&page_size=5", None),
            ("GET", "/history/orders?page=1&page_size=5", None),
            ("GET", "/ai/reports?page=1&page_size=5", None),
            ("GET", "/risk/settings", None),
        ]
        print("=== Lianghua acceptance smoke ===")
        for method, path, body in checks:
            url = f"{BASE}{path}"
            try:
                if method == "GET":
                    r = client.get(url)
                else:
                    r = client.post(url, json=body or {})
                ok = r.status_code == 200 and r.json().get("success") is True
                status = "OK" if ok else f"FAIL {r.status_code}"
                print(f"  [{status}] {method} {path}")
                if not ok:
                    failed += 1
                    print(f"         body={r.text[:200]}")
            except Exception as exc:
                failed += 1
                print(f"  [FAIL] {method} {path}: {exc}")

        # 可选：生成一份当日空范围报告（无成交也应成功）
        now = datetime.now(timezone.utc)
        payload = {
            "range_start": (now - timedelta(hours=1)).isoformat(),
            "range_end": now.isoformat(),
            "strategy_ids": [],
            "markets": [],
            "symbols": [],
        }
        try:
            r = client.post(f"{BASE}/ai/reports", json=payload)
            ok = r.status_code == 200 and r.json().get("success") is True
            print(f"  [{'OK' if ok else 'FAIL'}] POST /ai/reports")
            if not ok:
                failed += 1
        except Exception as exc:
            failed += 1
            print(f"  [FAIL] POST /ai/reports: {exc}")

    if failed:
        print(f"\n失败 {failed} 项")
        return 1
    print("\n全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
