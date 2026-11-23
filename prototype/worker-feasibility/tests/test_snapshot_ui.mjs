import assert from 'node:assert/strict';
import test from 'node:test';
import vm from 'node:vm';
import fs from 'node:fs';
const source=fs.readFileSync(new URL('../signin/snapshot.js',import.meta.url),'utf8');
const dates = fs.readFileSync(new URL('../signin/dates.js', import.meta.url), 'utf8');
const holdingDetail = fs.readFileSync(new URL('../signin/holding-detail.js', import.meta.url), 'utf8');
const planning = fs.readFileSync(new URL('../signin/planning.js', import.meta.url), 'utf8');
class Element {
  constructor(tag){this.tag=tag;this.textContent='';this.value='';this.children=[];this.listeners={};this.attributes={};this.dataset={};}
  append(child){child.parentElement=this;this.children.push(child);}
  remove(){this.parentElement.children=this.parentElement.children.filter(child=>child!==this);}
  querySelectorAll(selector){
    const key=selector.slice(6,-1).replace(/-([a-z])/g, (_, letter)=>letter.toUpperCase());
    return this.children.flatMap(child=>[...(key in child.dataset?[child]:[]),...child.querySelectorAll(selector)]);
  }
  replaceChildren(...children){this.children=children.flatMap(child=>child.fragment?child.children:[child]);}
  addEventListener(name,fn){this.listeners[name]=fn;}
  setAttribute(name,value){this.attributes[name]=value;}
}
function setup(fetcher, withPlanning = false, holdingStorage = null){
  const elements=new Map();const window=new EventTarget();
  let now = 1_000_000, nextTimer = 0;
  const timers = new Map(), events = {};
  class Clock extends Date { constructor(...args){super(...(args.length ? args : [now]));} static now(){return now;} }
  const setTimeout = (fn, delay) => {const id=++nextTimer;timers.set(id,{fn,at:now+delay,delay});return id;};
  const clearTimeout = id => timers.delete(id);
  const document={hidden:false,addEventListener(name,fn){events[name]=fn;},getElementById(id){if(!elements.has(id))elements.set(id,new Element());return elements.get(id);},createElement(tag){return new Element(tag);},createDocumentFragment(){const e=new Element();e.fragment=true;return e;},body:{classList:{add(){},remove(){}}}};
  const context = vm.createContext({document,window,fetch:fetcher,AbortController,Event,BigInt,Date:Clock,setTimeout,clearTimeout});
  vm.runInContext(dates, context);
  if (withPlanning) vm.runInContext(planning, context);
  if (holdingStorage) {
    const dialog = document.getElementById('holding-detail');
    dialog.showModal = () => { dialog.open = true; };
    dialog.close = () => { dialog.open = false; dialog.listeners.close(); };
    document.getElementById('holding-thesis').focus = () => {};
    document.getElementById('holdings-tab').focus = () => {};
    context.localStorage = {
      getItem: key => holdingStorage.get(key) ?? null,
      setItem: (key, value) => holdingStorage.set(key, value),
    };
    vm.runInContext(holdingDetail, context);
  }
  vm.runInContext(source, context);
  return {view:window.meridianSnapshot,el:id=>document.getElementById(id),window,timers,document,
    advance(ms){now+=ms;},
    async tick(ms){now+=ms;for(const [id,timer] of [...timers])if(timer.at<=now){timers.delete(id);await timer.fn();}},
    async visibility(hidden){document.hidden=hidden;await events.visibilitychange();await new Promise(resolve=>setImmediate(resolve));}
  };
}
function snapshot(){return {source:'trading212',basis:'broker_reported',environment:'demo',currency:'GBP',total_value:'9007199254740993.123456789',investments:{currentValue:'99',totalCost:'11',unrealizedProfitLoss:'2'},cash_components:{availableToTrade:'7'},account_retrieval:{retrieval_completed_at:'2026-01-02T12:00:00Z'},positions_retrieval:{retrieval_completed_at:'2026-01-02T12:00:01Z'},positions:[{name:'<img src=x>',ticker:'SYNTH',quantity:'0.00000000000000001',current_value:'10',account_currency:'GBP',instrument_currency:'USD',current_price:'12.34'}]};}
test('dashboard dates use the requested London-time format and keep UTC date buckets', () => {
 const window = {};
 vm.runInNewContext(dates, {window});
 const {timestamp, day} = window.meridianDates;
 assert.equal(timestamp('2026-11-22T17:40:27.414000+00:00'), '5:40pm 22 Nov 2026');
 assert.equal(timestamp('2026-07-22T23:40:27Z'), '12:40am 23 Jul 2026');
 assert.equal(timestamp('2026-07-22'), '22 Jul 2026');
 assert.equal(day('2026-07-22', true), '22 Jul');
 assert.equal(timestamp(null), 'Unavailable');
});
test('broker total stays exact; values missing remain unavailable and names are literal text',async()=>{
 const ui=setup(async()=>({ok:true,status:200,json:async()=>snapshot()}));await ui.view.load();
 assert.equal(ui.el('total-value').textContent,'£9,007,199,254,740,993.123456789');
 assert.match(content(ui.el('cash-reconciliation')), /Cash in pies Unavailable/);
 assert.equal(ui.el('holdings-body').children[0].children[0].textContent,'<img src=x>');
 ui.el('holding-search').value='absent';ui.el('holding-search').listeners.input();
 assert.equal(ui.el('holdings-body').children.length,0);
 ui.view.clear();assert.equal(ui.el('total-value').textContent,'—');assert.equal(ui.el('holdings-body').children.length,0);
});
test('Holdings sorts exact unrealised PnL in either direction with unavailable values last', async () => {
  const data = snapshot();
  data.positions = [
    ['MISSING',null], ['GAIN','1.000000000000000001'], ['LOSS','-3.25'],
    ['LARGER','1.000000000000000002'], ['FLAT','0'],
  ].map(([ticker, pnl]) => ({...data.positions[0], ticker, name:ticker, unrealized_profit_loss:pnl}));
  const ui = setup(async () => Response.json(data));
  await ui.view.load();
  const order = () => ui.el('holdings-body').children.map(row => row.children[0].textContent);
  const sort = ui.el('holding-sort');
  sort.value = 'pnl-desc';
  sort.listeners.change();
  assert.deepEqual(order(), ['LARGER','GAIN','FLAT','LOSS','MISSING']);
  sort.value = 'pnl-asc';
  sort.listeners.change();
  assert.deepEqual(order(), ['LOSS','FLAT','GAIN','LARGER','MISSING']);
  assert.match(content(ui.el('holdings-mobile-list').children[0]), /LOSS.*PnL −£3.25/s);
  const mobileLoss = findNode(ui.el('holdings-mobile-list'), node => node.textContent === 'PnL −£3.25');
  assert.equal(mobileLoss.attributes['data-tone'], 'loss');
});
test('holding detail shows broker figures and keeps notes scoped to the holding across reloads', async () => {
  const data = snapshot();
  data.positions[0].average_price_paid = '8.123456789012345';
  data.positions[0].unrealized_profit_loss = '-0.000000000000000001';
  data.investments.realizedProfitLoss = '-1';
  data.positions.push({...data.positions[0], ticker:'OTHER', name:'Other holding', average_price_paid:null, unrealized_profit_loss:'-0.00'});
  const storage = new Map();
  const load = async () => {
    const ui = setup(async () => Response.json(data), false, storage);
    await ui.view.load();
    ui.el('mobile-holdings-tab').listeners.click();
    return ui;
  };
  const open = (ui, label) => findNode(ui.el('holdings-body'), node => node.tag === 'button' && node.textContent === label)
    .listeners.click();
  const ui = await load();
  const [lossRow, flatRow] = ui.el('holdings-body').children;
  assert.equal(lossRow.children.at(-1).attributes['data-tone'], 'loss');
  assert.equal(flatRow.children.at(-1).attributes['data-tone'], '');
  assert.equal(lossRow.children[4].attributes['data-tone'], undefined);
  assert.equal(ui.el('unrealised-pnl').attributes['data-tone'], 'gain');
  assert.equal(ui.el('realised-pnl').attributes['data-tone'], 'loss');
  const mobile = ui.el('holdings-mobile-list').children[0].children[0];
  mobile.listeners.click();
  assert.equal(ui.el('mobile-holdings-tab').attributes['aria-pressed'], 'true');
  assert.equal(ui.el('holding-detail-pnl').attributes['data-tone'], 'loss');
  assert.equal(ui.el('holding-detail').open, true);
  assert.equal(ui.el('holding-detail-name').textContent, '<img src=x>');
  assert.equal(ui.el('holding-detail-value').textContent, '£10');
  assert.equal(ui.el('holding-detail-average').textContent, '8.123456789012345 USD');
  assert.match(ui.el('holding-detail-source').textContent, /Trading 212 · Holdings captured/);
  assert.equal(ui.el('holding-thesis').value, '');
  ui.el('holding-thesis').value = 'Synthetic reason';
  ui.el('holding-thesis-template').listeners.click();
  assert.equal(ui.el('holding-thesis').value, 'Synthetic reason');
  assert.match(ui.el('holding-exit').value, /Thesis invalidation/);
  ui.el('holding-exit').value = 'Synthetic exit condition';
  ui.el('holding-thesis-form').listeners.submit({preventDefault(){}});
  assert.match(ui.el('holding-thesis-status').textContent, /Notes saved/);
  ui.el('holding-detail-close').listeners.click();
  assert.equal(ui.el('holding-thesis').value, '');
  assert.equal(ui.el('holdings-body').children.length, 2);
  open(ui, 'Other holding');
  assert.equal(ui.el('holding-detail-average').textContent, 'Unavailable');
  assert.equal(ui.el('holding-thesis').value, '');

  const restored = await load();
  open(restored, '<img src=x>');
  assert.equal(restored.el('holding-thesis').value, 'Synthetic reason');
  assert.equal(restored.el('holding-exit').value, 'Synthetic exit condition');
  restored.view.clear();
  assert.equal(restored.el('holding-detail').open, false);
  assert.equal(restored.el('holding-detail-name').textContent, '');
  assert.equal(restored.el('holding-thesis').value, '');
  assert.equal(storage.size, 1);
});
test('late response cannot repopulate after clearing private state',async()=>{
 let finish;const ui=setup(()=>new Promise(resolve=>finish=resolve));const load=ui.view.load();ui.view.clear();finish({ok:true,status:200,json:async()=>snapshot()});await load;
 assert.equal(ui.el('total-value').textContent,'—');assert.equal(ui.el('holdings-body').children.length,0);
});
test('denied session clears fields and dispatches signout; empty snapshot has explicit state',async()=>{
 const ui=setup(async()=>({ok:false,status:401}));let ended=false;ui.window.addEventListener('meridian-session-ended',()=>ended=true);await ui.view.load();assert.equal(ended,true);assert.equal(ui.el('total-value').textContent,'—');
 const empty=setup(async()=>({ok:false,status:404}));await empty.view.load();assert.match(empty.el('snapshot-status').textContent,/No saved snapshot/);
});
test('failed saved-snapshot reload retains last successful figures',async()=>{
 let fail=false;
 const ui=setup(async path=>path.endsWith('/status')?({ok:true,status:200,json:async()=>({jobs:{}})}):fail?({ok:false,status:503}):({ok:true,status:200,json:async()=>snapshot()}));
 await ui.view.load();fail=true;ui.advance(60_000);await ui.view.load();
 assert.equal(ui.el('total-value').textContent,'£9,007,199,254,740,993.123456789');
 assert.match(ui.el('snapshot-status').textContent,/Last successful snapshot/);
});

