"""
Triangular grid for 동시가위바위보.

Grid structure (side=11, 121 total cells):
  Row k has (2k+1) cells, col index 0..2k
  Cell (r,c) is UPWARD triangle (△) if c is even
  Cell (r,c) is DOWNWARD triangle (▽) if c is odd

Adjacency:
  △(r,c) [c even]: (r,c-1), (r,c+1), (r+1,c+1)
  ▽(r,c) [c odd]:  (r,c-1), (r,c+1), (r-1,c-1)
  All results filtered by is_valid().
"""
from __future__ import annotations
from collections import deque
from typing import List, Tuple, Set


SIDE = 11  # triangle side length → 11^2 = 121 cells


class TriangularGrid:
    def __init__(self, side: int = SIDE):
        self.side = side
        self._adj_cache: dict[tuple, list] = {}
        self._reach_cache: dict[tuple, set] = {}

    def is_valid(self, r: int, c: int) -> bool:
        return 0 <= r < self.side and 0 <= c <= 2 * r

    def is_upward(self, r: int, c: int) -> bool:
        return c % 2 == 0

    def neighbors(self, r: int, c: int) -> List[Tuple[int, int]]:
        key = (r, c)
        if key in self._adj_cache:
            return self._adj_cache[key]
        if c % 2 == 0:  # upward △
            candidates = [(r, c - 1), (r, c + 1), (r + 1, c + 1)]
        else:           # downward ▽
            candidates = [(r, c - 1), (r, c + 1), (r - 1, c - 1)]
        result = [(nr, nc) for (nr, nc) in candidates if self.is_valid(nr, nc)]
        self._adj_cache[key] = result
        return result

    def reachable(self, r: int, c: int, radius: int) -> Set[Tuple[int, int]]:
        key = (r, c, radius)
        if key in self._reach_cache:
            return self._reach_cache[key]
        visited: Set[Tuple[int, int]] = {(r, c)}
        queue: deque = deque([(r, c, 0)])
        while queue:
            cr, cc, dist = queue.popleft()
            if dist >= radius:
                continue
            for nr, nc in self.neighbors(cr, cc):
                if (nr, nc) not in visited:
                    visited.add((nr, nc))
                    queue.append((nr, nc, dist + 1))
        self._reach_cache[key] = visited
        return visited

    def distance(self, r1: int, c1: int, r2: int, c2: int) -> int:
        if (r1, c1) == (r2, c2):
            return 0
        visited = {(r1, c1)}
        queue: deque = deque([(r1, c1, 0)])
        while queue:
            cr, cc, dist = queue.popleft()
            for nr, nc in self.neighbors(cr, cc):
                if (nr, nc) == (r2, c2):
                    return dist + 1
                if (nr, nc) not in visited:
                    visited.add((nr, nc))
                    queue.append((nr, nc, dist + 1))
        return 999  # unreachable

    def all_cells(self) -> List[Tuple[int, int]]:
        return [(r, c) for r in range(self.side) for c in range(2 * r + 1)]
