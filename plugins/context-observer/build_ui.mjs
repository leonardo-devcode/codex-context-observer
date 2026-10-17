import {build} from 'esbuild';
import {readFile,writeFile} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
const root=fileURLToPath(new URL('.',import.meta.url));
const version=JSON.parse(await readFile(root+'.codex-plugin/plugin.json','utf8')).version;
const bundled=await build({entryPoints:[root+'panel-entry.js'],bundle:true,minify:true,format:'iife',platform:'browser',write:false,
  plugins:[{name:'plugin-version',setup(build){build.onLoad({filter:/bridge\.js$/},async args=>({contents:(await readFile(args.path,'utf8')).replaceAll('__PLUGIN_VERSION__',version),loader:'js'}));}}]});
const source=bundled.outputFiles[0].text;
const template=await readFile(root+'template.html','utf8');
await writeFile(root+'panel.html',template.replace('__PLUGIN_SCRIPT__',()=>source.replaceAll('</script','<\\/script')));
