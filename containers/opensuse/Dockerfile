FROM opensuse/tumbleweed:latest

RUN zypper install -y awk bash find glibc-locale python3 tmux which zsh

ARG files_cachebust=1
COPY files/ /

RUN useradd --create-home build
RUN echo 'build ALL=(ALL) NOPASSWD: ALL' >>/etc/sudoers
RUN chown -R build:build /socklink
USER build

CMD ["/socklink/scripts/test.sh"]
