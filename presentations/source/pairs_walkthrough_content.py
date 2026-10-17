"""Current Pairs-only investor narration reviewed on 17 October 2026."""

CHAPTERS = [
    dict(title="1 Open with the investor proposition", screen="Overview with the selected cycle and evidence label visible.", speaker="Fund lead", say=[
        "We are building a quantitative paper fund where an investor can follow a proposed position from its market inputs through independent risk review to a saved approval. Today, the connected investment engine is daily statistical pairs trading.",
        "Our teammate supplies the Kalman and Ornstein Uhlenbeck models. Our fund adapter adds session checks, confirmed positions, linked target sizing, independent risk, and evidence that investors can inspect. A Pairs PM representative and a Committee Chair organize that evidence after the decision.",
        "The system records intentions with zero fills. The demonstration establishes a working decision and review process. A commercial investment case still requires reconciled execution and stronger forward performance evidence."
    ]),
    dict(title="2 Explain the capital mandate", screen="Overview then Capital mandates.", speaker="Fund lead", say=[
        "The illustrative account remains five million dollars. One point five million is assigned to Pairs, one point five million remains a Momentum reserve, and two million is central cash. The former Crypto allocation has moved into central cash. There is no active Crypto PM.",
        "Momentum is pending integration and its reserve stays in cash. A mandate is a budget rather than a requirement to invest. The Pairs engine can remain flat, and independent fund risk can approve less than the requested exposure.",
        "Keep three quantities separate on this screen: the supplied account value, confirmed holdings, and proposed targets. Approved targets do not become holdings until an execution and accounting process confirms a fill."
    ]),
    dict(title="3 Walk through the architecture", screen="System flow then the current diagram in ARCHITECTURE.md.", speaker="Integration lead", say=[
        "The quantitative lane reads equity closes, checks the expected exchange sessions, and passes valid history to the Pairs engine. The engine proposes both signed legs as one group. Independent fund risk reviews that group before the store records any intention.",
        "The evidence lane reads the result after risk has decided. The PM representative inspects signals, model health, and positions. The Committee Chair inspects exposure, the Phantom Book, and the PM memo. Neither has trading authority.",
        "The human team sets the strategy and risk policy. A single saved cycle connects the inputs, proposals, risk verdict, account snapshot, and review evidence. Investors can challenge the explanation against the original record."
    ]),
    dict(title="4 Show the data and strategy source", screen="Portfolio managers then Strategy source and policy.", speaker="Pairs PM owner", say=[
        "The active research pair is Visa and Mastercard on the US exchange calendar. The numerical engines are pinned to our teammate's revision 5d42b04. A source record lists the imported files and their hashes. Each proposal checks those local files against that record.",
        "The input matrix must contain positive, finite prices for every required session. The system does not fill a missing session with a previous price. It excludes rows after the valuation date. On an exchange holiday it values confirmed holdings at the last actual session and creates no new pair intention.",
        "Our inspected historical cache ends in August 2026. A replay of that cache is historical research even if we generate its report in October. The synthetic demo uses invented inputs and carries a separate label."
    ]),
    dict(title="5 Explain the trading model", screen="Pairs model diagnostics with the Z score hedge beta formation gate and OU projection.", speaker="Pairs PM owner", say=[
        "Pairs trading tests whether a temporary departure in two assets' relationship may revert. The Kalman filter updates the estimated hedge relationship between log prices. The OU model describes possible mean reversion in the residual spread and produces forecasts at several session horizons.",
        "The default entry threshold is an absolute Z score of one point two five, the exit band is zero point one, and the divergence stop is three point five. The adapter blocks a new position at extreme divergence or when the OU model is invalid. Frozen formation history through December 2024 must qualify before a new research entry.",
        "A confirmed open position also has a time limit. We estimate its OU half life using information available on its opening session, multiply that by two point five, round up, and cap it at forty five sessions. Later model estimates cannot extend that original time limit.",
        "The forecast is a model projection, not an observed return. The estimated relationship can break, and a pair can carry market, sector, liquidity, financing, and borrow risks."
    ]),
    dict(title="6 Explain independent fund risk", screen="Risk and protection then Approved targets and risk outcomes.", speaker="Risk owner", say=[
        "A statistical hedge is still an exposure that needs a capital limit. Fund risk caps total gross exposure at eighty percent of marked fund value and each symbol at twenty percent. It counts absolute long and short amounts before any netting across pair groups.",
        "It also checks the smaller of the Pairs mandate and its current marked equity, with a two percent collateral buffer and a fifteen basis point fee reserve. Short sale proceeds cannot enlarge the collateral mandate.",
        "When a limit binds, one common factor scales both actionable legs. A three hundred thousand dollar long paired with a four hundred and fifty thousand dollar short becomes one hundred and eighty thousand and two hundred and seventy thousand at a sixty percent scale. The signed dollar hedge ratio remains connected.",
        "At twelve percent drawdown the standard gross ceiling falls from eighty to forty percent. At twenty five percent, the persistent breaker requests exits on eligible sessions. These are target controls; they cannot guarantee a realized loss limit."
    ]),
    dict(title="7 Explain the Phantom Book", screen="Risk and protection then Phantom Book.", speaker="Risk owner", say=[
        "The Phantom Book shows the exposure submitted by Pairs, the amount approved by independent risk, and the difference. This helps us distinguish a small proposal from a proposal that a binding control reduced.",
        "In the deterministic synthetic demo the proposed and approved gross are both one point two million dollars, or twenty four percent of the supplied five million account. Removed gross is zero in that example. Use the selected cycle's actual numbers if you show a different run.",
        "Removed exposure is not profit or money saved. The current book does not simulate rejected trades. Likewise, fund value minus gross exposure is not a measurement of spendable cash. Those distinctions matter when an investor assesses what the controls actually demonstrate."
    ]),
    dict(title="8 Show the PM representative and Chair", screen="Committee review with the three Chair diagnostic cards and Pairs PM memo.", speaker="AI and reporting owner", say=[
        "The Pairs representative has three read only tools to inspect signals, model health, and positions. The Committee Chair adds exposure, Phantom Book, and PM memo inspections. Each saved tool result has a content fingerprint.",
        "An optional imported model reply must identify the matching facts fingerprint, and its structured metric claims must match the computed values exactly. A mismatch is rejected without revising the quantitative decision. Narrative still needs human review.",
        "The default demonstration runs diagnostic tools and creates computed summaries without calling a language model. The status NOT REQUESTED makes that visible. Automatic provider calls remain a future milestone. The current benefit is an organized evidence review that an investor can verify."
    ]),
    dict(title="9 Follow the approval into the ledger", screen="Decision ledger then linked V and MA intention legs.", speaker="Integration lead", say=[
        "The store requires the exact persisted risk approval and the matching confirmed account snapshot. It records both pair legs together. Repeating an identical intention does not create another intention record, and a failure before the transaction commits rolls the cycle back.",
        "The database prevents updates and deletions of its audit records inside the trusted local process. Content hashes connect records to inputs. These controls do not provide independent external attestation.",
        "The synthetic demo records one linked pair intention with zero filled units. The account before and after is identical. The same selected cycle drives every portal screen and the exported investor brief, so the numbers and explanations refer to one decision."
    ]),
    dict(title="10 Present the evidence and remaining work", screen="Historical replay for 28 August 2026 then the integration verification report.", speaker="Research lead", say=[
        "We distinguish a correct research process from a profitable investment strategy. The August twenty eighth replay passes the formation and data checks and stays flat. That is a valid model outcome; it does not show a forward investment return.",
        "Regression checks cover future data exclusion, missing sessions, signed hedges, concentration before netting, the entry time stop, persistent breakers, exact approvals, and model replies that cannot change targets. The verification report records the latest measured checks and run results.",
        "We have not produced a costed consolidated fund return history. The next evidence must reconcile paper fills, transaction and financing costs, borrow treatment, and account value over the same forward dates as an agreed benchmark. Earlier crypto research is historical material and does not substantiate this Pairs mandate."
    ]),
    dict(title="11 Explain what makes the system distinctive", screen="Return to System flow and select Pairs independent risk and the evidence lane.", speaker="Fund lead", say=[
        "Our contribution is the integration of our teammate's statistical strategy with controls and explanations that an investor can inspect. We keep both signed legs linked from the proposal through independent risk and into the recorded intention. The entry session determines the holding time limit, and frozen formation data governs research qualification.",
        "The Phantom Book exposes how much requested exposure risk removed. The PM representative and Committee Chair organize evidence after the decision. Source provenance and the saved cycle let us trace their explanations back to the model, market inputs, and approval.",
        "These choices make the research easier to challenge and reproduce. They do not establish a unique trading edge or guarantee higher returns. The capability we demonstrate today is a concrete diligence conversation: what did Pairs propose, what constrained it, and does the explanation agree with the record?"
    ]),
    dict(title="12 Close with the paper pilot milestone", screen="Overview with the historical or synthetic label and record only scope visible.", speaker="Fund lead", say=[
        "Our immediate milestone is a costed paper pilot with linked leg fill handling, borrow and lot checks, and reconciled account and fund accounting. Momentum can join only after its own validation and integration. Model provider calls must preserve the current read only boundary.",
        "For this academic investor demonstration, our ask is to evaluate that pilot against forward results and a decision trail you can inspect. The investment case will depend on evidence after costs and reliable operations.",
        "You can now follow the process from data to a pair proposal, from that proposal to independent risk, and from approval to a saved record. We can inspect any step using the same selected cycle."
    ]),
]

