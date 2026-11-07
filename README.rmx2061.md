# Realme 6 Pro / RMX2061 — Android 6.12 port

Experimental source work for Evolution X CNB. There is no RMX2061 bootable
image or validated Realme board DTS yet. The existing Xiaomi reference
DTBs are build checks only and must not be flashed to RMX2061.

## Source and authorship

- Android Common Kernel: <https://android.googlesource.com/kernel/common>
- Starting tag: `android16-6.12-2026-09_r14` (Linux 6.12.92)
- Starting commit: `1c2e69ab43af9f6078be91c53b2c6043390e39a6`
- Port branch: `rmx2061-cnb-6.12`

Keep the base tag unchanged, original SPDX/copyright notices, and original
patch authors, dates and sign-off chains. Import upstream changes as
separate commits with their source commit IDs. Describe any backport
adjustments explicitly. Keep new device work separate from imported work;
do not attribute copied drivers to the porter or invent review/sign-off
trailers. A submitter must personally certify their own DCO sign-off before
external submission; using a configured Git committer identity is not that
certification. See `Documentation/process/submitting-patches.rst`.

The initial checkout is shallow. Earlier history remains available from
the original repositories; the source has not been reinitialized as a new
project. Referenced donor commits are fetched before import.

| Imported prerequisite | Original author | Original commit |
| --- | --- | --- |
| Disable the broken SHM bridge path on SM7125 | Vitalii Skorkin | [`e2467151dcab02a7b134eac32b74fb8267bc2a24`](https://github.com/torvalds/linux/commit/e2467151dcab02a7b134eac32b74fb8267bc2a24) |

That backport adds only the SM7125 blacklist entry. Its context was adjusted
because this ACK base lacks the adjacent SM7150 entry. Its original author,
author date, sign-offs, review/acknowledgment tags and source link are kept.

## Build checks

The first checks used Linux ARM64 and Ubuntu Clang/LLD 18.1.3, with the
kernel's ARM64 `defconfig`. These are bootstrap checks, not a production
GKI build. The checked paths were the TrustZone allocator's SHM bridge mode
and the two existing Xiaomi SM7125 reference DTBs.

On Linux, with LLVM, GNU make, GCC host tools, flex, bison, bc, OpenSSL and
ELF development headers installed, run from this source directory:

```sh
make O=/path/to/out ARCH=arm64 LLVM=1 defconfig
make O=/path/to/out ARCH=arm64 LLVM=1 -j4 \
    drivers/firmware/qcom/qcom_tzmem.o \
    qcom/sm7125-xiaomi-curtana.dtb \
    qcom/sm7125-xiaomi-joyeuse.dtb
```

Confirm `CONFIG_QCOM_TZMEM_MODE_SHMBRIDGE=y` in the output `.config` when
checking the imported fix. Keep outputs on a Linux filesystem with enough
storage, outside the source checkout. The ACK release's toolchain constants
are Clang `r536225` and Rust `1.82.0.p2` in `build.config.constants`; a full
GKI build with those matching dependencies remains to be done.

As of 2026-11-07, the original and patched sources both passed the targeted
Linux compilation checks. A local harness exercising the actual allocator
initializer reproduced an unwanted firmware call on SM7125 before the fix;
afterward all five cases passed: SM7125 bypass, existing SC7180 bypass,
supported-platform enable, unsupported firmware fallback and firmware error
propagation. This harness replaces OF matching and the firmware call; it
does not validate TrustZone on physical hardware.

New scratch Python checks, logs and downloaded patches belong under
`.port-local/`, excluded locally through `.git/info/exclude`. Do not remove
or globally ignore upstream Python tools/tests.

## Remaining device work

The local CNB device configuration uses boot header v2, a 64 MiB boot
partition, separate 24 MiB DTBO, and shipping API level 29. These are source
settings, not live-device measurements. The installed phone's boot/DTBO
selection, reserved memory, panel/touch variant, firmware and CNB platform
manifest still need to be captured before finalizing the Realme board DTS.

The available vendor tree contains 42 modules with vermagic
`4.14.180-perf+ SMP preempt mod_unload modversions aarch64`. They cannot be
reused as 6.12 kernel modules. The ION, KGSL, HWC, camera, audio/DSP and
security interfaces also need an explicit compatibility audit and port.

No phone was attached during this stage. No boot, encryption, graphics,
camera, radio, suspend, thermal or charging acceptance test has passed.
