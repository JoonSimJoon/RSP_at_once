// =====================================================================
// submit.js — Code submission + replay playback
// =====================================================================

let replayData = [];
let replayIndex = 0;
let replayInterval = null;
let replayPlaying = false;

const replayCanvas = document.getElementById('replay-canvas');
const replayCtx = replayCanvas ? replayCanvas.getContext('2d') : null;

// =====================================================================
// Code submission
// =====================================================================

async function submitCode() {
  const btn = document.getElementById('btn-submit-code');
  const codeEditor = document.getElementById('code-editor');
  const code = codeEditor.value.trim();

  if (!code) {
    alert('코드를 입력하세요.');
    return;
  }

  const languageRadio = document.querySelector('input[name="language"]:checked');
  const language = languageRadio ? languageRadio.value : 'cpp';

  // Reset result panels
  hideElement('compile-output');
  hideElement('match-result');
  hideElement('replay-controls');

  btn.disabled = true;
  btn.textContent = '컴파일 중...';

  try {
    const res = await fetch('/api/submit', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code, language }),
    });
    const data = await res.json();

    if (data.error) {
      showCompileError(data.error || '오류', data.detail || data.error);
      btn.disabled = false;
      btn.textContent = '▶ 제출 및 시뮬레이션 실행';
      return;
    }

    if (data.job_id) {
      pollJob(data.job_id);
    } else if (data.result) {
      // Immediate result (no job queue)
      showResult(data.result);
      if (data.replay) {
        loadReplay(data.replay);
      }
      btn.disabled = false;
      btn.textContent = '▶ 제출 및 시뮬레이션 실행';
    }
  } catch (e) {
    showCompileError('네트워크 오류', e.message);
    btn.disabled = false;
    btn.textContent = '▶ 제출 및 시뮬레이션 실행';
  }
}

// =====================================================================
// Job polling
// =====================================================================

function pollJob(jobId) {
  const btn = document.getElementById('btn-submit-code');
  const interval = setInterval(async () => {
    try {
      const res = await fetch(`/api/job/${jobId}`);
      const data = await res.json();

      if (data.status === 'done') {
        clearInterval(interval);
        showResult(data.result);
        if (data.replay) {
          loadReplay(data.replay);
        }
        btn.disabled = false;
        btn.textContent = '▶ 제출 및 시뮬레이션 실행';
      } else if (data.status === 'error') {
        clearInterval(interval);
        showCompileError(data.error_type || '실행 오류', data.detail || '알 수 없는 오류');
        btn.disabled = false;
        btn.textContent = '▶ 제출 및 시뮬레이션 실행';
      } else {
        // Still running
        btn.textContent = '\u23F3 ' + (data.progress || '실행 중...');
      }
    } catch (e) {
      clearInterval(interval);
      showCompileError('폴링 오류', e.message);
      btn.disabled = false;
      btn.textContent = '▶ 제출 및 시뮬레이션 실행';
    }
  }, 1000);
}

// =====================================================================
// Result display
// =====================================================================

function showCompileError(title, message) {
  const el = document.getElementById('compile-output');
  el.style.display = 'block';
  el.textContent = `[${title}]\n${message}`;
}

function showResult(result) {
  const el = document.getElementById('match-result');
  el.style.display = 'block';

  if (!result) {
    el.textContent = '결과 없음';
    return;
  }

  const winner = result.winner;
  const scores = result.scores || {};

  let html = '';
  if (winner === 'DRAW') {
    html += '<div style="font-size:24px;margin-bottom:12px;">무승부!</div>';
  } else if (winner) {
    const sym = window.SYMBOLS[winner] || '';
    const ko = window.KO[winner] || winner;
    const color = window.COLORS[winner] || '#FFF';
    html += `<div style="font-size:24px;margin-bottom:12px;color:${color}">` +
      `${sym} 승자: ${ko} (${winner})</div>`;
  }

  const scoreLines = [];
  for (const type of ['SCISSORS', 'ROCK', 'PAPER']) {
    const count = scores[type] || 0;
    const ko = window.KO[type] || type;
    scoreLines.push(`${ko} ${count}개`);
  }
  html += '<div>점수: ' + scoreLines.join(' | ') + '</div>';

  if (result.turns !== undefined) {
    html += `<div style="margin-top:8px;color:#AAA;">총 ${result.turns}턴</div>`;
  }

  el.innerHTML = html;
}

