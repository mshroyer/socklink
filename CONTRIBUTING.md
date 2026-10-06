# Contribution and development guide

## Submitting a PR

When submitting a PR, please ensure lints and most tests pass at least when run locally: `scripts/lint.sh` if you have emacs and shellcheck installed (or alternately, use `scripts/lint.sh -c` to run lints in a docker or podman container), and `scripts/test.sh` on your local machine.

If you'd like to run a fuller set of tests against your PR before submitting, see below.  I'm happy to send you my VM tester images if you'd like them, but also don't sweat submitting a PR that's only tested locally.

## Tests

Because of how subtly differently Unix shell scripts can behave from one system to the next, this project relies heavily on a Python-based test suite that uses [pexpect](https://pexpect.readthedocs.io/en/stable/) to hook socklink.sh up to tmux in a pseudoterminal and run it through its paces.

The test cases are parameterized across the set of supported shells and a handful of locale settings.

Invoke `scripts/test.sh` without arguments to run tests directly on your host.  The script will handle creating a `.venv` under the project directory and installing Python dependencies.  A single positional argument can be provided to tell pytest to run a specific test:

```sh
scripts/test.sh tests/test_integration.py::test_gc_tty_links
```

## Testing in Linux containers

If you have podman or docker in your path, run cross-Linux distro tests by passing the `-c` flag to `test.sh`, giving one of the available container definitions:

```sh
scripts/test.sh -c debian
```

These correspond to the Dockerfiles in the containers directory, and can be listed with `test.sh -l`.

Containers do not persist between test runs, but images are cached.  These can be freed with `podman image prune`.

## Testing in VMs

BSD and Illumos tests are run in x86-64 KVM virtual machines kept as .qcow2 disk images in the vms project directory, if present.  Running these require an available `qemu-kvm` or `qemu-system-x86_64` binary, plus `xorriso` to bundle the source tree for the VM.

The VM disk images are *not* included in the source repo, and must be prepared as described below.  List available VMs with `test.sh -l`, and run tests in them with the `-m` flag:

```sh
scripts/test.sh -m openbsd79
```

Test runner VMs must have:

- Serial console enabled at 115200 baud
- An enabled root account with password `socklink-test`
- A regular user named `test`
- Python, zsh, and bash
- The zh_CN locale installed and present in `locale -a`
- Automatic network configuration via DHCP

If adding a new OS, [vm_test.py](./scripts/vm_test.py) must be updated to recognize its uname and understand how to mount the virtual CD-ROM.  Instructions for preparing VMs for supported OSes follow.

### OpenBSD VM

[Download](https://www.openbsd.org/faq/faq4.html#Download) the latest amd64 `install*.iso`.  Prepare a disk image and boot the installer:

```sh
qemu-img create -f qcow2 vms/openbsd79.qcow2 10G
qemu-kvm \
        -machine q35,accel=kvm \
        -cpu host \
        -m 2G \
        -netdev user,id=net0 \
        -device virtio-net-pci,netdev=net0 \
        -cdrom install79.iso \
        -drive file=vms/openbsd79.qcow2,if=virtio \
        -serial stdio
```

In the installer:

1. Choose "Install"
2. Configure the network interface vio0 as "autoconf"
3. Set root password "socklink-test"
4. Say no to starting sshd and using the X Window System
5. Say yes to changing the default console to com0
6. Set com0's speed to 115200 baud
7. Create a regular user "test" with an arbitrary password
8. Install to sd0, no encryption, whole drive, auto layout
9. Install all sets from cd0

Reboot.  You should now be able to interact with OpenBSD in the terminal where `qemu-kvm` is running.  There:

1. Log in as root
2. `pkg_add python zsh bash`
3. `echo boot >>/etc/boot.conf` to disable boot delay
