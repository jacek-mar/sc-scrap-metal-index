"""v0.3 generator: strings-only TPAK reader, Steam lookup, snapshot, errors (synthetic data only)."""
import io
import json
import struct
import tempfile
import unittest
import zlib
from contextlib import redirect_stderr
from pathlib import Path

from sc_smi_gen import compare, steam
from sc_smi_gen.__main__ import main
from sc_smi_gen.make_snapshot import reduce
from sc_smi_gen.tpak import Pak, PakError, extract_strings


def deflate(data):
    c = zlib.compressobj(9, zlib.DEFLATED, -15)
    return c.compress(data) + c.flush()


def xor_first(blob, key):
    return struct.pack('<I', struct.unpack_from('<I', blob)[0] ^ (key & 0xFFFFFFFF)) + blob[4:]


def pad4(b):
    return b + b'\0' * (-len(b) % 4)


def make_pak(files, chunk=None):
    """Write a TPAK v7 file from the public format description (test helper)."""
    names = list(files)
    n = len(names)
    register, offsets = b'', []
    for idx, name in enumerate(names):
        raw = name.encode()
        k = (len(raw) % 5 + idx) & 0xFF
        offsets.append(len(register) + 4)
        register += struct.pack('<I', len(raw)) + bytes(b ^ ((2 * (j + len(raw)) + k) & 0xFF) for j, b in enumerate(raw)) + b'\0'
    data, chunks, table = b'', [], b''
    for i, name in enumerate(names):
        content = files[name]
        pieces = [content[p:p + chunk] for p in range(0, len(content), chunk)] if chunk else [content]
        first = len(chunks)
        for p_index, piece in enumerate(pieces):
            stored = deflate(piece) if p_index % 2 == 0 else piece  # mix compressed and stored chunks
            chunks.append((sum(len(x) for x in pieces[:p_index]), len(piece), len(data), len(stored)))
            data += stored
        table += struct.pack('<4I', len(content), offsets[i], len(pieces), first)
    c1 = deflate(register); c2 = deflate(table)
    chunk_table = b''.join(struct.pack('<4I', *c) for c in chunks); c3 = deflate(chunk_table)
    m = len(chunks)
    out = struct.pack('<7I', 0x4B415054, 7, 0, n, 0xFFFFFFE3, len(register), len(c1)) + xor_first(c1, n)
    out = pad4(out) + struct.pack(f'<{n}I', *sorted(range(n), key=lambda i: names[i]))
    out += struct.pack('<I', len(c2)) + xor_first(c2, len(c2) + n)
    out = pad4(out) + struct.pack('<2I', len(c3), m) + xor_first(c3, m + len(c3) + n)
    return pad4(out) + data


class TpakTest(unittest.TestCase):
    files = {'strings\\english\\string.txt': '"a"\t"Alpha"\n'.encode() * 50,
             'strings\\russian\\string.txt': '"a"\t"Альфа"\n'.encode() * 50,
             'fonts\\font.tfd': b'\x00\x01binary'}

    def test_lists_and_reads_multi_chunk_entries(self):
        pak = Pak(make_pak(self.files, chunk=64))
        self.assertEqual(pak.names(), sorted(k.lower() for k in self.files))
        for name, content in self.files.items():
            self.assertEqual(pak.read(name), content)

    def test_extracts_only_the_two_string_tables(self):
        with tempfile.TemporaryDirectory() as tmp:
            pak = Path(tmp) / 'strings.pak'; pak.write_bytes(make_pak(self.files))
            written = extract_strings(pak, Path(tmp) / 'out')
            self.assertEqual(sorted(p.relative_to(Path(tmp) / 'out').as_posix() for p in written),
                             ['english/string.txt', 'russian/string.txt'])
            self.assertFalse(any((Path(tmp) / 'out').rglob('*.tfd')))
            self.assertEqual((Path(tmp) / 'out/russian/string.txt').read_bytes(), self.files['strings\\russian\\string.txt'])

    def test_rejects_other_files_and_missing_tables(self):
        with self.assertRaises(PakError):
            Pak(b'PK\x03\x04' + b'\0' * 40)
        with tempfile.TemporaryDirectory() as tmp:
            pak = Path(tmp) / 'strings.pak'; pak.write_bytes(make_pak({'fonts\\font.tfd': b'x'}))
            with self.assertRaises(PakError):
                extract_strings(pak, Path(tmp) / 'out')


