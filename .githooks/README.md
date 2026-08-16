# Git hooks

This directory is the repo `core.hooksPath`. The `commit-msg` hook strips
tool attribution trailers (`Co-authored-by: Cursor`, and similar) so the
published history stays under the local git user.

Enable once per clone:

```
git config core.hooksPath .githooks
```
