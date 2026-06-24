# -*- coding: utf-8 -*-
"""
SKYTOTO AI HUB
Sun · Moon · Star · Cloud · Rain · Earth Agents

주의:
- 이 앱은 스포츠 경기 데이터 분석, 기록, 모니터링 보조용입니다.
- 자동구매, 대리구매, 결제 자동 클릭 기능은 제공하지 않습니다.
- 구매 여부는 사용자가 공식 발매처에서 직접 판단하고, 앱에는 기록만 남깁니다.
"""

from __future__ import annotations

import json
import math
import os
import random
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import requests
import streamlit as st

try:
    import gspread
    from google.oauth2.service_account import Credentials
except Exception:  # gspread가 없어도 앱은 실행됨
    gspread = None
    Credentials = None

KST = timezone(timedelta(hours=9))
APP_NAME = "SKYTOTO AI HUB"
DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

FILES = {
    "settings": DATA_DIR / "settings.json",
    "games": DATA_DIR / "games.csv",
    "odds": DATA_DIR / "odds.csv",
    "team_stats": DATA_DIR / "team_stats.csv",
    "players": DATA_DIR / "players.csv",
    "prematch": DATA_DIR / "prematch_snapshot.csv",
    "lineups": DATA_DIR / "lineups.csv",
    "coach_tactics": DATA_DIR / "coach_tactics.csv",
    "match_stats": DATA_DIR / "match_stats.csv",
    "recommend": DATA_DIR / "recommend.csv",
    "purchase": DATA_DIR / "purchase_log.csv",
    "results": DATA_DIR / "results.csv",
    "result_review": DATA_DIR / "result_review.csv",
    "learning_memory": DATA_DIR / "learning_memory.csv",
    "learning": DATA_DIR / "learning.json",
    "errors": DATA_DIR / "error_log.csv",
    "api_diag": DATA_DIR / "api_diagnostics.json",
}

DEFAULT_SETTINGS = {
    "official_purchase_url": "https://www.betman.co.kr/",
    "google_sheet_id": "",
    "service_account_json": "",
    "sports_api_url": "",
    "sports_api_key": "",
    "auto_refresh_sec": 60,
    "min_confidence": 70,
    "max_risk": 55,
    "cloud_mode": False,
    "safe_mode": True,
}

DEFAULT_WEIGHTS = {
    "recent_form": 0.22,
    "odds_value": 0.18,
    "head_to_head": 0.12,
    "home_away": 0.10,
    "injury_lineup": 0.14,
    "coach_tactics": 0.10,
    "market_risk": 0.08,
    "risk_penalty": 0.06,
}

SHEETS = [
    "SETTINGS", "GAMES", "ODDS", "TEAM_STATS", "PLAYERS", "PRE_MATCH",
    "LINEUPS", "COACH_TACTICS", "MATCH_STATS", "RECOMMEND", "PURCHASE_LOG",
    "RESULTS", "RESULT_REVIEW", "LEARNING_MEMORY", "LEARNING", "ERROR_LOG"
]

# ----------------------------- 공통 유틸 -----------------------------

def now_kst() -> datetime:
    return datetime.now(KST)


def kst_str(dt: Optional[datetime] = None) -> str:
    dt = dt or now_kst()
    return dt.strftime("%Y-%m-%d %H:%M:%S KST")


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def read_csv(path: Path, columns: Optional[List[str]] = None) -> pd.DataFrame:
    if path.exists():
        try:
            return pd.read_csv(path)
        except Exception:
            pass
    return pd.DataFrame(columns=columns or [])


