# Realme 6 Pro / RMX2061 — Android 6.12 port

Experimental source work for Evolution X CNB. The initial RMX2061 board
DTS covers identification, fixed reserved memory and the debug UART. It
has not been boot-tested; there is no bootable RMX2061 image yet. The
existing Xiaomi reference DTBs must not be flashed to RMX2061.

## Source and authorship

- Android Common Kernel: <https://android.googlesource.com/kernel/common>
- Starting tag: `android16-6.12-2026-09_r14` (Linux 6.12.92)
- Starting commit: `1c2e69ab43af9f6078be91c53b2c6043390e39a6`
- Development and default branch: `main`

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

Realme board data is adapted from the Linux Foundation's 2019–2020 vendor
descriptions in `arch/arm64/boot/dts/19721/{atoll.dtsi,atoll-ab-idp-overlay.dts}`
of the local ShadowBladeX tree at commit
`7306b28fccd87db72f25b314105747b1ce6f653c`, checked against a running RMX2061.
The new board DTS retains those copyright notices and GPL-2.0-only license.

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

The initial Realme board can be compiled in the same configured output:

```sh
make O=/path/to/out ARCH=arm64 LLVM=1 qcom/sm7125-realme-rmx2061.dtb
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

## Initial Realme board and live evidence

Read-only captures on 2026-11-07 identify the connected RMX2061 as Atoll-AB
(SoC ID 443), project 19721, board ID `<34 0>`, DTBO index 0. It runs
Evolution X 17.0 / Android 17 with Astra 4.14.357. Its panel command-line
selection is `dsi_nt36672c_jdi_video_display`; this does not establish a
working 6.12 panel or touch driver.

The captured boot header is v2, with 4 KiB packing pages, a 64 MiB boot
partition and separate 24 MiB DTBO partition. The running kernel config
and decompressed Image header independently confirm 4 KiB kernel pages.
The old Image's text offset is `0x80000`; the 6.12 Image header specifies
zero. Whether the bootloader hardcodes an offset remains unverified.
Boot header address fields and the ARM64 Image text offset are distinct;
no bootloader workaround or image packaging change is implemented yet.

`sm7125-realme-rmx2061.dts` retains the measured Qualcomm selectors and
`oppo,dtsi_no = <19721>`. It enables UART8 at `0xa88000`, GPIO44/45, through
its QUP parent. It leaves RAM capacity for the bootloader to populate.
Storage, USB, display, GPU, video and remote processors remain disabled,
along with the unused graphics, video and camera clock controllers.

The fixed reservation map preserves all captured regions and their
`no-map` coverage. The overlapping vendor removal/modem reservations are
split at `0x86000000`, preserving their union. Duplicate splash/display
dump reservations become one region. The inherited SC7180 XBL/AOP/command
DB reservations are retained conservatively, reserving an extra 1 MiB at
`0x80600000` compared with the live vendor map; command DB placement still
needs independent confirmation. The vendor log region is reserved without
enabling its unaudited custom ramoops layout. Unused dynamic pools are
deferred with their consumers; the unrelated SC7180 RMTFS reservation is
removed rather than borrowing a Xiaomi address.

The Realme DTB compiled with the bootstrap Linux toolchain. A local check
of the compiled artifact verifies boot selectors, UART wiring, complete
fixed/no-map reservation coverage, absence of overlapping reservations,
and disabled storage/USB/remote processors. Raw phone captures, unique
identifiers and local Python checks remain excluded from Git.

## Remaining device work

Next are the pinned production toolchain/full Image build, vendor-interface
feasibility audit, PMIC/regulator integration, UFS and USB, and boot-image
DTB/DTBO packaging. The CNB platform manifest and firmware paths still need
an integration audit. The product shipping API level remains 29.

The available vendor tree contains 42 modules with vermagic
`4.14.180-perf+ SMP preempt mod_unload modversions aarch64`. They cannot be
reused as 6.12 kernel modules. The ION, KGSL, HWC, camera, audio/DSP and
security interfaces also need an explicit compatibility audit and port.

No boot, encryption, graphics, camera, radio, suspend, thermal or charging
acceptance test has passed. The debug UART has not been validated on hardware.
