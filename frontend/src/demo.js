// Invented, precomputed presentation fixtures. No broker, workbook or live inputs.
export const PREVIEW_NOTICE = 'DEMO PREVIEW · Invented data · Not connected to your account';
export const snapshot = {
  environment: 'demo', source: 'invented', asOf: '2026-10-31', currency: 'GBP',
  nav: '40000.00', holdingsValue: '38600.00', cash: '1400.00',
  dayChange: '184.00', dayChangePercent: '0.46',
};
export const holdings = [
  { ticker: 'VUAG', name: 'Vanguard S&P 500 UCITS ETF', group: 'Core', value: '9000.00', weight: '22.50', dayChange: '24.00', changePercent: '0.27', color: '#76b9eb', kind: 'ETF', description: 'Illustrative US large-cap equity holding.' },
  { ticker: 'IWDA', name: 'iShares Core MSCI World UCITS ETF', group: 'Core', value: '7600.00', weight: '19.00', dayChange: '20.00', changePercent: '0.26', color: '#9390ed', kind: 'ETF', description: 'Illustrative developed-market equity holding.' },
  { ticker: 'MSFT', name: 'Microsoft', group: 'Growth', value: '5400.00', weight: '13.50', dayChange: '48.00', changePercent: '0.90', color: '#60c4c7', kind: 'Equity', description: 'An invented position for exploring the holding detail view.' },
  { ticker: 'NVDA', name: 'NVIDIA', group: 'Growth', value: '4800.00', weight: '12.00', dayChange: '60.00', changePercent: '1.27', color: '#9bc57d', kind: 'Equity', description: 'An invented position for exploring the holding detail view.' },
  { ticker: 'ASML', name: 'ASML Holding', group: 'Growth', value: '3900.00', weight: '9.75', dayChange: '18.00', changePercent: '0.46', color: '#879bd9', kind: 'Equity', description: 'An invented position for exploring the holding detail view.' },
  { ticker: 'AMZN', name: 'Amazon', group: 'Growth', value: '3600.00', weight: '9.00', dayChange: '8.00', changePercent: '0.22', color: '#d9af70', kind: 'Equity', description: 'An invented position for exploring the holding detail view.' },
  { ticker: 'ULVR', name: 'Unilever', group: 'Defensive', value: '2500.00', weight: '6.25', dayChange: '4.00', changePercent: '0.16', color: '#7da7d2', kind: 'Equity', description: 'An invented position for exploring the holding detail view.' },
  { ticker: 'GSK', name: 'GSK', group: 'Defensive', value: '1800.00', weight: '4.50', dayChange: '2.00', changePercent: '0.11', color: '#d59282', kind: 'Equity', description: 'An invented position for exploring the holding detail view.' },
];
export const groups = [
  { name: 'Core', value: '16600.00', weight: '41.50', color: '#65c5c6', description: 'Broad-market foundations', count: 2 },
  { name: 'Growth', value: '17700.00', weight: '44.25', color: '#8e9aeb', description: 'Long-term growth companies', count: 4 },
  { name: 'Defensive', value: '4300.00', weight: '10.75', color: '#d8b579', description: 'Defensive equity positions', count: 2 },
];
export const histories = {
  '1M': { labels: ['01 Oct', '03 Oct', '05 Oct', '07 Oct', '09 Oct', '11 Oct', '13 Oct', '15 Oct', '17 Oct', '19 Oct', '21 Oct', '23 Oct', '25 Oct', '27 Oct', '29 Oct', '31 Oct'], values: [38100, 38350, 38200, 38700, 38500, 38850, 38620, 39200, 39000, 39180, 39500, 39320, 39650, 39550, 39816, 40000] },
  '3M': { labels: ['01 Aug', '08 Aug', '15 Aug', '22 Aug', '29 Aug', '05 Sep', '12 Sep', '19 Sep', '26 Sep', '03 Oct', '10 Oct', '17 Oct', '24 Oct', '31 Oct'], values: [35300, 35900, 35700, 36600, 36200, 37100, 36900, 37600, 37300, 38200, 38700, 39000, 39500, 40000] },
  'All': { labels: ['Jan 26', 'Feb 26', 'Mar 26', 'Apr 26', 'May 26', 'Jun 26', 'Jul 26', 'Aug 26', 'Sep 26', 'Oct 26'], values: [25200, 26800, 26100, 29200, 31100, 30400, 33100, 35300, 37600, 40000] },
};