def write_csv(path: Path, df: pd.DataFrame) -> None:
    path.parent.mkdir(exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8-sig")


def append_csv(path: Path, row: Dict[str, Any]) -> None:
    old = read_csv(path)
    new = pd.concat([old, pd.DataFrame([row])], ignore_index=True)
    write_csv(path, new)


def log_error(area: str, message: str) -> None:
    append_csv(FILES["errors"], {"time": kst_str(), "area": area, "message": str(message)[:500]})


def pct(v: float) -> str:
    try:
        return f"{float(v):.1f}%"
    except Exception:
        return "-"


def clamp(v: float, lo: float = 0, hi: float = 100) -> float:
    return max(lo, min(hi, float(v)))

# ----------------------------- Google Sheet Hub -----------------------------

class GoogleSheetHub:
    def __init__(self, settings: Dict[str, Any]):
        self.settings = settings
        self.client = None
        self.sheet = None
        self.ready = False
        self.error = ""
        self._connect()

    def _connect(self) -> None:
        sid = self.settings.get("google_sheet_id", "").strip()
        raw = self.settings.get("service_account_json", "").strip()
        if not sid or not raw or gspread is None or Credentials is None:
            return
        try:
            info = json.loads(raw)
            scopes = [
                "https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/drive",
            ]
            creds = Credentials.from_service_account_info(info, scopes=scopes)
            self.client = gspread.authorize(creds)
            self.sheet = self.client.open_by_key(sid)
            self.ready = True
            self.ensure_sheets()
        except Exception as e:
            self.error = str(e)
            log_error("GoogleSheetHub", e)

    def ensure_sheets(self) -> None:
        if not self.ready:
            return
        existing = {ws.title for ws in self.sheet.worksheets()}
        for name in SHEETS:
            if name not in existing:
                self.sheet.add_worksheet(title=name, rows=2000, cols=30)

    def append(self, tab: str, row: Dict[str, Any]) -> bool:
        if not self.ready:
            return False
        try:
            ws = self.sheet.worksheet(tab)
            values = ws.get_all_values()
            headers = values[0] if values else []
            keys = list(row.keys())
            if not headers:
                ws.append_row(keys, value_input_option="USER_ENTERED")
                headers = keys
            for k in keys:
                if k not in headers:
                    headers.append(k)
                    ws.update(values=[headers], range_name="A1")
            ws.append_row([row.get(h, "") for h in headers], value_input_option="USER_ENTERED")
            return True
        except Exception as e:
            log_error(f"GoogleSheetHub.append.{tab}", e)
            return False

    def sync_dataframe(self, tab: str, df: pd.DataFrame) -> bool:
        if not self.ready:
            return False
        try:
            ws = self.sheet.worksheet(tab)
            ws.clear()
            if df.empty:
                ws.update(values=[["empty"]], range_name="A1")
            else:
                safe = df.replace([np.inf, -np.inf], np.nan).fillna("")
                ws.update(values=[safe.columns.tolist()] + safe.astype(str).values.tolist(), range_name="A1")
            return True
        except Exception as e:
            log_error(f"GoogleSheetHub.sync.{tab}", e)
            return False

# ----------------------------- 데이터 모델 -----------------------------

@dataclass
class Game:
    game_id: str
    league: str
    home_team: str
    away_team: str
    start_time: str
    market_type: str = "승무패"
    status: str = "예정"
    source: str = "sample_or_api"

@dataclass
class AgentResult:
    agent: str
    score: float
    risk: float
    summary: str
    details: Dict[str, Any]

# ----------------------------- API / 샘플 데이터 -----------------------------


def mask_secret(value: str, keep: int = 4) -> str:
    value = str(value or "")
    if not value:
        return ""
    if len(value) <= keep * 2:
        return "*" * len(value)
    return value[:keep] + "…" + value[-keep:]


def build_api_request(settings: Dict[str, Any]) -> Tuple[str, Dict[str, Any], Dict[str, str], str]:
    """URL 템플릿과 키를 실제 호출값으로 변환. 토큰 원문은 화면에 표시하지 않음."""
    url = settings.get("sports_api_url", "").strip()
    key = settings.get("sports_api_key", "").strip()
    today_dash = now_kst().strftime("%Y-%m-%d")
    today_plain = now_kst().strftime("%Y%m%d")
    final_url = (
        url.replace("{api_key}", key)
           .replace("{today_dash}", today_dash)
           .replace("{today}", today_plain)
    )
    params: Dict[str, Any] = {}
    headers: Dict[str, str] = {"Accept": "application/json"}
    if key and "{api_key}" not in url and "api_token=" not in final_url and "serviceKey" not in final_url:
        if "api.sportmonks.com" in final_url:
            params["api_token"] = key
        elif "api-sports.io" in final_url or "api-football" in final_url:
            headers["x-apisports-key"] = key
        else:
            params["api_key"] = key
    safe_url = final_url.replace(key, mask_secret(key)) if key else final_url
    return final_url, params, headers, safe_url


def save_api_diag(diag: Dict[str, Any]) -> None:
    try:
        save_json(FILES["api_diag"], diag)
    except Exception:
        pass


def load_api_diag() -> Dict[str, Any]:
    return load_json(FILES["api_diag"], {})


def test_sportmonks_api(settings: Dict[str, Any], allow_fallback_date: bool = True) -> Dict[str, Any]:
    """실제 Sportmonks/API 연결 상태를 화면에서 확인하기 위한 진단 함수."""
    url = settings.get("sports_api_url", "").strip()
    key = settings.get("sports_api_key", "").strip()
    diag: Dict[str, Any] = {
        "time": kst_str(),
        "provider": settings.get("sports_api_provider") or "sportmonks" if "sportmonks" in url else "custom",
        "token_detected": bool(key),
        "token_preview": mask_secret(key),
        "url_template": url,
        "status": "not_started",
        "http_status": "",
        "safe_final_url": "",
        "params_keys": [],
        "response_data_count": 0,
        "normalized_games_count": 0,
        "sample_fallback": False,
        "message": "",
        "first_game": {},
        "response_preview": "",
    }
    if not url:
        diag.update(status="error", message="스포츠 API URL 템플릿이 비어 있습니다.", sample_fallback=True)
        save_api_diag(diag)
        return diag
    if not key:
        diag.update(status="error", message="스포츠 API KEY/SPORTMONKS_API_TOKEN이 비어 있습니다.", sample_fallback=True)
        save_api_diag(diag)
        return diag

    candidate_settings = [settings.copy()]
    # 오늘 경기 데이터가 없을 때 원인 확인을 쉽게 하려고 내일/7일치도 자동 테스트 가능하게 함.
    if allow_fallback_date and "fixtures/date/{today_dash}" in url:
        tomorrow = (now_kst() + timedelta(days=1)).strftime("%Y-%m-%d")
        week_end = (now_kst() + timedelta(days=7)).strftime("%Y-%m-%d")
        s2 = settings.copy()
        s2["sports_api_url"] = url.replace("/fixtures/date/{today_dash}", f"/fixtures/date/{tomorrow}")
        candidate_settings.append(s2)
        s3 = settings.copy()
        s3["sports_api_url"] = url.replace("/fixtures/date/{today_dash}", f"/fixtures/between/{now_kst().strftime('%Y-%m-%d')}/{week_end}")
        candidate_settings.append(s3)

    last_error = ""
    for idx, cand in enumerate(candidate_settings, start=1):
        try:
            final_url, params, headers, safe_url = build_api_request(cand)
            diag["safe_final_url"] = safe_url
            diag["params_keys"] = list(params.keys())
            diag["attempt"] = idx
            r = requests.get(final_url, params=params, headers=headers, timeout=18)
            diag["http_status"] = int(r.status_code)
            text = r.text or ""
            diag["response_preview"] = text[:900]
            try:
                data = r.json()
            except Exception:
                data = {"raw_text": text[:900]}
            if isinstance(data, dict):
                raw_items = data.get("data") or data.get("response") or data.get("items") or data.get("games") or []
                diag["response_data_count"] = len(raw_items) if isinstance(raw_items, list) else (1 if raw_items else 0)
                if "message" in data:
                    diag["api_message"] = data.get("message")
                if "error" in data:
                    diag["api_error"] = data.get("error")
                if "errors" in data:
                    diag["api_errors"] = data.get("errors")
            elif isinstance(data, list):
                diag["response_data_count"] = len(data)
            if r.status_code >= 400:
                last_error = f"HTTP {r.status_code}: {diag.get('api_message') or diag.get('api_error') or text[:300]}"
                continue
            games = normalize_api_items(data)
            diag["normalized_games_count"] = len(games)
            if games:
                g = games[0]
                diag["status"] = "success"
                diag["message"] = "Sportmonks/API 실제 경기 데이터 연결 성공"
                diag["first_game"] = asdict(g)
                diag["source"] = g.source
                save_api_diag(diag)
                return diag
            last_error = "HTTP는 성공했지만 participants/팀명 파싱 결과가 0건입니다. include 권한 또는 플랜 데이터 범위를 확인하세요."
        except Exception as e:
            last_error = str(e)
            diag["message"] = last_error
    diag.update(status="error", message=last_error or "API 경기 데이터를 찾지 못했습니다.", sample_fallback=True)
    save_api_diag(diag)
    return diag

def fetch_games_from_api(settings: Dict[str, Any]) -> List[Game]:
    """사용자가 API URL을 넣으면 JSON을 읽고, 실패하면 샘플 데이터로 안전 전환.

    Sportmonks 전용 형식도 같이 처리합니다.
    - URL 예: https://api.sportmonks.com/v3/football/fixtures/date/{today_dash}?api_token={api_key}&include=participants;league
    - {today_dash} = YYYY-MM-DD
    - {today} = YYYYMMDD
    """
    url = settings.get("sports_api_url", "").strip()
    key = settings.get("sports_api_key", "").strip()
    if not url:
        save_api_diag({"time": kst_str(), "status": "sample", "message": "API URL이 비어 있어 샘플 사용", "sample_fallback": True})
        return make_sample_games()
    if not key:
        save_api_diag({"time": kst_str(), "status": "sample", "message": "API KEY가 비어 있어 샘플 사용", "sample_fallback": True})
        return make_sample_games()
    try:
        diag = test_sportmonks_api(settings, allow_fallback_date=True)
        if diag.get("status") != "success":
            raise ValueError(diag.get("message") or "API 진단 실패")
        final_url, params, headers, _safe_url = build_api_request(settings)
        r = requests.get(final_url, params=params, headers=headers, timeout=18)
        r.raise_for_status()
        data = r.json()
        items = normalize_api_items(data)
        if not items:
            # 진단에서 내일/7일치가 잡혔으면 그 데이터라도 사용
            if diag.get("safe_final_url") and diag.get("attempt", 1) > 1:
                test_settings = settings.copy()
                safe = str(diag.get("safe_final_url", ""))
                # 보안 때문에 safe URL은 실제 호출에 쓰지 않고 진단 재시도 결과만 안내
            raise ValueError("API 응답에서 경기 목록을 찾지 못했습니다. 허브/검사 → Sportmonks API 연결 테스트를 확인하세요.")
        save_api_diag({**diag, "used_for_analysis": True, "analysis_games_count": len(items)})
        return items
    except Exception as e:
        log_error("fetch_games_from_api", e)
        save_api_diag({**load_api_diag(), "time": kst_str(), "status": "sample", "message": str(e), "sample_fallback": True})
        return make_sample_games()


def _name_from_obj(obj: Any) -> str:
    if isinstance(obj, str):
        return obj
    if not isinstance(obj, dict):
        return ""
    return str(
        obj.get("name")
        or obj.get("display_name")
        or obj.get("short_code")
        or obj.get("common_name")
        or obj.get("team_name")
        or ""
    )


def _sportmonks_participants_to_teams(participants: Any) -> Tuple[str, str]:
    """Sportmonks participants 배열에서 홈/원정 팀명을 추출."""
    home = ""
    away = ""
    if isinstance(participants, dict):
        participants = participants.get("data") or participants.get("items") or []
    if not isinstance(participants, list):
        return home, away

    fallback: List[str] = []
    for p in participants:
        if not isinstance(p, dict):
            continue
        name = _name_from_obj(p)
        if not name and isinstance(p.get("team"), dict):
            name = _name_from_obj(p.get("team"))
        meta = p.get("meta") if isinstance(p.get("meta"), dict) else {}
        loc = str(
            meta.get("location")
            or p.get("location")
            or p.get("venue")
            or p.get("type")
            or ""
        ).lower()
        if name:
            fallback.append(name)
        if loc == "home":
            home = name
        elif loc == "away":
            away = name

    if not home and fallback:
        home = fallback[0]
    if not away and len(fallback) > 1:
        away = fallback[1]
    return home, away


def normalize_api_items(data: Any) -> List[Game]:
    """여러 API 응답 형태를 최대한 넓게 흡수. Sportmonks v3 포함."""
    if isinstance(data, dict):
        for key in ["items", "games", "matches", "data", "list", "body"]:
            if key in data:
                found = normalize_api_items(data[key])
                if found:
                    return found
        if "response" in data:
            return normalize_api_items(data["response"])

    if isinstance(data, list):
        games: List[Game] = []
        for i, x in enumerate(data):
            if not isinstance(x, dict):
                continue

            # 일반 API 형태
            home = x.get("home_team") or x.get("home") or x.get("homeTeam") or x.get("team1") or x.get("hTeam")
            away = x.get("away_team") or x.get("away") or x.get("awayTeam") or x.get("team2") or x.get("aTeam")

            # Sportmonks v3: participants 안에 홈/원정 팀이 들어감
            if (not home or not away) and "participants" in x:
                home, away = _sportmonks_participants_to_teams(x.get("participants"))

            # 일부 API: localteam/visitorteam 형태
            if not home:
                home = _name_from_obj(x.get("localteam") or x.get("home_team"))
            if not away:
                away = _name_from_obj(x.get("visitorteam") or x.get("away_team"))

            if not home or not away:
                continue

            start = (
                x.get("starting_at")
                or x.get("start_time")
                or x.get("startTime")
                or x.get("game_time")
                or x.get("date")
                or kst_str(now_kst() + timedelta(hours=i + 2))
            )
            league_obj = x.get("league") or x.get("competition") or x.get("sports")
            league = _name_from_obj(league_obj) or str(league_obj or "Football")
            gid = str(x.get("game_id") or x.get("fixture_id") or x.get("id") or f"API-{i}-{home}-{away}")
            games.append(Game(gid, league, str(home), str(away), str(start), source="sportmonks" if "participants" in x else "api"))
        return games
    return []


def make_sample_games() -> List[Game]:
    base = now_kst().replace(minute=0, second=0, microsecond=0)
    samples = [
        ("K리그", "A팀", "B팀", 2),
        ("KBO", "해팀", "달팀", 3),
        ("EPL", "별팀", "구름팀", 5),
        ("J리그", "비팀", "땅팀", 7),
    ]
    games = []
    for i, (lg, h, a, addh) in enumerate(samples, 1):
        dt = base + timedelta(hours=addh)
        games.append(Game(f"SAMPLE-{now_kst().strftime('%Y%m%d')}-{i}", lg, h, a, dt.strftime("%Y-%m-%d %H:%M:%S KST"), source="sample"))
    return games


def save_games(games: List[Game], hub: Optional[GoogleSheetHub]) -> pd.DataFrame:
    df_old = read_csv(FILES["games"])
    df_new = pd.DataFrame([asdict(g) for g in games])
    if df_old.empty:
        merged = df_new
    else:
        merged = pd.concat([df_old, df_new], ignore_index=True).drop_duplicates("game_id", keep="last")
    write_csv(FILES["games"], merged)
    if hub and hub.ready:
        hub.sync_dataframe("GAMES", merged)
    return merged

# ----------------------------- 에이전트 -----------------------------

def deterministic_rng(game_id: str) -> random.Random:
    seed = abs(hash(game_id)) % (2**32)
    return random.Random(seed)


def sun_agent(game: Dict[str, Any]) -> AgentResult:
    try:
        stime = str(game.get("start_time", ""))
        risk = 10
        summary = "일정 정상 / 마감 전 분석 가능"
        if "KST" not in stime:
            risk += 8
            summary = "시간 표기 확인 필요"
        return AgentResult("Sun", 78, risk, summary, {"start_time": stime, "status": game.get("status", "")})
    except Exception as e:
        return AgentResult("Sun", 50, 50, f"일정 분석 오류: {e}", {})


def moon_agent(game: Dict[str, Any]) -> AgentResult:
    rng = deterministic_rng(str(game.get("game_id", "")) + "moon")
    open_odds = round(rng.uniform(1.55, 3.10), 2)
    current_odds = round(open_odds + rng.uniform(-0.35, 0.30), 2)
    change = round(current_odds - open_odds, 2)
    value_score = clamp(72 + (open_odds - 1.7) * 12 - abs(change) * 22)
    risk = clamp(25 + abs(change) * 55)
    if current_odds < 1.35:
        risk += 15
    summary = f"초기 {open_odds} → 현재 {current_odds}, 변화 {change:+.2f}"
    return AgentResult("Moon", value_score, risk, summary, {"open_odds": open_odds, "current_odds": current_odds, "change": change})


def star_agent(game: Dict[str, Any]) -> AgentResult:
    rng = deterministic_rng(str(game.get("game_id", "")) + "star")
    home_recent = rng.randint(1, 5)
    away_recent = rng.randint(0, 4)
    h2h = rng.randint(0, 5)
    home_adv = rng.randint(55, 78)
    score = clamp(45 + home_recent * 7 - away_recent * 4 + h2h * 3 + (home_adv - 55) * 0.6)
    summary = f"홈 최근승 {home_recent}/5, 원정 최근승 {away_recent}/5, 상대우세 {h2h}/5"
    details = {
        "home_recent_wins_5": home_recent,
        "away_recent_wins_5": away_recent,
        "head_to_head_home_wins_5": h2h,
        "home_strength": home_adv,
        "coach_note": "감독 변화 없음(외부 API 연결 시 자동 갱신)",
        "starter_note": "예상 주전 확인 대기(경기 직전 재확인 필요)",
    }
    return AgentResult("Star", score, 28, summary, details)


def rain_agent(game: Dict[str, Any]) -> AgentResult:
    rng = deterministic_rng(str(game.get("game_id", "")) + "rain")
    injury_count = rng.randint(0, 3)
    suspended = rng.randint(0, 2)
    coach_change = rng.choice([False, False, False, True])
    lineup_confirmed = rng.choice([False, True, True])
    risk = 18 + injury_count * 12 + suspended * 10 + (18 if coach_change else 0) + (12 if not lineup_confirmed else 0)
    score = clamp(88 - risk)
    summary = f"부상 {injury_count}, 징계 {suspended}, 선발확정 {'완료' if lineup_confirmed else '대기'}"
    return AgentResult("Rain", score, clamp(risk), summary, {
        "injury_count": injury_count,
        "suspended_count": suspended,
        "coach_change_recent": coach_change,
        "lineup_confirmed": lineup_confirmed,
    })


def earth_learning_load() -> Dict[str, Any]:
    return load_json(FILES["learning"], {"weights": DEFAULT_WEIGHTS, "history_count": 0, "note": "초기 가중치"})


def earth_agent(game: Dict[str, Any], base_score: float, risk: float) -> AgentResult:
    learning = earth_learning_load()
    weights = learning.get("weights", DEFAULT_WEIGHTS)
    history_count = int(learning.get("history_count", 0))
    stability_bonus = min(6, history_count / 50)
    score = clamp(base_score + stability_bonus - max(0, risk - 55) * 0.25)
    summary = f"누적 학습 {history_count}건, 현재 가중치 적용"
    return AgentResult("Earth", score, risk, summary, {"weights": weights, "history_count": history_count})


def analyze_game(game: Dict[str, Any]) -> Dict[str, Any]:
    sun = sun_agent(game)
    moon = moon_agent(game)
    star = star_agent(game)
    rain = rain_agent(game)
    weights = earth_learning_load().get("weights", DEFAULT_WEIGHTS)

    injury_lineup_score = rain.score
    coach_tactics_score = 100 - (25 if rain.details.get("coach_change_recent") else 0)
    market_risk_score = 100 - moon.risk
    base = (
        star.score * weights.get("recent_form", 0.22)
        + moon.score * weights.get("odds_value", 0.18)
        + star.details.get("head_to_head_home_wins_5", 2.5) / 5 * 100 * weights.get("head_to_head", 0.12)
        + star.details.get("home_strength", 60) * weights.get("home_away", 0.10)
        + injury_lineup_score * weights.get("injury_lineup", 0.14)
        + coach_tactics_score * weights.get("coach_tactics", 0.10)
        + market_risk_score * weights.get("market_risk", 0.08)
        + rain.score * weights.get("risk_penalty", 0.06)
    )
    risk = clamp((sun.risk + moon.risk + rain.risk) / 3)
    earth = earth_agent(game, base, risk)
    confidence = clamp(earth.score)

    if confidence >= 80 and risk <= 45:
        grade = "강추천"
    elif confidence >= 70 and risk <= 60:
        grade = "추천"
    elif confidence >= 60:
        grade = "관망"
    else:
        grade = "제외"

    if rain.details.get("lineup_confirmed") is False:
        final_note = "최종 선발 확인 전: 추천 확정 아님"
    else:
        final_note = "선발 확인 완료 또는 변수 낮음"

    pick = f"{game.get('home_team')} 우세" if grade != "제외" else "구매 제외"
    reason = " / ".join([sun.summary, moon.summary, star.summary, rain.summary, earth.summary])
    row = {
        "created_at": kst_str(),
        "game_id": game.get("game_id"),
        "league": game.get("league"),
        "home_team": game.get("home_team"),
        "away_team": game.get("away_team"),
        "start_time": game.get("start_time"),
        "pick": pick,
        "grade": grade,
        "confidence": round(confidence, 1),
        "risk_level": round(risk, 1),
        "expected_value_note": "배당가치/위험도 기반 후보. 수익 보장 아님.",
        "final_note": final_note,
        "reason": reason,
        "sun": json.dumps(asdict(sun), ensure_ascii=False),
        "moon": json.dumps(asdict(moon), ensure_ascii=False),
        "star": json.dumps(asdict(star), ensure_ascii=False),
        "rain": json.dumps(asdict(rain), ensure_ascii=False),
        "earth": json.dumps(asdict(earth), ensure_ascii=False),
    }
    return row


def run_analysis(games_df: pd.DataFrame, hub: Optional[GoogleSheetHub]) -> pd.DataFrame:
    rows = []
    for _, game in games_df.iterrows():
        try:
            gdict = game.to_dict()
            rec = analyze_game(gdict)
            rows.append(rec)
            save_agent_bigdata(gdict, rec, hub)
        except Exception as e:
            log_error("run_analysis", e)
    rec_df = pd.DataFrame(rows)
    old = read_csv(FILES["recommend"])
    merged = pd.concat([old, rec_df], ignore_index=True) if not old.empty else rec_df
    if not merged.empty:
        merged = merged.drop_duplicates("game_id", keep="last")
    write_csv(FILES["recommend"], merged)
    if hub and hub.ready:
        hub.sync_dataframe("RECOMMEND", merged)
    return merged


# ----------------------------- 경기별 빅데이터 저장 / 원인 분석 -----------------------------

def _safe_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, default=str)


