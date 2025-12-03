// ---------------------------------------
// Portfolio WebSocket
// ---------------------------------------
const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
const portfolioWS = new WebSocket(`${protocol}://${window.location.host}/ws/portfolio`);

portfolioWS.onmessage = (event) => {
    const data = JSON.parse(event.data);
    if (data && data.portfolio_equity !== undefined) {
        document.getElementById("portfolio-equity").textContent =
            `Equity: ${data.portfolio_equity.toFixed(2)}`;
        document.getElementById("portfolio-realized").textContent =
            `Realized PnL: ${data.total_realized_pnl.toFixed(2)}`;
        document.getElementById("portfolio-unrealized").textContent =
            `Unrealized PnL: ${data.total_unrealized_pnl.toFixed(2)}`;
    }
};


// ---------------------------------------
// Symbol Panels
// ---------------------------------------
async function loadSymbols() {
    const res = await fetch("/telemetry/symbols");
    const symbols = await res.json();

    const container = document.getElementById("symbols-container");
    container.innerHTML = "";

    Object.keys(symbols).forEach(symbol => {
        const div = document.createElement("div");
        div.className = "symbol-panel";
        // sanitize id
        const safeId = symbol.replace(/[^a-zA-Z0-9_-]/g, "_");
        div.id = `symbol-${safeId}`;
        div.innerHTML = `
            <h3>${symbol}</h3>
            <div class='label'>Regime:</div> <span id='${safeId}-regime'></span><br>
            <div class='label'>Intent:</div> <span id='${safeId}-intent'></span><br>
            <div class='label'>Strength:</div> <span id='${safeId}-strength'></span><br>
            <div class='label'>Position:</div> <span id='${safeId}-position'></span><br>
            <div class='label'>PnL:</div> <span id='${safeId}-pnl'></span><br>
        `;
        container.appendChild(div);

        subscribeSymbol(symbol, safeId);
    });
}


// ---------------------------------------
// Subscribe to each symbol WebSocket
// ---------------------------------------
function subscribeSymbol(symbol, safeId) {
    const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
    const ws = new WebSocket(`${protocol}://${window.location.host}/ws/symbol/${encodeURIComponent(symbol)}`);

    ws.onmessage = (event) => {
        const data = JSON.parse(event.data);

        document.getElementById(`${safeId}-regime`).textContent = data.last_regime || '';
        document.getElementById(`${safeId}-intent`).textContent = data.intent || '';
        document.getElementById(`${safeId}-strength`).textContent = (data.strength || 0).toFixed(3);

        const exec = data.execution || {};
        const posSide = exec.side || "flat";
        const qty = exec.qty || 0;

        document.getElementById(`${safeId}-position`).textContent = `${posSide} (${qty})`;

        const unreal = exec.unrealized_pnl || 0;
        const real = exec.realized_pnl || 0;

        document.getElementById(`${safeId}-pnl`).textContent = `R: ${real.toFixed(2)} | U: ${unreal.toFixed(2)}`;
    };
}


// ---------------------------------------
// Initial load
// ---------------------------------------
loadSymbols();
