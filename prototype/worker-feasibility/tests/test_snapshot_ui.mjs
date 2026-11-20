import assert from 'node:assert/strict';
import test from 'node:test';
import vm from 'node:vm';
import fs from 'node:fs';
const source=fs.readFileSync(new URL('../signin/snapshot.js',import.meta.url),'utf8');
class Element {
  constructor(){this.textContent='';this.value='';this.children=[];this.listeners={};this.attributes={};}
  append(child){this.children.push(child);}
  replaceChildren(...children){this.children=children.flatMap(child=>child.fragment?child.children:[child]);}
  addEventListener(name,fn){this.listeners[name]=fn;}
  setAttribute(name,value){this.attributes[name]=value;}
}
function setup(fetcher){
  const elements=new Map();const window=new EventTarget();
  let now = 1_000_000, nextTimer = 0;
  const timers = new Map(), events = {};
  class Clock extends Date { constructor(...args){super(...(args.length ? args : [now]));} static now(){return now;} }
  const setTimeout = (fn, delay) => {const id=++nextTimer;timers.set(id,{fn,at:now+delay,delay});return id;};
  const clearTimeout = id => timers.delete(id);
  const document={hidden:false,addEventListener(name,fn){events[name]=fn;},getElementById(id){if(!elements.has(id))elements.set(id,new Element());return elements.get(id);},createElement(){return new Element();},createDocumentFragment(){const e=new Element();e.fragment=true;return e;},body:{classList:{add(){},remove(){}}}};
  vm.runInNewContext(source,{document,window,fetch:fetcher,AbortController,Event,BigInt,Date:Clock,setTimeout,clearTimeout});
  return {view:window.meridianSnapshot,el:id=>document.getElementById(id),window,timers,document,
    advance(ms){now+=ms;},
    async tick(ms){now+=ms;for(const [id,timer] of [...timers])if(timer.at<=now){timers.delete(id);await timer.fn();}},
    async visibility(hidden){document.hidden=hidden;await events.visibilitychange();await new Promise(resolve=>setImmediate(resolve));}
  };
}
function snapshot(){return {source:'trading212',basis:'broker_reported',environment:'demo',currency:'GBP',total_value:'9007199254740993.123456789',investments:{currentValue:'99',totalCost:'11',unrealizedProfitLoss:'2'},cash_components:{availableToTrade:'7'},account_retrieval:{retrieval_completed_at:'2026-01-02T12:00:00Z'},positions_retrieval:{retrieval_completed_at:'2026-01-02T12:00:01Z'},positions:[{name:'<img src=x>',ticker:'SYNTH',quantity:'0.00000000000000001',current_value:'10',account_currency:'GBP',instrument_currency:'USD',current_price:'12.34'}]};}
test('broker total stays exact; values missing remain unavailable and names are literal text',async()=>{
 const ui=setup(async()=>({ok:true,status:200,json:async()=>snapshot()}));await ui.view.load();
 assert.equal(ui.el('total-value').textContent,'£9,007,199,254,740,993.123456789');
 assert.equal(ui.el('cash-in-pies').textContent,'Unavailable');
 assert.equal(ui.el('holdings-body').children[0].children[0].textContent,'<img src=x>');
 ui.el('holding-search').value='absent';ui.el('holding-search').listeners.input();
 assert.equal(ui.el('holdings-body').children.length,0);
 ui.view.clear();assert.equal(ui.el('total-value').textContent,'—');assert.equal(ui.el('holdings-body').children.length,0);
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
 let reads=0;
 const ui=setup(async path=>{reads++;assert.equal(path,'/api/v1/portfolio/snapshot');return {ok:true,status:200,json:async()=>({...snapshot(),refresh_health:{jobs:{snapshot:{stale:false}}}})};});
 ui.view.start();await new Promise(resolve=>setImmediate(resolve));
 assert.equal(reads,1);assert.equal([...ui.timers.values()][0].delay,600_000);
 await ui.tick(599_999);assert.equal(reads,1);
 await ui.tick(1);assert.equal(reads,2);
 await ui.visibility(true);assert.equal(ui.timers.size,0);
 await ui.tick(600_000);assert.equal(reads,2);
 await ui.visibility(false);assert.equal(reads,3);
 ui.view.clear();await ui.tick(600_000);assert.equal(reads,3);
});
test('outage backoff resists reload and visibility storms and retains last-good values',async()=>{
 let reads=0, fail=false;
 const ui=setup(async()=>{reads++;return fail?{ok:false,status:503}:{ok:true,status:200,json:async()=>snapshot()};});
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
 const ui=setup(async(path,options)=>{if(options?.method==='POST'){posts++;return {ok:true,status:202,json:async()=>({status:'queued'})};}reads++;return {ok:true,status:200,json:async()=>snapshot()};});
 ui.view.start();await new Promise(resolve=>setImmediate(resolve));
 ui.document.cookie='__Host-meridian_csrf=synthetic';
 await ui.el('refresh-broker').listeners.click();await ui.el('refresh-broker').listeners.click();
 assert.equal(posts,1);assert.equal(reads,1);
 await ui.tick(60_000);assert.equal(reads,2);
});

