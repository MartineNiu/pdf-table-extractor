from collections import Counter
from typing import List, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from pdfplumber.page import Page

def find_text_alignment_tables(page: "Page") -> List[List[float]]:
    """
    Analyzes a page to find clusters of vertically aligned text, adapting the
    proven projection-based method to work on a full-page scale.
    This is Engine 2 of the dual-engine approach.

    :param page: A pdfplumber page object.
    :return: A list of bounding boxes for tables found through text alignment.
    """
    words = page.extract_words(x_tolerance=3, y_tolerance=3, keep_blank_chars=False)
    if not words:
        return []

    # Group words into lines, which are fundamental for analysis.
    words.sort(key=lambda w: (w['top'], w['x0']))
    lines = []
    if words:
        current_line = [words[0]]
        # Use a slightly larger tolerance for full-page analysis
        tolerance = (current_line[0]['bottom'] - current_line[0]['top']) * 0.7 if (current_line[0]['bottom'] - current_line[0]['top']) > 0 else 3
        for word in words[1:]:
            if abs(word['top'] - current_line[-1]['top']) < tolerance:
                current_line.append(word)
            else:
                lines.append(sorted(current_line, key=lambda w: w['x0']))
                current_line = [word]
                tolerance = (word['bottom'] - word['top']) * 0.7 if (word['bottom'] - word['top']) > 0 else 3
        lines.append(sorted(current_line, key=lambda w: w['x0']))

    # Find groups of consecutive lines that likely form a table.
    table_line_groups = []
    if not lines:
        return []
        
    avg_heights = [l[0]['bottom'] - l[0]['top'] for l in lines if l and l[0]['bottom'] > l[0]['top']]
    if not avg_heights: return []
    avg_height = sum(avg_heights) / len(avg_heights)
    max_line_gap = avg_height * 2.0 # Allow a gap of up to 2 lines between table rows

    current_group = [lines[0]]
    for i in range(1, len(lines)):
        prev_line_bottom = max(w['bottom'] for w in current_group[-1])
        current_line_top = min(w['top'] for w in lines[i])
        
        if (current_line_top - prev_line_bottom) < max_line_gap:
            current_group.append(lines[i])
        else:
            if len(current_group) >= 3: # A table should have at least 3 rows
                table_line_groups.append(current_group)
            current_group = [lines[i]]
    if len(current_group) >= 3:
        table_line_groups.append(current_group)

    # Now, for each group of lines, apply the proven projection method.
    table_bboxes = []
    for group in table_line_groups:
        group_bbox = (
            min(w['x0'] for l in group for w in l),
            min(w['top'] for l in group for w in l),
            max(w['x1'] for l in group for w in l),
            max(w['bottom'] for l in group for w in l)
        )

        row_word_counts = [len(row) for row in group]
        if not row_word_counts: continue
        
        count_info = Counter(row_word_counts).most_common(1)
        if not count_info: continue
        
        most_common_word_count = count_info[0][0]
        if most_common_word_count < 2: continue # Need at least 2 columns
            
        template_words = [word for row in group if len(row) == most_common_word_count for word in row]
        if not template_words: continue

        table_width = int(group_bbox[2] - group_bbox[0])
        if table_width <= 0: continue
        
        projection = [0] * table_width
        for word in template_words:
            start_x = int(word['x0'] - group_bbox[0])
            end_x = int(word['x1'] - group_bbox[0])
            for i in range(max(0, start_x), min(table_width, end_x)):
                projection[i] += 1

        gaps = []
        in_gap = projection[0] == 0
        gap_start = 0 if in_gap else -1
        for i in range(1, table_width):
            is_zero = projection[i] == 0
            if is_zero and not in_gap:
                in_gap = True; gap_start = i
            elif not is_zero and in_gap:
                in_gap = False
                gaps.append((gap_start, i, i - gap_start))
        if in_gap: gaps.append((gap_start, table_width, table_width - gap_start))

        num_expected_gaps = most_common_word_count - 1
        min_gap_width = 3
        wide_gaps = [g for g in gaps if g[2] > min_gap_width]
        wide_gaps.sort(key=lambda g: g[2], reverse=True)
        top_gaps = wide_gaps[:num_expected_gaps]

        if len(top_gaps) < num_expected_gaps:
             # Not enough clear separators found, this might not be a well-structured table.
             continue
        
        # --- Add virtual lines for column separators to the geometry info ---
        virtual_lines = []
        for gap in top_gaps:
            # Calculate the middle of the gap to represent the column separator
            separator_x = group_bbox[0] + gap[0] + (gap[2] / 2)
            virtual_lines.append({
                "x0": separator_x,
                "top": group_bbox[1],
                "x1": separator_x,
                "bottom": group_bbox[3],
                "geom_type": "virtual_line"
            })

        table_bboxes.append({
            "bbox": list(group_bbox),
            "geometries": virtual_lines
        })

    print(f"    - (Text-Align) Found {len(table_bboxes)} potential tables on page {page.page_number}.")
    return table_bboxes 