test('snapshot and health share one request, polling waits ten minutes and pauses while hidden',async()=>{
 let reads=0, historyReads=0;
 const ui=setup(async path=>{if(path.endsWith('/history')){historyReads++;return {ok:false,status:503};}reads++;assert.equal(path,'/api/v1/portfolio/snapshot');return {ok:true,status:200,json:async()=>({...snapshot(),refresh_health:{jobs:{snapshot:{stale:false}}}})};});
 ui.view.start();await new Promise(resolve=>setImmediate(resolve));
 assert.equal(reads,1);assert.equal([...ui.timers.values()][0].delay,600_000);
 await ui.tick(599_999);assert.equal(reads,1);
 await ui.tick(1);assert.equal(reads,2);
 await ui.visibility(true);assert.equal(ui.timers.size,0);
 await ui.tick(600_000);assert.equal(reads,2);
 await ui.visibility(false);assert.equal(reads,3);
 ui.view.clear();await ui.tick(600_000);assert.equal(reads,3);assert.equal(historyReads,1);
});
test('outage backoff resists reload and visibility storms and retains last-good values',async()=>{
 let reads=0, fail=false;
 const ui=setup(async path=>{if(path.endsWith('/history')) return {ok:false,status:503};reads++;return fail?{ok:false,status:503}:{ok:true,status:200,json:async()=>snapshot()};});
 ui.view.start();await new Promise(resolve=>setImmediate(resolve));fail=true;
 await ui.tick(600_000);assert.equal(reads,2);
 for(let i=0;i<5;i++){await ui.view.load();await ui.visibility(true);await ui.visibility(false);}
 assert.equal(reads,2);
 assert.equal(ui.el('total-value').textContent,'£9,007,199,254,740,993.123456789');
 await ui.tick(600_000);assert.equal(reads,3);
 assert.equal([...ui.timers.values()][0].delay,1_200_000);
});
test('repeated manual clicks queue once and do not immediately re-read the old snapshot',async()=>{
 let reads=0, posts=0;
 const ui=setup(async(path,options)=>{if(options?.method==='POST'){posts++;return {ok:true,status:202,json:async()=>({status:'queued'})};}if(path.endsWith('/history')) return {ok:false,status:503};reads++;return {ok:true,status:200,json:async()=>snapshot()};});
 ui.view.start();await new Promise(resolve=>setImmediate(resolve));
 ui.document.cookie='__Host-meridian_csrf=synthetic';
 await ui.el('refresh-broker').listeners.click();await ui.el('refresh-broker').listeners.click();
 assert.equal(posts,1);assert.equal(reads,1);
 await ui.tick(60_000);assert.equal(reads,2);
});

