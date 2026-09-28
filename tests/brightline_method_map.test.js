const fs=require('fs'), path=require('path');
const root=path.resolve(__dirname,'..');
const wxc=fs.readFileSync(path.join(root,'docs/assets/wenxuecity.js'),'utf8');
const kh=fs.readFileSync(path.join(root,'docs/assets/knowledge.js'),'utf8');
for(const s of ['BrightLine 方法地图','Survival first','先建立 thesis','概率题','AI 是研究助手','网站：5步决策链','BrightLine 2026 覆盖进度','重复观点自动合并']){
  if(!wxc.includes(s)) throw new Error('missing wenxuecity framework marker: '+s);
}
for(const s of ["process:'决策流程'",'普通投资者的决策流程','Trend Pulse 负责告诉你价格行为','杠杆最后讨论','BrightLine方法地图']){
  if(!kh.includes(s)) throw new Error('missing knowledge workflow marker: '+s);
}
console.log('brightline_method_map.test.js: all assertions passed');
