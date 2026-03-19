"""
Flask backend for 동시가위바위보 웹게임.

Provides:
  - WebGame class for human-vs-AI play via web API
  - Code submission endpoint with background match execution
  - Grid geometry endpoint for rendering
"""
import sys
import os
import math
import json
import time
import uuid
import random
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path

from flask import Flask, request, jsonify, render_template, session

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from simulator.engine.map import TriangularGrid, SIDE
from simulator.engine.state import (
    GameState, PieceType, Action, BEATS, PIECE_CAP, MAX_TURNS,
)
from simulator.engine.combat import resolve_combat
from simulator.simulator import run_match
from simulator.replay import ReplayReader

# ---------------------------------------------------------------------------
# Grid geometry (ported from gui.py)
# ---------------------------------------------------------------------------
UNIT_S = 48
H = UNIT_S * math.sqrt(3) / 2
GRID_CX = 480
GRID_TOP = 30


def cell_vertices(r, c):
    x_left = GRID_CX - (r + 1) * UNIT_S / 2
    y_top = GRID_TOP + r * H
    y_bot = GRID_TOP + (r + 1) * H
    if c % 2 == 0:  # upward
        k = c // 2
        return [
            (x_left + k * UNIT_S, y_bot),
            (x_left + (k + 1) * UNIT_S, y_bot),
            (x_left + k * UNIT_S + UNIT_S / 2, y_top),
        ]
    else:  # downward
        k = (c - 1) // 2
        return [
            (x_left + k * UNIT_S + UNIT_S / 2, y_top),
            (x_left + (k + 1) * UNIT_S + UNIT_S / 2, y_top),
            (x_left + (k + 1) * UNIT_S, y_bot),
        ]


# ---------------------------------------------------------------------------
# AI move helper (ported from gui.py)
# ---------------------------------------------------------------------------
def ai_move(state, ptype, grid):
    """Pick ONE random action for ptype. Distance-1 = CLONE, distance-2 = MOVE."""
    player = state.players[ptype]
    occupied = {(p.row, p.col) for p in state.all_living_pieces()}
    pieces = player.living_pieces()
    random.shuffle(pieces)
    for piece in pieces:
        r1 = grid.reachable(piece.row, piece.col, 1) - {(piece.row, piece.col)}
        r2 = grid.reachable(piece.row, piece.col, 2) - {(piece.row, piece.col)} - r1
        # CLONE targets: distance-1, empty, under cap
        clone_targets = [c for c in r1 if c not in occupied and player.piece_count() < PIECE_CAP]
        # MOVE targets: distance-2, not occupied by friendly
        friendly = {(p.row, p.col) for p in pieces}
        move_targets = [c for c in r2 if c not in friendly]
        candidates = (
            [("CLONE", t) for t in clone_targets] +
            [("MOVE", t) for t in move_targets]
        )
        if candidates:
            atype, t = random.choice(candidates)
            return [Action(piece.id, atype, t[0], t[1])]
    return []


