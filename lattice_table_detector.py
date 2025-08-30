from typing import List, Dict, Any, Tuple, Set
import numpy as np
from collections import defaultdict

def find_lattice_tables(page_elements: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    基于线条封闭空间检测lattice表格
    
    算法步骤:
    1. 提取所有水平线和垂直线
    2. 找出所有线条交叉点
    3. 识别封闭单元格
    4. 将相邻的封闭单元格组合成表格
    
    Args:
        page_elements: 页面元素列表，包含线条、文本块等
        
    Returns:
        检测到的lattice表格列表
    """
    print("开始基于线条封闭空间检测lattice表格...")
    
    # 1. 提取所有水平线和垂直线
    h_lines = [line for line in page_elements if 
               (line.get('type') == 'line' and 
                (line.get('geom_type') == 'line_horizontal' or 
                 (line.get('top') == line.get('bottom', line.get('top'))))) or
               (line.get('type') == 'rect' and 
                line.get('geom_type') == 'line_horizontal')]
    
    v_lines = [line for line in page_elements if 
               (line.get('type') == 'line' and 
                (line.get('geom_type') == 'line_vertical' or 
                 (line.get('x0') == line.get('x1')))) or
               (line.get('type') == 'rect' and 
                line.get('geom_type') == 'line_vertical')]
    
    print(f"  - 找到 {len(h_lines)} 条水平线和 {len(v_lines)} 条垂直线")
    
    if len(h_lines) < 2 or len(v_lines) < 2:
        print("  - 水平线或垂直线数量不足，无法形成lattice表格")
        return []
    
    # 计算页面中所有线条的边界
    all_lines = h_lines + v_lines
    if all_lines:
        page_min_x = min(line['x0'] for line in all_lines)
        page_max_x = max(line['x1'] for line in all_lines)
        page_min_y = min(line['top'] for line in all_lines)
        page_max_y = max(line.get('bottom', line['top']) for line in all_lines)
        print(f"  - 页面线条边界: ({page_min_x}, {page_min_y}) - ({page_max_x}, {page_max_y})")
    
    # 2. 找出所有线条交叉点
    intersections = find_line_intersections(h_lines, v_lines)
    print(f"  - 找到 {len(intersections)} 个线条交叉点")
    
    # 如果交叉点太少，可能不是表格
    if len(intersections) < 4:
        print("  - 交叉点数量不足，无法形成lattice表格")
        return []
    
    # 3. 识别封闭单元格
    cells = find_closed_cells(h_lines, v_lines, intersections)
    print(f"  - 找到 {len(cells)} 个封闭单元格")
    
    if not cells:
        print("  - 未找到封闭单元格，无法形成lattice表格")
        return []
    
    # 4. 将相邻的封闭单元格组合成表格
    tables = group_cells_into_tables(cells)
    print(f"  - 组合成 {len(tables)} 个lattice表格")
    
    # 5. 构建最终的表格数据
    final_tables = []
    
    # 记录已处理的区域，避免重复检测
    processed_areas = []
    
    for i, table_cells in enumerate(tables):
        # 过滤掉太小的表格（少于2个单元格）
        if len(table_cells) < 2:
            continue
            
        # 计算表格边界 - 首先基于单元格
        min_x = min(cell[0][0] for cell in table_cells)
        min_y = min(cell[0][1] for cell in table_cells)
        max_x = max(cell[1][0] for cell in table_cells)
        max_y = max(cell[1][1] for cell in table_cells)
        
        # 检查是否与已处理的区域重叠
        is_overlapping = False
        for area in processed_areas:
            area_min_x, area_min_y, area_max_x, area_max_y = area
            # 如果两个矩形有重叠
            if (max(min_x, area_min_x) < min(max_x, area_max_x) and 
                max(min_y, area_min_y) < min(max_y, area_max_y)):
                overlap_area = (min(max_x, area_max_x) - max(min_x, area_min_x)) * (min(max_y, area_max_y) - max(min_y, area_min_y))
                table_area = (max_x - min_x) * (max_y - min_y)
                area_area = (area_max_x - area_min_x) * (area_max_y - area_min_y)
                
                # 如果重叠面积超过任一区域的50%，则认为是重复表格
                if overlap_area > 0.5 * min(table_area, area_area):
                    is_overlapping = True
                    break
        
        if is_overlapping:
            continue
            
        # 找出与表格相关的所有线条（包括水平线和垂直线）
        h_lines_in_table = []
        v_lines_in_table = []
        
        # 检查水平线
        for line in h_lines:
            # 水平线与表格区域有交集
            if (min_x <= line['x1'] and line['x0'] <= max_x and 
                min_y <= line['top'] <= max_y):
                h_lines_in_table.append(line)
        
        # 检查垂直线
        for line in v_lines:
            # 垂直线与表格区域有交集
            if (min_y <= line.get('bottom', line['top']) and line['top'] <= max_y and 
                min_x <= line['x0'] <= max_x):
                v_lines_in_table.append(line)
        
        # 扩展表格边界，确保包含所有相关线条
        if h_lines_in_table:
            min_x = min(min_x, min(line['x0'] for line in h_lines_in_table))
            max_x = max(max_x, max(line['x1'] for line in h_lines_in_table))
        
        if v_lines_in_table:
            min_y = min(min_y, min(line['top'] for line in v_lines_in_table))
            max_y = max(max_y, max(line.get('bottom', line['top']) for line in v_lines_in_table))
        
        # 特殊处理：检查表格边界附近的线条（可能是表格的边框线）
        for line in h_lines:
            # 如果水平线在表格上边界或下边界附近
            if ((abs(line['top'] - min_y) < 5 or abs(line['top'] - max_y) < 5) and
                line['x0'] <= max_x and line['x1'] >= min_x):
                min_x = min(min_x, line['x0'])
                max_x = max(max_x, line['x1'])
                if abs(line['top'] - min_y) < 5:
                    min_y = min(min_y, line['top'])
                if abs(line['top'] - max_y) < 5:
                    max_y = max(max_y, line['top'])
        
        for line in v_lines:
            # 如果垂直线在表格左边界或右边界附近
            if ((abs(line['x0'] - min_x) < 5 or abs(line['x0'] - max_x) < 5) and
                line['top'] <= max_y and line.get('bottom', line['top']) >= min_y):
                min_y = min(min_y, line['top'])
                max_y = max(max_y, line.get('bottom', line['top']))
                if abs(line['x0'] - min_x) < 5:
                    min_x = min(min_x, line['x0'])
                if abs(line['x0'] - max_x) < 5:
                    max_x = max(max_x, line['x0'])
        
        # 收集表格内的几何元素
        table_bbox = (min_x, min_y, max_x, max_y)
        geoms_inside = []
        
        # 收集所有与表格有交集的线条
        for line in all_lines:
            # 水平线与表格有交集
            if line in h_lines and min_x <= line['x1'] and line['x0'] <= max_x and min_y <= line['top'] <= max_y:
                geoms_inside.append({
                    "x0": line["x0"], 
                    "top": line["top"], 
                    "x1": line["x1"], 
                    "bottom": line.get("bottom", line["top"]), 
                    "geom_type": line.get("geom_type", "line")
                })
            # 垂直线与表格有交集
            elif line in v_lines and min_y <= line.get('bottom', line['top']) and line['top'] <= max_y and min_x <= line['x0'] <= max_x:
                geoms_inside.append({
                    "x0": line["x0"], 
                    "top": line["top"], 
                    "x1": line["x1"], 
                    "bottom": line.get("bottom", line["top"]), 
                    "geom_type": line.get("geom_type", "line")
                })
        
        # 检查表格内是否有文本元素
        text_blocks_inside = [
            elem for elem in page_elements 
            if elem.get('type') == 'text_block' and
            max(table_bbox[0], elem['bbox'][0]) < min(table_bbox[2], elem['bbox'][2]) and
            max(table_bbox[1], elem['bbox'][1]) < min(table_bbox[3], elem['bbox'][3])
        ]
        
        # 只有当表格内有文本元素时，或单元格数量足够多时，才认为是有效表格
        if text_blocks_inside or len(table_cells) >= 4:
            # 构建表格数据
            final_tables.append({
                "type": "table",
                "bbox": table_bbox,
                "parsing_strategy": "lattice",
                "reason": f"Found by lattice analysis ({len(table_cells)} cells)",
                "geometries": geoms_inside
            })
            
            # 记录已处理的区域
            processed_areas.append(table_bbox)
    
    return final_tables

def find_line_intersections(h_lines: List[Dict[str, Any]], v_lines: List[Dict[str, Any]]) -> List[Tuple[float, float]]:
    """
    找出所有水平线和垂直线的交叉点
    
    Args:
        h_lines: 水平线列表
        v_lines: 垂直线列表
        
    Returns:
        交叉点列表，每个交叉点为 (x, y) 坐标
    """
    intersections = []
    
    for h_line in h_lines:
        h_y = h_line['top']  # 水平线的y坐标
        h_x0 = h_line['x0']
        h_x1 = h_line['x1']
        
        for v_line in v_lines:
            v_x = v_line['x0']  # 垂直线的x坐标
            v_y0 = v_line['top']
            v_y1 = v_line.get('bottom', v_line['top'])
            
            # 严格检查线条是否相交（无容差）
            if h_x0 <= v_x <= h_x1 and v_y0 <= h_y <= v_y1:
                intersections.append((v_x, h_y))
    
    # 去除完全重复的交叉点
    unique_intersections = []
    for point in intersections:
        if point not in unique_intersections:
            unique_intersections.append(point)
    
    return unique_intersections

def find_closed_cells(h_lines: List[Dict[str, Any]], v_lines: List[Dict[str, Any]], 
                     intersections: List[Tuple[float, float]]) -> List[Tuple[Tuple[float, float], Tuple[float, float]]]:
    """
    识别封闭单元格
    
    Args:
        h_lines: 水平线列表
        v_lines: 垂直线列表
        intersections: 交叉点列表
        
    Returns:
        封闭单元格列表，每个单元格由左上角和右下角坐标表示
    """
    # 将交叉点按坐标排序
    sorted_x = sorted(set(x for x, _ in intersections))
    sorted_y = sorted(set(y for _, y in intersections))
    
    # 检查相邻交叉点之间是否有线条连接
    cells = []
    
    for i in range(len(sorted_x) - 1):
        for j in range(len(sorted_y) - 1):
            x1, y1 = sorted_x[i], sorted_y[j]       # 左上角
            x2, y2 = sorted_x[i+1], sorted_y[j+1]   # 右下角
            
            # 计算单元格大小
            cell_width = x2 - x1
            cell_height = y2 - y1
            
            # 忽略过小的单元格
            if cell_width < 1 or cell_height < 1:
                continue
            
            # 严格检查四条边是否都有线条（无容差）
            top_edge = any(
                h['top'] == y1 and 
                h['x0'] <= x1 and 
                h['x1'] >= x2 
                for h in h_lines
            )
            
            bottom_edge = any(
                h['top'] == y2 and 
                h['x0'] <= x1 and 
                h['x1'] >= x2 
                for h in h_lines
            )
            
            left_edge = any(
                v['x0'] == x1 and 
                v['top'] <= y1 and 
                v.get('bottom', v['top']) >= y2 
                for v in v_lines
            )
            
            right_edge = any(
                v['x0'] == x2 and 
                v['top'] <= y1 and 
                v.get('bottom', v['top']) >= y2 
                for v in v_lines
            )
            
            # 允许一定的宽容度：如果至少有3条边，也认为是封闭单元格
            edges_count = sum([top_edge, bottom_edge, left_edge, right_edge])
            if edges_count >= 3:  # 至少3条边
                cells.append(((x1, y1), (x2, y2)))
    
    return cells

def group_cells_into_tables(cells: List[Tuple[Tuple[float, float], Tuple[float, float]]]) -> List[List[Tuple[Tuple[float, float], Tuple[float, float]]]]:
    """
    将相邻的封闭单元格组合成表格
    
    Args:
        cells: 封闭单元格列表
        
    Returns:
        表格列表，每个表格是一组单元格
    """
    if not cells:
        return []
    
    # 使用并查集算法将相邻单元格分组
    parent = {}
    
    def find(cell):
        if cell not in parent:
            parent[cell] = cell
        if parent[cell] != cell:
            parent[cell] = find(parent[cell])
        return parent[cell]
    
    def union(cell1, cell2):
        parent[find(cell1)] = find(cell2)
    
    # 初始化并查集
    for cell in cells:
        parent[cell] = cell
    
    # 合并相邻单元格
    for i, cell1 in enumerate(cells):
        for cell2 in cells[i+1:]:
            # 检查两个单元格是否相邻
            if are_cells_adjacent(cell1, cell2):
                union(cell1, cell2)
    
    # 将单元格分组
    groups = defaultdict(list)
    for cell in cells:
        groups[find(cell)].append(cell)
    
    # 过滤掉太小的组（少于2个单元格）
    return [group for group in groups.values() if len(group) >= 2]

def are_cells_adjacent(cell1: Tuple[Tuple[float, float], Tuple[float, float]], 
                      cell2: Tuple[Tuple[float, float], Tuple[float, float]]) -> bool:
    """
    检查两个单元格是否相邻
    
    Args:
        cell1: 第一个单元格
        cell2: 第二个单元格
        
    Returns:
        如果单元格相邻则返回True，否则返回False
    """
    # 提取单元格坐标
    (x1_1, y1_1), (x2_1, y2_1) = cell1
    (x1_2, y1_2), (x2_2, y2_2) = cell2
    
    # 检查单元格是否共享一条边（严格检查，无容差）
    
    # 水平相邻（左右相邻）
    if (x2_1 == x1_2 or x2_2 == x1_1) and max(y1_1, y1_2) < min(y2_1, y2_2):
        return True
    
    # 垂直相邻（上下相邻）
    if (y2_1 == y1_2 or y2_2 == y1_1) and max(x1_1, x1_2) < min(x2_1, x2_2):
        return True
    
    # 检查单元格是否共享一个角点
    corners1 = [(x1_1, y1_1), (x2_1, y1_1), (x1_1, y2_1), (x2_1, y2_1)]
    corners2 = [(x1_2, y1_2), (x2_2, y1_2), (x1_2, y2_2), (x2_2, y2_2)]
    
    for c1 in corners1:
        for c2 in corners2:
            if c1[0] == c2[0] and c1[1] == c2[1]:
                return True
    
    return False

def visualize_table_detection(page_elements, cells, output_path=None):
    """
    可视化表格检测结果（用于调试）
    
    Args:
        page_elements: 页面元素列表
        cells: 检测到的单元格列表
        output_path: 输出文件路径
    """
    try:
        import matplotlib.pyplot as plt
        from matplotlib.patches import Rectangle
        
        # 创建图形
        fig, ax = plt.subplots(figsize=(10, 14))
        
        # 绘制所有线条
        for elem in page_elements:
            if elem.get('type') == 'line' or (elem.get('type') == 'rect' and elem.get('geom_type', '').startswith('line_')):
                x0, top = elem['x0'], elem['top']
                x1, bottom = elem['x1'], elem.get('bottom', elem['top'])
                
                if elem.get('geom_type') == 'line_horizontal' or (elem.get('top') == elem.get('bottom', elem.get('top'))):
                    ax.plot([x0, x1], [top, top], 'b-', linewidth=0.5)
                elif elem.get('geom_type') == 'line_vertical' or (elem.get('x0') == elem.get('x1')):
                    ax.plot([x0, x0], [top, bottom], 'g-', linewidth=0.5)
        
        # 绘制检测到的单元格
        for cell in cells:
            (x1, y1), (x2, y2) = cell
            width, height = x2 - x1, y2 - y1
            ax.add_patch(Rectangle((x1, y1), width, height, fill=False, edgecolor='r', linewidth=0.8))
        
        # 设置坐标轴
        ax.set_xlim(0, 1000)  # 根据实际PDF尺寸调整
        ax.set_ylim(1000, 0)  # 注意y轴反转，使得坐标系与PDF一致
        ax.set_aspect('equal')
        ax.set_title('Table Detection Visualization')
        
        # 保存或显示图像
        if output_path:
            plt.savefig(output_path, dpi=300, bbox_inches='tight')
            print(f"可视化结果已保存到: {output_path}")
        else:
            plt.show()
        
        plt.close()
    
    except ImportError:
        print("无法导入matplotlib，跳过可视化")
    except Exception as e:
        print(f"可视化过程中出错: {str(e)}") 