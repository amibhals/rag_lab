let apiKey='';
let lastResult=null;
const $=id=>document.getElementById(id);
function esc(s){return String(s??'').replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]))}
// Gemini's answer is model-generated HTML derived from untrusted document content
// (indirect prompt injection risk), so strip anything that could execute script
// before it ever reaches innerHTML.
function sanitizeHtml(html){
  const doc=new DOMParser().parseFromString(String(html??''),'text/html');
  const banned=new Set(['SCRIPT','STYLE','IFRAME','OBJECT','EMBED','LINK','META','FORM']);
  const walker=doc.createTreeWalker(doc.body,NodeFilter.SHOW_ELEMENT);
  const toRemove=[];
  while(walker.nextNode()){
    const el=walker.currentNode;
    if(banned.has(el.tagName)){toRemove.push(el);continue}
    [...el.attributes].forEach(a=>{
      const n=a.name.toLowerCase();
      if(n.startsWith('on')||((n==='href'||n==='src')&&/^\s*javascript:/i.test(a.value)))el.removeAttribute(a.name);
    });
  }
  toRemove.forEach(el=>el.remove());
  return doc.body.innerHTML;
}
function linkifyCitations(html){return html.replace(/\[C(\d+)\]/g,(m,n)=>`<span class="cite" onclick="focusSource(${n})">[C${n}]</span>`)}
function focusSource(n){
  if(!lastResult)return;
  const idx=parseInt(n,10)-1;
  const item=(lastResult.final_context||[])[idx];
  if(!item)return alert('Source chunk not available for this citation.');
  $('traceSection').classList.remove('hidden');
  const target=[...document.querySelectorAll('#trace details')].find(el=>el.querySelector('summary')?.textContent.includes(`[C${idx+1}]`));
  if(target){target.open=true;target.scrollIntoView({behavior:'smooth',block:'center'});target.classList.add('flash');setTimeout(()=>target.classList.remove('flash'),1500)}
  else alert(`${item.chunk_id}\n${item.document} · page ${item.page}\n\n${item.text}`);
}
async function saveKey(){apiKey=$('apiKey').value.trim();if(!apiKey)return $('keyStatus').textContent='Enter a key';let r=await fetch('/api/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({api_key:apiKey})});let d=await r.json();$('keyStatus').textContent=d.ok?'✓ Configured for this session':'Error';}
async function uploadFiles(){let fs=$('files').files;if(!fs.length)return;$('uploadStatus').textContent='Analyzing…';let fd=new FormData();[...fs].forEach(f=>fd.append('files',f));let r=await fetch('/api/upload',{method:'POST',body:fd});let d=await r.json();$('uploadStatus').textContent=d.ok?'Uploaded and chunked. Review the map below before indexing.':d.detail;refresh();}
async function indexDocs(){if(!apiKey)await saveKey();$('uploadStatus').textContent='Embedding and indexing…';let r=await fetch('/api/index',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({api_key:apiKey})});let d=await r.json();$('uploadStatus').textContent=d.ok?`Indexed ${d.indexed_chunks} new chunks.${d.skipped_documents?` (${d.skipped_documents} document(s) already indexed, skipped)`:''}`:d.detail;refresh();}
async function refresh(){let r=await fetch('/api/status');let s=await r.json();$('keyStatus').textContent=s.api_key_configured?'✓ API key ready':'';let c=await (await fetch('/api/chunks')).json();renderDocs(c.documents,s);}
function renderDocs(docs,s){let total=0;let sizes=[];let html='';docs.forEach(doc=>{total+=doc.chunks.length;doc.chunks.forEach(c=>sizes.push(c.chunk_size));html+=`<div class="doc"><b>${esc(doc.name)}</b> · ${doc.pages} page/section units · ${doc.chunks.length} chunks · ${doc.indexed?'🟢 indexed':'🟡 not indexed'}<div>${[...new Set(doc.chunks.map(c=>c.page))].map(p=>{let cs=doc.chunks.filter(c=>c.page===p);return `<div class="page"><b>Page ${p}</b>${cs.map(c=>`<div class="chunk" onclick='showChunk(${JSON.stringify(c)})'><span><b>${c.id}</b> · ${c.chunk_size} chars</span><small>${c.start_char}-${c.end_char}</small></div>`).join('')}</div>`}).join('')}</div></div>`});$('docMap').innerHTML=html||'<p>No documents uploaded yet.</p>';let avg=sizes.length?Math.round(sizes.reduce((a,b)=>a+b,0)/sizes.length):0;$('stats').innerHTML=[['Documents',docs.length],['Total chunks',total],['Avg chunk size',avg+' chars'],['Chunk overlap',s.config.chunk_overlap+' chars'],['Indexed vectors',s.total_chunks],['Embedding dimensions',s.config.embedding_dimension],['Retrieval K',s.config.retrieval_k],['Threshold',s.config.threshold]].map(x=>`<div class="stat"><small>${x[0]}</small><strong>${x[1]}</strong></div>`).join('')}
function showChunk(c){alert(`${c.id}\n${c.document} · page ${c.page}\nRange: ${c.start_char}-${c.end_char}\n\n${c.text}`)}
async function ask(){let q=$('question').value.trim();if(!q)return;if(!apiKey)await saveKey();$('answer').innerHTML='<p>Running retrieval → filtering → context construction → Gemini…</p>';let r=await fetch('/api/query',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question:q,api_key:apiKey})});let d=await r.json();if(!r.ok){$('answer').innerHTML=`<p class="bad">${esc(d.detail)}</p>`;return}renderAnswer(d);renderTrace(d);}
function renderAnswer(d){
  lastResult=d;
  const safeAnswer=linkifyCitations(sanitizeHtml(d.answer||''));
  const sources=(d.sources||[]).map(x=>`<span class="srcpill" onclick="focusSource('${String(x.citation).replace('C','')}')">[${esc(x.citation)}] ${esc(x.document)} p.${esc(x.page)}</span>`).join(' ');
  $('answer').innerHTML=`<div class="answerbox"><h3>Grounded Answer</h3>${safeAnswer}<hr><small>Grounding status: <b>${d.validation?.grounding_status||'NOT RUN'}</b></small>${sources?`<div class="sources"><b>Sources</b><div>${sources}</div></div>`:''}</div>`;
}
function renderTrace(d){$('traceSection').classList.remove('hidden');let ret=d.retrieval||{};let rows=[...(ret.retrieved||[]),...(ret.rejected||[])].sort((a,b)=>a.rank-b.rank);$('trace').innerHTML=`<div class="tracegrid"><div>${panel('Question',`<p>${esc(d.question)}</p>`)}${panel('Query Embedding',`<p>Model: ${esc(d.query_embedding?.model)}<br>Dimensions: ${d.query_embedding?.dimensions}<br>Status: ${d.query_embedding?.status}</p>`)}${panel('Decision',`<p>${d.decision?.question_answerable?'✅ Evidence sufficient':'❌ Evidence insufficient'}</p><p>${esc(d.decision?.reason)}</p>`)}</div><div>${panel('Retrieval',`<p>Searched: ${ret.searched} chunks · Returned: ${ret.returned}<br>Threshold: ${d.config?.similarity_threshold}</p><table class="table"><tr><th>Rank</th><th>Chunk</th><th>Similarity</th><th>State</th></tr>${rows.map(x=>`<tr><td>${x.rank}</td><td>${esc(x.chunk_id)}</td><td class="score ${x.similarity>=d.config.similarity_threshold?'good':'bad'}">${x.similarity}</td><td>${x.similarity>=d.config.similarity_threshold?'Retrieved':'Rejected'}</td></tr>`).join('')}</table>`)}</div></div>${panel('Selected Context', (d.final_context||[]).map((x,i)=>`<details><summary>[C${i+1}] ${esc(x.chunk_id)} · ${esc(x.document)} p.${x.page} · ${x.similarity}</summary><div class="chunktext">${esc(x.text)}</div></details>`).join('')||'None')}${panel('LLM Prompt Sent',`<details><summary>Show prompt</summary><div class="chunktext">${esc(d.prompt||'No generation occurred.')}</div></details>`)}${panel('Validation',`<p>Status: <b>${d.validation?.grounding_status||'N/A'}</b></p><p>Citations detected: ${JSON.stringify(d.validation?.valid_citations||[])}</p>`)}${panel('Sources', (d.sources||[]).map(x=>`<div>${x.citation} · ${esc(x.document)} · page ${x.page} · ${esc(x.chunk_id)}</div>`).join(''))}`}
function panel(title,body){return `<div class="panel"><h3>${title}</h3>${body}</div>`}
refresh();
