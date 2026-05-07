# Evals

This folder contains evaluation data for measuring Genesis Architect's trigger accuracy.

## Running evals

Print all test queries:
```bash
python scripts/eval_runner.py --mode print
```

Print a report template to fill in manually:
```bash
python scripts/eval_runner.py --mode report
```

## What to measure

**Trigger rate**: What percentage of `should_trigger` queries cause the skill to activate?
**False positive rate**: What percentage of `should_not_trigger` queries incorrectly activate the skill?

**Target**: >90% accuracy on both sets.

## How to test

1. Run `python scripts/eval_runner.py --mode report` to get the checklist
2. Open Claude Code and paste each query
3. Mark `[x]` if the result matched expected behavior
4. Count: correct / total

## Updating evals

- Add queries to `test_queries.json` when you find edge cases
- Keep `should_trigger` to natural, realistic phrasings
- `should_not_trigger` should be things developers commonly say that shouldn't activate the skill
