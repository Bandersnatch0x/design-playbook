# Dogfood NNN - <scene>

Date: YYYY-MM-DD
Ask: <one-line product UI ask>
Scene: <class, chosen to differ from prior dogfoods>

## Process gates (six)

| Gate | Pass |
| --- | --- |
| L5/L6 present before pretty UI | |
| Decision report before code | |
| Point-back evaluator findings | |
| No skip of Done when | |
| Generalizes (not hardcoded to one scene) | |
| Recirculate closure (blocking -> fix -> re-eval -> 0 blocking, or accepted) | |

## Point-back findings

- <declaration>: <issue> (<severity; blocking?>)

## Recirculate closure trail

For each blocking finding, record: `recirculate -> fix -> re-eval -> 0 blocking` (or explicit acceptance + reason).

- blocking: <issue> -> reopen <declaration> -> fix <what> -> re-eval <result> -> 0 blocking | accepted: <reason>

## Process gaps / skill fixes

- <none, or: skill / symptom / proposed fix (completion criterion or pointer)>

## Verdict

<pass/fail across six gates; one line>