def save_agent_bigdata(game: Dict[str, Any], rec: Dict[str, Any], hub: Optional[GoogleSheetHub]) -> None:
    """모든 경기마다 경기 전 스냅샷, 배당, 선수/감독/위험 데이터를 남김."""
    try:
        gid = str(game.get("game_id"))
        sun = json.loads(rec.get("sun", "{}")) if rec.get("sun") else {}
        moon = json.loads(rec.get("moon", "{}")) if rec.get("moon") else {}
        star = json.loads(rec.get("star", "{}")) if rec.get("star") else {}
        rain = json.loads(rec.get("rain", "{}")) if rec.get("rain") else {}

        prematch_row = {
            "captured_at": kst_str(),
            "game_id": gid,
            "league": game.get("league"),
            "home_team": game.get("home_team"),
            "away_team": game.get("away_team"),
            "start_time": game.get("start_time"),
            "market_type": game.get("market_type", "승무패"),
            "ai_pick": rec.get("pick"),
            "grade": rec.get("grade"),
            "confidence": rec.get("confidence"),
            "risk_level": rec.get("risk_level"),
            "reason": rec.get("reason"),
            "source": game.get("source", "sample_or_api"),
        }
        append_csv(FILES["prematch"], prematch_row)
        append_csv(FILES["odds"], {
            "captured_at": kst_str(), "game_id": gid,
            "open_odds": moon.get("details", {}).get("open_odds", ""),
            "current_odds": moon.get("details", {}).get("current_odds", ""),
            "odds_change": moon.get("details", {}).get("change", ""),
            "market_summary": moon.get("summary", ""),
        })
        append_csv(FILES["team_stats"], {
            "captured_at": kst_str(), "game_id": gid,
            "home_recent_wins_5": star.get("details", {}).get("home_recent_wins_5", ""),
            "away_recent_wins_5": star.get("details", {}).get("away_recent_wins_5", ""),
            "head_to_head_home_wins_5": star.get("details", {}).get("head_to_head_home_wins_5", ""),
            "home_strength": star.get("details", {}).get("home_strength", ""),
            "team_summary": star.get("summary", ""),
        })
        append_csv(FILES["lineups"], {
            "captured_at": kst_str(), "game_id": gid,
            "injury_count": rain.get("details", {}).get("injury_count", ""),
            "suspended_count": rain.get("details", {}).get("suspended_count", ""),
            "lineup_confirmed": rain.get("details", {}).get("lineup_confirmed", ""),
            "starter_note": star.get("details", {}).get("starter_note", ""),
            "risk_summary": rain.get("summary", ""),
        })
        append_csv(FILES["coach_tactics"], {
            "captured_at": kst_str(), "game_id": gid,
            "coach_change_recent": rain.get("details", {}).get("coach_change_recent", ""),
            "coach_note": star.get("details", {}).get("coach_note", ""),
            "tactics_note": "외부 선발/포메이션 API 연결 시 자동 갱신. 현재는 경기 후 리뷰에서 수동 보강 가능.",
        })
        if hub and hub.ready:
            hub.append("PRE_MATCH", prematch_row)
            for tab, fname in [("ODDS", "odds"), ("TEAM_STATS", "team_stats"), ("LINEUPS", "lineups"), ("COACH_TACTICS", "coach_tactics")]:
                df = read_csv(FILES[fname])
                hub.sync_dataframe(tab, df)
    except Exception as e:
        log_error("save_agent_bigdata", e)


