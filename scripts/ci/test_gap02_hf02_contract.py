"""Independent XZ fixture checks; not a substitute for Flutter extraction tests.

The archive 4.3.0 encoder (_writeMultibyteInteger, blob
82a778fbc27a9c6bb9ca39531953bd5c6597c521 at upstream b48a841b5) emits
most-significant seven-bit groups first. Its decoder and the XZ format expect
least-significant groups first. Freeze the malformed shape independently of
future encoder upgrades; never make ObtainX accept it.
"""
import hashlib
import io
import json
import lzma
from pathlib import Path
import struct
import tarfile
import unittest
import zlib

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / 'test/fixtures/r01_archives'
SMALL = b'test apk content'
LARGE = bytes((i * 31) % 251 for i in range(196608 + 37))


def xz_index(data):
    footer = len(data) - 12
    backward_size = (struct.unpack_from('<I', data, footer + 4)[0] + 1) * 4
    start = footer - backward_size
    assert data[-2:] == b'YZ' and data[start] == 0
    assert zlib.crc32(data[start:footer - 4]) == struct.unpack_from('<I', data, footer - 4)[0]
    return start, footer


def vli(value):
    encoded = bytearray()
    while value >= 128:
        encoded.append((value & 127) | 128)
        value >>= 7
    encoded.append(value)
    return bytes(encoded)


def read_tar(data, expected):
    decoded = lzma.decompress(data, format=lzma.FORMAT_XZ, memlimit=32 * 1024 * 1024)
    with tarfile.open(fileobj=io.BytesIO(decoded), mode='r:') as archive:
        assert archive.getnames() == ['nested/app.apk']
        member = archive.getmember('nested/app.apk')
        assert member.isfile() and member.size == len(expected)
        with archive.extractfile(member) as apk:
            assert apk.read() == expected
    return decoded


class Gap02Hf02XzFixtures(unittest.TestCase):
    def fixture(self, name):
        path = FIXTURES / name
        data = path.read_bytes()
        manifest = json.loads((ROOT / 'docs/R01_FIXTURE_SHA256.json').read_text())
        self.assertEqual(hashlib.sha256(data).hexdigest(), manifest['files'][name])
        return data

    def test_independent_valid_compressed_xz_fixtures(self):
        cases = [('hf02_nested_crc64.tar.xz', 4, SMALL)]
        cases += [(f'hf02_large_{name}.tar.xz', check, LARGE)
                  for name, check in [('crc32', 1), ('crc64', 4), ('sha256', 10)]]
        for name, check, expected in cases:
            with self.subTest(name=name):
                data = self.fixture(name)
                self.assertTrue(lzma.is_check_supported(check))
                self.assertEqual(data[7], check)
                # The first LZMA2 chunk must actually be compressed.
                self.assertGreaterEqual(data[12 + (data[12] + 1) * 4], 128)
                self.assertGreater(len(read_tar(data, expected)), len(data))
                xz_index(data)

    def test_original_encoder_index_defect_isolated(self):
        data = self.fixture('hf02_legacy_index.tar.xz')
        start, footer = xz_index(data)
        self.assertEqual(data[start:start + 6], bytes.fromhex('000190189000'))
        with self.assertRaises(lzma.LZMAError):
            read_tar(data, SMALL)
        # The unchanged TAR is 2048 bytes; the stored block unpadded extent
        # includes 12 header, 4 LZMA2 framing and 8 check bytes. Only replace
        # the two bad index VLIs and dependent CRC. No payload change.
        correct = bytearray(data)
        correct[start + 2:start + 6] = vli(2072) + vli(2048)
        correct[footer - 4:footer] = struct.pack('<I', zlib.crc32(correct[start:footer - 4]))
        self.assertEqual(correct[start:start + 6], bytes.fromhex('000198108010'))
        self.assertEqual(len(read_tar(bytes(correct), SMALL)), 2048)

    def test_block_check_corruption_has_valid_metadata_but_refuses(self):
        valid = self.fixture('hf02_large_crc64.tar.xz')
        bad = self.fixture('hf02_bad_block_check.tar.xz')
        start, footer = xz_index(valid)
        self.assertEqual(xz_index(bad), (start, footer))
        self.assertEqual(len(valid), len(bad))
        self.assertEqual([i for i, pair in enumerate(zip(valid, bad))
                          if pair[0] != pair[1]], [start - 1])
        self.assertEqual(valid[start - 1] ^ bad[start - 1], 1)
        read_tar(valid, LARGE)
        with self.assertRaises(lzma.LZMAError):
            read_tar(bad, LARGE)

    def test_required_flutter_paths_remain_wired(self):
        performance = (ROOT / 'test/performance_work_test.dart').read_text()
        security = (ROOT / 'test/archive_extraction_security_test.dart').read_text()
        self.assertIn('hf02_nested_crc64.tar.xz', performance)
        self.assertNotIn('archive.XZEncoder()', performance)
        self.assertIn('extractTarballOffIsolate(file.path', performance)
        for marker in ('hf02_large_$check.tar.xz', 'hf02_legacy_index.tar.xz',
                       'hf02_bad_block_check.tar.xz', 'hf02_large_crc64.tar.xz'):
            self.assertIn(marker, security)
        workflow = (ROOT / '.github/workflows/obtainx-r00-flutter.yml').read_text()
        self.assertIn('flutter test --no-pub test/archive_extraction_security_test.dart', workflow)
        self.assertIn('flutter test --no-pub', workflow)
