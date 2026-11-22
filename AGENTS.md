# Independent U30 Pro port

- This repository also carries the F50 Pro / MU3356 product profile. Read
  docs/F50PRO-PORTING.zh-CN.md and devices/f50pro/profile.json. U30 Pro and
  F50 Pro share the UMS9632 platform transport/kernel and native boot-container
  adapter, not their SIM topology, battery, screen or product identity.
  `/etc/mu300/platform=u30pro` names that existing native platform ABI;
  `/etc/mu300/model` selects the product. Never map a MU3356 board ID through
  MU5358's table. Shared caches are intentional only for identical platform
  source/config receipts; product selection stays explicit and sequential.

- This repository is https://github.com/kanoqwq/u30pro_openwrt, maintained on
  main at D:/Git/u30pro_openwrt. Its starting branch was
  u30pro-bringup, based on kanoqwq/mu300-linux minikano-openwrt-feats at
  29061dc8, never the MU300 main branch.
- Read docs/U30PRO-PORT.zh-CN.md. U30 Pro uses UMS9632, Linux 6.12.94,
  AIC8800 SDIO and its own native panel. Never assemble MU300 hardware images
  as a U30 Pro release or run the inherited MU300 platform services blindly.
- devices/u30pro/native source provenance is in devices/u30pro/reference.json;
  local adaptations must carry their original and current hashes and rationale.
- Existing U30Pro, MU300 and E5 repositories and the user's clean reference
  checkout are read-only for this task. Do not change or push them.
- Device access is read-only until the user authorizes the particular write,
  reboot or hardware trial. Do not change IMEI/NV. No fastboot or SPD.
- Android/Linux slots and storage geometry must be verified per device.
  Never default Android to A, copy reference LBAs, use reserve2 config storage,
  or inherit the upstream whole-device/A-B installer.
- MU300/E5's maintained modem framework is authoritative: retain its AT
  ownership, SPACTCARD selection, transaction ordering, boot replay and event
  recovery. Hardware adapters may map native ports and load CP firmware; they
  must not remove protocol steps based solely on physical-channel grouping.
- On U30 Pro one MU300 bridge owns general/data ports nr2/nr0 for bank 0 and
  nr5/nr3 for bank 1. Physical bank identity alone does not select the firmware
  SIM context: preserve SPACTCARD. Never start the reference native atd/celld.
  CP loading, NV notification, display and hardware drivers come from U30 Pro;
  installation/update/storage remain MU300 mu300root, not reserve2/overlay.


# Hardware and modem fixes

- Implement new firmware-side control and background features in ucode. Python
  remains available for host builds, offline diagnostics and tests, rather than
  being the default runtime implementation. Prefer existing ubus, modem and
  device events plus deadline timers; do not introduce independent polling when
  the required event or accounting sample already exists. Preserve native
  hardware drivers and existing AT ownership/ordering during migrations.
- For runtime migrations, complete at least six documented regression rounds
  before reporting readiness. Compare against the original implementation and
  cover real RPC/event dispatch, concurrency/fault recovery, upgrade/rollback
  with preserved user data, and sustained execution. Fix differences and rerun
  the final matrix; keep offline results distinct from hardware acceptance.

- NR0 is the sole ingress for automatic modem URC events. Do not select an
  event channel by SIM number or wait on NR3 for SIM2 notifications. The
  ingress channel does not identify the event's SIM; confirm the target using
  the existing explicit SIM-selection/query mechanism. This rule concerns
  unsolicited reception only: preserve each control/data operation's existing
  AT owner, command channel, queue and ordering. Never move all AT/control
  traffic onto NR0 or add a competing reader to its existing owner.
- Before adapting UFS hardware, read `docs/UFS-PORTING.zh-CN.md`. It records
  the U30 Air investigation, 512/4K geometry contract, trial boot recovery,
  and the separate E5/Changxing 60 follow-up. Do not use fastboot.
- Use each model's stock Android firmware behavior as the reference for power,
  charging, battery accounting, radio initialization and reconnection.
- Prefer the actual device's driver/RIL binary and device tree over a merely
  similar vendor source tree. Record firmware versions and the evidence used.
- Separate confirmed defects, hypotheses and untested hardware behavior in
  reports. AOSP explains the framework design; its default timers are not proof
  of the model's carrier or vendor configuration.
- Do not hide a symptom with arbitrary percentage caps, forced recalibration,
  radio resets, disabled sleep or reduced functionality. Preserve existing AT
  ownership, command ordering, boot replay and explicit user choices.
- Apply shared fixes to shared build/update paths. Keep charger-chip and board
  differences in the model profiles, and do not call an offline test a successful
  hardware validation.

# Backport architecture

- Fully replace a migrated operation or keep its original implementation until
  the rewrite is complete. Do not add availability/version probes that silently
  select an older backend, RPC or algorithm after the new one fails.
