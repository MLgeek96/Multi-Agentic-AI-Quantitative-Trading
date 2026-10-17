'use strict';

const $ = selector => document.querySelector(selector);
const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const numeric = value => typeof value === 'number' && Number.isFinite(value);
const money = value => numeric(value) ? new Intl.NumberFormat('en-US', {style:'currency', currency:'USD', maximumFractionDigits:0}).format(value) : '—';
const compact = value => !numeric(value) ? '—' : Math.abs(value) >= 1e6 ? `$${(value / 1e6).toFixed(2)}m` : money(value);
const percent = value => numeric(value) ? `${(value * 100).toFixed(1)}%` : '—';
const decimal = (value, digits=2) => numeric(value) ? value.toLocaleString('en-US', {maximumFractionDigits:digits, minimumFractionDigits:digits}) : '—';
const human = value => String(value ?? 'unavailable').replaceAll('_', ' ').toLowerCase();
const badge = (label, tone='neutral') => `<span class="pill ${tone}">${escapeHtml(label)}</span>`;
const statusBadge = status => badge(human(status).toUpperCase(), ['READY','REVIEWED','PASS','INTENTS_RECORDED'].includes(status) ? 'good' : ['INPUT_HOLD','RISK_VETO','BREAKER_LATCHED','REJECTED'].includes(status) ? 'bad' : 'neutral');
const jsonDetails = (label, value) => `<details><summary class="detail-summary">${escapeHtml(label)}</summary><pre class="json">${escapeHtml(JSON.stringify(value, null, 2))}</pre></details>`;
const empty = message => `<div class="empty">${escapeHtml(message)}</div>`;
const gross = group => (group.legs || []).reduce((sum, leg) => sum + Math.abs(leg.units * leg.price_usd), 0);
const sumGross = groups => groups.reduce((sum, group) => sum + gross(group), 0);
const pmTitle = pm => pm === 'crypto' ? 'Crypto PM' : pm === 'pairs' ? 'Pairs PM' : 'Momentum PM';
const views = {
  overview: ['Fund overview', 'One view of your capital, managers, and independent risk controls.'],
  risk: ['Risk monitor', 'Trace every target through capital, concentration, and drawdown controls.'],
  pms: ['Portfolio managers', 'From strategy evidence to signed targets, with each manager in focus.'],
  flow: ['System flow', 'Follow the connections from market inputs to the permanent decision record.'],
  audit: ['Decision ledger', 'Inspect the evidence, approvals, and linked intentions behind this cycle.']
};
let report = null;
let selectedId = null;
let reportList = [];
let indexWarnings = [];
let activeNode = 'risk';
let activePair = 0;
let loading = false;

async function getJson(url) {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`Could not load saved report (${response.status}).`);
  return response.json();
}

async function loadReports() {
  if (loading) return;
  loading = true;
  $('#refresh').disabled = true;
  try {
    const data = await getJson('/api/reports');
    reportList = data.reports;
    indexWarnings = data.warnings;
    $('#cycle-select').innerHTML = reportList.map((r, i) => `<option value="${escapeHtml(r.id)}">${escapeHtml(`${r.mode === 'demo' ? 'Demo' : 'Historical'} · ${r.as_of} · ${r.cycle_id.slice(0,8)}${i === 0 ? ' · latest saved' : ''}`)}</option>`).join('');
    if (!reportList.length) {
      report = null;
      selectedId = null;
      $('#export').disabled = true;
      $('#mode-badge').innerHTML = 'NO REPORTS';
      $('#source-note').textContent = 'No saved coordinator cycles found.';
      $('#content').innerHTML = empty('Generate a demonstration with python -m fund_agents, then refresh reports. You can also select a custom report directory using --reports when starting the dashboard.') + (indexWarnings.length ? jsonDetails('Skipped report details', indexWarnings) : '');
      return;
    }
    selectedId = reportList.some(r => r.id === selectedId) ? selectedId : reportList[0].id;
    $('#cycle-select').value = selectedId;
    await loadSelected();
  } catch (error) { showError(error); }
  finally { loading = false; $('#refresh').disabled = false; }
}

