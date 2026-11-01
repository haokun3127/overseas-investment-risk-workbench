'use strict';
// Work queues and compact context use existing permissions and business actions.
const webSourceStatuses={unrun:'尚未运行',failed:'最近检索失败',undecided:'未筛选',active:'正在检索',completed:'最近检索完成',scheduled:'已开启定时',manual:'仅手动触发',disabled:'已停用'};
function overviewScope(){
  const scoped=state.auth?.role==='company';
  return `<div class="overview-scope">统计范围：${scoped?'本公司':`全部公司（${state.overviewScope?.company_count??'—'} 家）`}<span>${scoped?'':'背景公司仅用于新分析，不会过滤统计'}</span></div>`;
}
function companyContext(){
  const scoped=state.auth?.role==='company';
  return `<details class="company-context" ${state.company?'':'open'}><summary><span>${scoped?'本公司档案':'新分析背景'}</span><strong>${esc(state.company?.name||'请选择公司')}</strong><span class="context-action">设置${icon('arrow')}</span></summary>${companyPanel({compact:true})}<p class="context-help">${scoped?'公司档案用于本公司的后续分析。':'选择仅影响本会话此后提交、且没有归属公司的资料；已有资料和统计范围不变。'}</p></details>`;
}
function collectionHealth(h){
  if(state.auth?.role!=='admin')return '';
  if(!h)return '<section class="collection-health" aria-label="采集动态"><p>采集状态暂时无法读取，<a href="#websites">前往网站检索重试</a>。</p></section>';
  const elapsed=h.last_success?Date.now()-Date.parse(h.last_success):null;
  const days=elapsed==null?null:Math.max(0,Math.floor(elapsed/86400000));
  const stale=days!=null&&days>=2;
  const queue=(key,label,n)=>`<a href="#websites?status=${key}"><span>${label}</span><strong>${n??0}</strong>${icon('arrow')}</a>`;
  return `<section class="collection-health ${stale?'is-stale':''}" aria-label="采集动态"><div class="collection-health-head"><h2>采集动态</h2><span>${h.active?`${h.active} 个检索任务执行中`:h.scheduled?`${h.scheduled} 个网站已开启定时`:'当前为手动采集'}</span></div><div class="collection-times"><p><span>最近采集成功</span><strong>${h.last_success?when(h.last_success):'尚无成功记录'}</strong>${stale?`<span class="stale-note">已 ${days} 天未更新</span>`:''}</p><p><span>最近分析完成</span><strong>${h.last_analysis?when(h.last_analysis):'尚无分析记录'}</strong></p></div><nav aria-label="采集工作队列">${queue('failed','最近失败',h.latest_failed)}${queue('unrun','未运行',h.unrun)}${queue('undecided','未筛选',h.undecided)}${queue('scheduled','定时网站',h.scheduled)}</nav></section>`;
}
let versionTimer=null,versionDismissed=false;
async function checkRelease(){
  if(document.hidden||$('#shell')?.hidden)return;
  const version=document.querySelector('meta[name=app-version]')?.content;
  if(!version)return;
  try{
    const response=await fetch('api/release',{cache:'no-store',signal:AbortSignal.timeout(10000)});
    if(!response.ok)return;
    const latest=await response.json();
    if(latest.version===version||versionDismissed||$('#release-notice'))return;
    const notice=document.createElement('aside');notice.id='release-notice';notice.className='release-notice';notice.setAttribute('role','status');
    notice.innerHTML='<span>工作台有新版本。请先保存正在编辑的内容，再刷新。</span><button class="primary small" data-release-refresh>刷新版本</button><button class="text-button" data-release-dismiss>稍后</button>';
    document.body.append(notice);
    $('[data-release-refresh]',notice).onclick=()=>location.reload();
    $('[data-release-dismiss]',notice).onclick=()=>{versionDismissed=true;notice.remove();};
  }catch(_error){/* A version check never blocks ongoing business work. */}
}
function bindOperations(){
  if(!versionTimer){versionTimer=setInterval(checkRelease,60000);document.addEventListener('visibilitychange',()=>{if(!document.hidden)checkRelease();});}
}
