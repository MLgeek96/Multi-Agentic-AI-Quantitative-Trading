# Granular Mathematical Foundations & Derivations of the Strategy Archetype

**Course:** FE5209 Financial Econometrics  
**Degree:** Master of Science in Financial Engineering (MFE)  
**Institution:** Department of Mathematics / Risk Management Institute (RMI), National University of Singapore (NUS)  
**Instructor:** Associate Professor Chen Ying  
**Challenge:** *Challenge 1: Can You Beat the Market?*  
**Date:** September 2026  

---

## Executive Summary & Architecture Map

The strategy archetype deployed in this project is an **Institutional Dynamic Statistical Arbitrage (Pairs Trading) Framework** operating in discrete time with continuous-time stochastic underpinning. It synthesizes five mathematical and econometric pillars:

```
[Asset 1 & Asset 2 Log Prices: y_t, x_t]
                  │
                  ▼
┌────────────────────────────────────────────────────────┐
│ 1. Cointegration Foundation (I(1) & CI(1,1))            │
│    - Granger Representation Theorem                    │
│    - Engle-Granger Two-Step with MacKinnon Adjustment  │
│    - Johansen Vector Error Correction Model (VECM)     │
└─────────────────────────┬──────────────────────────────┘
                          │ (If Cointegrated)
                          ▼
┌────────────────────────────────────────────────────────┐
│ 2. Continuous-Time Ornstein-Uhlenbeck (OU) SDE         │
│    - Itô Calculus Exact Solution                       │
│    - Discrete AR(1) Parameter Mapping                  │
│    - Analytical Half-Life: τ_{1/2} = ln(2) / θ         │
└─────────────────────────┬──────────────────────────────┘
                          │ (Dynamic State-Space Model)
                          ▼
┌────────────────────────────────────────────────────────┐
│ 3. Recursive Online State-Space Kalman Filter          │
│    - Time-Varying Hedge Ratio θ_t = [α_t, β_t]^T       │
│    - Orthogonal Projection / MMSE Gain Derivation      │
│    - Causal Standardized Innovation: Z_t = e_t / √F_t  │
└─────────────────────────┬──────────────────────────────┘
                          │ (Slide 1 Requirement)
                          ▼
┌────────────────────────────────────────────────────────┐
│ 4. Multi-Horizon Spread Forecasting Engine             │
│    - E[S_{t+h} | F_t] & Var[S_{t+h} | F_t]             │
│    - Analytical 95% Confidence Bounds for h ∈ {1..10}  │
└─────────────────────────┬──────────────────────────────┘
                          │ (Execution Under Microstructure)
                          ▼
┌────────────────────────────────────────────────────────┐
│ 5. Market-Neutral Capital Allocation & Quantization    │
│    - Zero-Beta Dollar Weights Derivation               │
│    - Minimum Board Lot Quantization (SGX vs. US/EU)    │
│    - Friction Hurdle Rate: |Z^*| ≥ [2 c_round + drag]  │
└────────────────────────────────────────────────────────┘
```

---

## Pillar 1: Econometric Cointegration Foundation

### 1.1 The Spurious Regression Problem
Let $y_t = \ln(P_{1,t})$ and $x_t = \ln(P_{2,t})$ denote the log prices of two assets. If both series are integrated of order one, $y_t \sim I(1)$ and $x_t \sim I(1)$, standard regression:
$$y_t = \alpha + \beta x_t + \varepsilon_t$$
yields a high $R^2$ and statistically significant $t$-statistics even when the two series are completely independent. This is the **spurious regression phenomenon** (Granger & Newbold, 1974), caused by non-stationary error variance:
$$\operatorname{Var}(\varepsilon_t) = \mathcal{O}(t) \to \infty \quad \text{as } t \to \infty$$
Therefore, high Pearson correlation $\rho_{x,y}$ is insufficient for pairs trading.

### 1.2 Definition of Cointegration
Following Engle & Granger (1987), two $I(1)$ series $y_t$ and $x_t$ are cointegrated of order $(1, 1)$, denoted $(y_t, x_t)' \sim CI(1, 1)$, if there exists a cointegrating vector $\boldsymbol{\beta}^* = (1, -\alpha, -\beta)'$ such that the linear combination:
$$S_t = y_t - \alpha - \beta x_t$$
is stationary, $S_t \sim I(0)$, possessing:
$$\mathbb{E}[S_t] = \mu < \infty, \quad \operatorname{Var}(S_t) = \sigma_S^2 < \infty, \quad \operatorname{Cov}(S_t, S_{t-k}) = \gamma_k \quad (\text{independent of } t)$$

