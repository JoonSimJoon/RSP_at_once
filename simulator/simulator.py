"""
동시가위바위보 simulator — main entry point.

Usage:
  python simulator.py --agent-scissors ./agents/random_agent \
                      --agent-rock     ./agents/random_agent \
                      --agent-paper    ./agents/greedy_agent \
                      [--max-turns 200] [--timeout-ms 1000] \
                      [--replay replays/game.jsonl] [--no-color] [--quiet]
"""
from __future__ import annotations
import argparse
import subprocess
import sys
import os
import json
import shlex
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Allow running as script from any directory
sys.path.insert(0, str(Path(__file__).parent.parent))

from simulator.engine.map import TriangularGrid
from simulator.engine.state import GameState, PieceType, Action, MAX_TURNS
from simulator.engine.combat import resolve_combat
from simulator.engine.protocol import encode_state, decode_actions
from simulator.visualizer import print_state
from simulator.replay import ReplayWriter


def _read_line_timeout(proc: subprocess.Popen, timeout_s: float) -> Optional[str]:
    """Read one line from proc.stdout with a timeout. Returns None on timeout/error."""
    result: list = []
    error: list = []

    def _reader():
        try:
            line = proc.stdout.readline()
            result.append(line)
        except Exception as e:
            error.append(str(e))

    t = threading.Thread(target=_reader, daemon=True)
    t.start()
    t.join(timeout=timeout_s)
    if t.is_alive():
        return None  # timeout
    if error or not result:
        return None
    line = result[0]
    if isinstance(line, bytes):
        line = line.decode("utf-8", errors="replace")
    return line.strip() or None


def collect_actions(
    procs: Dict[PieceType, subprocess.Popen],
    state: GameState,
    timeout_s: float,
) -> Dict[PieceType, List[Action]]:
    """Send state to all agents and collect their responses simultaneously."""
    # Send state to all agents
    for ptype, proc in procs.items():
        if not state.players[ptype].is_alive():
            continue
        try:
            msg = encode_state(state, ptype) + "\n"
            proc.stdin.write(msg.encode("utf-8"))
            proc.stdin.flush()
        except (BrokenPipeError, OSError):
            pass

    # Collect responses
    all_actions: Dict[PieceType, List[Action]] = {}
    for ptype, proc in procs.items():
        if not state.players[ptype].is_alive():
            all_actions[ptype] = []
            continue
        raw = _read_line_timeout(proc, timeout_s)
        if raw:
            all_actions[ptype] = decode_actions(raw, ptype)
        else:
            all_actions[ptype] = []  # timeout → no-op

    return all_actions


def run_match(
    agent_cmds: Dict[PieceType, str],
    max_turns: int = MAX_TURNS,
    timeout_ms: int = 1000,
    replay_path: Optional[str] = None,
    quiet: bool = False,
    no_color: bool = False,
) -> Tuple[str, Dict[str, int]]:
    """
    Run a full match. Returns (winner_str, scores_dict).
    winner_str is PieceType value or "DRAW".
    """
    grid = TriangularGrid()
    state = GameState(grid, max_turns=max_turns)
    timeout_s = timeout_ms / 1000.0

    # Spawn agent subprocesses
    procs: Dict[PieceType, subprocess.Popen] = {}
    for ptype, cmd in agent_cmds.items():
        try:
            args = shlex.split(cmd) if isinstance(cmd, str) else cmd
            proc = subprocess.Popen(
                args,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                shell=False,
            )
            procs[ptype] = proc
        except Exception as e:
            print(f"ERROR: Failed to start agent for {ptype.value}: {e}", file=sys.stderr)
            # Eliminate player immediately
            for p in state.players[ptype].pieces:
                p.alive = False

    # Replay writer
    writer = None
    if replay_path:
        agents_info = {t.value: cmd for t, cmd in agent_cmds.items()}
        writer = ReplayWriter(replay_path, agents_info, grid.side, max_turns)

    try:
        if not quiet:
            print_state(state, no_color=no_color)

        while True:
            state.turn += 1

            # Collect actions from all agents
            all_actions = collect_actions(procs, state, timeout_s)

            # Apply actions simultaneously
            state.apply_actions(all_actions)

            # Resolve combat
            kills = resolve_combat(state)

            # Record replay
            if writer:
                writer.write_turn(state, all_actions, kills)

            # Visualize
            if not quiet:
                print_state(state, no_color=no_color)
                if kills:
                    kill_str = ", ".join(
                        f"{p.owner.value}#{p.id}" for p in kills
                    )
                    print(f"  ☠  Killed: {kill_str}")

            # Check winner
            result = state.check_winner()
            if result is not None:
                if writer:
                    writer.write_result(result, state.scores())
                return result, state.scores()

    finally:
        for proc in procs.values():
            try:
                proc.terminate()
                proc.wait(timeout=2)
            except Exception:
                pass
        if writer:
            writer.close()


def main():
    parser = argparse.ArgumentParser(description="동시가위바위보 Simulator")
    parser.add_argument("--agent-scissors", required=True, help="Command for SCISSORS agent")
    parser.add_argument("--agent-rock",     required=True, help="Command for ROCK agent")
    parser.add_argument("--agent-paper",    required=True, help="Command for PAPER agent")
    parser.add_argument("--max-turns",  type=int, default=MAX_TURNS)
    parser.add_argument("--timeout-ms", type=int, default=1000)
    parser.add_argument("--replay",     type=str, default=None, help="Path to save JSONL replay")
    parser.add_argument("--quiet",      action="store_true", help="No visualization")
    parser.add_argument("--no-color",   action="store_true", help="Disable ANSI colors")
    args = parser.parse_args()

    agent_cmds = {
        PieceType.SCISSORS: args.agent_scissors,
        PieceType.ROCK:     args.agent_rock,
        PieceType.PAPER:    args.agent_paper,
    }

    winner, scores = run_match(
        agent_cmds,
        max_turns=args.max_turns,
        timeout_ms=args.timeout_ms,
        replay_path=args.replay,
        quiet=args.quiet,
        no_color=args.no_color,
    )

    print(f"\n{'='*40}")
    print(f"WINNER: {winner}")
    print(f"Scores: {scores}")
    print(f"{'='*40}")


if __name__ == "__main__":
    main()