async function loadSelected() {
  $('#cycle-select').disabled = true;
  $('#export').disabled = true;
  try {
    const next = await getJson(`/api/report?id=${encodeURIComponent(selectedId)}`);
    report = next;
    activePair = 0;
    $('#mode-badge').textContent = report.mode === 'demo' ? 'SYNTHETIC DEMO' : 'HISTORICAL REPLAY';
    $('#mode-badge').className = `pill ${report.mode === 'demo' ? 'warn' : 'neutral'}`;
    const generated = new Date(report.generated_at_utc).toLocaleString('en-GB', {timeZone:'Asia/Singapore', day:'2-digit',month:'short',year:'numeric',hour:'2-digit',minute:'2-digit',hour12:false});
    $('#source-note').innerHTML = `<b>Valuation date ${escapeHtml(report.as_of)}</b> · ${report.mode === 'demo' ? 'Invented market inputs' : 'Saved historical inputs'} · Generated ${escapeHtml(generated)} SGT. This is a saved snapshot; it does not establish current market coverage.${indexWarnings.length ? ` ${indexWarnings.length} unreadable report(s) skipped.` : ''}`;
    $('#footer-cycle').textContent = `Cycle ${report.cycle_id.slice(0,8)} · ${report.config.account_key}`;
    $('#export').disabled = false;
    render();
  } catch (error) { showError(error); }
  finally { $('#cycle-select').disabled = false; }
}

function showError(error) {
  report = null;
  $('#export').disabled = true;
  $('#mode-badge').textContent = 'CONNECTION ERROR';
  $('#source-note').textContent = 'Report data unavailable. Refresh to reconnect.';
  $('#content').innerHTML = `<div class="empty error">${escapeHtml(error.message)} Check that the local dashboard server is running, then refresh reports.</div>`;
}

function context() {
  const risk = report.fund_risk;
  const metrics = risk.metrics || {};
  const cfg = report.config;
  const snapshot = report.portfolio_before;
  const groups = risk.approved_groups || [];
  const nav = numeric(metrics.marked_nav_usd) ? metrics.marked_nav_usd : null;
  const peak = Math.max(snapshot.peak_nav_usd || 0, risk.state?.peak_nav_usd || 0);
  const drawdown = nav !== null && peak > 0 ? Math.max(0, 1 - nav / peak) : null;
  const names = {};
  groups.forEach(g => (g.legs || []).forEach(l => { names[l.symbol] = (names[l.symbol] || 0) + Math.abs(l.units * l.price_usd); }));
  const largestName = nav ? Math.max(0, ...Object.values(names)) / nav : null;
  return {risk,metrics,cfg,snapshot,groups,nav,drawdown,names,largestName};
}

function metric(label, value, sub, icon='↗') {
  return `<div class="metric"><div class="metric-label">${label}<span>${icon}</span></div><div class="metric-value">${value}</div><div class="metric-sub">${sub}</div></div>`;
}

function metricsPanel() {
  const {metrics,nav,risk,drawdown,cfg,snapshot} = context();
  return `<div class="metric-grid">
    ${metric('Marked fund NAV', money(nav), nav === null ? 'Unavailable · valuation held' : `${snapshot.holdings.length === 0 ? 'Cash-only supplied account' : 'From confirmed account snapshot'} · USD`, '◈')}
    ${metric('Approved target gross', percent(metrics.target_gross_fraction), `${money(metrics.target_gross_usd)} <span class="muted">/ ${percent(cfg.maximum_fund_gross)} fund limit</span>`, '↗')}
    ${metric('Fund drawdown', percent(drawdown), `${risk.state?.breaker_latched ? '<span class="negative">Breaker latched</span>' : 'Snapshot vs. recorded peak'} · ${percent(cfg.maximum_drawdown)} breaker`, '◇')}
    ${metric('Recorded intent groups', String((report.execution_receipts || []).length), `${numeric(metrics.filled_orders) ? metrics.filled_orders : '—'} fills · <span class="positive">record-only execution</span>`, '≡')}
  </div>`;
}

function allocationPanel() {
  const {cfg} = context();
  const sleeves = [
    ['Crypto PM',cfg.crypto_budget_usd,'#456b51','Connected'], ['Pairs PM',cfg.pairs_budget_usd,'#aac096','Connected'],
    ['Momentum reserve',cfg.momentum_reserve_usd,'#d6dcca','Awaiting integration'], ['Central cash',cfg.central_cash_usd,'#edf0e8','Liquidity reserve']
  ];
  const total = sleeves.reduce((sum,s) => sum+s[1],0);
  let stop = 0;
  const gradient = sleeves.map(s => { const start = stop; stop += total ? s[1]/total*100 : 0; return `${s[2]} ${start}% ${stop}%`; }).join(',');
  return `<section class="panel"><div class="section-heading"><h2>Capital allocation</h2><span>Configured mandates</span></div><div class="allocation-content"><div class="donut" style="background:conic-gradient(${gradient})" role="img" aria-label="${escapeHtml(sleeves.map(s => `${s[0]} ${percent(s[1]/total)}`).join(', '))}"><div class="donut-inner"><strong>${compact(total)}</strong><small>initial fund mandate</small></div></div><div class="legend">${sleeves.map(s => `<div class="legend-row"><i class="swatch" style="background:${s[2]}"></i><div>${s[0]}<small>${s[3]}</small></div><strong>${percent(total ? s[1]/total : null)}</strong></div>`).join('')}</div></div><div class="panel-foot">Mandates show the initial capital plan. Approved targets and confirmed holdings are tracked separately.</div></section>`;
}

