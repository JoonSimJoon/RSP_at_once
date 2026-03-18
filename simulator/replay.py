"""
Replay system for 동시가위바위보.

Format: JSONL (one JSON object per line)
  Line 0: {"type":"config","side":11,"max_turns":200,"agents":{...}}
  Line N+1: {"type":"turn","turn":N,"scores":{...},"actions":{...},"kills":[...],
             "pieces":[{"id":0,"owner":"ROCK","row":10,"col":0},...]},

Usage:
  writer = ReplayWriter("game.jsonl", agents_info)
  writer.write_turn(state, actions_dict, kills_list)
  writer.close()

  for record in ReplayReader("game.jsonl"):
      print(record)
"""
import json
import time
from pathlib import Path
from typing import Dict, List, Optional, Any, Iterator
from .engine.state import GameState, PieceType, Action
from .engine.state import Piece


class ReplayWriter:
    def __init__(self, path: str, agents: Dict[str, str], side: int = 11, max_turns: int = 200):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._f = open(self.path, "w", encoding="utf-8")
        config = {
            "type": "config",
            "side": side,
            "max_turns": max_turns,
            "agents": agents,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        self._f.write(json.dumps(config, ensure_ascii=False) + "\n")
        self._f.flush()

    def write_turn(
        self,
        state: GameState,
        actions: Dict[PieceType, List[Action]],
        kills: List[Piece],
    ):
        pieces = [
            {"id": p.id, "owner": p.owner.value, "row": p.row, "col": p.col}
            for p in state.all_living_pieces()
        ]
        actions_serialized = {}
        for ptype, acts in actions.items():
            actions_serialized[ptype.value] = [
                {"piece_id": a.piece_id, "action": a.action_type,
                 "row": a.target_row, "col": a.target_col}
                for a in acts
            ]
        record = {
            "type": "turn",
            "turn": state.turn,
            "scores": state.scores(),
            "actions": actions_serialized,
            "kills": [{"id": p.id, "owner": p.owner.value} for p in kills],
            "pieces": pieces,
        }
        self._f.write(json.dumps(record, ensure_ascii=False) + "\n")
        self._f.flush()

    def write_result(self, winner: str, scores: Dict[str, int]):
        record = {"type": "result", "winner": winner, "scores": scores}
        self._f.write(json.dumps(record, ensure_ascii=False) + "\n")
        self._f.flush()

    def close(self):
        self._f.close()


class ReplayReader:
    def __init__(self, path: str):
        self.path = path

    def __iter__(self) -> Iterator[Dict[str, Any]]:
        with open(self.path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    yield json.loads(line)


def replay_playback(path: str, speed: float = 1.0, no_color: bool = False):
    """Play back a saved replay in the terminal."""
    import time as _time
    from .engine.map import TriangularGrid
    from .engine.state import GameState, Piece as _Piece
    from .visualizer import print_state

    config = None
    grid = TriangularGrid()

    for record in ReplayReader(path):
        if record["type"] == "config":
            config = record
            print(f"Replay: {path}")
            print(f"Agents: {record.get('agents', {})}")
            print(f"Recorded: {record.get('timestamp', 'unknown')}")
            print()
            continue

        if record["type"] == "turn":
            # Reconstruct a minimal display state
            print(f"\033[2J\033[H", end="")  # clear screen
            print(f"Turn {record['turn']} | Scores: {record['scores']}")
            if record.get("kills"):
                kill_str = ", ".join(f"{k['owner']}#{k['id']}" for k in record["kills"])
                print(f"Kills: {kill_str}")
            print()
            # Simple grid print from pieces list
            _print_pieces(record["pieces"], record["turn"], grid, no_color)
            _time.sleep(1.0 / speed)
            continue

        if record["type"] == "result":
            print(f"\n=== RESULT: {record['winner']} wins! ===")
            print(f"Final scores: {record['scores']}")


def _print_pieces(pieces_data: list, turn: int, grid, no_color: bool):
    """Minimal piece rendering for replay playback."""
    ANSI_MAP = {"SCISSORS": "\033[93m", "ROCK": "\033[91m", "PAPER": "\033[96m"}
    RESET = "\033[0m"
    SYM = {"SCISSORS": "S", "ROCK": "R", "PAPER": "P"}

    cell_map: dict = {}
    for p in pieces_data:
        key = (p["row"], p["col"])
        cell_map.setdefault(key, {}).update(
            {p["owner"]: cell_map.get(key, {}).get(p["owner"], 0) + 1}
        )

    for r in range(grid.side):
        indent = " " * (2 * (grid.side - 1) - 2 * r)
        row_parts = [indent]
        for c in range(2 * r + 1):
            prefix = "△" if c % 2 == 0 else "▽"
            owners = cell_map.get((r, c), {})
            if not owners:
                row_parts.append(prefix + ". ")
            else:
                dominant = max(owners, key=lambda t: owners[t])
                count = owners[dominant]
                sym = SYM[dominant]
                display = f"{sym}{min(count,9)}" if count > 1 else f"{sym} "
                if not no_color:
                    row_parts.append(ANSI_MAP[dominant] + prefix + display + RESET)
                else:
                    row_parts.append(prefix + display)
        print("".join(row_parts))
    print()