test('failed manual request pauses further manual and saved-snapshot requests',async()=>{
 let calls=0;
 const ui=setup(async(path,options)=>{if(path.endsWith('/history')) return {ok:false,status:503};calls++;return options?.method==='POST'?{ok:false,status:503}:{ok:true,status:200,json:async()=>snapshot()};});
 ui.document.cookie='__Host-meridian_csrf=synthetic';
 ui.view.start();await new Promise(resolve=>setImmediate(resolve));
 await ui.el('refresh-broker').listeners.click();
 ui.advance(60_000);
 await ui.el('refresh-broker').listeners.click();await ui.view.load();
 assert.equal(calls,2);
 assert.match(ui.el('refresh-status').textContent,/cooling down/);
});

test('new-holding notice and metadata limitations render through the existing snapshot view',async()=>{
 const data=snapshot();data.holding_changes={added_tickers:['SYNTH'],closed_tickers:[]};
 data.positions[0].metadata={state:'pending'};
 const ui=setup(async()=>({ok:true,status:200,json:async()=>data}));await ui.view.load();
 assert.match(ui.el('snapshot-status').textContent,/1 holdings added, 0 no longer held/);
 assert.match(ui.el('snapshot-status').textContent,/not execution confirmations/);
 const ticker=ui.el('holdings-body').children[0].children[0].children[0];
 assert.equal(ticker.textContent,'SYNTH · metadata pending');
 assert.equal(ui.el('holdings-body').children[0].children[2].textContent,'12.34 USD');
 ui.view.clear();assert.equal(ui.el('snapshot-status').textContent,'');
});


function content(element){return [element.textContent,...element.children.map(content)].join(' ');}
test('funding view shows monetary categories separately from current cash and clears them',async()=>{
 const data=snapshot();data.cash_reconciliation={reported_activity:{since:'2026-01-01T00:00:00Z',cutoff:'2026-01-02T12:00:00Z',excluded_conflicts:1,totals:[{category:'dividends',currency:'GBP',amount:'0.01234567890123456789',event_count:1},{category:'cash_interest',currency:'GBP',amount:'0.25',event_count:2},{category:'deposits',currency:'GBP',amount:'100',event_count:1},{category:'withdrawals',currency:'GBP',amount:'-4',event_count:1},{category:'deposits',currency:'USD',amount:'7',event_count:1}]}};
 const ui=setup(async()=>({ok:true,status:200,json:async()=>data}));await ui.view.load();
 ui.el('axis-tab').listeners.click();
 assert.equal(ui.el('cash-panel').hidden,true);
 ui.el('cash-tab').listeners.click();
 assert.equal(ui.el('cash-panel').hidden,false);
 assert.equal(ui.el('axis-panel').hidden,true);
 const text=content(ui.el('cash-reconciliation'));
 assert.match(text,/Cash available to trade now £7/);
 assert.match(text,/Paid dividends & distributions £0.01234567890123456789/);
 assert.match(text,/Cash interest £0.25/); assert.match(text,/Deposits £100/);
 assert.match(text,/Withdrawals −£4/); assert.match(text,/Deposits 7 USD/);
 assert.match(text,/Fees Not established/);assert.match(text,/Historical coverage is incomplete/);
 assert.match(text,/do not describe the composition of today’s cash/);
 assert.match(text,/1 conflicting records excluded/);
 assert.doesNotMatch(text,/578|cash events captured|unexplained difference/);
 ui.view.clear();assert.equal(content(ui.el('cash-reconciliation')),'—');
});
test('funding view retains current cash with an older or unavailable activity snapshot',async()=>{
 const data=snapshot();data.cash_reconciliation={availability:'provisional',event_count:578,activity_counts:{DEPOSIT:9}};
 const ui=setup(async()=>({ok:true,status:200,json:async()=>data}));await ui.view.load();
 const text=content(ui.el('cash-reconciliation'));
 assert.match(text,/Cash available to trade now £7/);
 assert.match(text,/amounts are not available in this saved snapshot/);
 assert.doesNotMatch(text,/578|£0|sign conventions/);
});

function descendants(element){return [element,...element.children.flatMap(descendants)];}
test('activity drilldown loads only on demand and paginates the saved total',async()=>{
 const data=snapshot(),revision='a'.repeat(64);
 data.cash_reconciliation={source_snapshot_id:'saved',input_revision:revision,activity_details_available:true,
  history_coverage:{scope:'broker_available_history',families:[{family:'transactions',state:'provider_history_traversed',completed_at:'2026-01-02T10:00:00Z',earliest_observed_at:'2025-01-01T00:00:00Z'},{family:'dividends',state:'not_established'}]},
  reported_activity:{since:'2026-01-01T00:00:00Z',cutoff:'2026-01-02T12:00:00Z',excluded_conflicts:0,totals:[{category:'cash_interest',currency:'GBP',amount:'5.25',event_count:21}]}};
 const calls=[];
 const ui=setup(async(url,options)=>{
  if(url.endsWith('/snapshot')) return {ok:true,status:200,json:async()=>data};
  const query=JSON.parse(options.body);calls.push(query);
  assert.equal(options.headers['X-CSRF-Token'],'n'.repeat(43));
  return {ok:true,status:200,json:async()=>({snapshot_id:'saved',input_revision:revision,category:'cash_interest',currency:'GBP',offset:query.offset,total_count:21,
   entries:Array.from({length:query.offset===0?20:1},(_,i)=>({occurred_at:'2026-01-01T00:00:00Z',instrument_label:'<img src=x>',amount:'0.25',currency:'GBP',reference:'ref-'+(query.offset+i),family:'transactions',provider_type:'INTEREST_ON_FREE_CASH',source_id:'source-'+i,revision_id:'revision-'+i,revision:1,digest:'b'.repeat(64)}))})};
 });
 ui.document.cookie='__Host-meridian_csrf='+'n'.repeat(43);await ui.view.load();assert.equal(calls.length,0);
 const root=ui.el('cash-reconciliation');assert.match(content(root),/all available broker pages fetched/);assert.match(content(root),/completed broker history traversal has not been established/);
 await descendants(root).find(node=>node.textContent==='View transactions').listeners.click();
 assert.equal(calls.length,1);assert.equal(calls[0].snapshot_id,'saved');assert.match(content(root),/Showing 1–20 of 21/);
 assert.match(content(root),/ref-0/);assert.match(content(root),/SHA-256/);assert.match(content(root),/<img src=x>/);
 await descendants(root).find(node=>node.textContent==='Next page').listeners.click();
 assert.equal(calls[1].offset,20);assert.match(content(root),/Showing 21–21 of 21/);
 assert.doesNotMatch(content(root),/ref-0/);
 await descendants(root).find(node=>node.textContent==='Close transactions').listeners.click();
 assert.equal(descendants(root).find(node=>node.id==='cash-transactions').hidden,true);
 assert.doesNotMatch(content(root),/ref-20/);
 ui.view.clear();assert.equal(content(root),'—');
});
test('late activity page cannot repopulate after signout',async()=>{
 const data=snapshot();data.cash_reconciliation={source_snapshot_id:'saved',input_revision:'a'.repeat(64),activity_details_available:true,reported_activity:{since:'2026-01-01',cutoff:'2026-01-02',totals:[{category:'deposits',currency:'GBP',amount:'1',event_count:1}]}};
 let finish;
 const ui=setup(async(url)=>url.endsWith('/snapshot')?{ok:true,status:200,json:async()=>data}:await new Promise(resolve=>{finish=resolve;}));
 ui.document.cookie='';await ui.view.load();
 const pending=descendants(ui.el('cash-reconciliation')).find(node=>node.textContent==='View transactions').listeners.click();
 ui.view.clear();finish({ok:true,status:200,json:async()=>({entries:[{reference:'should-not-appear'}]})});await pending;
 assert.equal(content(ui.el('cash-reconciliation')),'—');
});

