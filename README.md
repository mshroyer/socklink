# tsock

A zero-dependency, cross-platform `SSH_AUTH_SOCK` wrangler for tmux.

(It's just a shell script, the Python is all tests.)

## Tests

You can run the unit tests with [uv](https://docs.astral.sh/uv/):

```
% uv run pytest
```

The tests will use your system versions of `tmux` and any shells available for
test.
