from collections.abc import Generator
from contextlib import contextmanager
from csv import DictReader
from io import TextIOWrapper
from typing import TextIO
from zipfile import ZipFile


class GtfsHelper:
    def __init__(self, z: ZipFile):
        self.z = z

    def has_file(self, name_part: str) -> bool:
        return f'{name_part}.txt' in self.z.namelist()

    @contextmanager
    def open_table(self, name_part: str):
        with self.z.open(f'{name_part}.txt', 'r') as f:
            yield TextIOWrapper(f, encoding='utf-8-sig')

    def table_reader(self, fileobj: TextIO, id_column: str,
                     ) -> Generator[tuple[dict, str], None, None]:
        """Iterates over CSV rows and returns (row, our_id, source_id)."""
        for row in DictReader(fileobj):
            yield (
                {k: v.strip() for k, v in row.items()},
                row[id_column],
            )

    def sequence_reader(self, fileobj: TextIO, id_column: str,
                        seq_column: str,
                        max_overlapping: int = 20,
                        ) -> Generator[tuple[list[dict], str], None, None]:
        cur_ids: list[str] = []
        cur_lists: list[list[tuple[int, str, dict]]] = []
        seen_ids: set[str] = set()

        for row, row_id in self.table_reader(fileobj, id_column):
            # Find the row_id index. From the tail, because latest ids are appended there.
            idx = len(cur_ids) - 1
            while idx >= 0 and cur_ids[idx] != row_id:
                idx -= 1

            if idx < 0:
                # Not found: dump the oldest sequence and add the new one.
                if row_id in seen_ids:
                    raise ValueError(
                        f'Unsorted sequence file, {id_column} {row_id} is in two parts')
                seen_ids.add(row_id)

                if len(cur_ids) >= max_overlapping:
                    last_id = cur_ids.pop(0)
                    last_rows = cur_lists.pop(0)
                    last_rows.sort(key=lambda r: r[0])
                    yield [r[2] for r in last_rows], last_id

                cur_ids.append(row_id)
                cur_lists.append([])
                idx = len(cur_ids) - 1

            cur_lists[idx].append((int(row[seq_column]), row_id, row))

        for i, row_id in enumerate(cur_ids):
            rows = cur_lists[i]
            rows.sort(key=lambda r: r[0])
            yield [r[2] for r in rows], row_id
