#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-only
# Ubuntu/Debian x86_64 builder for the RMX2061 6.12 bring-up tree.
set -Eeuo pipefail

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
fail() { echo "ERROR: $*" >&2; exit 1; }
usage() {
    cat <<'EOF'
Usage: ./build.sh [--install-deps] [--configure-only]

First build: ./build.sh --install-deps
Next build:  ./build.sh
Preflight:   ./build.sh --configure-only

Downloads pinned Android Clang/Rust/bindgen and AnyKernel3, builds Image,
Image.gz, modules and RMX2061 DTB/DTBO, then creates a bring-up AnyKernel3 ZIP.
Uploads the validated ZIP to GoFile after success (GOFILE_UPLOAD=0 disables it).
No flashing, cache wiping or source cleaning is performed.

Environment: JOBS (all available CPUs), OUT_DIR (out), DIST_DIR (dist), TOOLCHAIN_DIR (.build-tools),
CLANG_DIR, RUST_DIR, BINDGEN, ANYKERNEL_DIR, KERNELRELEASE, GOFILE_UPLOAD (1).
Existing external tool directories must contain the versions pinned below.
EOF
}
install_deps=0
configure_only=0
for arg in "$@"; do
    case "$arg" in
        --install-deps) install_deps=1 ;;
        --configure-only) configure_only=1 ;;
        -h|--help) usage; exit 0 ;;
        *) fail "Unknown argument: $arg (see --help)" ;;
    esac
done
[[ $(uname -s) == Linux && $(uname -m) == x86_64 ]] || fail "Run on an x86_64 Linux VM."
if ((install_deps)); then
    privilege=()
    if ((EUID != 0)); then privilege=(sudo); fi
    "${privilege[@]}" apt-get update
    "${privilege[@]}" apt-get install -y build-essential bc bison flex curl git \
        python3 jq libssl-dev libelf-dev libdw-dev zlib1g-dev libncurses-dev pkg-config \
        cpio rsync kmod xz-utils zstd lz4 device-tree-compiler ca-certificates util-linux
fi
for tool in make gcc bc bison flex curl git python3 openssl pkg-config rsync depmod \
            tar gzip xz sha256sum realpath flock fdtget; do
    command -v "$tool" >/dev/null || fail "Missing $tool; run ./build.sh --install-deps."
done
pkg-config --exists libelf libdw openssl zlib || fail "Missing development libraries; use --install-deps."
GOFILE_UPLOAD=${GOFILE_UPLOAD:-1}
[[ $GOFILE_UPLOAD == 0 || $GOFILE_UPLOAD == 1 ]] || fail "GOFILE_UPLOAD must be 0 or 1."
if [[ $GOFILE_UPLOAD == 1 ]]; then
    command -v jq >/dev/null || fail "Missing jq; use --install-deps or GOFILE_UPLOAD=0."
fi

cd "$ROOT"
OUT_DIR=$(realpath -m "${OUT_DIR:-$ROOT/out}")
DIST_DIR=$(realpath -m "${DIST_DIR:-$ROOT/dist}")
TOOLCHAIN_DIR=$(realpath -m "${TOOLCHAIN_DIR:-$ROOT/.build-tools}")
[[ $OUT_DIR != "$ROOT" && $ROOT != "$OUT_DIR/"* ]] || fail "OUT_DIR must be separate from the source."
[[ $OUT_DIR != *[[:space:]]* && $ROOT != *[[:space:]]* ]] || fail "Kbuild requires source/output paths without whitespace."
mkdir -p "$OUT_DIR" "$DIST_DIR" "$TOOLCHAIN_DIR"
exec 9>"$OUT_DIR/.rmx2061-build.lock"
flock -n 9 || fail "Another build is using $OUT_DIR."
exec 8>"$TOOLCHAIN_DIR/.rmx2061-tools.lock"
flock -n 8 || fail "Another process is setting up these toolchains."
JOBS=${JOBS:-$(nproc)}
[[ $JOBS =~ ^[1-9][0-9]*$ ]] || fail "JOBS must be a positive integer."
CLANG_DIR=$(realpath -m "${CLANG_DIR:-$TOOLCHAIN_DIR/clang-r536225}")
RUST_DIR=$(realpath -m "${RUST_DIR:-$TOOLCHAIN_DIR/rust-1.82.0.p2}")
BINDGEN=$(realpath -m "${BINDGEN:-$TOOLCHAIN_DIR/clang-tools/bin/bindgen}")
ANYKERNEL_DIR=$(realpath -m "${ANYKERNEL_DIR:-$TOOLCHAIN_DIR/AnyKernel3}")
AK3_REV=f1d4fc3dc76eec5b9385eaa8ea617c89b429a539

