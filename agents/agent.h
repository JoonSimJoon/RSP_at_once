#pragma once
#include <iostream>
#include <string>
#include <vector>
#include <set>
#include <map>
#include <queue>
#include <algorithm>
#include <sstream>
#include <cstdlib>
#include <ctime>

// ─── Types ──────────────────────────────────────────────────────────────────
enum class PieceType { SCISSORS, ROCK, PAPER, UNKNOWN };

inline PieceType parseType(const std::string& s) {
    if (s == "SCISSORS") return PieceType::SCISSORS;
    if (s == "ROCK")     return PieceType::ROCK;
    if (s == "PAPER")    return PieceType::PAPER;
    return PieceType::UNKNOWN;
}

inline std::string typeStr(PieceType t) {
    switch(t) {
        case PieceType::SCISSORS: return "SCISSORS";
        case PieceType::ROCK:     return "ROCK";
        case PieceType::PAPER:    return "PAPER";
        default:                  return "UNKNOWN";
    }
}

// Returns true if 'attacker' beats 'defender'
inline bool beats(PieceType attacker, PieceType defender) {
    return (attacker == PieceType::SCISSORS && defender == PieceType::PAPER)
        || (attacker == PieceType::ROCK     && defender == PieceType::SCISSORS)
        || (attacker == PieceType::PAPER    && defender == PieceType::ROCK);
}

// What type does my_type beat? (prey)
inline PieceType prey(PieceType t) {
    switch(t) {
        case PieceType::SCISSORS: return PieceType::PAPER;
        case PieceType::ROCK:     return PieceType::SCISSORS;
        case PieceType::PAPER:    return PieceType::ROCK;
        default:                  return PieceType::UNKNOWN;
    }
}

// What type beats my_type? (predator)
inline PieceType predator(PieceType t) {
    switch(t) {
        case PieceType::SCISSORS: return PieceType::ROCK;
        case PieceType::ROCK:     return PieceType::PAPER;
        case PieceType::PAPER:    return PieceType::SCISSORS;
        default:                  return PieceType::UNKNOWN;
    }
}

struct Cell { int r, c; };
inline bool operator==(const Cell& a, const Cell& b) { return a.r==b.r && a.c==b.c; }
inline bool operator<(const Cell& a, const Cell& b)  { return a.r<b.r || (a.r==b.r && a.c<b.c); }

struct MyPiece  { int id, row, col; };
struct EnemyPiece { int row, col; PieceType type; };

struct GameState {
    int turn, max_turns;
    PieceType my_type;
    std::vector<MyPiece>    my_pieces;
    std::vector<EnemyPiece> enemy_pieces;
};

struct Action {
    int piece_id;
    std::string action;  // "MOVE" or "CLONE"
    int row, col;
};

// ─── Grid Math ───────────────────────────────────────────────────────────────
constexpr int SIDE = 11;

inline bool isValid(int r, int c) {
    return r >= 0 && r < SIDE && c >= 0 && c <= 2 * r;
}

inline std::vector<Cell> neighbors(int r, int c) {
    std::vector<Cell> result;
    std::vector<Cell> candidates;
    if (c % 2 == 0) { // upward △
        candidates = {{r, c-1}, {r, c+1}, {r+1, c+1}};
    } else {           // downward ▽
        candidates = {{r, c-1}, {r, c+1}, {r-1, c-1}};
    }
    for (auto& nc : candidates)
        if (isValid(nc.r, nc.c)) result.push_back(nc);
    return result;
}

// BFS reachable cells within 'radius' hops (includes start cell)
inline std::vector<Cell> reachable(int r, int c, int radius) {
    std::set<Cell> visited;
    std::queue<std::tuple<int,int,int>> q;
    visited.insert({r, c});
    q.push({r, c, 0});
    while (!q.empty()) {
        auto [cr, cc, dist] = q.front(); q.pop();
        if (dist >= radius) continue;
        for (auto& nb : neighbors(cr, cc)) {
            if (!visited.count(nb)) {
                visited.insert(nb);
                q.push({nb.r, nb.c, dist+1});
            }
        }
    }
    return std::vector<Cell>(visited.begin(), visited.end());
}

inline int distance(int r1, int c1, int r2, int c2) {
    if (r1==r2 && c1==c2) return 0;
    std::set<Cell> visited;
    std::queue<std::tuple<int,int,int>> q;
    visited.insert({r1,c1});
    q.push({r1,c1,0});
    while (!q.empty()) {
        auto [cr, cc, dist] = q.front(); q.pop();
        for (auto& nb : neighbors(cr, cc)) {
            if (nb.r==r2 && nb.c==c2) return dist+1;
            if (!visited.count(nb)) {
                visited.insert(nb);
                q.push({nb.r, nb.c, dist+1});
            }
        }
    }
    return 999;
}

// ─── Minimal JSON parser ─────────────────────────────────────────────────────
// NOTE: Engine emits compact JSON (no spaces). These parsers tolerate optional
// whitespace after ':' and between tokens for robustness.
// Known limitation: array parser uses naive ']' search — safe as long as
// string values never contain ']' (guaranteed by current protocol).

