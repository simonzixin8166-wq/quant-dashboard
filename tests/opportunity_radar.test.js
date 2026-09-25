const assert=require('assert');
const {filterContracts,dte}=require('../docs/assets/opportunity-radar.js');

const now=new Date('2026-01-01T12:00:00Z');
const rows=[
  {expiration:'2027-07-18',strike:500,bid:20,ask:21,mid:20.5,delta:.55,iv:.25},
  {expiration:'2027-07-18',strike:520,bid:10,ask:13,mid:11.5,delta:.56,iv:.26},
  {expiration:'2027-07-18',strike:450,bid:40,ask:41,mid:40.5,delta:.76,iv:.24},
  {expiration:'2026-06-18',strike:500,bid:20,ask:21,mid:20.5,delta:.55,iv:.25},
];
assert(dte('2027-07-18',now)>540);
const growth=filterContracts(rows,'growth',now);
assert.strictEqual(growth.length,1);
assert.strictEqual(growth[0].strike,500);
const replacement=filterContracts(rows,'replacement',now);
assert.strictEqual(replacement.length,1);
assert.strictEqual(replacement[0].strike,450);
console.log('opportunity_radar.test.js: all assertions passed');
