"""
Simultaneous RPS combat resolution for 동시가위바위보.

Rules:
- A piece is defeated if ANY adjacent (or co-located) enemy piece beats it.
- All kills computed from pre-combat snapshot, then applied simultaneously.
- A dying piece still kills its prey (simultaneous semantics).
"""
from __future__ import annotations
from typing import List, TYPE_CHECKING
from .state import GameState, Piece, BEATS

if TYPE_CHECKING:
    pass


def resolve_combat(state: GameState) -> List[Piece]:
    """
    Compute and apply simultaneous combat.
    Returns list of killed pieces.
    """
    living = state.all_living_pieces()
    if len(living) < 2:
        return []

    # Build spatial index: cell → list of living pieces
    cell_map: dict[tuple, list[Piece]] = {}
    for piece in living:
        key = (piece.row, piece.col)
        cell_map.setdefault(key, []).append(piece)

    # Collect kills (using snapshot — do NOT remove yet)
    to_kill: set[int] = set()  # piece ids

    for piece in living:
        pos = (piece.row, piece.col)
        # Check co-located enemies and adjacent cell enemies
        positions_to_check = [pos] + state.grid.neighbors(piece.row, piece.col)
        for check_pos in positions_to_check:
            for other in cell_map.get(check_pos, []):
                if other.owner == piece.owner:
                    continue
                # Does 'other' beat 'piece'?
                if BEATS.get(other.owner) == piece.owner:
                    to_kill.add(piece.id)

    # Apply kills simultaneously
    killed: List[Piece] = []
    for piece in living:
        if piece.id in to_kill:
            piece.alive = False
            killed.append(piece)

    return killed
