import pdfplumber
import re
from typing import List, Optional, Tuple
from .data_models import StandardNode
from .pdf_analyzer import ParserConfig

class VisualParser:
    def __init__(self, pdf_path: str, config: Optional[ParserConfig] = None):
        self.pdf_path = pdf_path
            # Permanent config for FSSC reports based on analysis
        self.config = ParserConfig(
            body_size=11.2,
            l1_size=16.1,
            l2_size=13.5,
            l3_size=11.5,
            is_flat_structure=False,
            headers_are_bold=True,
            headers_have_numbering=True
        )

    def parse(self, start_page: int = 0, end_page: Optional[int] = None) -> List[StandardNode]:
        
        doc = pdfplumber.open(self.pdf_path)
        root_children = []
        stack = [(0, None)]
        print(f"Parsing {self.pdf_path} using Visual Hierarchy & Numbering...")
        print(f"Config: Body={self.config.body_size}, L1={self.config.l1_size}, L2={self.config.l2_size}, L3={self.config.l3_size}, Flat={self.config.is_flat_structure}")
        total_pages = len(doc.pages)
        if end_page is None or end_page > total_pages:
            end_page = total_pages
        
        # First pass: detect repeated text across pages (headers/footers)
        repeated_texts = set()
        text_pages = {}
        for page_num in range(start_page, end_page):
            page = doc.pages[page_num]
            chars = page.chars
            # Group chars into lines
            lines = []
            current_line = []
            current_y = None
            for char in sorted(chars, key=lambda c: (c['top'], c['x0'])):
                if current_y is None or abs(char['top'] - current_y) > 5:  # new line
                    if current_line:
                        lines.append(current_line)
                    current_line = [char]
                    current_y = char['top']
                else:
                    current_line.append(char)
            if current_line:
                lines.append(current_line)
            
            for line in lines:
                text = ''.join(c['text'] for c in line).strip()
                if not text: continue
                if text not in text_pages:
                    text_pages[text] = set()
                text_pages[text].add(page_num)
        for text, pages in text_pages.items():
            if len(pages) > 1:
                repeated_texts.add(text)
        
        for page_num in range(start_page, end_page):
            page = doc.pages[page_num]
            chars = page.chars
            # Group chars into lines
            lines = []
            current_line = []
            current_y = None
            for char in sorted(chars, key=lambda c: (c['top'], c['x0'])):
                if current_y is None or abs(char['top'] - current_y) > 5:  # new line
                    if current_line:
                        lines.append(current_line)
                    current_line = [char]
                    current_y = char['top']
                else:
                    current_line.append(char)
            if current_line:
                lines.append(current_line)
            
            for line in lines:
                text = ''.join(c['text'] for c in line).strip()
                if not text: continue
                if text in repeated_texts: continue
                if re.match(r'^\d+\s*/\s*\d+$', text): continue
                if not line: continue
                # Skip headers and footers based on position
                y_top = min(c['top'] for c in line)
                y_bottom = max(c['bottom'] for c in line)
                if y_top < 20 or y_bottom > page.height - 50:
                    continue
                first_char = line[0]
                size = round(first_char['size'], 1)
                font = first_char['fontname'].lower()
                x0 = first_char['x0']
                is_bold = any("bold" in c['fontname'].lower() or "fett" in c['fontname'].lower() or "black" in c['fontname'].lower() for c in line)
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
                        if size >= self.config.l1_size:
                            level = 1
                        elif size >= self.config.l2_size:
                            level = 2
                        elif size >= self.config.l3_size:
                            level = 3
                        else:
                            level = 4
                        if level > 5: level = 5
                else:
                    is_header_candidate = has_numbering and is_bold
                    if is_header_candidate:
                        if size >= self.config.l1_size:
                            level = 1
                        elif size >= self.config.l2_size:
                            level = 2
                        elif size >= self.config.l3_size:
                            level = 3
                        else:
                            level = 4
                    if level < 10:
                        clean_text = text.replace('\u200b', '').strip()
                        if len(clean_text) < 3: continue
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
                        # Format text for Markdown
                        formatted_text = text
                        is_list_item = False
                        
                        # Detect list markers
                        if re.match(r'^•\s', text):
                            formatted_text = re.sub(r'^•\s', '- ', text)
                            is_list_item = True
                        elif re.match(r'^-\s', text):
                            is_list_item = True
                        elif re.match(r'^\d+\.\s', text):
                            is_list_item = True
                        # Only treat as list if indented and looks like a list (short or specific patterns), not table data
                        elif x0 > 70 and len(text.strip()) < 100 and not re.search(r'[A-Z][a-z]+ [A-Z]', text):  # avoid names
                            formatted_text = "- " + text
                            is_list_item = True
                        
                        current_node = stack[-1][1]
                        if current_node:
                            if re.match(r'^[A-Z]+\)', formatted_text) and not current_node.content:
                                current_node.title += ' ' + formatted_text
                            else:
                                if current_node.content:
                                    current_node.content += "\n"
                                current_node.content += formatted_text
                        else:
                            pass
            
            # Extract tables on this page
            tables = page.extract_tables()
            for table in tables:
                if not table: continue
                markdown = ""
                for i, row in enumerate(table):
                    markdown += "| " + " | ".join(str(cell).strip() if cell else "" for cell in row) + " |\n"
                    if i == 0:
                        markdown += "|" + "|".join("---" for _ in row) + "|\n"
                current_node = stack[-1][1]
                if current_node and markdown:
                    if current_node.content:
                        current_node.content += "\n\n" + markdown
                    else:
                        current_node.content = markdown
        
        def update_node_types(nodes):
            for node in nodes:
                if node.content.strip():
                    node.node_type = "requirement"
                update_node_types(node.children)
        
        update_node_types(root_children)
        return root_children