### 1.3 Engle-Granger Two-Step Estimation & MacKinnon Critical Values
* **Step 1 (Co-integrating OLS):** Fit $y_t = \hat{\alpha} + \hat{\beta} x_t + \hat{e}_t$ via Ordinary Least Squares over the formation window $t = 1, \dots, T$.
* **Step 2 (Stationarity of Residuals):** Test the estimated residual $\hat{e}_t$ using the Augmented Dickey-Fuller (ADF) regression:
  $$\Delta \hat{e}_t = \gamma \hat{e}_{t-1} + \sum_{j=1}^p \delta_j \Delta \hat{e}_{t-j} + u_t$$
  where $p$ is chosen by minimizing the Akaike Information Criterion (AIC).
* **The MacKinnon Adjustment:** The test statistic is $t_\gamma = \frac{\hat{\gamma}}{\operatorname{SE}(\hat{\gamma})}$. Because $\hat{e}_t$ is unobserved and calculated from an estimated cointegrating vector that minimizes residual variance, $t_\gamma$ does **not** follow the standard Dickey-Fuller distribution. Using standard critical values leads to severe over-rejection of the null hypothesis (false cointegration). We compute $p$-values using **MacKinnon's (2010) response surface parameters**:
  $$\text{Crit}_\alpha(N, T) = \beta_\infty + \frac{\beta_1}{T} + \frac{\beta_2}{T^2}$$
  where $N = 2$ variables. We enforce $p \le 0.10$.

