# socklink.sh: Keeps SSH agent forwarding working when switching tmux clients

[![Lint status](https://github.com/mshroyer/socklink/actions/workflows/lint.yml/badge.svg)](https://github.com/mshroyer/socklink/actions/workflows/lint.yml)
[![AlmaLinux 10 status](https://github.com/mshroyer/socklink/actions/workflows/test-el10.yml/badge.svg)](https://github.com/mshroyer/socklink/actions/workflows/test-el10.yml)
[![Alpine Linux status](https://github.com/mshroyer/socklink/actions/workflows/test-alpine.yml/badge.svg)](https://github.com/mshroyer/socklink/actions/workflows/test-alpine.yml)
[![Arch Linux status](https://github.com/mshroyer/socklink/actions/workflows/test-archlinux.yml/badge.svg)](https://github.com/mshroyer/socklink/actions/workflows/test-archlinux.yml)
[![Debian status](https://github.com/mshroyer/socklink/actions/workflows/test-debian.yml/badge.svg)](https://github.com/mshroyer/socklink/actions/workflows/test-debian.yml)
[![Fedora status](https://github.com/mshroyer/socklink/actions/workflows/test-fedora.yml/badge.svg)](https://github.com/mshroyer/socklink/actions/workflows/test-fedora.yml)
[![FreeBSD status](https://github.com/mshroyer/socklink/actions/workflows/test-freebsd.yml/badge.svg)](https://github.com/mshroyer/socklink/actions/workflows/test-freebsd.yml)
[![macOS status](https://github.com/mshroyer/socklink/actions/workflows/test-macos.yml/badge.svg)](https://github.com/mshroyer/socklink/actions/workflows/test-macos.yml)
[![NetBSD status](https://github.com/mshroyer/socklink/actions/workflows/test-netbsd.yml/badge.svg)](https://github.com/mshroyer/socklink/actions/workflows/test-netbsd.yml)
[![OpenBSD status](https://github.com/mshroyer/socklink/actions/workflows/test-openbsd.yml/badge.svg)](https://github.com/mshroyer/socklink/actions/workflows/test-openbsd.yml)
[![OpenIndiana status](https://github.com/mshroyer/socklink/actions/workflows/test-openindiana.yml/badge.svg)](https://github.com/mshroyer/socklink/actions/workflows/test-openindiana.yml)
[![OpenSUSE status](https://github.com/mshroyer/socklink/actions/workflows/test-opensuse.yml/badge.svg)](https://github.com/mshroyer/socklink/actions/workflows/test-opensuse.yml)
[![Ubuntu status](https://github.com/mshroyer/socklink/actions/workflows/test-ubuntu.yml/badge.svg)](https://github.com/mshroyer/socklink/actions/workflows/test-ubuntu.yml)
[![Ubuntu Devel status](https://github.com/mshroyer/socklink/actions/workflows/test-ubuntu-devel.yml/badge.svg)](https://github.com/mshroyer/socklink/actions/workflows/test-ubuntu-devel.yml)

Ever reconnect to a long-running remote tmux session and find you can no longer `git push` or `scp` because your SSH agent forwarding is broken?  This is especially troublesome when using YubiKeys with proof-of-presence: In that case matters that the agent is forwarded to the client you're at right now, and not to some other connected client where your YubiKey starts blinking, hopelessly waiting for someone to touch it.

This happens because your tmux panes inherit the `SSH_AUTH_SOCK` environment variable corresponding to the SSH client where you started the tmux session.  That will work initially, but when you disconnect that client or connect another one, the variable's value may point to the incorrect authentication socket or none at all.

[socklink.sh](./socklink.sh) is a single-file shell script that does bookkeeping of symlinks and environment variables so that the `SSH_AUTH_SOCK` in your tmux panes always points at your current client.  It does this through some invocations you add to your interactive shell's initialization script (such as `.zshrc` or `.bashrc`) and tmux hooks configured in `.tmux.conf`; there's no daemon to run in the background.  It uses tmux's relatively new `client-active` hook so that even if you have two clients concurrently connected, SSH auth should "just work" when you sit down at one computer or the other.

See [this blog post](https://markshroyer.com/2025/09/socklink/) for a more detailed design description.

## Setup

`socklink.sh` only needs to be present on the system you're SSHing into, not your client system.  The easiest way to get started is to copy the [latest release](https://github.com/mshroyer/socklink/releases) to wherever you want to keep it on your server's filesystem, then run:

```sh
./socklink.sh setup
```

The script will install the necessary hooks to your `.tmux.conf`, `.bashrc`, and `.zshrc`.  If you're using a different interactive shell than bash or zsh, you can instead manually setup the hooks by adding the equivalent of the following to your shell's init file:

```sh
if [ -n "$THIS_IS_AN_INTERACTIVE_SESSION" ]; then
        if [ -z "$TMUX" ]; then
                $PATH_TO/socklink.sh set-tty-link -c shell-init
        else
                export SSH_AUTH_SOCK="$($PATH_TO/socklink.sh show-server-link)"
        fi
fi
```

The tmux hooks can also be added manually instead of by running `setup`, and look like:

```
if-shell -b '"$PATH_TO/socklink.sh" test-tmux-feature client-active-hook' {
	set-hook -ga client-active 'run-shell "\"$PATH_TO/socklink.sh\" -c client-active set-server-link-by-name \"#{hook_client}\""'
}
set-hook -ga client-attached 'run-shell "\"$PATH_TO/socklink.sh\" -c client-attached set-server-link \"#{client_tty}\""'
set-hook -ga session-created 'run-shell "\"$PATH_TO/socklink.sh\" -c session-created set-server-link \"#{client_tty}\""'
set-hook -ga session-created 'run-shell "\"$PATH_TO/socklink.sh\" -c session-created set-tmux-env"'
```

After setup, restart any tmux sessions and any interactive shells.

No additional dependencies should be needed outside of what's present in tested operating systems' base installations, with the exception of very minimalist installations of certain Linux distros like Fedora and OpenSUSE, where standard tools like `awk`, `find`, `ps`, or `which` might be missing.

## Why a shell script?

Implementing this as a shell script [proved to be](https://markshroyer.com/2025/09/socklink/) much more challenging than it would have been as a Python script, so why make a shell script?

I use lots of different Linux distros and BSD systems on a regular basis, and synchronize a [shared set of dotfiles](https://github.com/mshroyer/config) across them.  Some of these systems don't have Python or even Perl, so it's useful to me to have a plain shell script that I can drop on any Unix-like system and expect to work.

## Platform support and tests

Different Unix-like systems use different versions of `/bin/sh` and associated POSIX commands: Alpine Linux's `sh` is `ash`, Debian's is `dash`, Fedora's is `bash`, and the BSDs and Illumos all have their own.  `socklink.sh` has a Python and [pexpect](https://pexpect.readthedocs.io/en/stable/)-based test suite that hooks it up to tmux inside pseudoterminals and verifies its behavior across these different implementations.

It's tested on the following operating systems:

| OS                                                                  |                                                                                                                                                                                         Status |      Runs as       |         Runs on         |
|---------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------:|:------------------:|:-----------------------:|
| [AlmaLinux 10](https://hub.docker.com/_/almalinux)                  |                 [![AlmaLinux 10 status](https://github.com/mshroyer/socklink/actions/workflows/test-el10.yml/badge.svg)](https://github.com/mshroyer/socklink/actions/workflows/test-el10.yml) |     container      |    schedule, release    |
| [Alpine Linux](https://hub.docker.com/_/alpine/)                    |             [![Alpine Linux status](https://github.com/mshroyer/socklink/actions/workflows/test-alpine.yml/badge.svg)](https://github.com/mshroyer/socklink/actions/workflows/test-alpine.yml) |     container      |    schedule, release    |
| [Arch Linux](https://hub.docker.com/_/archlinux/)                   |         [![Arch Linux status](https://github.com/mshroyer/socklink/actions/workflows/test-archlinux.yml/badge.svg)](https://github.com/mshroyer/socklink/actions/workflows/test-archlinux.yml) |     container      |    schedule, release    |
| [Debian Unstable](https://hub.docker.com/_/debian)                  |                   [![Debian status](https://github.com/mshroyer/socklink/actions/workflows/test-debian.yml/badge.svg)](https://github.com/mshroyer/socklink/actions/workflows/test-debian.yml) |     container      |    schedule, release    |
| [Fedora Rawhide](https://hub.docker.com/_/fedora)                   |                   [![Fedora status](https://github.com/mshroyer/socklink/actions/workflows/test-fedora.yml/badge.svg)](https://github.com/mshroyer/socklink/actions/workflows/test-fedora.yml) |     container      |    schedule, release    |
| [FreeBSD 15.1](https://freebsd.org/)                                |                [![FreeBSD status](https://github.com/mshroyer/socklink/actions/workflows/test-freebsd.yml/badge.svg)](https://github.com/mshroyer/socklink/actions/workflows/test-freebsd.yml) |         vm         |    schedule, release    |
| [macOS Latest](https://github.com/actions/runner-images)            |                      [![macOS status](https://github.com/mshroyer/socklink/actions/workflows/test-macos.yml/badge.svg)](https://github.com/mshroyer/socklink/actions/workflows/test-macos.yml) | directly on runner |    schedule, release    |
| [NetBSD 11](https://netbsd.org/)                                    |                   [![NetBSD status](https://github.com/mshroyer/socklink/actions/workflows/test-netbsd.yml/badge.svg)](https://github.com/mshroyer/socklink/actions/workflows/test-netbsd.yml) |         vm         |    schedule, release    |
| [OpenBSD 7.9](https://openbsd.org/)                                 |                [![OpenBSD status](https://github.com/mshroyer/socklink/actions/workflows/test-openbsd.yml/badge.svg)](https://github.com/mshroyer/socklink/actions/workflows/test-openbsd.yml) |         vm         |    schedule, release    |
| [OpenIndiana 2026.04](https://www.openindiana.org/)                 |    [![OpenIndiana status](https://github.com/mshroyer/socklink/actions/workflows/test-openindiana.yml/badge.svg)](https://github.com/mshroyer/socklink/actions/workflows/test-openindiana.yml) |         vm         |    schedule, release    |
| [OpenSUSE Tumbleweed](https://hub.docker.com/r/opensuse/tumbleweed) |             [![OpenSUSE status](https://github.com/mshroyer/socklink/actions/workflows/test-opensuse.yml/badge.svg)](https://github.com/mshroyer/socklink/actions/workflows/test-opensuse.yml) |     container      |    schedule, release    |
| [Ubuntu 26.04](https://github.com/actions/runner-images)            |                   [![Ubuntu status](https://github.com/mshroyer/socklink/actions/workflows/test-ubuntu.yml/badge.svg)](https://github.com/mshroyer/socklink/actions/workflows/test-ubuntu.yml) | directly on runner | push, schedule, release |
| [Ubuntu Devel](https://hub.docker.com/_/ubuntu)                     | [![Ubuntu Devel status](https://github.com/mshroyer/socklink/actions/workflows/test-ubuntu-devel.yml/badge.svg)](https://github.com/mshroyer/socklink/actions/workflows/test-ubuntu-devel.yml) |     container      |    schedule, release    |

You can run the tests on your own system with:

```sh
./scripts/test.sh
```

The tests will use your system versions of `tmux` and `/bin/sh`, as well as zsh and/or bash as a test interactive shell for `setup`.  See [CONTRIBUTING.md](./CONTRIBUTING.md) for information about how to run the tests on other systems too.

The reguarly-scheduled Debian Unstable, Fedora Rawhide, and OpenSUSE Tumbleweed tests are meant to serve as early warnings of breakage due to new software versions; the AlmaLinux and Ubuntu LTS tests ensure things keep working on older Linux distros.  Testing ubuntu-devel aims to catch compatibility issues with [uutils](https://github.com/uutils).  It would be nice to have something like Rawhide tests for the BSDs, but that isn't feasible since these VMs must be recreated by hand, which I plan to do approximately quarterly.

## Limitations

### Background control clients

Because the hooks installed by the `setup` command rely on tmux's accounting of which client is currently "active", it's possible that if you have a control client running in the background along with your main, interactive tmux client, the control client might "steal" active status from your interactive client and redirect your `SSH_AUTH_SOCK` away from it.

I haven't tested this scenario because it's not a setup that I personally use. Let me know if this is a problem for you in practice.

### Old tmux versions

tmux versions older than tmux 3.4 or OpenBSD 7.1 lack the `client-active` hook installed by `setup`.  Without this hook, attaching a new client will still switch `SSH_AUTH_SOCK` over to that client, but hopping between still-connected clients won't work automatically.

If needed, you can work around this by running

```sh
socklink.sh set-server-link
```

from your shell, either manually as needed or as a bash preexec or zsh periodic function.

## Troubleshooting

If you're in a tmux session managed by this script and `SSH_AUTH_SOCK` still isn't working as expected for you, here are some things you can try:

1. Run `echo $SSH_AUTH_SOCK` to ensure the environment variable is set.  It should have a value like `/tmp/socklink-$(uid)/servers/$PID`.  If not, it's likely that your shell init is incorrect.

2. Run `readlink $SSH_AUTH_SOCK` and look at the name of the link it points to.  This link should exist, and the tty indicated by its filename should match what you see when you detach tmux and run `tty`.  If not, it's likely the `socklink.sh set-server-link` tmux hook isn't being invoked as expected.

Logging can be enabled by setting the `SOCKLINK_LOG` environment variable to a log file's path, or by adding

```sh
SOCKLINK_LOG="/some/path/to/socklink.log"
```

to `~/.socklink.conf`.  Heads up that there's no log rotation, so this file will (slowly) grow unbounded.

## License

[MIT License](LICENSE.txt)
