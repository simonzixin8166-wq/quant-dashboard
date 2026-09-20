const fs=require('fs'),vm=require('vm'),assert=require('assert');
vm.runInThisContext(fs.readFileSync('docs/assets/options-v2.js','utf8'));

const base={strategy:'SELL_PUT',spot:42.62,strike:40,premium:3.5,qty:1,multiplier:100,targetSpot:0,iv:.60,ivChange:0,fee:.65,rate:.042,dividend:0,dte:43,forwardDays:43};
const expiry=globalThis.OptionV2.evaluate(base);
assert(Math.abs(expiry.maxProfit-348.70)<.01,'Sell Put maximum profit must include 100x and fees');
assert(Math.abs(expiry.maxLoss-3651.30)<.01,'Sell Put maximum loss must include 100x and fees');
assert(Math.abs(expiry.breakeven-36.50)<.001,'Sell Put break-even is per-share price');
assert(Math.abs(expiry.netPnl+3651.30)<.01,'Expiry loss at zero must equal maximum loss');

const qty2=globalThis.OptionV2.evaluate({...base,qty:2,targetSpot:50});
assert(qty2.positionValue>=0,'Position value must be non-negative');
assert(Math.abs(qty2.maxProfit-697.40)<.01,'Quantity must scale total dollars');

const covered=globalThis.OptionV2.evaluate({...base,strategy:'COVERED_CALL',strike:45,stockCost:40,targetSpot:50,forwardDays:43});
assert(Number.isFinite(covered.maxLoss),'Covered Call cannot be treated as naked unlimited loss');
assert(covered.grossPnl>0,'Covered Call must include the stock leg');

const held={symbol:'LITE',expiry:'2026-11-20',opt_type:'Put',side:'Short',strike:660,cost:33.48,qty:1};
assert.strictEqual(globalThis.OptionV2.occSymbol(held),'LITE261120P00660000','OCC symbol must preserve strike ×1000');
const heldMetrics=globalThis.OptionV2.positionMetrics(held,{bid:34.9,ask:43.2,mid:39.05,last:40});
assert(Math.abs(heldMetrics.mark-43.2)<.001,'Short position must use Ask as conservative close price');
assert(Math.abs(heldMetrics.pnl+972)<.01,'Existing position P&L must use saved entry cost ×100');
assert(Math.abs(heldMetrics.breakeven-626.52)<.001,'Saved short put break-even must use actual entry cost');

const customMultiplier=globalThis.OptionV2.positionMetrics({...held,multiplier:10},{bid:30,ask:32,mid:31,last:31});
assert(Math.abs(customMultiplier.pnl-14.8)<.01,'Saved contract multiplier must be respected instead of always forcing 100');
const expiredRisk=globalThis.OptionV2.positionRisk({...held,expiry:'2000-01-01'},null);
assert.strictEqual(expiredRisk.level,'danger','Expired positions must be marked pending settlement, never safe');
const wideSpreadRisk=globalThis.OptionV2.positionRisk({...held,expiry:'2099-01-01'},{underlyingPrice:800,bid:10,ask:20,mid:15});
assert.strictEqual(wideSpreadRisk.level,'warn','Wide bid/ask spreads must trigger a liquidity warning');

console.log('options_v2.test.js: all assertions passed');
