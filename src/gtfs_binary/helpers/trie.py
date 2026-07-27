import itertools
from dataclasses import dataclass
from typing import Generator
from .. import gtfs_binary_pb2 as g


class Node:
    def __init__(self, values: list[int]) -> None:
        self.values = values
        self.children: dict[bytes, "Node"] = {}
        self.packed_index: int | None = None

    def find(self, prefix: bytes) -> tuple[Node | None, int]:
        for p, node in self.children.items():
            if prefix.startswith(p):
                return node, len(p)
            if p.startswith(prefix):
                return node, len(prefix)
        return None, 0

    def all_values(self) -> Generator[int]:
        for v in self.values:
            yield v
        for c in self.children.values():
            yield from c.all_values()

    def count_values(self) -> int:
        return len(self.values) + sum(
            c.count_values() for c in self.children.values())

    def all_nodes(self, edge: bytes = b'') -> Generator[tuple[bytes, Node]]:
        yield edge, self
        for prefix, node in self.children.items():
            yield from node.all_nodes(prefix)

    def which_child(self, search: bytes) -> tuple[Node, bytes]:
        for p, node in self.children.items():
            if search.startswith(p):
                return node, search[len(p):]
        return self, search

    def insert(self, prefix: bytes, value: int) -> None:
        if not prefix:
            self.values.append(value)
            return
        for p, node in self.children.items():
            if p[0] == prefix[0]:
                # We have found a common prefix: split and insert.
                plen = 1
                while (plen < len(prefix) and plen < len(p)
                       and prefix[plen] == p[plen]):
                    plen += 1
                intermediate = Node([])
                intermediate.children[p[plen:]] = node
                if plen == len(prefix):
                    intermediate.values.append(value)
                else:
                    intermediate.children[prefix[plen:]] = Node([value])
                self.children[p[:plen]] = intermediate
                del self.children[p]
                return
        self.children[prefix] = Node([value])

    def __repr__(self) -> str:
        return f'Node({self.values}, {self.children})'

    def __eq__(self, other) -> bool:
        return self.values == other.values and self.children == other.children


class Trie:
    def __init__(self, values: list[str] | None = None) -> None:
        self.clear()
        if values:
            self.populate(values)

    def clear(self) -> None:
        self.root = Node([])

    def add(self, key: str, value: int) -> None:
        byte_key = key.encode()
        node = self.root
        while True:
            nxt, remainder = node.which_child(byte_key)
            byte_key = remainder
            if nxt == node:
                break
            node = nxt
        node.insert(byte_key, value)

    def populate(self, values: list[str]) -> None:
        for i, value in enumerate(values):
            self.add(value, i)

    def find(self, prefix: str) -> list[int]:
        byte_prefix = prefix.encode()
        pos = 0
        node = self.root
        while pos < len(byte_prefix):
            nxt, plen = node.find(byte_prefix[pos:])
            if not nxt:
                return []
            node = nxt
            pos += plen
        return list(node.all_values())

    def __str__(self) -> str:
        return str(self.root)

    def __eq__(self, other) -> bool:
        return self.root == other.root


@dataclass
class PackedNode:
    edge_offset: int
    edge_count: int
    ids_offset: int
    ids_count: int


@dataclass
class PackedEdge:
    label_offset: int
    label_length: int
    node_index: int


def pack_trie(trie: Trie) -> g.StopLookup:
    values: list[int] = []
    string: bytes = b''
    nodes: list[PackedNode] = []
    edges: list[PackedEdge] = []

    edge_nodes: list[Node] = []

    for _, node in trie.root.all_nodes():
        node.packed_index = len(nodes)
        nodes.append(PackedNode(
            edge_offset=0 if not node.children else len(edges),
            edge_count=len(node.children),
            ids_offset=len(values),
            ids_count=node.count_values(),
        ))
        values.extend(node.values)

        for prefix, subnode in node.children.items():
            pos = string.find(prefix)
            edge_nodes.append(subnode)
            edges.append(PackedEdge(
                label_offset=pos if pos >= 0 else len(string),
                label_length=len(prefix),
                node_index=-1,
            ))
            if pos < 0:
                string += prefix

    for i, node in enumerate(edge_nodes):
        if node.packed_index is None:
            raise ValueError('Node has an unset index')
        edges[i].node_index = node.packed_index

    return g.StopLookup(
        string_blob=string,
        stop_ids=values,
        nodes=list(itertools.chain.from_iterable(
            [n.edge_offset, n.edge_count, n.ids_offset, n.ids_count]
            for n in nodes)),
        edges=list(itertools.chain.from_iterable(
            [e.label_offset, e.label_length, e.node_index]
            for e in edges)),
    )


class PackedTrie:
    def __init__(self, trie: g.StopLookup) -> None:
        self.trie = trie

    def find(self, search: str) -> list[int]:
        if not search:
            return []
        sb = search.encode()
        node = 0
        while sb:
            found = False
            for edge_idx in range(self.trie.nodes[node+1]):
                edge = (self.trie.nodes[node] + edge_idx) * 3
                p_start = self.trie.edges[edge]
                prefix = self.trie.string_blob[
                    p_start:p_start+self.trie.edges[edge+1]]
                if prefix.startswith(sb) or sb.startswith(prefix):
                    node = self.trie.edges[edge+2] * 4
                    sb = sb[min(len(sb), len(prefix)):]
                    found = True
                    break
            if not found:
                return []

        first_stop = self.trie.nodes[node+2]
        return self.trie.stop_ids[
            first_stop:first_stop + self.trie.nodes[node+3]]
