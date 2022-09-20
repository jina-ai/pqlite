from pathlib import Path
from typing import Dict, List, Union

from docarray import Document, DocumentArray
from rocksdict import Options, Rdict, ReadOptions, WriteBatch, WriteOptions


class DocStorage:
    """The backend storage engine of Documents"""

    def __init__(
        self,
        path: Union[str, Path],
        serialize_config: Dict = {},
        create_if_missing: bool = True,
        **kwargs,
    ):
        self._path = path

        opt = Options(raw_mode=True)
        opt.set_inplace_update_support(True)
        opt.set_allow_concurrent_memtable_write(False)

        # configure mem-table to a large value (256 MB)
        opt.set_write_buffer_size(0x10000000)
        # # set to plain-table for better performance
        # opt.set_plain_table_factory(PlainTableFactoryOptions())

        opt.create_if_missing(create_if_missing=create_if_missing)
        self._db = Rdict(path=str(path), options=opt)
        self._serialize_config = serialize_config

        self._size = len(list(self._db.keys()))

    def insert(self, docs: 'DocumentArray'):
        write_batch = WriteBatch(raw_mode=True)
        write_opt = WriteOptions()
        write_opt.set_sync(True)
        batch_size = 0
        for doc in docs:
            write_batch.put(doc.id.encode(), doc.to_bytes(**self._serialize_config))
            batch_size += 1
        self._db.write(write_batch, write_opt=write_opt)
        self._size += batch_size

    def update(self, docs: 'DocumentArray'):
        write_batch = WriteBatch(raw_mode=True)
        write_opt = WriteOptions()
        write_opt.set_sync(True)
        for doc in docs:
            key = doc.id.encode()
            if key not in self._db:
                raise ValueError(f'The Doc ({doc.id}) does not exist in database!')

            write_batch.put(key, doc.to_bytes(**self._serialize_config))
        self._db.write(write_batch, write_opt=write_opt)

    def delete(self, doc_ids: List[str]):
        for doc_id in doc_ids:
            del self._db[doc_id.encode()]

    def get(self, doc_ids: Union[str, list]) -> DocumentArray:
        docs = DocumentArray()
        if isinstance(doc_ids, str):
            doc_ids = [doc_ids]

        for doc_bytes in self._db[[k.encode() for k in doc_ids]]:
            if doc_bytes:
                docs.append(Document.from_bytes(doc_bytes, **self._serialize_config))

        return docs

    def clear(self):
        self._size = 0
        self._db.close()
        self._db.destroy(str(self._path))

    def close(self):
        self._db.close()

    def __len__(self):
        return self._size

    @property
    def stat(self):
        return {'entries': len(self)}

    @property
    def size(self):
        return self.stat['entries']

    def batched_iterator(self, batch_size: int = 1, **kwargs):
        count = 0
        docs = DocumentArray()

        read_opt = ReadOptions(raw_mode=True)

        for value in self._db.values(read_opt=read_opt):
            doc = Document.from_bytes(value, **self._serialize_config)
            docs.append(doc)
            count += 1

            if count == batch_size:
                yield docs
                count = 0
                docs = DocumentArray()

        if count > 0:
            yield docs
