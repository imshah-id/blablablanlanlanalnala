#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Offline packaging/upload checks. Never contacts GoFile or a device."""
import importlib.util
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('package', ROOT / 'scripts/package-rmx2061.py')
package = importlib.util.module_from_spec(spec)
spec.loader.exec_module(package)


class PackageTests(unittest.TestCase):
    def test_partial_install_failure_restores_both_images(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            device = root / 'device'
            device.mkdir()
            original_boot = bytes(40) + struct.pack('<I', 2) + bytes(20)
            (device / 'boot').write_bytes(original_boot)
            (device / 'dtbo').write_bytes(b'original dtbo')
            (root / 'tools').mkdir()
            (root / 'tools/ak3-core.sh').write_text('''
AKHOME=$PWD
BOOTIMG=$PWD/boot.img
ui_print() { echo "$@"; }
abort() { echo "$@"; exit 1; }
getprop() { [ "$1" != ro.bootmode ] || echo recovery; }
blockdev() { case "$2" in */boot) echo 67108864;; *) echo 25165824;; esac; }
sha256sum() { if [ "$1" = -c ]; then return 0; fi; command sha256sum "$@"; }
split_boot() { cp "$BLOCK" "$BOOTIMG"; }
flash_boot() { printf 'new boot' > "$BLOCK"; }
flash_generic() { printf 'partial dtbo' > "$DTBO_BLOCK"; abort 'injected DTBO failure'; }
''')
            original = '''# Supported devices
device.name1=RMX2061
BLOCK=/dev/block/bootdevice/by-name/boot;
. tools/ak3-core.sh;
# boot install
write_boot;
## end boot install
'''
            script = package.adapt_installer(original).replace('/dev/block/bootdevice/by-name', str(device))
            result = subprocess.run(['bash'], input=script, text=True, cwd=root, capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('Original boot and DTBO restored and verified.', result.stdout)
            self.assertEqual((device / 'boot').read_bytes(), original_boot)
            self.assertEqual((device / 'dtbo').read_bytes(), b'original dtbo')

    def test_dtbo_table_offsets_and_length(self):
        overlay = struct.pack('>2I', 0xd00dfeed, 40) + bytes(32)
        result = package.dtbo_image(overlay)
        header = struct.unpack_from('>8I', result)
        entry = struct.unpack_from('>8I', result, header[5])
        self.assertEqual(header[1], len(result))
        self.assertEqual(result[entry[1]:entry[1] + entry[0]], overlay)

    def test_rejects_truncated_overlay(self):
        with self.assertRaises(ValueError):
            package.dtbo_image(struct.pack('>2I', 0xd00dfeed, 100) + bytes(32))

    def test_adapts_fork_without_legacy_device_edits(self):
        original = '''properties() { '
kernel.string=old
do.cleanup=1
# Supported devices
device.name1=RMX2061
device.name2=RMX2170
'; }
PATCH_VBMETA_FLAG=auto;
. tools/ak3-core.sh;
# boot install
dump_boot;
patch_fstab fstab.tuna /data ext4 options old new;
write_boot;
## end boot install
'''
        result = package.adapt_installer(original)
        self.assertNotIn('RMX2170', result)
        self.assertNotIn('fstab.tuna', result)
        self.assertIn('. tools/ak3-core.sh;', result)
        self.assertIn('split_boot\n', result)
        self.assertIn('flash_generic dtbo', result)
        self.assertIn('Readback mismatch', result)
        subprocess.run(['sh', '-n'], input=result.encode(), check=True)


@unittest.skipUnless(shutil.which('jq'), 'jq required for upload tests')
class UploadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        self.file = self.path / 'kernel with spaces.zip'
        self.file.write_bytes(b'test ZIP payload')
        curl = self.path / 'curl'
        curl.write_text('''#!/usr/bin/env python3
import json, os, sys
with open(os.environ['CALL_LOG'], 'a') as log:
    log.write(json.dumps(sys.argv[1:]) + '\\n')
mode = os.environ.get('RESPONSE_MODE', '')
if sys.argv[-1].endswith('/servers'):
    if mode == 'bad_server':
        print('not json')
    else:
        print(json.dumps({'status':'ok','data':{'servers':[{'name':'store1'}]}}))
elif mode == 'http_error':
    sys.exit(22)
elif mode == 'api_error':
    print(json.dumps({'status':'error-quota','data':{}}))
else:
    print(json.dumps({'status':'ok','data':{'downloadPage':'https://gofile.io/d/Test123'}}))
''')
        curl.chmod(0o755)
        self.env = dict(os.environ, PATH=str(self.path) + os.pathsep + os.environ['PATH'],
                        CALL_LOG=str(self.path / 'calls'))

    def run_upload(self, mode=''):
        return subprocess.run(['bash', str(ROOT / 'scripts/upload-gofile.sh'), str(self.file)],
                              env=dict(self.env, RESPONSE_MODE=mode), capture_output=True, text=True)

    def test_success_and_filename_with_spaces(self):
        result = self.run_upload()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), 'https://gofile.io/d/Test123')
        self.assertEqual(len((self.path / 'calls').read_text().splitlines()), 2)

    def test_bad_server_cannot_trigger_upload(self):
        self.assertNotEqual(self.run_upload('bad_server').returncode, 0)
        self.assertEqual(len((self.path / 'calls').read_text().splitlines()), 1)

    def test_upload_errors_never_print_success_link(self):
        for mode in ['http_error', 'api_error']:
            with self.subTest(mode=mode):
                result = self.run_upload(mode)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, '')

    def test_missing_file_never_contacts_server(self):
        self.file.unlink()
        self.assertNotEqual(self.run_upload().returncode, 0)
        self.assertFalse((self.path / 'calls').exists())


if __name__ == '__main__':
    unittest.main()
