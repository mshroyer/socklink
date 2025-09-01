import os
from textwrap import dedent


from tests.testlib import (
    Sandbox,
    SocklinkStub,
)


def test_get_device_filename(stub: SocklinkStub):
    assert stub.run("get-device-filename", "/dev/pts/12") == "dev+pts+12"


def test_get_filename_device(stub: SocklinkStub):
    assert stub.run("get-filename-device", "dev+pts+12") == "/dev/pts/12"


def test_stat_mode(sandbox: Sandbox, stub: SocklinkStub):
    path = sandbox.root / "foo.txt"
    path.touch()
    path.chmod(0o644)

    assert stub.run("stat-mode", path) == "644"


def test_get_pid_uid(stub: SocklinkStub):
    assert stub.run("get-pid-uid", os.getpid()) == str(os.getuid())

    # Asking for the UID of a non-existent process should succeed and return
    # the empty string
    assert stub.run("get-pid-uid", 0) == ""


def test_client_active_hook(stub: SocklinkStub):
    assert not stub.run_test("has-client-active-hook", "tmux 3.2")
    assert stub.run_test("has-client-active-hook", "tmux 3.3")

    # Debian 12
    assert stub.run_test("has-client-active-hook", "tmux 3.3a")

    # AlmaLinux 10
    assert stub.run_test("has-client-active-hook", "tmux next-3.4")

    # OpenBSD
    assert not stub.run_test("has-client-active-hook", "tmux openbsd-7.0")
    assert stub.run_test("has-client-active-hook", "tmux openbsd-7.7")


def test_set_section_no_file(sandbox: Sandbox, stub: SocklinkStub):
    rc_file = sandbox.root / "test_rc_file"
    stub.run(
        "set-socklink-section",
        rc_file,
        stdin=dedent("""\
    foo
    bar
    """),
    )

    assert rc_file.read_text() == dedent("""\
    ### SOCKLINK INSTALLATION BEGIN
    foo
    bar
    ### SOCKLINK INSTALLATION END
    """)


def test_set_section_empty_file(sandbox: Sandbox, stub: SocklinkStub):
    rc_file = sandbox.root / "test_rc_file"
    rc_file.touch()
    stub.run(
        "set-socklink-section",
        rc_file,
        stdin=dedent("""\
    foo
    bar
    """),
    )

    assert rc_file.read_text() == dedent("""\
    ### SOCKLINK INSTALLATION BEGIN
    foo
    bar
    ### SOCKLINK INSTALLATION END
    """)


def test_set_section_single_char_file(sandbox: Sandbox, stub: SocklinkStub):
    rc_file = sandbox.root / "test_rc_file"
    rc_file.write_text("a")
    stub.run(
        "set-socklink-section",
        rc_file,
        stdin=dedent("""\
    foo
    bar
    """),
    )

    assert rc_file.read_text() == dedent("""\
    a

    ### SOCKLINK INSTALLATION BEGIN
    foo
    bar
    ### SOCKLINK INSTALLATION END
    """)


def test_set_section_single_char_file_with_lf(sandbox: Sandbox, stub: SocklinkStub):
    rc_file = sandbox.root / "test_rc_file"
    rc_file.write_text("a\n")
    stub.run(
        "set-socklink-section",
        rc_file,
        stdin=dedent("""\
    foo
    bar
    """),
    )

    assert rc_file.read_text() == dedent("""\
    a

    ### SOCKLINK INSTALLATION BEGIN
    foo
    bar
    ### SOCKLINK INSTALLATION END
    """)


def test_set_section_empty_section(sandbox: Sandbox, stub: SocklinkStub):
    rc_file = sandbox.root / "test_rc_file"
    rc_file.write_text(
        dedent("""\
    ### SOCKLINK INSTALLATION BEGIN
    ### SOCKLINK INSTALLATION END
    """)
    )
    stub.run(
        "set-socklink-section",
        rc_file,
        stdin=dedent("""\
    foo
    bar
    """),
    )

    assert rc_file.read_text() == dedent("""\
    ### SOCKLINK INSTALLATION BEGIN
    foo
    bar
    ### SOCKLINK INSTALLATION END
    """)


def test_set_section_not_preeixsting(sandbox: Sandbox, stub: SocklinkStub):
    rc_file = sandbox.root / "test_rc_file"
    rc_file.write_text(
        dedent("""\
        This is a test
        The remainder of this file should be unmodified.
        """)
    )
    stub.run(
        "set-socklink-section",
        rc_file,
        stdin=dedent("""\
        foo
        bar
        """),
    )

    assert rc_file.read_text() == dedent("""\
        This is a test
        The remainder of this file should be unmodified.

        ### SOCKLINK INSTALLATION BEGIN
        foo
        bar
        ### SOCKLINK INSTALLATION END
        """)


def test_set_section_not_preeixsting_no_lf(sandbox: Sandbox, stub: SocklinkStub):
    rc_file = sandbox.root / "test_rc_file"
    rc_file.write_text(
        dedent("""\
        This is a test
        The remainder of this file should be unmodified.""")
    )
    stub.run(
        "set-socklink-section",
        rc_file,
        stdin=dedent("""\
        foo
        bar
        """),
    )

    assert rc_file.read_text() == dedent("""\
        This is a test
        The remainder of this file should be unmodified.

        ### SOCKLINK INSTALLATION BEGIN
        foo
        bar
        ### SOCKLINK INSTALLATION END
        """)


def test_set_section_preserves_rest(sandbox: Sandbox, stub: SocklinkStub):
    rc_file = sandbox.root / "test_rc_file"
    rc_file.write_text(
        dedent("""\
        This is a test

        ### SOCKLINK INSTALLATION BEGIN
        ### SOCKLINK INSTALLATION END
        The remainder of this file should be unmodified.
        """)
    )
    stub.run(
        "set-socklink-section",
        rc_file,
        stdin=dedent("""\
        foo
        bar
        """),
    )

    assert rc_file.read_text() == dedent("""\
        This is a test

        ### SOCKLINK INSTALLATION BEGIN
        foo
        bar
        ### SOCKLINK INSTALLATION END
        The remainder of this file should be unmodified.
        """)


def test_has_manual_config_head(sandbox: Sandbox, stub: SocklinkStub):
    rc_file = sandbox.root / "test_rc_file"
    rc_file.write_text(
        dedent("""\
        socklink.sh set-tty-link
        ### SOCKLINK INSTALLATION BEGIN
        echo foo
        ### SOCKLINK INSTALLATION END
        echo bar
        """)
    )
    assert stub.run_test("has-manual-config", rc_file)


def test_has_manual_config_installation(sandbox: Sandbox, stub: SocklinkStub):
    rc_file = sandbox.root / "test_rc_file"
    rc_file.write_text(
        dedent("""\
        echo foo
        ### SOCKLINK INSTALLATION BEGIN
        socklink.sh set-tty-link
        ### SOCKLINK INSTALLATION END
        echo bar
        """)
    )
    assert not stub.run_test("has-manual-config", rc_file)


def test_has_manual_config_tail(sandbox: Sandbox, stub: SocklinkStub):
    rc_file = sandbox.root / "test_rc_file"
    rc_file.write_text(
        dedent("""\
        echo foo
        ### SOCKLINK INSTALLATION BEGIN
        echo bar
        ### SOCKLINK INSTALLATION END
        socklink.sh show-server-link
        """)
    )
    assert stub.run_test("has-manual-config", rc_file)
