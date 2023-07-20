import warnings
from pathlib import Path
from typing import Dict, List, Union
import pickle
from rocksdict import Options, Rdict, ReadOptions, WriteBatch, WriteOptions


class DocStorage:
    """The backend storage engine of Documents"""

    def __init__(
        self,
        path: Union[str, Path],
        create_if_missing: bool = True,
        **kwargs,
    ):
        self._path = str(path)

        self._kwargs = kwargs

        self._init_db(create_if_missing=create_if_missing, **self._kwargs)

    def _init_db(self, create_if_missing: bool = True, **kwargs):
        opt = Options(raw_mode=True)

        opt.optimize_for_point_lookup(1024)

        opt.set_inplace_update_support(True)
        opt.set_allow_concurrent_memtable_write(False)

        # configure mem-table to a large value (256 MB)
        opt.set_write_buffer_size(0x10000000)

        # 256 MB file size
        opt.set_target_file_size_base(0x10000000)

        # # set to plain-table for better performance
        # opt.set_plain_table_factory(PlainTableFactoryOptions())

        opt.create_if_missing(create_if_missing)

        self._db = Rdict(path=self._path, options=opt)

        # get the size of the database, if it is not created, set it to 0
        self._size = len(list(self._db.keys()))

        self._is_closed = False

    def insert(self, docs: 'List'):
        write_batch = WriteBatch(raw_mode=True)
        write_opt = WriteOptions()
        write_opt.sync = True
        batch_size = 0
        for doc in docs:
            #TODO: How to serialize a dict
            #write_batch.put(doc.id.encode(), doc.to_bytes(**self._serialize_config))
            write_batch.put(doc['id'].encode(), pickle.dumps(doc))
            batch_size += 1
        self._db.write(write_batch, write_opt=write_opt)
        self._size += batch_size

    def update(self, docs: 'List'):
        write_batch = WriteBatch(raw_mode=True)
        write_opt = WriteOptions()
        write_opt.sync = True
        for doc in docs:
            key = doc['id'].encode()
            if key not in self._db:
                raise ValueError(f'The Doc ({doc["id"]}) does not exist in database!')

            #write_batch.put(key, doc.to_bytes(**self._serialize_config))
            # TODO: Serialize
            write_batch.put(key, pickle.dumps(doc))
        self._db.write(write_batch, write_opt=write_opt)

    def delete(self, doc_ids: List[str]):
        write_batch = WriteBatch(raw_mode=True)
        write_opt = WriteOptions()
        write_opt.sync = True
        for doc_id in doc_ids:
            write_batch.delete(doc_id.encode())
        self._db.write(write_batch, write_opt=write_opt)
        self._size -= len(doc_ids)

    def get(self, doc_ids: Union[str, list]) -> List:
        docs = []
        if isinstance(doc_ids, str):
            doc_ids = [doc_ids]

        for doc_bytes in self._db[[k.encode() for k in doc_ids]]:
            if doc_bytes:
                #docs.append(Document.from_bytes(doc_bytes, **self._serialize_config))
                # TODO: Deserialize
                docs.append(pickle.loads(doc_bytes))

        return docs

    def clear(self):
        if self._is_closed:
            warnings.warn(
                '`DocStorage` had been closed already, will skip this close operation.'
            )
        else:
            self._db.close()
        self._db.destroy(self._path)

        # re-initialize the database for the next usage
        self._init_db(create_if_missing=True, **self._kwargs)

    def close(self):
        if self._is_closed:
            warnings.warn(
                '`DocStorage` had been closed already, will skip this close operation.'
            )
            return
        try:
            self._db.flush(wait=True)
            self._db.close()
        except Exception as ex:
            if 'No such file or directory' not in str(ex):
                # this is a known bug, we can safely ignore it
                raise ex
        self._is_closed = True

    def __len__(self):
        return self._size

    @property
    def stat(self):
        return {'entries': len(self)}

    @property
    def size(self):
        return self.stat['entries']

    @property
    def last_transaction_id(self):
        return self._db.latest_sequence_number()

    def batched_iterator(self, batch_size: int = 1, **kwargs) -> 'List':
        count = 0
        docs = []

        read_opt = ReadOptions()

        for value in self._db.values(read_opt=read_opt):
            #doc = Document.from_bytes(value, **self._serialize_config)
            #TODO: Deserialize
            docs.append(pickle.loads(value))
            count += 1

            if count == batch_size:
                yield docs
                count = 0
                docs = []

        if count > 0:
            yield docs
