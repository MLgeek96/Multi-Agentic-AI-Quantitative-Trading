"""Create PDF previews, a pitch guide, and a presentation-materials ZIP.

This is a roadshow handoff pack, not the final course submission ZIP.
Run build_roadshow.mjs first with the same build/output directory variables.
"""
from pathlib import Path
import csv
import io
import json
import os
import shutil
import textwrap
import zipfile
import xml.etree.ElementTree as ET

from pypdf import PdfReader
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak

ROOT = Path(__file__).resolve().parents[2]
BUILD = Path(os.environ.get('FE5209_DECK_BUILD_DIR', ROOT / '.codex-build/roadshow-20261017')).resolve()
OUT = Path(os.environ.get('FE5209_DECK_OUTPUT_DIR', ROOT / 'presentations/roadshow_20261017')).resolve()
PDF = Path(os.environ.get('FE5209_PDF_OUTPUT_DIR', ROOT / 'output/pdf')).resolve()
PDF.mkdir(parents=True, exist_ok=True)
OUT.mkdir(parents=True, exist_ok=True)
names = [('FE5209_Investor_Roadshow_v2', 14), ('FE5209_60_Second_Pitch_v2', 4)]
for name, count in names:
    images = sorted((BUILD / name / 'previews').glob('slide-*.png'))
    assert len(images) == count
    dest = PDF / (name + '.pdf')
    assert not dest.exists(), f'Preserve existing PDF: {dest}'
    c = canvas.Canvas(str(dest), pagesize=(960, 540), pageCompression=1)
    c.setTitle(name.replace('_', ' '))
    c.setAuthor('FE5209 project team')
    c.setSubject('Visual slide preview. Editable objects and notes are in the companion PPTX.')
    for image in images:
        c.drawImage(ImageReader(str(image)), 0, 0, width=960, height=540, mask='auto')
        c.showPage()
    c.save()
    assert len(PdfReader(dest).pages) == count
    print(f'PDF preview: {dest.name}, {count} pages')

# Verify the native allocation table in the delivered presentation.
with zipfile.ZipFile(OUT / 'FE5209_Investor_Roadshow_v2.pptx') as z:
    ns = {'a': 'http://schemas.openxmlformats.org/drawingml/2006/main'}
    rows = ET.fromstring(z.read('ppt/slides/slide4.xml')).findall('.//a:tbl/a:tr', ns)
    cells = [[''.join(x.itertext()) for x in r.findall('a:tc', ns)] for r in rows]
    assert sum(int(cells[r][1].replace(',', '')) for r in range(1,5)) == 5_000_000
    assert sum(int(cells[r][2].replace('%', '')) for r in range(1,5)) == 100

segments = json.loads((BUILD / 'pitch_segments.json').read_text(encoding='utf-8'))
word_count = sum(len(s['copy'].split()) for s in segments)
assert 120 <= word_count <= 140, word_count
plain = '\n\n'.join(f"{s['start']:02}-{s['end']:02} seconds: {s['title']}\n{s['copy']}" for s in segments)
(OUT / '60_second_pitch_script.txt').write_text(
    f'FE5209 60-second pitch narration\n{word_count} whitespace-delimited words. Rehearse to 58-60 seconds.\n'
    'Timing is a recording plan, not a measured narration duration.\n\n' + plain + '\n', encoding='utf-8')
def stamp(sec):
    return f'00:00:{sec:02},000' if sec < 60 else '00:01:00,000'
srt = '\n\n'.join(f"{i}\n{stamp(s['start'])} --> {stamp(s['end'])}\n" + '\n'.join(textwrap.wrap(s['copy'], 65)) for i,s in enumerate(segments, 1))
(OUT / '60_second_pitch_draft_subtitles.srt').write_text(srt + '\n', encoding='utf-8')

with (OUT / 'historical_crypto_evidence.csv').open('w', newline='', encoding='utf-8') as f:
    w=csv.writer(f)
    w.writerow(['model','period_start','period_end','total_return_percent','maximum_drawdown_percent','sharpe_zero_risk_free','source'])
    for row in [
        ['adaptive_trend','2024-01-01','2026-07-31',10.089,-23.778,0.321172860559578],
        ['equal_weight_BTC_ETH','2024-01-01','2026-07-31',10.768,'',''],
        ['BTC_buy_and_hold','2024-01-01','2026-07-31',42.346,'',''],
    ]:
        w.writerow(row + ['reports/daily_portfolio/research_report.md'])

