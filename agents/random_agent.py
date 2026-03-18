"""Python random agent — for testing the simulator without a C++ compiler."""
import sys
import json
import random
from collections import deque

SIDE = 11

def is_valid(r, c):
    return 0 <= r < SIDE and 0 <= c <= 2 * r

def neighbors(r, c):
    if c % 2 == 0:
        cands = [(r, c-1), (r, c+1), (r+1, c+1)]
    else:
        cands = [(r, c-1), (r, c+1), (r-1, c-1)]
    return [(nr, nc) for nr, nc in cands if is_valid(nr, nc)]

def reachable(r, c, radius):
    visited = {(r, c)}
    q = deque([(r, c, 0)])
    while q:
        cr, cc, d = q.popleft()
        if d >= radius:
            continue
        for nr, nc in neighbors(cr, cc):
            if (nr, nc) not in visited:
                visited.add((nr, nc))
                q.append((nr, nc, d + 1))
    return visited

while True:
    line = sys.stdin.readline()
    if not line:
        break
    state = json.loads(line.strip())
    actions = []
    for piece in state["my_pieces"]:
        r, c = piece["row"], piece["col"]
        move_targets = list(reachable(r, c, 2) - {(r, c)})
        clone_targets = neighbors(r, c)
        if not move_targets and not clone_targets:
            continue
        if clone_targets and random.random() < 0.4:
            t = random.choice(clone_targets)
            actions.append({"piece_id": piece["id"], "action": "CLONE", "row": t[0], "col": t[1]})
        elif move_targets:
            t = random.choice(move_targets)
            actions.append({"piece_id": piece["id"], "action": "MOVE", "row": t[0], "col": t[1]})
    print(json.dumps({"actions": actions}), flush=True)
