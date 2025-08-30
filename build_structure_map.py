import pdfplumber
import json
from pathlib import Path
from collections import Counter, defaultdict
import argparse

# Import the newly created table finding modules
from geometric_table_finder import find_geometric_tables
from text_alignment_table_finder import find_text_alignment_tables

def calculate_iou(box_a, box_b):
    """
    Calculate the Intersection over Union (IoU) of two bounding boxes.
    """
    # Determine the coordinates of the intersection rectangle
    x_left = max(box_a[0], box_b[0])
    y_top = max(box_a[1], box_b[1])
    x_right = min(box_a[2], box_b[2])
    y_bottom = min(box_a[3], box_b[3])

    if x_right < x_left or y_bottom < y_top:
        return 0.0

    intersection_area = (x_right - x_left) * (y_bottom - y_top)

    box_a_area = (box_a[2] - box_a[0]) * (box_a[3] - box_a[1])
    box_b_area = (box_b[2] - box_b[0]) * (box_b[3] - box_b[1])

    iou = intersection_area / float(box_a_area + box_b_area - intersection_area)
    return iou

def analyze_page_layout(page):
    """
    Analyzes a single page to find all tables using a dual-engine approach
    and returns a clean list of page elements.
    This function now orchestrates calls to specialized table finders.
    """
    orientation = "portrait" if page.width <= page.height else "landscape"
    words = page.extract_words(
        x_tolerance=2, 
        y_tolerance=2, 
        keep_blank_chars=False,
        extra_attrs=["fontname", "size"]
    )
    images = page.images
    lines = page.lines
    rects = page.rects

    # =========================================================================
    # Step 1: Pre-process all text on the page into text_blocks
    # =========================================================================
    words.sort(key=lambda w: (w['top'], w['x0']))
    line_clusters = []
    if words:
        current_line = [words[0]]
        line_height_tolerance = (words[0]['bottom'] - words[0]['top']) * 0.7 if words[0]['bottom'] > words[0]['top'] else 5
        for next_word in words[1:]:
            if abs(next_word['top'] - current_line[-1]['top']) < line_height_tolerance:
                current_line.append(next_word)
            else:
                line_clusters.append(current_line)
                current_line = [next_word]
                line_height_tolerance = (next_word['bottom'] - next_word['top']) * 0.7 if next_word['bottom'] > next_word['top'] else 5
        line_clusters.append(current_line)

    page_elements = []
    
    # 添加所有线条到page_elements
    for line in lines:
        # 确保必要的属性存在
        line_element = {
            "type": "line",
            "bbox": (line.get('x0', 0), line.get('top', 0), line.get('x1', 0), line.get('bottom', line.get('top', 0))),
            "x0": line.get('x0', 0),
            "top": line.get('top', 0),
            "x1": line.get('x1', 0),
            "bottom": line.get('bottom', line.get('top', 0)),
        }
        
        # 处理宽度和高度
        if 'width' in line:
            line_element['width'] = line['width']
        elif 'x0' in line and 'x1' in line:
            line_element['width'] = line['x1'] - line['x0']
        else:
            line_element['width'] = 0
            
        if 'height' in line:
            line_element['height'] = line['height']
        elif 'top' in line and 'bottom' in line:
            line_element['height'] = line['bottom'] - line['top']
        else:
            line_element['height'] = 0
        
        # 修改：根据线条特征确定geom_type
        if line_element['x0'] == line_element['x1']:  # 完全垂直的线
            line_element['geom_type'] = 'line_vertical'
        elif line_element['top'] == line_element['bottom']:  # 完全水平的线
            line_element['geom_type'] = 'line_horizontal'
        elif line_element['width'] > line_element['height']:  # 更宽的线条视为水平线
            line_element['geom_type'] = 'line_horizontal'
        else:  # 更高的线条视为垂直线
            line_element['geom_type'] = 'line_vertical'
        
        # 处理可能的线条属性
        if 'pts' in line:
            line_element['pts'] = line['pts']
        if 'linewidth' in line:
            line_element['linewidth'] = line['linewidth']
        if 'stroke' in line:
            line_element['stroke'] = line['stroke']
        if 'fill' in line:
            line_element['fill'] = line['fill']
        if 'stroking_color' in line:
            line_element['stroking_color'] = line['stroking_color']
            
        page_elements.append(line_element)
    
    # 添加所有矩形到page_elements
    for rect in rects:
        # 确保必要的属性存在
        rect_element = {
            "type": "rect",
            "bbox": (rect.get('x0', 0), rect.get('top', 0), rect.get('x1', 0), rect.get('bottom', rect.get('top', 0))),
            "x0": rect.get('x0', 0),
            "top": rect.get('top', 0),
            "x1": rect.get('x1', 0),
            "bottom": rect.get('bottom', rect.get('top', 0)),
            "geom_type": "rect"
        }
        
        # 处理宽度和高度
        if 'width' in rect:
            rect_element['width'] = rect['width']
        elif 'x0' in rect and 'x1' in rect:
            rect_element['width'] = rect['x1'] - rect['x0']
        else:
            rect_element['width'] = 0
            
        if 'height' in rect:
            rect_element['height'] = rect['height']
        elif 'top' in rect and 'bottom' in rect:
            rect_element['height'] = rect['bottom'] - rect['top']
        else:
            rect_element['height'] = 0
            
        # 自动将非常细长的矩形识别为线条
        if rect_element['width'] > 5 and rect_element['height'] <= 1:
            rect_element['geom_type'] = 'line_horizontal'
        elif rect_element['height'] > 5 and rect_element['width'] <= 1:
            rect_element['geom_type'] = 'line_vertical'
            
        page_elements.append(rect_element)

    for word_cluster in line_clusters:
        if not word_cluster: continue
        sorted_cluster = sorted(word_cluster, key=lambda w: w['x0'])
        merged_word_objects = []
        if sorted_cluster:
            current_merge = sorted_cluster[0].copy()
            for i in range(1, len(sorted_cluster)):
                next_word = sorted_cluster[i]
                current_word_width = current_merge['x1'] - current_merge['x0']
                num_chars = len(current_merge['text'])
                avg_char_width = (current_word_width / num_chars) if num_chars > 0 else 5
                gap = next_word['x0'] - current_merge['x1']
                if gap < (avg_char_width * 0.5) and abs(next_word['top'] - current_merge['top']) < 5:
                    current_merge['text'] += next_word['text']
                    current_merge['x1'] = max(current_merge['x1'], next_word['x1'])
                    current_merge['bottom'] = max(current_merge['bottom'], next_word['bottom'])
                else:
                    merged_word_objects.append(current_merge)
                    current_merge = next_word.copy()
            merged_word_objects.append(current_merge)
        if not merged_word_objects: continue
        cluster_bbox = (
            min(w['x0'] for w in merged_word_objects), min(w['top'] for w in merged_word_objects),
            max(w['x1'] for w in merged_word_objects), max(w['bottom'] for w in merged_word_objects),
        )
        page_elements.append({
            "type": "text_block", "bbox": cluster_bbox,
            "text": " ".join(w['text'] for w in merged_word_objects),
            "words": [{"text": w['text'], "x0": w['x0'], "x1": w['x1'], "top": w['top'], "bottom": w['bottom']} for w in merged_word_objects]
        })

    for img in images:
        page_elements.append({ "type": "image", "bbox": [img['x0'], img['top'], img['x1'], img['bottom']] })

    # =========================================================================
    # Step 2: Engine 1 - Find tables based on geometric lines and rectangles
    # =========================================================================
    geometric_tables = find_geometric_tables(page, page_elements)

    # =========================================================================
    # Step 3: Engine 2 - Find tables based on text alignment
    # =========================================================================
    text_table_bboxes = find_text_alignment_tables(page)
    
    # =========================================================================
    # Step 4: De-duplicate and add final tables to page elements
    # =========================================================================
    final_tables = list(geometric_tables)
    geo_table_bboxes = [t['bbox'] for t in geometric_tables]

    for text_bbox_info in text_table_bboxes:
        text_bbox = text_bbox_info["bbox"]
        is_overlapping = False
        for geo_bbox in geo_table_bboxes:
            if calculate_iou(text_bbox, geo_bbox) > 0.1:
                is_overlapping = True
                break
        
        if not is_overlapping:
            final_tables.append({
                "type": "table",
                "bbox": tuple(text_bbox),
                "parsing_strategy": "text_only",
                "reason": "Found by text alignment",
                "geometries": text_bbox_info.get("geometries", [])
            })
    
    final_table_bboxes = [t['bbox'] for t in final_tables]
    
    elements_to_keep = []
    for el in page_elements:
        is_inside_table = False
        if el['type'] == 'text_block':
            for table_bbox in final_table_bboxes:
                if calculate_iou(el['bbox'], table_bbox) > 0.8:
                     is_inside_table = True
                     break
        if not is_inside_table:
            elements_to_keep.append(el)
            
    elements_to_keep.extend(final_tables)
    
    elements_to_keep.sort(key=lambda x: x['bbox'][1])
    
    layout_info = {
        "page_number": page.page_number,
        "dimensions": (page.width, page.height),
        "orientation": orientation,
        "elements": elements_to_keep
    }
    
    # 打印调试信息
    element_types = Counter(el['type'] for el in elements_to_keep)
    geom_types = Counter(el.get('geom_type', 'none') for el in elements_to_keep)
    print(f"  - Page {page.page_number} elements: {dict(element_types)}")
    print(f"  - Page {page.page_number} geometry types: {dict(geom_types)}")
    
    return layout_info