test('portfolio exposures show exact amounts and filter the existing holdings view', async () => {
  const data = snapshot();
  const value = '10.000000000000000000001';
  data.positions[0].current_value = value;
  data.positions.push({name:'Missing Wallet',ticker:'MISSING',quantity:'2',instrument_currency:'USD'});
  const observed = {value,portfolio_pct:'0',invested_pct:'10.1'};
  const sector = {...observed,value:'5.000000000000000000001',invested_pct:'5.05'};
  const missing = {value:null,portfolio_pct:null,invested_pct:null};
  data.exposures = {
    account_as_of:data.account_retrieval.retrieval_completed_at,
    positions_as_of:data.positions_retrieval.retrieval_completed_at,
    invested_denominator:'99',portfolio_denominator:data.total_value,
    observed_holdings:observed,missing_values:1,
    holdings:[{ticker:'SYNTH',quote_currency:'USD',...observed},{ticker:'MISSING',quote_currency:null,...missing}],
    quote_currencies:[{quote_currency:'USD',missing_values:0,...observed},{quote_currency:null,missing_values:1,...missing}],
    concentration:[{top:1,position_count:1,...missing}],
    sectors:{classified:sector,observed,sources:{SYNTH:{as_of:'2026-01-01',url:'https://example.test/fact'}},
      buckets:[
        {label:'Industrials',...sector,members:{SYNTH:{value:sector.value,holding_pct:'50',source_labels:['ICB · Industrials']}}},
        {label:null,...sector,value:'5',members:{SYNTH:{value:'5',holding_pct:'50'},MISSING:{value:null,holding_pct:'100'}}},
      ]},
    issuer_domiciles:{classified:missing,observed,sources:{},
      buckets:[{label:null,...observed,members:{SYNTH:{value,holding_pct:'100'},MISSING:{value:null,holding_pct:'100'}}}]},
    fund_markets:{classified:observed,observed,sources:{},
      buckets:[{label:'Synthetic region',...observed,members:{SYNTH:{value,holding_pct:'100'}}}]},
    cash_component_pct:{availableToTrade:'0',inPies:null,reservedForOrders:null},
  };
  const ui = setup(async () => ({ok:true,status:200,json:async()=>data}));
  const createElement = ui.document.createElement;
  let arcs = 0;
  ui.document.createElement = tag => {
    const element = createElement(tag);
    if (tag === 'canvas') element.getContext = () => ({
      clearRect() {}, beginPath() {}, stroke() {}, arc() { arcs++; },
    });
    return element;
  };
  await ui.view.load();
  const section = ui.el('portfolio-exposures');
  const find = (node, value) => node.textContent === value ? node
    : node.children.map(child => find(child, value)).find(Boolean);
  assert.ok(find(section, '£10.000000000000000000001'));
  assert.ok(find(section, '10.1%'));
  assert.ok(find(section, 'Largest position'));
  assert.ok(find(section, 'Equity sectors'));
  const charts = section.children.filter(node => node.tag === 'figure');
  assert.deepEqual(charts.map(chart => chart.children[0].textContent), [
    'Concentration · each ring is a share of ISA value',
    'Holdings · share of observed GBP position values',
    'Listing currencies · share of observed GBP values',
    'Equity sectors · share of observed GBP values',
    'Direct shares · issuer domicile · share of observed GBP values',
    'Funds · underlying markets · share of observed GBP values',
    'Cash components · each ring is a share of ISA value',
  ]);
  assert.ok(find(charts[0], 'Unavailable'));
  assert.ok(find(charts[3], 'Unclassified'));
  assert.ok(find(charts[5], 'Synthetic region'));
  assert.ok(find(charts[6], '0%'));
  assert.ok(find(charts[6], 'Unavailable'));
  assert.equal(arcs, 7);
  const legend = ui.el('overview-allocation-legend');
  assert.ok(find(legend, 'Industrials'));
  assert.ok(find(legend, '£5.000000000000000000001'));
  assert.ok(find(legend, 'Unclassified'));
  assert.ok(find(legend, '£5'));
  assert.equal(find(legend, 'USD'), undefined);
  assert.equal(ui.el('overview-marked-value').textContent, '£10.000000000000000000001');
  assert.match(ui.el('overview-allocation-status').textContent, /without a usable GBP mark/);
  find(ui.el('overview-top-holdings'), '<img src=x>').listeners.click();
  assert.equal(ui.el('workspace-path').textContent, 'Holdings');
  assert.equal(ui.el('holdings-body').children.length, 1);
  ui.el('exposures-tab').listeners.click();
  assert.equal(section.hidden,false);
  const link = label => findNode(section, node => node.tag === 'button' && node.textContent === label);
  link('Industrials').listeners.click();
  const contributing = ui.el('holdings-body').children[0];
  assert.ok(find(contributing, 'Bucket contribution: £5.000000000000000000001 · 50% of position'));
  assert.ok(find(contributing, 'Source categories · ICB · Industrials'));
  assert.equal(find(contributing, 'Source · 1 Jan 2026').href, 'https://example.test/fact');
  link('Unclassified quote currency').listeners.click();
  assert.equal(ui.el('holdings-panel').hidden,false);
  assert.equal(ui.el('holdings-body').children.length,1);
  assert.equal(ui.el('holdings-body').children[0].children[0].textContent,'Missing Wallet');
  link('USD').listeners.click();
  assert.equal(ui.el('holdings-body').children[0].children[5].textContent,'10.1%');
  link('Unclassified').listeners.click();
  assert.equal(ui.el('holdings-body').children.length,2);
  ui.el('clear-holding-scope').listeners.click();
  assert.equal(ui.el('holding-scope').hidden,true);
  ui.view.clear();
  assert.equal(section.children.length,0);
  assert.equal(ui.el('holdings-body').children.length,0);
  assert.equal(ui.el('overview-allocation-legend').children.length,0);
  assert.equal(ui.el('overview-allocation-ring').hidden,true);
});

