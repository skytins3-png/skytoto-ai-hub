# SKYTOTO AI HUB BIGDATA

스포츠 경기 데이터 분석·기록·학습 보조 앱입니다. 자동구매, 대리구매, 결제 자동 클릭 기능은 없습니다.

## AI 부서장

- Sun Chief: 경기 일정, 시작 시간, 마감 시간
- Moon Chief: 초기 배당, 현재 배당, 급락/급등, 시장 흐름
- Star Chief: 최근 승패, 상대전적, 홈/원정, 감독, 주전선수
- Rain Chief: 부상, 결장, 징계, 감독 교체, 위험 경기 차단
- Cloud Chief: API 통신, 로컬/구글시트 허브 저장, 모바일/PC 동기화
- Earth Chief: 결과 비교, 패배 원인 분석, 빅데이터 학습, 가중치 조정

## 저장되는 빅데이터

- GAMES: 경기 기본정보
- PRE_MATCH: 경기 전 AI 분석 스냅샷
- ODDS: 배당 변화
- TEAM_STATS: 최근 성적, 상대전적, 홈 강도
- LINEUPS: 선발, 부상, 징계, 결장
- COACH_TACTICS: 감독 변화, 전술 메모
- RECOMMEND: 추천 결과
- PURCHASE_LOG: 사용자가 직접 구매/관망 체크한 기록
- RESULTS: 경기 후 결과
- RESULT_REVIEW: 왜 이겼는지/왜 졌는지 원인 분석
- LEARNING_MEMORY: 다음 분석에 반영할 학습 메모
- LEARNING: Earth Agent 가중치
- ERROR_LOG: API/허브 오류

## 실행

```bash
pip install -r requirements.txt
python -m py_compile app.py
python -m py_compile scripts/cloud_runner.py
python scripts/cloud_runner.py
streamlit run app.py
```

## PC가 꺼져도 실행

`.github/workflows/skytoto-cloud-runner.yml`이 GitHub Actions에서 `scripts/cloud_runner.py`를 실행합니다. GitHub Secrets에 구글시트와 API 값을 넣으면 클라우드에서 자동 수집/분석/저장합니다.

## 안전 원칙

추천은 수익을 보장하지 않습니다. 자동구매 기능은 없고, 사용자가 공식 발매처에서 직접 판단합니다.


## 2026-06-23 Sportmonks 진단 강화
- 허브/검사 탭에 `Sportmonks 실제 API 연결 테스트` 버튼 추가
- 토큰 감지 여부, 최종 호출 URL(토큰 마스킹), HTTP 상태코드, 응답 개수, 파싱 경기 수 표시
- API 실패 시 샘플로 넘어간 이유를 `data/api_diagnostics.json`에 저장
- 기존 `샘플 수집/분석 테스트`는 실제 API가 아님을 명확히 표시
