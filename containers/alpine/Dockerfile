FROM alpine:edge

RUN apk add bash musl-locales python3 tmux zsh

ARG files_cachebust=1
COPY files/ /

RUN adduser -S -s /bin/sh build
RUN chown -R build /socklink
USER build

CMD ["/socklink/scripts/test.sh"]
