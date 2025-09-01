# tsock.sh Changelog

## v0.3.0-dev

- Support zsh in the `setup` subcommand.
- Fix and regression test silently-broken server link handling on Alpine Linux
  due to its incompatible ps implementation.
- Generally improved test coverage and more reliable integration tests.

## v0.2.0

- Renames the project to "socklink" to avoid confusion with the existing
  tsocks proxying library.
- Adds installation script for .tmux.conf and .bashrc hooks.

## v0.1.0

- Some improvements over the original version from my "config" repo to
  simplify querying the active client TTY and ensure non-default socket paths
  will be honored.
- Added automated tests on GitHub and SourceHut.
- Copied release automation from CoursePointer.