# ---------------------------------------------------------------------------
# WebGame
# ---------------------------------------------------------------------------
class WebGame:
    """Manages game state for human play via web API."""

    PHASE_ORDER = ["INPUT_SCISSORS", "INPUT_ROCK", "INPUT_PAPER"]
    PHASE_TO_TYPE = {
        "INPUT_SCISSORS": PieceType.SCISSORS,
        "INPUT_ROCK": PieceType.ROCK,
        "INPUT_PAPER": PieceType.PAPER,
    }

    def __init__(self, human_types: set):
        self.grid = TriangularGrid()
        self.state = GameState(self.grid)
        self.human_types = set(human_types)  # set of PieceType
        self.phase = "INPUT_SCISSORS"
        self.pending_actions = {}       # PieceType -> List[Action]
        self.piece_actions = {}         # piece_id -> Action (current human turn)
        self.last_kills = []
        self.winner = None
        self.last_accessed = time.time()

    # ---- serialisation -----------------------------------------------------

    def to_state_json(self):
        pieces = []
        for p in self.state.all_living_pieces():
            pieces.append({
                "id": p.id,
                "owner": p.owner.value,
                "row": p.row,
                "col": p.col,
            })
        kills = [{"id": p.id, "owner": p.owner.value} for p in self.last_kills]
        return {
            "turn": self.state.turn,
            "phase": self.phase,
            "human_types": [t.value for t in self.human_types],
            "winner": self.winner,
            "kills": kills,
            "pieces": pieces,
            "scores": self.state.scores(),
        }

    # ---- human action ingestion --------------------------------------------

    def apply_human_actions(self, actions_raw):
        """Accept actions for the current human phase, then auto-advance."""
        if self.phase not in self.PHASE_TO_TYPE:
            return self.to_state_json()

        ptype = self.PHASE_TO_TYPE[self.phase]

        # Only accept if the current phase is for a human player
        if ptype not in self.human_types:
            return self.to_state_json()

        # Parse raw actions — enforce max 1 action per player
        self.piece_actions = {}
        parsed = []
        for a in actions_raw[:1]:   # take at most the first action
            act = Action(
                piece_id=int(a["piece_id"]),
                action_type=a["action"],
                target_row=int(a["row"]),
                target_col=int(a["col"]),
            )
            self.piece_actions[act.piece_id] = act
            parsed.append(act)

        self.pending_actions[ptype] = parsed
        self._advance_phase()
        return self.to_state_json()

    # ---- phase management --------------------------------------------------

    def _advance_phase(self):
        """Move to the next phase; auto-play AI phases; apply round when done."""
        idx = self.PHASE_ORDER.index(self.phase)
        idx += 1

        if idx >= len(self.PHASE_ORDER):
            # All three players acted -- apply the round
            self._apply_round()
            return

        self.phase = self.PHASE_ORDER[idx]
        self._auto_advance_if_ai()

    def _auto_advance_if_ai(self):
        """Walk through phases, auto-executing AI players until a human phase
        is reached or the round is complete (then possibly loops into next round)."""
        while self.phase in self.PHASE_TO_TYPE:
            ptype = self.PHASE_TO_TYPE[self.phase]
            if ptype in self.human_types:
                # This phase needs human input -- stop here
                break
            # AI turn
            actions = ai_move(self.state, ptype, self.grid)
            self.pending_actions[ptype] = actions

            idx = self.PHASE_ORDER.index(self.phase)
            idx += 1
            if idx >= len(self.PHASE_ORDER):
                self._apply_round()
                # After apply_round, phase may be INPUT_SCISSORS again or DONE
                # If it's a new round starting with AI, keep looping
                if self.phase == "DONE":
                    break
                continue
            else:
                self.phase = self.PHASE_ORDER[idx]
                # Loop will check if next phase is also AI

    # ---- round execution ---------------------------------------------------

    def _apply_round(self):
        """Increment turn, apply all pending actions, resolve combat, check winner."""
        self.state.turn += 1
        self.state.apply_actions(self.pending_actions)
        self.last_kills = resolve_combat(self.state)
        self.pending_actions = {}
        self.piece_actions = {}

        w = self.state.check_winner()
        if w is not None:
            self.winner = w
            self.phase = "DONE"
        else:
            # Start next round
            self.phase = "INPUT_SCISSORS"
            self._auto_advance_if_ai()


# ---------------------------------------------------------------------------
# Flask app
# ---------------------------------------------------------------------------
app = Flask(__name__)
app.secret_key = os.urandom(24)

games = {}   # game_id (str) -> WebGame
jobs = {}    # job_id (str) -> dict

GRID = TriangularGrid()
TMP_DIR = Path(__file__).parent / "tmp"
TMP_DIR.mkdir(exist_ok=True)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/grid")
def api_grid():
    cells = []
    for r, c in GRID.all_cells():
        verts = cell_vertices(r, c)
        cells.append({
            "r": r,
            "c": c,
            "upward": c % 2 == 0,
            "vertices": [[round(x, 2), round(y, 2)] for x, y in verts],
        })
    return jsonify({"side": SIDE, "cells": cells})


@app.route("/api/game/new", methods=["POST"])
def api_game_new():
    data = request.json or {}
    human_type_strs = data.get("human_types", ["SCISSORS"])
    human_types = {PieceType(t) for t in human_type_strs}
    game_id = str(uuid.uuid4())
    game = WebGame(human_types)
    # Auto-advance if first phase is AI
    game._auto_advance_if_ai()
    games[game_id] = game
    return jsonify({"game_id": game_id, "state": game.to_state_json()})


@app.route("/api/game/<game_id>/state")
def api_game_state(game_id):
    game = games.get(game_id)
    if not game:
        return jsonify({"error": "not found"}), 404
    game.last_accessed = time.time()
    return jsonify(game.to_state_json())