function riskRow(label, value, limit, explanation) {
  const ratio = numeric(value) && numeric(limit) && limit > 0 ? value/limit : null;
  const color = ratio === null ? '#c9d1c0' : ratio >= 1 ? '#b36e58' : ratio >= .8 ? '#bc9b5d' : '#7b9b6d';
  return `<div class="risk-row"><div class="risk-label"><span>${label}</span><strong>${percent(value)} <span class="muted">/ ${percent(limit)}</span></strong></div><div class="track"><span style="width:${ratio === null ? 0 : Math.min(100,Math.max(0,ratio*100))}%;background:${color}"></span></div><div class="risk-caption"><span>${explanation}</span><span>${ratio === null ? 'Unavailable' : `${(ratio*100).toFixed(0)}% of limit`}</span></div></div>`;
}

function riskPanel() {
  const {risk,cfg,metrics,drawdown,largestName} = context();
  return `<section class="panel"><div class="section-heading"><h2>Risk guardrails</h2>${statusBadge(risk.status)}</div>
    ${riskRow('Fund gross exposure',metrics.target_gross_fraction,cfg.maximum_fund_gross,'Approved target · before netting')}
    ${riskRow('Largest symbol exposure',largestName,cfg.maximum_name_gross,'Aggregated across PM sleeves')}
    ${riskRow('Fund drawdown',drawdown,cfg.maximum_drawdown,'Confirmed snapshot vs. peak')}
    <div class="risk-summary"><span>${risk.status === 'INPUT_HOLD' ? 'Input hold · no approved targets' : risk.state?.breaker_latched ? 'Drawdown breaker remains latched' : risk.status === 'RISK_VETO' ? 'Final fund risk veto' : 'Independent fund review complete'}</span><a href="#risk">Details ↗</a></div></section>`;
}

function pmCards() {
  const {cfg,groups,risk} = context();
  return `<div class="section-heading"><h2>Portfolio managers</h2><span>Two connected · one reserved</span></div><div class="pm-grid">${['crypto','pairs'].map(pm => {
    const proposal = report.pm_proposals[pm];
    const details = proposal.diagnostics;
    const signal = pm === 'pairs' ? details.pairs?.[0]?.rationale : details.regime?.model;
    return `<article class="pm-card ${pm}"><div class="pm-top"><div class="pm-icon">${pm === 'crypto' ? '₿' : '⇄'}</div><div><h3>${pmTitle(pm)}</h3><p>${pm === 'crypto' ? 'Adaptive crypto strategies' : 'Kalman / OU mean reversion'}</p></div>${statusBadge(proposal.status)}</div><div class="pm-numbers"><div><small>Capital mandate</small><strong>${compact(cfg[pm+'_budget_usd'])}</strong></div><div><small>Approved gross</small><strong>${risk.status === 'INPUT_HOLD' ? '—' : compact(sumGross(groups.filter(g=>g.pm===pm)))}</strong></div></div><div class="pm-meta">${escapeHtml(details.error || signal || 'No model diagnostic available.')}</div><a class="pm-link" href="#pms">Inspect manager evidence <span style="float:right">↗</span></a></article>`;
  }).join('')}<article class="pm-card pending"><div class="pm-top"><div class="pm-icon">↗</div><div><h3>Momentum PM</h3><p>Equity momentum strategy</p></div>${badge('PENDING')}</div><div class="pm-numbers"><div><small>Reserved cash</small><strong>${compact(report.momentum_pm.reserved_cash_usd)}</strong></div><div><small>Signal engine</small><strong class="muted">—</strong></div></div><div class="pm-meta">Capital is reserved. The momentum engine is awaiting integration.</div><div class="pm-link muted">${escapeHtml(human(report.momentum_pm.status))}</div></article></div>`;
}

function alerts() {
  const messages = [...(report.fund_risk.alerts || [])];
  for (const [pm,p] of Object.entries(report.pm_proposals)) if(p.diagnostics.error) messages.push(`${pmTitle(pm)}: ${p.diagnostics.error}`);
  return messages.length ? `<div class="alert">${messages.map(escapeHtml).join('<br>')}</div>` : '';
}