test('Back exits a holding selection and walks back through the workspace tabs', async () => {
  const data = snapshot();
  data.positions.push({...data.positions[0],name:'Second holding',ticker:'SECOND'});
  data.exposures = {
    positions_as_of:data.positions_retrieval.retrieval_completed_at,
    account_as_of:data.account_retrieval.retrieval_completed_at,
    observed_holdings:{value:'20'}, holdings:[{ticker:'SYNTH',value:'10'},{ticker:'SECOND',value:'10'}],
    concentration:[], quote_currencies:[], cash_component_pct:{},
  };
  let reads = 0;
  const ui = setup(async () => { reads++; return Response.json(data); });
  await ui.view.load();
  const back = ui.el('workspace-back');
  const trail = () => ui.el('workspace-path').textContent;
  const selectStock = () => findNode(ui.el('overview-top-holdings'), node => node.tag === 'button').listeners.click();

  selectStock();
  assert.equal(trail(), 'Holdings');
  assert.equal(ui.el('holdings-body').children.length, 1);
  assert.equal(back.attributes['aria-label'], 'Back to all holdings');
  back.listeners.click();
  assert.equal(trail(), 'Holdings');
  assert.equal(ui.el('holdings-body').children.length, 2);
  assert.equal(ui.el('clear-holding-scope').hidden, true);
  back.listeners.click();
  assert.equal(trail(), 'AXIS overview');
  assert.equal(back.disabled, true);

  selectStock();
  ui.el('holdings-tab').listeners.click();
  assert.equal(ui.el('holdings-body').children.length, 2);
  ui.el('exposures-tab').listeners.click();
  ui.el('projections-tab').listeners.click();
  back.listeners.click();
  assert.equal(trail(), 'Exposures');
  back.listeners.click();
  assert.equal(trail(), 'Holdings');
  assert.equal(reads, 1);
  ui.view.clear();
  assert.equal(back.disabled, true);
});
test('History renders exact daily values, breaks the line across gaps, and clears on sign-out',async()=>{
 const days=Array.from({length:90},(_,index)=>({date:new Date(Date.UTC(2026,0,1+index)).toISOString().slice(0,10),status:'missing'}));
 for (const index of [86,87,89]) Object.assign(days[index],{
   status:'observed', total_value:index === 89 ? '9007199254740993.123456789' : String(100+index),
   observed_at:days[index].date+'T11:22:34+00:00',captured_at:days[index].date+'T11:22:33+00:00'
 });
 const data={source:'trading212',basis:'broker_reported',currency:'GBP',as_of:days[89].date+'T12:00:00+00:00',start_date:days[0].date,end_date:days[89].date,days};
 let reads=0, lines=0, fail=false;
 const ui=setup(async(path,options)=>{
   reads++;
   assert.equal(path,'/api/v1/portfolio/history');
   assert.equal(options.cache,'no-store');
   return fail ? {ok:false,status:503} : {ok:true,status:200,json:async()=>data};
 });
 const ctx=new Proxy({}, {get(_,key){return key === 'lineTo' ? ()=>lines++ : ()=>{};}});
 const chart = ui.el('history-chart');
 chart.getContext=()=>ctx;
 chart.clientWidth=358;
 ui.el('mobile-more').open=true;
 ui.el('mobile-history-tab').listeners.click();
 await new Promise(resolve=>setImmediate(resolve));
 assert.equal(reads,1);
 assert.equal(ui.el('mobile-more').open,false);
 assert.equal(ui.el('mobile-more-toggle').attributes['data-active'],'true');
 assert.equal(chart.width,358);
 assert.equal(lines,1);
 assert.match(ui.el('history-status').textContent,/3 of 90 days observed · 87 missing/);
 assert.match(ui.el('overview-history-caption').textContent,/3 of 30 UTC days observed/);
 ui.el('overview-90d').listeners.click();
 assert.match(ui.el('overview-history-caption').textContent,/3 of 90 UTC days observed/);
 assert.equal(reads,1);
 assert.match(ui.el('history-point').textContent,/£9,007,199,254,740,993.123456789.*12:22pm 31 Mar 2026.*12:22pm 31 Mar 2026/);
 ui.el('history-cash-link').listeners.click();
 assert.equal(ui.el('cash-panel').hidden,false);
 assert.equal(ui.el('history-panel').hidden,true);
 ui.el('workspace-back').listeners.click();
 assert.equal(ui.el('history-panel').hidden,false);
 assert.equal(ui.el('cash-panel').hidden,true);
 assert.equal(ui.el('history-body').children.length,90);
 assert.equal(ui.el('history-body').children[0].children[2].title, days[89].captured_at);
 assert.equal(ui.el('history-body').children[1].children[1].textContent,'No saved snapshot');
 chart.listeners.click({offsetX:342});
 assert.match(ui.el('history-point').textContent,/No saved snapshot/);
 ui.el('history-next-day').listeners.click();
 assert.match(ui.el('history-point').textContent,/£9,007,199,254,740,993.123456789/);
 chart.listeners.keydown({key:'ArrowLeft',preventDefault(){}});
 assert.match(ui.el('history-point').textContent,/No saved snapshot/);
 ui.el('axis-tab').listeners.click();
 ui.el('history-tab').listeners.click();
 assert.equal(reads,1);
 fail=true;
 await ui.el('reload-history').listeners.click();
 assert.match(ui.el('history-status').textContent,/Reload failed/);
 assert.equal(ui.el('history-body').children.length,90);
 ui.view.clear();
 assert.equal(ui.el('history-body').children.length,0);
 assert.equal(ui.el('history-point').textContent,'');
 assert.equal(ui.el('history-results').hidden,true);
});

test('late History reads cannot repopulate a signed-out dashboard',async()=>{
 let finish;
 const ui=setup(()=>new Promise(resolve=>finish=resolve));
 const load=ui.el('reload-history').listeners.click();
 ui.view.clear();
 finish({ok:true,status:200,json:async()=>{assert.fail('stale response should be ignored');}});
 await load;
 assert.equal(ui.el('history-status').textContent,'');
 assert.equal(ui.el('history-results').hidden,true);
});

