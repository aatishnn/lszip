import unittest
import lszip

class HelpersTest(unittest.TestCase):
    def test_generate_range_header(self):
        header_range = lszip.generate_range_header()
        self.assertEqual(header_range, {'Range': 'bytes=0-'})

        header_range = lszip.generate_range_header(20, 40)
        self.assertEqual(header_range, {'Range': 'bytes=20-40'})

        header_range = lszip.generate_range_header(12)
        self.assertEqual(header_range, {'Range': 'bytes=12-'})

        header_range = lszip.generate_range_header(-20)
        self.assertEqual(header_range, {'Range': 'bytes=-20'})

if __name__ == '__main__':
    unittest.main()
