const fs=require('fs');const path=require('path');
const root=path.resolve(__dirname,'..');
const lib=fs.readFileSync(path.join(root,'docs/assets/research-methods.js'),'utf8');
const ui=fs.readFileSync(path.join(root,'docs/assets/wenxuecity.js'),'utf8');
for(const s of ['没有可证明的优势时，指数优先','Survival > Timing','期权是表达工具','AI要连接真实数据']) if(!lib.includes(s)) throw new Error('missing method: '+s);
for(const s of ['投资助手','专业指标怎么理解','普通投资者怎么做','什么时候重新判断']) if(!ui.includes(s)) throw new Error('missing assistant UI: '+s);
console.log('research assistant: all assertions passed');
