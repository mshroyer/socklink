# tsock.sh

A zero-dependency, cross-platform `SSH_AUTH_SOCK` wrangler for tmux.

(It's just a shell script, the Python is all tests.)

## Tests

| Platform                                                                          | Status                                                                                                                | Runs on  |
|-----------------------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------|----------|
| [Alpine Linux Edge](https://man.sr.ht/builds.sr.ht/compatibility.md#alpine-linux) | [![status badge](https://builds.sr.ht/~mshroyer/tsock/alpine.svg)](https://builds.sr.ht/~mshroyer/tsock/alpine)       | schedule |
| [Arch Linux](https://man.sr.ht/builds.sr.ht/compatibility.md#arch-linux)          | [![status badge](https://builds.sr.ht/~mshroyer/tsock/archlinux.svg)](https://builds.sr.ht/~mshroyer/tsock/archlinux) | schedule |
| [Debian Testing](https://man.sr.ht/builds.sr.ht/compatibility.md#debian)          | [![status badge](https://builds.sr.ht/~mshroyer/tsock/debian.svg)](https://builds.sr.ht/~mshroyer/tsock/debian)       | schedule |
| [Fedora Rawhide](https://man.sr.ht/builds.sr.ht/compatibility.md#fedora-linux)    | [![status badge](https://builds.sr.ht/~mshroyer/tsock/fedora.svg)](https://builds.sr.ht/~mshroyer/tsock/fedora)       | schedule |
| [FreeBSD Latest](https://man.sr.ht/builds.sr.ht/compatibility.md#freebsd)         | [![status badge](https://builds.sr.ht/~mshroyer/tsock/freebsd.svg)](https://builds.sr.ht/~mshroyer/tsock/freebsd)     | schedule |
| [NetBSD Latest](https://man.sr.ht/builds.sr.ht/compatibility.md#netbsd)           | [![status badge](https://builds.sr.ht/~mshroyer/tsock/netbsd.svg)](https://builds.sr.ht/~mshroyer/tsock/netbsd)       | schedule |
| [OpenBSD Latest](https://man.sr.ht/builds.sr.ht/compatibility.md#openbsd)         | [![status badge](https://builds.sr.ht/~mshroyer/tsock/openbsd.svg)](https://builds.sr.ht/~mshroyer/tsock/openbsd)     | schedule |

You can run the unit tests with:

```
% scripts/test.sh
```

The tests will use your system versions of `tmux` and any shells available for
test.
