import fs from 'node:fs/promises';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath, pathToFileURL } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const build = path.resolve(process.env.FE5209_DECK_BUILD_DIR || path.join(root, '.codex-build/roadshow-20261017'));
const output = path.resolve(process.env.FE5209_DECK_OUTPUT_DIR || path.join(root, 'presentations/roadshow_20261017'));
const skill = process.env.FE5209_PRESENTATION_SKILL_DIR;
const python = process.env.RUNTIME_PYTHON;
if (!skill || !python || !process.env.RUNTIME_NODE_MODULES) throw new Error('Set the bundled runtime and presentation skill environment variables.');
const req = createRequire(path.join(process.env.RUNTIME_NODE_MODULES, 'package.json'));
const { Presentation, PresentationFile, FileBlob } = await import(pathToFileURL(req.resolve('@oai/artifact-tool')).href);
const { finalizePresentation, resolvePresentationFont, applyPresentationChartFont, makeNativeBulletParagraphs } = await import(pathToFileURL(path.join(skill, 'container_tools/artifact_tool_utils.mjs')).href);
const FONT = resolvePresentationFont({ fontFamily: 'Arial' });
const C = { ink:'#162A3A', muted:'#516476', white:'#FFFFFF', teal:'#087E8B', blue:'#2864A0', purple:'#7757A1', gray:'#80909B', line:'#D9E2E8', header:'#EDF2F5' };
const SRC = {
 brief:'algorithmic_trading_strategy_project_brief_execution_roadmap.md',
 integration:'reports/fund_agents/integration_report.md',
 fund:'fund_agents/README.md', crypto:'reports/daily_portfolio/research_report.md'
};
const agentSource = 'https://docs.langchain.com/oss/python/langgraph/workflows-agents';
const quantSource = 'https://waylandz.com/quant-book-en/Lesson-14-LLM-Applications-in-Quant/';
function deck() { return Presentation.create({ slideSize:{width:1280,height:720} }); }
function text(s, value, x,y,w,h,size=27, {color=C.ink,bold=false,align='left'}={}) {
 const a=s.shapes.add({geometry:'textbox',name:value.split('\n')[0].slice(0,80),position:{left:x,top:y,width:w,height:h},fill:'none',line:{fill:'none',width:0}});
 a.text=value;
 a.text.style={typeface:FONT,fontSize:size,color,bold,alignment:align,verticalAlignment:'top',insets:0,wrap:'square',autoFit:'none'};
 return a;
}
function slide(p,title,subtitle='') {
 const s=p.slides.add();s.background.fill=C.white;
 text(s,title,72,48,1136,70,44,{bold:true});
 if(subtitle)text(s,subtitle,72,126,1136,58,25,{color:C.muted});
 text(s,String(p.slides.items.length).padStart(2,'0'),1150,676,58,22,17,{color:C.muted,align:'right'});
 return s;
}
function list(s,items,x,y,w,h,size=27) {
 const a=text(s,'',x,y,w,h,size);
 a.text=makeNativeBulletParagraphs(items,{marginLeftPoints:18,hangingPoints:9,spaceAfterPoints:13});
 return a;
}
function table(s,values,x,y,w,h,widths,size=25) {
 const t=s.tables.add({rows:values.length,columns:values[0].length,left:x,top:y,width:w,height:h,columnWidths:widths,values});
 t.styleOptions={headerRow:true,bandedRows:false};t.borders.assign({fill:C.line,width:0.7,style:'solid'});
 t.cells.block({row:0,column:0,rowCount:values.length,columnCount:values[0].length}).assign({margins:{top:10,bottom:10,left:12,right:12},anchor:'center'});
 for(let r=0;r<values.length;r++){t.rows[r].height=h/values.length;for(let c=0;c<values[r].length;c++){
  const cell=t.getCell(r,c);cell.fill=r===0?C.header:C.white;
  cell.text.style={typeface:FONT,fontSize:size,color:C.ink,bold:r===0,verticalAlignment:'middle',autoFit:'none'};
 }}return t;
}
function notes(s,value,local=[],web=[]){s.speakerNotes.text=value+'\n\n'+local.map(x=>'Repository source: '+x).concat(web.map(x=>'Source: '+x)).join('\n');}
function chart(s,{categories,values,x,y,w,h,colors,format='0.00'}){
 const ch=s.charts.add('bar',{
  position:{left:x,top:y,width:w,height:h},categories,
  series:[{name:'Value',values,fill:C.blue,valuesFormatCode:format,points:values.map((v,idx)=>({idx,fill:colors?.[idx]||C.blue}))}],
  hasLegend:false,barOptions:{direction:'bar',grouping:'clustered',gapWidth:65},
  xAxis:{visible:true,majorGridlines:null,textStyle:{typeface:FONT,fontSize:24,fill:C.muted},line:{fill:'none',width:0}},
  yAxis:{visible:false,majorGridlines:null,line:{fill:'none',width:0}},
  dataLabels:{showValue:true,position:'outEnd',numberFormatCode:format,textStyle:{typeface:FONT,fontSize:25,fill:C.ink}},
  chartFill:'none',chartLine:{fill:'none',width:0},plotAreaFill:'none',plotAreaLine:{fill:'none',width:0}
 });applyPresentationChartFont(ch,{fontFamily:FONT});return ch;
}
// Editable governance diagram. The Board and investors are presentation roles.
function governance(s,{top=195,compact=false}={}){
 const cx=compact?620:640;
 const a=text(s,'Investors',cx-210,top,420,39,30,{bold:true,align:'center'});
 const b=text(s,'Board of Directors',cx-260,top+81,520,39,30,{bold:true,align:'center'});
 const c=text(s,'Investment Committee / CIO',cx-310,top+164,620,42,31,{bold:true,color:C.teal,align:'center'});
 const d=[text(s,'Momentum PM',82,top+288,320,43,29,{bold:true,color:C.blue,align:'center'}),text(s,'Daily Pairs PM',480,top+288,320,43,29,{bold:true,color:C.teal,align:'center'}),text(s,'Crypto PM',878,top+288,320,43,29,{bold:true,color:C.purple,align:'center'})];
 for(const [from,to] of [[a,b],[b,c],...d.map(x=>[c,x])])s.shapes.connect(from,to,{fromSide:'bottom',toSide:'top',kind:'elbow',line:{fill:C.gray,width:1.7},tail:{type:'triangle',width:'sm',length:'sm'}});
 return {a,b,c,d};
}