function overview() {
  return alerts() + metricsPanel() + `<div class="grid-main">${allocationPanel()}${riskPanel()}</div>` + pmCards() + `<section class="panel"><div class="section-heading"><h2>A connected decision pipeline</h2><a href="#flow">Explore system flow ↗</a></div><div class="flow-strip"><div class="mini-step">01 · Market inputs<small>Crypto candles + equity closes</small></div><span class="flow-arrow">→</span><div class="mini-step">02 · PM proposals<small>Signals, sizing, local checks</small></div><span class="flow-arrow">→</span><div class="mini-step">03 · Fund risk<small>Independent veto + hedge scaling</small></div><span class="flow-arrow">→</span><div class="mini-step">04 · Audit records<small>Linked intents · zero fills</small></div></div><div class="panel-foot">Advisory PM memos consume diagnostics after risk. They have no trading authority.</div></section>`;
}

function targetTable(groups, reviews=false) {
  if (!groups.length) return empty('No approved targets in this cycle. Missing inputs or a risk veto can prevent approval.');
  return `<div class="table-wrap"><table><thead><tr><th>MANAGER / GROUP</th><th>SYMBOL</th><th>SIGNED TARGET UNITS</th><th>TARGET NOTIONAL</th><th>${reviews ? 'REVIEW / SCALE' : 'SESSION'}</th></tr></thead><tbody>${groups.flatMap(g => g.legs.map((leg,i) => {
    const review = report.fund_risk.reviews.find(r => r.approved.group===g.group && r.approved.pm===g.pm);
    return `<tr><td>${i === 0 ? `${escapeHtml(g.group)}<small>${pmTitle(g.pm)}${g.hedge_beta !== null ? ` · β ${decimal(g.hedge_beta,4)}` : ''}</small>` : '<span class="muted">↳ linked leg</span>'}</td><td>${escapeHtml(leg.symbol)}<small>${leg.units > 0 ? 'Long' : leg.units < 0 ? 'Short' : 'Flat'}</small></td><td>${decimal(leg.units,4)}</td><td class="${leg.units < 0 ? 'negative' : ''}">${money(leg.units*leg.price_usd)}</td><td>${reviews ? `${review ? statusBadge(review.outcome) : '—'}<small>Scale ${percent(review?.scale)}</small>` : `${escapeHtml(g.signal_session)}<small>${g.actionable ? 'Actionable session' : 'Market closed · retain units'}</small>`}</td></tr>`;
  })).join('')}</tbody></table></div>`;
}

function riskView() {
  const {risk,cfg,groups,names,nav,snapshot} = context();
  return alerts() + metricsPanel() + `<div class="grid-equal">${riskPanel()}<section class="panel"><div class="section-heading"><h2>Concentration by symbol</h2><span>Approved gross / marked NAV</span></div>${nav === null ? empty('Concentration is unavailable because fund valuation was held.') : Object.keys(names).length ? Object.entries(names).sort((a,b)=>b[1]-a[1]).map(([name,value]) => riskRow(escapeHtml(name),value/nav,cfg.maximum_name_gross,money(value))).join('') : empty('No approved exposure to display.')}</section></div><section class="panel wide"><div class="section-heading"><h2>Capital protection policy</h2><span>Effective cycle configuration</span></div><div class="risk-policy"><div><h3>Collateral buffer</h3><strong>${percent(cfg.collateral_buffer)}</strong><small>Applied to the smaller of mandate and marked sleeve equity. Short proceeds add no collateral capacity.</small></div><div><h3>Fee reserve</h3><strong>${decimal(cfg.fee_buffer_bps,0)} bps</strong><small>Reserved against an upper bound on target-to-current turnover. This is a reserve, not fees charged.</small></div><div><h3>Linked group scaling</h3><strong>${risk.reviews?.length ? percent(Math.min(...risk.reviews.map(r=>r.scale))) : '—'}</strong><small>A common scale preserves the signed dollar hedge relationship. Closed markets retain confirmed units.</small></div></div></section><section class="panel wide"><div class="section-heading"><h2>Approved targets & risk outcomes</h2><span>Targets do not become holdings</span></div>${targetTable(groups,true)}${jsonDetails('Inspect exact risk decision and binding hashes',risk)}</section><section class="panel"><div class="section-heading"><h2>Confirmed holdings</h2><span>Supplied account · ${snapshot.holdings.length} positions</span></div>${snapshot.holdings.length ? jsonDetails('Inspect confirmed holdings',snapshot.holdings) : empty('The supplied account is flat. Intention records have not changed its holdings.')}<div class="panel-foot">Fund NAV, drawdown and current holdings reflect the supplied snapshot. Performance history, VaR, and realized P&L are unavailable in this record-only integration.</div></section>`;
}