@app.route("/api/game/<game_id>/action", methods=["POST"])
def api_game_action(game_id):
    game = games.get(game_id)
    if not game:
        return jsonify({"error": "not found"}), 404
    game.last_accessed = time.time()
    data = request.json or {}
    actions_raw = data.get("actions", [])
    result = game.apply_human_actions(actions_raw)
    return jsonify(result)


@app.route("/api/submit", methods=["POST"])
def api_submit():
    data = request.json or {}
    code = data.get("code", "")
    language = data.get("language", "cpp")  # "cpp" or "python"

    if not code.strip():
        return jsonify({"error": "empty_code", "detail": "코드가 비어있습니다."})

    job_id = str(uuid.uuid4())
    sub_dir = TMP_DIR / "submissions" / job_id
    sub_dir.mkdir(parents=True, exist_ok=True)
    replay_path = str(TMP_DIR / "replays" / f"{job_id}.jsonl")
    Path(replay_path).parent.mkdir(parents=True, exist_ok=True)

    if language == "cpp":
        # Write source
        src_file = sub_dir / "agent.cpp"
        src_file.write_text(code, encoding="utf-8")
        # Copy agent.h
        agent_h = ROOT / "agents" / "agent.h"
        if agent_h.exists():
            shutil.copy(agent_h, sub_dir / "agent.h")

        # Detect compiler
        compiler = shutil.which("g++")
        if not compiler:
            return jsonify({
                "error": "no_compiler",
                "detail": "g++를 찾을 수 없습니다. MinGW-w64를 설치하세요.",
            })

        # Compile (synchronous, 10s timeout)
        exe_name = "agent.exe" if os.name == "nt" else "agent"
        exe_path = sub_dir / exe_name
        try:
            result = subprocess.run(
                [compiler, "-std=c++17", "-O2", "-o", str(exe_path), str(src_file)],
                capture_output=True,
                text=True,
                timeout=10,
                cwd=str(sub_dir),
            )
        except subprocess.TimeoutExpired:
            return jsonify({
                "error": "compile_timeout",
                "detail": "컴파일 시간 초과 (10초)",
            })

        if result.returncode != 0:
            return jsonify({
                "error": "compile_error",
                "detail": result.stderr[:2000],
            })

        agent_cmd = str(exe_path)

    elif language == "python":
        src_file = sub_dir / "agent.py"
        src_file.write_text(code, encoding="utf-8")
        agent_cmd = f"python {src_file}"

    else:
        return jsonify({
            "error": "unsupported_language",
            "detail": f"지원하지 않는 언어: {language}",
        })

    # Start background match
    jobs[job_id] = {
        "status": "running",
        "progress": "매치 시작 중...",
        "created_at": time.time(),
    }

    random_agent = str(ROOT / "agents" / "random_agent.py")
    agent_cmds = {
        PieceType.SCISSORS: agent_cmd,
        PieceType.ROCK: f"python {random_agent}",
        PieceType.PAPER: f"python {random_agent}",
    }

    def run_job():
        try:
            jobs[job_id]["progress"] = "시뮬레이션 실행 중..."
            winner, scores = run_match(
                agent_cmds,
                max_turns=MAX_TURNS,
                timeout_ms=1000,
                replay_path=replay_path,
                quiet=True,
            )
            # Read replay
            replay_data = list(ReplayReader(replay_path))
            jobs[job_id].update({
                "status": "done",
                "result": {"winner": winner, "scores": scores},
                "replay": replay_data,
            })
        except Exception as e:
            jobs[job_id].update({"status": "error", "detail": str(e)})

    t = threading.Thread(target=run_job, daemon=True)
    t.start()

    return jsonify({"job_id": job_id})


@app.route("/api/job/<job_id>")
def api_job(job_id):
    job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "not found"}), 404
    return jsonify(job)


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------
def _cleanup_old():
    """Remove sessions/jobs older than 1 hour."""
    cutoff = time.time() - 3600
    for gid in list(games.keys()):
        if games[gid].last_accessed < cutoff:
            del games[gid]
    for jid in list(jobs.keys()):
        if jobs[jid].get("created_at", 0) < cutoff:
            del jobs[jid]


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    debug = os.getenv("FLASK_DEBUG", "1").lower() in {"1", "true", "yes", "on"}
    app.run(host="0.0.0.0", port=port, debug=debug)
