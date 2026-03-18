#include "agent.h"

int main() {
    std::srand(std::time(nullptr));

    while (true) {
        GameState gs = read_state();
        std::vector<Action> actions;

        for (auto& piece : gs.my_pieces) {
            // Get all reachable cells for MOVE (radius 2, exclude current)
            auto move_cells = reachable(piece.row, piece.col, 2);
            std::vector<Cell> move_targets;
            for (auto& c : move_cells)
                if (!(c.r == piece.row && c.c == piece.col))
                    move_targets.push_back(c);

            // Get adjacent cells for CLONE (radius 1)
            auto clone_targets = neighbors(piece.row, piece.col);

            bool can_move  = !move_targets.empty();
            bool can_clone = !clone_targets.empty();

            if (!can_move && !can_clone) continue;

            // Random choice: 40% CLONE, 60% MOVE (if both available)
            bool do_clone = can_clone && (!can_move || (std::rand() % 10 < 4));

            if (do_clone) {
                auto& t = clone_targets[std::rand() % clone_targets.size()];
                actions.push_back({piece.id, "CLONE", t.r, t.c});
            } else {
                auto& t = move_targets[std::rand() % move_targets.size()];
                actions.push_back({piece.id, "MOVE", t.r, t.c});
            }
        }

        write_actions(actions);
    }
    return 0;
}