def infer_result_causes(row: Dict[str, Any]) -> Tuple[str, str, str]:
    """경기 후 입력값으로 패배/승리 원인을 구조화."""
    causes = []
    learning_actions = []
    risk_tags = []

    def add(cond: bool, cause: str, action: str, tag: str) -> None:
        if cond:
            causes.append(cause)
            learning_actions.append(action)
            risk_tags.append(tag)

    hit = str(row.get("hit", "")).strip() == "적중"
    final_score = str(row.get("final_score", ""))
    red_card = int(float(row.get("red_card", 0) or 0))
    key_injury = int(float(row.get("key_injury", 0) or 0))
    lineup_issue = str(row.get("lineup_issue", "")).strip()
    coach_issue = str(row.get("coach_issue", "")).strip()
    odds_issue = str(row.get("odds_issue", "")).strip()
    fatigue_weather = str(row.get("fatigue_weather", "")).strip()
    data_issue = str(row.get("data_issue", "")).strip()

    add(key_injury > 0, f"핵심 선수 부상/결장 {key_injury}명 영향", "injury_lineup 가중치 강화", "injury")
    add(bool(lineup_issue), f"선발/로테이션 변수: {lineup_issue}", "선발확정 전 추천 강도 하향", "lineup")
    add(bool(coach_issue), f"감독/전술 변수: {coach_issue}", "coach_tactics 가중치 강화", "coach")
    add(bool(odds_issue), f"배당/시장 변수: {odds_issue}", "market_risk 가중치 강화", "odds")
    add(red_card > 0, f"퇴장/카드 변수 {red_card}건", "퇴장 발생 경기는 사후 예외 처리", "red_card")
    add(bool(fatigue_weather), f"체력/날씨/원정 변수: {fatigue_weather}", "위험 차단 조건 강화", "weather_fatigue")
    add(bool(data_issue), f"데이터 부족/오류: {data_issue}", "데이터 부족 경기 추천 제한", "data_missing")

    if not causes:
        if hit:
            causes.append("예측 방향과 경기 흐름이 일치")
            learning_actions.append("현재 성공 패턴 유지")
            risk_tags.append("success_pattern")
        else:
            causes.append("명확한 원인 미입력: 영상/뉴스/선발/배당 재검토 필요")
            learning_actions.append("미확인 실패 패턴으로 보수 조정")
            risk_tags.append("unknown_failure")

    summary = ("적중 원인" if hit else "실패 원인") + f" / 최종스코어 {final_score}: " + " | ".join(causes)
    action = " | ".join(dict.fromkeys(learning_actions))
    tags = ",".join(dict.fromkeys(risk_tags))
    return summary, action, tags


