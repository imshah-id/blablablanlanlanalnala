#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Package only validated outputs from an RMX2061 build, without flashing."""
import gzip
import hashlib
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import zipfile
import zlib


def adapt_installer(original):
    """Keep the ShadowBladeX AK3 fork; adapt only its device policy/install block."""
    start = original.index('# boot install\n')
    end = original.index('## end boot install', start)
    install = '''# boot install
[ "$(getprop ro.bootmode)" = recovery ] || abort "Install from recovery only."
[ -z "$(getprop ro.boot.slot_suffix)" ] || abort "A-only RMX2061 required."
[ "$(blockdev --getsize64 "$BLOCK")" = 67108864 ] || abort "Unexpected boot partition size."
DTBO_BLOCK=/dev/block/bootdevice/by-name/dtbo
[ "$(blockdev --getsize64 "$DTBO_BLOCK")" = 25165824 ] || abort "Unexpected DTBO partition size."
set -o pipefail
sha256sum -c payload.sha256 || abort "Payload checksum failure."
ui_print "RMX2061 6.12 bring-up: phone boot is not yet confirmed."
split_boot
[ "$(od -An -tu4 -j40 -N4 "$BOOTIMG" | tr -d ' ')" = 2 ] || abort "Boot header v2 required."
dd if="$DTBO_BLOCK" of="$AKHOME/dtbo-before.img" bs=1048576 || abort "DTBO backup failed."
boot_before=$(sha256sum "$BOOTIMG" | cut -d' ' -f1)
dtbo_before=$(sha256sum "$AKHOME/dtbo-before.img" | cut -d' ' -f1)
[ "$boot_before" = "$(sha256sum "$BLOCK" | cut -d' ' -f1)" ] || abort "Boot backup mismatch."
[ "$dtbo_before" = "$(sha256sum "$DTBO_BLOCK" | cut -d' ' -f1)" ] || abort "DTBO backup mismatch."
restore_on_error() {
    result=$?
    trap - EXIT
    if [ "$result" != 0 ]; then
        ui_print "Installation failed; restoring saved boot and DTBO."
        dd if="$BOOTIMG" of="$BLOCK" bs=1048576 conv=fsync
        dd if="$AKHOME/dtbo-before.img" of="$DTBO_BLOCK" bs=1048576 conv=fsync
        sync
        if [ "$boot_before" = "$(sha256sum "$BLOCK" | cut -d' ' -f1)" ] &&
           [ "$dtbo_before" = "$(sha256sum "$DTBO_BLOCK" | cut -d' ' -f1)" ]; then
            ui_print "Original boot and DTBO restored and verified."
        else
            ui_print "RESTORATION FAILED: stay in recovery and restore your backups."
        fi
    fi
    exit "$result"
}
trap restore_on_error EXIT
flash_boot
flash_generic dtbo
sync
for pair in "boot-new.img:$BLOCK" "dtbo.img:$DTBO_BLOCK"; do
    file=${pair%%:*}
    device=${pair#*:}
    expected=$(sha256sum "$AKHOME/$file" | cut -d' ' -f1)
    actual=$(head -c "$(wc -c < "$AKHOME/$file")" "$device" | sha256sum | cut -d' ' -f1)
    [ "$actual" = "$expected" ] || abort "Readback mismatch: $device"
done
trap - EXIT
ui_print "Installation readback passed; this does not confirm kernel boot." \\
    "Temporary originals remain in $AKHOME; save backups before rebooting."
'''
    text = original[:start] + install + original[end:]
    text = re.sub(r'^device\.name\d+=.*\n', '', text, flags=re.M)
    text = text.replace('# Supported devices', '# Supported devices\ndevice.name1=RMX2061\ndevice.name2=rmx2061\ndevice.name3=realme6pro')
    text = re.sub(r'^kernel.string=.*$', 'kernel.string=RMX2061 Linux 6.12 bring-up (not daily-use)', text, flags=re.M)
    text = text.replace('do.cleanup=1', 'do.cleanup=0')
    text = text.replace('PATCH_VBMETA_FLAG=auto;', 'PATCH_VBMETA_FLAG=0;\nNO_MAGISK_CHECK=1;\nCUSTOMDD=bs=1048576;')
    text = text.replace('## Modified by Shahid Shamim (Realme 6 Pro & 7 Pro Support)',
                        '## Modified by Shahid Shamim; adapted for RMX2061 Linux 6.12 bring-up')
    text = text.replace('# Realme 6 Pro (RMX2061, atoll) & Realme 7 Pro (RMX2170, reatoll)',
                        '# Realme 6 Pro (RMX2061) only')
    return text