test('History exposes funding evidence and explains ineligible returns without browser calculations', async () => {
 const days=Array.from({length:90},(_,index)=>({date:new Date(Date.UTC(2026,0,1+index)).toISOString().slice(0,10),status:'missing'}));
 const end=days[89].date, start=days[88].date, at=end+'T04:00:00+00:00';
 Object.assign(days[89],{status:'observed',total_value:'100',observed_at:end+'T15:01:00+00:00',captured_at:end+'T15:00:00+00:00'});
 const interval={start_date:start,end_date:end,start_at:start+'T15:00:00+00:00',end_at:days[89].captured_at,return_pct:'2.727273',external_flow_count:1,net_external_flow:'20.123456789'};
 const performance={
   funding:[{kind:'DEPOSIT',amount:'20.123456789',currency:'GBP',at,reference:'invented-ref',signed_gbp:true}],
   funding_coverage:{start_at:days[0].date+'T00:00:00+00:00',end_at:end+'T16:00:00+00:00',completed_at:end+'T17:00:00+00:00'},
   intervals:[interval],latest_eligible:interval,longest_eligible:interval,longest_valuation:{start_date:start,end_date:end,days:2},
   month_to_date:{start_date:start,end_date:end,return_pct:null,intervals:0,reason:'missing_valuation'},year_to_date:null,
   drawdown:{start_at:interval.start_at,as_of:interval.end_at,intervals:1,current_pct:'5',current_peak_at:interval.start_at,
     worst_pct:'10',worst_peak_at:interval.start_at,worst_trough_at:interval.end_at,later_unavailable_intervals:1},
   benchmark:{state:'broker_observed',matched_intervals:1,eligible_intervals:2,source:'Invented closes',reviewed_at:end+'T17:00:00+00:00',
     latest_stretch:{start_date:start,end_date:end,portfolio_pct:'2.727273',benchmark_pct:'2',difference_pp:'0.727273',intervals:1},
     intervals:[{portfolio_start_at:interval.start_at,portfolio_end_at:interval.end_at,portfolio_pct:interval.return_pct,
       start_date:start,end_date:end,benchmark_pct:'2',difference_pp:'0.727273',
       start_mark:{price_gbp:'100',at:start+'T16:35:00+00:00'},
       end_mark:{price_gbp:'102',at:end+'T16:35:00+00:00'}},
       {portfolio_start_at:interval.start_at,portfolio_end_at:interval.end_at,portfolio_pct:'0.002775',start_date:start,end_date:end,
        benchmark_pct:null,difference_pp:null,reason:'missing_benchmark_mark'}]},

 };
 const data={source:'trading212',basis:'broker_reported',currency:'GBP',as_of:end+'T18:00:00+00:00',start_date:days[0].date,end_date:end,days,performance};
 const ui=setup(async()=>({ok:true,status:200,json:async()=>data}));
 ui.el('history-tab').listeners.click();
 await new Promise(resolve=>setImmediate(resolve));
 assert.equal(ui.el('history-funding-note').hidden,false);
 assert.equal(ui.el('history-point').children[0].href,'#history-funding-'+end);
 const text=node=>[node.textContent,...node.children.flatMap(text)];
 const results=text(ui.el('history-performance')).join(' ');
 for (const value of ['2.727273%','£20.123456789','invented-ref','Modified Dietz','A saved valuation is missing','0.727273 pp','VUAG capture missing','Quote age and split adjustments are unverified','1 of 2 eligible intervals matched','£102 · ']) assert.ok(results.includes(value), value);
 const compact = findNode(ui.el('history-performance'), node => node.className?.startsWith('benchmark-summary'));
 const rows = findNode(compact, node => node.tag === 'tbody').children;
 assert.deepEqual(rows[1].children.map(node => node.textContent), ['30–31 Mar 2026','2.73%','2%','0.73 pp']);
 assert.equal(rows[1].children[1].title, '2.727273%');
 assert.deepEqual(rows[0].children.map(node => node.textContent), ['30–31 Mar 2026','<0.01%','—','—']);
 assert.doesNotMatch(content(compact), /£102|VUAG capture missing/);
 const evidence = findNode(ui.el('history-performance'), node => node.tag === 'details' &&
   node.children[0]?.textContent === 'Exact returns, prices and capture times');
 assert.ok(evidence && !evidence.open);
 assert.match(content(evidence), /0.727273 pp.*£102/s);
 assert.ok(!results.includes('Portfolio drawdown'));
 const comparison = ui.el('overview-comparison').children;
 assert.equal(comparison.map(node => node.textContent).join(''), '2.73% vs 2.00%');
 assert.deepEqual(comparison.map(node => node.attributes['data-tone']), ['gain', undefined, 'gain']);
 assert.match(content(ui.el('overview-comparison-period')),/0.73 pp/);
 assert.equal(ui.el('overview-drawdown').attributes['data-tone'], 'loss');
 assert.equal(ui.el('overview-drawdown').textContent,'5.00%');
 ui.view.clear();
 assert.equal(ui.el('history-performance').children.length,0);
 assert.equal(ui.el('overview-comparison').textContent,'—');
 assert.equal(ui.el('history-funding-note').hidden,true);
});

