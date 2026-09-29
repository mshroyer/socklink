FROM debian:latest

RUN apt update
RUN apt install -y locales procps python3 python3-venv tmux zsh

RUN sed -i -e 's/^# *he_IL/he_IL/' -e 's/^# *zh_CN/zh_CN/' /etc/locale.gen
RUN locale-gen

ARG files_cachebust=1
COPY files/ /

RUN useradd --create-home build
RUN echo 'build ALL=(ALL) NOPASSWD: ALL' >>/etc/sudoers
RUN chown -R build:build /socklink
USER build

CMD ["/socklink/scripts/test.sh"]
