const TIER_COLORS = {
  'Funded': '#f5a623',
  'Series A': '#aaaaaa',
  'Pre-seed': '#8b5c2a',
  'Bootstrapped': '#00c805',
  'pending': '#3d3a36',
};

async function fetchLeaderboard() {
  try {
    const res = await fetch('/api/leaderboard');
    const data = await res.json();
    renderLeaderboard(data.leaderboard || []);
  } catch (e) {
    const el = document.getElementById('leaderboard-body');
    if (el) el.innerHTML = '<p class="error" style="color:#c0392b;font-family:\'JetBrains Mono\',monospace;font-size:13px;padding:24px 0;">Failed to load leaderboard. Please try again later.</p>';
  }
}

function renderLeaderboard(entries) {
  const el = document.getElementById('leaderboard-body');
  if (!el) return;

  if (!entries.length) {
    el.innerHTML = '<p style="color:#6b6560;font-family:\'JetBrains Mono\',monospace;font-size:13px;padding:24px 0;">No shipped projects yet. Be the first.</p>';
    return;
  }

  el.innerHTML = entries.map(e => {
    const color = TIER_COLORS[e.tier] || '#6b6560';
    const rank = e.rank <= 3 ? ['🥇','🥈','🥉'][e.rank - 1] : `#${e.rank}`;
    return `
      <div class="lb-row" style="display:flex;align-items:center;gap:16px;padding:16px 0;border-bottom:1px solid #2a2825;">
        <div style="font-family:'JetBrains Mono',monospace;font-size:14px;color:#6b6560;min-width:36px;">${rank}</div>
        <div style="flex:1;min-width:0;">
          <div style="font-family:'Alfa Slab One',serif;font-size:17px;color:#f0ede8;margin-bottom:2px;">${e.project_name}</div>
          <div style="font-family:'JetBrains Mono',monospace;font-size:11px;color:#6b6560;">by ${e.builder_name}</div>
        </div>
        <div style="display:flex;gap:10px;font-family:'JetBrains Mono',monospace;font-size:11px;">
          ${e.live_url ? `<a href="${e.live_url}" target="_blank" style="color:#f5a623;text-decoration:none;">Live →</a>` : ''}
          ${e.github_url ? `<a href="${e.github_url}" target="_blank" style="color:#6b6560;text-decoration:none;">GitHub</a>` : ''}
        </div>
        <div style="text-align:right;min-width:80px;">
          <div style="font-family:'JetBrains Mono',monospace;font-size:20px;font-weight:700;color:#f0ede8;">${e.score}</div>
          <div style="font-family:'JetBrains Mono',monospace;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.1em;color:${color};">${e.tier}</div>
        </div>
      </div>
    `;
  }).join('');
}

async function submitProject(e) {
  e.preventDefault();
  const form = document.getElementById('submit-form');
  const btn = document.getElementById('submit-btn');
  const msg = document.getElementById('submit-msg');

  const payload = {
    project_name: form.project_name.value.trim(),
    builder_name: form.builder_name.value.trim(),
    live_url: form.live_url.value.trim(),
    github_url: form.github_url.value.trim(),
    pitch_url: form.pitch_url.value.trim(),
  };

  btn.disabled = true;
  btn.textContent = 'submitting...';
  msg.textContent = '';

  try {
    const res = await fetch('/api/submit', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (res.ok) {
      msg.style.color = '#00c805';
      msg.textContent = 'Submitted! We\'ll review it soon.';
      form.reset();
    } else {
      msg.style.color = '#c0392b';
      msg.textContent = data.error || 'Submission failed.';
    }
  } catch (err) {
    msg.style.color = '#c0392b';
    msg.textContent = 'Network error. Please try again.';
  } finally {
    btn.disabled = false;
    btn.textContent = 'ship it';
  }
}

document.addEventListener('DOMContentLoaded', () => {
  fetchLeaderboard();
  const form = document.getElementById('submit-form');
  if (form) form.addEventListener('submit', submitProject);
});
