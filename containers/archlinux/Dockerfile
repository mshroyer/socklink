FROM archlinux:latest

RUN pacman --noconfirm -Syu
RUN pacman --noconfirm -S bash python tmux which zsh

ARG files_cachebust=1
COPY files/ /

CMD ["/socklink/scripts/test.sh"]
