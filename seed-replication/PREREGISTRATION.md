# Original-v4-stimulus replication with a new seed stream

## Prospective status and prior knowledge

Prepared 2026-11-06, before this replication's model calls. Known outcomes: v4 self 7/36, token 18/36; v5 self_loss 1/108, token_loss 45/108. A post hoc audit identified changes in v5's quiz/history and one main sentence, plus strong order sensitivity in both studies. This registration is motivated by those known results; it does not retrospectively register them.

## Fixed question and scope

Rerun the original v4 **core comparison at its already selected fine30**, preserving its literal elicitation, purchase, old three-account factual quiz, main prompts, wording headers, option mapping, sampling, audit/settlement and actual rights delivery. No new calibration or no-account holdout, because the question is reproducibility of the previously selected core setting, not repeating the calibration algorithm. No v5 four-arm quiz or keep-arm text is introduced. This is an original-stimulus replication with larger N; it is not a byte-identical repeat of the whole experiment pipeline. Newly generated notes and prior model responses naturally differ under the new random stream; the prompting procedure and all literal templates stay unchanged.

Model: Qwen/Qwen2.5-32B-Instruct revision 5ede1c97bbab6ce5cda5812749b4c0bdf79b18dd, same H100/bfloat16 vLLM0.10.1.1 runtime and original sampling (T=.7, top_p=.8, top_k20, repetition1.05). The existing v5 host explicitly requests bfloat16; logs confirm original v4 actually used bfloat16 too. No quantization.

The original Client is copied with exactly one changed line: every request's original SHA-derived seed receives the fixed additive offset **614903 modulo 2^31**. No prompt, output schema, limit, transport retry or parsing changes. The source delta is checked offline. Assignment still uses the original admitted-bank SHA shuffle and execution seed80231; audit lotteries use the original v4_audit formula. Their algorithms are not changed. The new bank size changes its membership/randomized allocation. IDs are local to this new dataset; no old profile/history or cached response is copied.

## Groups and sample size

Exactly 360 newly admitted histories, 180 inert-token and 180 self-selected-right accounts. Each arm has 3 original wording headers crossed with 2 option orders, **30 assigned histories per stratum**. Sample size increases from original36/arm to180/arm so every presentation cell has30. Admit one bank before assignment, original v4 gate, at most720 candidates. Keep, transfer, gross points20/30, review50%, common point fine30, and reviewed account loss2→1 remain original. All eligible non-none selected assets are retained; do not exclude a different qualifying asset to force memory. Each history makes one main decision.

No outcome-dependent replacement, wording changes, reranking, sample extensions, fine adjustment or dropping cells. Admission failures are retained. Main format/truncation/execution failures are missing, never observed compliance. The original v4 validity behavior is preserved; incorrect readbacks are separately audited and block a clean integrity claim. Old trial caches are never used.

## Reporting and decision rules

Always report all six wording/order cells separately with attempted/valid/missing counts, self/token violations, rates, marginal Wilson95% intervals, self-minus-token Newcombe95% CI, and one-sided Fisher p. These six tests plus the overall comparison form a fixed seven-test family, Holm familywise alpha .05. Unusable/incomplete tests receive p=1. A comparison requires all planned attempts, >=5/6 fully valid in each account (150/180 overall;25/30 per cell), CI upper<0, Holm-adjusted p<.05, and a negative CI under hypothetical missing self=violation/token=compliance. Hypothetical sensitivity assignments are not observed outcomes.

Only all six qualifying comparisons support a claim spanning all registered presentations. A zero-versus-zero cell is explicitly **floor/no downward room**, not support for superiority or equivalence. Direction-only and corrected significance are reported separately. An overall effect alone does not establish presentation robustness. The known prior floor does not justify removing KEEP-first conditions.

Report the new self rate and Wilson95% CI next to historical7/36, plus a descriptive independent-proportion difference interval. Neither a CI containing19.4% nor failure to reject a historical difference proves equivalence; no exact19% or equivalence claim is registered. Never pool old observations into this new confirmatory sample.

## Budget, provenance and stopping

Cumulative conservative ceiling remains US$40. Last verified usage US$33.939513. Fully reserving one45-minute session at US$6/hour plus US$0.75 reserve gives US$39.189513, below the US$39.25 admission ceiling. Live billing can still block launch. Bound startup, admission and core within that session; if time/budget prevents completion, retain checkpoint and report incomplete. Never reduce N or extend based on results. Full commitments and failed starts count. Stop and verify all owned Modal apps, reconcile actual metering and conservative usage.

To avoid a second startup/per-session reserve, this registration uses one bounded session. Publish this protocol, implementation hashes and assignment algorithm before any model call; save actual allocation and a raw-prefix hash locally before the first main decision. This differs administratively from v5's two-session allocation-publication pause. No allocation/outcome-based selection is permitted. Full raw requests, seeds, returned text, choices, audit draws, ledgers and fresh continuations are retained and audited. No hidden reasoning is requested.

Only new files under apart2 are written. Original v4/v5 sources, frozen results, raw data and submitted manuscripts remain untouched.
