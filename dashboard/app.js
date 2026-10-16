(function(){
  const sample=[
    ['TESTCO','Breakout','Daily',48.5,46.2,52,55,60,4.2,92,'Watch'],
    ['ALPHA','Pullback','Daily',112.3,107.8,120,126,134,5.0,88,'Watch'],
    ['NOVA','Base breakout','Weekly',23.4,21.8,26.5,30,35,6.6,86,'Watch'],
    ['VECTOR','Continuation','Daily',76.1,72.4,81,86,94,4.3,82,'Watch'],
    ['ZENITH','Pullback','Daily',34.2,32.1,37.5,41,46,5.6,80,'Watch'],
    ['ORION','Breakout','Daily',18.75,17.2,21,24,28,6.0,78,'Review']
  ];
  let rows=sample.map(x=>({symbol:x[0],setup_family:x[1],timeframe:x[2],entry_price:x[3],stop_loss:x[4],target_1:x[5],target_2:x[6],target_3:x[7],risk_reward_t1:x[8],score:x[9],status:x[10]}));
  const $=id=>document.getElementById(id), n=v=>Number.isFinite(Number(v))?Number(v).toFixed(2):'—';
  function render(){
    const q=($('search').value||'').toLowerCase(), visible=rows.filter(r=>!q||Object.values(r).join(' ').toLowerCase().includes(q));
    $('rows').innerHTML=visible.length?visible.map((r,i)=>`<tr class="${i===0?'selected':''}" data-symbol="${r.symbol}"><td class="symbol">${r.symbol}</td><td>${r.setup_family||'—'}</td><td>${r.timeframe||'—'}</td><td class="mono">${n(r.entry_price)}</td><td class="mono">${n(r.stop_loss)}</td><td class="mono">${n(r.target_1)}</td><td class="mono">${n(r.target_2)}</td><td class="mono">${n(r.target_3)}</td><td class="mono">${n(r.risk_reward_t1)}</td><td class="mono">${r.score??'—'}</td><td><span class="pill ${String(r.status).toLowerCase().includes('review')?'info':''}">${r.status||'Review'}</span></td></tr>`).join(''):'<tr><td colspan="11" class="muted">No candidates match this search.</td></tr>';
    $('candidateCount').textContent=visible.length;
    const rr=visible.map(r=>Number(r.risk_reward_t1)).filter(Number.isFinite);
    $('avgRR').textContent=rr.length?(rr.reduce((a,b)=>a+b,0)/rr.length).toFixed(1):'—';
    $('triggeredCount').textContent=visible.filter(r=>/trigger/i.test(r.status||'')).length;
    document.querySelectorAll('#rows tr[data-symbol]').forEach(tr=>tr.addEventListener('click',()=>{document.querySelectorAll('#rows tr').forEach(x=>x.classList.remove('selected'));tr.classList.add('selected')}));
  }
  function parseCSV(text){const lines=text.trim().split(/\r?\n/).filter(Boolean);if(lines.length<2)return[];const headers=lines.shift().split(',').map(x=>x.trim().toLowerCase().replace(/\s+/g,'_'));return lines.map(line=>{const vals=line.split(','),o={};headers.forEach((h,i)=>o[h]=(vals[i]||'').trim());return o})}
  $('search').addEventListener('input',render);
  $('loadBtn').addEventListener('click',()=>$('csvFile').click());
  $('csvFile').addEventListener('change',e=>{const f=e.target.files[0];if(!f)return;const reader=new FileReader();reader.onload=()=>{const parsed=parseCSV(reader.result);if(parsed.length){rows=parsed;$('tableStatus').textContent=`Loaded ${parsed.length} rows`;render()}};reader.readAsText(f)});
  $('exportBtn').addEventListener('click',()=>{const head='symbol,setup_family,timeframe,entry_price,stop_loss,target_1,target_2,target_3,risk_reward_t1,score,status\\n';const body=rows.map(r=>[r.symbol,r.setup_family,r.timeframe,r.entry_price,r.stop_loss,r.target_1,r.target_2,r.target_3,r.risk_reward_t1,r.score,r.status].join(',')).join('\\n');const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([head+body],{type:'text/csv'}));a.download='oscar-candidates.csv';a.click();URL.revokeObjectURL(a.href)});
  function exportRows(){ $('exportBtn').click(); }
  document.querySelectorAll('.nav a').forEach(link=>link.addEventListener('click',e=>{
    e.preventDefault();
    const page=link.getAttribute('href').slice(1);
    document.body.dataset.page=page==='paper'?'paper':page==='reports'?'reports':'overview';
    document.querySelectorAll('.nav a').forEach(x=>x.classList.toggle('active',x===link));
    window.scrollTo({top:0,behavior:'smooth'});
  }));
  document.querySelectorAll('.tabs button').forEach(tab=>tab.addEventListener('click',()=>{
    document.querySelectorAll('.tabs button').forEach(x=>x.classList.remove('active'));tab.classList.add('active');
    document.querySelector('.legend span:last-child').textContent='Backtest window · '+tab.textContent;
  }));
  $('paperExport').addEventListener('click',exportRows);
  $('reportExport').addEventListener('click',exportRows);
  render();
})();
