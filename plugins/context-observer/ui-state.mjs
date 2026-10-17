export function sortRows(rows) {
  return [...rows].sort((a,b)=>{
    const av=a.status==='estimate' && Number.isFinite(a.tokens) ? a.tokens : -1;
    const bv=b.status==='estimate' && Number.isFinite(b.tokens) ? b.tokens : -1;
    return bv-av || a.label.localeCompare(b.label,'en-US');
  });
}
export function relativeAge(time, now=Date.now()) {
  const stamp=typeof time==='number'?time:Date.parse(time);
  if(!Number.isFinite(stamp)) return 'not recorded';
  const seconds=Math.max(0,Math.floor((now-stamp)/1000));
  if(seconds<2) return 'just now';
  if(seconds<60) return `${seconds} s ago`;
  if(seconds<3600) return `${Math.floor(seconds/60)} min ago`;
  if(seconds<86400) return `${Math.floor(seconds/3600)} h ago`;
  return `${Math.floor(seconds/86400)} days ago`;
}
export function versionState(ui, plugin) {
  const running=plugin?.runningVersion;
  const installed=plugin?.installedVersion;
  return {mismatch:!!running && ui!==running, pending:!!installed && installed!==running};
}