def save_result_review(result_row: Dict[str, Any], hub: Optional[GoogleSheetHub]) -> Dict[str, Any]:
    """경기 결과 입력 후 왜 맞고 틀렸는지 리뷰를 남김."""
    summary, action, tags = infer_result_causes(result_row)
    review = {
        "reviewed_at": kst_str(),
        "game_id": result_row.get("game_id"),
        "hit": result_row.get("hit"),
        "final_score": result_row.get("final_score", ""),
        "profit_loss": result_row.get("profit_loss", 0),
        "cause_summary": summary,
        "learning_action": action,
        "risk_tags": tags,
        "coach_issue": result_row.get("coach_issue", ""),
        "lineup_issue": result_row.get("lineup_issue", ""),
        "odds_issue": result_row.get("odds_issue", ""),
        "memo": result_row.get("memo", ""),
    }
    append_csv(FILES["result_review"], review)
    append_csv(FILES["learning_memory"], {
        "time": kst_str(),
        "game_id": result_row.get("game_id"),
        "memory_type": "success" if result_row.get("hit") == "적중" else "failure",
        "risk_tags": tags,
        "learning_action": action,
        "applied_next": "다음 update_learning_from_results 실행 시 가중치 반영",
    })
    if hub and hub.ready:
        hub.append("RESULT_REVIEW", review)
        hub.sync_dataframe("LEARNING_MEMORY", read_csv(FILES["learning_memory"]))
    return review

# ----------------------------- 학습 업데이트 -----------------------------

