"""适配层内部契约单测：来源标识、状态映射与检索结果映射（无需 LightRAG 引擎）。"""

import pytest
from adapter.contract import (
    MAX_GRAPH_NODES,
    STATUS_FAILED,
    STATUS_INDEXED,
    STATUS_INDEXING,
    belongs_to_kb,
    build_file_source,
    chunk_top_k_for,
    map_chunks,
    map_engine_status,
    map_graph,
    parse_doc_ids,
    parse_file_source,
    sanitize_filename,
)


def test_file_source_roundtrip():
    """来源标识必须可无损还原出知识库 ID、文档 ID 与文件名。"""
    source = build_file_source("kb-1", "doc-a", "产品手册 v2.pdf")

    assert source == "kb-1__doc-a__产品手册 v2.pdf"
    assert parse_file_source(source) == ("kb-1", "doc-a", "产品手册 v2.pdf")


def test_file_source_strips_path_separators():
    """文件名中的路径分隔符被收敛，避免破坏三段结构（LightRAG 只保留 basename）。"""
    source = build_file_source("kb-1", "doc-a", "../etc/passwd")

    assert source == "kb-1__doc-a__.._etc_passwd"
    assert parse_file_source(source) == ("kb-1", "doc-a", ".._etc_passwd")


def test_build_file_source_rejects_separator_in_ids():
    """ID 里出现分隔符会让三段结构静默切错，构造函数必须直接拒绝。"""
    with pytest.raises(ValueError):
        build_file_source("kb__1", "doc-a", "a.txt")
    with pytest.raises(ValueError):
        build_file_source("kb-1", "doc__a", "a.txt")
    with pytest.raises(ValueError):
        build_file_source("", "doc-a", "a.txt")


def test_parse_file_source_rejects_unknown_shape():
    """结构不合法的来源标识不返回伪造 ID，交由调用方按纯文本处理。"""
    assert parse_file_source("unknown_source") == ("", "", "")
    assert parse_file_source("") == ("", "", "")
    assert parse_file_source("kb-1__") == ("", "", "")


def test_sanitize_filename_keeps_chinese():
    """中文文件名保持原样，仅替换控制字符与分隔符。"""
    assert sanitize_filename("退款说明\n.md") == "退款说明_.md"
    assert sanitize_filename("") == "document"


def test_belongs_to_kb_uses_id_prefix():
    """按知识库过滤只认完整 ID 前缀，避免 kb-1 误命中 kb-10。"""
    source = build_file_source("kb-1", "doc-a", "a.txt")

    assert belongs_to_kb(source, "kb-1") is True
    assert belongs_to_kb(source, "kb-10") is False
    assert belongs_to_kb(source, "") is True


def test_engine_status_mapping_is_not_optimistic():
    """未知状态按 indexing 处理，禁止提前宣称 indexed。"""
    assert map_engine_status("processed") == STATUS_INDEXED
    assert map_engine_status("failed") == STATUS_FAILED
    assert map_engine_status("pending") == STATUS_INDEXING
    assert map_engine_status("processing") == STATUS_INDEXING
    assert map_engine_status("something-new") == STATUS_INDEXING
    assert map_engine_status(None) == STATUS_INDEXING


def test_chunk_top_k_expands_only_for_kb_filter():
    """指定知识库时放大候选窗口，未指定时按 top_k 原样召回。"""
    assert chunk_top_k_for("", 5) == 5
    assert chunk_top_k_for("kb-1", 5) == 20
    assert chunk_top_k_for("kb-1", 20) == 60


def _payload(*chunks):
    """构造 ``aquery_data`` 结构的最小响应。"""
    return {"status": "success", "data": {"chunks": list(chunks)}}


def test_map_chunks_filters_other_kb_and_dedupes():
    """跨库结果被过滤，重复切块只保留首次出现，保持引擎排序。"""
    items = map_chunks(
        _payload(
            {"chunk_id": "c1", "file_path": "kb-1__doc-a__a.txt", "content": "甲", "reference_id": "1"},
            {"chunk_id": "c2", "file_path": "kb-2__doc-z__z.txt", "content": "乙", "reference_id": "2"},
            {"chunk_id": "c1", "file_path": "kb-1__doc-a__a.txt", "content": "甲", "reference_id": "1"},
            {"chunk_id": "c3", "file_path": "kb-1__doc-b__b.txt", "content": "丙", "reference_id": "1"},
        ),
        "kb-1",
        5,
    )

    assert [item["id"] for item in items] == ["c1", "c3"]
    assert [item["doc_id"] for item in items] == ["doc-a", "doc-b"]
    assert items[0]["doc_name"] == "a.txt"
    assert items[0]["text"] == "甲"


def test_map_chunks_truncates_to_top_k():
    """映射结果不超过 top_k。"""
    items = map_chunks(
        _payload(
            *[
                {"chunk_id": f"c{i}", "file_path": "kb-1__doc-a__a.txt", "content": str(i)}
                for i in range(5)
            ]
        ),
        "kb-1",
        2,
    )

    assert len(items) == 2


