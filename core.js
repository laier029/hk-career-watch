(function(root){
  'use strict';
  const empty = () => ({version:2, jobs:{}});
  const fields = ['read_at','saved_at','applied_at','dismissed_at'];
  function parseState(value){
    if(!value || ![1,2].includes(value.version)) throw Error('不是有效的岗位记录备份');
    const source=value.version===1?value.read:value.jobs;
    if(!source || typeof source!=='object' || Array.isArray(source) || Object.keys(source).length>100000) throw Error('记录格式或大小不正确');
    const state=empty();
    for(const [id,raw] of Object.entries(source)){
      if(!/^[a-f0-9]{24}$/.test(id))throw Error('岗位 ID 无效');
      const row=value.version===1?{read_at:raw}:raw;
      if(!row || typeof row!=='object' || Array.isArray(row))throw Error('状态格式不正确');
      state.jobs[id]={};
      for(const [k,v] of Object.entries(row)){
        if(!fields.includes(k) || typeof v!=='string' || !/^\d{4}-\d{2}-\d{2}T/.test(v) || !Number.isFinite(Date.parse(v)))throw Error('状态日期或字段不正确');
        state.jobs[id][k]=v;
      }
    }
    return state;
  }
  function combine(a,b){
    const result=parseState(a);
    for(const [id,row] of Object.entries(parseState(b).jobs)){
      result.jobs[id]||={};
      for(const [k,v] of Object.entries(row))if(!result.jobs[id][k] || v>result.jobs[id][k])result.jobs[id][k]=v;
    }
    return result;
  }
  function migrate(state,jobs){
    const result=parseState(state),targets={};
    for(const job of jobs)for(const alias of job.legacy_ids||[])(targets[alias]||=[]).push(job.id);
    let ambiguous=0;
    for(const [alias,ids] of Object.entries(targets)){
      if(!result.jobs[alias])continue;
      if(ids.length!==1 || jobs.some(j=>j.id===alias)){ambiguous++;continue;}
      result.jobs[ids[0]]=combine({version:2,jobs:{[ids[0]]:result.jobs[ids[0]]||{}}},{version:2,jobs:{[ids[0]]:result.jobs[alias]}}).jobs[ids[0]];
      delete result.jobs[alias];
    }
    return {state:result,ambiguous};
  }
  function isExpired(job,today){return ['archived','expired'].includes(job.state)||Boolean(job.deadline&&job.deadline<today);}
  function updated(job,row){return Boolean(job.changed_at && (!row.read_at || Date.parse(job.changed_at)>Date.parse(row.read_at)));}
  function needsReview(job){return ['review','recheck'].includes(job.state);}
  function matches(job,filter,state,today,since){
    const row=state.jobs[job.id]||{},expired=isExpired(job,today);
    if(filter.track!=='all' && job.track!==filter.track)return false;
    if(filter.category && job.category!==filter.category)return false;
    if(filter.tags?.length && !filter.tags.some(t=>job.role_tags?.includes(t)))return false;
    if(filter.watchlist==='yes'&&!job.watchlist || filter.watchlist==='no'&&job.watchlist)return false;
    if(filter.origin && job.origin!==filter.origin)return false;
    if(filter.source && !(job.sources||[]).some(s=>s.name.includes(filter.source)))return false;
    if(filter.search && !(job.company+' '+job.title).toLowerCase().includes(filter.search.toLowerCase()))return false;
    if(filter.status==='read'&&!row.read_at || filter.status==='unread'&&row.read_at || filter.status==='dismissed'&&!row.dismissed_at)return false;
    switch(filter.tab){
      case 'saved':if(!row.saved_at)return false;break;
      case 'applied':if(!row.applied_at)return false;break;
      case 'review':if(!needsReview(job)||row.dismissed_at||expired)return false;break;
      case 'pending':if(expired||job.state==='excluded'||needsReview(job)||row.dismissed_at||row.applied_at||(row.read_at&&!updated(job,row)))return false;break;
      default:if(!filter.history && (expired||job.state==='excluded'||row.dismissed_at))return false;
    }
    if(filter.quick==='new' && !((job.first_seen||'')>since || updated(job,row)))return false;
    if(filter.quick==='closing' && !(job.deadline&&job.deadline>=today&&Date.parse(job.deadline)-Date.parse(today)<=7*86400000))return false;
    return true;
  }
  function rank(job,state,today,since){
    const row=state.jobs[job.id]||{};
    if((job.first_seen||'')>since || updated(job,row))return 0;
    if(job.deadline&&job.deadline>=today&&Date.parse(job.deadline)-Date.parse(today)<=7*86400000)return 1;
    return 2;
  }
  function sort(jobs,state,today,since){return [...jobs].sort((a,b)=>rank(a,state,today,since)-rank(b,state,today,since) || Number(!a.role_tags?.length)-Number(!b.role_tags?.length) || (b.first_seen||'').localeCompare(a.first_seen||'') || a.title.localeCompare(b.title));}
  function action(state,ids,field,at){
    if(!fields.includes(field))throw Error('Unknown action');
    const next=parseState(state);
    for(const id of ids){next.jobs[id]||={};if(at)next.jobs[id][field]=at;else delete next.jobs[id][field];}
    return next;
  }
  function safeUrl(value){try{const u=new URL(value);return ['https:','http:'].includes(u.protocol)?u.href:null;}catch{return null;}}
  const api={empty,parseState,combine,migrate,isExpired,updated,needsReview,matches,sort,action,safeUrl};
  if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.JobCore=api;
})(typeof window==='undefined'?globalThis:window);
