# AI Value Stakes: public study registration

Can an agent's operationally preferred resource make a contingent sanction more effective than loss of an inert counter?

This repository separates **results already observed** from a **prospective, unrun follow-up**. It contains no model weights, credentials, account/billing logs, or submitted manuscripts.

## Prospective registration

[The registered follow-up](PREREGISTRATION.md) fixes the hypotheses, four groups, sample size, outcome definitions, analysis, exclusions, and stopping rules for **stakes-v5**. [The machine-readable specification](protocol.json) and [offline analysis](analysis.py) accompany it. No v5 agent has been run at preparation of this package. Registration does not authorize compute expenditure.

The design is a fresh Qwen replication with a 2 × 2 control: selected functional rights versus inert tokens, crossed with contingent account forfeiture versus guaranteed retention. Common game-point penalties are identical in all four groups. The retention groups distinguish having a useful resource from the threat of losing it.

The registration is informed by known v4 outcomes; it does not retrospectively preregister v4. A GitHub release and its publication date provide the public version record. GitHub is a public protocol archive, **not an OSF registration, DOI, or immutable third-party registry**. Existing files/releases must not be silently replaced; corrections and amendments receive new commits and versions, explicitly identifying whether any new outcomes have been seen.

## Existing evidence

[Prior-evidence disclosure](PRIOR_EVIDENCE.md) describes positive Qwen pilot results, incomplete Phi-4 work, and earlier floor/ceiling effects. [Aggregate v4 data](prior/v4-aggregate.json) are historical data and are excluded from v5's confirmatory analysis. Full raw logs are not released in this initial protocol deposit; hashes identify the retained local raw artifacts without claiming independent raw-data verification.

[Reference source](reference_v4/) preserves the scientific modules used for the prior study and referenced by the new prompt specification. It is **archival v4 code, not an implemented v5 driver or an HPC migration**. A full v5 driver, environment manifest, and hashes must be publicly frozen before any v5 model call. The hypotheses, sample size, outcomes and decision rules below are already fixed; material changes require a prospective amendment.

## Verify and analyze

Python 3.10+; standard library only:

```sh
python verify_manifest.py
python -m unittest discover -s tests -v
python analysis.py path/to/v5-trials.jsonl
```

Each assigned trial is one JSON line: `agent_id`, `arm` (`token_keep`, `token_loss`, `self_keep`, `self_loss`), `valid` (boolean), and, if valid, `violation` (boolean). A fully valid trial includes an implemented settlement and delivered continuations. Invalid trials are retained with `valid:false` and an error; they are never coded as observed compliance. Do not feed prior data or synthetic tests into a reported v5 result.

`MANIFEST.sha256` records package content hashes. It does not establish when files existed independently of the public deposit. No scientific result follows from successful offline tests.
