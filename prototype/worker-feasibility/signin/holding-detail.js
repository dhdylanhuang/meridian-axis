(() => {
  const el = id => document.getElementById(id);
  const dialog = el('holding-detail');
  const form = el('holding-thesis-form');
  const thesis = el('holding-thesis');
  const exit = el('holding-exit');
  const status = el('holding-thesis-status');
  const { timestamp } = window.meridianDates;
  const figureIds = ['value', 'average', 'price', 'quantity', 'name', 'ticker', 'source'];
  let selected = null;
  let opener = null;

  function open(holding, snapshot, button, decimal) {
    if (!snapshot || dialog.open) return;
    selected = `meridian-axis:holding-notes:v1:${snapshot.environment}:${holding.ticker}`;
    opener = button;
    const money = (value, currency) => currency ? decimal(value, currency) : 'Unavailable';
    const figures = {
      name: holding.name || holding.ticker,
      ticker: holding.ticker,
      value: money(holding.current_value, holding.account_currency),
      average: money(holding.average_price_paid, holding.instrument_currency),
      price: money(holding.current_price, holding.instrument_currency),
      quantity: decimal(holding.quantity),
      source: `Trading 212 · Holdings captured ${timestamp(snapshot.positions_retrieval?.retrieval_completed_at)}`,
    };
    for (const id of figureIds) el(`holding-detail-${id}`).textContent = figures[id];
    thesis.value = exit.value = '';
    status.textContent = '';
    try {
      const saved = JSON.parse(localStorage.getItem(selected));
      if (saved) {
        thesis.value = typeof saved.thesis === 'string' ? saved.thesis : '';
        exit.value = typeof saved.exit === 'string' ? saved.exit : '';
        if (saved.updatedAt) status.textContent = `Last saved ${timestamp(saved.updatedAt)}.`;
      }
    } catch {
      status.textContent = 'Saved notes could not be read from this browser.';
    }
    dialog.showModal();
  }

  function clear() {
    opener = null;
    selected = null;
    thesis.value = exit.value = '';
    status.textContent = '';
    for (const id of figureIds) el(`holding-detail-${id}`).textContent = '';
    if (dialog.open) dialog.close();
  }

  form.addEventListener('submit', event => {
    event.preventDefault();
    if (!selected || !dialog.open) return;
    try {
      localStorage.setItem(selected, JSON.stringify({
        thesis: thesis.value,
        exit: exit.value,
        updatedAt: new Date().toISOString(),
      }));
      status.textContent = 'Notes saved in this browser.';
    } catch {
      status.textContent = 'Notes could not be saved. Check whether this browser allows site storage.';
    }
  });
  el('holding-thesis-template').addEventListener('click', () => {
    if (!thesis.value.trim()) thesis.value = 'Investment case:\nEvidence to track:\nKey risk:';
    if (!exit.value.trim()) exit.value = 'Thesis invalidation:\nRisk or sizing trigger:\nReview date:';
    thesis.focus();
  });
  el('holding-detail-close').addEventListener('click', () => dialog.close());
  dialog.addEventListener('close', () => {
    if (dialog.open) return;
    const previous = opener;
    clear();
    if (previous) (previous.isConnected ? previous : el('holdings-tab')).focus();
  });

  window.meridianHoldingDetail = { open, clear };
})();
