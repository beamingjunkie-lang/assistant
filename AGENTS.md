# Repository Workflow

`https://github.com/beamingjunkie-lang/assistant.git` on `main` is the
authoritative destination for generated code. Work in the checkout that tracks
this remote; do not create or update a separate copy of the project.

For every completed change, use this order:

1. Fetch `origin/main` and confirm the working tree state.
2. Make one coherent, scoped change.
3. Run the smallest relevant test, then the full existing test suite when the
   change affects shared behavior.
4. Review the diff and confirm it contains no credentials, generated build
   output, or unrelated edits.
5. Commit the completed change with a clear message.
6. Push that commit directly to `origin/main`.

Do not force-push, rewrite history, or bypass validation. If `main` advances
while work is in progress, integrate the remote changes before pushing.