const p=deck();
// 1
{
 const s=p.slides.add();s.background.fill=C.ink;
 text(s,'Three PM Quant Fund',72,175,1136,94,68,{bold:true,color:C.white});
 text(s,'An AI-assisted paper investment platform',72,303,1136,62,35,{color:'#C9E1E8'});
 text(s,'Equity momentum, daily pairs trading and crypto',72,417,1136,61,29,{color:C.white});
 text(s,'FE5209 investor roadshow\n17 October 2026',72,580,1000,65,24,{color:'#C9E1E8'});
 notes(s,'This academic paper-fund design uses USD 5 million of illustrative capital. The proposed organization gives investors the capital-provider role, the student team the Board role, and an Investment Committee the former portfolio-coordinator role. Crypto and pairs are connected in a local record-only prototype. Momentum, automatic AI calls, fund fills and a consolidated performance history remain pending. The title is a descriptive working title, not a registered fund name.',[SRC.brief,SRC.integration]);
}
// 2
{
 const s=slide(p,'The investor opportunity','A proposed way to review several quantitative strategies as one accountable fund');
 text(s,'Investment problem',72,214,530,43,31,{bold:true});
 list(s,['A single trading style can struggle when conditions change','Separate strategy reports can hide overlapping exposure','Investors need to understand why capital is at risk'],72,282,530,285,28);
 text(s,'Our fund design',678,214,530,43,31,{bold:true});
 list(s,['Three PM mandates with separate virtual accounts','One Investment Committee and common risk controls','AI explanations linked to computed strategy evidence'],678,282,530,285,28);
 text(s,'Diversification and better investor understanding are hypotheses to test',72,621,1136,44,25,{color:C.teal,bold:true});
 notes(s,'The investor proposition is an organized way to assess complementary strategies and their combined risk. Equity momentum and crypto trend signals can share directional market risk, so different strategy names do not establish diversification. Test correlations, drawdowns and contribution to risk before making a performance claim. The commercial framing supports the course roadshow and does not represent actual external fundraising.',[SRC.brief,SRC.fund]);
}
// 3
{
 const s=slide(p,'Fund governance','Proposed presentation roles with clear responsibility for capital');
 governance(s);
 text(s,'Capital providers',914,198,294,36,23,{color:C.muted});
 text(s,'Human team oversight',914,279,294,36,23,{color:C.muted});
 text(s,'Mandates and allocation',914,362,294,36,23,{color:C.muted});
 text(s,'Independent coded risk approval precedes execution',72,609,1136,50,28,{bold:true,color:C.teal});
 notes(s,'Investors supply paper capital and receive reporting. The Board of Directors is a simulated governance role performed by the human student team. It approves the mandate, risk policy and changes. The Investment Committee, led by a CIO role, replaces the presentation label Portfolio Coordinator. Quantitative allocation code implements its declared capital policy. A future AI chair may summarize PM evidence and challenge proposals, but cannot override coded risk. Each PM retains its own quant engine and virtual account. Keep the implementation module names unchanged for this presentation revision. The organization is a demonstration design, not a claim of legally constituted corporate governance.',[SRC.fund,SRC.integration]);
}
// 4
{
 const s=slide(p,'USD 5m paper-capital mandate','Illustrative starting capital, subject to the course convention');
 const values=[1500000,1500000,1500000,500000];const names=['Momentum PM','Pairs PM','Crypto PM','Central cash'];const total=values.reduce((a,b)=>a+b,0);
 table(s,[['Mandate','USD','Share'],...names.map((n,i)=>[n,values[i].toLocaleString('en-US'),(values[i]/total*100)+'%']),['Total fund',total.toLocaleString('en-US'),'100%']],72,203,605,352,[250,190,165],24);
 text(s,'Initial capital, USD millions',745,207,463,40,26,{bold:true});
 chart(s,{categories:['Momentum','Pairs','Crypto','Cash'],values:values.map(x=>x/1e6),x:735,y:267,w:473,h:285,colors:[C.blue,C.teal,C.purple,C.gray],format:'0.0'});
 text(s,'Initial budgets stay fixed. Returns cause each PM’s fund weight to drift.',72,594,1136,45,26);
 text(s,'Current prototype: momentum capital stays in cash until its engine connects.',72,643,1136,30,23,{color:C.muted});
 notes(s,'USD 1.5 million is a capital mandate for each PM, with USD 0.5 million centrally. These sum to USD 5 million and 100%. A mandate does not force full investment. The first experiment keeps initial capital in each sleeve without discretionary transfers. The Investment Committee sets this policy before the run. Dynamic reallocation is an optional future experiment and needs cost and transfer accounting. The current prototype reserves the momentum allocation in cash. The initial USD 5 million is a supplied account value and is not earned performance.',[SRC.fund,SRC.integration]);
}
// 5
{
 const s=slide(p,'The three PM mandates','Each PM owns its strategy and an attributable virtual portfolio');
 table(s,[['PM','Investment approach','Current status'],['Equity momentum','Teammate stock-selection rule\nUniverse and cadence to confirm','Integration pending'],['Daily pairs','Teammate Kalman hedge estimate\nand mean-reverting spread forecast','Adapter connected\nV/MA research setup'],['Crypto','Existing crypto signal engine\nLong exposure or cash','Adapter connected\nDaily baseline separate']],72,205,1136,326,[250,556,330],25);
 text(s,'Common PM output: target holdings, timestamps, model version and evidence',72,579,1136,58,28,{bold:true,color:C.teal});
 notes(s,'The daily pairs adapter imports the teammate’s Kalman, OU and forecasting engines, with recorded provenance and local integration corrections. V/MA is the current research configuration, not a finalized class universe. Preserve signed legs and the hedge relationship. Crypto in the integrated prototype wraps crypto_agents.MetaAgent. The historical adaptive-trend performance discussed later belongs to the separate daily_portfolio baseline, not this integrated crypto adapter. Momentum needs its actual package and mandate. Every included asset must satisfy the course eligibility rule and mandatory class asset requirement.',[SRC.fund,SRC.integration,SRC.brief]);
}
// 6
{
 const s=slide(p,'The multi-agent AI role','Separate PM contexts, diagnostic tools and evidence-linked explanations');
 table(s,[['AI representative','Questions it investigates','Investor-facing memo'],['Momentum PM AI','Rankings, concentration\nand proposed holdings','Why these stocks?\nWhere is exposure concentrated?'],['Pairs PM AI','Spread signal, hedge ratio\nand model health','Why this linked trade?\nWhat could invalidate the spread?'],['Crypto PM AI','Signal qualification, costs\nand volatility','Why take exposure or hold cash?\nWhich inputs need review?']],72,205,1136,326,[259,443,434],25);
 text(s,'Planned AI committee chair compares PM memos and records unresolved issues',72,567,1136,60,27,{bold:true,color:C.teal});
 text(s,'Current tools and imported replies exist. Automatic model calls remain pending.',72,643,1136,30,23,{color:C.muted});
 notes(s,'The proposed AI contribution is investigation and explanation. An agent dynamically chooses allowed diagnostic tools, while a fixed call sequence is a workflow. The same language model may support multiple PM representatives through distinct mandates and contexts. The current two-PM prototype exposes inspect_signals, inspect_model_health and inspect_positions. Default runs call all three and generate computed evidence. Optional imported tool selections and digest-checked replies exist. Automatic provider calls and autonomous selection remain pending. The proposed committee chair reviews reports and asks follow-up questions. Quantitative code still calculates holdings and independent code approves risk. AI-on/off evaluation holds targets constant and measures factual accuracy, citation coverage, review time, latency and model cost.',[SRC.fund],[agentSource,quantSource]);
}
// 7
{
 const s=slide(p,'The Investment Committee meeting','Illustrative demonstration sequence, to replace with actual saved tool traces');
 table(s,[['Participant','Review question','Evidence shown'],['Pairs PM AI','Do both legs preserve\nthe intended hedge?','Signed target legs and\nhedge-ratio diagnostics'],['Crypto PM AI','Why does the engine\npropose exposure or cash?','Signal qualification and\nlocal risk verdict'],['Committee / CIO','Where do PM proposals\nshare fund exposure?','Combined gross exposure\nand symbol limits'],['Risk controller','Does the proposal satisfy\nthe approved policy?','Coded approval or rejection\nwith a saved reason']],72,203,1136,369,[280,435,421],25);
 text(s,'The Board reviews policy and exceptions. The ledger preserves each decision.',72,618,1136,49,26,{bold:true,color:C.teal});
 notes(s,'These are demonstration questions rather than a fabricated agent conversation. The existing local engine can provide proposals, diagnostics, risk verdicts and intention receipts for crypto and pairs. A real model-generated response must be identified as such and linked to its exact input digest. Default diagnostic output is computed evidence, not evidence that an LLM ran. Use an actual saved run for the class demo, and label synthetic inputs and historical replays. A future AI chair can synthesize the memos, but allocation follows a predeclared code policy and the risk controller remains final.',[SRC.fund,SRC.integration]);
}
// 8
{
 const s=slide(p,'The daily pairs decision cycle','Daily frequency is confirmed. Exact signal and fill timing still needs agreement.');
 table(s,[['Time','Owner','Output'],['After session t close','Data and Pairs PM','Validated closes and linked target legs'],['Before execution','Investment Committee / CIO','Mandate policy and combined exposure'],['Before execution','Independent risk controller','Approval or rejection with reasons'],['Next eligible session','Proposed paper-fill adapter','Costed fills, subject to borrow and leg handling'],['After valuation','Accounting and PM reporting','Fund NAV, closing-price CSV and memos']],72,203,1136,380,[278,355,503],24);
 text(s,'Current integration records intentions and zero fills',72,619,1136,47,29,{bold:true,color:C.teal});
 notes(s,'After-close signal formation and next-session fills are a proposed integration convention. Confirm the teammate’s original timestamps and execution assumptions. A signal computed using a completed close cannot claim a fill at that same already-observed close. Equity sessions differ from the 24/7 crypto calendar. The existing adapter checks the configured exchange calendar and preserves actual source session dates on closed-market days. Its inspected equity cache ends in August 2026, so it cannot establish October live evidence. A daily signal can correctly result in no trade.',[SRC.fund,SRC.integration,SRC.brief]);
}
// 9
{
 const s=slide(p,'Independent risk and fund accounting','The committee works within a declared risk policy');
 text(s,'Current coded controls',72,208,530,42,31,{bold:true});
 list(s,['80% fund gross-exposure limit','20% gross exposure per symbol','Linked scaling preserves each pair’s hedge','25% fund drawdown breaker stays latched'],72,274,530,287,27);
 text(s,'Accounting still to complete',678,208,530,42,31,{bold:true});
 list(s,['Confirm holdings before valuing the account','Add costed fills and short-position financing','Reconcile PM P&L with consolidated fund NAV','Record capital transfers separately from return'],678,274,530,287,27);
 text(s,'Fund NAV = sum of PM NAVs + central cash',72,616,1136,45,31,{bold:true,color:C.teal});
 notes(s,'Limits are current prototype configuration defaults, not a proof of safe or profitable execution. Fund gross exposure counts positions across sleeves before netting. Cash, collateral buffers and fee reserves constrain connected mandates. Risk uses one common factor for actionable target groups to preserve pair relationships. Existing crypto risk checks remain upstream. Closed markets retain confirmed units. Missing PM inputs hold the cycle. Record-only execution does not charge simulated fees or create new holdings. The future fill adapter needs executable quotes, borrow checks, board lots, linked fills, costs and proper marked accounting before a fund return is claimed.',[SRC.fund,SRC.integration]);
}
// 10
{
 const s=slide(p,'Historical crypto evidence','Separate daily baseline, 1 January 2024 to 31 July 2026 validation');
 text(s,'Total return, percent',72,202,670,41,28,{bold:true});
 chart(s,{categories:['Adaptive trend','Equal-weight BTC/ETH','BTC buy-and-hold'],values:[10.089,10.768,42.346],x:72,y:268,w:690,h:271,colors:[C.teal,C.gray,C.gray],format:'0.00'});
 text(s,'Baseline risk',848,203,360,43,30,{bold:true});
 text(s,'−23.78%',848,275,360,70,52,{bold:true,color:C.teal});
 text(s,'Maximum drawdown',848,349,360,40,25,{color:C.muted});
 text(s,'0.32',848,423,360,61,49,{bold:true});
 text(s,'Sharpe, zero risk-free rate',848,491,360,60,25,{color:C.muted});
 text(s,'10 bps turnover cost model. The baseline trails both reported benchmarks.',72,581,1136,42,25,{bold:true});
 text(s,'Historical baseline evidence does not establish integrated-fund or October performance.',72,636,1136,34,23,{color:C.muted});
 notes(s,'Source report: 943 validation observations. Adaptive trend returned 10.089%, maximum drawdown -23.778%, Sharpe 0.3211728606 at zero risk-free rate, with 29 closed round trips. BTC buy-and-hold returned 42.346% and equal-weight BTC/ETH returned 10.768%. The report includes the configured 10 bps turnover charge, but excludes taxes, outages, spread history and market impact. These are walk-forward validation results for crypto_quant.daily_portfolio and must not be attributed to the crypto_agents.MetaAgent integrated adapter or the full fund. The baseline does not support an outperformance claim. The proposed fund still needs independent consolidated evaluation.',[SRC.crypto,SRC.brief,SRC.integration]);
}
// 11
{
 const s=slide(p,'Evidence for the investor review','Current local capability and the remaining performance gap');
 table(s,[['Evidence','Current position'],['Two-PM local integration','Crypto and daily pairs proposals, diagnostics and risk\nRecorded intentions with zero fills'],['Momentum and connected AI','Momentum package and automatic AI calls pending\nOptional imported replies already supported'],['Combined fund performance','No costed consolidated return history yet\nInitial USD 5m account is supplied capital'],['October evaluation','Course window: 1–23 October 2026\nPreserve genuine forward records and label replays']],72,201,1136,365,[350,786],25);
 text(s,'Final scorecard: net return, benchmark, Sharpe, drawdown and trading statistics',72,608,1136,59,27,{bold:true,color:C.teal});
 notes(s,'The integration report records a deterministic demo and an August historical replay, with zero fills. Those demonstrate orchestration and safety controls rather than investment returns. Before presenting final performance, add a consolidated costed ledger, data provenance and the actual start date for the combined fund. The course requires net P&L, total and annualized return, Sharpe, volatility, maximum drawdown, win rate, profit per trade, trade frequency, holding period, and drawdown frequency and duration. Use the official benchmark and mandatory assets once confirmed. A partial or replayed October series must be labeled honestly. Avoid tuning to the October window.',[SRC.integration,SRC.brief]);
}
// 12
{
 const s=slide(p,'The hosted investor demonstration','One small application is enough for the first version');
 text(s,'Investor view',72,211,530,43,31,{bold:true});
 list(s,['Fund NAV and each PM’s contribution','Current holdings and capital mandates','PM explanations with source diagnostics','Committee decisions and risk verdicts'],72,279,530,280,27);
 text(s,'Proposed operating setup',678,211,530,43,31,{bold:true});
 list(s,['One Streamlit dashboard','Python runner on a daily schedule','SQLite on persistent storage','Server-side credentials and a saved run history'],678,279,530,280,27);
 text(s,'Class demo: one saved day, actual inputs, PM proposals, risk decision and receipts',72,608,1136,61,26,{bold:true,color:C.teal});
 notes(s,'The dashboard and deployment remain proposed. Preserve the existing Python engines and add a small presentation layer, rather than a service per agent. Daily runs must continue independently of dashboard visits. Keep database state on persistent storage and model credentials on the server. Demonstrate one genuine recorded cycle, with clear synthetic or historical labels. Until fills and accounting exist, show proposal and intention history instead of a fabricated NAV chart. This is an implementation recommendation based on the local design, not a deployed-service claim.',[SRC.fund,SRC.integration]);
}
// 13
{
 const s=slide(p,'Submission and team accountability','Saturday, 24 October 2026, according to the new course announcement');
 text(s,'Required Canvas ZIP',72,210,530,43,31,{bold:true});
 list(s,['Editable presentation slides','Supporting data and closing-price CSV','Reproducible source code','Named individual contribution statement'],72,278,530,267,27);
 text(s,'Required registration sheet',678,210,530,43,31,{bold:true});
 list(s,['Group name and every member’s details','Out-of-sample strategy performance','Class-accessible video link, if prepared'],678,278,530,244,27);
 text(s,'Optional pitch: maximum 60 seconds. A narrated PowerPoint is sufficient.',72,580,1136,49,27,{bold:true,color:C.teal});
 text(s,'Role owners: Momentum PM, Pairs PM, Crypto PM, integration/risk and reporting',72,641,1136,32,23,{color:C.muted});
 notes(s,'Source: the course announcement pasted by the user on 17 October 2026. It sets Saturday 24 October as the submission date, requires one Canvas ZIP containing editable slides, supporting data and source code, and requires an update to the group registration spreadsheet with all members and out-of-sample performance. A shareable video link is required only if a video is prepared. The video is optional but strongly encouraged and must be at most 60 seconds. The announcement does not specify a submission hour, so verify the Canvas time and timezone. The earlier project brief additionally requires daily closing prices and explicit individual attribution. Names, group name, final performance and video URL remain team inputs. Spreadsheet URL: https://docs.google.com/spreadsheets/d/1N5ZyqvW8sSQpk8IlT_ByFysJfc27CKGa6ixITQDr76Y/edit?gid=0#gid=0',[SRC.brief]);
}
// 14
{
 const s=slide(p,'The investment case','A paper pilot whose decisions classmates can inspect');
 text(s,'Three specialist PM mandates',72,219,1136,54,38,{bold:true});
 text(s,'An Investment Committee accountable to a human Board',72,317,1136,54,35,{bold:true});
 text(s,'AI explanations grounded in strategy diagnostics',72,415,1136,54,35,{bold:true,color:C.teal});
 text(s,'Our ask: assess the pilot using the final costed out-of-sample evidence',72,568,1136,80,32,{bold:true});
 notes(s,'Close by inviting classmates to evaluate the academic paper pilot and challenge its evidence. Explain how each PM generates a proposal, what the committee reviews, and why coded risk retains authority. State the remaining gaps when asked. The investment case depends on final after-cost results, benchmark comparison and reproducibility, rather than an assumed benefit from AI or diversification. This class roadshow makes no claim of actual fundraising, operational deployment or full-fund profitability.',[SRC.integration,SRC.brief]);
}

