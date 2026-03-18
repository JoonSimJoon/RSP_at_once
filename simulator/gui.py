"""
Pygame GUI for 동시가위바위보 (Simultaneous Rock-Paper-Scissors).

Usage:
    python -m simulator.gui --scissors human --rock ai --paper ai
"""
from __future__ import annotations

import sys
import os
import math
import random
import argparse
from enum import Enum
from collections import deque
from typing import Dict, List, Optional, Set, Tuple

# ---------------------------------------------------------------------------
# Path setup so we can import simulator.engine.*
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame

from simulator.engine.map import TriangularGrid, SIDE
from simulator.engine.state import GameState, PieceType, Action, BEATS, PIECE_CAP, Piece
from simulator.engine.combat import resolve_combat

# ===========================================================================
# Constants
# ===========================================================================

UNIT_S = 48
H = UNIT_S * math.sqrt(3) / 2
GRID_CX = 480
GRID_TOP = 30

SCREEN_W, SCREEN_H = 1200, 780

COLORS = {
    "bg": (240, 235, 220),
    "cell_up": (215, 210, 195),
    "cell_down": (195, 190, 175),
    "cell_border": (160, 155, 140),
    "highlight_move": (140, 180, 255),
    "highlight_clone": (120, 220, 140),
    "selected_border": (255, 220, 0),
    "action_border": (255, 160, 0),
    "SCISSORS": (210, 55, 55),
    "ROCK": (90, 90, 90),
    "PAPER": (55, 110, 210),
    "panel_bg": (50, 50, 60),
    "text": (240, 240, 230),
    "btn_move": (80, 120, 200),
    "btn_clone": (60, 170, 80),
    "btn_confirm": (180, 140, 40),
    "btn_hover": (255, 255, 200),
}

TYPE_KO = {
    PieceType.SCISSORS: "가위",
    PieceType.ROCK: "바위",
    PieceType.PAPER: "보",
}

PIECE_SYMBOL = {
    PieceType.SCISSORS: "✂",
    PieceType.ROCK: "✊",
    PieceType.PAPER: "✋",
}

# ===========================================================================
# Phases
# ===========================================================================


class GamePhase(Enum):
    START = "start"
    INPUT_SCISSORS = "input_scissors"
    INPUT_ROCK = "input_rock"
    INPUT_PAPER = "input_paper"
    APPLYING = "applying"
    COMBAT = "combat"
    GAME_OVER = "game_over"


PHASE_ORDER = [GamePhase.INPUT_SCISSORS, GamePhase.INPUT_ROCK, GamePhase.INPUT_PAPER]

PHASE_TO_TYPE = {
    GamePhase.INPUT_SCISSORS: PieceType.SCISSORS,
    GamePhase.INPUT_ROCK: PieceType.ROCK,
    GamePhase.INPUT_PAPER: PieceType.PAPER,
}

# ===========================================================================
# Pixel <-> Cell coordinate helpers
# ===========================================================================


def cell_vertices(r: int, c: int) -> List[Tuple[float, float]]:
    """Return 3 (x, y) pixel vertices for cell (r, c)."""
    x_left = GRID_CX - (r + 1) * UNIT_S / 2
    y_top = GRID_TOP + r * H
    y_bot = GRID_TOP + (r + 1) * H

    if c % 2 == 0:  # upward triangle
        k = c // 2
        return [
            (x_left + k * UNIT_S, y_bot),
            (x_left + (k + 1) * UNIT_S, y_bot),
            (x_left + k * UNIT_S + UNIT_S / 2, y_top),
        ]
    else:  # downward triangle
        k = (c - 1) // 2
        return [
            (x_left + k * UNIT_S + UNIT_S / 2, y_top),
            (x_left + (k + 1) * UNIT_S + UNIT_S / 2, y_top),
            (x_left + (k + 1) * UNIT_S, y_bot),
        ]


