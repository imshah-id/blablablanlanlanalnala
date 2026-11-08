# Realme 6 Pro (RMX2061) — Linux 6.12

Device support for RMX2061 / Qualcomm SM7125 (Atoll-AB), based on Android
Common Kernel 6.12. Intended for custom ROM development; integration is not
tied to a particular ROM project.

**Status: source bring-up.** Board descriptions and selected driver paths
build, but this kernel has not booted on RMX2061. There is no validated boot
image, flashable package or hardware-support release.

## Port status

Updated: 2026-11-07. “Implemented” means source/configuration is present.
Build checks do not establish that a component works on the phone.

| Component | Implemented | Verification | Remaining work |
| --- | --- | --- | --- |
| Android kernel base | Pinned ACK 6.12.92; SM7125 TrustZone SHM-bridge fix | Targeted compilation and allocator regression checks | Matching production toolchain and full Image build |
| Board identification | RMX2061 DTS; SoC 443, board 34/0, project 19721 | Compared with live DT/selected DTBO; compiled-DTB checks | Bootloader acceptance and DTB/DTBO packaging |
| Reserved memory | Fixed firmware carveouts; overlapping vendor ranges normalized | Complete fixed/no-map coverage and non-overlap checks | Command DB location and dynamic pools |
| Debug console | UART8 at 0xa88000; GPIO44/45 | DT compilation, bindings and pinctrl assertions | Physical UART output |
| PMICs and regulators | PM6150/PM6150L descriptions; six UFS/USB rails | Supply/voltage checks, bindings and driver compilation | Physical rail operation; remaining peripheral supplies |
| PMIC temperature monitoring | Upstream thermal trips; built-in temperature/ADC drivers | Configuration and driver compilation | Physical thermal/suspend testing |
| UFS storage | Controller/PHY supplies; TLMM119 reset | DT/schema checks; host, core and PHY compilation | Device enumeration, I/O and power transitions |
| USB device mode | USB2-only DWC3/QUSB2; vendor PHY tuning; configfs/FunctionFS | DT/schema checks and driver compilation | Enumeration, gadget functions and suspend/resume |
| Inline storage crypto | UFS crypto and Qualcomm ICE selected in bring-up config | Configuration and driver compilation | Firmware/key compatibility and encrypted-data access |
| Display and touch | No board drivers enabled | JDI NT36672C panel selection captured as reference | Panel, backlight and touch bring-up |
| GPU | Disabled | Disabled-state checks | Driver/userspace interface decision and bring-up |
| Modem, DSP and connectivity | Board remote processors disabled | Disabled-state checks | Firmware mapping, modem, Wi-Fi, Bluetooth and audio |
| Camera, sensors and fingerprint | Not ported | None | Driver and userspace integration |
| Battery and charging | Not ported | None | Fuel gauge, charger, Type-C/OTG, protections and fast charging |
| ROM integration | Not implemented | No userspace boot test | Init, fstab, modules, VINTF, SELinux and vendor interfaces |

No boot, storage I/O, USB enumeration, graphics, camera, radio, encrypted-data,
suspend, thermal or charging acceptance test has passed on this kernel.

## Source baseline