def update_learning_from_results(hub: Optional[GoogleSheetHub]) -> Dict[str, Any]:
    rec = read_csv(FILES["recommend"])
    res = read_csv(FILES["results"])
    reviews = read_csv(FILES["result_review"])
    if rec.empty or res.empty or "game_id" not in rec or "game_id" not in res:
        return earth_learning_load()
    df = rec.merge(res, on="game_id", how="inner", suffixes=("_rec", "_res"))
    if df.empty:
        return earth_learning_load()

    learning = earth_learning_load()
    weights = learning.get("weights", DEFAULT_WEIGHTS).copy()
    # 새 항목이 없으면 기본 가중치와 합침
    for k, v in DEFAULT_WEIGHTS.items():
        weights.setdefault(k, v)

    hits = 0
    total = 0
    profit = 0.0
    for _, row in df.iterrows():
        total += 1
        hit = str(row.get("hit", "")).strip() == "적중"
        if hit:
            hits += 1
        try:
            profit += float(row.get("profit_loss", 0) or 0)
        except Exception:
            pass
    hit_rate = hits / total if total else 0

    # 리뷰 태그 기반 학습: 틀린 원인은 다음 추천에서 위험가중치 강화
    tag_text = ""
    if not reviews.empty and "risk_tags" in reviews:
        tag_text = ",".join(reviews["risk_tags"].dropna().astype(str).tolist()).lower()
    failure_count = 0
    if not reviews.empty and "hit" in reviews:
        failure_count = int((reviews["hit"].astype(str) == "미적중").sum())

    def bump(key: str, amount: float, lo: float = 0.03, hi: float = 0.30) -> None:
        weights[key] = min(hi, max(lo, weights.get(key, DEFAULT_WEIGHTS.get(key, 0.1)) + amount))

    if hit_rate >= 0.58 and profit >= 0:
        bump("recent_form", 0.006)
        bump("odds_value", 0.004)
    else:
        bump("risk_penalty", 0.008)
        bump("market_risk", 0.006)

    if "injury" in tag_text or "lineup" in tag_text:
        bump("injury_lineup", 0.012)
        bump("risk_penalty", 0.006)
    if "coach" in tag_text:
        bump("coach_tactics", 0.010)
    if "odds" in tag_text:
        bump("market_risk", 0.010)
        bump("odds_value", -0.004)
    if "data_missing" in tag_text or "unknown_failure" in tag_text:
        bump("risk_penalty", 0.010)

    # 합계 1로 정규화
    ssum = sum(max(0.001, float(v)) for v in weights.values())
    weights = {k: round(max(0.001, float(v)) / ssum, 4) for k, v in weights.items()}
    learning = {
        "updated_at": kst_str(),
        "weights": weights,
        "history_count": int(total),
        "review_count": int(len(reviews)) if not reviews.empty else 0,
        "failure_review_count": failure_count,
        "hit_rate": round(hit_rate * 100, 2),
        "profit_loss_sum": round(profit, 2),
        "note": "Earth Agent: 결과·원인리뷰·위험태그를 반영해 다음 경기 가중치 조정",
    }
    save_json(FILES["learning"], learning)
    if hub and hub.ready:
        hub.append("LEARNING", learning)
    return learning

# ----------------------------- UI -----------------------------

def load_settings() -> Dict[str, Any]:
    data = load_json(FILES["settings"], DEFAULT_SETTINGS.copy())
    merged = DEFAULT_SETTINGS.copy()
    merged.update(data)

    # Streamlit Cloud Secrets / GitHub Actions 환경변수 자동 반영
    # 화면 입력이 비어 있어도 Secrets에 넣어둔 토큰으로 작동하게 함.
    try:
        secrets = st.secrets
    except Exception:
        secrets = {}

    sportmonks_token = (
        str(secrets.get("SPORTMONKS_API_TOKEN", "")).strip()
        if hasattr(secrets, "get") else ""
    ) or os.getenv("SPORTMONKS_API_TOKEN", "").strip()

    sports_key = (
        str(secrets.get("SKYTOTO_SPORTS_API_KEY", "")).strip()
        if hasattr(secrets, "get") else ""
    ) or os.getenv("SKYTOTO_SPORTS_API_KEY", "").strip()

    sports_url = (
        str(secrets.get("SKYTOTO_SPORTS_API_URL", "")).strip()
        if hasattr(secrets, "get") else ""
    ) or os.getenv("SKYTOTO_SPORTS_API_URL", "").strip()

    if sportmonks_token and not merged.get("sports_api_key"):
        merged["sports_api_key"] = sportmonks_token
    elif sports_key and not merged.get("sports_api_key"):
        merged["sports_api_key"] = sports_key

    if sports_url and not merged.get("sports_api_url"):
        merged["sports_api_url"] = sports_url
    elif sportmonks_token and not merged.get("sports_api_url"):
        merged["sports_api_url"] = "https://api.sportmonks.com/v3/football/fixtures/date/{today_dash}?api_token={api_key}&include=participants;league"

    return merged


def save_settings(data: Dict[str, Any]) -> None:
    save_json(FILES["settings"], data)


