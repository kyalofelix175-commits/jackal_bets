const API_BASE = '/api';
let currentUser = null;
let selectedBets = {}; 

// DOM Selectors
const authPage = document.getElementById('auth-page');
const mainApp = document.getElementById('main-app');
const authForm = document.getElementById('auth-form');
const authTitle = document.getElementById('auth-title');
const phoneInput = document.getElementById('phone');
const passwordInput = document.getElementById('password');
const authSubmitBtn = document.getElementById('auth-submit-btn');
const toggleAuthBtn = document.getElementById('toggle-auth-btn');
const toggleText = document.getElementById('toggle-text');
const dashPhone = document.getElementById('dash-phone');
const dashBalance = document.getElementById('dash-balance');
const totalOddsText = document.getElementById('total-odds');
const matchesList = document.getElementById('matches-list');
const navSlipCount = document.getElementById('nav-slip-count');

// Modals
const depositModal = document.getElementById('deposit-modal');
const withdrawModal = document.getElementById('withdraw-modal');
const betModal = document.getElementById('bet-modal');
const profileModal = document.getElementById('profile-modal');
const closeModalBtns = document.querySelectorAll('.close-modal');

let isSignUpMode = true;

// Auth Toggle Layout
toggleAuthBtn.addEventListener('click', () => {
    isSignUpMode = !isSignUpMode;
    authTitle.textContent = isSignUpMode ? "Sign Up" : "Sign In";
    authSubmitBtn.textContent = isSignUpMode ? "Create Account" : "Sign In";
    toggleText.textContent = isSignUpMode ? "Already have an account?" : "Don't have an account?";
    toggleAuthBtn.textContent = isSignUpMode ? "Sign In" : "Sign Up";
    authForm.reset();
});