const segments = [
 {start:0,end:10,title:'The opportunity',copy:'Investors face a familiar problem: one trading style can struggle when markets change, while separate reports hide the portfolio’s combined risks.'},
 {start:10,end:25,title:'Our solution',copy:'Our proposed five-million-dollar paper fund combines equity momentum, daily pairs trading and crypto. An Investment Committee sets PM mandates under a human Board. AI representatives would investigate diagnostics and explain the evidence.'},
 {start:25,end:45,title:'The evidence',copy:'Our local prototype connects crypto and pairs with independent risk checks. The prototype records intentions, with zero fills. Historical crypto validation returned 10.09 percent after modelled turnover costs, versus 10.77 percent for equal-weight bitcoin and ether. Full-fund results remain pending.'},
 {start:45,end:60,title:'The pitch',copy:'We invite you to assess a transparent paper pilot: inspect every proposal, challenge every explanation, and judge the final out-of-sample results. The goal is a fund you can understand and audit.'}
];
const q=deck();
{
 const s=q.slides.add();s.background.fill=C.ink;
 text(s,'A fund you can inspect',72,183,1136,100,64,{bold:true,color:C.white});
 text(s,'Three PM Quant Fund',72,335,1136,63,35,{color:'#C9E1E8'});
 text(s,'One paper fund with a shared view of risk',72,447,1136,58,31,{color:C.white});
 text(s,'FE5209 academic project',72,615,1136,35,23,{color:'#C9E1E8'});
 notes(s,'0–10 seconds\n\n'+segments[0].copy+'\n\nWorking descriptive title. Academic paper proposal.');
}
{
 const s=slide(q,'The proposed fund','10–25 seconds');
 text(s,'USD 5m paper capital',72,214,1136,65,48,{bold:true,color:C.teal});
 table(s,[['PM mandate','Initial capital'],['Equity momentum','USD 1.5m'],['Daily pairs trading','USD 1.5m'],['Crypto','USD 1.5m'],['Central cash','USD 0.5m']],72,308,700,300,[430,270],27);
 text(s,'Human Board',848,311,360,46,31,{bold:true});
 text(s,'Investment\nCommittee / CIO',848,390,360,89,31,{bold:true});
 text(s,'AI PM diagnostics\nand explanations',848,527,360,86,28,{color:C.teal,bold:true});
 notes(s,'10–25 seconds\n\n'+segments[1].copy+'\n\nAllocation is illustrative. Board oversight, AI representatives and committee presentation roles are proposed. Current momentum mandate stays in cash.',[SRC.fund]);
}
{
 const s=slide(q,'Evidence to date','25–45 seconds');
 text(s,'10.09%',72,235,530,99,70,{bold:true,color:C.teal});
 text(s,'Crypto baseline validation return',72,348,530,66,30,{bold:true});
 text(s,'10.77% equal-weight BTC/ETH',72,448,530,72,30);
 text(s,'Local crypto + pairs prototype',678,243,530,70,32,{bold:true});
 text(s,'Recorded intentions, zero fills',678,312,530,39,24,{color:C.muted});
 text(s,'Independent coded risk checks',678,365,530,55,29);
 text(s,'Full-fund results pending',678,471,530,55,29,{bold:true,color:C.teal});
 text(s,'1 Jan 2024–31 Jul 2026. Baseline includes a 10 bps turnover cost model.',72,606,1136,58,24,{color:C.muted});
 notes(s,'25–45 seconds\n\n'+segments[2].copy+'\n\nThe historical baseline belongs to the separate daily portfolio workflow. It trails the equal-weight benchmark. The integrated prototype records intentions with zero fills and no consolidated P&L.',[SRC.crypto,SRC.integration]);
}
{
 const s=slide(q,'An auditable paper pilot','45–60 seconds');
 text(s,'Every PM proposal has a record',72,228,1136,64,43,{bold:true});
 text(s,'Every risk decision has a reason',72,347,1136,64,43,{bold:true});
 text(s,'Final results must justify the investment case',72,466,1136,94,41,{bold:true,color:C.teal});
 text(s,'FE5209 paper-fund demonstration',72,629,1136,33,24,{color:C.muted});
 notes(s,'45–60 seconds\n\n'+segments[3].copy+'\n\nInvite evaluation by classmates. Make no promise of returns. Use the final team name and member details when supplied.');
}