class SteamTest(unittest.TestCase):
    def test_library_folders_both_formats(self):
        new = '"libraryfolders"\n{\n\t"0"\n\t{\n\t\t"path"\t\t"C:\\\\Program Files (x86)\\\\Steam"\n\t}\n\t"1"\n\t{\n\t\t"path"\t\t"D:\\\\SteamLibrary"\n\t}\n}'
        old = '"LibraryFolders"\n{\n\t"TimeNextStatsReport"\t\t"1"\n\t"1"\t\t"E:\\\\Games\\\\Steam"\n}'
        self.assertEqual([str(p) for p in steam.libraries(new)][-1].replace('/', '\\'), 'D:\\SteamLibrary')
        self.assertEqual([str(p).replace('/', '\\') for p in steam.libraries(old)], ['E:\\Games\\Steam'])


class SnapshotTest(unittest.TestCase):
    def test_keeps_item_references_and_drops_the_rest(self):
        doc = {'_id': {'$oid': 'x'}, 'uid': {'$numberLong': '2'}, 'nickName': 'someone', 'credits': 5,
               'items': [{'iid': 7, 'defName': 'Module_A', 'amount': 3}, {'iid': 8, 'defName': 'Weapon_B'}],
               'vessels': [{'vid': 1, 'defName': 'Ship_C', 'equipped': [7, 0], 'hullCondition': 1.0}],
               'craftResources': {'Res_D': 4}, 'auras': []}
        kept = reduce(doc, '', True)[1]
        self.assertEqual(kept, {'uid': {'$numberLong': '2'}, 'items': [{'iid': 7, 'defName': 'Module_A'}, {'iid': 8, 'defName': 'Weapon_B'}],
                                'vessels': [{'vid': 1, 'defName': 'Ship_C', 'equipped': [7, 0]}],
                                'craftResources': {'Res_D': 4}, 'auras': []})

    def test_bundled_snapshot_has_no_names_or_addresses(self):
        sample = Path(__file__).resolve().parent.parent / 'sc_smi_gen' / 'sample'
        text = ''.join(p.read_text(encoding='utf-8') for p in sample.rglob('*.json'))
        self.assertTrue(text)
        for needle in ('nickName', 'username', 'password', 'test_user', '192.0.2.', '$oid'):
            self.assertNotIn(needle, text)
        for p in sample.rglob('*.json'):
            for line in p.read_text(encoding='utf-8').splitlines():
                json.loads(line)


class CliTest(unittest.TestCase):
    def test_clear_error_for_a_wrong_folder(self):
        with tempfile.TemporaryDirectory() as tmp, redirect_stderr(io.StringIO()) as err:
            self.assertEqual(main(['--gamedir', tmp, '--out', str(Path(tmp) / 'o')]), 1)
        self.assertIn('does not look like a Star Conflict install', err.getvalue())
        self.assertNotIn('Traceback', err.getvalue())

    def test_compare_ignores_only_the_generation_date(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = Path(tmp) / 'a', Path(tmp) / 'b'
            for root, date in ((a, '2026-01-01'), (b, '2026-02-02')):
                (root / 'data').mkdir(parents=True)
                (root / 'data/manifest.json').write_text(json.dumps({'generated_at': date, 'files': 1}))
                (root / 'data/x.csv').write_text('same')
            self.assertEqual(compare.compare(a, b), [])
            (b / 'data/x.csv').write_text('changed')
            self.assertEqual(compare.compare(a, b), ['differs: data/x.csv'])


if __name__ == '__main__':
    unittest.main()
