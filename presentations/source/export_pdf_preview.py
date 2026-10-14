from pathlib import Path
import argparse
import os
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from pypdf import PdfReader
import zipfile
import xml.etree.ElementTree as ET

workspace = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser(description='Export a PDF preview from the rendered expanded deck')
parser.add_argument('--build-dir', type=Path, default=Path(os.environ.get('FE5209_DECK_BUILD_DIR', workspace / '.codex-build/fe5209-deck-rebuild')))
parser.add_argument('--output', type=Path)
parser.add_argument('--pptx', type=Path)
args = parser.parse_args()
build = args.build_dir.resolve()
exports = Path(os.environ.get('FE5209_DECK_OUTPUT_DIR', build / 'exports')).resolve()
output = args.output or exports / 'FE5209_Multi_Agent_Project_Expanded.pdf'
output.parent.mkdir(parents=True,exist_ok=True)
assert not output.exists(), 'Preserve an existing output'
slides = sorted((build/'previews').glob('slide-*.png'))
assert len(slides)==12
c = canvas.Canvas(str(output),pagesize=(960,540),pageCompression=1)
c.setTitle('FE5209 multi-agent quantitative fund - scope and design')
c.setAuthor('FE5209 project team')
c.setSubject('Twelve-slide visual preview. Editable text, tables, chart and speaker notes are in the PPTX.')
for slide in slides:
 c.drawImage(ImageReader(str(slide)),0,0,width=960,height=540,preserveAspectRatio=True,mask='auto')
 c.showPage()
c.save()
reader=PdfReader(output)
assert len(reader.pages)==12
assert all(float(p.mediabox.width)==960 and float(p.mediabox.height)==540 for p in reader.pages)

# Verify the allocation directly from the final native table, including percentages.
pptx = args.pptx or exports / 'FE5209_Multi_Agent_Project_Expanded.pptx'
with zipfile.ZipFile(pptx) as z:
 root=ET.fromstring(z.read('ppt/slides/slide3.xml'))
 ns={'a':'http://schemas.openxmlformats.org/drawingml/2006/main'}
 rows=root.findall('.//a:tbl/a:tr',ns)
 cells=[[''.join(tc.itertext()) for tc in row.findall('a:tc',ns)] for row in rows]
 dollars=[int(cells[r][1].replace(',','')) for r in range(1,5)]
 shares=[int(cells[r][2].replace('%','')) for r in range(1,5)]
 assert sum(dollars)==int(cells[5][1].replace(',',''))==5_000_000
 assert sum(shares)==int(cells[5][2].replace('%',''))==100
print('PDF preview: 12 pages. Final native table reconciles USD 5m and 100%.')
print(output)
