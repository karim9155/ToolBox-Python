import fitz
from collections import Counter
import re
from dataclasses import dataclass

@dataclass
class ParserConfig:
    body_size: float
    l1_size: float
    l2_size: float
    l3_size: float
    is_flat_structure: bool = False
    headers_are_bold: bool = True
    headers_have_numbering: bool = True
    header_regex: str = None

class PDFAnalyzer:
    def __init__(self, pdf_path: str):
        self.pdf_path = pdf_path

    def analyze(self) -> ParserConfig:
        doc = fitz.open(self.pdf_path)
        sizes = []
        numbered_bold_sizes = []
        for i in range(min(10, len(doc))):
            page = doc[i]
            blocks = page.get_text("dict")["blocks"]
            for b in blocks:
                if "lines" not in b: continue
                for line in b["lines"]:
                    if not line["spans"]: continue
                    span = line["spans"][0]
                    text = "".join([s["text"] for s in line["spans"]]).strip()
                    if not text: continue
                    size = round(span["size"], 1)
                    font = span["font"].lower()
                    is_bold = "bold" in font or "black" in font or "fett" in font
                    sizes.append(size)
                    if re.match(r'^\d+(?:\.\d+)*', text) and is_bold:
                        numbered_bold_sizes.append(size)
        if not sizes:
            return ParserConfig(11.0, 14.0, 12.0, 11.5)
        size_counts = Counter(sizes)
        body_size = size_counts.most_common(1)[0][0]
        if numbered_bold_sizes:
            header_size_counts = Counter(numbered_bold_sizes)
            unique_header_sizes = sorted(header_size_counts.keys(), reverse=True)
            if len(unique_header_sizes) >= 1:
                l1_size = unique_header_sizes[0]
                l2_size = unique_header_sizes[1] if len(unique_header_sizes) > 1 else l1_size
                l3_size = unique_header_sizes[2] if len(unique_header_sizes) > 2 else l2_size
            else:
                l1_size = body_size
                l2_size = body_size
                l3_size = body_size
        else:
            l1_size = body_size
            l2_size = body_size
            l3_size = body_size
        is_flat_structure = abs(l1_size - body_size) < 0.5
        print(f"Analysis Result for {self.pdf_path}:")
        print(f"  Body Size: {body_size}")
        print(f"  Detected Header Sizes: {sorted(list(set(numbered_bold_sizes)), reverse=True)}")
        print(f"  Flat Structure: {is_flat_structure}")
        print(f"  Config -> L1: {l1_size}, L2: {l2_size}, L3: {l3_size}")
        return ParserConfig(
            body_size=body_size,
            l1_size=l1_size,
            l2_size=l2_size,
            l3_size=l3_size,
            is_flat_structure=is_flat_structure,
            headers_are_bold=True,
            headers_have_numbering=True
        )
