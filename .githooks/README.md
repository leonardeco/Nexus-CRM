# Git hooks

This directory is `core.hooksPath` for this clone. The `commit-msg`
hook drops tool-attribution trailers so history stays under the
local git user.

Enable once per clone:

```
git config core.hooksPath .githooks
```
