import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';
const source=readFileSync('plugins/context-observer/bridge.js','utf8').replace("import {App} from '@modelcontextprotocol/ext-apps';",'');
let app, response, requests=[];
class App {
  constructor(){app=this;}
  connect(){return Promise.resolve();}
  callServerTool(request){requests.push(request);return Promise.resolve(response);}
}
const window={dispatchEvent(){}};
vm.runInNewContext(source,{App,window,Event,setTimeout,clearTimeout});
const result=(threadId,binding,count)=>({_meta:{binding,snapshot:{threadId,count}}});
app.ontoolresult(result('A','binding-A',1));
assert.equal((await window.readContextSnapshot()).threadId,'A');
app.ontoolresult(result('B','binding-B',99));
response=result('A','binding-A',2);
assert.equal((await window.readContextSnapshot()).count,2);
assert.deepEqual(requests.at(-1).arguments.binding,'binding-A');
response=result('B','binding-B',99);
await assert.rejects(()=>window.readContextSnapshot(),/outra conversa/);
response=result('A','binding-A',3);
assert.equal((await window.readContextSnapshot()).count,3);
assert.equal(window.rebindContext,undefined);
console.log('Bridge: vínculo original preservado, atualizações recebidas e outra conversa rejeitada.');