download() {
    local url=$1 dest=$2 digest=$3
    if [[ ! -f $dest ]] || ! echo "$digest  $dest" | sha256sum -c --status; then
        curl --fail --location --retry 3 --connect-timeout 30 "$url" -o "$dest.part"
        echo "$digest  $dest.part" | sha256sum -c - || fail "Download checksum failed: $dest"
        mv "$dest.part" "$dest"
    fi
}
extract_tool() {
    local dest=$1 archive=$2 url=$3 digest=$4 temp
    [[ ! -e $dest ]] || fail "Incomplete tool directory $dest; choose a new TOOLCHAIN_DIR or repair it."
    download "$url" "$TOOLCHAIN_DIR/$archive" "$digest"
    mkdir -p "$(dirname "$dest")"
    temp=$(mktemp -d "${dest}.tmp.XXXXXX")
    tar -xzf "$TOOLCHAIN_DIR/$archive" -C "$temp"
    mv "$temp" "$dest"
}
if [[ ! -x $CLANG_DIR/bin/clang ]]; then
    extract_tool "$CLANG_DIR" clang-r536225.tar.gz \
        https://android.googlesource.com/platform/prebuilts/clang/host/linux-x86/+archive/77c95e8253c2c82ffd4fee92c0ad9f5ac1e8ca04/clang-r536225.tar.gz \
        0b59d8dcf0163b888e456667029147ba55a8fe76b06791bd4a7b481706b1f8ec
fi
if [[ ! -x $RUST_DIR/bin/rustc ]]; then
    extract_tool "$RUST_DIR" rust-1.82.0.p2.tar.gz \
        https://android.googlesource.com/platform/prebuilts/rust/+archive/5c78b1e636b2bf68d46a6980437590fddca64147/linux-x86/1.82.0.p2.tar.gz \
        590414047d833f510cc2f352afa509772fe2a2095e9ca24b70d2a1ee0cd7a2bd
fi
if [[ ! -x $BINDGEN ]]; then
    mkdir -p "$(dirname "$BINDGEN")"
    curl --fail --location --retry 3 --connect-timeout 30 \
        'https://android.googlesource.com/platform/prebuilts/clang-tools/+/c03d5bc912878cdcbdc38fcb003e94116b978956/linux-x86/bin/bindgen?format=TEXT' \
        | base64 -d > "$BINDGEN.part"
    echo "80cd7d3962a33094cba36b507e420b069a972fa6b32030520357a7327e30f349  $BINDGEN.part" | sha256sum -c -
    chmod 755 "$BINDGEN.part"
    mv "$BINDGEN.part" "$BINDGEN"
fi
export PATH="$CLANG_DIR/bin:$RUST_DIR/bin:$(dirname "$BINDGEN"):$PATH"
export BINDGEN LIBCLANG_PATH="$CLANG_DIR/lib"
export RUST_LIB_SRC="$RUST_DIR/lib/rustlib/src/rust/library"
clang --version | grep -F 'based on r536225' || fail "Clang r536225 required."
rustc --version | grep -F 'rustc 1.82.0' || fail "Android Rust 1.82.0.p2 required."
[[ $("$BINDGEN" --version) == 'bindgen 0.69.5' ]] || fail "bindgen 0.69.5 required."
[[ -f $RUST_LIB_SRC/core/src/lib.rs ]] || fail "Rust library sources are missing."
flock -u 8

