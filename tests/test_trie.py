import unittest
from gtfs_binary import Trie, PackedTrie, pack_trie


class TestTrie(unittest.TestCase):
    def test_trie(self):
        t = Trie()
        t.add('test', 1)
        t.add('teist', 2)
        t.add('teine', 3)
        t.add('tei', 4)

        self.assertEqual(len(t.root.children), 1, str(t.root))
        te = t.root.children.get(b'te')
        self.assertIsNotNone(te, str(t.root))
        self.assertEqual(len(te.children), 2, str(te))
        tei = te.children.get(b'i')
        self.assertIsNotNone(tei, str(te))
        self.assertEqual(len(tei.children), 2, str(tei))

        self.assertEqual(t.find('test'), [1])
        self.assertEqual(t.find('tes'), [1])
        self.assertEqual(t.find('teine'), [3])
        self.assertEqual(t.find('tein'), [3])
        self.assertEqual(set(t.find('tei')), set([2, 3, 4]))
        self.assertEqual(set(t.find('te')), set([1, 2, 3, 4]))
        self.assertEqual(set(t.find('t')), set([1, 2, 3, 4]))

    def test_populate(self):
        t = Trie()
        t.add('test', 0)
        t.add('teist', 1)
        t.add('teine', 2)
        t.add('tei', 3)

        tp = Trie()
        tp.populate(['test', 'teist', 'teine', 'tei'])

        self.assertEqual(t, tp)

    def test_dfs(self):
        t = Trie()
        t.populate(['abc', 'abd', 'abcd', 'abcde', 'abde', 'bac'])
        self.assertEqual(list(t.root.all_values()), [0, 2, 3, 1, 4, 5])

    def test_packed(self):
        t = Trie()
        t.add('test', 1)
        t.add('teist', 2)
        t.add('teine', 3)
        t.add('tei', 4)
        p = PackedTrie(pack_trie(t))

        self.assertEqual(p.find('test'), [1], p)
        self.assertEqual(p.find('tes'), [1], p)
        self.assertEqual(p.find('teine'), [3], p)
        self.assertEqual(p.find('tein'), [3], p)
        self.assertEqual(set(p.find('tei')), set([2, 3, 4]), p)
        self.assertEqual(set(p.find('te')), set([1, 2, 3, 4]), p)
        self.assertEqual(set(p.find('t')), set([1, 2, 3, 4]), p)


if __name__ == '__main__':
    unittest.main()
