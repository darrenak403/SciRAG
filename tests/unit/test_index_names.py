import uuid

from scirag.index.qdrant_index import chunks_collection, papers_collection, point_id

PAPER = uuid.UUID("01890000-0000-7000-8000-000000000001")


def test_the_same_chunk_always_gets_the_same_point_id():
    assert point_id(PAPER, 3, 1) == point_id(PAPER, 3, 1)


def test_point_ids_differ_by_paper_chunk_and_chunking_version():
    other = uuid.UUID("01890000-0000-7000-8000-000000000002")
    ids = {
        point_id(PAPER, 3, 1),
        point_id(PAPER, 4, 1),
        point_id(PAPER, 3, 2),
        point_id(other, 3, 1),
    }
    assert len(ids) == 4


def test_each_embedding_model_and_size_has_its_own_collection():
    name = chunks_collection("amazon.titan-embed-text-v2:0", 1024)
    assert name.startswith("chunks__amazon-titan-embed-text-v2-0-")
    assert name.endswith("__1024__v1")
    assert chunks_collection("m", 768) != chunks_collection("m", 1024)
    # Names that differ only in punctuation still get separate collections.
    assert chunks_collection("org/model", 768) != chunks_collection("org-model", 768)
    assert papers_collection("chunks__m__768__v1") == "papers__m__768__v1"
