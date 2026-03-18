"""
JSON encode/decode for agent communication protocol.

Simulator → Agent (one JSON line per turn):
{
  "turn": N,
  "max_turns": 200,
  "my_type": "ROCK",
  "my_pieces": [{"id": 0, "row": 10, "col": 0}, ...],
  "enemy_pieces": [{"row": 0, "col": 0, "type": "SCISSORS"}, ...]
}

Agent → Simulator (one JSON line):
{
  "actions": [
    {"piece_id": 0, "action": "MOVE", "row": 9, "col": 1},
    {"piece_id": 1, "action": "CLONE", "row": 10, "col": 1}
  ]
}
"""
from __future__ import annotations
import json
from typing import List, Dict, Any
from .state import GameState, PieceType, Action


def encode_state(state: GameState, ptype: PieceType) -> str:
    """Encode game state as JSON string for the given player."""
    my_player = state.players[ptype]
    enemy_pieces = []
    for t, player in state.players.items():
        if t == ptype:
            continue
        for p in player.living_pieces():
            enemy_pieces.append({"row": p.row, "col": p.col, "type": t.value})

    msg = {
        "turn": state.turn,
        "max_turns": state.max_turns,
        "my_type": ptype.value,
        "my_pieces": [
            {"id": p.id, "row": p.row, "col": p.col}
            for p in my_player.living_pieces()
        ],
        "enemy_pieces": enemy_pieces,
    }
    return json.dumps(msg, ensure_ascii=False)


def decode_actions(raw: str, ptype: PieceType) -> List[Action]:
    """Parse agent JSON response into Action list. Returns [] on error."""
    try:
        data = json.loads(raw)
        actions = []
        for item in data.get("actions", []):
            actions.append(Action(
                piece_id=int(item["piece_id"]),
                action_type=str(item["action"]).upper(),
                target_row=int(item["row"]),
                target_col=int(item["col"]),
            ))
        return actions
    except (KeyError, ValueError, TypeError, json.JSONDecodeError):
        return []
