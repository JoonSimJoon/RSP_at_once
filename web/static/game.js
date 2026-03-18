// =====================================================================
// game.js — Canvas renderer + human play API client
// =====================================================================

let gridCells = [];
let cellMap = new Map();

let gameId = null;
let gameState = null;
let selectedPieceId = null;
let pendingActions = {};   // at most 1 entry
let moveTargets = new Set();   // distance-2 → MOVE
let cloneTargets = new Set();  // distance-1 → CLONE
let humanTypes = new Set(['SCISSORS']);

const canvas = document.getElementById('game-canvas');
const ctx = canvas.getContext('2d');

const COLORS = {
  bg: '#F0EBDC', cell_up: '#D7D2C3', cell_down: '#C3BEB3',
  cell_border: '#A09B8C', highlight_move: '#8CB4FF', highlight_clone: '#78DC8C',
  selected_border: '#FFDC00', action_border: '#FFA000',
  SCISSORS: '#D23737', ROCK: '#5A5A5A', PAPER: '#3778D2',
};
const SYMBOLS = { SCISSORS: '\u2702', ROCK: '\u270A', PAPER: '\u270B' };
const KO = { SCISSORS: '\uAC00\uC704', ROCK: '\uBC14\uC704', PAPER: '\uBCF4' };

// =====================================================================
// Geometry helpers
// =====================================================================

function pointInTriangle(px, py, verts) {
  const [ax, ay] = verts[0], [bx, by] = verts[1], [cx, cy] = verts[2];
  const sign = (p1x, p1y, p2x, p2y, p3x, p3y) =>
    (p1x - p3x) * (p2y - p3y) - (p2x - p3x) * (p1y - p3y);
  const d1 = sign(px, py, ax, ay, bx, by);
  const d2 = sign(px, py, bx, by, cx, cy);
  const d3 = sign(px, py, cx, cy, ax, ay);
  const hasNeg = (d1 < 0) || (d2 < 0) || (d3 < 0);
  const hasPos = (d1 > 0) || (d2 > 0) || (d3 > 0);
  return !(hasNeg && hasPos);
}

function centroid(verts) {
  const cx = (verts[0][0] + verts[1][0] + verts[2][0]) / 3;
  const cy = (verts[0][1] + verts[1][1] + verts[2][1]) / 3;
  return [cx, cy];
}

function getNeighbors(r, c) {
  if (c % 2 === 0) {
    return [[r, c - 1], [r, c + 1], [r + 1, c + 1]];
  } else {
    return [[r, c - 1], [r, c + 1], [r - 1, c - 1]];
  }
}

function isValid(r, c) {
  return r >= 0 && r < 11 && c >= 0 && c <= 2 * r;
}

function bfsReachable(r, c, radius) {
  const visited = new Set([`${r},${c}`]);
  const queue = [[r, c, 0]];
  while (queue.length) {
    const [cr, cc, d] = queue.shift();
    if (d >= radius) continue;
    for (const [nr, nc] of getNeighbors(cr, cc)) {
      const key = `${nr},${nc}`;
      if (!visited.has(key) && isValid(nr, nc)) {
        visited.add(key);
        queue.push([nr, nc, d + 1]);
      }
    }
  }
  visited.delete(`${r},${c}`);
  return visited;
}

function computeTargets(piece) {
  const r1 = bfsReachable(piece.row, piece.col, 1);
  const r2 = bfsReachable(piece.row, piece.col, 2);
  cloneTargets = r1;                          // distance-1 = CLONE
  moveTargets = new Set([...r2].filter(k => !r1.has(k)));  // distance-2 only = MOVE
}

// =====================================================================
// Hit testing
// =====================================================================

function hitTestCell(px, py) {
  for (const cell of gridCells) {
    if (pointInTriangle(px, py, cell.vertices)) {
      return cell;
    }
  }
  return null;
}

// =====================================================================
// Drawing
// =====================================================================

function drawTriangleOnCtx(targetCtx, vertices, fillColor, strokeColor, lineWidth) {
  targetCtx.beginPath();
  targetCtx.moveTo(vertices[0][0], vertices[0][1]);
  targetCtx.lineTo(vertices[1][0], vertices[1][1]);
  targetCtx.lineTo(vertices[2][0], vertices[2][1]);
  targetCtx.closePath();
  targetCtx.fillStyle = fillColor;
  targetCtx.fill();
  targetCtx.strokeStyle = strokeColor || COLORS.cell_border;
  targetCtx.lineWidth = lineWidth || 1;
  targetCtx.stroke();
}

