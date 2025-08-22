# tsock.sh

A zero-dependency, cross-platform `SSH_AUTH_SOCK` manager for tmux.

It's just a shell script!  The Python is all test automation.

## Tests

Different Linux and BSD distributions can use different versions of `/bin/sh`
and associated POSIX commands--Alpine Linux's `sh` is `ash`, Debian's is
`dash`, Fedora's is `bash`, and so on.  Automating cross-platform testing has
caught bugs that would have otherwise shipped with this script.

| OS                                                                                | Status                                                                                                                                                                 | Runs on        |
|-----------------------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------:|:--------------:|
| [Alpine Linux Edge](https://man.sr.ht/builds.sr.ht/compatibility.md#alpine-linux) | [![Alpine Linux status](https://builds.sr.ht/~mshroyer/tsock/alpine.svg)](https://builds.sr.ht/~mshroyer/tsock/alpine)                                                 | schedule       |
| [Arch Linux](https://man.sr.ht/builds.sr.ht/compatibility.md#arch-linux)          | [![Arch Linux status](https://builds.sr.ht/~mshroyer/tsock/archlinux.svg)](https://builds.sr.ht/~mshroyer/tsock/archlinux)                                             | schedule       |
| [Debian Testing](https://man.sr.ht/builds.sr.ht/compatibility.md#debian)          | [![Debian status](https://builds.sr.ht/~mshroyer/tsock/debian.svg)](https://builds.sr.ht/~mshroyer/tsock/debian)                                                       | schedule       |
| [Fedora Rawhide](https://man.sr.ht/builds.sr.ht/compatibility.md#fedora-linux)    | [![Fedora status](https://builds.sr.ht/~mshroyer/tsock/fedora.svg)](https://builds.sr.ht/~mshroyer/tsock/fedora)                                                       | schedule       |
| [FreeBSD Latest](https://man.sr.ht/builds.sr.ht/compatibility.md#freebsd)         | [![FreeBSD status](https://builds.sr.ht/~mshroyer/tsock/freebsd.svg)](https://builds.sr.ht/~mshroyer/tsock/freebsd)                                                    | schedule       |
| [macOS Latest](https://github.com/actions/runner-images)                          | [![macOS status](https://github.com/mshroyer/tsock/actions/workflows/test-macos.yml/badge.svg)](https://github.com/mshroyer/tsock/actions/workflows/test-macos.yml)    | push, schedule |
| [NetBSD Latest](https://man.sr.ht/builds.sr.ht/compatibility.md#netbsd)           | [![NetBSD status](https://builds.sr.ht/~mshroyer/tsock/netbsd.svg)](https://builds.sr.ht/~mshroyer/tsock/netbsd)                                                       | schedule       |
| [OpenBSD Latest](https://man.sr.ht/builds.sr.ht/compatibility.md#openbsd)         | [![OpenBSD status](https://builds.sr.ht/~mshroyer/tsock/openbsd.svg)](https://builds.sr.ht/~mshroyer/tsock/openbsd)                                                    | schedule       |
| [Ubuntu Latest](https://github.com/actions/runner-images)                         | [![Ubuntu status](https://github.com/mshroyer/tsock/actions/workflows/test-ubuntu.yml/badge.svg)](https://github.com/mshroyer/tsock/actions/workflows/test-ubuntu.yml) | push, schedule |

You can run the unit tests with:

```
% scripts/test.sh
```

The tests will use your system versions of `tmux` and any shells available for
test.
