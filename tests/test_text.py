from finfacts.ingest.text import chunk_words


def test_chunks_overlap_and_cover_all_words() -> None:
    words = [f"w{i}" for i in range(1000)]
    chunks = chunk_words(" ".join(words), size=600, overlap=75)
    assert [len(c.split()) for c in chunks] == [600, 475]
    assert chunks[1].split()[0] == "w525"  # 75 words of overlap with the first chunk
    assert chunks[-1].split()[-1] == "w999"


def test_short_and_empty_text() -> None:
    assert chunk_words("one two three", size=600, overlap=75) == ["one two three"]
    assert chunk_words("   ", size=600, overlap=75) == []
    assert len(chunk_words(" ".join(["x"] * 600), size=600, overlap=75)) == 1
