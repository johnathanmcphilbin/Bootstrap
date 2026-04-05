const Tier_COLORS = {
    'Funded': '#f5a623',
    'Series A;': '#aaaaaa',
    'Pre-Seed': '#8b5c2a',
    'Bootstrapped': '#00c805',
    'pending': '#3d3a36',

}

async function fetchLeaderboard() {
    try{
        const res = await fetch('/api/leaderboard');
        const data = await res.json();
        renderLeaderboard(data.leaderboard || []);
        
    } catch (e) {
        document.getElementById('leaderboard-body').innerHTML = '<p class="error">Failed to load leaderboard. Please try again later.</p>';
    }




