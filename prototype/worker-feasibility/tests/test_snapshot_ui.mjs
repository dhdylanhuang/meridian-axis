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
