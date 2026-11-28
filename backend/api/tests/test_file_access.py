"""附件鉴权只按文件 ID 收窄候选，不把无关附件整表读进进程。"""

from sqlalchemy import JSON, BigInteger, Integer, MetaData, create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.errors import AppError
from app.models import Message, StoredFile, User, Workspace
from app.models import Session as AgentSession
from app.routers.files import _require_file_access

_MODELS = (User, Workspace, AgentSession, Message, StoredFile)


def _session():
    """最小 SQLite：去掉跨库外键，JSONB 换成 SQLite 能存的 JSON。"""
    metadata = MetaData()
    for model in _MODELS:
        table = model.__table__.to_metadata(metadata)
        for column in table.columns:
            if isinstance(column.type, JSONB):
                column.type = JSON()
            elif isinstance(column.type, BigInteger) and column.primary_key:
                column.type = Integer()
            column.foreign_keys.clear()
        table.constraints = {
            item for item in table.constraints if item.__class__.__name__ != "ForeignKeyConstraint"
        }
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _user(db, user_id: str) -> User:
    user = User(id=user_id, username=user_id, password_hash="x")
    db.add(user)
    return user


def _file(owner_id: str, file_id: str) -> StoredFile:
    return StoredFile(
        id=file_id,
        filename="note.txt",
        size_bytes=4,
        sha256="a" * 64,
        storage_path=f"/tmp/{file_id}",
        uploaded_by=owner_id,
    )


def test_file_access_matches_string_and_object_refs_only():
    """属主放行；成员只能靠自己可见会话里的精确 ID，前缀撞车和已删除会话都不算。"""
    db = _session()
    owner = _user(db, "owner")
    reader = _user(db, "reader")
    stranger = _user(db, "stranger")
    target = _file(owner.id, "file-1")
    decoy = _file(owner.id, "file-10")
    db.add_all([target, decoy])
    own_session = AgentSession(id="s-own", user_id=reader.id, visibility="private")
    private_session = AgentSession(id="s-private", user_id=reader.id, visibility="private")
    deleted_session = AgentSession(id="s-deleted", user_id=stranger.id, visibility="private")
    db.add_all([own_session, private_session, deleted_session])
    db.flush()
    deleted_session.deleted_at = own_session.created_at
    db.add_all([
        Message(session_id=own_session.id, role="user", content="a", attachments=["file-10"], source_id="m1"),
        Message(
            session_id=private_session.id, role="user", content="b",
            attachments=[{"file_id": "file-1"}], source_id="m2",
        ),
        Message(session_id=deleted_session.id, role="user", content="d", attachments=["file-1"], source_id="m4"),
    ])
    db.commit()

    _require_file_access(db, owner, target)
    _require_file_access(db, reader, target)
    try:
        _require_file_access(db, stranger, target)
    except AppError as exc:
        assert exc.code.value == "NOT_FOUND"
    else:
        raise AssertionError("他人私有会话中的附件不能凭文件 ID 读取")
    db.close()
