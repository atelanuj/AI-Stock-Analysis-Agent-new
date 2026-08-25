document.addEventListener('DOMContentLoaded', () => {
  const $ = (id) => document.getElementById(id);
  let mfNavChart = null;
  let mfReturnsChart = null;
  let stockChartType = 'candlestick';
  let stockChartPeriod = '3mo';

  const themeKey = 'stock-ai-theme';
  let theme = localStorage.getItem(themeKey) || 'dark';
  document.documentElement.setAttribute('data-theme', theme);
  updateThemeIcon();

  $('theme-toggle').addEventListener('click', () => {
    theme = theme === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem(themeKey, theme);
    updateThemeIcon();
    const symbol = $('stock-symbol')?.dataset.symbol;
    const market = $('stock-symbol')?.dataset.market;
    if (symbol && market && !$('stock-results').classList.contains('hidden')) loadCandles(symbol, market);
  });

  function updateThemeIcon() {
    $('theme-toggle').innerHTML = theme === 'dark' ? '<i class="fa-solid fa-sun"></i>' : '<i class="fa-solid fa-moon"></i>';
  }

  document.querySelectorAll('.nav-btn').forEach(btn => btn.addEventListener('click', () => {
    document.querySelectorAll('.nav-btn').forEach(x => x.classList.remove('active'));
    document.querySelectorAll('.tab-pane').forEach(x => x.classList.add('hidden'));
    btn.classList.add('active');
    $(`tab-${btn.dataset.tab}`).classList.remove('hidden');
  }));

  function currency(value, code) {
    if (value === null || value === undefined || Number.isNaN(Number(value))) return '--';
    return new Intl.NumberFormat('en-US', {style: 'currency', currency: code || 'USD', maximumFractionDigits: 2}).format(Number(value));
  }

  function num(value, digits = 2) {
    if (value === null || value === undefined || Number.isNaN(Number(value))) return '--';
    return Number(value).toFixed(digits);
  }

  function pct(value) {
    if (value === null || value === undefined || Number.isNaN(Number(value))) return '--';
    const v = Number(value); return `${v > 0 ? '+' : ''}${v.toFixed(2)}%`;
  }

  function escapeHtml(value) {
    return String(value ?? '').replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
  }

  function scoreColor(v) {
    if (v >= 70) return 'var(--positive)';
    if (v >= 45) return 'var(--warning)';
    return 'var(--negative)';
  }


  function safeExternalUrl(value) {
    if (!value) return null;
    try {
      const u = new URL(value, window.location.origin);
      return ['http:', 'https:'].includes(u.protocol) ? u.href : null;
    } catch (_) { return null; }
  }

  function formatNewsDate(value) {
    if (!value) return '';
    const d = new Date(value);
    return Number.isNaN(d.getTime()) ? '' : d.toLocaleDateString(undefined, {month:'short', day:'numeric', year:'numeric'});
  }

  function setMetricStatus(id, status, label, title) {
    const box = $(id);
    box.classList.remove('metric-good', 'metric-caution', 'metric-bad', 'metric-neutral');
    box.classList.add(`metric-${status}`);
    const signal = box.querySelector('.metric-signal');
    if (signal) signal.textContent = label;
    box.title = title || '';
  }

  function applyMetricColors(market, f, t) {
    const pe = Number(f.trailing_pe);
    if (f.trailing_pe == null) setMetricStatus('metric-pe','neutral','No data','P/E is unavailable.');
    else if (pe <= 0) setMetricStatus('metric-pe','bad','Loss-making / N.M.','A non-positive P/E often means earnings are negative or the ratio is not meaningful.');
    else if (pe <= 20) setMetricStatus('metric-pe','good','Lower valuation','Generic heuristic only; compare P/E with sector peers and the company’s growth rate.');
    else if (pe <= 35) setMetricStatus('metric-pe','caution','Moderate valuation','Generic heuristic only; sector growth and historical valuation matter.');
    else setMetricStatus('metric-pe','bad','High valuation','A high P/E can increase valuation risk, although high-growth companies may justify it.');

    const cap = Number(f.market_cap);
    if (!f.market_cap) setMetricStatus('metric-mcap','neutral','No data','Market cap is unavailable.');
    else if ((market.currency === 'INR' && cap >= 1e12) || (market.currency !== 'INR' && cap >= 1e11)) setMetricStatus('metric-mcap','good','Large-cap size','Green here means larger size/liquidity as a risk proxy; it does not mean the stock is automatically a better investment.');
    else if ((market.currency === 'INR' && cap >= 2e11) || (market.currency !== 'INR' && cap >= 1e10)) setMetricStatus('metric-mcap','caution','Mid-size','Medium company size can carry more volatility/liquidity risk than mega/large caps.');
    else setMetricStatus('metric-mcap','bad','Smaller-cap risk','Red here highlights higher size/liquidity risk, not poor business quality.');

    const roe = f.return_on_equity == null ? null : Number(f.return_on_equity) * 100;
    if (roe == null || Number.isNaN(roe)) setMetricStatus('metric-roe','neutral','No data','ROE is unavailable.');
    else if (roe >= 15) setMetricStatus('metric-roe','good','Strong efficiency','ROE above ~15% is a common favorable heuristic, but leverage and sector norms matter.');
    else if (roe >= 8) setMetricStatus('metric-roe','caution','Moderate efficiency','ROE is moderate; compare with peers and the company’s cost of equity.');
    else setMetricStatus('metric-roe','bad','Weak efficiency','Low or negative ROE can indicate weak shareholder-capital efficiency.');

    const rsi = t.rsi14 == null ? null : Number(t.rsi14);
    if (rsi == null || Number.isNaN(rsi)) setMetricStatus('metric-rsi','neutral','No data','RSI is unavailable.');
    else if (rsi >= 45 && rsi <= 65) setMetricStatus('metric-rsi','good','Healthy momentum','RSI in this band often indicates constructive momentum without an extreme reading.');
    else if ((rsi >= 35 && rsi < 45) || (rsi > 65 && rsi < 75)) setMetricStatus('metric-rsi','caution','Watch momentum','RSI is moving toward a weaker or more stretched zone; confirmation from trend/price action helps.');
    else setMetricStatus('metric-rsi','bad', rsi >= 75 ? 'Overbought / stretched' : 'Oversold / weak', 'Extreme RSI readings can persist and are not standalone buy/sell signals.');
  }

  // STOCKS
  $('stock-search-btn').addEventListener('click', runStockAnalysis);
  $('stock-search-input').addEventListener('keydown', e => { if (e.key === 'Enter') runStockAnalysis(); });
  document.querySelectorAll('#chart-type-toggle .segment-btn').forEach(btn => btn.addEventListener('click', () => {
    stockChartType = btn.dataset.chartType;
    document.querySelectorAll('#chart-type-toggle .segment-btn').forEach(x => x.classList.toggle('active', x === btn));
    const symbol = $('stock-symbol').dataset.symbol, market = $('stock-symbol').dataset.market;
    if (symbol && market) loadCandles(symbol, market);
  }));
  document.querySelectorAll('#chart-period-toggle .segment-btn').forEach(btn => btn.addEventListener('click', () => {
    stockChartPeriod = btn.dataset.period;
    document.querySelectorAll('#chart-period-toggle .segment-btn').forEach(x => x.classList.toggle('active', x === btn));
    const symbol = $('stock-symbol').dataset.symbol, market = $('stock-symbol').dataset.market;
    if (symbol && market) loadCandles(symbol, market);
  }));

  async function runStockAnalysis() {
    const symbol = $('stock-search-input').value.trim().toUpperCase();
    const market = $('stock-market-select').value;
    if (!symbol) return;
    $('stock-results').classList.add('hidden'); $('stock-error').classList.add('hidden'); $('stock-loading').classList.remove('hidden');
    try {
      const res = await fetch(`/analyze/${encodeURIComponent(symbol)}?market=${market}`);
      if (!res.ok) throw new Error((await res.json()).detail || 'Stock analysis failed');
      const data = await res.json();
      renderStock(data);
      await loadCandles(symbol, market);
      $('stock-results').classList.remove('hidden');
    } catch (err) {
      $('stock-error-msg').textContent = err.message; $('stock-error').classList.remove('hidden');
    } finally { $('stock-loading').classList.add('hidden'); }
  }

  function renderStock(data) {
    const m = data.evidence.market, f = data.evidence.fundamentals, t = data.evidence.technical, ai = data.ai_analysis;
    $('stock-name').textContent = data.company_name;
    $('stock-symbol').textContent = data.symbol; $('stock-symbol').dataset.symbol = data.symbol; $('stock-symbol').dataset.market = m.market;
    $('stock-price').textContent = currency(m.current_price, m.currency); $('stock-market-badge').textContent = `${m.market} · ${m.currency}`;

    const scoreMap = [['overall','overall'],['fund','fundamental'],['tech','technical'],['val','valuation'],['risk','risk']];
    scoreMap.forEach(([id,key]) => { const v = data.scores[key]; $(`score-${id}`).style.width = `${v}%`; $(`score-${id}`).style.backgroundColor = scoreColor(v); $(`score-${id}-val`).textContent = `${v}/100`; });

    $('m-pe').textContent = num(f.trailing_pe); $('m-roe').textContent = f.return_on_equity == null ? '--' : pct(f.return_on_equity * 100); $('m-rsi').textContent = num(t.rsi14);
    const cap = f.market_cap; $('m-mcap').textContent = cap ? new Intl.NumberFormat('en-US',{notation:'compact',maximumFractionDigits:2}).format(cap) : '--';
    applyMetricColors(m, f, t);

    $('ai-rating').textContent = ai.rating || data.deterministic_rating; $('ai-rating').style.color = /BUY/.test(ai.rating || '') ? 'var(--positive)' : /SELL|REDUCE/.test(ai.rating || '') ? 'var(--negative)' : 'var(--warning)';
    $('ai-confidence').textContent = `Confidence: ${(ai.confidence || 'low').toUpperCase()}`; $('ai-thesis-text').textContent = ai.thesis || '--';
    $('ai-positives-list').innerHTML = (ai.positives || []).map(x => `<li>${escapeHtml(x)}</li>`).join('') || '<li>No positives supplied.</li>';
    $('ai-risks-list').innerHTML = (ai.risks || []).map(x => `<li>${escapeHtml(x)}</li>`).join('') || '<li>No risks supplied.</li>';

    renderTrend(t);
    renderPatterns(t.candlestick_patterns || []);
    $('news-list').innerHTML = (data.evidence.news || []).slice(0,8).map(n => {
      const headline = escapeHtml(n.headline || n.title || 'News');
      const publisher = escapeHtml(n.publisher || n.source || '');
      const date = escapeHtml(formatNewsDate(n.published_at));
      const summary = n.summary ? `<p class="news-summary">${escapeHtml(n.summary)}</p>` : '';
      const url = safeExternalUrl(n.url);
      const body = `<div class="news-title">${headline}</div>${summary}<div class="news-meta"><span>${publisher}${publisher && date ? ' · ' : ''}${date}</span>${url ? '<span class="news-read">Read full article <i class="fa-solid fa-arrow-up-right-from-square"></i></span>' : '<span>Link unavailable</span>'}</div>`;
      return url ? `<a class="news-item" href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer" title="Open full article on publisher site">${body}</a>` : `<div class="news-item">${body}</div>`;
    }).join('') || '<p class="text-muted">No recent news returned.</p>';
  }

  function renderTrend(t) {
    const timelines = t.timeline_biases || {};
    const order = ['1W','1M','3M','6M','1Y'];
    const fallback = t.trend_outlook || {};
    if (!timelines['1W'] && fallback.directional_bias) timelines['1W'] = fallback;

    $('trend-support').textContent = num(t.support_20d);
    $('trend-resistance').textContent = num(t.resistance_20d);
    $('trend-timeframes').innerHTML = order.map(label => {
      const o = timelines[label] || {};
      const bias = o.directional_bias || 'NEUTRAL';
      return `<button type="button" class="timeframe-bias-card ${label === '1W' ? 'active' : ''}" data-horizon="${label}">
        <span class="timeframe-label">${label}</span>
        <strong class="${bias.toLowerCase()}">${escapeHtml(bias)}</strong>
        <small>${o.confidence_pct ?? '--'}% signal</small>
        <small>${o.return_pct == null ? '' : `${pct(o.return_pct)} lookback`}</small>
      </button>`;
    }).join('');

    const showHorizon = (label) => {
      const o = timelines[label] || fallback;
      $('trend-confidence').textContent = `${label} signal confidence ${o.confidence_pct ?? '--'}%`;
      $('trend-reasons').innerHTML = (o.reasons || []).map(x => `<li>${escapeHtml(x)}</li>`).join('') || '<li>No supporting signals available.</li>';
      $('trend-timeframes').querySelectorAll('.timeframe-bias-card').forEach(card => card.classList.toggle('active', card.dataset.horizon === label));
    };
    $('trend-timeframes').querySelectorAll('.timeframe-bias-card').forEach(card => card.addEventListener('click', () => showHorizon(card.dataset.horizon)));
    showHorizon('1W');
  }

  function renderPatterns(patterns) {
    $('pattern-list').innerHTML = patterns.length ? patterns.slice(0,8).map(p => { const h=p.historical_5d||{}; const hist=h.occurrences ? ` Historical 5-session directional hit rate: ${h.directional_hit_rate_pct}% across ${h.occurrences} occurrences; avg forward return ${h.average_forward_return_pct}%.` : ''; return `<div class="pattern-item"><div><b>${escapeHtml(p.pattern)}</b><span>${escapeHtml(p.date)}</span></div><span class="bias-chip ${String(p.bias).toLowerCase()}">${escapeHtml(p.bias)}</span><p>${escapeHtml(p.note + hist)}</p></div>`; }).join('') : '<p class="text-muted">No notable recent patterns detected.</p>';
  }

  async function loadCandles(symbol, market) {
    const period = stockChartPeriod;
    const res = await fetch(`/api/candles/${encodeURIComponent(symbol)}?market=${market}&period=${period}`);
    if (!res.ok) return;
    const data = await res.json();
    const c = data.candles || [];
    if (!c.length || typeof Plotly === 'undefined') return;

    const dates = c.map(x => x.date);
    let traces;
    if (stockChartType === 'line') {
      traces = [{
        type:'scatter', mode:'lines', x:dates, y:c.map(x=>x.close), name:`${symbol} close`,
        line:{width:2, color:getComputedStyle(document.documentElement).getPropertyValue('--primary-color').trim() || '#3b82f6'},
        hovertemplate:'%{x}<br>Close: %{y:.2f}<extra></extra>'
      }];
    } else {
      traces = [{
        type:'candlestick', x:dates, open:c.map(x=>x.open), high:c.map(x=>x.high), low:c.map(x=>x.low), close:c.map(x=>x.close), name:symbol
      }];
    }

    const shapes = [];
    if (data.support_20d != null) shapes.push({type:'line',xref:'paper',x0:0,x1:1,y0:data.support_20d,y1:data.support_20d,line:{dash:'dot',width:1,color:'rgba(16,185,129,.65)'}});
    if (data.resistance_20d != null) shapes.push({type:'line',xref:'paper',x0:0,x1:1,y0:data.resistance_20d,y1:data.resistance_20d,line:{dash:'dot',width:1,color:'rgba(239,68,68,.65)'}});
    const annotations = stockChartType === 'candlestick' ? (data.patterns || []).slice(0,5).map(p => ({
      x:p.date, y:(c.find(x=>x.date===p.date)||{}).high, text:p.pattern, showarrow:true, arrowhead:2, font:{size:10}
    })).filter(a=>a.y) : [];

    const textColor = getComputedStyle(document.documentElement).getPropertyValue('--text-primary').trim();
    const secondary = getComputedStyle(document.documentElement).getPropertyValue('--text-secondary').trim();
    Plotly.react('candlestick-chart', traces, {
      paper_bgcolor:'rgba(0,0,0,0)', plot_bgcolor:'rgba(0,0,0,0)', font:{color:textColor},
      margin:{l:55,r:15,t:15,b:40},
      xaxis:{rangeslider:{visible:false},gridcolor:'rgba(128,128,128,.12)',tickfont:{color:secondary}},
      yaxis:{gridcolor:'rgba(128,128,128,.12)',tickfont:{color:secondary},fixedrange:false},
      shapes, annotations, hovermode:'x unified'
    }, {responsive:true,displaylogo:false,scrollZoom:true});
  }

  // FUNDS
  let mfTimer;
  $('mf-market-select').addEventListener('change', () => { $('mf-autocomplete').classList.add('hidden'); $('mf-search-input').placeholder = $('mf-market-select').value === 'IN' ? 'Search Indian mutual fund name' : 'Search US fund/ETF or enter ticker'; });
  $('mf-search-input').addEventListener('input', () => {
    clearTimeout(mfTimer); const q = $('mf-search-input').value.trim(); if (q.length < 2) return $('mf-autocomplete').classList.add('hidden');
    mfTimer = setTimeout(() => searchFunds(q), 400);
  });
  $('mf-search-btn').addEventListener('click', analyzeFundFromInput);
  $('mf-search-input').addEventListener('keydown', e => { if(e.key==='Enter') analyzeFundFromInput(); });

  async function searchFunds(q) {
    const market = $('mf-market-select').value; const res = await fetch(`/mf/search?q=${encodeURIComponent(q)}&market=${market}`); if (!res.ok) return;
    const rows = await res.json();
    $('mf-autocomplete').innerHTML = rows.slice(0,12).map(x => `<div class="ac-item" data-id="${escapeHtml(x.identifier || x.scheme_code || x.symbol)}">${escapeHtml(x.scheme_name || x.symbol)} <small>${escapeHtml(x.quote_type || '')}</small></div>`).join('');
    $('mf-autocomplete').classList.toggle('hidden', !rows.length);
    $('mf-autocomplete').querySelectorAll('.ac-item').forEach(el => el.addEventListener('click', () => { $('mf-search-input').value = el.textContent.trim(); $('mf-autocomplete').classList.add('hidden'); analyzeFund(el.dataset.id, market); }));
  }

  async function analyzeFundFromInput() {
    const market = $('mf-market-select').value, q = $('mf-search-input').value.trim(); if (!q) return;
    if (market === 'US' && /^[A-Za-z0-9.\-^]+$/.test(q)) return analyzeFund(q.toUpperCase(), market);
    const res = await fetch(`/mf/search?q=${encodeURIComponent(q)}&market=${market}`); const rows = res.ok ? await res.json() : [];
    if (!rows.length) return showMFError('No matching funds found.');
    analyzeFund(rows[0].identifier || rows[0].scheme_code || rows[0].symbol, market);
  }

  async function analyzeFund(identifier, market) {
    $('mf-results').classList.add('hidden'); $('mf-error').classList.add('hidden'); $('mf-loading').classList.remove('hidden');
    try { const res = await fetch(`/mf/analyze/${encodeURIComponent(identifier)}?market=${market}`); if(!res.ok) throw new Error((await res.json()).detail || 'Fund analysis failed'); renderFund(await res.json()); $('mf-results').classList.remove('hidden'); }
    catch(err){ showMFError(err.message); } finally { $('mf-loading').classList.add('hidden'); }
  }
  function showMFError(msg){ $('mf-error-msg').textContent=msg; $('mf-error').classList.remove('hidden'); }

  function renderFund(data) {
    $('mf-name').textContent = data.scheme_name || data.identifier; $('mf-category').textContent = data.scheme_category || data.quote_type || 'Fund'; $('mf-nav').textContent = currency(data.current_nav, data.currency || (data.market==='IN'?'INR':'USD')); $('mf-date').textContent = `As of ${data.date}`;
    $('mf-score').textContent = `${data.analysis.score}/100`; $('mf-rating').textContent = data.analysis.rating; $('mf-summary').textContent = data.analysis.summary;
    const r=data.returns||{}, risk=data.risk_metrics||{}; $('mf-ret-1y').textContent=pct(r['1Y']); $('mf-ret-3y').textContent=pct(r['3Y']); $('mf-ret-5y').textContent=pct(r['5Y']); $('mf-ret-6m').textContent=pct(r['6M']); $('mf-vol').textContent=pct(risk.annualized_volatility_pct); $('mf-mdd').textContent=pct(risk.max_drawdown_pct); $('mf-positive').textContent=pct(risk.positive_day_ratio_pct);
    let er=data.expense_ratio; if(er!=null && Number(er)<=1) er=Number(er)*100; $('mf-expense').textContent=er==null?'--':`${Number(er).toFixed(2)}%`;
    const history=[...(data.history||[])].reverse(); const labels=history.map(x=>x.date), navs=history.map(x=>x.nav);
    if(mfNavChart) mfNavChart.destroy(); mfNavChart=new Chart($('mf-nav-chart'),{type:'line',data:{labels,datasets:[{label:'NAV / Price',data:navs,borderWidth:2,pointRadius:0,tension:.1}]},options:{responsive:true,plugins:{legend:{display:false}},scales:{x:{ticks:{maxTicksLimit:6}}}}});
    const keys=['1M','3M','6M','1Y','3Y','5Y']; if(mfReturnsChart) mfReturnsChart.destroy(); mfReturnsChart=new Chart($('mf-returns-chart'),{type:'bar',data:{labels:keys,datasets:[{label:'Return %',data:keys.map(k=>r[k]??0)}]},options:{responsive:true,plugins:{legend:{display:false}}}});
  }

  // SCREENER
  $('screen-asset').addEventListener('change', updateScreenerMode); $('screen-run').addEventListener('click', runScreener); updateScreenerMode();
  function updateScreenerMode(){ const isStock=$('screen-asset').value==='STOCK'; $('screen-trend').disabled=!isStock; $('screen-input').placeholder=isStock?'Optional symbols, comma separated. Blank = built-in popular-market universe.':'Enter scheme codes/tickers comma separated, OR a search phrase such as index / technology / S&P 500.'; }

  async function runScreener(){ const asset=$('screen-asset').value, market=$('screen-market').value, raw=$('screen-input').value.trim(), min=Number($('screen-min-score').value||0); $('screen-results').classList.add('hidden'); $('screen-error').classList.add('hidden'); $('screen-loading').classList.remove('hidden');
    try { let url,payload; if(asset==='STOCK'){url='/screen/stocks';payload={market,symbols:raw?raw.split(',').map(x=>x.trim()).filter(Boolean):[],use_default_universe:true,top_n:10,min_overall_score:min,min_technical_score:0,trend_bias:$('screen-trend').value};} else {url='/screen/funds'; const looksList=raw.includes(',') || /^\d+$/.test(raw) || (market==='US' && /^[A-Z0-9.\-^]+(?:\s*,\s*[A-Z0-9.\-^]+)*$/i.test(raw)); payload={market,identifiers:looksList&&raw?raw.split(',').map(x=>x.trim()).filter(Boolean):[],query:looksList?null:(raw||null),top_n:10,max_candidates:15,min_score:min};}
      const res=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)}); if(!res.ok) throw new Error((await res.json()).detail||'Screener failed'); renderScreener(await res.json(),asset); }
    catch(err){$('screen-error-msg').textContent=err.message;$('screen-error').classList.remove('hidden');} finally{$('screen-loading').classList.add('hidden');}
  }

  function renderScreener(data,asset){ const rows=data.top||[]; if(asset==='STOCK'){ $('screen-head').innerHTML='<tr><th>Symbol</th><th>Name</th><th>Price</th><th>Overall</th><th>Technical</th><th>Trend</th><th>Pattern</th><th>Rating</th></tr>'; $('screen-body').innerHTML=rows.map(r=>`<tr><td><b>${escapeHtml(r.symbol)}</b></td><td>${escapeHtml(r.company_name)}</td><td>${escapeHtml(r.currency||'')} ${num(r.current_price)}</td><td>${r.overall_score}</td><td>${r.technical_score}</td><td><span class="bias-chip ${String(r.trend_bias).toLowerCase()}">${r.trend_bias} ${r.trend_confidence_pct??'--'}%</span></td><td>${escapeHtml(r.latest_pattern?.pattern||'--')}</td><td>${escapeHtml(r.rating)}</td></tr>`).join(''); }
    else { $('screen-head').innerHTML='<tr><th>Fund</th><th>Type</th><th>Score</th><th>1Y</th><th>3Y Ann.</th><th>Max DD</th><th>Volatility</th><th>Rating</th></tr>'; $('screen-body').innerHTML=rows.map(r=>`<tr><td><b>${escapeHtml(r.name||r.identifier)}</b><br><small>${escapeHtml(r.identifier)}</small></td><td>${escapeHtml(r.quote_type||r.category||'Fund')}</td><td>${r.score}</td><td>${pct(r.return_1y_pct)}</td><td>${pct(r.return_3y_annualized_pct)}</td><td>${pct(r.max_drawdown_pct)}</td><td>${pct(r.annualized_volatility_pct)}</td><td>${escapeHtml(r.rating)}</td></tr>`).join(''); }
    $('screen-note').textContent=`Evaluated ${data.evaluated||0} candidates. ${(data.errors||[]).length} errors. ${data.note||data.method||''}`; $('screen-results').classList.remove('hidden');
  }

  // PORTFOLIO
  $('portfolio-add').addEventListener('click', () => addHoldingRow()); $('portfolio-run').addEventListener('click', runPortfolio); addHoldingRow('STOCK','IN','RELIANCE',1,0); addHoldingRow('STOCK','US','AAPL',1,0);
  function addHoldingRow(asset='STOCK',market='IN',identifier='',qty='',avg=''){ const tr=document.createElement('tr'); tr.innerHTML=`<td><select class="glass-input pf-asset"><option value="STOCK" ${asset==='STOCK'?'selected':''}>Stock</option><option value="FUND" ${asset==='FUND'?'selected':''}>Fund</option></select></td><td><select class="glass-input pf-market"><option value="IN" ${market==='IN'?'selected':''}>IN</option><option value="US" ${market==='US'?'selected':''}>US</option></select></td><td><input class="glass-input pf-id" value="${escapeHtml(identifier)}" placeholder="AAPL / 120503"></td><td><input class="glass-input pf-qty" type="number" min="0" step="any" value="${qty}"></td><td><input class="glass-input pf-avg" type="number" min="0" step="any" value="${avg}"></td><td><button class="icon-btn pf-remove"><i class="fa-solid fa-trash"></i></button></td>`; tr.querySelector('.pf-remove').addEventListener('click',()=>tr.remove()); $('portfolio-input-body').appendChild(tr); }

  async function runPortfolio(){ const holdings=[...$('portfolio-input-body').querySelectorAll('tr')].map(tr=>({asset_type:tr.querySelector('.pf-asset').value,market:tr.querySelector('.pf-market').value,identifier:tr.querySelector('.pf-id').value.trim(),quantity:Number(tr.querySelector('.pf-qty').value),average_price:Number(tr.querySelector('.pf-avg').value)})).filter(x=>x.identifier&&x.quantity>0&&x.average_price>0); if(!holdings.length){$('portfolio-error-msg').textContent='Add at least one complete holding.';$('portfolio-error').classList.remove('hidden');return;} $('portfolio-results').classList.add('hidden');$('portfolio-error').classList.add('hidden');$('portfolio-loading').classList.remove('hidden');
    try{const res=await fetch('/portfolio/analyze',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({holdings})}); if(!res.ok) throw new Error((await res.json()).detail||'Portfolio analysis failed'); renderPortfolio(await res.json());}catch(err){$('portfolio-error-msg').textContent=err.message;$('portfolio-error').classList.remove('hidden');}finally{$('portfolio-loading').classList.add('hidden');}
  }
  function renderPortfolio(data){const s=data.summary;$('pf-value').textContent=num(s.market_value);$('pf-pnl').textContent=`${num(s.total_pnl)} (${pct(s.total_pnl_pct)})`;$('pf-quality').textContent=`${num(s.weighted_quality_score,1)}/100`;$('pf-concentration').textContent=pct(s.largest_position_weight_pct);$('pf-warnings').innerHTML=(data.warnings||[]).map(w=>`<div class="warning-box"><i class="fa-solid fa-triangle-exclamation"></i> ${escapeHtml(w)}</div>`).join('');$('pf-body').innerHTML=(data.positions||[]).map(p=>`<tr><td><b>${escapeHtml(p.identifier)}</b><br><small>${escapeHtml(p.name||'')}</small></td><td>${p.asset_type}</td><td>${p.market}</td><td>${pct(p.weight_pct)}</td><td>${num(p.pnl)} (${pct(p.pnl_pct)})</td><td>${num(p.overall_score,1)}</td><td>${escapeHtml(p.rating)}</td></tr>`).join('');$('portfolio-results').classList.remove('hidden');}
});
