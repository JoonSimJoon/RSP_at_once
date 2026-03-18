#include "agent.h"

// Manhattan-like BFS distance to nearest enemy of given type
int nearestEnemy(int r, int c, PieceType target_type,
                 const std::vector<EnemyPiece>& enemies) {
    int best = 999;
    for (auto& e : enemies) {
        if (e.type != target_type) continue;
        int d = distance(r, c, e.row, e.col);
        if (d < best) { best = d; }
    }
    return best;
}

Cell nearestEnemyCell(int r, int c, PieceType target_type,
                      const std::vector<EnemyPiece>& enemies) {
    int best = 999;
    Cell best_cell{r, c};
    for (auto& e : enemies) {
        if (e.type != target_type) continue;
        int d = distance(r, c, e.row, e.col);
        if (d < best) { best = d; best_cell = {e.row, e.col}; }
    }
    return best_cell;
}

// Among reachable cells, pick the one closest to target
Cell moveToward(int r, int c, Cell target, int radius) {
    auto cells = reachable(r, c, radius);
    Cell best{r, c};
    int best_dist = distance(r, c, target.r, target.c);
    for (auto& cc : cells) {
        if (cc.r == r && cc.c == c) continue;
        int d = distance(cc.r, cc.c, target.r, target.c);
        if (d < best_dist) { best_dist = d; best = cc; }
    }
    return best;
}

// Among reachable cells, pick the one farthest from threat
Cell moveAway(int r, int c, Cell threat, int radius) {
    auto cells = reachable(r, c, radius);
    Cell best{r, c};
    int best_dist = distance(r, c, threat.r, threat.c);
    for (auto& cc : cells) {
        if (cc.r == r && cc.c == c) continue;
        int d = distance(cc.r, cc.c, threat.r, threat.c);
        if (d > best_dist) { best_dist = d; best = cc; }
    }
    return best;
}

int main() {
    std::srand(std::time(nullptr));

    while (true) {
        GameState gs = read_state();
        std::vector<Action> actions;
        PieceType my = gs.my_type;
        PieceType my_prey      = prey(my);
        PieceType my_predator  = predator(my);

        // Build set of enemy positions for quick lookup
        std::set<Cell> predator_cells;
        for (auto& e : gs.enemy_pieces)
            if (e.type == my_predator)
                predator_cells.insert({e.row, e.col});

        for (auto& piece : gs.my_pieces) {
            // 1. Is prey within MOVE radius (2)?
            int prey_dist = nearestEnemy(piece.row, piece.col, my_prey, gs.enemy_pieces);
            if (prey_dist > 0 && prey_dist <= 3) {
                Cell target = nearestEnemyCell(piece.row, piece.col, my_prey, gs.enemy_pieces);
                Cell dest   = moveToward(piece.row, piece.col, target, 2);
                if (!(dest.r == piece.row && dest.c == piece.col)) {
                    actions.push_back({piece.id, "MOVE", dest.r, dest.c});
                    continue;
                }
            }

            // 2. Is predator adjacent?
            bool predator_adjacent = false;
            Cell threat_cell{-1,-1};
            for (auto& nb : neighbors(piece.row, piece.col)) {
                if (predator_cells.count(nb)) {
                    predator_adjacent = true;
                    threat_cell = nb;
                    break;
                }
            }
            if (predator_adjacent) {
                Cell dest = moveAway(piece.row, piece.col, threat_cell, 2);
                if (!(dest.r == piece.row && dest.c == piece.col)) {
                    actions.push_back({piece.id, "MOVE", dest.r, dest.c});
                    continue;
                }
            }

            // 3. Default: try to CLONE away from predators, else random MOVE
            auto nbs = neighbors(piece.row, piece.col);
            std::vector<Cell> safe_nbs;
            for (auto& nb : nbs)
                if (!predator_cells.count(nb))
                    safe_nbs.push_back(nb);

            if (!safe_nbs.empty() && std::rand() % 2 == 0) {
                auto& t = safe_nbs[std::rand() % safe_nbs.size()];
                actions.push_back({piece.id, "CLONE", t.r, t.c});
            } else {
                auto move_cells = reachable(piece.row, piece.col, 2);
                std::vector<Cell> move_targets;
                for (auto& c : move_cells)
                    if (!(c.r == piece.row && c.c == piece.col))
                        move_targets.push_back(c);
                if (!move_targets.empty()) {
                    auto& t = move_targets[std::rand() % move_targets.size()];
                    actions.push_back({piece.id, "MOVE", t.r, t.c});
                }
            }
        }

        write_actions(actions);
    }
    return 0;
}