function forecastChart(pair) {
  const forecasts = (pair.forecasts || []).filter(f=>numeric(f.horizon_days)&&numeric(f.expected_z));
  if (!forecasts.length || !numeric(pair.z_score) || !numeric(pair.spread_std) || pair.spread_std <= 0) return empty('The OU forecast is unavailable for this pair. No forecast curve has been synthesized.');
  const points = [{horizon_days:0,expected_z:pair.z_score}, ...forecasts];
  const lo = Math.min(-report.config.entry_z, ...points.map(p=>p.expected_z), ...forecasts.filter(p=>numeric(p.lower_95)).map(p=>p.lower_95/pair.spread_std));
  const hi = Math.max(report.config.entry_z, ...points.map(p=>p.expected_z), ...forecasts.filter(p=>numeric(p.upper_95)).map(p=>p.upper_95/pair.spread_std));
  const pad=(hi-lo)*.15 || 1, bottom=lo-pad, top=hi+pad;
  const xmax=Math.max(...points.map(p=>p.horizon_days)), x=d=>52+(d/xmax)*600, y=z=>220-(z-bottom)/(top-bottom)*190;
  const line=points.map((p,i)=>`${i?'L':'M'} ${x(p.horizon_days)} ${y(p.expected_z)}`).join(' ');
  const intervals=forecasts.filter(p=>numeric(p.lower_95)&&numeric(p.upper_95));
  const band=intervals.length ? intervals.map((p,i)=>`${i?'L':'M'} ${x(p.horizon_days)} ${y(p.upper_95/pair.spread_std)}`).join(' ')+' '+[...intervals].reverse().map(p=>`L ${x(p.horizon_days)} ${y(p.lower_95/pair.spread_std)}`).join(' ')+' Z' : '';
  return `<svg class="chart" viewBox="0 0 690 262" role="img" aria-label="${escapeHtml(pair.pair)} expected future spread Z-score by horizon in sessions, with OU 95 percent interval"><title>OU forward projection, not historical performance</title>${[lo,(lo+hi)/2,hi].map(v=>`<line x1="52" x2="652" y1="${y(v)}" y2="${y(v)}" stroke="#e8ece2"/><text x="10" y="${y(v)+4}">${v.toFixed(1)}</text>`).join('')}<line x1="52" x2="652" y1="${y(0)}" y2="${y(0)}" stroke="#b6c3aa" stroke-dasharray="4 4"/>${[-report.config.entry_z,report.config.entry_z].map(v=>`<line x1="52" x2="652" y1="${y(v)}" y2="${y(v)}" stroke="#ddd7bc" stroke-dasharray="3 5"/>`).join('')}<path d="${band}" fill="#dfead5" opacity=".8"/><path d="${line}" fill="none" stroke="#628453" stroke-width="2.5"/>${points.map(p=>`<circle cx="${x(p.horizon_days)}" cy="${y(p.expected_z)}" r="3.5" fill="#628453"><title>${p.horizon_days} sessions: Z ${p.expected_z.toFixed(3)}</title></circle><text x="${x(p.horizon_days)}" y="245" text-anchor="middle">${p.horizon_days===0?'Now':`+${p.horizon_days}`}</text>`).join('')}</svg><div class="chart-legend"><span><i></i>Expected Z</span><span><i style="background:#dfead5;height:8px"></i>95% OU interval</span><span>Horizon in sessions</span></div>`;
}

