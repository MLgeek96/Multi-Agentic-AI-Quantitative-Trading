# Six-asset HMM probability export

Each transition matrix is fixed after fitting that asset on 2020-2024 data. Rows are the
current hidden state and columns are the next hidden state. The hourly filtered probabilities
are causal and time-varying; they use only observations available at that candle.

### BTCUSDT

| from \ to | trend | sideways | crisis |
| --- | ---: | ---: | ---: |
| trend | 0.9780 | 0.0140 | 0.0079 |
| sideways | 0.0189 | 0.9806 | 0.0005 |
| crisis | 0.0205 | 0.0000 | 0.9795 |

### ETHUSDT

| from \ to | trend | sideways | crisis |
| --- | ---: | ---: | ---: |
| trend | 0.9795 | 0.0140 | 0.0066 |
| sideways | 0.0165 | 0.9829 | 0.0006 |
| crisis | 0.0178 | 0.0005 | 0.9817 |

### SOLUSDT

| from \ to | trend | sideways | crisis |
| --- | ---: | ---: | ---: |
| trend | 0.9827 | 0.0104 | 0.0068 |
| sideways | 0.0122 | 0.9871 | 0.0007 |
| crisis | 0.0202 | 0.0005 | 0.9794 |

### XRPUSDT

| from \ to | trend | sideways | crisis |
| --- | ---: | ---: | ---: |
| trend | 0.9803 | 0.0144 | 0.0053 |
| sideways | 0.0152 | 0.9844 | 0.0004 |
| crisis | 0.0142 | 0.0000 | 0.9858 |

### BNBUSDT

| from \ to | trend | sideways | crisis |
| --- | ---: | ---: | ---: |
| trend | 0.9820 | 0.0126 | 0.0053 |
| sideways | 0.0158 | 0.9840 | 0.0002 |
| crisis | 0.0154 | 0.0001 | 0.9845 |

### DOGEUSDT

| from \ to | trend | sideways | crisis |
| --- | ---: | ---: | ---: |
| trend | 0.9793 | 0.0161 | 0.0045 |
| sideways | 0.0124 | 0.9874 | 0.0001 |
| crisis | 0.0202 | 0.0000 | 0.9798 |