inline size_t skipWS(const std::string& s, size_t pos) {
    while (pos < s.size() && (s[pos]==' '||s[pos]=='\t'||s[pos]=='\r'||s[pos]=='\n'))
        ++pos;
    return pos;
}

inline std::string jsonGetStr(const std::string& json, const std::string& key) {
    std::string search = "\"" + key + "\"";
    size_t pos = json.find(search);
    if (pos == std::string::npos) return "";
    pos = skipWS(json, pos + search.size());
    if (pos >= json.size() || json[pos] != ':') return "";
    pos = skipWS(json, pos + 1);
    if (pos >= json.size() || json[pos] != '"') return "";
    ++pos;
    size_t end = json.find('"', pos);
    if (end == std::string::npos) return "";
    return json.substr(pos, end - pos);
}

inline int jsonGetInt(const std::string& json, const std::string& key) {
    std::string search = "\"" + key + "\"";
    size_t pos = json.find(search);
    if (pos == std::string::npos) return 0;
    pos = skipWS(json, pos + search.size());
    if (pos >= json.size() || json[pos] != ':') return 0;
    pos = skipWS(json, pos + 1);
    if (pos >= json.size()) return 0;
    try { return std::stoi(json.substr(pos)); } catch(...) { return 0; }
}

// Parse array of objects with fields. Returns vector of maps.
inline std::vector<std::map<std::string,std::string>> jsonGetArray(
    const std::string& json, const std::string& key)
{
    std::vector<std::map<std::string,std::string>> result;
    std::string search = "\"" + key + "\"";
    size_t start = json.find(search);
    if (start == std::string::npos) return result;
    start = skipWS(json, start + search.size());
    if (start >= json.size() || json[start] != ':') return result;
    start = skipWS(json, start + 1);
    if (start >= json.size() || json[start] != '[') return result;
    ++start;
    size_t end = json.find(']', start);
    std::string arr = json.substr(start, end - start);

    // Split by },{
    size_t pos = 0;
    while (pos < arr.size()) {
        size_t obj_start = arr.find('{', pos);
        if (obj_start == std::string::npos) break;
        size_t obj_end = arr.find('}', obj_start);
        if (obj_end == std::string::npos) break;
        std::string obj = arr.substr(obj_start+1, obj_end-obj_start-1);

        std::map<std::string,std::string> fields;
        // Parse key:value pairs
        size_t p = 0;
        while (p < obj.size()) {
            size_t ks = obj.find('"', p);
            if (ks == std::string::npos) break;
            size_t ke = obj.find('"', ks+1);
            std::string k = obj.substr(ks+1, ke-ks-1);
            size_t vs = ke+2; // skip ":"
            std::string v;
            if (vs < obj.size() && obj[vs] == '"') {
                size_t ve = obj.find('"', vs+1);
                v = obj.substr(vs+1, ve-vs-1);
                p = ve+1;
            } else {
                size_t ve = obj.find_first_of(",}", vs);
                if (ve == std::string::npos) ve = obj.size();
                v = obj.substr(vs, ve-vs);
                p = ve+1;
            }
            fields[k] = v;
        }
        result.push_back(fields);
        pos = obj_end+1;
    }
    return result;
}

// ─── I/O ─────────────────────────────────────────────────────────────────────
inline GameState read_state() {
    std::string line;
    std::getline(std::cin, line);
    GameState gs;
    gs.turn      = jsonGetInt(line, "turn");
    gs.max_turns = jsonGetInt(line, "max_turns");
    gs.my_type   = parseType(jsonGetStr(line, "my_type"));

    for (auto& f : jsonGetArray(line, "my_pieces")) {
        MyPiece p;
        p.id  = std::stoi(f.count("id")  ? f.at("id")  : "0");
        p.row = std::stoi(f.count("row") ? f.at("row") : "0");
        p.col = std::stoi(f.count("col") ? f.at("col") : "0");
        gs.my_pieces.push_back(p);
    }
    for (auto& f : jsonGetArray(line, "enemy_pieces")) {
        EnemyPiece ep;
        ep.row  = std::stoi(f.count("row")  ? f.at("row")  : "0");
        ep.col  = std::stoi(f.count("col")  ? f.at("col")  : "0");
        ep.type = parseType(f.count("type") ? f.at("type") : "");
        gs.enemy_pieces.push_back(ep);
    }
    return gs;
}

inline void write_actions(const std::vector<Action>& actions) {
    std::string out = "{\"actions\":[";
    for (size_t i = 0; i < actions.size(); i++) {
        if (i > 0) out += ",";
        out += "{\"piece_id\":" + std::to_string(actions[i].piece_id)
             + ",\"action\":\"" + actions[i].action + "\""
             + ",\"row\":"      + std::to_string(actions[i].row)
             + ",\"col\":"      + std::to_string(actions[i].col) + "}";
    }
    out += "]}";
    std::cout << out << "\n";
    std::cout.flush();
}
