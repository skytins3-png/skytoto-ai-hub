# -*- coding: utf-8 -*-
"""
GitHub Actions / 서버용 자동 실행기
PC가 꺼져 있어도 클라우드에서 API 수집 → 분석 → Google Sheet 저장을 실행합니다.

필수 GitHub Secrets 예시:
- SKYTOTO_GOOGLE_SHEET_ID
- SKYTOTO_SERVICE_ACCOUNT_JSON
- SKYTOTO_SPORTS_API_URL
- SKYTOTO_SPORTS_API_KEY
"""

import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import (  # noqa: E402
    DEFAULT_SETTINGS,
    GoogleSheetHub,
    fetch_games_from_api,
    save_games,
    run_analysis,
    update_learning_from_results,
    kst_str,
)


def main() -> None:
    settings = DEFAULT_SETTINGS.copy()
    settings.update({
        "google_sheet_id": os.getenv("SKYTOTO_GOOGLE_SHEET_ID", ""),
        "service_account_json": os.getenv("SKYTOTO_SERVICE_ACCOUNT_JSON", ""),
        "sports_api_url": os.getenv("SKYTOTO_SPORTS_API_URL", ""),
        "sports_api_key": os.getenv("SKYTOTO_SPORTS_API_KEY", ""),
        "cloud_mode": True,
    })
    print(f"[{kst_str()}] SKYTOTO cloud runner start")
    hub = GoogleSheetHub(settings)
    if not hub.ready:
        print("Google Sheet hub not connected. Check secrets and sheet sharing permission.")
    games = fetch_games_from_api(settings)
    games_df = save_games(games, hub)
    rec_df = run_analysis(games_df, hub)
    learning = update_learning_from_results(hub)
    print(f"games={len(games_df)} recommendations={len(rec_df)} learning={learning}")
    print(f"[{kst_str()}] SKYTOTO cloud runner done")


if __name__ == "__main__":
    main()