function pmsView() {
  const {cfg} = context();
  const pairs = report.pm_proposals.pairs;
  const crypto = report.pm_proposals.crypto;
  const pairList = pairs.diagnostics.pairs || [];
  const pair = pairList[activePair];
  return alerts() + pmCards() + `<section class="panel wide"><div class="section-heading"><h2>Pairs PM · model workbench</h2>${pairList.length ? `<select id="pair-select" aria-label="Pair diagnostics">${pairList.map((p,i)=>`<option value="${i}" ${i===activePair?'selected':''}>${escapeHtml(p.pair)} · ${escapeHtml(p.signal_session)}</option>`).join('')}</select>` : statusBadge(pairs.status)}</div>${pair ? `<p class="subheading">${escapeHtml(pair.rationale)}<br>${escapeHtml(pair.calendar)} · ${pair.rows} observed sessions · ${escapeHtml(pair.market_closed ? 'Market closed; last session valuation only' : 'Signal from completed exchange session')}</p><div class="grid-equal"><div><div class="fact-grid"><div class="fact"><small>Current Z-score</small><strong>${decimal(pair.z_score)}</strong></div><div class="fact"><small>Kalman hedge β</small><strong>${decimal(pair.beta_kalman,4)}</strong></div><div class="fact"><small>OU half-life</small><strong>${decimal(pair.ou_half_life)} <span style="font-size:10px">sessions</span></strong></div><div class="fact"><small>Entry / exit |Z|</small><strong>${decimal(cfg.entry_z)} / ${decimal(cfg.exit_z)}</strong></div><div class="fact"><small>Stop |Z|</small><strong>${decimal(cfg.stop_z)}</strong></div><div class="fact"><small>Holding / maximum</small><strong>${pair.held_sessions} / ${cfg.max_holding_sessions}</strong></div></div><p class="subheading">Target position: <b>${pair.target_position > 0 ? 'Long spread' : pair.target_position < 0 ? 'Short spread' : 'Flat'}</b> · Formation: ${pair.formation ? pair.formation.qualified ? 'qualified' : 'not qualified' : 'disabled / unavailable'}<br>${escapeHtml(pairs.diagnostics.formation_policy)}</p></div><div><div class="section-heading"><h2>Spread reversion forecast</h2>${badge('MODEL PROJECTION')}</div>${forecastChart(pair)}<div class="panel-foot">Saved forward OU estimates. The shaded band is model uncertainty, not a return history or profit guarantee.</div></div></div>` : empty(pairs.diagnostics.error || 'No pair diagnostics are available.')}${jsonDetails('Inspect complete pairs evidence',pairs)}</section><section class="panel wide"><div class="section-heading"><h2>Crypto PM · strategy evidence</h2>${statusBadge(crypto.status)}</div><p class="subheading">${escapeHtml(crypto.diagnostics.regime?.model || crypto.diagnostics.error || 'No regime diagnostic')}<br>${escapeHtml(crypto.diagnostics.regime?.interpretation || '')}</p>${(crypto.diagnostics.specialist_signals||[]).length ? `<div class="table-wrap"><table><thead><tr><th>SYMBOL</th><th>SPECIALIST</th><th>SIGNAL EXPOSURE</th><th>ANNUALIZED VOLATILITY</th><th>RATIONALE</th></tr></thead><tbody>${crypto.diagnostics.specialist_signals.map(s=>`<tr><td>${escapeHtml(s.symbol)}</td><td>${escapeHtml(s.expert)}</td><td>${percent(s.exposure)}</td><td>${percent(s.annualized_volatility)}</td><td>${escapeHtml(s.reason)}</td></tr>`).join('')}</tbody></table></div>` : empty('No specialist signals available.')}${jsonDetails('Inspect local crypto risk, weights, and model diagnostics',crypto.diagnostics)}</section><section class="panel"><div class="section-heading"><h2>PM diagnostic memos</h2><span>Advisory · after risk</span></div><div class="grid-equal">${Object.entries(report.pm_representatives).map(([pm,memo])=>`<div><div class="audit-head"><h3>${pmTitle(pm)}</h3>${statusBadge(memo.status)}</div><p class="subheading">${escapeHtml(memo.computed_memo?.summary)}<br>${escapeHtml(memo.tool_selection_source)}</p><p class="subheading">${memo.tool_calls?.length ?? 0} recorded diagnostic calls. ${memo.status === 'NOT_REQUESTED' ? 'No LLM reply was imported.' : 'Inspect evidence for imported reply validation.'}</p>${jsonDetails('Inspect tool calls and memo provenance',memo)}</div>`).join('')}</div><div class="panel-foot">No automatic LLM provider is connected. Diagnostic memos cannot change quantitative targets, fund risk, or recorded intentions.</div></section>`;
}

