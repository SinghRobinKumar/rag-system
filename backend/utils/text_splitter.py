"""
Recursive text splitter for chunking documents.
Splits text into overlapping chunks while respecting natural boundaries.
"""
from typing import Optional


def split_text(
    text: str,
    chunk_size: int = 512,
    chunk_overlap: int = 50,
    separators: Optional[list[str]] = None,
) -> list[str]:
    """
    Split text into chunks using recursive character splitting.

    Strategy: Try to split on the largest separator first (paragraphs),
    then fall back to smaller ones (sentences, words, characters).
    """
    if separators is None:
        separators = ["\n\n", "\n", ". ", ", ", " ", ""]

    if len(text) <= chunk_size:
        return [text.strip()] if text.strip() else []

    chunks = []
    current_separator = separators[0]
    remaining_separators = separators[1:]

    # Find the best separator that actually splits the text
    for sep in separators:
        if sep in text:
            current_separator = sep
            remaining_separators = separators[separators.index(sep) + 1:]
            break

    # Split text using the chosen separator
    parts = text.split(current_separator) if current_separator else list(text)

    current_chunk = ""
    for part in parts:
        # Add separator back (except for empty string separator)
        piece = part if not current_separator else part + current_separator

        if len(current_chunk) + len(piece) <= chunk_size:
            current_chunk += piece
        else:
            if current_chunk.strip():
                chunks.append(current_chunk.strip())

            # If a single piece is larger than chunk_size, recursively split it
            if len(piece) > chunk_size and remaining_separators:
                sub_chunks = split_text(
                    piece, chunk_size, chunk_overlap, remaining_separators
                )
                chunks.extend(sub_chunks)
                current_chunk = ""
            else:
                # Start new chunk with overlap from previous
                if chunk_overlap > 0 and chunks:
                    overlap_text = chunks[-1][-chunk_overlap:]
                    current_chunk = overlap_text + piece
                else:
                    current_chunk = piece

    if current_chunk.strip():
        chunks.append(current_chunk.strip())

    return chunks
