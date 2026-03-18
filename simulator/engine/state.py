"""
Game state: Piece, Player, GameState for 동시가위바위보.

Initial placement (4 pieces each):
  SCISSORS → (0,0), (1,0), (1,1), (2,2)
  ROCK     → (10,0), (9,0), (10,1), (9,2)
  PAPER    → (10,20), (9,18), (10,19), (9,16)

Actions (applied simultaneously):
  MOVE:  piece moves to target within BFS radius 2 (cannot stay same cell)
  CLONE: creates new piece at adjacent cell (radius 1); original stays

Piece cap: 20 per player.
Each cell holds at most one piece. Friendly pieces cannot share a cell.
Enemy pieces on same or adjacent cells trigger combat.
"""
from __future__ import annotations
from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from .map import TriangularGrid

MAX_TURNS = 200
PIECE_CAP = 20


class PieceType(str, Enum):
    SCISSORS = "SCISSORS"
    ROCK = "ROCK"
    PAPER = "PAPER"


# RPS: who does each type beat?
BEATS: Dict[PieceType, PieceType] = {
    PieceType.SCISSORS: PieceType.PAPER,
    PieceType.ROCK: PieceType.SCISSORS,
    PieceType.PAPER: PieceType.ROCK,
}

INITIAL_POSITIONS: Dict[PieceType, List[Tuple[int, int]]] = {
    # Top corner — small upward triangle (row0 apex + row1 base)
    PieceType.SCISSORS: [(0, 0), (1, 0), (1, 1), (1, 2)],
    # Bottom-left corner — small downward triangle
    PieceType.ROCK:     [(9, 0), (10, 0), (10, 1), (10, 2)],
    # Bottom-right corner — small downward triangle
    PieceType.PAPER:    [(9, 18), (10, 18), (10, 19), (10, 20)],
}


@dataclass
class Action:
    piece_id: int
    action_type: str   # "MOVE" or "CLONE"
    target_row: int
    target_col: int


@dataclass
class Piece:
    id: int
    owner: PieceType
    row: int
    col: int
    alive: bool = True


class Player:
    def __init__(self, ptype: PieceType):
        self.ptype = ptype
        self.pieces: List[Piece] = []

    def living_pieces(self) -> List[Piece]:
        return [p for p in self.pieces if p.alive]

    def piece_count(self) -> int:
        return len(self.living_pieces())

    def is_alive(self) -> bool:
        return self.piece_count() > 0


class GameState:
    def __init__(self, grid: TriangularGrid, max_turns: int = MAX_TURNS):
        self.grid = grid
        self.max_turns = max_turns
        self.turn = 0
        self._next_id = 0
        self.players: Dict[PieceType, Player] = {
            t: Player(t) for t in PieceType
        }
        self._init_pieces()

    def _new_id(self) -> int:
        i = self._next_id
        self._next_id += 1
        return i

    def _init_pieces(self):
        for ptype, positions in INITIAL_POSITIONS.items():
            for r, c in positions:
                piece = Piece(id=self._new_id(), owner=ptype, row=r, col=c)
                self.players[ptype].pieces.append(piece)

    def get_piece(self, piece_id: int) -> Optional[Piece]:
        for player in self.players.values():
            for p in player.pieces:
                if p.id == piece_id:
                    return p
        return None

    def all_living_pieces(self) -> List[Piece]:
        result = []
        for player in self.players.values():
            result.extend(player.living_pieces())
        return result

    def apply_actions(self, all_actions: Dict[PieceType, List[Action]]):
        """Apply all MOVE and CLONE actions simultaneously.

        Cell occupancy rule: each cell holds at most one piece per team.
        Friendly pieces cannot share a cell after resolution.
        Swaps (A→B's cell while B→A's cell) are allowed since both vacate.
        """
        # --- Phase 1: collect valid moves ---------------------------------
        proposed_moves: List[Tuple[Piece, int, int]] = []
        clone_targets: List[Tuple[PieceType, int, int]] = []
        clone_claimed: set = set()
        same_owner_claimed: Dict[Tuple[int, int], PieceType] = {}  # cell -> owner

        for ptype, actions in all_actions.items():
            player = self.players[ptype]
            seen_ids: set = set()
            for action in actions:
                if action.piece_id in seen_ids:
                    continue
                seen_ids.add(action.piece_id)
                piece = self.get_piece(action.piece_id)
                if piece is None or not piece.alive or piece.owner != ptype:
                    continue
                tr, tc = action.target_row, action.target_col
                if not self.grid.is_valid(tr, tc):
                    continue

                if action.action_type == "MOVE":
                    reachable = self.grid.reachable(piece.row, piece.col, 2)
                    reachable.discard((piece.row, piece.col))
                    if (tr, tc) not in reachable:
                        continue
                    # Reject if another friendly already claimed this cell
                    if same_owner_claimed.get((tr, tc)) == ptype:
                        continue
                    same_owner_claimed[(tr, tc)] = ptype
                    proposed_moves.append((piece, tr, tc))

                elif action.action_type == "CLONE":
                    if player.piece_count() >= PIECE_CAP:
                        continue
                    neighbors = self.grid.neighbors(piece.row, piece.col)
                    if (tr, tc) in neighbors and (ptype, tr, tc) not in clone_claimed:
                        clone_claimed.add((ptype, tr, tc))
                        clone_targets.append((ptype, tr, tc))

        # --- Phase 2: filter moves that would land on non-moving friendly --
        moving_ids: set = {piece.id for piece, _, _ in proposed_moves}

        valid_moves: List[Tuple[Piece, int, int]] = []
        for piece, tr, tc in proposed_moves:
            # Is there a friendly piece at target that won't move away?
            blocker = any(
                p.row == tr and p.col == tc and p.id not in moving_ids and p.id != piece.id
                for p in self.players[piece.owner].living_pieces()
            )
            if not blocker:
                valid_moves.append((piece, tr, tc))

        # --- Phase 3: apply moves -----------------------------------------
        for piece, nr, nc in valid_moves:
            piece.row = nr
            piece.col = nc

        # --- Phase 4: apply clones (target must be empty after moves) ------
        occupied: set = {(p.row, p.col) for p in self.all_living_pieces()}
        for ptype, r, c in clone_targets:
            player = self.players[ptype]
            if player.piece_count() >= PIECE_CAP:
                continue
            if (r, c) in occupied:
                continue  # cell taken — skip
            new_piece = Piece(id=self._new_id(), owner=ptype, row=r, col=c)
            player.pieces.append(new_piece)
            occupied.add((r, c))

    def check_winner(self) -> Optional[str]:
        """
        Returns:
          PieceType value string if one player won,
          "DRAW" if all eliminated,
          None if game continues.
        """
        alive = [t for t in PieceType if self.players[t].is_alive()]
        if len(alive) == 1:
            return alive[0].value
        if len(alive) == 0:
            return "DRAW"
        if self.turn >= self.max_turns:
            counts = {t: self.players[t].piece_count() for t in alive}
            max_count = max(counts.values())
            winners = [t for t, c in counts.items() if c == max_count]
            if len(winners) == 1:
                return winners[0].value
            return "DRAW"
        return None

    def scores(self) -> Dict[str, int]:
        return {t.value: self.players[t].piece_count() for t in PieceType}
