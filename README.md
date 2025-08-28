# socklink.sh

A zero-dependency, cross-platform `SSH_AUTH_SOCK` manager for tmux.

It's just a shell script!  The Python is all test automation.

## Tests

Different Linux and BSD distributions can use different versions of `/bin/sh`
and associated POSIX commands--Alpine Linux's `sh` is `ash`, Debian's is
`dash`, Fedora's is `bash`, and so on.  Automating cross-platform testing has
caught bugs that would have otherwise shipped with this script.

| OS                                                                             |                                                                                                                                                                       Status | Runs on        |
|--------------------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------:|:--------------:|
| [Alpine Linux](https://man.sr.ht/builds.sr.ht/compatibility.md#alpine-linux)   |                                                 [![Alpine Linux status](https://builds.sr.ht/~mshroyer/socklink/alpine.svg)](https://builds.sr.ht/~mshroyer/socklink/alpine) | schedule       |
| [Arch Linux](https://man.sr.ht/builds.sr.ht/compatibility.md#arch-linux)       |                                             [![Arch Linux status](https://builds.sr.ht/~mshroyer/socklink/archlinux.svg)](https://builds.sr.ht/~mshroyer/socklink/archlinux) | schedule       |
| [Debian Testing](https://man.sr.ht/builds.sr.ht/compatibility.md#debian)       |                                                       [![Debian status](https://builds.sr.ht/~mshroyer/socklink/debian.svg)](https://builds.sr.ht/~mshroyer/socklink/debian) | schedule       |
| [Fedora Rawhide](https://man.sr.ht/builds.sr.ht/compatibility.md#fedora-linux) |                                                       [![Fedora status](https://builds.sr.ht/~mshroyer/socklink/fedora.svg)](https://builds.sr.ht/~mshroyer/socklink/fedora) | schedule       |
| [FreeBSD Latest](https://man.sr.ht/builds.sr.ht/compatibility.md#freebsd)      |                                                    [![FreeBSD status](https://builds.sr.ht/~mshroyer/socklink/freebsd.svg)](https://builds.sr.ht/~mshroyer/socklink/freebsd) | schedule       |
| [macOS Latest](https://github.com/actions/runner-images)                       |    [![macOS status](https://github.com/mshroyer/socklink/actions/workflows/test-macos.yml/badge.svg)](https://github.com/mshroyer/socklink/actions/workflows/test-macos.yml) | push, schedule |
| [NetBSD Latest](https://man.sr.ht/builds.sr.ht/compatibility.md#netbsd)        |                                                       [![NetBSD status](https://builds.sr.ht/~mshroyer/socklink/netbsd.svg)](https://builds.sr.ht/~mshroyer/socklink/netbsd) | schedule       |
| [OpenBSD Latest](https://man.sr.ht/builds.sr.ht/compatibility.md#openbsd)      |                                                    [![OpenBSD status](https://builds.sr.ht/~mshroyer/socklink/openbsd.svg)](https://builds.sr.ht/~mshroyer/socklink/openbsd) | schedule       |
| [Ubuntu Latest](https://github.com/actions/runner-images)                      | [![Ubuntu status](https://github.com/mshroyer/socklink/actions/workflows/test-ubuntu.yml/badge.svg)](https://github.com/mshroyer/socklink/actions/workflows/test-ubuntu.yml) | push, schedule |

You can run the unit tests with:

```
% scripts/test.sh
```

The tests will use your system versions of `tmux` and any shells available for
test.

## Limitations

### Background control clients

Because the hooks installed by the `setup` command rely on tmux's accounting
of which client is currently "active", it's possible that if you have a
control client running in the background along with your main, interactive
tmux client, the control client might "steal" active status from your
interactive client and redirect your `SSH_AUTH_SOCK` away from it.

I haven't tested this scenario because it's not a setup that I personally use.
Let me know if this is a problem for anyone in practice.

### Old tmux versions

tmux versions older than tmux 3.4 or OpenBSD 7.1 lack the `client-active` hook
installed by `setup`.  Without this hook, attaching a new client will still
switch `SSH_AUTH_SOCK` over to that client, but hopping between
still-connected clients won't work automatically.

If needed, you can work around this by running

```
socklink.sh set-server-link
```

from your shell, either manually as needed or as a bash preexec, zsh periodic
function, or so on.
