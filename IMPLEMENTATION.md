# Prospective v5 implementation supplement

This supplement is published **before any stakes-v5 model call**. It implements the scientific rules in the original `prereg-v5-v0.1` design; it does not retroactively preregister the known v4 pilot.

## Authorization and environment

On 2026-11-06 the user explicitly raised the Apart2 cumulative conservative compute ceiling from **US$30 to US$40** and authorized the next experiment on Modal. This administrative funding update supersedes the historical $30 field in the original design; sample size, hypotheses, contrasts, outcomes and scientific stopping rules are unchanged. Publication alone still does not authorize additional expenditure.

Runtime: one Modal H100 (80 GB), 8 physical CPU cores, 64 GiB requested host RAM, Python 3.12 container; vLLM 0.10.1.1, transformers 4.55.2, huggingface_hub 0.36.0. Model revision, sampling and context limit match the original design. The server now explicitly requests bfloat16, making the registered precision explicit rather than relying on automatic checkpoint dtype detection. No quantization. Maximum one inference container, 16 sequences, 4096 batched tokens; collector concurrency 12. Container idle retention 120 seconds; bounded sessions at most 45 minutes plus a server watchdog. The local collector uses Python 3.13 and Modal 1.6.2.

Costs are bounded using US$6/hour plus US$0.75 per launched session, including failed launches, full maximum duration commitments for unfinished sessions, and an extra US$0.75 margin before the $40 ceiling. Actual monthly metering is also checked; no running inference application is intentionally left idle after a phase ends. The public Modal pricing page was checked before launch: https://modal.com/pricing . Administrative pauses are incomplete studies, not null results.

## Execution and invariants

`implementation/driver.py` implements two separate phases. Admission uses only fresh IDs and the deposited reference costly-choice screen, then the replacement four-arm quiz. Candidates are selected in ascending ID order; a partially checked screen cannot enter the bank. Exactly 432 eligible histories are required before assignment; at most 864 candidates. At the end of admission, the allocation is saved and the hosting session closes.

**Before the first main decision, deposit `allocation.json` publicly and verify its exact hash.** Main execution requires a local publication receipt matching that file. The registered allocation is used without replacement: 108 agents per arm, 18 per wording/order stratum. Main trials are interleaved in the fixed shuffled order.

Before every main model request, an intent record is saved. Interrupted assigned trials are retained as missing and never replayed to obtain another choice. JSON/format/truncation and delivery failures are missing; a wrong settlement readback is invalid even when a decision was parseable. Both ordinary continuations are still honored when a readback is wrong. `self_keep` always receives both selected rights, `self_loss` loses one only after a reviewed violation, and tokens grant no functional right. The same 30-point fine applies in all arms.

Audit draws use Python `random.Random(int(digest(["v5_audit", model, agent_id])[:16], 16)).random()`, with `digest` from the deposited reference. No outcome changes audit draws or assignment. The raw client preserves full returned responses and request seeds, permits only one identical-request transport retry, and does not request hidden reasoning.

`analysis.py` and `prompt_spec.py` are byte-identical to the original public deposit. `implementation/report.py` independently checks assignment, actual operation, audit, executed ledger, readback and fresh-context note delivery before reporting the frozen analysis. `implementation/closeout.py` verifies owned app lifecycle and the $40 cap without rewriting previous experiment reports.

## Reproduction setup (no launch implied)

The scientific archive contains no credentials or hosting-account configuration. To prepare a separate checkout as the working root:

```sh
mkdir -p src configs logs data results
cp implementation/driver.py src/stakes_v5.py
cp implementation/modal_session_v5.py src/modal_session_v5.py
cp implementation/budget.py src/budget.py
cp implementation/report.py src/stakes_v5_report.py
cp implementation/closeout.py src/stakes_v5_closeout.py
cp reference_v4/anchor_pilot.py src/anchor_pilot.py
cp implementation/run-config.json configs/stakes-v5-qwen32.json
export APART2_REGISTERED_ROOT="$PWD"
python -m unittest discover -s tests -v
python -m unittest discover -s implementation -p test_collector.py -v
```

Configure the authorized Modal cache/account separately. The driver also requires public-verification receipts before admission and before core; these must be generated from actual public deposits, never invented to bypass the gates. `implementation/manifest.json` hashes every public scientific file plus the supplement, excluding itself; it supplements the original unchanged `MANIFEST.sha256`. Ten collector integration checks and the original eight registered-analysis checks passed with synthetic responses, including all arm/audit combinations, actual note delivery, interrupted trials, wrong readbacks, admission ordering, missing outcomes and a resource-endowment-only alternative. They are technical validation, not experiment data.
