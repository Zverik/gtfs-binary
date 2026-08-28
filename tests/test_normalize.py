import unittest
from gtfs_binary import Trie, PackedTrie, pack_trie, normalize_name


class TestNormalizeName(unittest.TestCase):
    def test_case(self):
        self.assertEqual(normalize_name('King Ouest'), 'king ouest')

    def test_diacritics(self):
        # French, as in the Sherbrooke (STS) feed.
        self.assertEqual(
            normalize_name('Université de Sherbrooke'),
            'universite de sherbrooke')
        self.assertEqual(normalize_name('Place de la Cité'),
                         'place de la cite')
        self.assertEqual(normalize_name('Bibliothèque Éva -Senécal'),
                         'bibliotheque eva -senecal')

    def test_other_languages(self):
        # Estonian, Czech, German.
        self.assertEqual(normalize_name('Väike-Õismäe'), 'vaike-oismae')
        self.assertEqual(normalize_name('Václavské náměstí'),
                         'vaclavske namesti')
        self.assertEqual(normalize_name('Grünstraße'), 'grunstrasse')

    def test_idempotent(self):
        once = normalize_name('Séminaire-Collégial')
        self.assertEqual(normalize_name(once), once)

    def test_no_diacritics_unchanged(self):
        self.assertEqual(normalize_name('bowen - talbot'), 'bowen - talbot')


class TestNormalizedLookup(unittest.TestCase):
    """The index and the query must agree after normalization."""

    NAMES = [
        'Université de Sherbrooke',
        'Place de la Cité',
        'King Ouest / Belvédère Sud',
        'Séminaire de Sherbrooke',
    ]

    def setUp(self):
        t = Trie()
        t.populate([normalize_name(n) for n in self.NAMES])
        self.packed = PackedTrie(pack_trie(t))

    def find(self, query: str) -> list[int]:
        return list(self.packed.find(normalize_name(query)))

    def test_accented_query(self):
        self.assertEqual(self.find('Université'), [0])

    def test_unaccented_query(self):
        # The whole point: no accents on a phone keyboard.
        self.assertEqual(self.find('universite'), [0])

    def test_mixed_case_query(self):
        self.assertEqual(self.find('PLACE DE LA CITE'), [1])

    def test_partial_unaccented(self):
        self.assertEqual(self.find('king ouest / belvedere'), [2])

    def test_seminaire(self):
        self.assertEqual(self.find('seminaire'), [3])

    def test_miss_still_misses(self):
        self.assertEqual(self.find('carrefour'), [])


if __name__ == '__main__':
    unittest.main()
