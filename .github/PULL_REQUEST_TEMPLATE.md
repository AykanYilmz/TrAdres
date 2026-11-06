## What does this change?

<!-- One or two sentences. Link the issue if there is one: "Fixes #12". -->

## Accuracy

<!-- If this changes parsing, paste the numbers from `uv run python -m eval`. -->

| | Before | After |
|---|---|---|
| Exact addresses | | |
| F1 | | |

## Checklist

- [ ] There is no real person's address in this pull request.
- [ ] `uv run pytest` passes.
- [ ] `uv run ruff check .`, `uv run ruff format --check .` and `uv run mypy` pass.
- [ ] I did not read or change `eval/holdout/` or `eval/holdout2/`.
- [ ] A new behaviour has a test, or a case in `eval/addresses/katkilar.yaml`.
- [ ] `CHANGELOG.md` has a line under `[Unreleased]` for a change users can see.