// =====================================================================
// Replay
// =====================================================================

function loadReplay(replayArray) {
  if (!replayArray || replayArray.length === 0) return;

  replayData = replayArray;
  replayIndex = 0;
  replayPlaying = false;
  if (replayInterval) {
    clearInterval(replayInterval);
    replayInterval = null;
  }

  const controls = document.getElementById('replay-controls');
  controls.style.display = 'flex';

  const slider = document.getElementById('replay-slider');
  slider.max = String(replayData.length - 1);
  slider.value = '0';

  renderReplayTurn(0);
}

function renderReplayTurn(index) {
  if (index < 0 || index >= replayData.length) return;
  replayIndex = index;

  const turnData = replayData[index];
  if (!turnData) return;

  // Update UI
  document.getElementById('replay-turn-display').textContent =
    `Turn ${turnData.turn !== undefined ? turnData.turn : index}`;
  document.getElementById('replay-slider').value = String(index);

  // Render grid
  if (!replayCtx || !replayCanvas) return;

  // Use shared grid data from game.js
  const cells = window.gridCells;
  if (!cells || cells.length === 0) return;

  window.renderGrid(replayCtx, replayCanvas, null);
  window.renderPieces(replayCtx, turnData.pieces, null);
}

function replayPlay() {
  if (replayPlaying) {
    replayPause();
    return;
  }
  replayPlaying = true;
  document.getElementById('rb-play').textContent = '\u23F8';

  const speedSelect = document.getElementById('replay-speed');
  const delay = parseInt(speedSelect.value) || 1000;

  replayInterval = setInterval(() => {
    if (replayIndex >= replayData.length - 1) {
      replayPause();
      return;
    }
    renderReplayTurn(replayIndex + 1);
  }, delay);
}

function replayPause() {
  replayPlaying = false;
  document.getElementById('rb-play').textContent = '\u25B6';
  if (replayInterval) {
    clearInterval(replayInterval);
    replayInterval = null;
  }
}

function replayPrev() {
  replayPause();
  if (replayIndex > 0) {
    renderReplayTurn(replayIndex - 1);
  }
}

function replayNext() {
  replayPause();
  if (replayIndex < replayData.length - 1) {
    renderReplayTurn(replayIndex + 1);
  }
}

// =====================================================================
// Helpers
// =====================================================================

function hideElement(id) {
  const el = document.getElementById(id);
  if (el) el.style.display = 'none';
}

// =====================================================================
// Event listeners
// =====================================================================

function setupSubmitHandlers() {
  const btnSubmit = document.getElementById('btn-submit-code');
  if (btnSubmit) {
    btnSubmit.addEventListener('click', submitCode);
  }

  const rbPrev = document.getElementById('rb-prev');
  if (rbPrev) rbPrev.addEventListener('click', replayPrev);

  const rbPlay = document.getElementById('rb-play');
  if (rbPlay) rbPlay.addEventListener('click', replayPlay);

  const rbNext = document.getElementById('rb-next');
  if (rbNext) rbNext.addEventListener('click', replayNext);

  const slider = document.getElementById('replay-slider');
  if (slider) {
    slider.addEventListener('input', () => {
      replayPause();
      renderReplayTurn(parseInt(slider.value));
    });
  }

  const speedSelect = document.getElementById('replay-speed');
  if (speedSelect) {
    speedSelect.addEventListener('change', () => {
      if (replayPlaying) {
        replayPause();
        replayPlay();
      }
    });
  }
}

setupSubmitHandlers();
