// Local synthetic integration helper; no HTTP route or deployed entrypoint.
import fs from 'node:fs';
import { createCashReconciler } from '../src/cash_reconciliation_adapter.mjs';
import { summarizeCashReport, summarizeActivityDetails } from '../src/cash_reconciliation_summary.mjs';
const input=fs.readFileSync(0,'utf8');
const module=new WebAssembly.Module(fs.readFileSync(new URL('../src/reconciliation_wasm/axis_reconciliation_bg.wasm',import.meta.url)));
const report=createCashReconciler(module)(input);
process.stdout.write(JSON.parse(input).detail_query ? summarizeActivityDetails(report,'live') : await summarizeCashReport(input,report,'live'));
