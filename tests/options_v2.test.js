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

console.log('options_v2.test.js: all assertions passed');