const nodeDefinitions = {
  inputs: ['Market inputs','Completed UTC crypto candles and a local equity close matrix enter separate PM adapters. The pairs adapter validates every expected exchange session and does not forward-fill missing prices. A missing PM input holds the whole cycle.','crypto_agents/data.py · fund_agents/pairs.py'],
  crypto: ['Crypto PM','The existing Meta agent routes regime, signal, sizing and local risk checks. Its final locally reviewed quantities become fund target groups, converted to USD under the explicit account valuation convention.','fund_agents/crypto.py · crypto_agents/meta.py'],
  pairs: ['Pairs PM','Kalman estimation produces a signed hedge beta. The OU engine projects spread reversion; formation health, divergence rules and holding limits gate target positions. Both legs travel together as one target group.','fund_agents/pairs.py · fund_agents/vendor/pairs_trading/'],
  risk: ['Independent fund risk','The coordinator sends both proposals and the same confirmed account snapshot to fund risk. Gross exposure is counted before netting; symbol exposure is aggregated across sleeves. A common scaling factor preserves pair hedges, and the drawdown breaker remains latched in SQLite.','fund_agents/risk.py'],
  execution: ['Linked intention records','Execution checks the exact persisted approval and account snapshot before recording each linked group. Repeated intentions are deduplicated. There is no quote, borrow, exchange-order or fill adapter, and supplied holdings do not change.','fund_agents/store.py'],
  audit: ['Atomic audit & report','Decisions, intentions, risk state and the complete cycle are persisted in one transaction. JSON reports expose snapshots, decisions, evidence digests, diagnostic calls and receipts. This dashboard reads those exports.','fund_agents/coordinator.py · fund_agents/__main__.py'],
  momentum: ['Momentum reserve','The fund reserves cash for a future equity momentum manager. There is no connected momentum signal engine, proposal, or execution path.','FundSnapshot.momentum_cash_usd · momentum_pm.status']
};

function flowNode(key, step, sub, tone='') {
  return `<button class="flow-node ${tone} ${activeNode===key?'selected':''}" data-node="${key}" aria-pressed="${activeNode===key}"><span class="node-step">${step}</span><b>${nodeDefinitions[key][0]}</b><small>${escapeHtml(sub)}</small></button>`;
}

function nodeDetail() {
  const [title,description,source] = nodeDefinitions[activeNode];
  let evidence;
  if (activeNode==='inputs') evidence={as_of:report.as_of,crypto_data_basis:report.pm_proposals.crypto.diagnostics.data_basis,pairs_data_basis:report.pm_proposals.pairs.diagnostics.data_basis,errors:Object.fromEntries(Object.entries(report.pm_proposals).map(([k,p])=>[k,p.diagnostics.error||null]))};
  else if (['crypto','pairs'].includes(activeNode)) evidence=report.pm_proposals[activeNode];
  else if (activeNode==='risk') evidence=report.fund_risk;
  else if (activeNode==='execution') evidence=report.execution_receipts;
  else if (activeNode==='momentum') evidence=report.momentum_pm;
  else evidence={cycle_id:report.cycle_id,config_sha256:report.config_sha256,decision_id:report.fund_risk.decision_id,snapshot_sha256:report.fund_risk.snapshot_sha256};
  return `<h3>${title}</h3><p>${description}</p><div class="code-ref">${source}</div>${jsonDetails('Inspect this connection’s saved evidence',evidence)}`;
}

function flowView() {
  return `<section class="panel wide"><div class="section-heading"><h2>How the fund connects</h2>${statusBadge(report.status)}</div><p class="subheading">Select a component to inspect its responsibilities, source modules, and actual cycle evidence. Arrows show data and approval flow.</p><div class="flow-grid"><div class="flow-stack">${flowNode('inputs','01 / INGEST',report.mode === 'demo' ? 'Invented demo inputs' : `Historical inputs · ${report.as_of}`)}</div><span class="flow-arrow">→</span><div class="flow-stack">${flowNode('crypto','02 / PROPOSE',human(report.pm_proposals.crypto.status))}${flowNode('pairs','02 / PROPOSE',human(report.pm_proposals.pairs.status))}</div><span class="flow-arrow">→</span><div>${flowNode('risk','03 / APPROVE',human(report.fund_risk.status))}</div><span class="flow-arrow">→</span><div class="flow-stack">${flowNode('execution','04 / RECORD',`${report.execution_receipts.length} linked receipts · no fills`)}${flowNode('audit','05 / PERSIST','SQLite + JSON evidence')}</div></div><div class="advisory"><b>↳ Diagnostic tools → PM memos</b><span>Signals · model health · positions. Computed or imported advisory evidence runs after risk and has no trading authority.</span></div><div style="max-width:300px;margin:20px 0">${flowNode('momentum','PENDING / RESERVED','Cash only · no proposal connection','pending')}</div><div id="flow-detail" class="flow-detail">${nodeDetail()}</div></section><div class="grid-equal"><section class="panel"><div class="section-heading"><h2>Shared contracts</h2></div><p class="subheading">FundSnapshot → PMProposal → TargetGroup → FundRisk review → linked receipt.<br>Each pair target includes two signed legs, the hedge beta, valuation date, and signal session. Exact hashes bind execution records to approval and supplied holdings.</p>${jsonDetails('Inspect configuration',report.config)}</section><section class="panel"><div class="section-heading"><h2>Implemented boundary</h2>${badge('RECORD ONLY','warn')}</div><p class="subheading">Connected: crypto, pairs, independent risk, diagnostic tools, atomic persistence and this dashboard.<br>Pending: momentum signals, automatic LLM calls, executable quotes, borrow checks, fills and consolidated performance accounting.</p></section></div>`;
}

