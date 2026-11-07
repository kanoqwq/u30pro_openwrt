# Built-in nft capability packages

The project's kernel configurations build `NFT_SOCKET` and `NFT_TPROXY` in. Installing OpenWrt's
feed modules would supply binaries for another kernel. These two small APKs declare the already available
capabilities under the usual `kmod-nft-socket` and `kmod-nft-tproxy` names instead (issue #470).

Each package contains only a capability marker and the normal OpenWrt package file list. The package manager
owns both files and can remove them normally. There are no `.ko` files, autoload entries, firewall rules or
application changes. The date-based version identifies this firmware metadata, not a kernel ABI.

`tools/u30pro-package.py finish` installs these packages before recording the image package baseline.
It uses the selected UMS9632 object's `.config`, after `verified_kernel()` ties that config to the
built Image and source receipt. Both U30 Pro and F50 Pro use this same kernel. The inherited MU300
kernel configs and `openwrt/build-rootfs.sh` are not the native product build path.

Every required expression, IPv4/IPv6 and socket/TPROXY family helper must be built in. A missing or
module-only feature stops before package generation. The builder uses Alpine 3.23 apk-tools via Docker,
or an explicitly supplied `MU300_APK_MKPKG` host binary for offline builds. The existing ARM64 OpenWrt
container installs the resulting APKs with networking, scripts and commit hooks disabled. No additional
kernel or rootfs build tree is created. Root ownership is normalized and host xattrs are excluded.

Live installation additionally requires built-in symbols in `/proc/config.gz` and successful
`nft --check` probes for socket or TCP/UDP TPROXY. These probes never commit tables or rules.

Locally built unsigned packages can be installed offline with `apk add --no-network --allow-untrusted FILE...`.
Do not use `--no-scripts` for a live install. Remove them with `apk del kmod-nft-socket kmod-nft-tproxy` if needed.
These declarations apply to the project's kernels; a replacement kernel without these features needs matching
real modules instead, and the declarations must be removed.
