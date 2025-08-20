# tsock.sh

A zero-dependency, cross-platform `SSH_AUTH_SOCK` wrangler for tmux.

(It's just a shell script, the Python is all tests.)

## Tests

| Platform  | Status                                                                                                                | Runs on  |
|-----------|-----------------------------------------------------------------------------------------------------------------------|----------|
| alpine    | [![status badge](https://builds.sr.ht/~mshroyer/tsock/alpine.svg)](https://builds.sr.ht/~mshroyer/tsock/alpine)       | schedule |
| archlinux | [![status badge](https://builds.sr.ht/~mshroyer/tsock/archlinux.svg)](https://builds.sr.ht/~mshroyer/tsock/archlinux) | schedule |
| debian    | [![status badge](https://builds.sr.ht/~mshroyer/tsock/debian.svg)](https://builds.sr.ht/~mshroyer/tsock/debian)       | schedule |
| fedora    | [![status badge](https://builds.sr.ht/~mshroyer/tsock/fedora.svg)](https://builds.sr.ht/~mshroyer/tsock/fedora)       | schedule |
| freebsd   | [![status badge](https://builds.sr.ht/~mshroyer/tsock/freebsd.svg)](https://builds.sr.ht/~mshroyer/tsock/freebsd)     | schedule |
| netbsd    | [![status badge](https://builds.sr.ht/~mshroyer/tsock/netbsd.svg)](https://builds.sr.ht/~mshroyer/tsock/netbsd)       | schedule |
| openbsd   | [![status badge](https://builds.sr.ht/~mshroyer/tsock/openbsd.svg)](https://builds.sr.ht/~mshroyer/tsock/openbsd)     | schedule |

You can run the unit tests with:

```
% scripts/test.sh
```

The tests will use your system versions of `tmux` and any shells available for
test.
