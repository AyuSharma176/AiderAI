from sqlalchemy import inspect

from app.models import (
    AgentExecutionLog,
    Conversation,
    Document,
    DocumentChunk,
    Order,
    Ticket,
    User,
)


def test_entities_use_uuid_primary_keys() -> None:
    for model in (
        User,
        Conversation,
        Document,
        DocumentChunk,
        Order,
        Ticket,
        AgentExecutionLog,
    ):
        primary_key = inspect(model).primary_key
        assert len(primary_key) == 1
        assert primary_key[0].name == "id"
        assert primary_key[0].type.python_type.__name__ == "UUID"


def test_document_embedding_dimension_and_indexes() -> None:
    assert DocumentChunk.__table__.c.embedding.type.dim == 768
    index_names = {index.name for index in DocumentChunk.__table__.indexes}
    assert "ix_document_chunks_embedding_hnsw" in index_names


def test_owned_records_reference_users() -> None:
    assert Conversation.__table__.c.user_id.foreign_keys
    assert Order.__table__.c.user_id.foreign_keys
    assert Ticket.__table__.c.user_id.foreign_keys