test('Risk applies a dated range and clears private drawdown on sign-out',async()=>{
 const requests=[];
 const ui=setup(async(path)=>{
   requests.push(path);
   const custom=path.includes('?');
   const start=custom?'2026-11-18':'2026-08-23';
   const end=custom?'2026-11-19':'2026-11-20';
   return {ok:true,status:200,json:async()=>({
     performance_state:'available',earliest_date:'2026-08-23',latest_date:'2026-11-20',range:{start,end},
     metrics:{observed:{eligible:1,requested:1,loss_intervals:1,worst:{return_pct:'-12',start_at:start+'T18:00:00+00:00',end_at:end+'T18:00:00+00:00'}},
       daily_state:'awaiting_approved_series',minimum_daily:60,
       cutoff_pilot:{observations:[
         {date:'2026-11-23',target_at:'2026-11-23T22:00:00Z',captured_at:'2026-11-23T22:00:14Z',
          total_value_gbp:'123.456789',status:'observed',funding_coverage:'covered'},
         {date:'2026-11-24',target_at:'2026-11-24T22:00:00Z',captured_at:'2026-11-24T22:00:20Z',
          total_value_gbp:'118.321',status:'observed',funding_coverage:'covered'},
         {date:'2026-11-25',target_at:'2026-11-25T22:00:00Z',captured_at:'2026-11-25T22:00:15Z',
          total_value_gbp:'118.321',status:'observed',funding_coverage:'covered'},
         {date:'2026-11-26',target_at:'2026-11-26T22:00:00Z',status:'missing'},
       ]},
       cutoff_returns:{approval_state:'awaiting_review',intervals:[
         {end_date:'2026-11-23',return_pct:'1.25',approved:false,net_external_flow_gbp:'20.123456',external_flow_count:1},
         {end_date:'2026-11-24',return_pct:'0.25',approved:false,net_external_flow_gbp:'-5.12',external_flow_count:2},
         {end_date:'2026-11-25',return_pct:'0',approved:false,net_external_flow_gbp:'0',external_flow_count:0},
         {end_date:'2026-11-26',reason:'missing_cutoff_observation'},
       ]},
       session_performance: custom ? {
         latest_portfolio:{start_date:start,end_date:end,sessions:1,portfolio_pct:'0.952381'},
         rows:[{start_at:start+'T16:00:00Z',end_at:end+'T16:00:00Z',
           net_external_flow_gbp:'100',external_flow_count:1,portfolio_pct:'0.952381'}],
       } : null,
       holding_correlation: custom ? {state:'available',holdings_as_of:end+'T16:00:00Z',
         included_holdings:2,universe_holdings:2,included_weight_pct:'70',universe_weight_pct:'70',
         n:60,minimum_daily:60,start_date:start,end_date:end,pair_count:1,
         pairs:[{first:'AAA',second:'BBB',correlation:'0.9'}],excluded:[],
       } : {state:'awaiting_approved_holding_series'},
       measures:[
         {key:'volatility',n:0,value:null,reason:'need_portfolio'}]},
     drawdown:{start_at:start+'T18:00:00+00:00',as_of:end+'T18:00:00+00:00',
       intervals:1,current_pct:custom?'12':'5',worst_pct:'12',current_peak_at:start+'T18:00:00+00:00'},
   })};
 });
 ui.el('risk-tab').listeners.click();
 await new Promise(resolve=>setImmediate(resolve));
 assert.equal(ui.el('risk-panel').hidden,false);
 assert.equal(ui.el('risk-start').min,'2026-08-23');
 ui.el('risk-start').value='2026-11-18';
 ui.el('risk-end').value='2026-11-19';
 ui.el('risk-filter').listeners.submit({preventDefault(){}});
 await new Promise(resolve=>setImmediate(resolve));
 assert.deepEqual(requests,['/api/v1/portfolio/risk','/api/v1/portfolio/risk?start=2026-11-18&end=2026-11-19']);
 assert.match(ui.el('risk-status').textContent,/18 Nov 2026 to 19 Nov 2026/);
 const text=node=>[node.textContent,...node.children.flatMap(text)];
 const riskText=text(ui.el('risk-results'));
 assert.ok(riskText.includes('12%'));
 assert.ok(riskText.includes('Worst observed interval return'));
 assert.ok(riskText.includes('Annualised volatility'));
 assert.ok(riskText.includes('£123.456789'));
 assert.ok(riskText.includes('Missed window'));
 assert.ok(riskText.includes('1.25% · Provisional'));
 assert.ok(riskText.includes('+£20.123456 · 1 flow'));
 assert.ok(riskText.includes('−£5.12 · 2 flows'));
 assert.ok(riskText.includes('£0 · 0 flows'));
 assert.ok(riskText.includes('Missing scheduled capture'));
 assert.ok(riskText.includes('10:00pm 23 Nov 2026'));
 assert.ok(riskText.includes('AAA and BBB'));
 assert.ok(riskText.includes('0.952381%'));
 assert.ok(riskText.includes('£100 · 1 event'));
 assert.ok(riskText.includes('Needs more approved portfolio returns'));
 ui.view.clear();
 assert.equal(ui.el('risk-results').children.length,0);
 assert.equal(ui.el('risk-start').value,'');
});

test('Portfolio Changes identifies gaps and links exposure rows to dated holdings', async () => {
  const date = '2026-11-20', capture = date + 'T15:00:00.123456+00:00';
  const observed = {date,status:'observed',positions_captured_at:capture,
    account_captured_at:capture,observed_at:capture,portfolio_denominator:'1000'};
  let missing = true;
  const ui = setup(async url => {
    assert.equal(url, '/api/v1/portfolio/changes?start=2026-11-19&end=2026-11-20');
    return {ok:true,status:200,json:async()=>({
      method:'observed_portfolio_changes_v1',
      start:{...observed,date:'2026-11-19',status:missing?'missing':'observed'}, end:observed,
      holdings:[{ticker:'SYNTH',status:'quantity_changed',value_change:'10',
        start:{present:true,value:'11',quantity:'1',weight_pct:'1.1'},
        end:{present:true,value:'21',quantity:'2',weight_pct:'2.1'}}],
      cash:[{label:'availableToTrade',start_value:'3',end_value:'1.764322',value_change:'-1.235678',
        start_weight_pct:'0.3',end_weight_pct:'0.18',weight_change_pp:'-0.12',members:[]}],allocations:[],
      top_five:{label:'Top five holdings',start_value:'11',end_value:'21',value_change:'10',
        start_weight_pct:'1.1',end_weight_pct:'2.1',weight_change_pp:'1',
        members:[{ticker:'SYNTH',start_value:'11',end_value:'21'}]},
    })};
  });
  ui.el('changes-tab').listeners.click();
  ui.el('changes-start').value = '2026-11-19';
  ui.el('changes-end').value = date;
  const submit = async () => {
    ui.el('changes-filter').listeners.submit({preventDefault(){}});
    await new Promise(resolve => setImmediate(resolve));
  };
  await submit();
  const results = ui.el('changes-results');
  assert.match(content(results), /No approved Trading 212 snapshot was saved/);
  missing = false;
  await submit();
  assert.match(content(results), /19–20 Nov 2026 UTC/);
  assert.match(content(results), /Quantity changed.*\+£10/s);
  const snapshots = findNode(results, node => node.tag === 'details' &&
    node.children[0]?.textContent === 'Snapshot times and ISA values');
  assert.ok(snapshots && !snapshots.open);
  assert.match(content(snapshots), /3:00pm 20 Nov 2026/);
  const tables = results.children.filter(node => node.className === 'compact-table');
  const holding = findNode(tables[0], node => node.tag === 'tbody').children[0];
  assert.equal(holding.children.length, 4);
  assert.equal(holding.children[1].textContent, '+£10');
  assert.equal(holding.children[1].attributes['data-tone'], 'gain');
  assert.equal(holding.children[2].attributes['data-tone'], undefined);
  const cash = findNode(tables[1], node => node.tag === 'tbody').children[0];
  assert.equal(cash.children[1].textContent, '−£1.24');
  assert.equal(cash.children[1].title, '−£1.235678');
  assert.equal(cash.children[1].attributes['data-tone'], 'loss');
  assert.equal(cash.children[2].attributes['data-tone'], 'loss');
  const link = descendants(results).find(node=>node.href==='#change-holding-0');
  link.listeners.click();
  assert.equal(descendants(results).find(node=>node.id==='change-holding-0').open, true);
  ui.view.clear();
  assert.equal(results.children.length, 0);
});

function findNode(root, predicate) {
  if (predicate(root)) return root;
  for (const child of root.children) {
    const found = findNode(child, predicate);
    if (found) return found;
  }
}
const planningSnapshot = () => ({ ...snapshot(), total_value: '1000' });