def test_map_chunks_excludes_unattributable_chunks_when_filtering():
    """指定知识库时，无法归属的切块被过滤，避免跨库串上下文。"""
    items = map_chunks(
        _payload({"chunk_id": "c9", "file_path": "unknown_source", "content": "外部片段"}),
        "kb-1",
        5,
    )

    assert items == []


def test_map_chunks_keeps_unattributable_chunks_without_filter():
    """未指定知识库时，无法归属的切块仍作为纯文本上下文返回。"""
    items = map_chunks(
        _payload({"chunk_id": "c9", "file_path": "unknown_source", "content": "外部片段"}),
        "",
        5,
    )

    assert items[0]["id"] == "c9"
    assert items[0]["doc_id"] == ""
    assert items[0]["text"] == "外部片段"


def test_map_chunks_handles_empty_payload():
    """空响应不抛异常，返回空列表。"""
    assert map_chunks({}, "kb-1", 5) == []
    assert map_chunks({"data": None}, "kb-1", 5) == []


def _graph_node(node_id: str, file_path: str, **extra) -> dict:
    """构造 LightRAG 子图节点（属性里带来源与类型）。"""
    return {
        "id": node_id,
        "properties": {"file_path": file_path, "entity_type": "业务", "description": "说明", **extra},
    }


def test_parse_doc_ids_handles_multiple_sources():
    """实体可能由多篇文档共同抽取，只解析当前知识库的文档 ID。"""
    file_path = "kb-1__doc-a__a.txt<SEP>kb-2__doc-z__z.txt<SEP>kb-1__doc-b__b.txt"

    assert parse_doc_ids(file_path, "kb-1") == ["doc-a", "doc-b"]


def test_map_graph_filters_other_kb_and_drops_dangling_edges():
    """跨库实体被过滤，悬空边一并丢弃，避免前端画出孤立关系。"""
    payload = {
        "nodes": [
            _graph_node("退款", "kb-1__doc-a__a.txt"),
            _graph_node("其它库实体", "kb-2__doc-z__z.txt"),
        ],
        "edges": [
            {
                "source": "退款",
                "target": "其它库实体",
                "properties": {"description": "跨库关系", "weight": 2},
            }
        ],
        "is_truncated": False,
    }

    result = map_graph(payload, "kb-1", 10)

    assert [node["id"] for node in result["nodes"]] == ["退款"]
    assert result["edges"] == []
    assert result["truncated"] is False
    assert result["engine"] == "lightrag"


def test_map_graph_orders_by_degree_and_truncates():
    """节点按过滤后的度数降序，超出上限时标记 truncated。"""
    payload = {
        "nodes": [
            _graph_node("n1", "kb-1__doc-a__a.txt"),
            _graph_node("n2", "kb-1__doc-a__a.txt"),
            _graph_node("n3", "kb-1__doc-a__a.txt"),
        ],
        "edges": [
            {"source": "n2", "target": "n3", "properties": {"weight": 1}},
            {"source": "n2", "target": "n1", "properties": {"weight": 1}},
        ],
        "is_truncated": False,
    }

    result = map_graph(payload, "kb-1", 2)

    # n2 度数为 2 排首位；n1 与 n3 同度，按 ID 升序保留 n1。
    assert [node["id"] for node in result["nodes"]] == ["n2", "n1"]
    assert result["nodes"][0]["degree"] == 2
    assert result["truncated"] is True
    # n3 被截断后，n2-n3 边必须一起消失。
    assert [(edge["source"], edge["target"]) for edge in result["edges"]] == [("n2", "n1")]


def test_map_graph_normalises_types_and_descriptions():
    """实体类型列表合并成文本，超长描述截断，权重缺失按 1.0。"""
    payload = {
        "nodes": [
            _graph_node(
                "退款",
                "kb-1__doc-a__a.txt",
                entity_type=["业务", "流程"],
                description="长" * 500,
            )
        ],
        "edges": [{"source": "退款", "target": "退款", "properties": {}}],
    }

    result = map_graph(payload, "kb-1", 10)

    node = result["nodes"][0]
    assert node["entity_type"] == "业务,流程"
    assert len(node["description"]) == 400
    assert node["description"].endswith("…")
    assert result["edges"] == []


def test_map_graph_caps_limit_and_handles_empty_payload():
    """limit 收敛到契约上限；空 payload 返回空图而不是异常。"""
    assert map_graph({}, "kb-1", 10) == {
        "nodes": [],
        "edges": [],
        "truncated": False,
        "engine": "lightrag",
    }
    result = map_graph({"nodes": [_graph_node("甲", "kb-1__doc-a__a.txt")]}, "kb-1", 10_000)
    assert len(result["nodes"]) == 1
    assert MAX_GRAPH_NODES >= 500
