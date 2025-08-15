from tests.testlib import Sandbox, SocketManager, Terminal


class TestSshAuthSock:
    def test_unset(self, sandbox: Sandbox):
        terminal = Terminal(sandbox, login_sock=False)
        assert terminal.get_ssh_auth_sock() is None

    def test_tmux_session(
        self, terminal: Terminal, socket_manager: SocketManager, sandbox: Sandbox
    ):
        socket = socket_manager.reserve_unique()
        sandbox.write_debug(f"socket = {socket}")
        terminal.run(f"tmux -S {socket}")
        assert terminal.get_ssh_auth_sock() is not None