announcement = '''COURSE ANNOUNCEMENT SUMMARY
Source: announcement supplied by the user in chat on 17 October 2026.

Deadline: Saturday, 24 October 2026. The announcement does not state an hour.
Required Canvas upload: one ZIP containing editable presentation slides,
supporting data and source code.
Required group-registration update: group name, all member information,
out-of-sample strategy or forecast performance, and video URL if prepared.
Video: optional but strongly encouraged, maximum 60 seconds, approximately
120-140 script words. Narrated PowerPoint is acceptable. Link must work for class.
Suggested structure: opportunity 0-10s, solution 10-25s, evidence 25-45s, pitch 45-60s.
Registration spreadsheet:
https://docs.google.com/spreadsheets/d/1N5ZyqvW8sSQpk8IlT_ByFysJfc27CKGa6ixITQDr76Y/edit?gid=0#gid=0

The original project brief separately requires daily closing prices and named
individual contributions. Its evaluation window remains 1-23 October 2026.
'''
(OUT / 'course_announcement_summary.txt').write_text(announcement, encoding='utf-8')

checklist = '''FE5209 FINAL SUBMISSION CHECKLIST - DUE 24 OCTOBER 2026

This roadshow handoff ZIP contains presentation materials only. It is not the
final course submission. Strategy source, supporting prices, final fund results,
member names and the optional video must be added or completed by the team.

BEFORE RECORDING
[ ] Agree the group/fund name and enter every member's name and responsibility.
[ ] Confirm mandatory assets, official benchmark, capital and cost conventions.
[ ] Replace proposed capability with actual capability only when demonstrated.
[ ] Add final consolidated out-of-sample evidence, with dates and trading costs.
[ ] Label historical validation, synthetic demonstrations and replays separately.
[ ] Confirm daily pairs signal time, fill time, shorting/borrow and both-leg handling.
[ ] Preserve genuine October records and the combined fund's actual start date.

CANVAS ZIP - REQUIRED
[ ] Editable roadshow PPTX, final named contribution statement, optional PDF copy.
[ ] All strategy and integration source, requirements and reproducible run commands.
[ ] Supporting data, asset identifiers, price timestamps and data provenance.
[ ] Daily closing-price CSV for every included portfolio asset.
[ ] Costed fund/PM NAV history and benchmark on the same dates and calendar.
[ ] Net P&L, return, Sharpe, volatility, MDD, trade count, win rate, profit per trade,
    holding period, and drawdown frequency/duration. Mark undefined values N/A.
[ ] Final code/data snapshot and an archive inventory. Exclude credentials/caches.
[ ] Unzip into a fresh folder and check that documented runs reproduce outputs.
[ ] Confirm the exact Canvas cutoff hour/timezone and upload one final ZIP.

REGISTRATION SHEET - REQUIRED
[ ] Group name and all members' details.
[ ] Out-of-sample performance with period, benchmark and cost convention.
[ ] Video link, if produced, accessible to the entire class.

OPTIONAL 60-SECOND VIDEO
[ ] Record the four pitch slides using the supplied narration in speaker notes.
[ ] Rehearse and shorten pauses to keep the exported MP4 at or below 60 seconds.
[ ] Add subtitles and align the draft SRT with the actual recorded speech.
[ ] Use the final group name. Keep unsupported performance claims out of the pitch.
[ ] Test playback and class access to the hosted link in a separate browser session.

SUGGESTED ROLE OWNERS - REPLACE WITH ACTUAL NAMES
Momentum PM owner: ____________________
Pairs PM owner: _______________________
Crypto PM owner: ______________________
Fund integration and risk: ____________
Reporting and operations: _____________
For a four-person team, distribute the last two responsibilities explicitly.

No Canvas submission, spreadsheet update, hosted deployment or video upload has
been performed by preparing this pack.
'''
(OUT / 'submission_checklist.txt').write_text(checklist, encoding='utf-8')

# A short companion guide with fixed page breaks for predictable reading.
styles=getSampleStyleSheet()
styles.add(ParagraphStyle(name='Title2',fontName='Helvetica-Bold',fontSize=24,leading=29,textColor=colors.HexColor('#162A3A'),spaceAfter=20))
styles.add(ParagraphStyle(name='Head2',fontName='Helvetica-Bold',fontSize=14,leading=18,textColor=colors.HexColor('#087E8B'),spaceBefore=13,spaceAfter=7))
styles.add(ParagraphStyle(name='Body2',fontName='Helvetica',fontSize=10.5,leading=15,spaceAfter=9,textColor=colors.HexColor('#162A3A')))
styles.add(ParagraphStyle(name='Small2',fontName='Helvetica',fontSize=8.5,leading=11,spaceAfter=6,textColor=colors.HexColor('#516476')))
flow=[]
def para(value,style='Body2'):
    flow.append(Paragraph(value,styles[style]))