function drawPieceOnCtx(targetCtx, cx, cy, owner, symbol, isSelected, hasPending, count) {
  const radius = 13;
  // Outer rings
  if (isSelected) {
    targetCtx.beginPath();
    targetCtx.arc(cx, cy, radius + 3, 0, Math.PI * 2);
    targetCtx.strokeStyle = COLORS.selected_border;
    targetCtx.lineWidth = 3;
    targetCtx.stroke();
  }
  if (hasPending) {
    targetCtx.beginPath();
    targetCtx.arc(cx, cy, radius + 6, 0, Math.PI * 2);
    targetCtx.strokeStyle = COLORS.action_border;
    targetCtx.lineWidth = 2;
    targetCtx.stroke();
  }
  // Circle
  targetCtx.beginPath();
  targetCtx.arc(cx, cy, radius, 0, Math.PI * 2);
  targetCtx.fillStyle = COLORS[owner] || '#888';
  targetCtx.fill();
  targetCtx.strokeStyle = '#222';
  targetCtx.lineWidth = 1;
  targetCtx.stroke();
  // Symbol
  targetCtx.fillStyle = '#FFF';
  targetCtx.font = '14px sans-serif';
  targetCtx.textAlign = 'center';
  targetCtx.textBaseline = 'middle';
  targetCtx.fillText(symbol, cx, cy);
  // Count badge
  if (count > 1) {
    targetCtx.fillStyle = '#FF4444';
    targetCtx.beginPath();
    targetCtx.arc(cx + 10, cy - 10, 7, 0, Math.PI * 2);
    targetCtx.fill();
    targetCtx.fillStyle = '#FFF';
    targetCtx.font = 'bold 9px sans-serif';
    targetCtx.textAlign = 'center';
    targetCtx.textBaseline = 'middle';
    targetCtx.fillText(String(count), cx + 10, cy - 10);
  }
}

function renderGrid(targetCtx, targetCanvas, highlights) {
  targetCtx.fillStyle = COLORS.bg;
  targetCtx.fillRect(0, 0, targetCanvas.width, targetCanvas.height);

  for (const cell of gridCells) {
    const key = `${cell.r},${cell.c}`;
    let fillColor;
    if (highlights && highlights.move && highlights.move.has(key)) {
      fillColor = COLORS.highlight_move;
    } else if (highlights && highlights.clone && highlights.clone.has(key)) {
      fillColor = COLORS.highlight_clone;
    } else {
      fillColor = cell.upward ? COLORS.cell_up : COLORS.cell_down;
    }
    drawTriangleOnCtx(targetCtx, cell.vertices, fillColor, COLORS.cell_border, 1);
  }
}

