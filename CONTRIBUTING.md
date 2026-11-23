# Contributing to frappix

Thank you for helping. Bug reports, fixes, tests and documentation are all
welcome.

## Before you start

- For a bug, open an issue with the frappix version, the Frappe version and a
  minimal example.
- For a new feature, open an issue first so the scope can be agreed before
  you write code.
- For a security problem, do **not** open an issue. Follow
  [SECURITY.md](SECURITY.md).

## Making a change

1. Fork the repository and create a branch from `main`.
2. Set up the project and learn the layout from the
   [developer guide](docs/DEVELOPMENT.md).
3. Add or update tests. A change to behaviour needs a test that fails without
   it.
4. Run the checks:

   ```bash
   uv run ruff check . && uv run ruff format --check .
   uv run mypy
   uv run pytest --cov
   ```

5. Add a line under `Unreleased` in [CHANGELOG.md](CHANGELOG.md).
6. Open a pull request. Use a
   [Conventional Commits](https://www.conventionalcommits.org) title, such as
   `fix(protocol): encode '#' in document names`.

## What reviewers look for

- The sync and async clients stay identical in behaviour.
- The security rules in the developer guide still hold.
- Public functions are typed and documented.
- No new runtime dependency without a strong reason.

By contributing you agree that your work is released under the
[MIT License](LICENSE).
