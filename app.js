(function(){
 'use strict';
 const C=window.JobCore,D=window.JOB_DATA,$=id=>document.getElementById(id);
 const base='hk-career-watch:',path=location.pathname.replace(/index\.html$/,''),key=base+'state:v2:'+path,oldKey=base+'read:v1:'+path,filterKey=base+'filters:v2:'+path,visitKey=base+'checked:v2:'+path;
 const defaults={track:'supply',tab:'pending',category:'',tags:[],search:'',watchlist:'',origin:'',source:'',status:'',history:false,quick:''};
 const tabs=[['pending','待查看'],['saved','收藏'],['applied','已投递'],['review','待核实'],['all','全部岗位']];
 const cats=[['','所有类型'],['daily','日常实习'],['holiday','寒暑假实习'],['graduate','毕业项目']];
 const tags={procurement:'采购与寻源',planning:'计划与库存',logistics:'物流与履约',analytics:'供应链分析与运营'};
 const seasons={winter:'寒假',summer:'暑假',both:'寒 / 暑皆可',none:''};
 let state=C?C.empty():{},filter={...defaults},selected=new Set(),undo=null,since='',storageOK=true;
 const today=()=>new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Hong_Kong',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
 const el=(tag,text,cls)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;};
 const button=(label,fn,pressed)=>{const b=el('button',label);b.type='button';if(pressed!==undefined)b.setAttribute('aria-pressed',String(pressed));b.addEventListener('click',fn);return b;};
 const date=s=>s?new Date(s).toLocaleString('zh-CN',{timeZone:'Asia/Hong_Kong',hour12:false}):'未确认';
 const error=s=>{$('error').textContent=s;$('error').hidden=!s;};
 function load(){try{const raw=localStorage.getItem(key),old=localStorage.getItem(oldKey);const migrated=C.migrate(raw?C.parseState(JSON.parse(raw)):old?C.parseState(JSON.parse(old)):C.empty(),D.jobs);state=migrated.state;if(migrated.ambiguous)error(migrated.ambiguous+' 条旧记录有 ID 歧义，已保留未自动迁移。');storageOK=true;return true;}catch{storageOK=false;error('本地记录未能读取。为保护原记录，暂停状态写入；请使用已有备份恢复。');return false;}}
 function save(next){if(!storageOK)return false;try{localStorage.setItem(key,JSON.stringify(next));state=next;return true;}catch{error('记录无法保存，本次操作未生效。请检查浏览器存储空间。');return false;}}
 function notify(message,canUndo=false){$('toast-text').textContent=message;$('undo').hidden=!canUndo;$('toast').hidden=false;}
 function change(ids,field,remove=false){if(!load())return;const previous=JSON.parse(JSON.stringify(state));const next=C.action(state,ids,field,remove?null:new Date().toISOString());if(save(next)){undo={previous,ids};selected.clear();render();notify('已更新 '+ids.length+' 条岗位记录',true);}}
 function setFilter(patch){filter={...filter,...patch};selected.clear();try{localStorage.setItem(filterKey,JSON.stringify(filter));}catch{error('筛选设置不能保存；仍可在当前页面使用。');}render();}
 function link(label,url){const safe=C.safeUrl(url);if(!safe)return el('span','链接不可用');const a=el('a',label);a.href=safe;a.target='_blank';a.rel='noopener noreferrer';return a;}
 function badge(label,cls=''){return el('span',label,'badge '+cls);}
 function showTabs(id,choices,value,fn,count){$(id).replaceChildren(...choices.map(([v,label])=>{const b=button(label,()=>fn(v),v===value);if(count)b.append(el('span',String(count(v)),'count'));return b;}));}
 const short=(text,len)=>text.length>len?text.slice(0,len)+'…':text;
 function item(job){
   const row=state.jobs[job.id]||{},article=el('article',undefined,'job'),select=el('input');article.dataset.id=job.id;select.type='checkbox';select.checked=selected.has(job.id);select.setAttribute('aria-label','选中 '+job.title);select.addEventListener('change',()=>{select.checked?selected.add(job.id):selected.delete(job.id);batch();});article.append(select);
   const main=el('div');main.append(el('div',job.company+(job.watchlist?' · 重点雇主':''),'company'),el('div',job.title,'job-title'));
   if(C.updated(job,row))main.append(badge('有重要更新','new'));else if(job.first_seen>since)main.append(badge('新发现','new'));
   for(const tag of job.role_tags||[])main.append(badge(tags[tag]));main.append(badge(cats.find(x=>x[0]===job.category)?.[1]||job.category));if(seasons[job.season])main.append(badge(seasons[job.season]));
   if(C.needsReview(job))main.append(badge(job.state==='recheck'?'待复查':'待核实','warn'));
   if(C.isExpired(job,today()))main.append(badge('已归档','warn'));if(job.state==='excluded')main.append(badge('已排除','warn'));
   article.append(main);
   const timing=el('div',undefined,'dates'),start=job.timing?.start,duration=job.timing?.duration;
   timing.append(el('div',start?'入职 · '+short(start,70):'入职 · 未注明'),el('div',duration?'时长 · '+short(duration,65):'时长 · 未注明'),el('div',job.deadline?'截止 · '+job.deadline:'发现 · '+(job.first_seen||'').slice(0,10)));article.append(timing);
   const actions=el('div',undefined,'actions'),open=link('查看原岗位 ↗',job.url);open.className='open';actions.append(open);
   actions.append(button(row.read_at&&!C.updated(job,row)?'恢复未读':'已读',()=>change([job.id],'read_at',Boolean(row.read_at&&!C.updated(job,row)))));
   actions.append(button(row.saved_at?'★ 已收藏':'☆ 收藏',()=>change([job.id],'saved_at',Boolean(row.saved_at)),Boolean(row.saved_at)));
   const menu=el('details'),summary=el('summary','更多'),menuBody=el('div',undefined,'menu');menuBody.append(button(row.applied_at?'取消已投递':'已投递',()=>change([job.id],'applied_at',Boolean(row.applied_at))),button(row.dismissed_at?'恢复合适':'不合适',()=>change([job.id],'dismissed_at',Boolean(row.dismissed_at))));menu.append(summary,menuBody);actions.append(menu);article.append(actions);
   const detail=el('details',undefined,'job-detail');detail.append(el('summary','要求、匹配依据与检查记录'));
   const content=el('div',undefined,'detail-content');
   function group(heading,lines){content.append(el('h4',heading));const ul=el('ul');for(const value of lines)ul.append(el('li',value));content.append(ul);}
   group('匹配依据',job.match_evidence?.length?job.match_evidence:['未取得明确职责']);
   group('需要核对',job.review_reasons?.length?job.review_reasons:['未发现明显资格冲突；最终以官网要求为准']);
   group('资格原文摘要',job.requirements?.length?job.requirements:['毕业要求 / 语言 / 工作许可：未注明']);
   group('项目时间与其他要求',['地点：'+(job.location||'待确认'),'入职：'+(start||'未注明'),'时长：'+(duration||'未注明'),'每周工作：'+(job.timing?.days||'未注明')]);
   group('发现与验证',['首次发现：'+date(job.first_seen),'来源发布日期：'+(job.posted||'未注明'),'最后发现：'+date(job.last_seen),'最后官网确认：'+date(job.last_verified),'重要变更：'+date(job.changed_at)]);
   content.append(el('h4','所有发现来源'));
   for(const source of job.sources||[{name:job.source,url:job.url}]){const p=el('p');p.append(link(source.name,source.url),document.createTextNode(' · '+date(source.seen_at)));content.append(p);}
   if(job.note)content.append(el('p',job.note));detail.append(content);article.append(detail);return article;
 }
 function batch(){const visibleIDs=[...$('jobs').querySelectorAll('article input[type=checkbox]')];$('batch-read').disabled=!selected.size;$('batch-read').textContent=selected.size?selected.size+' 项标为已读':'选中项标为已读';$('select-all').checked=visibleIDs.length>0&&visibleIDs.every(x=>x.checked);$('select-all').indeterminate=selected.size>0&&!$('select-all').checked;}
 function render(){
   const focused=document.activeElement,focusParent=focused?.parentElement?.id,focusText=focused?.textContent,day=today();
   const oldRow=focused?.closest('article.job'),oldIndex=oldRow?[...$('jobs').children].indexOf(oldRow):-1,actionIndex=oldRow?[...oldRow.querySelectorAll('button')].indexOf(focused):-1;
   const match=(j,f=filter)=>C.matches(j,f,state,day,since);
   showTabs('tracks',[['supply','供应链'],['business','其他商科']],filter.track,v=>setFilter({track:v,tags:[]}));
   showTabs('tabs',tabs,filter.tab,v=>setFilter({tab:v,status:'',quick:''}),v=>D.jobs.filter(j=>match(j,{...filter,tab:v,status:'',quick:''})).length);
   showTabs('categories',cats,filter.category,v=>setFilter({category:v}));
   $('tags').replaceChildren(...Object.entries(tags).map(([v,label])=>button(label,()=>setFilter({tags:filter.tags.includes(v)?filter.tags.filter(x=>x!==v):[...filter.tags,v]}),filter.tags.includes(v))));$('tags').hidden=filter.track!=='supply';
   for(const name of ['search','watchlist','origin','source','status'])if($(name).value!==filter[name])$(name).value=filter[name];$('history').checked=filter.history;
   $('filter-count').textContent=[filter.watchlist,filter.origin,filter.source,filter.status,filter.history].filter(Boolean).length?'（已启用）':'';
   for(const [id,value] of [['new','new'],['closing','closing']])$(id).setAttribute('aria-pressed',String(filter.quick===value));
   const jobs=C.sort(D.jobs.filter(j=>match(j)),state,day,since);$('jobs').replaceChildren(...jobs.map(item));$('empty').hidden=jobs.length>0;
   $('heading').textContent=tabs.find(t=>t[0]===filter.tab)?.[1]||'岗位';document.title='香港求职追踪 · '+$('heading').textContent;
   const backlog=D.jobs.filter(j=>C.matches(j,{...defaults,track:filter.track},state,day,since)).length;
   const savedChanges=D.jobs.filter(j=>state.jobs[j.id]?.saved_at&&C.updated(j,state.jobs[j.id])).length;
   $('notice').textContent=jobs.length+' 条结果 · 待处理 '+backlog+' 条'+(savedChanges?' · 收藏中 '+savedChanges+' 条有更新':'');batch();
   if(focusParent && !focused.isConnected){const next=[...$(focusParent).querySelectorAll('button')].find(b=>b.textContent===focusText);next?.focus({preventScroll:true});}
   if(oldRow && !focused.isConnected){const rows=[...$('jobs').children],next=rows.find(r=>r.dataset.id===oldRow.dataset.id)||rows[Math.min(oldIndex,rows.length-1)];(next?.querySelectorAll('button')[Math.max(0,actionIndex)]||$('batch-read').nextElementSibling)?.focus({preventScroll:true});}
 }
 if(!D||!C||D.version!==2){error('快照或页面版本不匹配，请刷新；如仍失败请检查部署。');return;}
 load();
 try{const saved=JSON.parse(localStorage.getItem(filterKey)||'null');if(saved&&typeof saved==='object')filter={...defaults,...saved,tab:'pending',status:'',quick:'',tags:Array.isArray(saved.tags)?saved.tags.filter(t=>tags[t]):[]};since=localStorage.getItem(visitKey)||new Date(Date.now()-7*86400000).toISOString();}catch{error('筛选偏好无法读取，已使用默认筛选。');}
 $('stamp').textContent='最近成功更新 · '+date(D.updated_at);$('delta').textContent='本轮新增 '+(D.health?.new_count||0)+' · 重要变更 '+(D.health?.changed_count||0);
 const warnings=[],h=D.health||{};
 if(!h.last_light_success||Date.now()-Date.parse(h.last_light_success)>48*3600000)warnings.push('轻量更新超过 48 小时未成功');
 if(!h.last_full_success||Date.now()-Date.parse(h.last_full_success)>9*86400000)warnings.push('全面检查超过 9 天未成功');
 const issues=D.sources.filter(s=>['error','partial','blocked'].includes(s.status));if(issues.length)warnings.push(issues.length+' 个检查项失败或仅部分覆盖，详见底部诊断');
 $('health').textContent=warnings.join(' · ');$('health').hidden=!warnings.length;$('source-summary').textContent='来源与检查记录 · '+D.employer_count+' 家重点雇主 / '+issues.length+' 项需留意';
 const statusNames={ok:'已读取',partial:'部分覆盖',error:'失败',unchanged:'未变化',empty:'本轮无结果',blocked:'受限'};
 for(const s of D.sources){const row=el('div',undefined,'source');row.append(link(s.name,s.url),el('span',statusNames[s.status]||s.status,issues.includes(s)?'failed':''),el('span',s.message+' · '+date(s.checked_at)));$('sources').append(row);}
 for(const name of ['search','watchlist','origin','source','status'])$(name).addEventListener(name==='search'?'input':'change',()=>setFilter({[name]:$(name).value,...(name==='status'&&$(name).value?{tab:'all',history:true}:{})}));
 $('history').addEventListener('change',()=>setFilter({history:$('history').checked}));$('reset').addEventListener('click',()=>setFilter({...defaults,tags:[],track:filter.track,tab:filter.tab}));
 for(const name of ['new','closing'])$(name).addEventListener('click',()=>setFilter({quick:filter.quick===name?'':name}));
 $('select-all').addEventListener('change',()=>{selected=$('select-all').checked?new Set(D.jobs.filter(j=>C.matches(j,filter,state,today(),since)).map(j=>j.id)):new Set();render();});
 $('batch-read').addEventListener('click',()=>change([...selected],'read_at'));
 $('undo').addEventListener('click',()=>{if(!undo||!load())return;const restored=C.parseState(state);for(const id of undo.ids){if(undo.previous.jobs[id])restored.jobs[id]=undo.previous.jobs[id];else delete restored.jobs[id];}if(save(restored)){undo=null;render();notify('已撤销最近一次操作');}});
 $('finish').addEventListener('click',()=>{try{since=new Date().toISOString();localStorage.setItem(visitKey,since);render();notify('已记下检查时间。未读岗位仍保留，不会自动标为已读。');}catch{error('检查时间未能保存。');}});
 $('export').addEventListener('click',()=>{if(!load())return;const blob=new Blob([JSON.stringify(state,null,2)],{type:'application/json'}),url=URL.createObjectURL(blob),a=el('a');a.href=url;a.download='hk-career-private-'+today()+'.json';document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);notify('已导出私人记录。请勿上传到公开仓库。');});
 $('import').addEventListener('click',()=>$('import-file').click());
 $('import-file').addEventListener('change',async e=>{const file=e.target.files[0];if(!file)return;try{if(file.size>8*1024*1024)throw Error('文件超过 8 MB');const incoming=C.migrate(C.parseState(JSON.parse(await file.text())),D.jobs);if(!load())return;const previous=C.parseState(state);if(save(C.combine(state,incoming.state))){undo={previous,ids:Object.keys(incoming.state.jobs)};render();notify('已合并备份；未匹配及歧义记录继续保留'+(incoming.ambiguous?'（歧义 '+incoming.ambiguous+' 条）':''),true);}}catch(err){error('未导入：'+err.message);}finally{e.target.value='';}});
 window.addEventListener('storage',e=>{if(e.key===key||e.key===null){load();render();}});render();
})();