function renderPieces(targetCtx, pieces, opts) {
  if (!pieces) return;

  // Group pieces by cell
  const cellPieces = new Map();
  for (const p of pieces) {
    if (p.alive === false) continue;
    const key = `${p.row},${p.col}`;
    if (!cellPieces.has(key)) cellPieces.set(key, []);
    cellPieces.get(key).push(p);
  }

  for (const [key, pcs] of cellPieces.entries()) {
    const cell = cellMap.get(key);
    if (!cell) continue;
    const [cx, cy] = centroid(cell.vertices);

    if (pcs.length === 1) {
      const p = pcs[0];
      const isSelected = opts && opts.selectedId === p.id;
      const hasPending = opts && opts.pendingIds && opts.pendingIds.has(p.id);
      drawPieceOnCtx(targetCtx, cx, cy, p.owner, SYMBOLS[p.owner] || '?', isSelected, hasPending, 1);
    } else {
      // Multiple pieces on same cell — group by owner
      const byOwner = new Map();
      for (const p of pcs) {
        if (!byOwner.has(p.owner)) byOwner.set(p.owner, []);
        byOwner.get(p.owner).push(p);
      }
      const owners = Array.from(byOwner.keys());
      const spacing = 14;
      const startX = cx - ((owners.length - 1) * spacing) / 2;
      let idx = 0;
      for (const owner of owners) {
        const group = byOwner.get(owner);
        const ox = startX + idx * spacing;
        const anySelected = opts && group.some(p => opts.selectedId === p.id);
        const anyPending = opts && opts.pendingIds && group.some(p => opts.pendingIds.has(p.id));
        drawPieceOnCtx(targetCtx, ox, cy, owner, SYMBOLS[owner] || '?', anySelected, anyPending, group.length);
        idx++;
      }
    }
  }

  // Draw pending action arrows
  if (opts && opts.pending) {
    for (const [pieceId, action] of Object.entries(opts.pending)) {
      const piece = pieces.find(p => p.id === parseInt(pieceId));
      if (!piece) continue;
      const srcCell = cellMap.get(`${piece.row},${piece.col}`);
      const dstCell = cellMap.get(`${action.row},${action.col}`);
      if (!srcCell || !dstCell) continue;
      const [sx, sy] = centroid(srcCell.vertices);
      const [dx, dy] = centroid(dstCell.vertices);
      // Draw arrow
      targetCtx.strokeStyle = action.action === 'MOVE' ? COLORS.highlight_move : COLORS.highlight_clone;
      targetCtx.lineWidth = 2;
      targetCtx.setLineDash([4, 4]);
      targetCtx.beginPath();
      targetCtx.moveTo(sx, sy);
      targetCtx.lineTo(dx, dy);
      targetCtx.stroke();
      targetCtx.setLineDash([]);
      // Arrowhead
      const angle = Math.atan2(dy - sy, dx - sx);
      const headLen = 8;
      targetCtx.beginPath();
      targetCtx.moveTo(dx, dy);
      targetCtx.lineTo(dx - headLen * Math.cos(angle - 0.4), dy - headLen * Math.sin(angle - 0.4));
      targetCtx.lineTo(dx - headLen * Math.cos(angle + 0.4), dy - headLen * Math.sin(angle + 0.4));
      targetCtx.closePath();
      targetCtx.fillStyle = action.action === 'MOVE' ? COLORS.highlight_move : COLORS.highlight_clone;
      targetCtx.fill();
    }
  }
}

function renderKills(targetCtx, kills) {
  if (!kills || kills.length === 0) return;
  for (const kill of kills) {
    const cell = cellMap.get(`${kill.row},${kill.col}`);
    if (!cell) continue;
    const [cx, cy] = centroid(cell.vertices);
    targetCtx.beginPath();
    targetCtx.arc(cx, cy, 18, 0, Math.PI * 2);
    targetCtx.strokeStyle = '#FF0000';
    targetCtx.lineWidth = 3;
    targetCtx.stroke();
    // X mark
    targetCtx.strokeStyle = '#FF0000';
    targetCtx.lineWidth = 2;
    targetCtx.beginPath();
    targetCtx.moveTo(cx - 8, cy - 8);
    targetCtx.lineTo(cx + 8, cy + 8);
    targetCtx.moveTo(cx + 8, cy - 8);
    targetCtx.lineTo(cx - 8, cy + 8);
    targetCtx.stroke();
  }
}

function renderState(state) {
  if (!state) return;

  // Always show both: blue=MOVE(2칸), green=CLONE(1칸)
  const highlights = {
    move: moveTargets,
    clone: cloneTargets,
  };

  renderGrid(ctx, canvas, highlights);

  const pendingIds = new Set(Object.keys(pendingActions).map(Number));
  renderPieces(ctx, state.pieces, {
    selectedId: selectedPieceId,
    pendingIds: pendingIds,
    pending: pendingActions,
  });

  if (state.kills) {
    renderKills(ctx, state.kills);
  }

  updateInfoPanel(state);
}

// =====================================================================
// Info panel
// =====================================================================

