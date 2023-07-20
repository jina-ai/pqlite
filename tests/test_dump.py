import numpy as np
import pytest

from annlite import AnnLite

np.random.seed(123456)

D = 50
N = 1000


@pytest.fixture
def index_data():
    index_data = []
    for i in range(N):
        index_data.append(dict(id=str(i)))
    half_embedding = np.random.random((N, D))
    for data, embedding in zip(index_data, half_embedding):
        data['embedding'] = embedding
    return index_data


def test_dump_load(tmpfile, index_data):
    query = index_data[0:1]

    index = AnnLite(D, data_path=tmpfile)
    index.index(index_data)
    matches = index.search(query, limit=10)
    gt = [m['id'] for m in matches[0]]
    index.dump()
    index.close()

    new_index = AnnLite(D, data_path=tmpfile)
    matches = new_index.search(query, limit=10)
    new_gt = [m['id'] for m in matches[0]]
    assert len(set(gt) & set(new_gt)) / len(gt) == 1.0
    new_index.close()

    new_index = AnnLite(D, n_components=D // 2, data_path=tmpfile)
    matches = new_index.search(query, limit=10)
    new_gt = [m['id'] for m in matches[0]]
    assert len(set(gt) & set(new_gt)) / len(gt) > 0.6