- Keep platform/model choices explicit. Validate required dependencies and
  report failures directly; retain safety checks and recovery within the chosen
  implementation.

# Rootfs and kernel package architecture

- These ports intentionally combine an OpenWrt armsr base rootfs/package ecosystem
  with a separately built, model-specific kernel and matching modules. The APK
  database's base-distribution kernel identity is not the running kernel identity;
  a difference from `uname -r`, a firmware version or an ABI hash alone is not a bug.
- Preserve the base rootfs's kernel/kmod package metadata and dependency strategy.
  Do not rewrite them into custom native-kernel identities, generate capability
  packages or add native-kernel world pins merely to make the records agree.
  Diagnose actual repository/package conflicts before changing package policy.
- Validate the delivered Image, modules, source/config receipts and model pairing
  through the existing build paths. Retaining armsr metadata does not establish
  compatibility of third-party `.ko` files and is not permission to force-load them
  or bypass existing module checks. Keep artifact-integrity checks separate from
  runtime feature gating; do not add fixed firmware/hash allowlists.
- For updates, preserve unrelated user packages, constraints and configuration.
  Cleanup of the withdrawn generated native-kernel metadata must remain scoped to
  confirmed records from that migration and use the normal OTA transaction/rollback.
  Do not infer an `apk upgrade` boot failure from metadata differences alone.
- Read `docs/NATIVE-KERNEL-APK.zh-CN.md` before changing kernel package metadata.

# Local builds and release packaging

- A device hotfix is not complete until its production source, hardware profile,
  boot/service ordering, build/install path and relevant regression checks are
  updated in this repository. Never use files from work/, a deployed device or
  an old package as the production fix. Record temporary diagnostics separately.
- Before reporting a hotfix ready for release, compare the prepared root with
  the current sources and verify changed native binaries against their build
  receipts. Register new files/services/catalogs in the tracked assembly path;
  a successful copy to the device alone is not release integration.

- Read `docs/BUILD.zh-CN.md`, `docs/LOCAL-BUILD.zh-CN.md` and `docs/AGENT-BUILD.zh-CN.md` before a local build or release. Public defaults must build without adjacent repos or private captures; local cache overrides must be explicitly selected, never auto-discovered. Use the
  version-controlled `tools/build-release.py` entry point for task logging,
  workspace locking and release assembly. Never generate another release worker
  in `work/`, or execute/modify an old worker to assemble a new release.
- Reuse the existing `/home/kano/openwrt-build` workspace on this machine.
  Register input paths in `tools/build-layout.json` or an explicitly selected
  local config. Do not migrate builds to C:, create timestamped source/object
  trees, clone another kernel, export another Docker volume, or duplicate a
  complete rootfs as a shortcut. Existing model-specific prepared source/object
  caches are retained; never share a patched source tree across models blindly.
- Keep final local releases under `release/`, task logs/status under
  `out/build-logs/` and `out/build-state/`, and package staging under the fixed
  workspace `package-work/u30pro-release/`. Investigations belong under
  `work/` or `dumps/`; they are not production build inputs unless registered.
- Separate native Windows/macOS installer builds, kernel/APK compilation, and
  package assembly. Check source fingerprints and matching Image/modules before
  reuse. Do not rebuild unchanged inputs merely because packaging is requested,
  or bypass a stale-input rejection to avoid compiling a changed dependency.
- Use only the model's tracked build/prepare scripts. Do not use `git reset`,
  `git clean`, archive extraction over a prepared tree, or an arbitrary cache
  substitution to switch profiles. Stop and describe missing/invalid registered
  inputs instead of silently choosing another tree or an old package.
- Successful assembly removes only its owned staging, after archive verification.
  Failed staging is retained for diagnosis and requires `clean-staging` before
  reuse. Never automatically delete source/object/download caches, device dumps,
  installation backups, or previous releases. Do not run `docker system prune`
  or remove volumes as routine build cleanup.

# Shared installer ownership

- installer/ is the Git submodule https://github.com/kanoqwq/openwrt-tools, pinned to a reviewed commit. Read installer/AGENTS.md and installer/docs/BUILD.zh-CN.md before installer work.
- Commit shared UI/backend/Android/runtime changes in that repository, then update this parent repository's gitlink. Never restore a full generated installer mirror or auto-follow an unpinned branch during packaging.
- Fresh checkouts must run git submodule update --init --recursive. Parent CI must use recursive submodules.
- E5, MU300 and U30 Pro keep distinct NV, storage identity and boot adapters. Both support eMMC/UFS. A model-name mismatch is a typed yes decision, not a hardcoded allowlist; other integrity and partition checks remain in effect.
- Reuse one verified native installer build across both parents with the existing artifact environment variables; do not duplicate SDK, node_modules, Cargo targets or rootfs caches.
