import unicodedata


def normalize_name(name: str) -> str:
    """Normalizes a stop or route name for the search index.

    Search keys in the `stop_by_name` trie are stored normalized, so that
    a user typing "universite" finds "Université de Sherbrooke". Feeds in
    French, Estonian, German, Czech and so on carry diacritics that nobody
    reliably types into a phone keyboard.

    The transformation is: NFKD decomposition, drop the combining marks,
    then casefold. Readers MUST apply the exact same function to a query
    before searching the trie, otherwise the index and the query disagree.
    """
    decomposed = unicodedata.normalize('NFKD', name)
    stripped = ''.join(c for c in decomposed if not unicodedata.combining(c))
    return stripped.casefold()
