from tenderproof.workflow import section_batches


def test_all_pages_attempted_once_without_crossing_sections_or_size_limit():
    pages = [{"page": n, "system": "LA01" if n <= 6 else "LA02" if n <= 9 else "ROOF"} for n in range(1, 13)]
    batches = section_batches(pages)
    assert [[p["page"] for p in batch] for batch in batches] == [[1, 2, 3, 4], [5, 6], [7, 8, 9], [10, 11, 12]]
    assert [p for batch in batches for p in batch] == pages
    assert all(len(batch) <= 4 and len({p["system"] for p in batch}) == 1 for batch in batches)


def test_batch_resume_starts_from_first_unpersisted_page():
    pages = [{"page": n, "system": "LA01"} for n in range(1, 10)]
    assert [[p["page"] for p in batch] for batch in section_batches(pages[4:])] == [[5, 6, 7, 8], [9]]
