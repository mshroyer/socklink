# socklink.sh

A zero-dependency, cross-platform `SSH_AUTH_SOCK` manager for tmux.

(It's just a shell script!  The Python is all test automation.)

See [this blog post](https://markshroyer.com/2025/09/socklink/) for a more
detailed overview.

## Installation

Copy the [latest release](https://github.com/mshroyer/socklink/releases) to
your filesystem, then run

```
socklink.sh setup
```

The script will install the necessary hooks to your `.tmux.conf`, `.bashrc`,
and `.zshrc` files.  If you're using a different interactive shell than bash
or zsh, you can instead manually setup the hooks by adding the equivalent of
the following to your shell's init file:

```
if [ -n "$THIS_IS_AN_INTERACTIVE_SESSION" ]; then
        if [ -z "$TMUX" ]; then
                socklink.sh set-tty-link -c shell-init
        else
                export SSH_AUTH_SOCK="$(socklink.sh show-server-link)"
        fi
fi
```

After setup, restart any tmux sessions and any interactive shells.

No additional dependencies should be needed outside of what's present in
tested operating systems' base installations, with the exception of Fedora
where `awk` may not necessarily be installed by default.

## Platform support and tests

Different Linux and BSD distributions can use different versions of `/bin/sh`
and associated POSIX commands: Alpine Linux's `sh` is `ash`, Debian's is
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

I've also observed that tests succeed on OpenIndiana Hipster, but I don't have
automated testing there.

You can run the tests locally with:

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

## Troubleshooting

If you're in a tmux session managed by this script and `SSH_AUTH_SOCK` still
isn't working as expected for you, here are some things you can try:

1. Run `echo $SSH_AUTH_SOCK` to ensure the environment variable is set.  It should
   have a value like `/tmp/socklink-$(uid)/servers/$PID`.  If not, it's likely
   that your shell init is incorrect.

2. Run `readlink $SSH_AUTH_SOCK` and look at the name of the link it points
   to.  This link should exist, and the tty indicated by its filename should
   match what you see when you detach tmux and run `tty`.  If not, it's likely
   the `socklink.sh set-server-link` tmux hook isn't being invoked as
   expected.

Logging can be enabled by setting the `SOCKLINK_LOG` environment variable to a
log file's path, or by adding

```
SOCKLINK_LOG="/some/path/to/socklink.log"
```

to `~/.socklink.conf`.  Heads up that there's no log rotation, so this file
will (slowly) grow unbounded.

## License

[MIT License](LICENSE.txt)
