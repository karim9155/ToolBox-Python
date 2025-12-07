import re
import json
import os

class HeadingDetection:
    def __init__(self, signals, font_clusters, debug_dir):
        self.signals = signals
        self.font_clusters = font_clusters
        self.debug_dir = debug_dir
        
        # Map font properties to cluster IDs for quick lookup
        self.font_map = {}
        for cluster in font_clusters:
            key = (cluster["font"], cluster["size"], cluster["flags"], cluster["color"])
            self.font_map[key] = cluster

    def run(self):
        print("Running Heading Detection (Strict Elimination Mode)...")
        
        candidates = []
        
        for page in self.signals:
            page_num = page["page_number"]
            
            for block in page["blocks"]:
                for line in block["lines"]:
                    # Combine spans to get full line text
                    full_text = "".join([span["text"] for span in line["spans"]]).strip()
                    
                    if not full_text:
                        continue

                    # Get font info
                    first_span = line["spans"][0]
                    font_key = (first_span["font"], round(first_span["size"], 1), first_span["flags"], first_span["color"])
                    cluster = self.font_map.get(font_key)
                    if not cluster:
                        cluster = self.font_clusters[-1]

                    # Strict Checks
                    is_bold = self._is_bold(line)
                    has_numbering = self._has_numbering(full_text)
                    
                    # Create candidate for ALL lines (so content is preserved)
                    candidate = {
                        "page": page_num,
                        "text": full_text,
                        "score": 0, 
                        "is_heading": False, # Determined after merge
                        "is_bold": is_bold,
                        "has_numbering": has_numbering,
                        "cluster_id": cluster["id"],
                        "reasons": [],
                        "bbox": line["bbox"]
                    }
                    
                    if is_bold:
                        candidate["reasons"].append("Bold")
                    if has_numbering:
                        candidate["reasons"].append("Numbered")
                        
                    candidates.append(candidate)

        # Merge multiline headings (based on Boldness)
        candidates = self._merge_multiline_candidates(candidates)
        
        # Final Decision: Is it a heading?
        for c in candidates:
            # Re-evaluate numbering on the merged text
            c["has_numbering"] = self._has_numbering(c["text"])
            
            # Strict Rule: Bold AND Numbered
            if c["is_bold"] and c["has_numbering"]:
                c["is_heading"] = True
                c["score"] = 100
            else:
                c["is_heading"] = False
                c["score"] = 0
        
        self._write_debug(candidates)
        return candidates

    def _is_bold(self, line):
        """Checks if the line is visually bold."""
        for span in line["spans"]:
            flags = span.get("flags", 0)
            font_name = span.get("font", "").lower()
            # Flag 16 is bold. Also check font names.
            if (flags & 16) or ("bold" in font_name) or ("fett" in font_name) or ("black" in font_name):
                return True
        return False

    def _has_numbering(self, text):
        """Checks if the text starts with a valid numbering pattern."""
        # 1. Standard Numeric with dot: "1. Title", "1.1 Title"
        if re.match(r'^(\d+\.|(\d+\.)+\d+)(\s|$)', text):
            return True
            
        # 2. Numeric without dot: "1 Title", "1", "2"
        if re.match(r'^\d+(\s|$)', text):
            return True

        # 3. Hyphenated Numbering: "25-001 Title"
        if re.match(r'^\d+-\d+(\s|$)', text):
            return True

        # 4. Letter Numbering: "A. Title"
        if re.match(r'^[A-Z]\.\s', text):
            return True
            
        # 5. Roman Numerals: "I. Title"
        if re.match(r'^[IVX]+\.\s', text):
            return True
            
        return False

        self._write_debug(candidates)
        return candidates

    def _merge_multiline_candidates(self, candidates):
        """
        Merges adjacent candidates that appear to be part of the same heading.
        """
        if not candidates:
            return []
            
        merged = []
        skip_next = False
        
        for i in range(len(candidates)):
            if skip_next:
                skip_next = False
                continue
                
            current = candidates[i]
            
            # If it's the last one, just add it
            if i == len(candidates) - 1:
                merged.append(current)
                break
                
            next_cand = candidates[i+1]
            
            # Check if they should be merged
            # 1. Must be on same page
            if current["page"] != next_cand["page"]:
                merged.append(current)
                continue
                
            # 2. Must be both BOLD (since we are merging potential headings)
            # If one is not bold, we don't merge (it's likely content)
            if not current["is_bold"] or not next_cand["is_bold"]:
                merged.append(current)
                continue
                
            # 3. Must have same font cluster (or very similar)
            if current["cluster_id"] != next_cand["cluster_id"]:
                merged.append(current)
                continue
                
            # 4. Vertical proximity (next one is directly below)
            # bbox is [x0, y0, x1, y1]
            # Gap between current.bottom and next.top
            gap = next_cand["bbox"][1] - current["bbox"][3]
            # Allow small gap (e.g. line spacing)
            if gap > 20: # Arbitrary threshold, depends on PDF scale. 20 is usually safe for single spacing.
                merged.append(current)
                continue
                
            # 5. Logic: If current starts with number and next DOES NOT, it's likely a split title.
            # Or if current doesn't end with punctuation.
            
            curr_has_number = self._has_numbering(current["text"])
            next_has_number = self._has_numbering(next_cand["text"])
            
            should_merge = False
            if curr_has_number and not next_has_number:
                should_merge = True
            elif not current["text"].strip().endswith(('.', ':', ';')) and not next_has_number:
                # If current line doesn't look finished
                should_merge = True
                
            if should_merge:
                # Merge them
                current["text"] += " " + next_cand["text"]
                # Update bbox to encompass both
                # bbox might be a tuple, convert to list to modify
                bbox = list(current["bbox"])
                bbox[2] = max(bbox[2], next_cand["bbox"][2]) # max x1
                bbox[3] = next_cand["bbox"][3] # new y1
                current["bbox"] = bbox
                
                # Combine reasons
                current["reasons"].extend([r for r in next_cand["reasons"] if r not in current["reasons"]])
                current["reasons"].append("Merged Multiline")
                
                merged.append(current)
                skip_next = True
            else:
                merged.append(current)
                
        return merged

    def _write_debug(self, data):
        if not self.debug_dir:
            return
        os.makedirs(self.debug_dir, exist_ok=True)
        output_path = os.path.join(self.debug_dir, "heading_candidates.json")
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"Debug output saved to: {output_path}")