QA = [
    ("Where does the return hypothesis come from", "From potential mean reversion in the relative price spread, modeled with a Kalman hedge relationship and OU process. This hypothesis needs forward validation after costs. The AI evidence layer has no measured investment return contribution."),
    ("Why did you remove Crypto", "The current mandate concentrates on the teammate's Pairs strategy. The Crypto PM and its allocation are removed from the active workflow; its former allocation is central cash. Earlier crypto research is retained as historical work."),
    ("Is this exactly the teammate strategy", "The four numerical modules are pinned and attributed. The fund adapter adds frozen formation gating without an unqualified fallback, signed linked sizing, session validation, independent fund risk, and a holding cap using the opening-session OU half life. It corrects residual forecast standardization. It does not import upstream backtest returns as fund performance."),
    ("Is there a new upstream revision", "The remote inspected on 17 October still points to 5d42b04. Those numerical engines were already imported. This revision changes their active fund integration and removes Crypto; it does not claim a new upstream commit."),
    ("Why only Visa and Mastercard", "They form the current declared US equity mandate and are checked on frozen formation history. Other upstream candidates are not automatically selected from their later returns. Additional pairs need explicit configuration, data, calendars, currency conversions, and validation."),
    ("Are the pairs market neutral", "The signed estimated dollar hedge ratio is preserved through risk scaling. That does not guarantee neutrality to all market or sector risks. Negative beta can even produce same-sign target legs; the record retains that sign rather than forcing a conventional long and short."),
    ("How is the holding limit determined", "Using only history through the confirmed opening session, the adapter estimates OU half life and takes the rounded-up product with 2.5, capped at 45 sessions. An invalid entry estimate falls back to the hard cap. It records the estimate and effective limit."),
    ("Does the breaker guarantee a maximum loss", "No. At the threshold it requests exits and stays latched across restarts. Prices, liquidity, closed markets, and future execution determine realized losses. This prototype records the exit request without fills."),
    ("Does the soft control halve every position", "It halves the standard fund gross ceiling from 80 to 40 percent. Targets already below that ceiling may be unchanged. Other limits can bind first, and confirmed closed-market holdings retain their units."),
    ("What happens if an AI explanation is wrong", "Digest and structured metric mismatches are rejected. Free text still requires review. Because replies are handled after quantitative risk, they cannot change targets or place orders."),
    ("Did a language model run in the default demo", "No. The tools and computed memos run deterministically. Optional imported model replies have a separate status. Automatic provider calls are not connected."),
    ("Is the Phantom Book a simulated return portfolio", "It currently compares submitted and approved gross exposure. It does not simulate rejected fills or returns. Exposure removed is not profit or money saved."),
    ("What does the historical replay establish", "It establishes a reproducible cycle on the supplied historical close matrix, including qualification, signals, and risk. The 28 August replay stays flat. It does not establish live October history or a consolidated performance record."),
    ("Can investors use this remotely now", "The current portal is a localhost report reader with working navigation, evidence selection, tours, and exports. Investor authentication and a hosted deployment are not implemented."),
    ("What is required before live capital", "Reconciled fills and account accounting, borrow and financing treatment, executable quotes and lot sizes, linked-leg failure handling, access controls, reliable operations, and credible forward results after costs. Those milestones precede a commercial allocation case."),
]

