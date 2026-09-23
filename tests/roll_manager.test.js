const fs=require('fs'),vm=require('vm'),assert=require('assert');
vm.runInThisContext(fs.readFileSync('docs/assets/roll-manager.js','utf8'));

const R=globalThis.RollManager;
assert.strictEqual(R.classifyRoll({delta:.3376,observation:'close',dte:87}).key,'hold');
assert.strictEqual(R.classifyRoll({delta:.74,observation:'intraday',dte:60}).key,'intraday','Intraday Delta must not trigger the close-based discipline');
assert.strictEqual(R.classifyRoll({delta:.74,observation:'close',watchCloses:1,dte:60}).key,'watch');
assert.strictEqual(R.classifyRoll({delta:.74,observation:'close',watchCloses:2,dte:60}).key,'roll');
assert.strictEqual(R.classifyRoll({delta:.74,observation:'close',catalyst:true,dte:60}).key,'catalyst');
assert.strictEqual(R.classifyRoll({delta:.81,observation:'close',dte:60}).key,'urgent');
assert.strictEqual(R.classifyRoll({delta:-.81,observation:'close',dte:60}).key,'urgent','Sell Put must use absolute Delta');
assert.strictEqual(R.classifyRoll({delta:-.55,observation:'close',dte:60,optionType:'put',assignmentMode:'accept',watch:.50,urgent:.70}).key,'put_watch','A cash-secured put willing to accept assignment should show assignment risk, not a mandatory roll');
assert.strictEqual(R.classifyRoll({delta:-.75,observation:'close',dte:60,optionType:'put',assignmentMode:'accept',watch:.50,urgent:.70}).key,'assignment','High put Delta must present assignment versus roll as a choice');
assert.strictEqual(R.classifyRoll({delta:-.75,observation:'close',dte:60,optionType:'put',assignmentMode:'avoid',watch:.50,urgent:.70}).key,'urgent','Avoid-assignment mode should escalate high absolute put Delta');
assert.strictEqual(R.classifyRoll({delta:.22,observation:'close',dte:4}).key,'expiry');

const initial=R.rollMath({type:'call',oldStrike:65,newStrike:65,oldExpiry:'2026-12-18',newExpiry:'2026-12-18',closeDebit:0,openCredit:0,qty:3,multiplier:100,priorPremium:3.85});
assert(Math.abs(initial.effectivePrice-68.85)<1e-9,'IREN initial effective sale price must be 65 + 3.85');
const rolled=R.rollMath({type:'call',oldStrike:65,newStrike:70,oldExpiry:'2026-12-18',newExpiry:'2027-01-15',closeDebit:8,openCredit:6,closeFee:1.95,openFee:1.95,qty:3,multiplier:100,priorPremium:3.85});
assert(Math.abs(rolled.netCash+603.9)<1e-9,'Roll net debit must include 300x and both fees');
assert(rolled.addedDays===28&&rolled.strikeChange===5);
assert(Math.abs(rolled.effectivePrice-(70+3.85-2-3.9/300))<1e-9);
const put=R.rollMath({type:'put',oldStrike:40,newStrike:35,oldExpiry:'2026-10-16',newExpiry:'2026-11-20',closeDebit:5,openCredit:4,qty:1,multiplier:100,priorPremium:3});
assert(Math.abs(put.effectivePrice-33)<1e-9,'Sell Put basis must be strike minus cumulative net premium');

const c=R.coverage(600,[{side:'Short',opt_type:'Call',collateral_mode:'covered',qty:3,multiplier:100},{side:'Short',opt_type:'Put',collateral_mode:'cash_secured',qty:2,multiplier:100}]);
assert.deepStrictEqual(c,{shares:600,contractShares:300,covered:300,uncovered:300,excess:0});
assert.deepStrictEqual(R.parseTranches('65-70:50%\n75-80:50%'),[{low:65,high:70,pct:50},{low:75,high:80,pct:50}]);

console.log('roll_manager.test.js: all assertions passed');
