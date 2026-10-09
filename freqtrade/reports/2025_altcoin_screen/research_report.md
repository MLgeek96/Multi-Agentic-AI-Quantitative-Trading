# 2025 SOL/XRP/BNB/DOGE strategy screen

## Conclusion

The best unchanged BTC/ETH strategy on the four-altcoin portfolio was **Bollinger 40d**, with
**21.22%** net return, **20.71%** maximum drawdown, and a
**0.21** wallet Sharpe after 0.10% entry and exit fees. Strategies with a positive
portfolio result: Bollinger 40d, Bollinger + RNN, Bollinger + LSTM, HMM trend only, Bollinger + GRU.

This is a transfer test, not an altcoin-specific optimization. The parameters were copied without
retuning, HMMs were fit only on 2020-2024 data, and the 2025 period was held out. A positive result
means the existing rule set transferred to this sample; it does not establish live profitability.

## Portfolio results

| model | return_pct | drawdown_pct | sharpe | profit_factor | trades |
| --- | --- | --- | --- | --- | --- |
| Bollinger 40d | 21.22% | 20.71% | 0.21 | 1.46 | 36 |
| Bollinger + RNN | 16.39% | 25.02% | -0.08 | 1.41 | 30 |
| Bollinger + LSTM | 16.20% | 19.08% | -0.03 | 1.39 | 35 |
| HMM trend only | 11.67% | 11.27% | 0.68 | 1.21 | 107 |
| Bollinger + GRU | 4.05% | 29.36% | -0.49 | 1.09 | 30 |
| HMM regime + LSTM | -1.72% | 18.96% | -0.03 | 0.97 | 113 |
| HMM regime | -8.42% | 28.15% | -0.24 | 0.91 | 206 |

## Return contribution by pair

These percentages are each pair's contribution to the shared 10,000 USDT wallet, not standalone
pair returns.

| model | SOL/USDT:USDT | XRP/USDT:USDT | BNB/USDT:USDT | DOGE/USDT:USDT |
| --- | --- | --- | --- | --- |
| Bollinger 40d | 7.63% | -8.20% | 9.47% | 12.33% |
| Bollinger + RNN | 8.68% | 1.14% | 9.48% | -2.91% |
| Bollinger + LSTM | 6.25% | -5.89% | 9.29% | 6.55% |
| HMM trend only | -5.05% | 10.83% | -0.38% | 6.28% |
| Bollinger + GRU | 7.28% | -15.37% | 9.28% | 2.85% |
| HMM regime + LSTM | -8.34% | 4.80% | 1.05% | 0.77% |
| HMM regime | -11.27% | 4.31% | -2.84% | 1.38% |

## Method

- Pairs: SOL, XRP, BNB, and DOGE USD-M perpetual futures.
- Period: 2025-01-01 through 2025-12-31 on one-hour candles.
- Starting wallet: 10,000 USDT; four concurrent 2,500 USDT positions; 1x isolated leverage.
- Costs: 0.10% on entry and 0.10% on exit; historical funding and slippage are not included.
- Sequence models: 48-hour inputs, 24-hour target, trailing 365-day training window, refreshed every 90 days, seed 42.
- HMM: three states fit separately for each pair on 2020-2024, then frozen and filtered causally during 2025.
- No missing candles were forward-filled.

Treat 2025 as consumed for these altcoins after reading this report. Any tuning should be done on
earlier rolling folds and evaluated on a new untouched period.