def point_in_triangle(
    px: float, py: float, verts: List[Tuple[float, float]]
) -> bool:
    ax, ay = verts[0]
    bx, by = verts[1]
    cx, cy = verts[2]

    def sign(p1x, p1y, p2x, p2y, p3x, p3y):
        return (p1x - p3x) * (p2y - p3y) - (p2x - p3x) * (p1y - p3y)

    d1 = sign(px, py, ax, ay, bx, by)
    d2 = sign(px, py, bx, by, cx, cy)
    d3 = sign(px, py, cx, cy, ax, ay)
    has_neg = (d1 < 0) or (d2 < 0) or (d3 < 0)
    has_pos = (d1 > 0) or (d2 > 0) or (d3 > 0)
    return not (has_neg and has_pos)


def pixel_to_cell(mx: float, my: float) -> Optional[Tuple[int, int]]:
    """Convert pixel coordinates to grid (r, c) or None."""
    r = int((my - GRID_TOP) / H)
    if r < 0 or r >= SIDE:
        return None
    x_left = GRID_CX - (r + 1) * UNIT_S / 2
    col_f = (mx - x_left) / (UNIT_S / 2)
    c = int(col_f)
    if c < 0 or c > 2 * r:
        return None
    verts = cell_vertices(r, c)
    if point_in_triangle(mx, my, verts):
        return (r, c)
    for dc in [-1, 1]:
        nc = c + dc
        if 0 <= nc <= 2 * r:
            verts2 = cell_vertices(r, nc)
            if point_in_triangle(mx, my, verts2):
                return (r, nc)
    return None


# ===========================================================================
# AI move generator
# ===========================================================================


def ai_move(
    state: GameState, ptype: PieceType, grid: TriangularGrid
) -> List[Action]:
    """Generate random valid actions for an AI player."""
    actions: List[Action] = []
    player = state.players[ptype]
    for piece in player.living_pieces():
        move_targets = list(
            grid.reachable(piece.row, piece.col, 2) - {(piece.row, piece.col)}
        )
        clone_targets = grid.neighbors(piece.row, piece.col)
        if (
            clone_targets
            and player.piece_count() < PIECE_CAP
            and random.random() < 0.35
        ):
            t = random.choice(clone_targets)
            actions.append(Action(piece.id, "CLONE", t[0], t[1]))
        elif move_targets:
            t = random.choice(move_targets)
            actions.append(Action(piece.id, "MOVE", t[0], t[1]))
    return actions


# ===========================================================================
# Game class
# ===========================================================================


