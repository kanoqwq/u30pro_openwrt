FROM scratch
ADD openwrt-25.12.5-armsr-armv8-rootfs.tar.gz /
RUN ["/usr/bin/apk", "add", "--no-cache", "--scripts=no", "--commit-hooks=no", "ucode", "ucode-mod-fs", "ucode-mod-uci", "ucode-mod-ubus", "ucode-mod-uloop", "ucode-mod-socket"]
CMD ["/bin/sh"]