function updateInfoPanel(state) {
  if (!state) return;

  document.getElementById('turn-display').textContent = `Turn ${state.turn || 0}`;

  const scoresDiv = document.getElementById('scores');
  scoresDiv.innerHTML = '';
  const counts = { SCISSORS: 0, ROCK: 0, PAPER: 0 };
  if (state.pieces) {
    for (const p of state.pieces) {
      if (p.alive !== false) {
        counts[p.owner] = (counts[p.owner] || 0) + 1;
      }
    }
  }
  for (const type of ['SCISSORS', 'ROCK', 'PAPER']) {
    const div = document.createElement('div');
    div.innerHTML = `<span style="color:${COLORS[type]}">${SYMBOLS[type]} ${KO[type]}</span>: ${counts[type]}개`;
    scoresDiv.appendChild(div);
  }

  const phaseDiv = document.getElementById('phase-display');
  const actionBtns = document.getElementById('action-buttons');
  const gameOverPanel = document.getElementById('game-over-panel');

  if (state.winner) {
    phaseDiv.textContent = '게임 종료';
    actionBtns.style.display = 'none';
    gameOverPanel.style.display = 'block';
    const winnerDisplay = document.getElementById('winner-display');
    if (state.winner === 'DRAW') {
      winnerDisplay.textContent = '무승부!';
    } else {
      winnerDisplay.innerHTML = `${SYMBOLS[state.winner]} ${KO[state.winner]} 승리!`;
      winnerDisplay.style.color = COLORS[state.winner] || '#FFDC32';
    }
  } else {
    gameOverPanel.style.display = 'none';
    const currentPhase = state.current_phase || state.phase || '';
    const currentType = currentPhase.replace('INPUT_', '');
    const isHumanPhase = humanTypes.has(currentType);
    phaseDiv.textContent = currentPhase ? `현재 페이즈: ${KO[currentType] || currentPhase}` : '';

    if (isHumanPhase) {
      actionBtns.style.display = 'block';
      const assigned = Object.keys(pendingActions).length;
      document.getElementById('progress-display').textContent =
        assigned > 0 ? '✔ 액션 배치됨 (Enter로 확인)' : '기물 클릭 → 목표 클릭 (파란=이동 초록=복제)';
    } else {
      actionBtns.style.display = 'none';
    }
  }
}

// =====================================================================
// Canvas interaction
// =====================================================================

function handleCanvasClick(event) {
  if (!gameState || gameState.winner) return;

  const rect = canvas.getBoundingClientRect();
  const scaleX = canvas.width / rect.width;
  const scaleY = canvas.height / rect.height;
  const px = (event.clientX - rect.left) * scaleX;
  const py = (event.clientY - rect.top) * scaleY;

  const cell = hitTestCell(px, py);
  if (!cell) return;

  const currentPhase = gameState.current_phase || gameState.phase || '';
  const currentType = currentPhase.replace('INPUT_', '');
  if (!humanTypes.has(currentType)) return;

  const clickKey = `${cell.r},${cell.c}`;

  // Check if clicked cell has a selectable piece
  const myPieces = (gameState.pieces || []).filter(
    p => p.alive !== false && p.owner === currentType && p.row === cell.r && p.col === cell.c
  );

  if (myPieces.length > 0) {
    // Select this piece
    const piece = myPieces[0];
    selectedPieceId = piece.id;
    computeTargets(piece);
    renderState(gameState);
    return;
  }

  // If we have a selected piece, try to assign action
  if (selectedPieceId !== null) {
    let actionType = null;
    if (moveTargets.has(clickKey)) actionType = 'MOVE';
    else if (cloneTargets.has(clickKey)) actionType = 'CLONE';

    if (actionType) {
      // 1기물 1액션: 새 액션이 이전 것을 교체
      pendingActions = {};
      pendingActions[selectedPieceId] = {
        piece_id: selectedPieceId,
        action: actionType,
        row: cell.r,
        col: cell.c,
      };
      selectedPieceId = null;
      moveTargets = new Set();
      cloneTargets = new Set();
      renderState(gameState);
    }
  }
}

// =====================================================================
// Game API
// =====================================================================

async function fetchGrid() {
  try {
    const res = await fetch('/api/grid');
    const data = await res.json();
    gridCells = data.cells;
    cellMap = new Map();
    for (const cell of gridCells) {
      cellMap.set(`${cell.r},${cell.c}`, cell);
    }
  } catch (e) {
    console.error('Failed to fetch grid:', e);
  }
}

