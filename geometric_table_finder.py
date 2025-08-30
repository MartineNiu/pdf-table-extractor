from typing import List, Dict, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from pdfplumber.page import Page

# 导入新的lattice表格检测算法
from lattice_table_detector import find_lattice_tables

def find_geometric_tables(page: "Page", page_elements: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Finds tables using a hybrid geometric approach.
    1. Uses page.find_tables() for initial candidates.
    2. Classifies candidates as 'lattice' or 'stream'.
    3. Applies different expansion logic for each type:
        - 'lattice': Expands to the max boundary of ALL nearby lines/rects.
        - 'stream': Expands HORIZONTALLY based on the max width of stitched horizontal
                    lines and text blocks within the table's vertical range.
    4. Stores the geometric elements that define the table in the final map.
    """
    lines = page.lines
    rects = page.rects
    
    print(f"    - DEBUG: Found {len(lines)} lines and {len(rects)} rectangles on page {page.page_number}")
    
    # 尝试检测线条被错误分类为矩形的情况
    thin_rects = [r for r in rects if (r['width'] > 5 and r['height'] <= 1) or (r['height'] > 5 and r['width'] <= 1)]
    if thin_rects:
        print(f"    - DEBUG: Found {len(thin_rects)} thin rectangles that might be lines")
    
    all_geoms = []
    for l in lines:
        # 判断线条是水平还是垂直
        # 注意：有些线条已经有geom_type属性，但可能是'line'
        width = l['x1'] - l['x0']
        height = l.get('bottom', l['top']) - l['top']
        
        # 修改：处理宽度或高度为0的情况，以及已有geom_type的情况
        if 'geom_type' not in l or l['geom_type'] == 'line':
            if l['x0'] == l['x1']:  # 完全垂直的线
                l['geom_type'] = 'line_vertical'
            elif l['top'] == l.get('bottom', l['top']):  # 完全水平的线
                l['geom_type'] = 'line_horizontal'
            elif width > height:  # 更宽的线条视为水平线
                l['geom_type'] = 'line_horizontal'
            else:  # 更高的线条视为垂直线
                l['geom_type'] = 'line_vertical'
        
        all_geoms.append(l)
    
    for r in rects:
        # 自动将非常细长的矩形识别为线条
        if (r['width'] > 5 and r['height'] <= 1):
            r['geom_type'] = 'line_horizontal'
            print(f"    - DEBUG: Reclassified thin horizontal rectangle as line: {r['x0']},{r['top']} -> {r['x1']},{r.get('bottom', r['top'])}")
        elif (r['height'] > 5 and r['width'] <= 1):
            r['geom_type'] = 'line_vertical'
            print(f"    - DEBUG: Reclassified thin vertical rectangle as line: {r['x0']},{r['top']} -> {r['x1']},{r.get('bottom', r['top'])}")
        else:
            r['geom_type'] = 'rect'
        all_geoms.append(r)

    # 1. 首先尝试使用新的基于线条封闭空间的lattice表格检测算法
    lattice_tables = find_lattice_tables(all_geoms + page_elements)
    if lattice_tables:
        print(f"    - DEBUG: 使用线条封闭空间算法找到 {len(lattice_tables)} 个lattice表格")
        return lattice_tables
    
    # 2. 如果新算法没有找到表格，回退到原始算法
    print(f"    - DEBUG: 线条封闭空间算法未找到表格，回退到原始算法")
    
    table_candidates = page.find_tables()
    print(f"    - DEBUG: Found {len(table_candidates)} initial table candidates")

    expanded_candidates = []
    for cand in table_candidates:
        cand_bbox = list(cand.bbox)
        
        # --- Classify table to decide expansion strategy ---
        geoms_inside = [g for g in all_geoms if max(cand_bbox[0], g['x0']) < min(cand_bbox[2], g['x1']) and max(cand_bbox[1], g['top']) < min(cand_bbox[3], g.get('bottom', g['top']))]
        
        # 修改：调整垂直几何元素计数逻辑，包含x0=x1的线条
        v_geoms_count = sum(1 for g in geoms_inside if 
                          g.get('geom_type') == 'line_vertical' or 
                          g['x0'] == g['x1'] or  # 完全垂直的线
                          (g.get('height', 1) > g.get('width', 0) and g.get('width', 0) < 5))
        
        parsing_strategy = "lattice" if v_geoms_count >= 2 else "stream"

        # --- Expand bounding box based on strategy ---
        search_bbox = (cand_bbox[0] - 10, cand_bbox[1] - 10, cand_bbox[2] + 10, cand_bbox[3] + 10)
        nearby_geoms = [g for g in all_geoms if max(search_bbox[0], g['x0']) < min(search_bbox[2], g['x1']) and max(search_bbox[1], g['top']) < min(search_bbox[3], g.get('bottom', g['top']))]

        if not nearby_geoms:
            expanded_bbox = tuple(cand_bbox)
        else:
            if parsing_strategy == 'lattice':
                geom_x0 = min(g['x0'] for g in nearby_geoms)
                geom_top = min(g['top'] for g in nearby_geoms)
                geom_x1 = max(g['x1'] for g in nearby_geoms)
                geom_bottom = max(g.get('bottom', g['top']) for g in nearby_geoms)
                expanded_bbox = (min(cand_bbox[0], geom_x0), min(cand_bbox[1], geom_top), max(cand_bbox[2], geom_x1), max(cand_bbox[3], geom_bottom))
            else:  # stream strategy - optimized
                # Use the candidate's vertical range to define a slice of the page
                table_top, table_bottom = cand_bbox[1], cand_bbox[3]

                # 1. 增大搜索范围，确保获取更多可能属于表格的水平线
                extended_search_bbox = (
                    cand_bbox[0] - 50,  # 水平方向扩大50个单位
                    table_top - 10,     # 垂直方向略微扩展
                    cand_bbox[2] + 50,  # 水平方向扩大50个单位
                    table_bottom + 10   # 垂直方向略微扩展
                )
                
                # 2. 获取扩展范围内的所有几何元素
                extended_geoms = [g for g in all_geoms if 
                                max(extended_search_bbox[0], g['x0']) < min(extended_search_bbox[2], g['x1']) and 
                                max(extended_search_bbox[1], g['top']) < min(extended_search_bbox[3], g.get('bottom', g['top']))]
                
                # 3. 筛选出扩展范围内的水平线和矩形
                # 修改：水平线条判断逻辑，包含top=bottom的线条
                h_lines_in_ext_range = [g for g in extended_geoms if 
                                    g.get('geom_type') == 'line_horizontal' or
                                    g['top'] == g.get('bottom', g['top']) or  # 完全水平的线
                                    (g.get('width', 0) > g.get('height', 1) and g.get('width', 0) > 5)]
                
                print(f"    - DEBUG: Found {len(h_lines_in_ext_range)} horizontal lines for stream table")
                if len(h_lines_in_ext_range) > 0:
                    print(f"    - DEBUG: Sample horizontal line: {h_lines_in_ext_range[0]}")
                
                # 4. 计算水平线的最大范围
                if h_lines_in_ext_range:
                    # 获取表格区域内所有水平线的左右边界
                    all_h_lines_x0 = [g['x0'] for g in h_lines_in_ext_range]
                    all_h_lines_x1 = [g['x1'] for g in h_lines_in_ext_range]
                    
                    # 统计水平线的左右边界分布，用于识别表格真实边界
                    # 这有助于处理有些行内可能有多段水平线的情况
                    from collections import Counter
                    x0_counter = Counter(round(x, 1) for x in all_h_lines_x0)
                    x1_counter = Counter(round(x, 1) for x in all_h_lines_x1)
                    
                    # 找出最频繁出现的左右边界值（可能是表格的真实边界）
                    common_x0 = x0_counter.most_common(2)
                    common_x1 = x1_counter.most_common(2)
                    
                    # 如果有明显的边界模式，使用最常见的边界值
                    if common_x0 and common_x0[0][1] >= 2:  # 至少出现2次
                        line_x0 = common_x0[0][0]
                    else:
                        line_x0 = min(all_h_lines_x0)
                        
                    if common_x1 and common_x1[0][1] >= 2:  # 至少出现2次
                        line_x1 = common_x1[0][0]
                    else:
                        line_x1 = max(all_h_lines_x1)
                else:
                    line_x0, line_x1 = cand_bbox[0], cand_bbox[2]

                # 5. 同时考虑文本块的范围
                text_blocks_in_slice = [el for el in page_elements if 
                                      el['type'] == 'text_block' and 
                                      max(table_top, el['bbox'][1]) < min(table_bottom, el['bbox'][3])]
                
                # 6. 处理合并单元格问题 - 分析文本块宽度分布
                if text_blocks_in_slice:
                    # 计算所有文本块的宽度
                    text_block_widths = [(tb['bbox'][2] - tb['bbox'][0]) for tb in text_blocks_in_slice]
                    avg_width = sum(text_block_widths) / len(text_block_widths) if text_block_widths else 0
                    
                    # 识别可能是合并单元格的宽文本块（宽度显著大于平均值）
                    merged_cell_candidates = [
                        tb for tb in text_blocks_in_slice 
                        if (tb['bbox'][2] - tb['bbox'][0]) > avg_width * 1.8  # 宽度是平均值的1.8倍以上
                    ]
                    
                    # 使用标准文本块（非合并单元格）确定左右边界
                    standard_blocks = [
                        tb for tb in text_blocks_in_slice 
                        if tb not in merged_cell_candidates
                    ]
                    
                    if standard_blocks:
                        text_x0 = min(tb['bbox'][0] for tb in standard_blocks)
                        text_x1 = max(tb['bbox'][2] for tb in standard_blocks)
                    else:
                        # 如果没有标准块，使用所有文本块
                        text_x0 = min(tb['bbox'][0] for tb in text_blocks_in_slice)
                        text_x1 = max(tb['bbox'][2] for tb in text_blocks_in_slice)
                else:
                    text_x0, text_x1 = cand_bbox[0], cand_bbox[2]
                
                # 7. 最终确定表格边界，优先使用水平线的边界
                # 修改：避免除以0的情况
                text_width = text_x1 - text_x0
                line_width = line_x1 - line_x0
                if h_lines_in_ext_range and (text_width == 0 or line_width >= text_width * 0.7):
                    final_x0 = line_x0
                    final_x1 = line_x1
                else:
                    # 否则结合使用文本块和水平线的信息
                    final_x0 = min(line_x0, text_x0)
                    final_x1 = max(line_x1, text_x1)
                
                expanded_bbox = (final_x0, table_top, final_x1, table_bottom)
        
        expanded_candidates.append({"bbox": expanded_bbox, "parsing_strategy": parsing_strategy})

    # --- Merge overlapping candidates post-expansion ---
    merged_candidates = []
    if expanded_candidates:
        expanded_candidates.sort(key=lambda t: (t['bbox'][1], t['bbox'][0]))
        current_table = expanded_candidates[0]
        for i in range(1, len(expanded_candidates)):
            next_table = expanded_candidates[i]
            box1, box2 = current_table['bbox'], next_table['bbox']
            if max(box1[0], box2[0]) < min(box1[2], box2[2]) and max(box1[1], box2[1]) < min(box1[3], box2[3]):
                current_table['bbox'] = (min(box1[0], box2[0]), min(box1[1], box2[1]), max(box1[2], box2[2]), max(box1[3], box2[3]))
                if next_table['parsing_strategy'] == 'lattice':
                    current_table['parsing_strategy'] = 'lattice'
            else:
                merged_candidates.append(current_table)
                current_table = next_table
        merged_candidates.append(current_table)

    # --- Final validation and data packaging ---
    final_tables = []
    for table_info in merged_candidates:
        table_bbox = table_info['bbox']
        geoms_inside_final = [g for g in all_geoms if max(table_bbox[0], g['x0']) < min(table_bbox[2], g['x1']) and max(table_bbox[1], g['top']) < min(table_bbox[3], g.get('bottom', g['top']))]

        if not geoms_inside_final or not (table_bbox[0] >= page.bbox[0] and table_bbox[1] >= page.bbox[1] and table_bbox[2] <= page.bbox[2] and table_bbox[3] <= page.bbox[3]):
            continue

        # 修改：调整水平和垂直几何元素的计数逻辑
        h_geoms_count = sum(1 for g in geoms_inside_final if 
                          g.get('geom_type') == 'line_horizontal' or
                          g['top'] == g.get('bottom', g['top']) or  # 完全水平的线
                          (g.get('width', 0) > g.get('height', 1)))
        
        v_geoms_count = sum(1 for g in geoms_inside_final if 
                          g.get('geom_type') == 'line_vertical' or
                          g['x0'] == g['x1'] or  # 完全垂直的线
                          (g.get('height', 1) > g.get('width', 0)))

        packaged_geoms = [{"x0": g["x0"], "top": g["top"], "x1": g["x1"], "bottom": g.get("bottom", g["top"]), "geom_type": g["geom_type"]} for g in geoms_inside_final]

        final_tables.append({
            "type": "table",
            "bbox": table_bbox,
            "parsing_strategy": table_info['parsing_strategy'],
            "reason": f"Found by geometric analysis ({h_geoms_count}h/{v_geoms_count}v geoms)",
            "geometries": packaged_geoms
        })

    print(f"    - (Geometric) Found {len(final_tables)} potential tables on page {page.page_number}.")
    return final_tables 