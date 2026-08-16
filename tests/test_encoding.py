import unittest
from gtfs_binary import encoding as e
from gtfs_binary import decoding as d


class TestEncoding(unittest.TestCase):
    def test_encode(self):
        self.assertEqual(e.pack_string('abc'), b'\x03abc')
        self.assertEqual(e.pack_string(''), b'\x00')
        self.assertEqual(
            e.pack_strings(['abc', '12']), b'\x03abc\x0212')
        self.assertEqual(
            e.pack_strings_common(['abc', '12']), b'\x03abc\x0212')
        self.assertEqual(
            e.pack_strings_common(['abc', 'abd']), b'\x03abc\x81\x01d')

        self.assertEqual(
            e.pack_1bit([True] * 4 + [False] * 4 + [True]),
            b'\xF0\x80')
        self.assertEqual(
            e.pack_2bit([3, 2, 1, 0, 2]), b'\xE4\x80')

        self.assertEqual(e.pack_uint(0), b'\x00')
        self.assertEqual(e.pack_uint(127), b'\x7f')
        self.assertEqual(e.pack_uint(128), b'\x80\x01')
        self.assertEqual(e.pack_uint(129), b'\x81\x01')

        self.assertEqual(e.pack_sint(0), b'\x00')
        self.assertEqual(e.pack_sint(-1), b'\x01')
        self.assertEqual(e.pack_sint(1), b'\x02')
        self.assertEqual(e.pack_sint(64), b'\x80\x01')
        self.assertEqual(e.pack_sint(-65), b'\x81\x01')

        self.assertEqual(e.pack_uints([1, 2, 129]), b'\x01\x02\x81\x01')
        self.assertEqual(e.pack_uints([1, 2, 129], add_len=True),
                         b'\x03\x01\x02\x81\x01')
        self.assertEqual(e.pack_sints([1, 2, -65]), b'\x02\x04\x81\x01')
        self.assertEqual(e.pack_sints([1, 2, -65], add_len=True),
                         b'\x03\x02\x04\x81\x01')

        self.assertEqual(e.pack_uints_delta([100, 102, 120, 300]),
                         b'\x64\x02\x12\xb4\x01')
        self.assertEqual(e.pack_uints_delta([100, 102, 120, 300], start=99),
                         b'\x01\x02\x12\xb4\x01')
        self.assertEqual(e.pack_sints_delta([100, 98, 120, -60]),
                         b'\xc8\x01\x03\x2c\xe7\x02')
        self.assertEqual(e.pack_sints_delta([100, 98, 120, -60], start=99),
                         b'\x02\x03\x2c\xe7\x02')

        self.assertEqual(e.pack_bytes_rle(b''), b'')
        self.assertEqual(e.pack_bytes_rle(b'112'), b'\x001\xff2')
        self.assertEqual(e.pack_bytes_rle(b'1'*130+b'ab'*64),
                         b'\x7f1\x801' + b'ab'*63 + b'a\xffb')
        self.assertEqual(e.pack_uints_rle([2, 1, 1, 1, 19, 20]),
                         b'\xff\x02\x01\x01\xfe\x13\x14')
        self.assertEqual(e.pack_strings_rle(['abc', '12', '12']),
                         b'\xff\x03abc\x00\x0212')

    def test_encode_decode(self):
        p1 = e.pack_string('abc')
        self.assertEqual(d.unpack_string(p1, 0), ('abc', len(p1)))
        self.assertEqual(d.unpack_string(b'1' + p1, 1), ('abc', len(p1)+1))
        p2 = e.pack_strings(['abc', '12'])
        self.assertEqual(d.unpack_strings(b'1' + p2, 1, 2),
                         (['abc', '12'], 1+len(p2)))

        s1 = ['abc', 'abdc', '12']
        ps1 = e.pack_strings_common(s1)
        self.assertEqual(
            d.unpack_strings_common(b'1'+ps1, 1, len(s1)), (s1, 1+len(ps1)))

        bits = [True] * 4 + [False] * 4 + [True]
        p3 = e.pack_1bit(bits)
        self.assertEqual(d.unpack_1bit(b'1'+p3, 1, 9), (bits, 1+len(p3)))
        bits2 = [3, 2, 1, 0, 2]
        p4 = e.pack_2bit(bits2)
        self.assertEqual(d.unpack_2bit(b'1'+p4, 1, 5), (bits2, 1+len(p4)))

        self.assertEqual(d.unpack_uint(e.pack_uint(0), 0), (0, 1))
        self.assertEqual(d.unpack_uint(b'1'+e.pack_uint(127), 1), (127, 2))
        self.assertEqual(d.unpack_uint(e.pack_uint(128), 0), (128, 2))

        self.assertEqual(d.unpack_sint(e.pack_sint(0), 0), (0, 1))
        self.assertEqual(d.unpack_sint(e.pack_sint(-1), 0), (-1, 1))
        self.assertEqual(d.unpack_sint(b'1'+e.pack_sint(1), 1), (1, 2))
        self.assertEqual(d.unpack_sint(e.pack_sint(64), 0), (64, 2))
        self.assertEqual(d.unpack_sint(e.pack_sint(-65), 0), (-65, 2))

        p5 = e.pack_bytes_rle(b'112')
        self.assertEqual(d.unpack_bytes_rle(b'1'+p5, 1, 3),
                         (b'112', 1+len(p5)))
        rle2 = [2, 1, 1, 1, 19, 20]
        p6 = e.pack_uints_rle(rle2)
        self.assertEqual(d.unpack_uints_rle(b'1'+p6, 1, len(rle2)),
                         (rle2, 1+len(p6)))
        rle3 = ['abc', '12', '12']
        p7 = e.pack_strings_rle(rle3)
        self.assertEqual(d.unpack_strings_rle(b'1'+p7, 1, len(rle3)),
                         (rle3, 1+len(p7)))


if __name__ == '__main__':
    unittest.main()
