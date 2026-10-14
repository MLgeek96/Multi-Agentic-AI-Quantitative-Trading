import fs from 'node:fs/promises';
import path from 'node:path';
import { pathToFileURL, fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';

const workspaceDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..');
const buildDir = path.resolve(process.env.FE5209_DECK_BUILD_DIR || path.join(workspaceDir,'.codex-build/fe5209-deck-rebuild'));
const outputDir = path.resolve(process.env.FE5209_DECK_OUTPUT_DIR || path.join(buildDir,'exports'));
const skillDir = process.env.FE5209_PRESENTATION_SKILL_DIR;
const runtimePython = process.env.RUNTIME_PYTHON;
const runtimeModules = process.env.RUNTIME_NODE_MODULES;
if (!skillDir || !runtimePython || !runtimeModules) {
 throw new Error('Set FE5209_PRESENTATION_SKILL_DIR, RUNTIME_PYTHON and RUNTIME_NODE_MODULES to the Codex bundled runtime paths.');
}
const runtimeRequire = createRequire(path.join(runtimeModules,'package.json'));
const { Presentation, PresentationFile, FileBlob } = await import(pathToFileURL(runtimeRequire.resolve('@oai/artifact-tool')).href);
const { finalizePresentation, resolvePresentationFont, applyPresentationChartFont, makeNativeBulletParagraphs } = await import(pathToFileURL(path.join(skillDir,'container_tools/artifact_tool_utils.mjs')).href);
const FONT = resolvePresentationFont({fontFamily:'Arial'});
const C = {ink:'#162A3A', muted:'#516476', paper:'#FFFFFF', teal:'#087E8B', blue:'#2864A0', purple:'#7757A1', gray:'#80909B', line:'#D9E2E8', header:'#EDF2F5'};
const p = Presentation.create({slideSize:{width:1280,height:720}});
const brief = path.join(workspaceDir,'algorithmic_trading_strategy_project_brief_execution_roadmap.md');
const arch = path.join(workspaceDir,'ARCHITECTURE.md');
const sourceNotes = (local=[],web=[]) => [...local.map(x=>'Repository source: '+path.relative(workspaceDir,x).replaceAll('\\','/')), ...web.map(x=>'Source: '+x)].join('\n');
const web14='https://waylandz.com/quant-book-en/Lesson-14-LLM-Applications-in-Quant/';
const web16='https://waylandz.com/quant-book-en/Lesson-16-Portfolio-Construction-and-Exposure-Management/';
const webAgents='https://docs.langchain.com/oss/python/langgraph/workflows-agents';

function txt(slide,text,x,y,w,h,size=26,{color=C.ink,bold=false,align='left'}={}) {
  const s=slide.shapes.add({geometry:'textbox',name:text.split('\n')[0].slice(0,70),position:{left:x,top:y,width:w,height:h},fill:'none',line:{fill:'none',width:0}});
  s.text=text;
  s.text.style={typeface:FONT,fontSize:size,color,bold,alignment:align,verticalAlignment:'top',insets:0,wrap:'square',autoFit:'none'};
  return s;
}
function add(title,subtitle='') {
  const s=p.slides.add(); s.background.fill=C.paper;
  txt(s,title,72,48,1136,68,44,{bold:true});
  if(subtitle) txt(s,subtitle,72,123,1136,54,25,{color:C.muted});
  txt(s,String(p.slides.items.length).padStart(2,'0'),1150,676,58,22,17,{color:C.muted,align:'right'});
  return s;
}
function bullets(s,items,x,y,w,h,size=27) {
  const sh=txt(s,'',x,y,w,h,size);
  sh.text=makeNativeBulletParagraphs(items,{marginLeftPoints:18,hangingPoints:9,spaceAfterPoints:13});
  return sh;
}
function table(s,values,x,y,w,h,widths,sz=24) {
  const t=s.tables.add({rows:values.length,columns:values[0].length,left:x,top:y,width:w,height:h,columnWidths:widths,values});
  t.styleOptions={headerRow:true,bandedRows:false};
  t.borders.assign({fill:C.line,width:0.7,style:'solid'});
  t.cells.block({row:0,column:0,rowCount:values.length,columnCount:values[0].length}).assign({margins:{top:10,bottom:10,left:12,right:12},anchor:'center'});
  for(let r=0;r<values.length;r++) {
    t.rows[r].height=h/values.length;
    for(let c=0;c<values[r].length;c++) {
      const cell=t.getCell(r,c); cell.fill=r===0?C.header:C.paper;
      cell.text.style={typeface:FONT,fontSize:sz,color:C.ink,bold:r===0,verticalAlignment:'middle',autoFit:'none'};
    }
  }
  return t;
}
function note(s,text,local=[],web=[]) {s.speakerNotes.text=text+'\n\n'+sourceNotes(local,web);}

// 1. A simple cover with editable typography.
{
 const s=p.slides.add(); s.background.fill=C.ink;
 txt(s,'AI-assisted multi-agent\nquantitative fund',72,166,1100,190,65,{bold:true,color:C.paper});
 txt(s,'FE5209 project scope and design',72,387,1100,50,32,{color:'#C9E1E8'});
 txt(s,'Three strategy PMs managing a USD 5m paper fund',72,463,1100,62,28,{color:C.paper});
 txt(s,'Proposed design\n14 October 2026',72,591,800,60,23,{color:'#C9E1E8'});
 note(s,'The project combines an equity momentum strategy, a daily pairs strategy and a crypto strategy. Each PM has a quantitative engine and a planned AI representative with diagnostic tools. A coordinator allocates capital and a deterministic risk controller approves portfolio changes. USD 5 million is the team’s proposed simulated capital, subject to the instructor’s starting-capital convention. This deck describes scope and design, with no claim that the combined fund is implemented or profitable.',[brief,arch]);
}

// 2. Course requirement and scope.
{
 const s=add('Project scope','A portfolio experiment with a visible AI review workflow');
 txt(s,'Course requirements',72,205,530,42,30,{bold:true});
 bullets(s,[
  'Automated model updates and daily forecasts',
  'Mandatory class assets with eligible history',
  'Out-of-sample evaluation: 1–23 October 2026',
  'Code, closing-price CSV and presentation'
 ],72,267,530,296,27);
 txt(s,'Proposed first version',678,205,530,42,30,{bold:true});
 bullets(s,[
  'Three PMs with separate paper ledgers',
  'Shared allocation and fund risk controls',
  'AI agents inspect tools and cite evidence',
  'One hosted application with saved run history'
 ],678,267,530,296,27);
 txt(s,'Initial capital and execution assumptions need instructor confirmation',72,621,1136,34,23,{color:C.muted});
 note(s,'The confirmed workspace brief permits a coherent multi-model ensemble. The mandatory core assets must appear in the selected universe, and each included asset needs history before 1 August 2025. The date range is 23 calendar days, not 23 US equity trading sessions. The required closing-price file covers all included portfolio assets. Live-tested code does not by itself establish instructor acceptance of paper execution. Keep the existing October history intact and label historical replays and backfilled records separately.',[brief]);
}

// 3. Allocation remains native, editable evidence.
{
 const s=add('USD 5m fund allocation','Illustrative initial mandates, with USD 0.5m held centrally');
 const allocations=[1500000,1500000,1500000,500000];
 const total=allocations.reduce((a,b)=>a+b,0);
 const names=['Momentum PM','Pairs PM','Crypto PM','Central cash'];
 const vals=[['Capital owner','USD','Share'],...names.map((n,i)=>[n,allocations[i].toLocaleString('en-US'),(allocations[i]/total*100).toFixed(0)+'%']),['Total fund',total.toLocaleString('en-US'),'100%']];
 table(s,vals,72,199,605,352,[250,190,165],24);
 txt(s,'Initial capital, USD millions',745,204,460,40,26,{bold:true});
 const ch=s.charts.add('bar',{
  position:{left:735,top:259,width:473,height:292},categories:['Momentum','Pairs','Crypto','Cash'],
  series:[{name:'Initial capital',values:allocations.map(v=>v/1e6),fill:C.blue,points:[{idx:0,fill:C.blue},{idx:1,fill:C.teal},{idx:2,fill:C.purple},{idx:3,fill:C.gray}],valuesFormatCode:'0.0'}],
  hasLegend:false,barOptions:{direction:'bar',grouping:'clustered',gapWidth:60},
  xAxis:{visible:true,majorGridlines:null,textStyle:{typeface:FONT,fontSize:24,fill:C.muted},line:{fill:'none',width:0}},yAxis:{visible:false,majorGridlines:null,line:{fill:'none',width:0}},
  dataLabels:{showValue:true,position:'outEnd',numberFormatCode:'0.0',textStyle:{typeface:FONT,fontSize:24,fill:C.ink}},
  chartFill:'none',chartLine:{fill:'none',width:0},plotAreaFill:'none',plotAreaLine:{fill:'none',width:0}
 });
 applyPresentationChartFont(ch,{fontFamily:FONT});
 txt(s,'The baseline keeps capital in each sleeve. Returns cause fund weights to drift.',72,595,1136,42,25);
 txt(s,'Equal initial capital can produce different risk. Each PM can retain cash.',72,641,1136,29,23,{color:C.muted});
 note(s,'The table totals USD 5 million: three allocations of USD 1.5 million and USD 0.5 million of central cash. These are capital mandates, not instructions to deploy every dollar. The baseline makes no transfers between PMs, so sleeve weights drift with returns. Restoring constant weights is a separate policy that must include turnover and costs. Compare a predefined alternative, such as capped inverse-volatility budgets, only after the initial allocation works. Preserve the same accounting and exposure limits across the comparison.',[],[web16]);
}

// 4. PM portfolio ownership and a consistent submission interface.
{
 const s=add('Each PM manages its own portfolio','A capital mandate gives each strategy an accountable virtual account');
 table(s,[
  ['PM','Strategy responsibility','Cadence'],
  ['Equity momentum','Run the teammate’s stock-selection rule\nand maintain target equity holdings','To confirm'],
  ['Pairs trading','Run the teammate’s paired-position rule\nand preserve the relationship between legs','Daily confirmed'],
  ['Crypto','Run the selected crypto strategy\nand manage exposure or cash','Daily proposed']
 ],72,202,1136,300,[265,611,260],25);
 txt(s,'Every PM tracks cash, positions, model state and net performance',72,548,1136,44,29,{bold:true,color:C.teal});
 txt(s,'Common proposal: decision time, input cutoff, model version, target holdings and reason codes',72,608,1136,64,25);
 note(s,'A PM owns a virtual portfolio rather than only returning a signal. The equity momentum and pairs owners retain their existing tested algorithms. Exact instruments, trading rules and signal/fill conventions still need their strategy packages. The three PMs share a submission contract that binds the proposed holdings to the available data and model version. The pairs proposal identifies both legs as one group. Each PM also maintains a cash balance, portfolio state, rolling estimates and after-cost results. The coordinator supplies capital and common constraints before each quantitative run. The AI representative inspects the resulting proposal using read-only diagnostic tools. All quantities and holdings still come from the quantitative engine. Equity universe details remain an assumption until the teammates provide tickers.',[brief,arch]);
}

// 5. Actual multi-AI contribution.
{
 const s=add('The multi-AI contribution','Each PM combines its existing strategy with a planned tool-using AI representative');
 table(s,[
  ['AI representative','Diagnostic tools','Evidence-linked output'],
  ['Momentum PM AI','Read rankings, holdings\nand sector exposure','Explain selections and\nconcentration concerns'],
  ['Pairs PM AI','Read daily spread signals,\nhedge ratios and pair health','Explain both legs and\nrelationship concerns'],
  ['Crypto PM AI','Read signals, volatility,\nliquidity and trading costs','Explain exposure or cash\nand data concerns']
 ],72,202,1136,320,[260,445,431],25);
 txt(s,'AI chooses investigations and writes PM memos',72,565,1136,40,29,{bold:true,color:C.teal});
 txt(s,'Quantitative code calculates targets. The coordinator and risk controller govern execution.',72,619,1136,52,25);
 note(s,'The LLM agents may use the same underlying model with separate mandates, tool access and state. To demonstrate agent behaviour, each representative chooses which permitted diagnostic tool to inspect in response to a question. A fixed sequence of prompts is an AI workflow. The numerical strategy engine still runs on schedule if AI is unavailable. AI reporting is the output of these agents, rather than a separate additional agent. An optional reviewer checks the PM memos against saved evidence. Code validates quoted metrics. No connected LLM agent is claimed in the existing scaffold, which currently accepts imported research replies.',[arch],[webAgents,web14]);
}

// 6. An illustrative exchange makes the AI layer visible.
{
 const s=add('An AI investment committee in practice','Illustrative exchange to replace with actual agent traces in the demonstration');
 table(s,[
  ['AI representative','Chosen diagnostic','Example PM memo'],
  ['Momentum PM AI','Inspect sector exposure','Several proposed holdings share a sector.\nI flag concentration for fund review.'],
  ['Pairs PM AI','Inspect both target legs','The target legs retain the hedge ratio.\nI attach the pair-health diagnostics.'],
  ['Crypto PM AI','Read entry qualification','The strategy has no qualified entry.\nIts quantitative target stays in cash.']
 ],72,202,1136,320,[265,340,531],24);
 txt(s,'The coordinator combines targets. The risk controller records its verdict.',72,567,1136,54,28,{bold:true,color:C.teal});
 txt(s,'Each factual claim links to a saved record. An optional reviewer checks the PM memos.',72,632,1136,42,24,{color:C.muted});
 note(s,'The messages on this slide illustrate the proposed behaviour. They are not an executed session, observed holdings or measured trading results. In the live demonstration, choose one saved decision day and ask what changed and which proposals deserve a closer check. The Momentum AI decides to inspect a concentration tool, the Pairs AI checks the grouped legs, and the Crypto AI reads why the deterministic signal remained in cash. Show the real tool requests, returned records and concise PM memos. The three representatives may use the same model with separate contexts and allowed tools. The coordinator applies the predeclared allocation policy to quantitative targets. The risk controller checks those targets through code. It has no majority-vote mechanism that allows AI opinions to bypass a limit. An optional reviewer can challenge unsupported statements, while numerical validation remains deterministic.',[arch],[webAgents,web14]);
}

// 7. Confirmed daily pairs frequency, with proposed fill timing visible.
{
 const s=add('Daily pairs decision cycle','Pairs frequency is confirmed. Exact signal and fill timing remains to be agreed.');
 table(s,[
  ['When','Owner','Output'],
  ['Session t, after close','Data adapter','Completed prices and validated timestamps'],
  ['Session t, after close','Pairs quant engine','Daily model update and linked target legs'],
  ['Before execution','Coordinator and risk','Combined exposure and approval verdict'],
  ['Next eligible session','Paper executor','Simulated fills under the declared cost model'],
  ['After valuation','Accounting and AI PMs','Fund NAV, CSV and evidence-linked memos']
 ],72,199,1136,382,[285,300,551],24);
 txt(s,'Both legs retain their hedge relationship. A daily signal can lead to no trade.',72,618,1136,42,25);
 note(s,'The teammate’s pairs strategy operates daily. The after-close and next-session timing shown here is a proposal, not a verified feature of that strategy. Inspect the actual decision timestamp, update method and fill convention before integration. Inputs must be available at the decision time, and a signal formed from a completed close cannot assume a fill at that same already-observed close. Keep equity sessions and holidays distinct from the crypto calendar. Use a common UTC valuation cutoff, preserve source price timestamps and record approved market-closed carry marks. Confirm momentum frequency. Daily crypto is proposed for the first integrated version.',[brief],['https://www.nyse.com/trade/hours-calendars','https://waylandz.com/quant-book-en/Lesson-19-Execution-System/']);
}

// 8. Boundaries and accounting.
{
 const s=add('Capital, risk and accounting','The coordinator proposes budgets. The risk controller has final approval.');
 txt(s,'Portfolio coordinator',72,205,530,42,30,{bold:true});
 bullets(s,[
  'Assign the initial PM capital mandates',
  'Combine holdings and identify overlap',
  'Track PM contribution to fund P&L',
  'Log transfers separately from returns'
 ],72,266,530,274,26);
 txt(s,'Independent risk controller',678,205,530,42,30,{bold:true});
 bullets(s,[
  'Check concentration and gross/net exposure',
  'Preserve linked pair positions',
  'Check available cash, margin and data',
  'Reject breaches and record the reason'
 ],678,266,530,274,26);
 txt(s,'Fund NAV = sum of PM NAVs + central cash',72,573,1136,46,31,{bold:true,color:C.teal});
 txt(s,'Capital transfers preserve fund NAV. Costs enter the ledger once.',72,634,1136,32,24,{color:C.muted});
 note(s,'Each PM maintains positions, cash, model state, orders and costs in a virtual sleeve ledger. Normalize consolidated reporting to USD and record the conversion used for USDT positions. Short-sale proceeds require a cash and margin policy. The initial paper model simulates sleeve orders separately and charges their respective costs, while reporting consolidated net exposure and sleeve gross exposure. Physical order netting is an extension requiring an attribution rule. Withdraw only unencumbered cash. Resizing a pair must preserve its declared hedge relationship. Each approved intent must reconcile to an execution record before the ledger claims a fill.',[arch],[web16,'https://waylandz.com/quant-book-en/Lesson-15-Risk-Control-and-Money-Management/']);
}

// 9. Required performance evidence is visible on the slide.
{
 const s=add('Performance evidence','Every consolidated result reconciles to the PM ledgers');
 txt(s,'Required course KPIs',72,205,530,42,30,{bold:true});
 bullets(s,[
  'Net P&L, total return and annualized return',
  'Sharpe ratio and annualized volatility',
  'Maximum drawdown, its frequency and duration',
  'Win rate, profit per trade, trade count and holding period'
 ],72,266,530,302,26);
 txt(s,'Fund and PM reporting',678,205,530,42,30,{bold:true});
 bullets(s,[
  'Fund NAV against the official benchmark',
  'Each PM’s contribution to profit and drawdown',
  'Fees, slippage and applicable financing costs',
  'Capital transfers recorded separately from returns'
 ],678,266,530,302,26);
 txt(s,'Saved evidence: closing prices, signals, orders, fills, allocation decisions and AI tool traces',72,608,1136,60,25,{color:C.teal,bold:true});
 note(s,'The course brief names the primary performance metrics shown here. Maintain a daily consolidated NAV series and distinct sleeve series, alongside the required daily closing-price file for every included portfolio asset. Each PM reports after-cost performance. Fund dollar P&L reconciles to the sleeves and central cash, with any shared costs charged once. When capital moves between sleeves, use a consistent flow-adjusted return convention or calculate performance before an end-of-period transfer. Report the currency conversion used for USDT positions. The mixed-asset fund needs a declared calendar and annualization policy. On nontrading equity days, mark the last valid equity close with its actual timestamp and market status. Undefined metrics should appear as unavailable. The short October window provides operational evidence with limited statistical precision. These are required outputs and planned calculations, not claimed current fund results.',[brief],[web16]);
}

// 10. Explicit hypotheses without fabricated performance.
{
 const s=add('Evaluation plan','Trading performance and AI review quality have separate tests');
 table(s,[
  ['Experiment','Question','Main evidence'],
  ['Each PM alone','Profitable after costs?','Net return, Sharpe and drawdown'],
  ['Initial-budget blend','Better as a combined fund?','Fund NAV, correlation and PM P&L'],
  ['Allocation alternative','Better after reallocation costs?','Incremental return, risk and turnover'],
  ['AI enabled / disabled','Accurate and useful explanations?','Cited facts, review time and cost']
 ],72,200,1136,350,[275,450,411],24);
 txt(s,'The AI comparison keeps quantitative portfolio decisions identical',72,583,1136,43,29,{bold:true,color:C.teal});
 txt(s,'Use the official benchmark and consistent dates, costs and capital conventions.',72,636,1136,34,24,{color:C.muted});
 note(s,'Primary course KPIs include P&L, total and annualized return, Sharpe ratio, maximum drawdown, annualized volatility, win rate, average profit per trade, trade count, holding period, and drawdown frequency and duration. Add PM attribution and exposure to evaluate coordination. Align annualization with the actual return series. A mixed-asset daily fund series needs a declared calendar and valuation policy. Show unavailable statistics when there are no qualifying trades or too few observations. Costs include applicable commissions, slippage and borrowing or funding. Fix allocation policies using development data and preserve the October evaluation history. The AI-on/off comparison tests operations and explanations, not an AI trading-alpha claim.',[brief],[web16]);
}

// 11. Small deployment and demonstrable submission.
{
 const s=add('Delivery and ownership','One application hosts the PM views and the daily decision history');
 txt(s,'Submission and demonstration',72,205,550,42,30,{bold:true});
 bullets(s,[
  'Reproducible strategy code and closing-price CSV',
  'Fund and PM performance dashboard',
  'Actual tool calls, risk verdicts and PM memos',
  'An isolated replay of a selected historical day'
 ],72,266,550,279,26);
 txt(s,'Proposed hosting',710,205,498,42,30,{bold:true});
 bullets(s,[
  'Streamlit dashboard',
  'One Python engine with a scheduled runner',
  'SQLite on persistent storage',
  'Server-side data and model credentials'
 ],710,266,498,279,26);
 txt(s,'Ownership: three PM owners, an integration lead and a reporting/operations lead',72,584,1136,60,25);
 txt(s,'For four members, share reporting and operations. Final slides must name every member.',72,650,1136,28,22,{color:C.muted});
 note(s,'The three strategy owners provide their assets, cadence, update method and target-position interface. The integration lead owns fund accounting, allocation, risk and execution reconciliation. The reporting and operations lead owns the hosted dashboard, AI trace presentation, scheduled runs and submission outputs. For a four-person team, distribute the latter responsibilities explicitly. Names are not supplied, so this is a proposed role allocation rather than a final individual-contribution statement. A small paid Render deployment can host the dashboard and separate scheduled engine in one service. Persistent disks belong to one service instance, and native Render cron jobs cannot access them. Keep the daily engine independent of dashboard visits. Streamlit Community Cloud is a demo alternative with a separate runner because idle applications hibernate.',[brief],['https://render.com/docs/disks','https://docs.streamlit.io/deploy/streamlit-community-cloud/manage-your-app']);
}

// 12. Readiness, evidence limits and scope boundary.
{
 const s=add('Readiness and remaining inputs','The combined fund and connected AI PMs are proposed work');
 txt(s,'Existing foundation',72,204,530,42,30,{bold:true});
 bullets(s,[
  'Crypto data and daily paper workflow',
  'Agent orchestration, risk checks and logs',
  'Recorded intents and optional AI replies'
 ],72,265,530,230,27);
 txt(s,'Inputs before integration',678,204,530,42,30,{bold:true});
 bullets(s,[
  'Strategy packages, assets and momentum cadence',
  'Mandatory assets and official benchmark',
  'Capital, costs, shorting and execution rules',
  'Member names and individual responsibilities'
 ],678,265,530,277,26);
 txt(s,'First version: initial budgets, shared accounting, fund risk and AI tool access',72,567,1136,55,27,{bold:true,color:C.teal});
 txt(s,'Extensions: dynamic allocation, regime routing and physical order netting',72,628,1136,38,24,{color:C.muted});
 note(s,'The existing agent architecture is a local crypto prototype. Its execution component records intents without fills, while the separate daily runner performs paper accounting. Direct LLM provider integration is deferred. Holdings currently use non-negative units and USDT cash, so equity calendars, signed pair positions and consolidated USD sleeve accounting need adaptation. The daily BTC/ETH baseline trails its equal-weight validation benchmark. The larger futures research has a documented failed quality gate and remains a research candidate. These are evidence limits, not invented results for the new fund. As of 14 October 2026, the course evaluation window has begun. Preserve existing records, log the new fund’s actual introduction date and label earlier replays or backfills. One application and one authoritative ledger are enough for the first version.',[arch,path.join(workspaceDir,'crypto_agents/models.py'),path.join(workspaceDir,'reports/daily_portfolio/research_report.md'),path.join(workspaceDir,'freqtrade/reports/2026_million_usdt_quality/million_usdt_quality_report.md'),brief]);
}

await fs.mkdir(path.join(buildDir,'previews'),{recursive:true});
await fs.mkdir(outputDir,{recursive:true});
const candidatePath=path.join(buildDir,'candidate.pptx');
await (await PresentationFile.exportPptx(p)).save(candidatePath);
console.log('Draft exported: '+p.slides.items.length+' slides');

const finalPath=path.join(outputDir,'FE5209_Multi_Agent_Project_Expanded.pptx');
const tableOwners=[3,4,5,6,7,10];
const result=await finalizePresentation({
 workspaceDir,candidatePath,finalPath,pythonExecutable:runtimePython,
 integrityValidatorPath:path.join(skillDir,'container_tools/inspect_presentation_package_integrity.py'),
 layoutValidatorPath:path.join(skillDir,'container_tools/inspect_presentation_layout_geometry.py'),
 layoutArgs:['--expected-slide-size-emu','12192000,6858000','--validate-bullet-geometry','--validate-heading-fit',...tableOwners.flatMap(n=>['--require-native-table-slide',String(n)])],
 requiredNativeTableOwnerSlides:tableOwners,requiredNativeChartOwnerSlides:[3],
 materializeLiteralChartWorkbooks:true,
 tableArithmeticContracts:[{slide:3,table:1,label_column:0,total_row:5,value_columns:[1],component_rows:[1,2,3,4]}],
 fontPolicy:{basis:'design',families:[FONT]},verifyArtifactToolImport:true,
 receiptPath:path.join(buildDir,'validation.json')
});
console.log('Finalized: '+finalPath);

const finalDeck=await PresentationFile.importPptx(await FileBlob.load(finalPath));
for(const [i,slide] of finalDeck.slides.items.entries()) {
 const png=await finalDeck.export({slide,format:'png',scale:1});
 const filename='slide-'+String(i+1).padStart(2,'0')+'.png';
 await fs.writeFile(path.join(buildDir,'previews',filename),new Uint8Array(await png.arrayBuffer()));
 console.log('Rendered '+filename);
}
await fs.writeFile(path.join(buildDir,'inspection.ndjson'),(await finalDeck.inspect({kind:'slide,textbox,table,chart,notes',maxChars:100000})).ndjson);
console.log('Presentation previews and inspection complete');
console.log('Build directory: '+buildDir);
