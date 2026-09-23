from app.rag.chunking import PageText, chunk_pages


def test_chunks_keep_configured_overlap_and_page_metadata() -> None:
    text = "abcdefghij" * 3

    chunks = chunk_pages([PageText(page_number=4, text=text)], size=15, overlap=5)

    assert [chunk.text for chunk in chunks] == [text[:15], text[10:25], text[20:]]
    assert [chunk.page_number for chunk in chunks] == [4, 4, 4]
    assert [chunk.chunk_index for chunk in chunks] == [0, 1, 2]


def test_chunking_skips_blank_pages() -> None:
    assert chunk_pages([PageText(page_number=1, text=" \n\t ")]) == []