def title(value): para(value,'Title2')
def head(value): para(value,'Head2')
def body(value): para(value)
def tbl(rows,widths):
    data=[[Paragraph(str(c),styles['Body2']) for c in row] for row in rows]
    t=Table(data,colWidths=widths,hAlign='LEFT')
    t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#EDF2F5')),('VALIGN',(0,0),(-1,-1),'TOP'),('GRID',(0,0),(-1,-1),0.4,colors.HexColor('#D9E2E8')),('TOPPADDING',(0,0),(-1,-1),7),('BOTTOMPADDING',(0,0),(-1,-1),7)]))
    flow.append(t)

title('Investor roadshow companion')
body('FE5209 academic paper fund. Prepared 17 October 2026. The new presentation uses investor language while keeping responsibility for quantitative decisions clear.')
head('The coordinator becomes the Investment Committee / CIO')
tbl([['Role','Responsibility in this project'],['Investors','Provide illustrative paper capital and evaluate reporting.'],['Board of Directors','Human student team approves the mandate, policy and material changes.'],['Investment Committee / CIO','Reviews PM evidence and applies a declared capital-allocation policy.'],['Three PMs','Own the strategy, virtual account and diagnostics for momentum, daily pairs and crypto.'],['Independent risk controller','Enforces coded limits before an execution intention.']], [145,354])
head('What the AI aspect actually means')
body('A proposed PM representative chooses relevant read-only diagnostic tools, examines computed facts and writes an explanation. Separate contexts and mandates make the representatives distinct. A future committee chair compares their memos and asks follow-up questions. AI reporting is the output of this review process.')
body('The current local prototype connects crypto and pairs, exposes diagnostic tools and accepts optional imported model replies. Automatic provider calls and autonomous tool selection remain pending. Quantitative code calculates targets. Risk code retains approval authority.')
para('Sources: fund_agents/README.md and reports/fund_agents/integration_report.md. Agent/workflow distinction: docs.langchain.com/oss/python/langgraph/workflows-agents.','Small2')
flow.append(PageBreak())

title('One-minute video plan')
body(f'The supplied script contains {word_count} whitespace-delimited words. Use the four-slide pitch deck. Planned durations total 60 seconds. Rehearsal and the exported MP4 determine actual duration.')
for s in segments:
    head(f"{s['start']}-{s['end']} seconds: {s['title']}")
    body(s['copy'].replace('’',"'"))
head('Recording and export')
body('Record narration over the pitch slides in PowerPoint or another editor. Aim for a 58-60 second export. Use a hard transition at each planned boundary. Check numbers aloud because percentages take longer to speak than their word count suggests.')
body('Add subtitles and align the draft SRT to the actual audio. Export MP4, verify its duration and play it once from start to finish. Upload it to a class-accessible location and test the share link. This pack contains no recorded MP4 or narration.')
para('The course announcement allows narrated PowerPoint. Its video is optional and capped at 60 seconds. Tool availability or pricing has not been assumed.','Small2')
flow.append(PageBreak())

title('Presenter notes and likely questions')
head('What should we say about the return evidence?')
body('The separate daily crypto baseline returned 10.089% in validation from 1 January 2024 to 31 July 2026, after its configured 10 bps turnover model. Equal-weight BTC/ETH returned 10.768%. Baseline maximum drawdown was -23.778% and zero-risk-free Sharpe was 0.321. It did not beat the reported benchmark. These figures do not establish combined-fund performance.')
head('Why combine momentum, pairs and crypto?')
body('They provide different proposed mandates, but their diversification benefit is a hypothesis. Crypto and equity momentum can share directional risk. Show measured correlations, contribution to drawdown and after-cost consolidated performance before claiming improvement.')
head('Why use USD 5 million?')
body('It is the team\'s illustrative paper-capital convention: USD 1.5m per PM and USD 0.5m central cash. It is subject to the course convention. Starting account capital is not earned return. Momentum capital stays in cash until its engine connects.')
head('What is already implemented?')
body('The local crypto/pairs integration generates proposals, diagnostic facts, risk decisions and grouped intentions. It records zero fills. Momentum, automatic AI calls, the dashboard, costed fund fills and consolidated P&L remain work to complete.')
head('How should the pairs PM run?')
body('Daily frequency is confirmed. After-close signals and next-eligible-session fills are proposed conventions requiring agreement with the strategy owner. Preserve the signed hedge relationship, actual exchange sessions and data timestamps. Validate borrow availability and the handling of partial two-leg fills.')
head('What will make the final roadshow convincing?')
body('Use one genuine recorded decision to show the PM proposals, a diagnostic investigation and a coded risk verdict. Then show the final out-of-sample NAV against the official benchmark with costs, dates and PM attribution. Name each member\'s contribution.')
para('Sources: reports/daily_portfolio/research_report.md, fund_agents/README.md, reports/fund_agents/integration_report.md and the project brief.','Small2')
flow.append(PageBreak())