def render_header() -> None:
    st.set_page_config(page_title=APP_NAME, page_icon="☀️", layout="wide")
    st.markdown(
        """
        <style>
        .main-title {font-size: 2.1rem; font-weight: 900; margin-bottom: 0.2rem;}
        .agent-badge {display:inline-block; padding:6px 10px; border-radius:999px; background:#1f2937; margin:3px; font-weight:700;}
        .big-card {border:1px solid #334155; border-radius:18px; padding:18px; background:#111827; margin-bottom:14px;}
        .warn {border-left:6px solid #f59e0b; padding:12px; background:#1f2937; border-radius:12px;}
        .good {border-left:6px solid #22c55e; padding:12px; background:#102018; border-radius:12px;}
        .bad {border-left:6px solid #ef4444; padding:12px; background:#211010; border-radius:12px;}
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(f"<div class='main-title'>{APP_NAME}</div>", unsafe_allow_html=True)
    st.markdown(
        "<span class='agent-badge'>☀️ Sun 일정</span>"
        "<span class='agent-badge'>🌙 Moon 배당</span>"
        "<span class='agent-badge'>⭐ Star 전력</span>"
        "<span class='agent-badge'>☁️ Cloud 저장</span>"
        "<span class='agent-badge'>🌧️ Rain 위험</span>"
        "<span class='agent-badge'>🌍 Earth 학습</span>",
        unsafe_allow_html=True,
    )
    st.caption("분석·기록·학습 보조 시스템입니다. 자동구매/결제 자동화 기능은 제공하지 않습니다.")


def sidebar_settings() -> Tuple[Dict[str, Any], GoogleSheetHub]:
    settings = load_settings()
    with st.sidebar:
        st.header("설정")
        settings["official_purchase_url"] = st.text_input("공식 구매처 URL", settings.get("official_purchase_url", ""))
        settings["sports_api_url"] = st.text_area("스포츠 API URL 템플릿", settings.get("sports_api_url", ""), height=90)
        settings["sports_api_key"] = st.text_input("스포츠 API KEY", settings.get("sports_api_key", ""), type="password")
        settings["google_sheet_id"] = st.text_input("Google Sheet ID", settings.get("google_sheet_id", ""))
        settings["service_account_json"] = st.text_area("Service Account JSON", settings.get("service_account_json", ""), height=120)
        settings["auto_refresh_sec"] = st.selectbox("자동 새로고침", [0, 30, 60, 120, 300], index=[0,30,60,120,300].index(int(settings.get("auto_refresh_sec", 60))))
        settings["min_confidence"] = st.slider("추천 최소 신뢰도", 50, 90, int(settings.get("min_confidence", 70)))
        settings["max_risk"] = st.slider("허용 위험도", 20, 80, int(settings.get("max_risk", 55)))
        settings["max_daily_recommend"] = st.slider("하루 표시 추천 수", 1, 5, int(settings.get("max_daily_recommend", 2)))
        settings["cloud_mode"] = st.toggle("허브/구글시트 모드", bool(settings.get("cloud_mode", False)))
        settings["safe_mode"] = st.toggle("안전모드: 자동구매 차단", True, disabled=True)
        if st.button("설정 저장", width="stretch"):
            save_settings(settings)
            st.success("설정 저장 완료")
        if st.button("데이터 수집 + 분석 실행", width="stretch"):
            st.session_state["run_now"] = True
    hub = GoogleSheetHub(settings) if settings.get("cloud_mode") else GoogleSheetHub({})
    return settings, hub


def render_status(settings: Dict[str, Any], hub: GoogleSheetHub) -> None:
    cols = st.columns(4)
    cols[0].metric("현재시간", now_kst().strftime("%H:%M:%S"))
    cols[1].metric("허브 상태", "연결" if hub.ready else "로컬")
    cols[2].metric("자동구매", "차단")
    cols[3].metric("저장 위치", "Google Sheet" if hub.ready else "data 폴더")
    if hub.error:
        st.warning(f"구글시트 연결 실패: {hub.error}")


def render_mobile_recommendations(settings: Dict[str, Any], rec_df: pd.DataFrame) -> None:
    st.subheader("📱 모바일 추천 결과")
    if rec_df.empty:
        st.info("아직 추천 결과가 없습니다. 사이드바에서 데이터 수집 + 분석 실행을 누르세요.")
        return
    filtered = rec_df.copy()
    filtered["confidence"] = pd.to_numeric(filtered["confidence"], errors="coerce").fillna(0)
    filtered["risk_level"] = pd.to_numeric(filtered["risk_level"], errors="coerce").fillna(100)
    filtered = filtered.sort_values(["confidence", "risk_level"], ascending=[False, True])
    filtered = filtered[(filtered["confidence"] >= int(settings.get("min_confidence", 75))) | (filtered["grade"].isin(["강추천", "추천"]))]
    filtered = filtered[filtered["risk_level"] <= int(settings.get("max_risk", 55))]
    if filtered.empty:
        st.warning("안전모드 기준을 통과한 추천이 없습니다. 관망이 수익 보호입니다.")
        return
    for _, row in filtered.head(int(settings.get("max_daily_recommend", 2))).iterrows():
        grade = row.get("grade", "")
        klass = "good" if grade == "강추천" else "warn" if grade in ["추천", "관망"] else "bad"
        st.markdown(f"<div class='{klass}'>", unsafe_allow_html=True)
        st.markdown(f"### {row.get('home_team')} vs {row.get('away_team')}")
        c1, c2, c3 = st.columns(3)
        c1.metric("추천", row.get("pick", "-"))
        c2.metric("신뢰도", pct(row.get("confidence", 0)))
        c3.metric("위험도", pct(row.get("risk_level", 0)))
        st.write(f"**등급:** {grade}  |  **시작:** {row.get('start_time', '-')}")
        st.write(f"**최종메모:** {row.get('final_note', '-')}")
        with st.expander("근거 보기"):
            st.write(row.get("reason", ""))
        b1, b2, b3 = st.columns(3)
        b1.link_button("공식 구매처 열기", settings.get("official_purchase_url", "https://www.betman.co.kr/"), width="stretch")
        if b2.button("구매 완료 체크", key=f"buy_{row.get('game_id')}", width="stretch"):
            append_csv(FILES["purchase"], {
                "time": kst_str(), "game_id": row.get("game_id"), "pick": row.get("pick"),
                "amount": "", "purchased": True, "memo": "사용자 직접 구매 체크"
            })
            st.success("구매 완료 기록 저장")
        if b3.button("관망 처리", key=f"wait_{row.get('game_id')}", width="stretch"):
            append_csv(FILES["purchase"], {
                "time": kst_str(), "game_id": row.get("game_id"), "pick": row.get("pick"),
                "amount": 0, "purchased": False, "memo": "관망 처리"
            })
            st.info("관망 기록 저장")
        st.markdown("</div>", unsafe_allow_html=True)


def render_pc_monitoring(rec_df: pd.DataFrame) -> None:
    st.subheader("🖥️ PC 모니터링")
    games = read_csv(FILES["games"])
    purchases = read_csv(FILES["purchase"])
    results = read_csv(FILES["results"])
    errors = read_csv(FILES["errors"])
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("경기 수", len(games))
    c2.metric("분석 완료", len(rec_df))
    c3.metric("구매 체크", len(purchases))
    c4.metric("오류 로그", len(errors))
    if not rec_df.empty:
        st.dataframe(rec_df[["league", "home_team", "away_team", "start_time", "pick", "grade", "confidence", "risk_level", "final_note"]], width="stretch", hide_index=True)
    with st.expander("구매 기록"):
        st.dataframe(purchases, width="stretch", hide_index=True)
    with st.expander("결과 입력 / 패배원인 분석 / 학습"):
        st.write("경기 후 결과와 원인을 입력하면 Earth Agent가 왜 맞았는지/틀렸는지 저장하고 다음 분석 가중치에 반영합니다.")
        if not rec_df.empty:
            gids = rec_df["game_id"].astype(str).tolist()
            gid = st.selectbox("경기 선택", gids)
            hit = st.selectbox("결과", ["적중", "미적중"])
            final_score = st.text_input("최종 스코어", placeholder="예: 2-1")
            profit = st.number_input("손익", value=0.0, step=1000.0)
            key_injury = st.number_input("핵심 선수 부상/결장 수", min_value=0, max_value=10, value=0)
            red_card = st.number_input("퇴장/중대 카드 변수", min_value=0, max_value=5, value=0)
            coach_issue = st.text_input("감독/전술 문제", placeholder="예: 평소와 다른 수비전술, 교체 타이밍 실패")
            lineup_issue = st.text_input("주전/선발/로테이션 문제", placeholder="예: 주전 공격수 결장, 후보 골키퍼 출전")
            odds_issue = st.text_input("배당/시장 흐름 문제", placeholder="예: 경기 직전 배당 급락, 인기 쏠림")
            fatigue_weather = st.text_input("체력/날씨/원정 변수", placeholder="예: 장거리 원정, 폭우, 휴식일 부족")
            data_issue = st.text_input("데이터 부족/오류", placeholder="예: 선발 정보 늦게 반영, API 누락")
            memo = st.text_input("추가 메모", "")
            if st.button("결과 저장 + 원인리뷰 + 학습 업데이트"):
                result_row = {
                    "time": kst_str(), "game_id": gid, "hit": hit, "final_score": final_score,
                    "profit_loss": profit, "key_injury": key_injury, "red_card": red_card,
                    "coach_issue": coach_issue, "lineup_issue": lineup_issue, "odds_issue": odds_issue,
                    "fatigue_weather": fatigue_weather, "data_issue": data_issue, "memo": memo
                }
                append_csv(FILES["results"], result_row)
                review = save_result_review(result_row, None)
                learning = update_learning_from_results(None)
                st.success(f"학습 업데이트 완료: 적중률 {learning.get('hit_rate', 0)}%")
                st.info(review.get("cause_summary", ""))
        with st.expander("저장된 원인 리뷰 보기"):
            st.dataframe(read_csv(FILES["result_review"]), width="stretch", hide_index=True)
    with st.expander("오류 로그"):
        st.dataframe(errors, width="stretch", hide_index=True)


def render_learning() -> None:
    st.subheader("🌍 Earth Agent 자가학습")
    learning = earth_learning_load()
    weights = learning.get("weights", DEFAULT_WEIGHTS)
    c1, c2, c3 = st.columns(3)
    c1.metric("학습 기록", learning.get("history_count", 0))
    c2.metric("최근 적중률", f"{learning.get('hit_rate', 0)}%")
    c3.metric("누적 손익", learning.get("profit_loss_sum", 0))
    st.json(weights)
    st.caption("학습은 수익 보장이 아니라, 실패 패턴을 줄이고 위험 가중치를 조정하는 방식입니다.")


def render_bigdata_store() -> None:
    st.subheader("🧠 경기별 빅데이터 저장소")
    st.caption("매 경기마다 경기 전 데이터, 배당, 팀전력, 선발/부상, 감독전술, 경기 후 원인리뷰를 따로 남깁니다.")
    tabs = st.tabs(["경기전", "배당", "팀전력", "선발/부상", "감독전술", "결과리뷰", "학습메모"])
    mapping = [
        ("prematch", "경기 전 스냅샷"),
        ("odds", "배당 변화"),
        ("team_stats", "팀 전력"),
        ("lineups", "선발/부상/징계"),
        ("coach_tactics", "감독/전술"),
        ("result_review", "결과 원인 리뷰"),
        ("learning_memory", "학습 메모"),
    ]
    for t, (key, label) in zip(tabs, mapping):
        with t:
            df = read_csv(FILES[key])
            st.write(f"**{label}** — {len(df)}건")
            st.dataframe(df.tail(200), width="stretch", hide_index=True)

def render_file_check() -> None:
    st.subheader("🧪 파일 검사 / 오류 검사")
    checks = []
    required = ["app.py", "requirements.txt", ".streamlit/config.toml"]
    for f in required:
        p = Path(f)
        checks.append({"항목": f, "상태": "정상" if p.exists() else "누락"})
    for name, path in FILES.items():
        checks.append({"항목": str(path), "상태": "존재" if path.exists() else "미생성(정상 가능)"})
    st.dataframe(pd.DataFrame(checks), width="stretch", hide_index=True)

    st.markdown("---")
    st.subheader("⚽ Sportmonks/API 실제 연결 검사")
    settings = load_settings()
    url = settings.get("sports_api_url", "")
    key = settings.get("sports_api_key", "")
    safe_url = url.replace("{api_key}", mask_secret(key)) if key else url
    c1, c2, c3 = st.columns(3)
    c1.metric("토큰 감지", "감지됨" if key else "없음")
    c2.metric("URL 템플릿", "있음" if url else "없음")
    c3.metric("공급자", "Sportmonks" if "sportmonks" in url.lower() else "Custom")
    st.caption("토큰은 보안상 앞뒤 일부만 표시합니다.")
    st.code(f"TOKEN = {mask_secret(key)}\nURL = {safe_url}", language="text")

    if st.button("Sportmonks 실제 API 연결 테스트", width="stretch"):
        diag = test_sportmonks_api(settings, allow_fallback_date=True)
        if diag.get("status") == "success":
            st.success(f"실제 데이터 연결 성공: {diag.get('normalized_games_count')}개 경기 파싱")
        else:
            st.error(f"실제 데이터 연결 실패: {diag.get('message')}")
        st.session_state["api_diag_now"] = diag

    diag = st.session_state.get("api_diag_now") or load_api_diag()
    if diag:
        view = dict(diag)
        # 응답 미리보기에는 토큰이 섞일 가능성이 낮지만 혹시 몰라 한번 더 마스킹
        token = settings.get("sports_api_key", "")
        if token:
            for k in ["safe_final_url", "response_preview", "message"]:
                if isinstance(view.get(k), str):
                    view[k] = view[k].replace(token, mask_secret(token))
        summary = {
            "검사시간": view.get("time", ""),
            "상태": view.get("status", ""),
            "HTTP": view.get("http_status", ""),
            "응답 data 개수": view.get("response_data_count", 0),
            "파싱 경기 수": view.get("normalized_games_count", 0),
            "샘플 대체": view.get("sample_fallback", False),
            "메시지": view.get("message", ""),
        }
        st.dataframe(pd.DataFrame([summary]), width="stretch", hide_index=True)
        if view.get("first_game"):
            st.write("첫 경기 파싱 결과")
            st.json(view.get("first_game"))
        with st.expander("진단 상세 보기"):
            st.json(view)

    st.markdown("---")
    with st.expander("샘플 수집/분석 테스트 — 실제 API 아님"):
        st.warning("이 버튼은 A팀/B팀 샘플을 만드는 테스트입니다. 실제 Sportmonks 연결 확인은 위의 API 연결 테스트 버튼을 사용하세요.")
        if st.button("샘플 수집/분석 테스트 실행"):
            hub = GoogleSheetHub({})
            games = save_games(make_sample_games(), hub)
            rec = run_analysis(games, hub)
            st.success(f"샘플 테스트 완료: 경기 {len(games)}개, 추천 {len(rec)}개")


def main() -> None:
    render_header()
    settings, hub = sidebar_settings()
    render_status(settings, hub)

    if settings.get("auto_refresh_sec", 0):
        st.caption(f"자동 새로고침 설정: {settings.get('auto_refresh_sec')}초. Streamlit Cloud에서는 앱이 열려 있을 때 중심으로 동작합니다. PC가 꺼져도 완전 자동 수집하려면 GitHub Actions 또는 Google Apps Script 스케줄러를 추가하세요.")

    if st.session_state.get("run_now"):
        games = fetch_games_from_api(settings)
        games_df = save_games(games, hub)
        rec_df = run_analysis(games_df, hub)
        st.session_state["run_now"] = False
    else:
        rec_df = read_csv(FILES["recommend"])

    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["모바일 추천", "PC 모니터링", "AI 학습", "빅데이터 저장소", "허브/검사", "안전 안내"])
    with tab1:
        render_mobile_recommendations(settings, rec_df)
    with tab2:
        render_pc_monitoring(rec_df)
    with tab3:
        render_learning()
    with tab4:
        render_bigdata_store()
    with tab5:
        render_file_check()
    with tab6:
        st.markdown("""
        ### 안전 운영 원칙
        - 본 앱은 스포츠 데이터 분석, 기록, 모니터링 보조용입니다.
        - 자동구매, 대리구매, 결제 자동 클릭 기능은 제공하지 않습니다.
        - 추천은 수익을 보장하지 않습니다.
        - 사용자는 공식 발매처에서 직접 판단하고, 구매 여부만 앱에 기록합니다.
        - 데이터가 부족하거나 선발/부상 정보가 불확실하면 관망 또는 제외가 우선입니다.
        """)

if __name__ == "__main__":
    main()
