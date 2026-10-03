FROM ubuntu:26.04

RUN apt update
RUN apt install -y locales procps python3 python3-venv tmux zsh

RUN sed -i -e 's/^# *he_IL/he_IL/' /etc/locale.gen
RUN locale-gen

# Also install emacs and shellcheck so that we can dual-purpose this container
# to run lints with the same software versions that will be used on GitHub
# Actions.
RUN apt install -y emacs-nox shellcheck

ARG files_cachebust=1
COPY files/ /

RUN useradd --create-home build
RUN echo 'build ALL=(ALL) NOPASSWD: ALL' >>/etc/sudoers
RUN chown -R build:build /socklink
USER build

CMD ["/socklink/scripts/test.sh"]
