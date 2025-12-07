import json
import os

class HierarchyBuilder:
    def __init__(self, candidates, font_clusters, tables, debug_dir):
        self.candidates = candidates
        self.font_clusters = font_clusters
        self.tables = tables
        self.debug_dir = debug_dir

    def _get_table_for_item(self, item):
        """
        Checks if the item's bbox falls inside any detected table on its page.
        Returns the table data if found, else None.
        """
        page_num = item["page"]
        item_bbox = item["bbox"] # [x0, y0, x1, y1]
        
        # Find tables for this page
        page_tables_data = next((p for p in self.tables if p["page_number"] == page_num), None)
        
        if not page_tables_data or not page_tables_data["tables"]:
            return None
            
        # Check intersection with any table
        x_center = (item_bbox[0] + item_bbox[2]) / 2
        y_center = (item_bbox[1] + item_bbox[3]) / 2
        
        for table in page_tables_data["tables"]:
            t_bbox = table["bbox"]
            # Check if center is inside table bbox
            if (t_bbox[0] <= x_center <= t_bbox[2]) and (t_bbox[1] <= y_center <= t_bbox[3]):
                return table
                
        return None

    def run(self):
        print("Running Hierarchy Builder...")
        
        # 1. Determine Levels based on Font Clusters used in Headings
        # Filter only valid headings
        valid_headings = [h for h in self.candidates if h["is_heading"]]
        
        # Get unique cluster IDs used by headings
        heading_cluster_ids = sorted(list(set(h["cluster_id"] for h in valid_headings)))
        
        # Map cluster_id -> level (1-based)
        # Since font_clusters are already sorted by size/importance, 
        # the lower the cluster_id, the higher the level (Level 1 is top).
        cluster_to_level = {cid: i+1 for i, cid in enumerate(heading_cluster_ids)}
        
        self._write_debug_levels(cluster_to_level)

        # 2. Build Tree
        root = {
            "type": "root",
            "title": "Document Root",
            "level": 0,
            "content": [],
            "children": []
        }
        
        stack = [root]
        raw_tree_events = []
        
        # --- REVISED LOGIC: START HIERARCHY AT FIRST LEVEL 1 HEADING ---
        # The "real" document structure begins when we encounter the first "Level 1" heading.
        # Any headings (even if they look like Level 2 or 3) appearing BEFORE the first Level 1
        # are considered "Front Matter" (Title page info, addresses, etc.) and not part of the tree.
        
        hierarchy_started = False
        processed_tables = set() # (page_num, table_id)

        for item in self.candidates:
            text = item["text"]
            
            if item["is_heading"]:
                # Determine level: Prefer Numbering Depth over Font Size
                # Pass the current stack to check for orphaned numbering
                level = self._determine_level(text, item["cluster_id"], cluster_to_level, stack)
                
                if not hierarchy_started:
                    # Check if this is a Level 1 heading
                    if level == 1:
                        hierarchy_started = True
                    else:
                        # It's a heading-like item (e.g. bold address) but appears before the main structure starts.
                        # Treat as emphasized content in Front Matter.
                        stack[-1]["content"].append(f"**{text}**") 
                        raw_tree_events.append({"event": "ADD_FRONT_MATTER", "text": text, "ignored_level": level})
                        continue

                # If we are here, hierarchy has started OR this is the starting Level 1 node
                
                new_node = {
                    "type": "section",
                    "title": text,
                    "level": level,
                    "content": [],
                    "children": []
                }
                
                # Pop stack until we find a parent with level < new_node.level
                # This ensures correct nesting (e.g. Level 2 goes inside Level 1)
                while len(stack) > 1 and stack[-1]["level"] >= level:
                    closed_node = stack.pop()
                    raw_tree_events.append({"event": "CLOSE", "title": closed_node["title"]})
                
                # Add to parent
                parent = stack[-1]
                parent["children"].append(new_node)
                stack.append(new_node)
                raw_tree_events.append({"event": "OPEN", "title": text, "level": level})
                
            else:
                # It's content
                # Filter out noise ("Too Short")
                if "Too Short" not in item["reasons"]:
                    # Check if this item belongs to a table
                    table_info = self._get_table_for_item(item)
                    
                    if table_info:
                        table_key = (item["page"], table_info["id"])
                        
                        if table_key not in processed_tables:
                            # First time encountering this table
                            # Insert the FULL structured table
                            stack[-1]["content"].append({
                                "type": "table",
                                "rows": table_info["rows"]
                            })
                            processed_tables.add(table_key)
                            raw_tree_events.append({"event": "ADD_TABLE", "rows": len(table_info["rows"])})
                        
                        # Skip this item as it is part of the table we just inserted (or already processed)
                        continue

                    # Normal content
                    stack[-1]["content"].append(text)
                    raw_tree_events.append({"event": "ADD_CONTENT", "preview": text[:20]})

        self._clean_tree(root)
        self._write_debug_tree(root, raw_tree_events)
        return root

    def _clean_tree(self, node):
        # Clean content for this node
        if node["content"]:
            node["content"] = self._merge_content_lines(node["content"])
        
        # Recurse
        for child in node["children"]:
            self._clean_tree(child)

    def _merge_content_lines(self, lines):
        if not lines:
            return []
            
        # Regex for list items: bullets or numbering (1., a), 1-)
        import re
        list_pattern = re.compile(r'^(\u2022|\-|\*|\d+\.|[a-zA-Z]\)|\d+\-)\s')
        
        final_blocks = []
        current_paragraph = []
        
        for line in lines:
            # If line is not a string (e.g. it's a table dict), flush paragraph and add it directly
            if not isinstance(line, str):
                if current_paragraph:
                    final_blocks.append(self._join_paragraph(current_paragraph))
                    current_paragraph = []
                final_blocks.append(line)
                continue

            line = line.strip()
            if not line:
                continue
                
            is_list_item = list_pattern.match(line)
            
            if is_list_item:
                # Flush current paragraph if exists
                if current_paragraph:
                    final_blocks.append(self._join_paragraph(current_paragraph))
                    current_paragraph = []
                # Add list item as its own block
                final_blocks.append(line)
            else:
                # It's part of a paragraph
                current_paragraph.append(line)
                
        # Flush remaining
        if current_paragraph:
            final_blocks.append(self._join_paragraph(current_paragraph))
            
        return final_blocks

    def _join_paragraph(self, lines):
        # Join lines with spaces, handling hyphens
        text = ""
        for i, line in enumerate(lines):
            if i == 0:
                text = line
                continue
            
            prev_line = lines[i-1]
            if prev_line.endswith("-"):
                # Check if it looks like a split word (no space before hyphen)
                # e.g. "conser-"
                if len(prev_line) > 1 and prev_line[-2] != " ":
                    # Remove hyphen and join directly
                    # "conser-" + "verie" -> "conserverie"
                    text = text[:-1] + line
                else:
                    # " - " or "word -", keep hyphen and add space
                    text += " " + line
            else:
                text += " " + line
        return text

    def _determine_level(self, text, cluster_id, cluster_to_level, stack=None):
        """
        Calculates the heading level.
        Uses a hybrid approach:
        - Calculates level from Numbering Depth (e.g. 1.1 -> 2)
        - Calculates level from Font Cluster Rank (e.g. Big Font -> 1)
        
        Logic:
        1. Base Level = Font Cluster Level.
        2. If Numbering Depth > Cluster Level (e.g. "1.1.1" with Level 2 font):
           - Check if parent numbering exists in the stack.
           - If YES: Demote to Numbering Depth.
           - If NO (Orphan): Ignore Numbering Depth, stick to Cluster Level.
        3. If Numbering Depth < Cluster Level (e.g. "5 Evaluations" with Level 2 font):
           - Do NOT promote. Stick to Cluster Level.
           - This ensures "5 Evaluations" (Level 2) and "2.5.1" (Level 2) are siblings if they share the same font.
        """
        import re
        
        # 1. Level from Numbering
        level_num = 10 # Default deep
        numbering_str = ""
        match = re.match(r'^(\d+(?:\.\d+)*)', text)
        if match:
            numbering_str = match.group(1)
            segments = [s for s in numbering_str.split('.') if s]
            if segments:
                level_num = len(segments)
                
        # 2. Level from Cluster
        # cluster_to_level is 1-based rank of heading clusters
        level_cluster = cluster_to_level.get(cluster_id, 10)

        # 3. Hybrid Decision
        
        # Start with Cluster Level (Visual Hierarchy)
        final_level = level_cluster
        
        # Check for Demotion (Numbering is deeper than Font)
        if level_num > level_cluster:
            # Check if this is a valid child of the current context
            # e.g. "2.5.1" (Depth 3) requires "2.5" (Depth 2) or "2" (Depth 1) in the stack?
            # Strictly, it requires the immediate parent "2.5".
            
            is_orphan = True
            if stack:
                # Look for parent numbering in the stack
                # Parent of "2.5.1" is "2.5"
                parent_num_str = numbering_str.rsplit('.', 1)[0]
                
                # Check if any node in the stack has this numbering
                # We iterate backwards to find the closest parent
                for node in reversed(stack):
                    node_title = node.get("title", "")
                    # Strict check: The node title must START with the parent numbering
                    # AND be followed by a separator (dot, space) or be the exact string.
                    # e.g. "2.5" matches "2.5.1" (No! "2.5" is parent of "2.5.1")
                    # We are looking for "2.5" in the stack.
                    # "2.5.1" in stack should NOT match "2.5".
                    
                    # Extract the numbering part of the node title
                    node_num_match = re.match(r'^(\d+(?:\.\d+)*)', node_title)
                    if node_num_match:
                        node_num = node_num_match.group(1)
                        if node_num == parent_num_str:
                            is_orphan = False
                            break
            
            if not is_orphan:
                final_level = level_num
            else:
                # It's an orphan (e.g. "2.5.1" without "2.5").
                # Trust the Font (Cluster Level).
                pass
                
        # Check for Promotion (Numbering is shallower than Font)
        elif level_num < level_cluster:
            # e.g. "5 Evaluations" (Depth 1) vs Cluster Level 2.
            # Do NOT promote. Trust the Font.
            # This ensures "5 Evaluations" stays Level 2, same as "2.5.1".
            pass
            
        return final_level

    def _write_debug_levels(self, level_map):
        if not self.debug_dir:
            return
        os.makedirs(self.debug_dir, exist_ok=True)
        output_path = os.path.join(self.debug_dir, "heading_levels.json")
        
        # Enrich with font info for debugging
        debug_data = []
        for cid, level in level_map.items():
            # Find the font cluster info
            cluster_info = next((c for c in self.font_clusters if c["id"] == cid), None)
            debug_data.append({
                "cluster_id": cid,
                "assigned_level": level,
                "font_info": cluster_info
            })
            
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(debug_data, f, indent=2, ensure_ascii=False)

    def _write_debug_tree(self, root, events):
        if not self.debug_dir:
            return
        os.makedirs(self.debug_dir, exist_ok=True)
        
        # Save events
        with open(os.path.join(self.debug_dir, "raw_tree.ndjson"), "w", encoding="utf-8") as f:
            for event in events:
                f.write(json.dumps(event, ensure_ascii=False) + "\n")
                
        # Save final JSON
        with open(os.path.join(self.debug_dir, "final_output.json"), "w", encoding="utf-8") as f:
            json.dump(root, f, indent=2, ensure_ascii=False)
            
        # Save Markdown preview
        with open(os.path.join(self.debug_dir, "final_output.md"), "w", encoding="utf-8") as f:
            self._recursive_md_export(root, f)
            
    def _recursive_md_export(self, node, f, indent=0):
        if node["level"] > 0:
            prefix = "#" * node["level"]
            f.write(f"{prefix} {node['title']}\n\n")
        elif node["title"] == "Document Root":
             # Don't print "Document Root" title, just its content (Front Matter)
             pass
        
        for content in node["content"]:
            f.write(f"{content}\n\n")
            
        for child in node["children"]:
            self._recursive_md_export(child, f, indent + 1)
