FROM archlinux:latest

RUN pacman --noconfirm -Syu
RUN pacman --noconfirm -S bash python tmux which zsh

ARG files_cachebust=1
COPY files/ /

RUN useradd --create-home build
RUN echo 'build ALL=(ALL) NOPASSWD: ALL' >>/etc/sudoers
RUN chown -R build:build /socklink
USER build

CMD ["/socklink/scripts/test.sh"]