async function startGame() {
  try {
    const body = { human_types: Array.from(humanTypes) };
    const res = await fetch('/api/game/new', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    gameId = data.game_id;
    gameState = data.state;
    selectedPieceId = null;
    pendingActions = {};
    moveTargets = new Set();
    cloneTargets = new Set();
    document.getElementById('start-overlay').classList.add('hidden');
    document.getElementById('game-over-panel').style.display = 'none';
    renderState(gameState);
  } catch (e) {
    console.error('Failed to start game:', e);
  }
}

async function confirmTurn() {
  if (!gameId || !gameState) return;

  const actions = Object.values(pendingActions);

  try {
    const res = await fetch(`/api/game/${gameId}/action`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ actions }),
    });
    const data = await res.json();
    if (data.error) {
      console.error('Action error:', data.error);
      return;
    }
    gameState = data;
    selectedPieceId = null;
    pendingActions = {};
    moveTargets = new Set();
    cloneTargets = new Set();
    renderState(gameState);
  } catch (e) {
    console.error('Failed to confirm turn:', e);
  }
}

async function fetchState() {
  if (!gameId) return;
  try {
    const res = await fetch(`/api/game/${gameId}/state`);
    const data = await res.json();
    gameState = data;
    renderState(gameState);
  } catch (e) {
    console.error('Failed to fetch state:', e);
  }
}

// =====================================================================
// Start overlay — type toggles
// =====================================================================

function renderTypeToggles() {
  const container = document.getElementById('type-toggles');
  container.innerHTML = '';
  for (const type of ['SCISSORS', 'ROCK', 'PAPER']) {
    const div = document.createElement('div');
    div.className = 'type-toggle' + (humanTypes.has(type) ? ' selected' : '');
    div.innerHTML = `
      <span style="color:${COLORS[type]}">${SYMBOLS[type]} ${KO[type]}</span>
      <span>${humanTypes.has(type) ? '사람' : 'AI'}</span>
    `;
    div.addEventListener('click', () => {
      if (humanTypes.has(type)) {
        humanTypes.delete(type);
      } else {
        humanTypes.add(type);
      }
      renderTypeToggles();
    });
    container.appendChild(div);
  }
}

// =====================================================================
// Tab switching
// =====================================================================

function setupTabs() {
  const tabBtns = document.querySelectorAll('.tab-btn');
  tabBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      tabBtns.forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      document.querySelectorAll('.tab-content').forEach(tc => tc.classList.remove('active'));
      const tabId = 'tab-' + btn.dataset.tab;
      document.getElementById(tabId).classList.add('active');
    });
  });
}

// =====================================================================
// Keyboard shortcuts
// =====================================================================

function setupKeyboard() {
  document.addEventListener('keydown', (e) => {
    // Don't capture keys when typing in textarea or input
    if (e.target.tagName === 'TEXTAREA' || e.target.tagName === 'INPUT') return;

    if (e.key === 'Enter') {
      confirmTurn();
    } else if (e.key === 'Escape') {
      selectedPieceId = null;
      moveTargets = new Set();
      cloneTargets = new Set();
      if (gameState) renderState(gameState);
    }
  });
}

// =====================================================================
// Button handlers
// =====================================================================

function setupButtons() {
  document.getElementById('btn-confirm').addEventListener('click', () => {
    confirmTurn();
  });

  document.getElementById('btn-start-game').addEventListener('click', () => {
    startGame();
  });

  document.getElementById('btn-restart').addEventListener('click', () => {
    document.getElementById('start-overlay').classList.remove('hidden');
    renderTypeToggles();
  });
}

// =====================================================================
// Init
// =====================================================================

async function init() {
  await fetchGrid();
  setupTabs();
  setupKeyboard();
  setupButtons();
  renderTypeToggles();

  canvas.addEventListener('click', handleCanvasClick);

  // Render empty grid
  if (gridCells.length > 0) {
    renderGrid(ctx, canvas, null);
  }
}

// Make some functions available globally for submit.js
window.gridCells = null;
window.cellMap = null;
window.renderGrid = renderGrid;
window.renderPieces = renderPieces;
window.COLORS = COLORS;
window.SYMBOLS = SYMBOLS;
window.KO = KO;

Object.defineProperty(window, 'gridCells', { get: () => gridCells });
Object.defineProperty(window, 'cellMap', { get: () => cellMap });

init();
