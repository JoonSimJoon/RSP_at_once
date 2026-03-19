# 동시가위바위보 (RSP At Once)

삼각 격자 위에서 **가위/바위/보 3진영이 동시에 행동**하는 시뮬레이터 프로젝트입니다.

- `simulator/`: 게임 엔진, 터미널 시뮬레이터, 리플레이
- `web/`: Flask 기반 웹 플레이/코드 제출 UI
- `agents/`: 예시 C++/Python 에이전트

## 주요 기능

- 3개 진영(가위/바위/보) 동시 턴 처리
- 행동 타입: `MOVE`(거리 2), `CLONE`(인접 복제)
- 전투 해석 및 승패 판정
- JSONL 리플레이 저장/재생
- 웹에서 인간 플레이 + 코드 제출 후 시뮬레이션

## 요구사항

- Python 3.10+
- (선택) `g++` (C++ 에이전트 빌드/제출용)
- Flask (`web/app.py` 실행 시 필요)

## 가상환경(venv) 설정

권장: 프로젝트 루트에서 가상환경을 만든 뒤 의존성을 설치하세요.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Windows (PowerShell):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## 빠른 시작

### 1) 예시 C++ 에이전트 빌드

```bash
bash agents/compile.sh
```

개별 빌드:

```bash
g++ -std=c++17 -O2 -o agents/random_agent agents/random_agent.cpp
g++ -std=c++17 -O2 -o agents/greedy_agent agents/greedy_agent.cpp
```

### 2) 시뮬레이터 실행

```bash
python3 simulator/simulator.py \
  --agent-scissors "python3 agents/random_agent.py" \
  --agent-rock "python3 agents/random_agent.py" \
  --agent-paper "python3 agents/random_agent.py" \
  --quiet
```

리플레이 저장:

```bash
python3 simulator/simulator.py \
  --agent-scissors "python3 agents/random_agent.py" \
  --agent-rock "python3 agents/random_agent.py" \
  --agent-paper "python3 agents/random_agent.py" \
  --replay replays/game.jsonl \
  --quiet
```

### 3) 웹 앱 실행

```bash
python3 web/app.py
```

기본 주소: `http://127.0.0.1:5000` (서버는 `0.0.0.0:5000`으로 바인딩)

## 최소 검증(사실상 단일 테스트)

이 저장소에는 현재 정식 테스트 프레임워크(`pytest`, `tests/`)가 없습니다.
아래 2개를 최소 실행 검증으로 사용합니다.

시뮬레이터 스모크 테스트:

```bash
python3 simulator/simulator.py \
  --agent-scissors "python3 agents/random_agent.py" \
  --agent-rock "python3 agents/random_agent.py" \
  --agent-paper "python3 agents/random_agent.py" \
  --max-turns 20 \
  --quiet
```

웹 엔드포인트 확인(서버 실행 후):

```bash
curl http://127.0.0.1:5000/api/grid
```

문법 체크:

```bash
python3 -m py_compile simulator/simulator.py web/app.py
python3 -m py_compile simulator/engine/state.py simulator/engine/protocol.py
```

## 프로젝트 구조

```text
.
├─ agents/
│  ├─ agent.h
│  ├─ random_agent.cpp
│  ├─ greedy_agent.cpp
│  └─ random_agent.py
├─ simulator/
│  ├─ simulator.py
│  ├─ replay.py
│  └─ engine/
│     ├─ map.py
│     ├─ state.py
│     ├─ combat.py
│     └─ protocol.py
└─ web/
   ├─ app.py
   ├─ templates/
   └─ static/
```

## 에이전트 통신 프로토콜

한 턴마다 JSON 한 줄(JSONL 스타일)로 통신합니다.

Simulator -> Agent:

```json
{
  "turn": 12,
  "max_turns": 200,
  "my_type": "ROCK",
  "my_pieces": [{"id": 0, "row": 10, "col": 0}],
  "enemy_pieces": [{"row": 0, "col": 0, "type": "SCISSORS"}]
}
```

Agent -> Simulator:

```json
{
  "actions": [
    {"piece_id": 0, "action": "MOVE", "row": 9, "col": 1},
    {"piece_id": 1, "action": "CLONE", "row": 10, "col": 1}
  ]
}
```

주의:

- `action` 값은 `MOVE` 또는 `CLONE`
- 키 이름(`piece_id`, `action`, `row`, `col`)은 고정 사용 권장

## 웹 API 요약

- `GET /api/grid`: 격자 기하 데이터
- `POST /api/game/new`: 새 게임 생성
- `GET /api/game/<game_id>/state`: 현재 게임 상태
- `POST /api/game/<game_id>/action`: 인간 플레이어 행동 제출
- `POST /api/submit`: 코드 제출 후 백그라운드 매치 실행
- `GET /api/job/<job_id>`: 제출 작업 상태/결과 조회

## 개발 메모

- 코드 작업 규칙은 `AGENTS.md`에 정리되어 있습니다.
- 현재 `.cursor/rules/`, `.cursorrules`, `.github/copilot-instructions.md`는 없습니다.
- 시뮬레이터/프로토콜 호환성을 깨지 않도록 키/행동 스키마를 유지하세요.
