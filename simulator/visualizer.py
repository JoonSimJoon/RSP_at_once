"""ASCII visualizer for 동시가위바위보 triangular grid."""
import sys
from typing import Optional
from .engine.state import GameState, PieceType

ANSI = {
    PieceType.SCISSORS: "\033[93m",   # yellow
    PieceType.ROCK:     "\033[91m",   # red
    PieceType.PAPER:    "\033[96m",   # cyan
}
RESET = "\033[0m"
USE_COLOR = sys.stdout.isatty()

SYMBOL = {PieceType.SCISSORS: "S", PieceType.ROCK: "R", PieceType.PAPER: "P"}


def render(state: GameState, no_color: bool = False) -> str:
    """Return ASCII string representation of current game state."""
    use_color = USE_COLOR and not no_color

    # Build cell → display string map
    # cell_info[(r,c)] = (symbol_char, owner) or None
    cell_map: dict = {}
    for piece in state.all_living_pieces():
        key = (piece.row, piece.col)
        if key not in cell_map:
            cell_map[key] = {}
        cell_map[key][piece.owner] = cell_map[key].get(piece.owner, 0) + 1

    lines = []
    # Header
    scores = state.scores()
    header = f"Turn {state.turn}/{state.max_turns}  |  "
    header += "  ".join(
        f"{SYMBOL[t]}:{scores[t.value]}" for t in PieceType
    )
    lines.append(header)
    lines.append("")

    max_cols = 2 * (state.grid.side - 1)  # = 20 for side=11
    for r in range(state.grid.side):
        indent = " " * (max_cols - 2 * r)  # center the row
        row_parts = [indent]
        for c in range(2 * r + 1):
            is_up = (c % 2 == 0)
            prefix = "△" if is_up else "▽"
            owners = cell_map.get((r, c), {})
            if not owners:
                cell_str = prefix + "."
            else:
                # Pick dominant owner (most pieces)
                dominant = max(owners, key=lambda t: owners[t])
                count = owners[dominant]
                sym = SYMBOL[dominant]
                if count > 1:
                    sym = f"{sym}{min(count,9)}"
                else:
                    sym = f"{sym} "
                if use_color:
                    cell_str = ANSI[dominant] + prefix + sym + RESET
                else:
                    cell_str = prefix + sym
            row_parts.append(cell_str)
        lines.append("".join(row_parts))

    lines.append("")
    return "\n".join(lines)


def print_state(state: GameState, no_color: bool = False):
    print(render(state, no_color=no_color))