// Secure Server Authorization Hooks
authForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const phone = phoneInput.value.trim();
    const password = passwordInput.value;

    if(password.length !== 5) {
        alert("⚠️ Password must be exactly 5 characters!");
        return;
    }

    const endpoint = isSignUpMode ? '/signup' : '/signin';
    try {
        const res = await fetch(`${API_BASE}${endpoint}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ phone, password })
        });
        const data = await res.json();
        
        if (!res.ok) throw new Error(data.error);

        if (isSignUpMode) {
            alert("✅ Account created.Sign in now.");
            toggleAuthBtn.click();
        } else {
            currentUser = data.user;
            authPage.classList.add('hidden');
            mainApp.classList.remove('hidden');
            updateDashboard();
            fetchRealMatches();
            try {
                fetch('/api/settle', { method: 'POST' });
            } catch (e) {
                console.log("Settlement check skipped.");
            }
        }
    } catch (err) {
        alert(`❌ ${err.message}`);
    }
});

// API Fetch Match Implementation
async function fetchRealMatches() {
    matchesList.innerHTML = '<div style="text-align:center; padding:30px; color:var(--text-secondary);">🔄 Loading matches...</div>';
    try {
        const res = await fetch(`${API_BASE}/matches`);
        const data = await res.json();
        if(!res.ok) throw new Error();
        processRealMatches(data);
    } catch {
        matchesList.innerHTML = '<div style="text-align:center; color:var(--danger-color); padding:20px;">❌ Error processing live sports data.</div>';
    }
}

function processRealMatches(apiMatches) {
    matchesList.innerHTML = '';
    let matchPool = [];

    apiMatches.slice(0, 50).forEach((game, index) => {
        const kickoffTime = new Date(game.commence_time);
        const formattedDate = kickoffTime.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' }) + 
                              ` • ${String(kickoffTime.getHours()).padStart(2, '0')}:${String(kickoffTime.getMinutes()).padStart(2, '0')}`;

        let odd1 = "2.00", oddX = "3.40", odd2 = "2.10"; 
        if (game.bookmakers && game.bookmakers.length > 0) {
            const marketData = game.bookmakers[0].markets.find(m => m.key === 'h2h');
            if (marketData && marketData.outcomes) {
                const home = marketData.outcomes.find(o => o.name === game.home_team);
                const away = marketData.outcomes.find(o => o.name === game.away_team);
                const draw = marketData.outcomes.find(o => o.name.toLowerCase() === 'draw');
                if (home) odd1 = home.price.toFixed(2);
                if (away) odd2 = away.price.toFixed(2);
                if (draw) oddX = draw.price.toFixed(2);
            }
        }

        matchPool.push({
            id: `real-${index}`,
            match: `${game.home_team} vs ${game.away_team}`,
            metaText: `${formattedDate}`,
            badgeHTML: kickoffTime < new Date() ? `<span class="badge-live">Live</span>` : '',
            odds: { '1': odd1, 'X': oddX, '2': odd2 }
        });
    });

    matchPool.forEach(game => {
        const matchBox = document.createElement('div');
        matchBox.className = 'match-box';
        matchBox.innerHTML = `
            <div class="match-teams">
                <div>${game.match} ${game.badgeHTML}</div>
                <span class="match-meta">${game.metaText}</span>
            </div>
            <div class="match-odds-container">
                <button class="odds-btn" data-game-id="${game.id}" data-choice="1">${game.odds['1']}</button>
                <button class="odds-btn" data-game-id="${game.id}" data-choice="X">${game.odds['X']}</button>
                <button class="odds-btn" data-game-id="${game.id}" data-choice="2">${game.odds['2']}</button>
            </div>
        `;
        matchesList.appendChild(matchBox);
    });

    setupOddsClickHandlers(matchPool);
}

function setupOddsClickHandlers(games) {
    document.querySelectorAll('.odds-btn').forEach(btn => {
        btn.onclick = () => {
            const gameId = btn.getAttribute('data-game-id');
            const choice = btn.getAttribute('data-choice');
            const oddsVal = parseFloat(btn.textContent);
            const matchName = games.find(g => g.id === gameId).match;
            const siblingButtons = btn.parentElement.querySelectorAll('.odds-btn');

            if (btn.classList.contains('selected')) {
                btn.classList.remove('selected');
                delete selectedBets[gameId];
            } else {
                siblingButtons.forEach(sb => sb.classList.remove('selected'));
                btn.classList.add('selected');
                selectedBets[gameId] = { choice, odds: oddsVal, match: matchName };
            }
            updateTotalOdds();
        };
    });
}

function updateTotalOdds() {
    let totalOdds = 1.00;
    const items = Object.values(selectedBets);
    items.forEach(bet => { totalOdds *= bet.odds; });
    const compiledOdds = items.length > 0 ? totalOdds.toFixed(2) : "1.00";
    
    totalOddsText.textContent = compiledOdds;
    document.getElementById('bet-slip-odds').textContent = compiledOdds;
    document.getElementById('selected-bets-count').textContent = items.length;
    navSlipCount.textContent = items.length;
    updatePotentialWin();
}

function updateDashboard() {
    if (!currentUser) return;
    dashPhone.textContent = `Phone: ${currentUser.phone}`;
    dashBalance.textContent = `Balance: Kes ${currentUser.balance.toFixed(2)}`;
}

// Fetch Histories from Backend SQLite 
async function loadHistoryLogs() {
    try {
        const res = await fetch(`${API_BASE}/history/${currentUser.phone}`);
        const data = await res.json();
        
        const betList = document.getElementById('bet-history-list');
        const txList = document.getElementById('transaction-history-list');

        betList.innerHTML = data.bets.length === 0 ? '<li>No open bets yet.</li>' : '';
        data.bets.forEach(b => {
            const li = document.createElement('li');
            li.innerHTML = `Match: <strong>${b.match_summary} (${b.predicted_choice})</strong><br>Stake: Kes ${b.stake} | Odds: ${b.odds} | Status: <strong style="color:${b.status === 'WON' ? '#00e676' : '#ff3b30'}">${b.status}</strong>`;
            betList.appendChild(li);
        });

        txList.innerHTML = data.transactions.length === 0 ? '<li>No entries found.</li>' : '';
        data.transactions.forEach(t => {
            const li = document.createElement('li');
            li.innerHTML = `${t.type}: <strong>Kes ${t.amount}</strong> <small style="float:right">${t.date}</small>`;
            txList.appendChild(li);
        });
    } catch (e) { console.error(e); }
}

// Financial transactions channeled securely to Server
document.getElementById('confirm-deposit').onclick = async () => {
    const amount = parseFloat(document.getElementById('deposit-amount').value);
    const res = await fetch(`${API_BASE}/deposit`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ phone: currentUser.phone, amount })
    });
    const data = await res.json();
    if(res.ok) {
        currentUser.balance = data.balance;
        updateDashboard();
        closeAllModals();
        alert('Deposit processed successfully.');
    } else alert(data.error);
};

document.getElementById("loginForm").addEventListener("submit", async function (e) {
  e.preventDefault();

  const username = document.getElementById("username").value;
  const password = document.getElementById("password").value;

  const res = await fetch("https://your-backend.onrender.com/login", {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({ username, password })
  });

  const data = await res.json();
  console.log(data);
});

document.getElementById('confirm-withdraw').onclick = async () => {
    const amount = parseFloat(document.getElementById('withdraw-amount').value);
    const res = await fetch(`${API_BASE}/withdraw`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ phone: currentUser.phone, amount })
    });
    const data = await res.json();
    if(res.ok) {
        currentUser.balance = data.balance;
        updateDashboard();
        closeAllModals();
        alert('Withdrawal completed safely.');
    } else alert(data.error);
};

const stakeInput = document.getElementById('bet-stake');
function updatePotentialWin() {
    const stake = parseFloat(stakeInput.value) || 0;
    const totalOdds = parseFloat(totalOddsText.textContent) || 1.00;
    document.getElementById('potential-win').textContent = `Kes ${(stake * totalOdds).toFixed(2)}`;
}
stakeInput.oninput = updatePotentialWin;

document.getElementById('place-bet-btn').onclick = async () => {
    const stake = parseFloat(stakeInput.value);
    const betItems = Object.values(selectedBets);

    if (betItems.length === 0) return alert("Your betslip is empty!");
    const activeBet = betItems[0]; // Simple single slip submission

    const res = await fetch(`${API_BASE}/bet`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            phone: currentUser.phone,
            matchSummary: activeBet.match,
            predictedChoice: activeBet.choice,
            odds: activeBet.odds,
            stake: stake
        })
    });
    const data = await res.json();
    if(res.ok) {
        currentUser.balance = data.balance;
        selectedBets = {};
        document.querySelectorAll('.odds-btn').forEach(b => b.classList.remove('selected'));
        updateTotalOdds();
        updateDashboard();
        closeAllModals();
        alert("🎟️ Bet placed successfully!");
    } else alert(data.error);
};

// Modal routing configurations
function closeAllModals() {
    [depositModal, withdrawModal, betModal, profileModal].forEach(m => m.classList.add('hidden'));
}
closeModalBtns.forEach(btn => btn.onclick = closeAllModals);
document.getElementById('nav-home').onclick = closeAllModals;
document.getElementById('nav-deposit').onclick = () => { closeAllModals(); depositModal.classList.remove('hidden'); };
document.getElementById('nav-withdraw').onclick = () => { closeAllModals(); withdrawModal.classList.remove('hidden'); };
document.getElementById('nav-bet').onclick = () => { closeAllModals(); betModal.classList.remove('hidden'); };
document.getElementById('profile-btn').onclick = () => { loadHistoryLogs(); profileModal.classList.remove('hidden'); };
document.getElementById('logout-btn').onclick = () => { location.reload(); };