def generate_structure_map(pdf_path: str, output_path: str):
    """
    Analyzes a PDF and creates a detailed JSON map of its structure,
    including pages, elements, and automatically detected tables.
    Now includes a dual-engine approach to find both geometric and text-only tables.
    """
    # This is the final, desired structure for our map.
    final_map_structure = {
        "pdf_path": str(Path(pdf_path).resolve()),
        "pages": []
    }
    
    with pdfplumber.open(pdf_path) as pdf:
        print(f"Starting to process {len(pdf.pages)} pages...")
        for i, page in enumerate(pdf.pages):
            print(f"  - Processing Page {i+1}/{len(pdf.pages)}...")
            
            # This contains the full analysis data for one page
            page_summary = analyze_page_layout(page)
            
            # We add the page number into the summary itself for easier access
            page_summary["page_number"] = i + 1
            
            final_map_structure["pages"].append(page_summary)

    print(f"\nFinished processing all pages. Writing to {output_path}...")
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(final_map_structure, f, ensure_ascii=False, indent=2)
    print("Structure map generation complete.")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Generate a structure map from a PDF.")
    parser.add_argument("pdf_path", help="Path to the PDF file.")
    parser.add_argument("output_path", help="Path to save the output JSON map.")
    args = parser.parse_args()

    # Directly call the generation function without checking for existing files.
    # This ensures that we can re-run the script to overwrite the map.
    generate_structure_map(args.pdf_path, args.output_path) 