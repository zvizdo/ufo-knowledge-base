import re
import sys


def clean_transcript(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    # Split into header (everything up to and including ---) and body
    parts = content.split("---\n\n", 1)
    if len(parts) == 2:
        header = parts[0] + "---\n\n"
        body = parts[1]
    else:
        header = ""
        body = content

    # Collapse multiple blank lines into one, then join single-blank-line
    # separated fragments into one continuous line per paragraph.
    # A "paragraph break" is 2+ blank lines; a single blank line between
    # fragments is just a VTT artifact — merge those fragments with a space.
    body = body.strip()

    # Normalise line endings
    body = body.replace("\r\n", "\n")

    # Split on 2+ consecutive blank lines (real paragraph breaks)
    paragraphs = re.split(r"\n{3,}", body)

    cleaned = []
    for para in paragraphs:
        # Within each paragraph, join lines separated by single blank lines
        # (or just newlines) into one line
        para = para.strip()
        if not para:
            continue
        # Replace any run of whitespace-only lines + surrounding newlines with a space
        para = re.sub(r"\n\s*\n", " ", para)
        # Replace bare newlines with a space
        para = re.sub(r"\n", " ", para)
        # Collapse multiple spaces
        para = re.sub(r" {2,}", " ", para)
        cleaned.append(para.strip())

    return header + "\n\n".join(cleaned) + "\n"


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python clean_transcript.py <path_to_transcript.md>")
        sys.exit(1)

    path = sys.argv[1]
    result = clean_transcript(path)

    with open(path, "w", encoding="utf-8") as f:
        f.write(result)

    print(f"Cleaned: {path}")