test('Projections tab accepts deposits, renders comparisons and shows allocation errors', async () => {
  const starting = planningSnapshot();
  const result = {target_value:'1100',deposits:'100',growth:'0',goal_difference:'-98900',
    series:[{date:'2026-01-02',value:'1000'},{date:'2030-04-30',value:'1100'}],
    schedule:[{date:'2030-04-30',deposit:0}],instructions:[{total:'100',allocations:[{kind:'cash',amount:'100',growth_pct:'0'}]}]};
  let submitted = [];
  const ui = setup(async (path, options) => {
    if (path.endsWith('/snapshot')) return Response.json(starting);
    assert.match(path, /\/projections$/);
    const payload = JSON.parse(options.body);
    submitted.push(payload);
    if (payload.assumptions.plans[0].deposits[0].allocations[0].share === '90') {
      return Response.json({error:'allocation_total_invalid'},{status:422});
    }
    return Response.json({method:'dated_isa_projection_v1',currency:'GBP',capture_time:payload.capture_time,
      opening_growth_pct:'0',goal:'100000',baseline:{...result,target_value:'1000',deposits:'0',schedule:[]},
      plans:[result,{...result,schedule:[]}]});
  }, true);
  ui.document.cookie = '__Host-meridian_csrf=synthetic';
  await ui.view.load();
  ui.el('projections-tab').listeners.click();
  assert.equal(ui.el('projections-panel').hidden, false);
  assert.equal(ui.el('risk-panel').hidden, true);
  const form = ui.el('projections-form');
  findNode(form, node => node.textContent === 'Add deposit').listeners.click();
  const field = label => findNode(form, node => node.textContent === label).children[0];
  field('Deposit amount (GBP)').value = '100';
  field('Date or first month').value = '2030-04-30';
  await form.onsubmit({preventDefault(){}});
  assert.equal(submitted[0].assumptions.plans[0].deposits[0].allocations[0].kind, 'cash');
  assert.match(content(ui.el('projections-capture')), /12:00pm 2 Jan 2026/);
  const projections = ui.el('projections-results');
  assert.match(content(projections), /Plan A.*£1,100.*cash-flow schedule/s);
  assert.ok(findNode(projections, node => node.textContent.endsWith(' gap') && node.attributes['data-tone'] === 'loss'));
  field('Allocation').value = '90';
  form.oninput();
  await form.onsubmit({preventDefault(){}});
  assert.match(ui.el('projections-status').textContent, /add up to 100%/);
  ui.view.clear();
  assert.equal(form.children.length, 0);
});

test('Stress Tests tab compares presets and submits a basket with a holding override', async () => {
  const starting = planningSnapshot();
  Object.assign(starting.positions[0], {instrument_type:'STOCK', current_value:'800', quantity:'1'});
  let assumptions;
  const ui = setup(async (path, options) => {
    if (path.endsWith('/snapshot')) return Response.json(starting);
    assert.match(path, /\/stress-tests$/);
    const payload = JSON.parse(options.body);
    assumptions = payload.assumptions;
    if (assumptions.scenarios.some(scenario => scenario.scope === 'basket' && !scenario.basket.length)) {
      return Response.json({error:'stress_basket_invalid'}, {status:422});
    }
    const row = {scope:'all',price_shock_pct:'-10',stressed_value:'920',impact:'-80',impact_pct:'-8',
      covered_value:'800',covered_pct:'80',covered_holdings:1,uncovered_value:'100',unshocked_marked_value:'0',
      holdings:[{ticker:'SYNTH',opening_value:'800',shock_pct:'-10',impact:'-80',stressed_value:'720'}]};
    return Response.json({method:'direct_isa_stress_v1',currency:'GBP',capture_time:payload.capture_time,
      opening_value:'1000',known_cash:'100',unreconciled_value:'100',total_holdings:1,
      unvalued_holdings:0,ineligible_holdings:0,scenarios:[row,{...row,scope:'basket'}]});
  }, true);
  ui.document.cookie = '__Host-meridian_csrf=synthetic';
  await ui.view.load();
  ui.el('stress-tab').listeners.click();
  assert.equal(ui.el('stress-panel').hidden, false);
  assert.equal(ui.el('projections-panel').hidden, true);
  const form = ui.el('stress-form');
  await form.onsubmit({preventDefault(){}});
  assert.deepEqual(assumptions.scenarios.map(row => row.price_shock_pct), ['-10','-20']);
  const field = label => findNode(form, node => node.textContent === label).children[0];
  const scope = field('Apply shock to');
  scope.value = 'basket';
  scope.listeners.change();
  form.oninput();
  await form.onsubmit({preventDefault(){}});
  assert.match(ui.el('stress-status').textContent, /Select at least one/);
  const selection = field('Include in basket');
  selection.checked = true;
  selection.listeners.change();
  field('Override shock (%)').value = '-5';
  await form.onsubmit({preventDefault(){}});
  assert.deepEqual(assumptions.scenarios[0], {scope:'basket',price_shock_pct:'-10',basket:['SYNTH'],
    overrides:[{ticker:'SYNTH',price_shock_pct:'-5'}]});
  const result = content(ui.el('stress-results'));
  assert.match(result, /Stressed ISA value £920/);
  assert.equal(findNode(ui.el('stress-results'), node => node.textContent === '−8%').attributes['data-tone'], 'loss');
  assert.match(result, /Uncovered value excluding displayed cash £100/);
  assert.match(result, /largest losses.*SYNTH.*−£80/s);
  ui.view.clear();
  assert.equal(form.children.length, 0);
});

test('Meridian refreshes after the 22:02 cutoff even if the snapshot stays unchanged', async () => {
  const meridian = fs.readFileSync(new URL('../signin/meridian.js', import.meta.url), 'utf8');
  const nodes = new Map();
  const document = {
    createElement: tag => new Element(tag),
    getElementById(id) {
      if (!nodes.has(id)) nodes.set(id, new Element());
      return nodes.get(id);
    },
  };
  let now = Date.parse('2026-11-23T22:01:00Z');
  class Clock extends Date { static now() { return now; } }
  let reads = 0;
  const window = {};
  const response = {
    method: 'meridian_common_sample_v1', state: 'insufficient_session_grid',
    price_basis: 'trading212_fixed_cutoff_gbp_price_v1',
    window: 90, n: 0, scheduled: 0, isa: '1000', excluded: [],
  };
  const context = vm.createContext({ window, document, Date: Clock, AbortController,
    fetch: async () => {
      reads++;
      return { ok: true, json: async () => response };
    },
  });
  vm.runInContext(dates, context);
  vm.runInContext(meridian, context);
  const tab = window.meridianDiversification;
  const saved = snapshot();
  const settle = () => new Promise(resolve => setImmediate(resolve));
  tab.setSnapshot(saved);
  tab.setOpen(true);
  await settle();
  tab.setSnapshot(saved);
  await settle();
  assert.equal(reads, 1);
  now = Date.parse('2026-11-23T22:03:00Z');
  tab.setSnapshot(saved);
  await settle();
  tab.setSnapshot(saved);
  await settle();
  assert.equal(reads, 2);
  tab.clear();
});