### 1.4 Johansen Maximum Likelihood Cointegration Test
To avoid normalization bias ($y_t$ on $x_t$ vs. $x_t$ on $y_t$), we formulate a Vector Autoregressive model of lag order $k$, $\text{VAR}(k)$:
$$\mathbf{Y}_t = \boldsymbol{\mu} + \sum_{i=1}^k \mathbf{A}_i \mathbf{Y}_{t-i} + \boldsymbol{\varepsilon}_t, \quad \mathbf{Y}_t = \begin{pmatrix} y_t \\ x_t \end{pmatrix}, \quad \boldsymbol{\varepsilon}_t \sim \text{IID}(\mathbf{0}, \boldsymbol{\Sigma})$$
Subtracting $\mathbf{Y}_{t-1}$ from both sides yields the **Vector Error Correction Model (VECM)**:
$$\Delta \mathbf{Y}_t = \boldsymbol{\mu} + \boldsymbol{\Pi} \mathbf{Y}_{t-1} + \sum_{i=1}^{k-1} \boldsymbol{\Gamma}_i \Delta \mathbf{Y}_{t-i} + \boldsymbol{\varepsilon}_t$$
where:
$$\boldsymbol{\Pi} = \sum_{i=1}^k \mathbf{A}_i - \mathbf{I}, \quad \boldsymbol{\Gamma}_i = -\sum_{j=i+1}^k \mathbf{A}_j$$
By the **Granger Representation Theorem**:
1. If $\operatorname{rank}(\boldsymbol{\Pi}) = 0$, $\boldsymbol{\Pi} = \mathbf{0}$, meaning $\mathbf{Y}_t$ are non-cointegrated unit root processes.
2. If $\operatorname{rank}(\boldsymbol{\Pi}) = 2$ (full rank), $\mathbf{Y}_t$ is already stationary in levels ($I(0)$).
3. If $\operatorname{rank}(\boldsymbol{\Pi}) = 1$ (reduced rank), there exists a factorization:
   $$\boldsymbol{\Pi} = \boldsymbol{\alpha} \boldsymbol{\beta}'$$
   where $\boldsymbol{\beta}$ is the $2 \times 1$ cointegrating vector ($\boldsymbol{\beta}' \mathbf{Y}_{t-1} \sim I(0)$) and $\boldsymbol{\alpha}$ is the $2 \times 1$ error-correction adjustment speed vector.

We solve for the ordered eigenvalues $\hat{\lambda}_1 \ge \hat{\lambda}_2$ of the generalized eigenvalue problem:
$$|\lambda \mathbf{S}_{11} - \mathbf{S}_{10} \mathbf{S}_{00}^{-1} \mathbf{S}_{01}| = 0$$
The **Trace Statistic** tests the null hypothesis of at most $r$ cointegrating vectors ($H_0: r \le 0$ vs. $H_1: r \ge 1$):
$$\lambda_{\text{trace}}(r) = -T \sum_{i=r+1}^2 \ln(1 - \hat{\lambda}_i)$$
We mandate $\lambda_{\text{trace}}(0) > \lambda_{\text{crit}, 0.05}$ (empirically $\approx 15.49$) to establish $r = 1$.

---

## Pillar 2: Continuous-Time Ornstein-Uhlenbeck (OU) Modeling

### 2.1 Stochastic Differential Equation (SDE)
We model the stationary spread $S_t$ as an Ornstein-Uhlenbeck diffusion process (Uhlenbeck & Ornstein, 1930):
$$dS_t = \theta (\mu - S_t) dt + \sigma dW_t$$
* $\theta > 0$: Speed of mean reversion ($1/\text{time}$).
* $\mu \in \mathbb{R}$: Long-term equilibrium spread level.
* $\sigma > 0$: Diffusion volatility parameter.
* $W_t$: Standard 1-dimensional Brownian motion satisfying $\mathbb{E}[dW_t] = 0$ and $(dW_t)^2 = dt$.

### 2.2 Complete Itô Calculus Analytical Derivation
To solve this linear stochastic differential equation, we introduce the integrating factor $e^{\theta t}$. Define the auxiliary function:
$$f(S_t, t) = S_t e^{\theta t}$$
By Itô's Lemma:
$$df(S_t, t) = \frac{\partial f}{\partial t} dt + \frac{\partial f}{\partial S_t} dS_t + \frac{1}{2} \frac{\partial^2 f}{\partial S_t^2} (dS_t)^2$$
Compute the partial derivatives:
$$\frac{\partial f}{\partial t} = \theta S_t e^{\theta t}, \quad \frac{\partial f}{\partial S_t} = e^{\theta t}, \quad \frac{\partial^2 f}{\partial S_t^2} = 0$$
Substitute $dS_t = \theta (\mu - S_t) dt + \sigma dW_t$ into the expansion:
$$\begin{aligned}
df(S_t, t) &= \theta S_t e^{\theta t} dt + e^{\theta t} \left[ \theta (\mu - S_t) dt + \sigma dW_t \right] + 0 \\
&= \theta S_t e^{\theta t} dt + \theta \mu e^{\theta t} dt - \theta S_t e^{\theta t} dt + \sigma e^{\theta t} dW_t \\
&= \theta \mu e^{\theta t} dt + \sigma e^{\theta t} dW_t
\end{aligned}$$
Integrating both sides over the time interval $[s, t]$ (where $s < t$):
$$f(S_t, t) - f(S_s, s) = \int_s^t \theta \mu e^{\theta u} du + \int_s^t \sigma e^{\theta u} dW_u$$
Substitute $f(S_t, t) = S_t e^{\theta t}$:
$$S_t e^{\theta t} - S_s e^{\theta s} = \mu \left[ e^{\theta t} - e^{\theta s} \right] + \sigma \int_s^t e^{\theta u} dW_u$$
Multiply the entire equation by $e^{-\theta t}$:
$$\mathbf{S_t = \mu + (S_s - \mu) e^{-\theta (t - s)} + \sigma \int_s^t e^{-\theta (t - u)} dW_u}$$

### 2.3 Exact Conditional Moments
Taking the conditional expectation $\mathbb{E}[\cdot \mid \mathcal{F}_s]$ (noting that the Itô stochastic integral is a martingale with zero expectation):
$$\mathbb{E}[S_t \mid \mathcal{F}_s] = \mu + (S_s - \mu) e^{-\theta (t - s)}$$
For conditional variance, apply the **Itô Isometry**:
$$\begin{aligned}
\operatorname{Var}(S_t \mid \mathcal{F}_s) &= \mathbb{E}\left[ \left( \sigma \int_s^t e^{-\theta (t - u)} dW_u \right)^2 \right] = \sigma^2 \int_s^t \left( e^{-\theta (t - u)} \right)^2 du \\
&= \sigma^2 \int_s^t e^{-2\theta (t - u)} du = \sigma^2 \left[ \frac{e^{-2\theta (t - u)}}{2\theta} \right]_{u=s}^{u=t} \\
&= \frac{\sigma^2}{2\theta} \left( 1 - e^{-2\theta (t - s)} \right)
\end{aligned}$$
As $t - s \to \infty$, the asymptotic stationary distribution is:
$$S_\infty \sim \mathcal{N}\left( \mu, \; \frac{\sigma^2}{2\theta} \right)$$

### 2.4 Discrete AR(1) Mapping
In empirical practice, asset prices are sampled at discrete intervals $\Delta t = 1$ trading day. Setting $t - s = \Delta t = 1$:
$$S_t = \mu (1 - e^{-\theta}) + e^{-\theta} S_{t-1} + \eta_t, \quad \eta_t \sim \mathcal{N}\left(0, \frac{\sigma^2}{2\theta}(1 - e^{-2\theta})\right)$$
This maps identically to a standard discrete autoregressive process:
$$S_t = a + b S_{t-1} + \eta_t, \quad \eta_t \sim \text{IID } \mathcal{N}(0, \sigma_\eta^2)$$
Matching coefficients:
$$b = e^{-\theta} \implies \boldsymbol{\theta = -\ln(b)}$$
$$a = \mu (1 - b) \implies \boldsymbol{\mu = \frac{a}{1 - b}}$$
$$\sigma_\eta^2 = \frac{\sigma^2}{2\theta}(1 - e^{-2\theta}) = \frac{\sigma^2}{2\theta}(1 - b^2) \implies \boldsymbol{\sigma = \sigma_\eta \sqrt{\frac{-2 \ln b}{1 - b^2}}}$$

### 2.5 Derivation of Mean-Reversion Half-Life ($\tau_{1/2}$)
The half-life $\tau_{1/2}$ is defined as the expected elapsed time required for a spread dislocation $(S_0 - \mu)$ to decay to half its initial magnitude:
$$\mathbb{E}[S_{\tau_{1/2}} \mid S_0] - \mu = \frac{1}{2} (S_0 - \mu)$$
Substitute the analytical solution:
$$(S_0 - \mu) e^{-\theta \tau_{1/2}} = \frac{1}{2} (S_0 - \mu)$$
Divide by $(S_0 - \mu) \neq 0$:
$$e^{-\theta \tau_{1/2}} = \frac{1}{2} \implies -\theta \tau_{1/2} = \ln\left(\frac{1}{2}\right) = -\ln(2) \implies \boldsymbol{\tau_{1/2} = \frac{\ln(2)}{\theta}}$$
* **Econometric Bounding:** We filter pairs requiring $2.0 \le \tau_{1/2} \le 90.0$ trading days.
* **Maximum Holding Horizon:** We set the time-stop exit rule at:
  $$T_{\text{max}} = 2.5 \times \tau_{1/2}$$
  At $t = 2.5 \tau_{1/2}$, the expected remaining mispricing is $(1/2)^{2.5} \approx 17.7\%$. If the trade has not reverted by this point, the thesis has failed, and capital is liquidated to prevent dead capital drag.

---

## Pillar 3: Dynamic Online State-Space Kalman Filtering

Static OLS estimates over a 4-year formation period fail because real-world cointegrating vectors drift as corporate leverage, capital intensity, and cost structures diverge. To obtain a **purely causal, non-anticipating dynamic hedge ratio**, we implement a state-space model via the Kalman Filter (Kalman, 1960).

```
   State Transition:  θ_t = θ_{t-1} + w_t,   w_t ~ N(0, Q)
                             │
                             ▼
   Observation:       y_t = H_t θ_t + v_t,   v_t ~ N(0, R),   H_t = [1, x_t]
                             │
           ┌─────────────────┴─────────────────┐
           ▼                                   ▼
   [1. Time Update (Predict)]          [2. Measurement Innovation]
   θ̂_{t|t-1} = θ̂_{t-1|t-1}             e_t = y_t - H_t θ̂_{t|t-1}
   P_{t|t-1} = P_{t-1|t-1} + Q         F_t = H_t P_{t|t-1} H_t^T + R
           │                                   │
           └─────────────────┬─────────────────┘
                             ▼
                     [3. Kalman Gain]
                     K_t = P_{t|t-1} H_t^T F_t^{-1}
                             │
           ┌─────────────────┴─────────────────┐
           ▼                                   ▼
   [4. State Update (Correct)]         [5. Covariance Update]
   θ̂_{t|t} = θ̂_{t|t-1} + K_t e_t       P_{t|t} = (I - K_t H_t) P_{t|t-1}
                             │
                             ▼
               [Standardized Causal Signal]
                     Z_t = e_t / √F_t
```

### 3.1 State-Space Equations
Define the state vector $\boldsymbol{\theta}_t \in \mathbb{R}^2$:
$$\boldsymbol{\theta}_t = \begin{pmatrix} \alpha_t \\ \beta_t \end{pmatrix}$$
* **State Transition Equation (System Evolution):**
  $$\boldsymbol{\theta}_t = \boldsymbol{\theta}_{t-1} + \mathbf{w}_t, \quad \mathbf{w}_t \sim \text{IID } \mathcal{N}(\mathbf{0}, \mathbf{Q})$$
  where $\mathbf{Q} = \begin{pmatrix} Q_\alpha & 0 \\ 0 & Q_\beta \end{pmatrix} = \begin{pmatrix} 10^{-5} & 0 \\ 0 & 10^{-5} \end{pmatrix}$ models smooth stochastic parameter drift.
* **Observation Equation (Measurement):**
  $$y_t = \mathbf{H}_t \boldsymbol{\theta}_t + v_t, \quad v_t \sim \text{IID } \mathcal{N}(0, R)$$
  where $\mathbf{H}_t = \begin{pmatrix} 1 & x_t \end{pmatrix} \in \mathbb{R}^{1 \times 2}$, and $R = 10^{-3}$ models market microstructural measurement noise.

### 3.2 Derivation of the Minimum Mean Square Error (MMSE) Update
Let $\hat{\boldsymbol{\theta}}_{t-1|t-1} = \mathbb{E}[\boldsymbol{\theta}_{t-1} \mid \mathcal{F}_{t-1}]$ and $\mathbf{P}_{t-1|t-1} = \operatorname{Cov}(\boldsymbol{\theta}_{t-1} \mid \mathcal{F}_{t-1})$.

#### Step 1: Predict (Prior Moments)
$$\hat{\boldsymbol{\theta}}_{t|t-1} = \mathbb{E}[\boldsymbol{\theta}_t \mid \mathcal{F}_{t-1}] = \mathbb{E}[\boldsymbol{\theta}_{t-1} + \mathbf{w}_t \mid \mathcal{F}_{t-1}] = \hat{\boldsymbol{\theta}}_{t-1|t-1}$$
$$\begin{aligned}
\mathbf{P}_{t|t-1} &= \mathbb{E}\left[ (\boldsymbol{\theta}_t - \hat{\boldsymbol{\theta}}_{t|t-1})(\boldsymbol{\theta}_t - \hat{\boldsymbol{\theta}}_{t|t-1})' \mid \mathcal{F}_{t-1} \right] \\
&= \mathbb{E}\left[ (\boldsymbol{\theta}_{t-1} - \hat{\boldsymbol{\theta}}_{t-1|t-1} + \mathbf{w}_t)(\boldsymbol{\theta}_{t-1} - \hat{\boldsymbol{\theta}}_{t-1|t-1} + \mathbf{w}_t)' \right] \\
&= \mathbf{P}_{t-1|t-1} + \mathbf{Q}
\end{aligned}$$

#### Step 2: Measurement Prediction & Innovation
Prior expected measurement:
$$\hat{y}_{t|t-1} = \mathbb{E}[y_t \mid \mathcal{F}_{t-1}] = \mathbf{H}_t \hat{\boldsymbol{\theta}}_{t|t-1} = \hat{\alpha}_{t|t-1} + \hat{\beta}_{t|t-1} x_t$$
The **measurement innovation (residual error)** is:
$$e_t = y_t - \hat{y}_{t|t-1} = y_t - \mathbf{H}_t \hat{\boldsymbol{\theta}}_{t|t-1}$$
Substitute $y_t = \mathbf{H}_t \boldsymbol{\theta}_t + v_t$:
$$e_t = \mathbf{H}_t (\boldsymbol{\theta}_t - \hat{\boldsymbol{\theta}}_{t|t-1}) + v_t$$
The **innovation variance** $F_t = \mathbb{E}[e_t^2 \mid \mathcal{F}_{t-1}]$ is:
$$F_t = \mathbb{E}\left[ \left(\mathbf{H}_t (\boldsymbol{\theta}_t - \hat{\boldsymbol{\theta}}_{t|t-1}) + v_t\right)^2 \right] = \mathbf{H}_t \mathbf{P}_{t|t-1} \mathbf{H}_t' + R$$

#### Step 3: Optimal Kalman Gain Derivation
We seek a linear estimator of the form:
$$\hat{\boldsymbol{\theta}}_{t|t} = \hat{\boldsymbol{\theta}}_{t|t-1} + \mathbf{K}_t e_t$$
The estimation error is:
$$\tilde{\boldsymbol{\theta}}_{t|t} = \boldsymbol{\theta}_t - \hat{\boldsymbol{\theta}}_{t|t} = (\boldsymbol{\theta}_t - \hat{\boldsymbol{\theta}}_{t|t-1}) - \mathbf{K}_t (\mathbf{H}_t (\boldsymbol{\theta}_t - \hat{\boldsymbol{\theta}}_{t|t-1}) + v_t) = (\mathbf{I} - \mathbf{K}_t \mathbf{H}_t) \tilde{\boldsymbol{\theta}}_{t|t-1} - \mathbf{K}_t v_t$$
The posterior error covariance matrix $\mathbf{P}_{t|t} = \mathbb{E}[\tilde{\boldsymbol{\theta}}_{t|t} \tilde{\boldsymbol{\theta}}_{t|t}']$ is:
$$\mathbf{P}_{t|t} = (\mathbf{I} - \mathbf{K}_t \mathbf{H}_t) \mathbf{P}_{t|t-1} (\mathbf{I} - \mathbf{K}_t \mathbf{H}_t)' + \mathbf{K}_t R \mathbf{K}_t'$$
To find the optimal gain $\mathbf{K}_t$, we minimize the Mean Square Error (trace of $\mathbf{P}_{t|t}$):
$$\frac{\partial \operatorname{Tr}(\mathbf{P}_{t|t})}{\partial \mathbf{K}_t} = -2 (\mathbf{I} - \mathbf{K}_t \mathbf{H}_t) \mathbf{P}_{t|t-1} \mathbf{H}_t' + 2 \mathbf{K}_t R = \mathbf{0}$$
$$-2 \mathbf{P}_{t|t-1} \mathbf{H}_t' + 2 \mathbf{K}_t \left( \mathbf{H}_t \mathbf{P}_{t|t-1} \mathbf{H}_t' + R \right) = \mathbf{0}$$
$$\mathbf{K}_t F_t = \mathbf{P}_{t|t-1} \mathbf{H}_t' \implies \mathbf{K_t = P_{t|t-1} H_t' F_t^{-1}}$$
Substituting $\mathbf{K}_t$ back into $\mathbf{P}_{t|t}$:
$$\mathbf{P}_{t|t} = (\mathbf{I} - \mathbf{K}_t \mathbf{H}_t) \mathbf{P}_{t|t-1}$$

### 3.3 The Standardized Causal Z-Score
By the Orthogonal Projection Theorem, under the true model, the innovation $e_t$ is orthogonal to all past observations:
$$\mathbb{E}[e_t \mid \mathcal{F}_{t-1}] = 0, \quad \operatorname{Var}(e_t \mid \mathcal{F}_{t-1}) = F_t$$
We define the **standardized innovation Z-score**:
$$\mathbf{Z_t = \frac{e_t}{\sqrt{F_t}} \sim \mathcal{N}(0, 1)}$$
* **Why this beats standard rolling Z-scores:** Traditional pairs trading defines $Z_t = \frac{S_t - \text{SMA}_k(S_t)}{\text{Std}_k(S_t)}$, which lags market turns by $k/2$ bars and suffers from arbitrary window choice. The Kalman $Z_t$ is:
  1. **Strictly causal** (utilizes only information up to $t$).
  2. **Heteroskedasticity-adjusted** ($F_t$ widens during turbulent regimes, preventing false entries).
  3. **Zero-lag** (updates instantaneously as new data arrive).

---

## Pillar 4: Multi-Horizon Continuous-Time Spread Forecasting Engine

Slide 1 of the Group Project instructions mandates: *"daily price data should be downloaded... forecasts are updated each day as new data arrive."*

We integrate the online state estimate $\hat{\boldsymbol{\theta}}_{t|t} = (\hat{\alpha}_t, \hat{\beta}_t)'$ with the continuous-time OU transition semigroup to project the multi-step-ahead spread trajectory.

### 4.1 Multi-Step Conditional Spread Distribution
At time $t$, given observed spread $S_t = y_t - \hat{\alpha}_t - \hat{\beta}_t x_t$, the forward spread at forecast horizon $t + h$ ($h \in \{1, 2, 3, 5, 10\}$ trading days) is conditionally Gaussian:
$$S_{t+h} \mid \mathcal{F}_t \sim \mathcal{N}\left( \hat{S}_{t+h|t}, \; \sigma_{h|t}^2 \right)$$
* **Conditional Point Forecast:**
  $$\mathbf{\hat{S}_{t+h|t} = \mathbb{E}[S_{t+h} \mid \mathcal{F}_t] = \mu + (S_t - \mu) e^{-\theta h}}$$
* **Conditional Forecast Variance:**
  $$\mathbf{\sigma_{h|t}^2 = \operatorname{Var}(S_{t+h} \mid \mathcal{F}_t) = \frac{\sigma^2}{2\theta} \left(1 - e^{-2\theta h}\right)}$$
* **Analytical 95% Confidence Interval Bounds:**
  $$\mathbf{\text{CI}_{95\%}(t+h) = \left[ \hat{S}_{t+h|t} - 1.96 \cdot \sigma_{h|t}, \quad \hat{S}_{t+h|t} + 1.96 \cdot \sigma_{h|t} \right]}$$

### 4.2 Translation to Asset Price Levels
Given current price $P_{2,t}$, the expected price of Asset 1 at horizon $t + h$ is:
$$\hat{P}_{1, t+h|t} = \exp\left( \hat{\alpha}_t + \hat{\beta}_t \ln(P_{2,t}) + \hat{S}_{t+h|t} \right)$$
These forecasts are dynamically regenerated daily by `update_strategy.py` and saved to `outputs/portfolio_spread_forecasts.csv`.

---

## Pillar 5: Market-Neutral Sizing & Discrete Microstructure Execution

### 5.1 Derivation of Market-Neutral Dollar Weights
When a trade signal is triggered for allocated capital $C_t = \$30,000$:
* Position State $\text{Pos}_t \in \{+1, -1, 0\}$:
  $$\text{Pos}_t = \begin{cases} +1 & \text{if } Z_t \le -1.25 \quad (\text{Long Spread: Long Asset 1, Short Asset 2}) \\ -1 & \text{if } Z_t \ge +1.25 \quad (\text{Short Spread: Short Asset 1, Long Asset 2}) \\ 0 & \text{if } |Z_t| \le 0.10 \text{ or } |Z_t| \ge 3.50 \text{ or } \Delta t \ge T_{\text{max}} \end{cases}$$

To ensure zero net sensitivity to Asset 2, dollar holdings $D_{1,t}$ and $D_{2,t}$ must satisfy:
$$\text{Beta Neutrality:} \quad D_{1,t} \cdot 1 + D_{2,t} \cdot \frac{1}{\hat{\beta}_t} = 0 \implies D_{2,t} = -\hat{\beta}_t D_{1,t}$$
$$\text{Capital Constraint:} \quad |D_{1,t}| + |D_{2,t}| = C_t \implies |D_{1,t}| (1 + |\hat{\beta}_t|) = C_t$$
Solving for continuous dollar amounts:
$$\mathbf{D_{1,t}^* = \text{Pos}_t \cdot C_t \cdot \frac{1}{1 + |\hat{\beta}_t|}}$$
$$\mathbf{D_{2,t}^* = -\text{Pos}_t \cdot C_t \cdot \frac{|\hat{\beta}_t|}{1 + |\hat{\beta}_t|}}$$
Unconstrained raw target shares:
$$S_{1,t}^* = \frac{D_{1,t}^*}{P_{1,t}}, \quad S_{2,t}^* = \frac{D_{2,t}^*}{P_{2,t}}$$

### 5.2 Board Lot Discretization Operator
In Singapore (SGX), equities trade strictly in **board lots of $L = 100$ shares**. In the US and Europe, $L = 1$. The executed share quantity is given by the floor integer operator:
$$\mathbf{S_{i,t} = \operatorname{sign}(S_{i,t}^*) \cdot \left\lfloor \frac{|S_{i,t}^*|}{L_i} \right\rfloor \cdot L_i}$$

#### Proof of Residual Delta Leakage (Hypothesis 1)
The executed dollar weight is $w_{i,t} = \frac{S_{i,t} P_{i,t}}{C_t}$. The residual dollar beta $\beta_{\text{residual}}$ is:
$$\beta_{\text{residual}} = w_{1,t} + \frac{w_{2,t}}{\hat{\beta}_t} = \frac{S_{1,t} P_{1,t} + \frac{1}{\hat{\beta}_t} S_{2,t} P_{2,t}}{C_t}$$
Because $|S_{i,t}^* - S_{i,t}| < L_i$, the maximum basis error $\Delta_{\text{error}}$ satisfies:
$$\Delta_{\text{error}} \le \frac{L_1 P_{1,t} + \frac{1}{|\hat{\beta}_t|} L_2 P_{2,t}}{C_t}$$
* **Case A: Singapore Large-Cap Banking (`D05.SI`, $P \approx \text{SGD } 38.00$, $L = 100$):**
  $$L_1 P_{1,t} = 100 \times 38.00 = \text{SGD } 3,800 \implies \frac{3,800}{30,000} = \mathbf{12.7\% \text{ tracking error!}}$$
  This large quantization error destroys market neutrality.
* **Case B: Singapore REITs (`M44U.SI`, $P \approx \text{SGD } 1.14$, $L = 100$):**
  $$L_1 P_{1,t} = 100 \times 1.14 = \text{SGD } 114 \implies \frac{114}{30,000} = \mathbf{0.38\% \text{ tracking error!}}$$
  The tracking error is virtually negligible.
* **Case C: US S&P 500 (`CAT`, $L = 1$):**
  $$L_1 P_{1,t} = 1 \times 378 = \$378 \implies \frac{378}{30,000} = \mathbf{1.26\% \text{ tracking error.}}$$

### 5.3 Complete Cash Accounting & PnL Formulation
At day $t$, given held shares $S_{1, t-1}$ and $S_{2, t-1}$:
1. **Asset Price PnL:**
   $$\Delta \Pi_{\text{price}, t} = S_{1, t-1} (P_{1,t} - P_{1, t-1}) + S_{2, t-1} (P_{2,t} - P_{2, t-1})$$
2. **Short Leg Borrow Fee Accrual:**
   $$\text{Borrow}_{t} = \left( \mathbb{I}_{\{S_{1, t-1} < 0\}} |S_{1, t-1}| P_{1, t-1} \cdot \frac{r_{\text{borrow}, 1}}{252} \right) + \left( \mathbb{I}_{\{S_{2, t-1} < 0\}} |S_{2, t-1}| P_{2, t-1} \cdot \frac{r_{\text{borrow}, 2}}{252} \right)$$
3. **Turnover Execution Fees:**
   $$\Delta S_{i,t} = |S_{i,t} - S_{i, t-1}| \implies \text{Fee}_t = \Delta S_{1,t} P_{1,t} c_1 + \Delta S_{2,t} P_{2,t} c_2$$
4. **Cash Collateral Yield Overlay:**
   Unencumbered margin equity $E_{\text{cash}, t} = C_t - \max(0, S_{1,t} P_{1,t}) - \max(0, S_{2,t} P_{2,t})$ earns:
   $$\text{Yield}_t = E_{\text{cash}, t} \cdot \frac{R_f}{252}, \quad R_f = 4.0\%$$
5. **Daily Net Portfolio Equity Update:**
   $$C_t = C_{t-1} + \Delta \Pi_{\text{price}, t} - \text{Borrow}_t - \text{Fee}_t + \text{Yield}_t$$

---

## Pillar 6: Theoretical Summary of Strategy Parameter Bounds

| Parameter | Mathematical Symbol | Value | Econometric Rationale & Justification |
| :--- | :--- | :--- | :--- |
| **ADF Significance Threshold** | $p_{\text{ADF}}$ | $\le 0.10$ | MacKinnon response surface threshold ensuring linear stationarity of spread. |
| **Johansen Rank Condition** | $\operatorname{rank}(\boldsymbol{\Pi})$ | $r \ge 1$ | Rejects spurious cross-correlation; confirms vector cointegration. |
| **OU Half-Life Filter** | $\tau_{1/2}$ | $[2.0, 90.0]$ days | Lower bound eliminates tick microstructure noise; upper bound prevents capital lockup. |
| **Kalman Process Covariance** | $\mathbf{Q} = \operatorname{diag}(Q_\alpha, Q_\beta)$ | $10^{-5} \cdot \mathbf{I}_2$ | Governs the drift velocity of $\beta_t$, calibrated to balance responsiveness and stability. |
| **Kalman Measurement Variance** | $R$ | $10^{-3}$ | Models microstructural observation noise from bid-ask bounce and tick rounding. |
| **Spread Entry Threshold** | $Z_{\text{entry}}$ | $\pm 1.25$ | Exceeds the theoretical no-arbitrage bandwidth $|Z^*| \ge \frac{2 c_{\text{round}} + \Delta t \cdot r_{\text{borrow}}}{\sqrt{F_t}}$. |
| **Spread Exit Threshold** | $Z_{\text{exit}}$ | $\pm 0.10$ | Captures ~92% of the total theoretical mean-reversion mispricing potential. |
| **Stop-Loss Circuit Breaker** | $Z_{\text{stop}}$ | $\pm 3.50$ | Tail risk truncation; cuts non-reverting losses from structural regime breaks ($p < 0.0005$). |
| **Maximum Holding Horizon** | $T_{\text{max}}$ | $2.5 \times \tau_{1/2}$ | Expected decay $>82.3\%$; liquidates stagnant capital if mean reversion stalls. |

---

## Pillar 7: Codebase Implementation Mapping

| Theoretical Mathematical Concept | File Implementation | Core Classes & Methods |
| :--- | :--- | :--- |
| **ADF, Engle-Granger & Johansen Cointegration** | `src/pair_selection.py` | `PairSelector.test_cointegration()`, `engle_granger()`, `coint_johansen()` |
| **Continuous-Time OU Estimation & Half-Life** | `src/ou_process.py` | `OrnsteinUhlenbeckEstimator.fit_ar1()`, `calculate_half_life()` |
| **State-Space Dynamic Kalman Filtering** | `src/kalman_filter.py` | `KalmanFilterRegression.update()`, `run_filter()` |
| **Multi-Horizon Spread Forecasting (Slide 1)** | `src/forecasting_engine.py` | `SpreadForecastingEngine.forecast_spread()`, `generate_live_signal()` |
| **Board Lot Quantization & Event Simulation** | `src/backtest_engine.py` | `PairsBacktestEngine.run_backtest()`, `get_market_microstructure()` |
| **Multi-Pair Portfolio Aggregator** | `src/portfolio_engine.py` | `PortfolioEngine.run_portfolio_backtest()` |
| **CAPM & Fama-French 3-Factor Regression** | `src/performance.py` | `calculate_performance_metrics()`, `regress_fama_french_3factor()` |
| **Live Daily Strategy Updating Script** | `update_strategy.py` | CLI execution generating `live_strategy_signals.csv` & plots |