class Game:
    def __init__(self, human_types: set):
        self.grid = TriangularGrid()
        self.state = GameState(self.grid)
        self.human_types: set = set(human_types)
        self.phase = GamePhase.START
        self.pending_actions: Dict[PieceType, List[Action]] = {}

        # Per-turn UI state
        self.selected_piece: Optional[Piece] = None
        self.action_mode: str = "MOVE"
        self.piece_actions: Dict[int, Action] = {}
        self.move_targets: Set[Tuple[int, int]] = set()
        self.clone_targets: Set[Tuple[int, int]] = set()
        self.last_kills: List[Piece] = []
        self.winner: Optional[str] = None
        self.apply_timer: int = 0
        self.combat_timer: int = 0

        # Button rects populated during draw, used during click handling
        self.btn_rects: Dict[str, pygame.Rect] = {}

    # ----- helpers --------------------------------------------------------

    def current_ptype(self) -> Optional[PieceType]:
        return PHASE_TO_TYPE.get(self.phase)

    def _update_targets(self):
        if not self.selected_piece:
            self.move_targets = set()
            self.clone_targets = set()
            return
        p = self.selected_piece
        r2 = self.grid.reachable(p.row, p.col, 2)
        r2.discard((p.row, p.col))
        self.move_targets = r2
        self.clone_targets = set(self.grid.neighbors(p.row, p.col))

    def _clear_selection(self):
        self.selected_piece = None
        self.move_targets = set()
        self.clone_targets = set()

    # ----- phase transitions ----------------------------------------------

    def confirm_turn(self):
        """Confirm current player's turn and advance to next phase."""
        ptype = self.current_ptype()
        if ptype is None:
            return
        actions = list(self.piece_actions.values())
        self.pending_actions[ptype] = actions
        self.piece_actions = {}
        self._clear_selection()

        idx = PHASE_ORDER.index(self.phase)
        if idx < 2:
            next_phase = PHASE_ORDER[idx + 1]
            self.phase = next_phase
            next_ptype = PHASE_TO_TYPE[next_phase]
            if next_ptype not in self.human_types:
                self.auto_advance_ai()
        else:
            self.phase = GamePhase.APPLYING
            self.apply_timer = 60

    def auto_advance_ai(self):
        """Auto-generate and confirm AI players until a human phase or APPLYING."""
        ptype = self.current_ptype()
        while ptype and ptype not in self.human_types:
            ai_actions = ai_move(self.state, ptype, self.grid)
            self.pending_actions[ptype] = ai_actions
            idx = PHASE_ORDER.index(self.phase)
            if idx < 2:
                self.phase = PHASE_ORDER[idx + 1]
                ptype = PHASE_TO_TYPE[self.phase]
            else:
                self.phase = GamePhase.APPLYING
                self.apply_timer = 60
                return

    def _auto_ai_if_needed(self):
        if self.phase in PHASE_ORDER:
            ptype = PHASE_TO_TYPE[self.phase]
            if ptype not in self.human_types:
                self.auto_advance_ai()

    def apply_round(self):
        self.state.turn += 1
        self.state.apply_actions(self.pending_actions)
        self.pending_actions = {}
        self.phase = GamePhase.COMBAT
        self.combat_timer = 90

    def resolve_combat_phase(self):
        self.last_kills = resolve_combat(self.state)
        winner = self.state.check_winner()
        if winner:
            self.winner = winner
            self.phase = GamePhase.GAME_OVER
        else:
            self.phase = GamePhase.INPUT_SCISSORS
            ptype = PieceType.SCISSORS
            if ptype not in self.human_types:
                self.auto_advance_ai()

    # ----- update ---------------------------------------------------------

    def update(self):
        if self.phase == GamePhase.APPLYING:
            self.apply_timer -= 1
            if self.apply_timer <= 0:
                self.apply_round()
        elif self.phase == GamePhase.COMBAT:
            self.combat_timer -= 1
            if self.combat_timer <= 0:
                self.resolve_combat_phase()

    # ----- input ----------------------------------------------------------

    def handle_click(self, mx: int, my: int):
        # ----- START phase ------------------------------------------------
        if self.phase == GamePhase.START:
            for t in PieceType:
                key = f"toggle_{t.value}"
                rect = self.btn_rects.get(key)
                if rect and rect.collidepoint(mx, my):
                    if t in self.human_types:
                        self.human_types.discard(t)
                    else:
                        self.human_types.add(t)
                    return
            start_rect = self.btn_rects.get("start")
            if start_rect and start_rect.collidepoint(mx, my):
                self.phase = GamePhase.INPUT_SCISSORS
                self._auto_ai_if_needed()
            return

        # ----- Info panel buttons -----------------------------------------
        if mx >= 900 and self.phase in PHASE_ORDER:
            ptype = PHASE_TO_TYPE[self.phase]
            if ptype in self.human_types:
                move_rect = self.btn_rects.get("mode_MOVE")
                if move_rect and move_rect.collidepoint(mx, my):
                    self.action_mode = "MOVE"
                    if self.selected_piece:
                        self._update_targets()
                    return
                clone_rect = self.btn_rects.get("mode_CLONE")
                if clone_rect and clone_rect.collidepoint(mx, my):
                    self.action_mode = "CLONE"
                    if self.selected_piece:
                        self._update_targets()
                    return
                confirm_rect = self.btn_rects.get("confirm")
                if confirm_rect and confirm_rect.collidepoint(mx, my):
                    self.confirm_turn()
                    return
            return

        # ----- Grid click -------------------------------------------------
        cell = pixel_to_cell(mx, my)
        if cell:
            self.handle_cell_click(*cell)

    def handle_cell_click(self, r: int, c: int):
        if self.phase not in PHASE_ORDER:
            return
        ptype = PHASE_TO_TYPE[self.phase]
        if ptype not in self.human_types:
            return
        player = self.state.players[ptype]

        # Click on own piece?
        my_pieces_here = [
            p for p in player.living_pieces() if p.row == r and p.col == c
        ]

        if my_pieces_here:
            p = my_pieces_here[0]
            if self.selected_piece and self.selected_piece.id == p.id:
                # Deselect
                self._clear_selection()
            else:
                self.selected_piece = p
                self._update_targets()
            return

        # Click on target cell
        if self.selected_piece:
            if self.action_mode == "MOVE" and (r, c) in self.move_targets:
                self.piece_actions[self.selected_piece.id] = Action(
                    self.selected_piece.id, "MOVE", r, c
                )
                self._clear_selection()
            elif self.action_mode == "CLONE" and (r, c) in self.clone_targets:
                if player.piece_count() < PIECE_CAP:
                    self.piece_actions[self.selected_piece.id] = Action(
                        self.selected_piece.id, "CLONE", r, c
                    )
                self._clear_selection()

    # ----- drawing --------------------------------------------------------

    def draw(self, screen: pygame.Surface, fonts: dict):
        self.btn_rects = {}
        screen.fill(COLORS["bg"])
        self._draw_grid(screen, fonts)
        self._draw_info_panel(screen, fonts)

    def _draw_grid(self, screen: pygame.Surface, fonts: dict):
        ptype = self.current_ptype()

        for r, c in self.grid.all_cells():
            verts = cell_vertices(r, c)

            # Base colour
            if (r, c) in self.move_targets:
                base_color = COLORS["highlight_move"]
            elif (r, c) in self.clone_targets:
                base_color = COLORS["highlight_clone"]
            elif c % 2 == 0:
                base_color = COLORS["cell_up"]
            else:
                base_color = COLORS["cell_down"]

            int_verts = [(int(x), int(y)) for x, y in verts]
            pygame.draw.polygon(screen, base_color, int_verts)
            pygame.draw.polygon(screen, COLORS["cell_border"], int_verts, 1)

            # Pieces on this cell
            pieces_here = [
                p
                for p in self.state.all_living_pieces()
                if p.row == r and p.col == c
            ]
            if not pieces_here:
                continue

            cx_p = sum(v[0] for v in verts) / 3
            cy_p = sum(v[1] for v in verts) / 3

            # Determine special border
            border_col = None
            for p in pieces_here:
                if (
                    self.selected_piece
                    and p.id == self.selected_piece.id
                ):
                    border_col = COLORS["selected_border"]
                    break
                if p.id in self.piece_actions:
                    border_col = COLORS["action_border"]

            p0 = pieces_here[0]
            radius = max(8, int(UNIT_S * 0.28))
            pygame.draw.circle(
                screen,
                COLORS[p0.owner.value],
                (int(cx_p), int(cy_p)),
                radius,
            )
            if border_col:
                pygame.draw.circle(
                    screen,
                    border_col,
                    (int(cx_p), int(cy_p)),
                    radius + 3,
                    3,
                )

            # Count badge for stacked pieces
            if len(pieces_here) > 1:
                badge = fonts["small"].render(
                    str(len(pieces_here)), True, (255, 255, 255)
                )
                screen.blit(
                    badge, (int(cx_p) + radius - 6, int(cy_p) - radius)
                )

            # Symbol
            sym = PIECE_SYMBOL.get(p0.owner, "?")
            sym_surf = fonts["symbol"].render(sym, True, (255, 255, 255))
            sym_rect = sym_surf.get_rect(center=(int(cx_p), int(cy_p)))
            screen.blit(sym_surf, sym_rect)

        # Highlight killed pieces during COMBAT phase
        if self.phase == GamePhase.COMBAT and self.last_kills:
            for p in self.last_kills:
                verts = cell_vertices(p.row, p.col)
                int_verts = [(int(x), int(y)) for x, y in verts]
                pygame.draw.polygon(screen, (255, 50, 50), int_verts, 4)

    def _draw_info_panel(self, screen: pygame.Surface, fonts: dict):
        px = 910
        pygame.draw.rect(screen, COLORS["panel_bg"], (900, 0, 300, SCREEN_H))

        y = 20
        # Title
        title = fonts["title"].render("동시가위바위보", True, COLORS["text"])
        screen.blit(title, (px, y))
        y += 40

        # Turn info
        turn_txt = fonts["mid"].render(
            f"Turn {self.state.turn}", True, (200, 200, 180)
        )
        screen.blit(turn_txt, (px, y))
        y += 30

        # Score
        for t in PieceType:
            cnt = self.state.players[t].piece_count()
            col = COLORS[t.value]
            ko = TYPE_KO[t]
            s = fonts["mid"].render(f"{ko}: {cnt}개", True, col)
            screen.blit(s, (px, y))
            y += 26
        y += 10

        # ----- Phase-specific content ------------------------------------
        if self.phase in PHASE_ORDER:
            self._draw_input_phase(screen, fonts, px, y)
        elif self.phase == GamePhase.APPLYING:
            msg = fonts["mid"].render(
                "▶ 이동 적용 중...", True, (255, 220, 100)
            )
            screen.blit(msg, (px, y))
        elif self.phase == GamePhase.COMBAT:
            msg = fonts["mid"].render(
                "⚔ 전투 해결 중...", True, (255, 100, 100)
            )
            screen.blit(msg, (px, y))
            y += 30
            if self.last_kills:
                k = fonts["small"].render(
                    f"{len(self.last_kills)}개 기물 제거됨",
                    True,
                    (220, 120, 120),
                )
                screen.blit(k, (px, y))
        elif self.phase == GamePhase.GAME_OVER:
            self._draw_game_over(screen, fonts, px, y)
        elif self.phase == GamePhase.START:
            self._draw_start(screen, fonts, px, y)

    def _draw_input_phase(
        self, screen: pygame.Surface, fonts: dict, px: int, y: int
    ):
        ptype = PHASE_TO_TYPE[self.phase]
        ko = TYPE_KO[ptype]
        is_human = ptype in self.human_types
        mode_str = "👤 사람" if is_human else "🤖 AI"
        ph = fonts["mid"].render(
            f"▶ {ko} 차례 ({mode_str})", True, COLORS[ptype.value]
        )
        screen.blit(ph, (px, y))
        y += 30

        if not is_human:
            return

        y += 10
        # MOVE / CLONE buttons
        for mode, col, label in [
            ("MOVE", COLORS["btn_move"], "이동 (반경2)"),
            ("CLONE", COLORS["btn_clone"], "복제 (반경1)"),
        ]:
            btn_col = col if self.action_mode == mode else (80, 80, 80)
            rect = pygame.Rect(px, y, 130, 34)
            pygame.draw.rect(screen, btn_col, rect, border_radius=6)
            txt = fonts["mid"].render(label, True, (255, 255, 255))
            screen.blit(txt, (px + 8, y + 7))
            self.btn_rects[f"mode_{mode}"] = rect
            y += 42

        y += 5
        # Assigned actions count
        ptype_cur = self.current_ptype()
        total_pieces = (
            self.state.players[ptype_cur].piece_count() if ptype_cur else 0
        )
        assigned = len(self.piece_actions)
        prog = fonts["small"].render(
            f"기물 {assigned}/{total_pieces} 설정됨", True, (180, 220, 180)
        )
        screen.blit(prog, (px, y))
        y += 25

        # Confirm button
        y += 5
        rect = pygame.Rect(px, y, 170, 40)
        pygame.draw.rect(screen, COLORS["btn_confirm"], rect, border_radius=8)
        conf_txt = fonts["mid"].render("✔ 턴 확인", True, (255, 255, 255))
        screen.blit(conf_txt, (px + 20, y + 10))
        self.btn_rects["confirm"] = rect
        y += 50

        # Help hints
        y += 5
        for hint in [
            "• 기물 클릭 → 선택",
            "• 목표 클릭 → 배치",
            "• 다시 기물 클릭 → 취소",
            "• M키: 이동, C키: 복제",
            "• Enter: 턴 확인",
        ]:
            h = fonts["small"].render(hint, True, (160, 160, 140))
            screen.blit(h, (px, y))
            y += 20

    def _draw_game_over(
        self, screen: pygame.Surface, fonts: dict, px: int, y: int
    ):
        y += 20
        if self.winner == "DRAW":
            w_txt = "무승부!"
        else:
            winner_type = PieceType(self.winner)
            w_txt = f"🏆 {TYPE_KO[winner_type]} 승리!"
        ww = fonts["title"].render(w_txt, True, (255, 220, 50))
        screen.blit(ww, (px, y))
        y += 50
        for t in PieceType:
            cnt = self.state.players[t].piece_count()
            s = fonts["mid"].render(f"{TYPE_KO[t]}: {cnt}개", True, COLORS[t.value])
            screen.blit(s, (px, y))
            y += 26
        y += 20
        restart = fonts["mid"].render("R키: 재시작", True, (200, 200, 200))
        screen.blit(restart, (px, y))

    def _draw_start(
        self, screen: pygame.Surface, fonts: dict, px: int, y: int
    ):
        y += 20
        st = fonts["mid"].render("시작 설정", True, COLORS["text"])
        screen.blit(st, (px, y))
        y += 35

        for t in PieceType:
            ko = TYPE_KO[t]
            is_h = t in self.human_types
            col = COLORS[t.value]
            label = f"{ko}: {'👤 사람' if is_h else '🤖 AI'}"
            txt = fonts["mid"].render(label, True, col)
            rect = pygame.Rect(px, y, 180, 26)
            screen.blit(txt, (px, y))
            self.btn_rects[f"toggle_{t.value}"] = rect
            y += 30

        y += 20
        rect = pygame.Rect(px, y, 160, 42)
        pygame.draw.rect(screen, (80, 160, 80), rect, border_radius=8)
        go = fonts["mid"].render("▶ 게임 시작", True, (255, 255, 255))
        screen.blit(go, (px + 15, y + 11))
        self.btn_rects["start"] = rect


