import fs from "node:fs/promises";
import path from "node:path";
import { FileBlob, SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const projectRoot = process.env.CRYPTO_FREQTRADE_ROOT
  ? path.resolve(process.env.CRYPTO_FREQTRADE_ROOT)
  : path.resolve(import.meta.dirname, "../..");
const outputDir = path.join(projectRoot, "reports", "2025_sequence_baseline");
const inputPath = path.join(outputDir, "report_data.json");
const outputPath = path.join(outputDir, "backtest_results.xlsx");
const previewPath = path.join(outputDir, "backtest_results_preview.png");

if (process.argv.includes("--inspect-only")) {
  const existing = await SpreadsheetFile.importXlsx(await FileBlob.load(outputPath));
  const inspection = await existing.inspect({
    kind: "sheet,table,drawing",
    include: "id,name,type,title",
    maxChars: 5000,
  });
  console.log(inspection.ndjson);
  const existingPreview = await existing.render({
    sheetName: "Summary",
    range: "A1:M40",
    scale: 1,
    format: "png",
  });
  const inspectionDir = path.resolve(projectRoot, "..", ".codex_work");
  await fs.mkdir(inspectionDir, { recursive: true });
  await fs.writeFile(
    path.join(inspectionDir, "existing_backtest_summary.png"),
    new Uint8Array(await existingPreview.arrayBuffer()),
  );
  process.exit(0);
}

const payload = JSON.parse(await fs.readFile(inputPath, "utf8"));

function columnLetter(columnNumber) {
  let value = columnNumber;
  let result = "";
  while (value > 0) {
    value -= 1;
    result = String.fromCharCode(65 + (value % 26)) + result;
    value = Math.floor(value / 26);
  }
  return result;
}

const workbook = Workbook.create();
const summary = workbook.worksheets.add("Summary");
const trades = workbook.worksheets.add("Trade log");
const equity = workbook.worksheets.add("Equity");
const method = workbook.worksheets.add("Method");

const font = "Arial";
const navy = "#17365D";
const blue = "#4472C4";
const lightBlue = "#D9EAF7";
const lightGray = "#E7E6E6";
const green = "#E2F0D9";
const red = "#FCE4D6";
const darkText = "#1F1F1F";

for (const sheet of [summary, trades, equity, method]) {
  sheet.showGridLines = false;
}

summary.tabColor = navy;
trades.tabColor = blue;

summary.getRange("A2:M2").merge();
summary.getRange("A2").values = [["BTC and ETH strategy backtest results"]];
summary.getRange("A2").format.font = { name: font, size: 16, bold: true, color: darkText };
summary.getRange("A3:M3").merge();
summary.getRange("A3").values = [["Freqtrade 2026.8 | 2025 holdout | 0.10% fee per side | 1x isolated futures"]];
summary.getRange("A3").format.font = { name: font, size: 10, italic: true, color: "#595959" };

const summaryHeaders = [
  "Model", "Return", "Max drawdown", "Wallet Sharpe", "Profit factor", "Trades",
  "Win rate", "BTC return", "ETH return", "Long return", "Short return",
  "Profit (USDT)", "Final balance (USDT)",
];
const summaryRows = payload.summaries.map((run) => [
  run.model, run.return, run.max_drawdown, run.wallet_sharpe, run.profit_factor,
  run.trades, run.win_rate, run.btc_return, run.eth_return, run.long_return,
  run.short_return, run.profit_usdt, run.final_balance_usdt,
]);
summary.getRange("A5:M5").values = [summaryHeaders];
summary.getRange("A6").write(summaryRows);
const summaryEndRow = 5 + summaryRows.length;
summary.tables.add(`A5:M${summaryEndRow}`, true, "BacktestSummary").style = "TableStyleMedium2";
summary.getRange(`B6:B${summaryEndRow}`).format.numberFormat = "0.00%";
summary.getRange(`C6:C${summaryEndRow}`).format.numberFormat = "0.00%";
summary.getRange(`D6:E${summaryEndRow}`).format.numberFormat = "0.00";
summary.getRange(`G6:K${summaryEndRow}`).format.numberFormat = "0.00%";
summary.getRange(`L6:M${summaryEndRow}`).format.numberFormat = "#,##0.00";
summary.getRange(`A5:M${summaryEndRow}`).format.font = { name: font, size: 10, color: darkText };
summary.getRange("A5:M5").format.font = { name: font, size: 10, bold: true, color: "#FFFFFF" };
summary.getRange("A5:M5").format.fill = navy;
summary.getRange("A11:M11").merge();
summary.getRange("A11").values = [["Reading the result"]];
summary.getRange("A11").format = { fill: lightBlue, font: { name: font, size: 10, bold: true, color: darkText } };
summary.getRange("A12:M16").values = [
  ["Bollinger only", "Best total return and best Sharpe. The neural gate did not improve the 2025 risk-adjusted result.", null, null, null, null, null, null, null, null, null, null, null],
  ["RNN gate", "Removed four trades, reduced return, and did not materially reduce drawdown. Shorts lost money.", null, null, null, null, null, null, null, null, null, null, null],
  ["GRU gate", "Lowest drawdown and highest win rate, but much lower return. Most profit came from shorts.", null, null, null, null, null, null, null, null, null, null, null],
  ["LSTM gate", "Nearly matched baseline return but exceeded its drawdown. ETH produced all net profit; BTC detracted.", null, null, null, null, null, null, null, null, null, null, null],
  ["Transformer gate", "Returned 2.16% from 12 trades. One 28.03% ETH winner offset a combined 1,183.02 USDT loss from the other 11 trades.", null, null, null, null, null, null, null, null, null, null, null],
];
summary.getRange("A12:A16").format.font = { name: font, size: 10, bold: true, color: darkText };
summary.getRange("B12:M16").merge(true);
summary.getRange("A12:M16").format.font = { name: font, size: 10, color: darkText };
summary.getRange("B12:M16").format.wrapText = true;
const cautionRows = [
  ["Important limitation", "The local dataset ends on 2025-12-31, so this workbook contains no 2026 test. Funding and slippage were not available; funding is fixed at 0 and fees are 0.10% on entry plus 0.10% on exit. Results are research, not live-trading evidence."],
  ["Selection rule", "The 2025 holdout is now consumed. Tune only on rolling 2020-2024 development folds, then wait for fresh 2026-or-later data for the next honest test."],
  ["Concentration", "Every model lost money on BTC and depended on ETH. Validate pair-specific rules before deployment."],
];
for (let i = 0; i < cautionRows.length; i += 1) {
  const row = 18 + i;
  summary.getRange(`B${row}:M${row}`).merge();
  summary.getRange(`A${row}`).values = [[cautionRows[i][0]]];
  summary.getRange(`B${row}`).values = [[cautionRows[i][1]]];
}
summary.getRange("A18:A20").format = { fill: lightGray, font: { name: font, size: 10, bold: true, color: darkText } };
summary.getRange("B18:M20").format = { font: { name: font, size: 10, color: darkText }, wrapText: true };

const equityModels = payload.summaries.map((run) => run.model);
const equityEndColumn = columnLetter(equityModels.length + 1);
const equityDates = payload.equity[equityModels[0]].map((point) => new Date(`${point.date}T00:00:00Z`));
const equityMatrix = [["Date", ...equityModels]];
for (let i = 0; i < equityDates.length; i += 1) {
  equityMatrix.push([
    equityDates[i],
    ...equityModels.map((model) => payload.equity[model][i].equity),
  ]);
}
equity.getRange("A1").write(equityMatrix);
equity.getRange(`A1:${equityEndColumn}${equityMatrix.length}`).format.font = { name: font, size: 9, color: darkText };
equity.getRange(`A1:${equityEndColumn}1`).format = { fill: navy, font: { name: font, size: 9, bold: true, color: "#FFFFFF" } };
equity.getRange(`A2:A${equityMatrix.length}`).format.numberFormat = "yyyy-mm-dd";
equity.getRange(`B2:${equityEndColumn}${equityMatrix.length}`).format.numberFormat = "#,##0.00";
equity.freezePanes.freezeRows(1);
equity.tables.add(`A1:${equityEndColumn}${equityMatrix.length}`, true, "EquityTable").style = "TableStyleMedium2";

const monthLabels = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const monthlyRows = [["Month", ...equityModels]];
for (let i = 0; i < equityDates.length; i += 1) {
  const next = equityDates[i + 1];
  if (!next || next.getUTCMonth() !== equityDates[i].getUTCMonth()) {
    monthlyRows.push([
      `${monthLabels[equityDates[i].getUTCMonth()]} ${equityDates[i].getUTCFullYear()}`,
      ...equityModels.map((model) => payload.equity[model][i].equity),
    ]);
  }
}
equity.getRange("G1").write(monthlyRows);
const monthlyEndColumn = columnLetter(7 + equityModels.length);
equity.getRange(`G1:${monthlyEndColumn}${monthlyRows.length}`).format.font = { name: font, size: 9, color: darkText };
equity.getRange(`G1:${monthlyEndColumn}1`).format = { fill: navy, font: { name: font, size: 9, bold: true, color: "#FFFFFF" } };
equity.getRange(`H2:${monthlyEndColumn}${monthlyRows.length}`).format.numberFormat = "#,##0.00";

const equityChart = summary.charts.add("line", equity.getRange(`G1:${monthlyEndColumn}${monthlyRows.length}`));
equityChart.title = "Month-end wallet balance (USDT)";
equityChart.titleTextStyle.typeface = font;
equityChart.titleTextStyle.fontSize = 12;
equityChart.legend = { position: "top", textStyle: { typeface: font, fontSize: 10 } };
equityChart.xAxis = { axisType: "textAxis", textStyle: { typeface: font, fontSize: 9 } };
equityChart.yAxis = { numberFormatCode: "#,##0", numberFormatSourceLinked: false, textStyle: { typeface: font, fontSize: 9 } };
equityChart.setPosition("A22", "M41");
const seriesColors = ["#4472C4", "#ED7D31", "#70AD47", "#A5A5A5", "#8064A2"];
for (let i = 0; i < equityChart.series.items.length; i += 1) {
  equityChart.series.items[i].line = { fill: seriesColors[i], style: "solid", width: 2 };
}

const tradeHeaders = [
  "Model", "Trade #", "Pair", "Side", "Opened", "Closed", "Hours", "Entry price",
  "Exit price", "Min price", "Max price", "Stake (USDT)", "Quantity", "Leverage",
  "Entry fee", "Exit fee", "Funding (USDT)", "Net profit (USDT)", "Net return",
  "Cumulative profit (USDT)", "Entry signal", "Exit reason", "Opened weekday",
];
const tradeRows = payload.trades.map((trade) => [
  trade.model, trade.trade_number, trade.pair, trade.side, new Date(`${trade.open_date}Z`),
  new Date(`${trade.close_date}Z`), trade.duration_hours, trade.entry_price, trade.exit_price,
  trade.minimum_price, trade.maximum_price, trade.stake_usdt, trade.quantity, trade.leverage,
  trade.entry_fee_rate, trade.exit_fee_rate, trade.funding_fees_usdt, trade.net_profit_usdt,
  trade.net_return, trade.cumulative_profit_usdt, trade.entry_signal, trade.exit_reason,
  trade.weekday_opened,
]);
trades.getRange("A1").write([tradeHeaders, ...tradeRows]);
trades.getRange(`A1:W${tradeRows.length + 1}`).format.font = { name: font, size: 9, color: darkText };
trades.getRange("A1:W1").format = { fill: navy, font: { name: font, size: 9, bold: true, color: "#FFFFFF" } };
trades.getRange(`E2:F${tradeRows.length + 1}`).format.numberFormat = "yyyy-mm-dd hh:mm";
trades.getRange(`G2:G${tradeRows.length + 1}`).format.numberFormat = "0.0";
trades.getRange(`H2:Q${tradeRows.length + 1}`).format.numberFormat = "0.00000000";
trades.getRange(`R2:R${tradeRows.length + 1}`).format.numberFormat = "#,##0.00";
trades.getRange(`S2:S${tradeRows.length + 1}`).format.numberFormat = "0.00%";
trades.getRange(`T2:T${tradeRows.length + 1}`).format.numberFormat = "#,##0.00";
trades.tables.add(`A1:W${tradeRows.length + 1}`, true, "TradeLog").style = "TableStyleMedium2";
trades.freezePanes.freezeRows(1);
trades.freezePanes.freezeColumns(4);
trades.getRange(`R2:R${tradeRows.length + 1}`).conditionalFormats.add("cellIs", {
  operator: "greaterThan", formula: 0, format: { fill: green },
});
trades.getRange(`R2:R${tradeRows.length + 1}`).conditionalFormats.add("cellIs", {
  operator: "lessThan", formula: 0, format: { fill: red },
});

method.getRange("A2:F2").merge();
method.getRange("A2").values = [["Backtest design and model definitions"]];
method.getRange("A2").format.font = { name: font, size: 14, bold: true, color: darkText };
method.getRange("A4:B4").values = [["Setting", "Value"]];
method.getRange("A5:B18").values = [
  ["Universe", "BTC/USDT:USDT and ETH/USDT:USDT"],
  ["Bars", "1-hour local candles"],
  ["Test period", "2025-01-01 through 2025-12-31"],
  ["Capital", "10,000 USDT; 5,000 USDT stake; two concurrent positions"],
  ["Execution", "1x isolated futures, long and short"],
  ["Trading cost", "0.10% entry fee plus 0.10% exit fee"],
  ["Funding", "0 (historical funding data not present)"],
  ["Core signal", "Close crosses a 40-day Bollinger band at 1.5 standard deviations"],
  ["Exit", "Price crosses the 40-day middle band"],
  ["Neural target", "Next 24-hour log return"],
  ["Neural entry gate", "Forecast above +0.20% for long or below -0.20% for short"],
  ["Input window", "48 hourly feature vectors"],
  ["Walk-forward", "365-day training window, refreshed every 90 days"],
  ["Training", "90/10 chronological split; seed 42; up to 6 epochs; patience 2"],
];
method.getRange("D4:F4").values = [["Model", "What changes", "Interpretation"]];
method.getRange("D5:F9").values = [
  ["Bollinger only", "No forecast gate", "Pure rule-based breakout control"],
  ["RNN gate", "Vanilla recurrent cell", "Shortest memory; most vulnerable to vanishing gradients"],
  ["GRU gate", "Update and reset gates", "Compact gated memory"],
  ["LSTM gate", "Input, forget and output gates", "Separate memory cell and the most parameters"],
  ["Transformer gate", "Four-head self-attention", "Direct timestep comparisons; 10,785 parameters"],
];
method.getRange("D10:F10").values = [["Small tuning grid", "Candidates", "Guardrail"]];
method.getRange("D11:F17").values = [
  ["Band window (days)", "20, 40, 60", "Tune on 2020-2024 folds only"],
  ["Band width", "1.5, 2.0", "Keep the middle-band exit fixed first"],
  ["Sequence (hours)", "24, 48, 168", "Compare identical folds and seeds"],
  ["Forecast horizon (hours)", "6, 24, 72", "Align threshold to the horizon"],
  ["Hidden size", "16, 32, 64", "Reject unstable seed sensitivity"],
  ["Forecast threshold", "0, 0.20%, 0.50%", "Penalize low trade counts"],
  ["Cost stress", "0.05%, 0.10%, 0.20% per side", "Add historical funding before live use"],
];
for (const range of ["A4:B4", "D4:F4", "D10:F10"]) {
  method.getRange(range).format = { fill: navy, font: { name: font, size: 10, bold: true, color: "#FFFFFF" } };
}
method.getRange("A4:F18").format.font = { name: font, size: 10, color: darkText };
method.getRange("A4:F18").format.verticalAlignment = "center";
method.getRange("B5:B18").format.wrapText = true;
method.getRange("E5:F17").format.wrapText = true;

summary.getRange("A1:M45").format.verticalAlignment = "center";
summary.getRange("A1:M45").format.font.name = font;
summary.getRange("A1:M45").format.autofitRows();
summary.getRange("A1:M45").format.autofitColumns();
summary.getRange("A:A").format.columnWidth = 22;
summary.getRange("B:M").format.columnWidth = 14;
summary.getRange("D:E").format.columnWidth = 16;
summary.getRange("L:M").format.columnWidth = 20;

trades.getRange(`A1:W${tradeRows.length + 1}`).format.autofitColumns();
for (const col of ["A:A", "C:C", "U:U", "V:V"]) trades.getRange(col).format.columnWidth = 24;
trades.getRange("E:F").format.columnWidth = 18;
equity.getRange(`A1:${monthlyEndColumn}${equityMatrix.length}`).format.autofitColumns();
method.getRange("A1:F20").format.autofitRows();
method.getRange("A1:F20").format.autofitColumns();
method.getRange("A:A").format.columnWidth = 24;
method.getRange("B:B").format.columnWidth = 54;
method.getRange("D:D").format.columnWidth = 24;
method.getRange("E:F").format.columnWidth = 38;
for (const range of ["A4:B4", "D4:F4", "D10:F10"]) {
  method.getRange(range).format = { fill: navy, font: { name: font, size: 10, bold: true, color: "#FFFFFF" } };
}

workbook.recalculate();
const summaryInspect = await workbook.inspect({
  kind: "table", range: "Summary!A2:M20", include: "values,formulas",
  tableMaxRows: 21, tableMaxCols: 13,
});
const errorInspect = await workbook.inspect({
  kind: "match", searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!",
  options: { useRegex: true, maxResults: 100 }, summary: "final formula error scan",
});
console.log(summaryInspect.ndjson);
console.log(errorInspect.ndjson);

const preview = await workbook.render({ sheetName: "Summary", range: "A1:M42", scale: 1, format: "png" });
await fs.writeFile(previewPath, new Uint8Array(await preview.arrayBuffer()));
for (const [sheetName, range, fileName] of [
  ["Trade log", "A1:W20", "trade_log_preview.png"],
  ["Equity", "A1:K20", "equity_preview.png"],
  ["Method", "A1:F18", "method_preview.png"],
]) {
  const rendered = await workbook.render({ sheetName, range, scale: 1, format: "png" });
  await fs.writeFile(path.join(outputDir, fileName), new Uint8Array(await rendered.arrayBuffer()));
}
const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);
const savedWorkbook = await SpreadsheetFile.importXlsx(await FileBlob.load(outputPath));
const savedInspect = await savedWorkbook.inspect({
  kind: "sheet,drawing", include: "id,name,type,title", maxChars: 4000,
});
console.log(savedInspect.ndjson);
console.log(JSON.stringify({ outputPath, previewPath, chartCount: summary.charts.items.length, tradeRows: tradeRows.length }));