title('Submission plan')
body('Deadline: Saturday, 24 October 2026. Confirm the actual Canvas cutoff hour and timezone. The course evaluation window remains 1-23 October 2026.')
head('Required: one Canvas ZIP')
body('Include editable slides, supporting data and source code. Retain the earlier brief\'s daily closing-price CSV and named contribution statement. Add requirements, run instructions, data provenance, after-cost NAV and benchmark series, and all required KPIs.')
head('Required: group registration spreadsheet')
body('Enter the group name, every member\'s information and out-of-sample strategy or forecast performance. Include a class-accessible video link if a video is prepared. The URL is preserved in course_announcement_summary.txt.')
head('Suggested work sequence')
tbl([['Date','Team action'],['17-18 Oct','Confirm roles, assets and benchmark. Review the interfaces and evidence gaps.'],['19-22 Oct','Complete only defensible integration scope. Preserve forward records and clearly label replays.'],['23 Oct','Close the evaluation window under the declared data cutoff. Freeze and reconcile final KPIs.'],['24 Oct','Finalize names and slides, record optional pitch, test the archive and submit before the actual cutoff.']], [95,404])
head('Readiness gaps the team must close')
body('Member names, momentum details, mandatory assets, official benchmark and final fund performance still need confirmation or completion. The optional narration and video link also remain to be produced. The supplied submission_checklist.txt contains the detailed checks.')
body('The roadshow ZIP is a presentation handoff pack. It contains neither a complete strategy/data submission nor a finished video. No Canvas upload or spreadsheet edit has taken place.')
para('Submission requirements source: course announcement supplied in chat on 17 October 2026. Earlier requirements source: algorithmic_trading_strategy_project_brief_execution_roadmap.md.','Small2')

guide=PDF/'FE5209_Roadshow_Pitch_and_Submission_Guide.pdf'
assert not guide.exists(), guide
def footer(c,doc):
    c.saveState();c.setFont('Helvetica',8);c.setFillColor(colors.HexColor('#516476'))
    c.drawString(48,29,'FE5209 paper-fund roadshow / 17 October 2026')
    c.drawRightString(547,29,str(doc.page));c.restoreState()
doc=SimpleDocTemplate(str(guide),pagesize=(595,842),leftMargin=48,rightMargin=48,topMargin=44,bottomMargin=50,title='FE5209 roadshow, pitch and submission guide',author='FE5209 project team')
doc.build(flow,onFirstPage=footer,onLaterPages=footer)
assert len(PdfReader(guide).pages)==4
print(f'Guide: 4 pages. Pitch: {word_count} words.')

# Archive only reviewed user deliverables and portable authoring sources.
archive=OUT/'FE5209_Roadshow_Materials.zip'
assert not archive.exists(), archive
with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED) as z:
    for name,_ in names:
        z.write(OUT/(name+'.pptx'),'slides/'+name+'.pptx')
        z.write(PDF/(name+'.pdf'),'previews/'+name+'.pdf')
    z.write(guide,'FE5209_Roadshow_Pitch_and_Submission_Guide.pdf')
    for name in ['60_second_pitch_script.txt','60_second_pitch_draft_subtitles.srt','historical_crypto_evidence.csv','course_announcement_summary.txt','submission_checklist.txt']:
        z.write(OUT/name,name)
    for name in ['build_roadshow.mjs','export_roadshow_pack.py']:
        z.write(ROOT/'presentations/source'/name,'build_sources/'+name)
    for name in ['ARCHITECTURE.md','fund_agents/README.md','reports/fund_agents/integration_report.md','reports/daily_portfolio/research_report.md','algorithmic_trading_strategy_project_brief_execution_roadmap.md']:
        z.write(ROOT/name,'evidence_sources/'+name)
    start = OUT / 'START_HERE.txt'
    if start.exists():
        z.write(start, 'START_HERE.txt')
print('Presentation materials archive: '+str(archive))
