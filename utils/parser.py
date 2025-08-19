def parse_input(text: str):
    terms = []
    for line in text.splitlines():
        if "-" in line:
            parts = line.split("-", 1)
            term = parts[0].strip()
            definition = parts[1].strip()
            terms.append((term, definition))
    return terms
