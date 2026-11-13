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
  const document={getElementById(id){if(!elements.has(id))elements.set(id,new Element());return elements.get(id);},createElement(){return new Element();},createDocumentFragment(){const e=new Element();e.fragment=true;return e;},body:{classList:{add(){},remove(){}}}};
  vm.runInNewContext(source,{document,window,fetch:fetcher,AbortController,Event,BigInt,Date});
  return {view:window.meridianSnapshot,el:id=>document.getElementById(id),window};
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