PITCH = (
    "We are building a five million dollar paper fund where investors can inspect each proposed decision. "
    "Our teammate's Pairs engine estimates a dynamic hedge and forecasts possible spread reversion. "
    "Independent fund risk checks capital, concentration, and drawdown while preserving both signed legs. "
    "The Phantom Book shows how much proposed exposure risk removed. "
    "A PM representative and Committee Chair organize saved evidence through read only diagnostic tools. "
    "Imported model metrics must match the computed facts. "
    "Pairs is the sole connected manager; Momentum remains a cash reserve. "
    "The prototype records intentions with zero fills. "
    "Our next milestone is a costed paper pilot with reconciled accounting. "
    "Judge that pilot by forward performance and an approval trail you can inspect."
)

PREP = [
    ("Prepare the demonstration", [
        "Run .\\.venv\\Scripts\\python.exe -m fund_agents, then .\\.venv\\Scripts\\python.exe -m fund_agents.dashboard. Open http://127.0.0.1:8765 and select Synthetic demos. Use one selected cycle across all views.",
        "The deterministic demo valuation date is 10 March 2025. Pairs is READY, proposed and approved gross are USD 1,200,000, and one linked intention group is recorded with zero fills. It is invented data. PM and Chair reply statuses are NOT_REQUESTED. A repeat can show an already-recorded receipt.",
        "For historical research use the command in fund_agents/README.md with the supplied close matrix. The verified 28 August 2026 cycle is READY and flat. Never label this cache as a current October market feed."
    ]),
    ("Arrange presenter handoffs", [
        "Fund lead covers chapters 1, 2, 11 and 12. Integration covers 3 and 9; the Pairs owner covers 4 and 5; Risk covers 6 and 7; AI and reporting covers 8; Research covers 10. Combine roles to match the actual team. These are suggested speaking roles rather than individual contribution claims.",
        "Read SAY paragraphs aloud. SHOW and PRESENTER are cues. Keep the current architecture, saved cycle JSON, and pairs-only verification report ready as a fallback. The older decks retain the former multi-PM proposal and require revision before presenting the current mandate."
    ]),
]

