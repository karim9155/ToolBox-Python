import fitz
import re
from typing import List, Optional, Tuple
from .data_models import StandardNode
from .pdf_analyzer import ParserConfig

class VisualParser:
    def __init__(self, pdf_path: str, config: Optional[ParserConfig] = None):
        self.pdf_path = pdf_path
        if config:
            self.config = config
        else:
            self.config = ParserConfig(11.2, 15.0, 12.5, 11.3, False)

    def parse(self, start_page: int = 0, end_page: Optional[int] = None) -> List[StandardNode]:
        doc = fitz.open(self.pdf_path)
        root_children = []
        stack = [(0, None)]
        print(f"Parsing {self.pdf_path} using Visual Hierarchy & Numbering...")
        print(f"Config: Body={self.config.body_size}, L1={self.config.l1_size}, L2={self.config.l2_size}, L3={self.config.l3_size}, Flat={self.config.is_flat_structure}")
        total_pages = len(doc)
        if end_page is None or end_page > total_pages:
            end_page = total_pages
        for page_num in range(start_page, end_page):
            page = doc[page_num]
            blocks = page.get_text("dict")["blocks"]
            for b in blocks:
                if "lines" not in b: continue
                for line in b["lines"]:
                    if not line["spans"]: continue
                    text = "".join([s["text"] for s in line["spans"]]).strip()
                    if not text: continue
                    if "Rapport d'audit (provisoire)" in text or "ProCert" in text or re.match(r'^\d+\s*/\s*\d+$', text):
                        continue
                    if "This report shall not be reproduced" in text:
                        continue
                    if text in ["Minor", "Major", "Critical", "Details of non-applicable clauses with justification"]:
                        continue
                    span = line["spans"][0]
                    size = span["size"]
                    font = span["font"].lower()
                    x0 = line["bbox"][0]
                    is_bold = "bold" in font or "fett" in font or "black" in font
                    numbering_match = re.match(r'^(\d+(?:\.\d+)*)', text)
                    has_numbering = bool(numbering_match)
                    level = 10
                    if self.config.header_regex:
                        match = re.match(self.config.header_regex, text)
                        if match:
                            if match.groups():
                                number_part = match.group(1)
                            else:
                                number_part = match.group(0)
                            if number_part and number_part.endswith('.'): number_part = number_part[:-1]
                            level = number_part.count('.') + 1 if number_part else 1
                            if level > 5: level = 5
                    elif self.config.is_flat_structure:
                        is_header_candidate = False
                        if is_bold:
                            is_header_candidate = True
                        elif has_numbering:
                            if size > self.config.body_size + 0.5:
                                is_header_candidate = True
                            else:
                                number_part = numbering_match.group(1)
                                if number_part:
                                    if number_part.endswith('.'): number_part = number_part[:-1]
                                    parts = number_part.split('.')
                                    if len(parts) >= 2:
                                        is_header_candidate = True
                        if is_header_candidate:
                            if has_numbering:
                                number_part = numbering_match.group(1)
                                if number_part:
                                    if number_part.endswith('.'): number_part = number_part[:-1]
                                    parts = number_part.split('.')
                                    level = len(parts)
                                else:
                                    level = 1
                            else:
                                parent_level = stack[-1][0]
                                if parent_level == 0:
                                    level = 1
                                else:
                                    level = parent_level + 1
                            if level > 5: level = 5
                    else:
                        is_header_candidate = is_bold or (has_numbering and size > self.config.body_size + 0.5)
                        if is_header_candidate and has_numbering:
                            if size >= self.config.l1_size - 0.1 and self.config.l1_size > self.config.body_size:
                                level = 1
                            elif size >= self.config.l2_size - 0.1 and self.config.l2_size > self.config.body_size:
                                level = 2
                            elif size >= self.config.l3_size - 0.1 and self.config.l3_size > self.config.body_size:
                                level = 3
                            else:
                                number_part = numbering_match.group(1) if numbering_match else None
                                if number_part:
                                    dots = number_part.count('.')
                                    if dots == 0: level = 1
                                    elif dots == 1: level = 2
                                    elif dots == 2: level = 3
                                    else: level = 4
                                else:
                                    level = 1
                    if level < 10:
                        clean_text = text.replace('\u200b', '').strip()
                        current_active_node = stack[-1][1]
                        if current_active_node and current_active_node.title.replace('\u200b', '').strip() == clean_text:
                            continue
                        temp_stack_index = len(stack) - 1
                        while temp_stack_index >= 0 and stack[temp_stack_index][0] >= level:
                            temp_stack_index -= 1
                        last_sibling = None
                        if temp_stack_index == -1:
                             if root_children:
                                 last_sibling = root_children[-1]
                        else:
                             potential_parent = stack[temp_stack_index][1]
                             if potential_parent:
                                 if potential_parent.children:
                                     last_sibling = potential_parent.children[-1]
                             else:
                                 if root_children:
                                     last_sibling = root_children[-1]
                        if last_sibling and last_sibling.title.replace('\u200b', '').strip() == clean_text:
                             continue
                        ref_code_match = re.match(r'^(\d+(?:\.\d+)*)', text)
                        reference_code = ref_code_match.group(1) if ref_code_match else None
                        new_node = StandardNode(
                            reference_code=reference_code,
                            title=text,
                            content="",
                            node_type="process" if level < 3 else "requirement",
                            children=[]
                        )
                        while stack and stack[-1][0] >= level:
                            stack.pop()
                        parent_node = stack[-1][1]
                        if parent_node:
                            parent_node.children.append(new_node)
                        else:
                            root_children.append(new_node)
                        stack.append((level, new_node))
                    else:
                        prefix = ""
                        if x0 > 70:
                            prefix = "- "
                        current_node = stack[-1][1]
                        if current_node:
                            if current_node.content:
                                current_node.content += "\n"
                            current_node.content += f"{prefix}{text}"
                        else:
                            pass
        return root_children