test('failed manual request pauses further manual and saved-snapshot requests',async()=>{
 let calls=0;
 const ui=setup(async(path,options)=>{calls++;return options?.method==='POST'?{ok:false,status:503}:{ok:true,status:200,json:async()=>snapshot()};});
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
  const missing = {value:null,portfolio_pct:null,invested_pct:null};
  data.exposures = {
    account_as_of:data.account_retrieval.retrieval_completed_at,
    positions_as_of:data.positions_retrieval.retrieval_completed_at,
    invested_denominator:'99',portfolio_denominator:data.total_value,
    observed_holdings:observed,missing_values:1,
    holdings:[{ticker:'SYNTH',quote_currency:'USD',...observed},{ticker:'MISSING',quote_currency:null,...missing}],
    quote_currencies:[{quote_currency:'USD',missing_values:0,...observed},{quote_currency:null,missing_values:1,...missing}],
    concentration:[{top:1,position_count:1,...missing}],
    sectors:{classified:observed,observed,sources:{SYNTH:{as_of:'2026-01-01',url:'https://example.test/fact'}},
      buckets:[{label:'Industrials',...observed,members:{SYNTH:{value,holding_pct:'50'}}}]},
    issuer_domiciles:{classified:missing,observed,sources:{},
      buckets:[{label:null,...observed,members:{SYNTH:{value,holding_pct:'100'},MISSING:{value:null,holding_pct:'100'}}}]},
    cash_component_pct:{availableToTrade:'0',inPies:null,reservedForOrders:null},
  };
  const ui = setup(async () => ({ok:true,status:200,json:async()=>data}));
  await ui.view.load();
  const section = ui.el('portfolio-exposures');
  const find = (node, value) => node.textContent === value ? node
    : node.children.map(child => find(child, value)).find(Boolean);
  assert.ok(find(section, '£10.000000000000000000001'));
  assert.ok(find(section, '10.1%'));
  assert.ok(find(section, 'Largest position'));
  assert.ok(find(section, 'Equity sectors'));
  ui.el('exposures-tab').listeners.click();
  assert.equal(section.hidden,false);
  find(section, 'Industrials').listeners.click();
  const contributing = ui.el('holdings-body').children[0];
  assert.ok(find(contributing, 'Bucket contribution: £10.000000000000000000001 · 50% of position'));
  assert.equal(find(contributing, 'Source · 2026-01-01').href, 'https://example.test/fact');
  find(section, 'Unclassified quote currency').listeners.click();
  assert.equal(ui.el('holdings-panel').hidden,false);
  assert.equal(ui.el('holdings-body').children.length,1);
  assert.equal(ui.el('holdings-body').children[0].children[0].textContent,'Missing Wallet');
  find(section, 'USD').listeners.click();
  assert.equal(ui.el('holdings-body').children[0].children[5].textContent,'10.1%');
  find(section, 'Unclassified').listeners.click();
  assert.equal(ui.el('holdings-body').children.length,2);
  ui.el('clear-holding-scope').listeners.click();
  assert.equal(ui.el('holding-scope').hidden,true);
  ui.view.clear();
  assert.equal(section.children.length,0);
  assert.equal(ui.el('holdings-body').children.length,0);
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
 ui.el('history-chart').getContext=()=>ctx;
 ui.el('history-tab').listeners.click();
 await new Promise(resolve=>setImmediate(resolve));
 assert.equal(reads,1);
 assert.equal(lines,1);
 assert.match(ui.el('history-status').textContent,/3 of 90 days observed · 87 missing/);
 assert.match(ui.el('history-point').textContent,/£9,007,199,254,740,993.123456789.*11:22:33 UTC.*11:22:34 UTC/);
 assert.equal(ui.el('history-body').children.length,90);
 assert.equal(ui.el('history-body').children[1].children[1].textContent,'No saved snapshot');
 ui.el('history-chart').listeners.keydown({key:'ArrowLeft',preventDefault(){}});
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