def dtbo_image(overlay):
    if len(overlay) < 40 or struct.unpack_from('>2I', overlay) != (0xd00dfeed, len(overlay)):
        raise ValueError('Invalid or truncated overlay DTB')
    return (struct.pack('>8I', 0xd7b7ab1e, 64 + len(overlay), 32, 32, 1, 32, 4096, 0)
            + struct.pack('>8I', len(overlay), 64, 0, 0, 0, 0, 0, 0) + overlay)


def package(out, dest, ak3, release):
    boot = out / 'arch/arm64/boot'
    image = (boot / 'Image').read_bytes()
    compressed = (boot / 'Image.gz').read_bytes()
    config = (out / '.config').read_bytes()
    if len(image) < 64 or image[56:60] != b'ARM\x64' or gzip.decompress(compressed) != image:
        raise ValueError('Invalid ARM64 Image or mismatched Image.gz')
    start = image.index(b'IKCFG_ST') + 8
    end = image.index(b'IKCFG_ED', start)
    if zlib.decompress(image[start:end], 31) != config:
        raise ValueError('Embedded configuration does not match this build')
    if (out / 'include/config/kernel.release').read_text().strip() != release:
        raise ValueError('Kernel release does not match this build')
    if ('Linux version ' + release + ' ').encode() not in image:
        raise ValueError('Image release does not match this build')
    dtb_path = boot / 'dts/qcom/sm7125-realme-rmx2061.dtb'
    overlay_path = boot / 'dts/qcom/sm7125-realme-rmx2061-overlay.dtbo'
    for path in (dtb_path, overlay_path):
        compatible = subprocess.check_output(['fdtget', '-t', 's', str(path), '/', 'compatible']).split()
        if b'realme,rmx2061' not in compatible or b'qcom,sm7125' not in compatible:
            raise ValueError('Wrong device tree: ' + str(path))
        for prop, expected in [('qcom,msm-id', b'443 0'), ('qcom,board-id', b'34 0')]:
            if subprocess.check_output(['fdtget', '-t', 'u', str(path), '/', prop]).strip() != expected:
                raise ValueError('Wrong device selector: ' + prop)
    dtb = dtb_path.read_bytes()
    if struct.unpack_from('>2I', dtb) != (0xd00dfeed, len(dtb)):
        raise ValueError('Invalid board DTB length')
    payload = {'Image.gz-dtb': compressed + dtb, 'dtb': dtb,
               'dtbo.img': dtbo_image(overlay_path.read_bytes())}
    dest.mkdir(parents=True, exist_ok=True)
    for name, data in dict(payload, Image=image, **{'Image.gz': compressed, 'kernel.config': config}).items():
        (dest / name).write_bytes(data)
    shutil.copyfile(overlay_path, dest / overlay_path.name)
    sums = ''.join(hashlib.sha256(data).hexdigest() + '  ' + name + '\n' for name, data in payload.items())
    installer = adapt_installer((ak3 / 'anykernel.sh').read_text())
    filename = dest / ('RMX2061-' + release + '-bringup.zip')
    with zipfile.ZipFile(filename, 'x', zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(ak3.rglob('*')):
            relative = path.relative_to(ak3)
            if path.is_file() and (relative.parts[0] in ('META-INF', 'tools') or relative.as_posix() == 'LICENSE'):
                archive.write(path, relative)
        archive.writestr('anykernel.sh', installer)
        for name, data in payload.items():
            archive.writestr(name, data)
        archive.writestr('payload.sha256', sums)
        archive.writestr('version', release + '\n')
    with zipfile.ZipFile(filename) as archive:
        if archive.testzip() is not None:
            raise ValueError('Corrupt ZIP')
        for required in ('LICENSE', 'META-INF/com/google/android/update-binary', 'tools/ak3-core.sh', 'tools/magiskboot'):
            if required not in archive.namelist():
                raise ValueError('Incomplete AnyKernel3 checkout: ' + required)
        for name, data in payload.items():
            if archive.read(name) != data:
                raise ValueError('ZIP payload mismatch: ' + name)
    print('Validated bring-up ZIP: ' + str(filename))


if __name__ == '__main__':
    if len(sys.argv) != 5:
        raise SystemExit('Usage: package-rmx2061.py OUT_DIR DIST_DIR ANYKERNEL_DIR KERNELRELEASE')
    package(*(Path(p).resolve() for p in sys.argv[1:4]), sys.argv[4])