export SOURCE_DATE_EPOCH=${SOURCE_DATE_EPOCH:-$(git log -1 --format=%ct)}
export KBUILD_BUILD_TIMESTAMP=${KBUILD_BUILD_TIMESTAMP:-$(date -u -d "@$SOURCE_DATE_EPOCH" '+%a %b %e %T UTC %Y')}
export KBUILD_BUILD_USER=${KBUILD_BUILD_USER:-builder}
export KBUILD_BUILD_HOST=${KBUILD_BUILD_HOST:-rmx2061}
export KBUILD_BUILD_VERSION=${KBUILD_BUILD_VERSION:-1}
base_version=$(make -s --no-print-directory kernelversion)
KERNELRELEASE=${KERNELRELEASE:-$base_version-rmx2061}
[[ $KERNELRELEASE =~ ^[a-zA-Z0-9._+-]+$ && ${#KERNELRELEASE} -le 64 ]] || fail "Invalid KERNELRELEASE."
make_args=(O="$OUT_DIR" ARCH=arm64 LLVM=1 KCFLAGS=-D__ANDROID_COMMON_KERNEL__ KERNELRELEASE="$KERNELRELEASE")
run_make() {
    local log=$1
    shift
    if make "${make_args[@]}" "$@" 2>&1 | tee "$OUT_DIR/$log"; then
        return 0
    else
        echo "Build stopped. Full log: $OUT_DIR/$log" >&2
        return 1
    fi
}
run_make rust-check.log rustavailable
run_make config.log defconfig rmx2061.config
for config in RUST ASHMEM MODULES MODVERSIONS GENDWARFKSYMS IKCONFIG PSTORE_RAM USB_DWC3 SCSI_UFS_QCOM; do
    grep -qx "CONFIG_$config=y" "$OUT_DIR/.config" || fail "Required CONFIG_$config is disabled."
done
if ((configure_only)); then
    echo "Toolchain and RMX2061 configuration passed: $OUT_DIR/.config"
    exit 0
fi
run_make build.log -j"$JOBS" Image Image.gz modules \
    qcom/sm7125-realme-rmx2061.dtb qcom/sm7125-realme-rmx2061-overlay.dtbo

flock -n 8 || fail "Another process is setting up AnyKernel3; rerun after it finishes."
if [[ ! -d $ANYKERNEL_DIR ]]; then
    git init "$ANYKERNEL_DIR"
    git -C "$ANYKERNEL_DIR" remote add origin https://github.com/theshaenix/AnyKernel3.git
    git -C "$ANYKERNEL_DIR" fetch --depth 1 origin "$AK3_REV"
    git -C "$ANYKERNEL_DIR" checkout --detach FETCH_HEAD
fi
[[ $(git -C "$ANYKERNEL_DIR" rev-parse HEAD) == "$AK3_REV" ]] || fail "AnyKernel3 must be pinned to $AK3_REV."
[[ -z $(git -C "$ANYKERNEL_DIR" status --porcelain) ]] || fail "Use a clean AnyKernel3 checkout."
flock -u 8

# A failed run cannot masquerade as an old successful ZIP.
result=$(mktemp -d "$DIST_DIR/RMX2061-$KERNELRELEASE-$(date -u +%Y%m%d-%H%M%S)-XXXXXX")
run_make modules-install.log -j"$JOBS" modules_install INSTALL_MOD_PATH="$result/modules" INSTALL_MOD_STRIP=1
rm -f "$result/modules/lib/modules/$KERNELRELEASE/build" "$result/modules/lib/modules/$KERNELRELEASE/source"
tar -czf "$result/modules.tar.gz" -C "$result/modules" .
python3 "$ROOT/scripts/package-rmx2061.py" "$OUT_DIR" "$result" "$ANYKERNEL_DIR" "$KERNELRELEASE"
cp "$OUT_DIR/"{build,config,rust-check,modules-install}.log "$result/"
git rev-parse HEAD > "$result/source-commit.txt"
git status --short > "$result/source-status.txt"
git diff --binary HEAD > "$result/source-changes.patch"
{ clang --version; rustc --version; "$BINDGEN" --version; echo "AnyKernel3 $AK3_REV"; } > "$result/toolchains.txt"
(cd "$result"; sha256sum -- *.zip *.tar.gz Image Image.gz Image.gz-dtb dtb dtbo.img kernel.config > SHA256SUMS)
echo "Build and packaging complete: $result"
echo "BRING-UP ONLY: compilation does not establish phone boot or Android compatibility."
if [[ $GOFILE_UPLOAD == 1 ]]; then
    if link=$(bash "$ROOT/scripts/upload-gofile.sh" "$result/RMX2061-$KERNELRELEASE-bringup.zip"); then
        printf '%s\n' "$link" > "$result/gofile-link.txt"
        echo "GoFile download: $link"
    else
        echo "Build succeeded, but GoFile upload failed. ZIP retained in $result." >&2
        echo "Retry: bash scripts/upload-gofile.sh '$result/RMX2061-$KERNELRELEASE-bringup.zip'" >&2
        exit 2
    fi
fi