# ===========================================================================
# Main
# ===========================================================================


def main():
    ap = argparse.ArgumentParser(description="동시가위바위보 GUI")
    ap.add_argument(
        "--scissors", default="human", choices=["human", "ai"]
    )
    ap.add_argument("--rock", default="ai", choices=["human", "ai"])
    ap.add_argument("--paper", default="ai", choices=["human", "ai"])
    args = ap.parse_args()

    human_types: set = set()
    if args.scissors == "human":
        human_types.add(PieceType.SCISSORS)
    if args.rock == "human":
        human_types.add(PieceType.ROCK)
    if args.paper == "human":
        human_types.add(PieceType.PAPER)

    pygame.init()
    screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
    pygame.display.set_caption("동시가위바위보")
    clock = pygame.time.Clock()

    # Try to load a Korean-capable font
    font_families = "malgungothic,microsoftyaheimicrosoftyaheiui,arial"
    fonts = {
        "title": pygame.font.SysFont(font_families, 20, bold=True),
        "mid": pygame.font.SysFont(font_families, 15),
        "small": pygame.font.SysFont(font_families, 12),
        "symbol": pygame.font.SysFont("segoeuisymbol,seguiemoji,arial", 14),
    }

    game = Game(human_types)

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            elif event.type == pygame.KEYDOWN:
                if (
                    event.key == pygame.K_r
                    and game.phase == GamePhase.GAME_OVER
                ):
                    game = Game(human_types)
                if event.key == pygame.K_ESCAPE:
                    running = False
                if event.key == pygame.K_m and game.phase in PHASE_ORDER:
                    game.action_mode = "MOVE"
                    if game.selected_piece:
                        game._update_targets()
                if event.key == pygame.K_c and game.phase in PHASE_ORDER:
                    game.action_mode = "CLONE"
                    if game.selected_piece:
                        game._update_targets()
                if event.key == pygame.K_RETURN and game.phase in PHASE_ORDER:
                    ptype = PHASE_TO_TYPE[game.phase]
                    if ptype in game.human_types:
                        game.confirm_turn()

            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                mx, my = event.pos
                game.handle_click(mx, my)

        game.update()
        game.draw(screen, fonts)
        pygame.display.flip()
        clock.tick(60)

    pygame.quit()


if __name__ == "__main__":
    main()