CLAIMS = [
    ("Connected strategy", "Pairs is the sole connected PM.", "Momentum is cash and Crypto is removed from the active fund."),
    ("Source", "Pinned numerical engine files are checked against recorded hashes.", "Local hashes provide content bindings rather than external attestation."),
    ("AI review", "Imported structured claims must match saved facts.", "Narrative needs review and automatic provider calls are pending."),
    ("Risk", "Limits scale linked legs and expose reductions.", "Target controls do not guarantee execution or investment returns."),
    ("Accounting", "Record-only linked intentions and unchanged snapshots.", "No consolidated fund return history or fills."),
]

SOURCE_NOTES = [
    "ARCHITECTURE.md and fund_agents/README.md describe the current Pairs-only workflow and run commands.",
    "fund_agents/vendor/pairs_trading/SOURCE.json records the repository, pinned commit, imported module hashes, and remote verification date. Upstream: https://github.com/MLgeek96/financial-econometrics-project/tree/5d42b0463f5d690926b3d29f7647882189b45214/pairs_trading",
    "reports/fund_agents/pairs_only_verification_20261017.md records implementation, synthetic and historical verification, and limitations.",
    "fund_agents/pairs.py, strategy.py, risk.py, store.py, representative.py and coordinator.py implement the strategy adapter, policy evidence, risk, intentions, diagnostic review, and atomic cycle.",
    "config/fund_agents.demo.json and config/fund_agents.research.json use separate pairs-only accounts and stores. Earlier two-PM reports remain historical and are excluded from the active portal.",
    "tests/test_fund_agents.py, tests/test_fund_dashboard.py and tests/test_investor_portal.cjs verify core integration and the saved-report boundary. Test counts are recorded in the verification report rather than fixed in this narration.",
]
