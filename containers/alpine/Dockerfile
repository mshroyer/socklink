FROM alpine:edge

RUN apk add bash musl-locales python3 tmux zsh

ARG files_cachebust=1
COPY files/ /

CMD ["/socklink/scripts/test.sh"]
