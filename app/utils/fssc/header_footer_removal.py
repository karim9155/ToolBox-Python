import json
import os
import re

class HeaderFooterRemoval:
    def __init__(self, signals, debug_dir):
        self.signals = signals
        self.debug_dir = debug_dir

    def run(self):
        """
        Identifies and removes headers and footers based on:
        1. Geometric zones (top/bottom of page)
        2. Repetition across pages
        3. Common patterns (Page numbers)
        """
        print("Running Header & Footer Removal...")
        
        # Configuration
        TOP_MARGIN_PERCENT = 0.15  # Increased to 15% to catch page numbers/dates
        BOTTOM_MARGIN_PERCENT = 0.15 # Increased to 15%
        REPETITION_THRESHOLD = 0.30 
        
        # Regex for common footer patterns
        # 1. Page numbers: "Page 1", "1/50", "1 / 50", "Page 1 of 50"
        # 2. Dates: "2025-09-23", "23/09/2025"
        FOOTER_REGEX = re.compile(r'(?i)(page\s*\d+)|(^\d+\s*/\s*\d+$)|(^\d+$)|(\d{4}-\d{2}-\d{2})|(\d{2}/\d{2}/\d{4})')

        # 1. Collect candidates from margins
        margin_texts = {} # "text" -> count
        
        total_pages = len(self.signals)
        
        for page in self.signals:
            height = page["height"]
            top_limit = height * TOP_MARGIN_PERCENT
            bottom_limit = height * (1 - BOTTOM_MARGIN_PERCENT)
            
            for block in page["blocks"]:
                # Check if block is in margin
                y0, y1 = block["bbox"][1], block["bbox"][3]
                is_header = y1 < top_limit
                is_footer = y0 > bottom_limit
                
                if is_header or is_footer:
                    # Get text
                    text = " ".join([span["text"] for line in block["lines"] for span in line["spans"]]).strip()
                    if text:
                        margin_texts[text] = margin_texts.get(text, 0) + 1

        # 2. Identify text to remove
        text_to_remove = set()
        for text, count in margin_texts.items():
            # If it repeats often, it's a header/footer
            if count / total_pages > REPETITION_THRESHOLD:
                text_to_remove.add(text)
            # Check regex
            elif FOOTER_REGEX.search(text):
                # FIX: Only remove if it's short (likely a page number or date line)
                # Long text with a date inside is likely content.
                if len(text) < 60:
                    text_to_remove.add(text)

        # 3. Filter signals
        cleaned_signals = []
        removed_count = 0
        
        for page in self.signals:
            new_page = page.copy()
            new_page["blocks"] = []
            
            height = page["height"]
            top_limit = height * TOP_MARGIN_PERCENT
            bottom_limit = height * (1 - BOTTOM_MARGIN_PERCENT)
            
            for block in page["blocks"]:
                y0, y1 = block["bbox"][1], block["bbox"][3]
                is_in_margin = (y1 < top_limit) or (y0 > bottom_limit)
                
                text = " ".join([span["text"] for line in block["lines"] for span in line["spans"]]).strip()
                
                # Remove if it's in the margin AND (it's a known repeated text OR looks like a footer pattern)
                should_remove = False
                if is_in_margin:
                    if text in text_to_remove:
                        should_remove = True
                    elif FOOTER_REGEX.search(text):
                        # Same length check here
                        if len(text) < 60:
                            should_remove = True
                
                if should_remove:
                    removed_count += 1
                else:
                    new_page["blocks"].append(block)
            
            cleaned_signals.append(new_page)

        print(f"Removed {removed_count} header/footer blocks.")
        self._write_debug(cleaned_signals, list(text_to_remove))
        return cleaned_signals

    def _write_debug(self, signals, removed_texts):
        if not self.debug_dir:
            return
        os.makedirs(self.debug_dir, exist_ok=True)
        
        # Save cleaned signals
        with open(os.path.join(self.debug_dir, "signals_cleaned.json"), "w", encoding="utf-8") as f:
            json.dump(signals, f, indent=2, ensure_ascii=False)
            
        # Save what was detected as header/footer text
        with open(os.path.join(self.debug_dir, "removed_headers_footers.json"), "w", encoding="utf-8") as f:
            json.dump(removed_texts, f, indent=2, ensure_ascii=False)
