import fitz  # PyMuPDF
import json
import os

class LayoutExtraction:
    def __init__(self, file_path, debug_dir):
        self.file_path = file_path
        self.debug_dir = debug_dir

    def run(self):
        """
        Extracts layout signals from the PDF.
        Returns a list of pages, each containing text blocks with font info.
        """
        print(f"Running Layout Extraction for: {os.path.basename(self.file_path)}")
        
        doc = fitz.open(self.file_path)
        all_signals = []

        for page_num, page in enumerate(doc):
            # get_text("dict") returns a dictionary with block/line/span structure
            # This is crucial for getting font information per span
            page_dict = page.get_text("dict")
            
            page_signals = {
                "page_number": page_num + 1,
                "width": page_dict["width"],
                "height": page_dict["height"],
                "blocks": []
            }

            for block in page_dict["blocks"]:
                if block["type"] == 0:  # Text block
                    block_data = {
                        "bbox": block["bbox"],
                        "lines": []
                    }
                    
                    for line in block["lines"]:
                        line_data = {
                            "bbox": line["bbox"],
                            "spans": []
                        }
                        
                        for span in line["spans"]:
                            # Extract relevant font/text properties
                            span_data = {
                                "text": span["text"],
                                "font": span["font"],
                                "size": span["size"],
                                "color": span["color"],
                                "flags": span["flags"], # bold/italic flags
                                "bbox": span["bbox"],
                                "origin": span["origin"]
                            }
                            line_data["spans"].append(span_data)
                        
                        block_data["lines"].append(line_data)
                    
                    page_signals["blocks"].append(block_data)
            
            # Extract table signals (boundaries) to help the Table Engine later
            tables = page.find_tables()
            page_signals["tables"] = []
            for i, table in enumerate(tables):
                page_signals["tables"].append({
                    "id": i,
                    "bbox": table.bbox,
                    "rows": table.extract(), # Extract actual content: [['Cell 1', 'Cell 2'], ...]
                    "row_count": table.row_count,
                    "col_count": table.col_count
                })

            all_signals.append(page_signals)

        doc.close()
        
        self._write_debug(all_signals)
        return all_signals

    def _write_debug(self, data):
        if not self.debug_dir:
            return
        os.makedirs(self.debug_dir, exist_ok=True)
        output_path = os.path.join(self.debug_dir, "signals_raw.json")
        
        # Use ensure_ascii=False to handle French characters correctly
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"Debug output saved to: {output_path}")