| Item | Revision |
| --- | --- |
| Upstream | [Android Common Kernel](https://android.googlesource.com/kernel/common) |
| Starting tag | `android16-6.12-2026-09_r14` |
| Starting commit | `1c2e69ab43af9f6078be91c53b2c6043390e39a6` |
| Kernel version | `6.12.92` |
| Development branch | `main` |
| Board source | `arch/arm64/boot/dts/qcom/sm7125-realme-rmx2061.dts` |
| Bring-up fragment | `arch/arm64/configs/rmx2061.config` |

The original upstream history and pinned tag are preserved. Existing Xiaomi
SM7125 DTBs are reference build targets and are unsuitable for RMX2061.

## Build and validation

### Ubuntu/Debian x86_64 VM

Copy this updated checkout to the VM, then run from the kernel directory:

```sh
./build.sh --install-deps
```

The first run installs host packages using sudo when needed and downloads the
pinned Android Clang r536225, Rust 1.82.0.p2 and bindgen 0.69.5. By default it
uses all available CPUs (`nproc`). Use `JOBS=8 ./build.sh` to override parallelism
if needed. Later builds use `./build.sh`; output is
incremental in `out/` and tool downloads are cached in `.build-tools/`.
`./build.sh --configure-only` checks the tools and resolves the board configuration
without compiling the kernel. The board fragment is reapplied on each run;
make persistent config changes in `arch/arm64/configs/rmx2061.config`.

Each successful build creates its own directory under `dist/` containing
Image, Image.gz, Image.gz-dtb, the board DTB, DTBO image, resolved config,
modules.tar.gz, full logs, source revision/change records and SHA256SUMS.
It also creates `RMX2061-<release>-bringup.zip` using the same
[theshaenix/AnyKernel3](https://github.com/theshaenix/AnyKernel3) fork as
ShadowBladeX, pinned to `f1d4fc3dc76eec5b9385eaa8ea617c89b429a539`.
`ANYKERNEL_DIR` can point to an existing clean checkout of that revision.

The generated installer keeps that fork's core/tools and A-only boot path,
restricts the device list to RMX2061 aliases, and removes the unrelated Galaxy
Nexus ramdisk example edits. It preserves the installed Android ramdisk, replaces
both DTB copies and DTBO, and verifies flash readback. Kernel modules remain in a
separate archive, not automatically installed into the existing ROM. It does not
add KernelSU or promise to retain root. Temporary pre-install images remain in
recovery's `/tmp/anykernel`; save durable boot/DTBO backups before flashing.
On a detected installer failure it attempts restoration, but this cannot protect
against power loss or establish that the new kernel boots.

After success, only the flashable ZIP is automatically uploaded to GoFile,
following the API flow in the requested
[GoFile-Upload helper](https://github.com/Sushrut1101/GoFile-Upload/blob/master/upload.sh).
The link is printed and saved in `gofile-link.txt`. Set `GOFILE_UPLOAD=0` to build
without uploading. An upload failure returns exit code 2 and retains all local
artifacts; retry without rebuilding:

```sh
bash scripts/upload-gofile.sh dist/<build-directory>/RMX2061-<release>-bringup.zip
```

These are **experimental bring-up ZIPs**, not daily-use releases. Packaging does
not fix the unresolved early boot failure or missing device drivers. The script
does not flash the phone. Run the offline helper tests with
`python3 scripts/tests/test_rmx2061_build.py` (requires jq).

### Manual build

Use Linux with LLVM/LLD, GNU make, GCC host tools, flex, bison, bc, OpenSSL
and ELF development headers. Keep output on a Linux filesystem outside the
source checkout.

The checks below used Linux ARM64 with Ubuntu Clang/LLD 18.1.3. They are
bootstrap checks. The pinned ACK release specifies Clang `r536225` and Rust
`1.82.0.p2` in `build.config.constants`; a full build with those matching
dependencies remains pending. This fragment supplements ARM64 `defconfig`;
it is not a complete ROM configuration or certified GKI configuration.

Configure a separate output:

```sh
make O=/path/to/out ARCH=arm64 LLVM=1 defconfig rmx2061.config
```

Compile the board and the driver paths checked during this milestone:

```sh
make O=/path/to/out ARCH=arm64 LLVM=1 -j4 \
    drivers/regulator/qcom-rpmh-regulator.o drivers/ufs/core/ \
    drivers/ufs/host/ufs-qcom.o drivers/ufs/host/ufshcd-pltfrm.o \
    drivers/soc/qcom/ice.o drivers/phy/qualcomm/phy-qcom-qmp-ufs.o \
    drivers/phy/qualcomm/phy-qcom-qusb2.o drivers/usb/dwc3/ \
    drivers/usb/gadget/configfs.o drivers/usb/gadget/function/f_fs.o \
    drivers/iio/adc/qcom-spmi-adc5.o drivers/iio/adc/qcom-vadc-common.o \
    drivers/thermal/qcom/qcom-spmi-temp-alarm.o \
    qcom/sm7125-realme-rmx2061.dtb
```

The fragment builds the early storage/PHY and configfs gadget paths into the
kernel, including the QMP parent dependency. PMIC temperature/ADC and
inline-crypto dependencies are also built in. Required symbols are checked
after Kconfig resolution, rather than inferred from the fragment text.

Validation covers the compiled selectors, reservation unions, UART/reset
pins, supply phandles, voltage limits, USB2-only PHY list, tuning, eFuse cell
and disabled subsystems. Targeted schema checks cover the new board, PMIC,
regulator, UFS and USB nodes. This is not a full-tree schema pass. During
initial schema preprocessing, the unchanged ACK bindings
`firmware/gunyah-cma-mem.yaml` and `iommu/pkvm,pviommu.yaml` reported parse
errors and were skipped by the validator.

## Board implementation notes

Read-only hardware captures confirm Atoll-AB / SoC ID 443, project 19721,
board ID `<34 0>` and selected DTBO index 0. Both the running 4.14 config
and its decompressed Image header indicate 4 KiB kernel pages. The captured
boot image uses header v2, 4 KiB packing pages, a 64 MiB boot partition and
a separate 24 MiB DTBO partition. Shipping API level 29 is unchanged.

The old ARM64 Image text offset is `0x80000`; the 6.12 header specifies
zero. This is separate from boot-image header address fields. Bootloader
hardcoding and actual load-address behavior remain unverified; no offset
workaround is implemented.

The reserved-memory map preserves every captured fixed region and its
`no-map` coverage. The removal/modem overlap is split at `0x86000000` and
duplicate display reservations are merged. Inherited XBL/AOP/command DB
reservations conservatively retain an extra 1 MiB at `0x80600000`; command
DB placement still needs confirmation. The vendor log region is reserved
without enabling its custom ramoops layout. Unused dynamic pools and their
consumers remain pending. No captured RAM capacity or unique identifiers
are hardcoded into the board source.

The six modeled rails use the vendor consumers' operating requests:

| Rail | Constraint (microvolts) | Consumers |
| --- | --- | --- |
| PM6150 L4 | 880000–900000 | UFS and USB PHY digital supply |
| PM6150 L11 | 1800000 | USB PHY PLL |
| PM6150 L12 | 1750000–1950000 | UFS VCCQ2 |
| PM6150 L17 | 3075000–3200000 | USB DP/DM analog supply |
| PM6150 L19 | 2960000 | UFS VCC |
| PM6150L L3 | 1200000 | UFS PHY PLL/shared reference rail |

These are configuration constraints, not measured voltages. The attempted
regulator-summary debugfs path was unavailable on the running phone.

USB currently supports only the source configuration for high-speed
peripheral mode. SuperSpeed, Type-C role switching and VBUS sourcing remain
disabled. Existing bindings express the vendor PHY tuning; the HSTX eFuse
cell is retained with a zero trim fallback matching the vendor driver's
valid-zero handling. PHY calibration still needs hardware validation.
USB wiring does not provide charger, battery or fast-charge support.

## Custom ROM integration requirements

The available vendor tree contains 42 prebuilt modules with vermagic
`4.14.180-perf+ SMP preempt mod_unload modversions aarch64`. These cannot be
loaded into 6.12; required modules need compatible source and rebuilding.
Firmware blobs and userspace libraries require separate assessment.

Audit the target ROM's ION, KGSL/graphics, display/HWC, camera/video,
audio/DSP RPC and secure-service contracts. Existing vendor binaries must
not be assumed compatible with upstream interfaces. Enabling ICE/crypto
at build time does not establish compatibility with existing encryption
keys or userdata.

Before any release, validate boot/recovery, storage and encryption, USB,
display/touch, GPU/video, radio/connectivity, audio, cameras, sensors,
biometrics, suspend, thermals and charging. ROM-specific init, fstab,
module installation, VINTF and SELinux changes should remain separately
reviewable from reusable kernel device support.

## Provenance and contributions

The SM7125 SHM-bridge prerequisite is a context-only backport of
[Vitalii Skorkin's upstream change](https://github.com/torvalds/linux/commit/e2467151dcab02a7b134eac32b74fb8267bc2a24).
Its author/date and original sign-off, review and acknowledgment trailers
are preserved. The local adaptation only adjusts missing neighboring context.

Realme board data is adapted from the Linux Foundation's 2019–2020 vendor
sources in the local ShadowBladeX snapshot
`7306b28fccd87db72f25b314105747b1ce6f653c`, under
`arch/arm64/boot/dts/19721/`: `atoll.dtsi`, `atoll-ab-idp-overlay.dts`,
`atoll-idp.dtsi`, `atoll-regulator.dtsi`, `atoll-usb.dtsi` and
`atoll-pinctrl.dtsi`. Voltage requests and fuse handling were cross-checked
against that snapshot's `drivers/phy/qualcomm/phy-qcom-ufs.c` and
`drivers/usb/phy/phy-msm-qusb-v2.c`. The board retains the original notices
and GPL-2.0-only license; current upstream drivers and PMIC descriptions
retain their own licenses.

Preserve authorship, copyright, source revision references and existing
sign-off chains when importing changes. Record adaptations separately;
contributors must personally certify any DCO sign-off they supply. Update
the port-status table with the checks performed and hardware results.

Raw hardware captures and local development checks stay outside tracked
source under locally excluded `.port-local/`. Existing upstream Python
sources and tests remain intact.