await fs.mkdir(output,{recursive:true});
await fs.mkdir(build,{recursive:true});
await fs.writeFile(path.join(build,'pitch_segments.json'),JSON.stringify(segments,null,2));
async function finish(p,name,tables,charts,arithmetic=[]){
 const tmp=path.join(build,name);await fs.mkdir(path.join(tmp,'previews'),{recursive:true});
 const candidate=path.join(tmp,'candidate.pptx');const final=path.join(output,name+'.pptx');
 await (await PresentationFile.exportPptx(p)).save(candidate);
 console.log('Draft '+name+': '+p.slides.items.length+' slides');
 await finalizePresentation({workspaceDir:root,candidatePath:candidate,finalPath:final,pythonExecutable:python,
  integrityValidatorPath:path.join(skill,'container_tools/inspect_presentation_package_integrity.py'),
  layoutValidatorPath:path.join(skill,'container_tools/inspect_presentation_layout_geometry.py'),
  layoutArgs:['--expected-slide-size-emu','12192000,6858000','--validate-bullet-geometry','--validate-heading-fit',...tables.flatMap(n=>['--require-native-table-slide',String(n)])],
  requiredNativeTableOwnerSlides:tables,requiredNativeChartOwnerSlides:charts,materializeLiteralChartWorkbooks:true,
  tableArithmeticContracts:arithmetic,fontPolicy:{basis:'design',families:[FONT]},verifyArtifactToolImport:true,receiptPath:path.join(tmp,'validation.json')});
 const finalDeck=await PresentationFile.importPptx(await FileBlob.load(final));
 for(const [i,s] of finalDeck.slides.items.entries()){
  const png=await finalDeck.export({slide:s,format:'png',scale:1});
  await fs.writeFile(path.join(tmp,'previews','slide-'+String(i+1).padStart(2,'0')+'.png'),new Uint8Array(await png.arrayBuffer()));
 }
 await fs.writeFile(path.join(tmp,'inspection.ndjson'),(await finalDeck.inspect({kind:'slide,textbox,table,chart,notes',maxChars:150000})).ndjson);
 console.log('Finalized and rendered '+final);
}
await finish(p,'FE5209_Investor_Roadshow_v2',[4,5,6,7,8,11],[4,10],[{slide:4,table:1,label_column:0,total_row:5,value_columns:[1],component_rows:[1,2,3,4]}]);
await finish(q,'FE5209_60_Second_Pitch_v2',[2],[]);
console.log('Build directory: '+build);