function auditView() {
  const {risk,snapshot} = context();
  const receipts=report.execution_receipts||[];
  return alerts() + `<section class="panel wide"><div class="section-heading"><h2>Cycle identity</h2>${statusBadge(report.status)}</div><div class="fact-grid"><div class="fact"><small>Valuation date</small><strong>${escapeHtml(report.as_of)}</strong></div><div class="fact"><small>Execution mode</small><strong style="font-size:17px">${escapeHtml(human(report.execution_mode))}</strong></div><div class="fact"><small>Account</small><strong style="font-size:14px">${escapeHtml(report.config.account_key)}</strong></div></div><p class="subheading">Cycle ID <span class="mono">${escapeHtml(report.cycle_id)}</span><br>Decision ID <span class="mono">${escapeHtml(risk.decision_id)}</span><br>Snapshot SHA-256 <span class="mono">${escapeHtml(risk.snapshot_sha256)}</span></p>${jsonDetails('Inspect confirmed account before and after', {before:snapshot,after:report.portfolio_after})}</section><section class="panel wide"><div class="section-heading"><h2>Execution receipts</h2><span>${receipts.length} groups · zero fills</span></div>${receipts.length ? receipts.map(receipt=>`<div><div class="audit-head"><h3>${escapeHtml(receipt.group)} <span class="muted">/ ${pmTitle(receipt.pm)}</span></h3>${statusBadge(receipt.status)}</div><div class="table-wrap"><table><thead><tr><th>SYMBOL</th><th>SIDE</th><th>CURRENT UNITS</th><th>TARGET UNITS</th><th>DELTA UNITS</th></tr></thead><tbody>${receipt.intent.legs.map(l=>`<tr><td>${escapeHtml(l.symbol)}</td><td>${escapeHtml(l.side)}</td><td>${decimal(l.current_units,4)}</td><td>${decimal(l.units,4)}</td><td>${decimal(l.delta_units,4)}</td></tr>`).join('')}</tbody></table></div>${jsonDetails('Inspect receipt, linked conditions, and intent digest',receipt)}</div>`).join('') : empty('No intention receipts were recorded in this cycle. Existing confirmed holdings remain unchanged.')}</section><section class="panel"><div class="section-heading"><h2>Evidence & limitations</h2><span>Export preserves the original cycle</span></div><p class="subheading">${report.limitations.map(escapeHtml).join('<br>')}</p>${jsonDetails('Inspect original full report',report)}${indexWarnings.length ? jsonDetails('Skipped report details',indexWarnings) : ''}</section>`;
}

function render() {
  const view = Object.hasOwn(views,location.hash.slice(1)) ? location.hash.slice(1) : 'overview';
  const [title,description]=views[view];
  $('#breadcrumb').textContent=title;
  $('#page-title').innerHTML=`${title}<span class="title-dot">.</span>`;
  $('#page-description').textContent=description;
  document.querySelectorAll('nav a').forEach(a=>a.classList.toggle('active',a.dataset.view===view));
  if (!report) return;
  $('#content').innerHTML=({overview,risk:riskView,pms:pmsView,flow:flowView,audit:auditView}[view])();
  document.querySelectorAll('[data-node]').forEach(button=>button.addEventListener('click',()=>{
    activeNode=button.dataset.node;
    document.querySelectorAll('[data-node]').forEach(b=>{b.classList.toggle('selected',b===button);b.setAttribute('aria-pressed',b===button);});
    $('#flow-detail').innerHTML=nodeDetail();
  }));
  $('#pair-select')?.addEventListener('change',event=>{activePair=Number(event.target.value);render();});
}

$('#cycle-select').addEventListener('change',()=>{selectedId=$('#cycle-select').value;loadSelected();});
$('#refresh').addEventListener('click',loadReports);
$('#export').addEventListener('click',()=>{
  if(!report)return;
  const url=URL.createObjectURL(new Blob([JSON.stringify(report,null,2)],{type:'application/json'}));
  const link=document.createElement('a');link.href=url;link.download=`fund-cycle-${report.mode}-${report.as_of}-${report.cycle_id}.json`;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
});
window.addEventListener('hashchange',render);
render();
loadReports();
