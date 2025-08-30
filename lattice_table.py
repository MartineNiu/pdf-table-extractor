import pdfplumber
import json
import csv
import os
import sys
import re
import copy
from collections import defaultdict

def extract_lattice_tables(pdf_path, map_path, output_dir, merge_tables=True):
    """
    从PDF文件中提取lattice类型表格
    优化逻辑:
    1. 直接使用pdfplumber的extract_table获取表格结构
    2. 智能处理居中文本导致的额外列和行问题
    3. 将表格的四角坐标放到文件名中
    4. 支持跨页表格的合并
    
    参数:
        pdf_path: PDF文件路径
        map_path: 结构地图文件路径
        output_dir: 输出目录
        merge_tables: 是否合并跨页表格，默认为True
    """
    print(f"--- 开始提取lattice表格 ---")
    print(f"PDF文件: {pdf_path}")
    print(f"结构地图: {map_path}")
    print(f"输出目录: {output_dir}")
    print(f"合并跨页表格: {merge_tables}")
    
    # 加载地图文件
    try:
        with open(map_path, 'r', encoding='utf-8') as f:
            structure_map = json.load(f)
    except FileNotFoundError:
        print(f"错误: 找不到地图文件 {map_path}")
        sys.exit(1)
        
    # 检查并创建输出目录
    if not os.path.exists(output_dir):
        print(f"输出目录 {output_dir} 不存在，正在创建...")
        os.makedirs(output_dir)

    extraction_count = 0
    
    # 存储所有提取的表格信息
    all_tables = []
    
    # 存储页面方向信息
    page_orientations = {}
    
    # 打开PDF文件
    with pdfplumber.open(pdf_path) as pdf:
        # 处理地图中的每一页
        pages_data = structure_map.get('pages', [structure_map]) if 'pages' in structure_map else [structure_map]
        
        for page_data in pages_data:
            page_num = page_data.get('page_number')
            if not page_num:
                continue
                
            print(f"处理第 {page_num} 页...")
            
            # 确保页码在PDF范围内
            if page_num > len(pdf.pages):
                print(f"警告: 地图中的页码 {page_num} 超出PDF页数范围")
                continue
            
            # 获取页面方向
            dimensions = page_data.get('dimensions', [0, 0])
            is_portrait = dimensions[0] < dimensions[1] if len(dimensions) >= 2 else True
            page_orientations[page_num] = 'portrait' if is_portrait else 'landscape'
            print(f"  页面方向: {'纵向' if is_portrait else '横向'} (dimensions: {dimensions})")
            
            # 获取页面元素
            all_elements = page_data.get('elements', [])
            text_blocks = [el for el in all_elements if el.get('type') == 'text_block']
            
            # 提取所有词元
            all_words = []
            for block in text_blocks:
                if 'words' in block:
                    all_words.extend(block['words'])
            
            # 获取PDF页面
            page = pdf.pages[page_num - 1]
            
            # 在当前页面搜索lattice表格
            table_index_on_page = 0
            for element in all_elements:
                if element.get('type') == 'table' and element.get('parsing_strategy') == 'lattice':
                    table_index_on_page += 1
                    bbox = element['bbox']
                    
                    print(f"  - 找到lattice表格 {table_index_on_page} 在第 {page_num} 页")
                    
                    # 裁剪表格区域
                    table_area = page.crop(bbox)
                    
                    try:
                        # 获取表格区域内的词元
                        table_words = [word for word in all_words if is_word_in_bbox(word, bbox)]
                        
                        if not table_words:
                            print(f"    警告: 表格区域内未找到词元")
                            continue
                            
                        print(f"    - 找到表格区域内的词元: {len(table_words)}个")
                        
                        # 估计表格的实际列数（基于词元分布）
                        estimated_cols = estimate_table_columns(table_words)
                        print(f"    - 估计表格实际列数: {estimated_cols}")
                        
                        # 直接使用pdfplumber的extract_table获取表格结构
                        table_settings = {
                            "vertical_strategy": "lines", 
                            "horizontal_strategy": "lines"
                        }
                        table_data = table_area.extract_table(table_settings)
                        
                        if not table_data:
                            print(f"    警告: 无法提取表格数据")
                            continue
                        
                        # 获取提取的表格列数
                        extracted_cols = max(len(row) for row in table_data)
                        print(f"    - 提取到的表格列数: {extracted_cols}")
                        
                        # 处理表格数据，修复居中文本问题
                        processed_table = fix_centered_text_issues(table_data, estimated_cols)
                        
                        # 获取处理后的实际最大列数
                        processed_max_cols = max(len(row) for row in processed_table)
                        print(f"    - 处理后的表格列数: {processed_max_cols}")
                        
                        # 将表格信息保存到内存中
                        table_info = {
                            'page_num': page_num,
                            'table_index': table_index_on_page,
                            'bbox': bbox,
                            'data': processed_table,
                            'max_cols': processed_max_cols,  # 使用处理后的最大列数
                            'orientation': page_orientations[page_num]  # 添加页面方向信息
                        }
                        all_tables.append(table_info)
                        
                        extraction_count += 1
                        
                    except Exception as e:
                        print(f"    提取表格时出错: {e}")
                        import traceback
                        print(traceback.format_exc())

    print(f"--- 提取完成。共提取lattice表格: {extraction_count} 个 ---")
    
    # 如果需要合并表格且有足够的表格
    if merge_tables and len(all_tables) > 1:
        print("开始处理跨页表格合并...")
        merged_tables = merge_cross_page_tables(all_tables, page_orientations)
        
        # 保存所有表格（合并后的）
        for table_info in merged_tables:
            save_table_with_coordinates_in_filename(
                table_info['data'], 
                table_info['bbox'], 
                table_info['page_num'], 
                table_info['table_index'], 
                output_dir,
                is_merged=table_info.get('is_merged', False),
                merged_pages=table_info.get('merged_pages', [])
            )
    else:
        # 直接保存所有表格
        for table_info in all_tables:
            save_table_with_coordinates_in_filename(
                table_info['data'], 
                table_info['bbox'], 
                table_info['page_num'], 
                table_info['table_index'], 
                output_dir
            )


def merge_cross_page_tables(all_tables, page_orientations):
    """
    合并跨页表格
    
    合并条件:
    1. 表格位于相邻页面
    2. 页面方向相同（横向只与横向合并，纵向只与纵向合并）
    3. 前一页表格的y1值在同方向页面的表格中最大（即最底部）或接近最大值
    4. 后一页表格的y0值在同方向页面的表格中最小（即最顶部）或接近最小值
    5. 表格的最大列数相等
    
    参数:
        all_tables: 所有提取的表格信息列表
        page_orientations: 页面方向信息字典
    
    返回:
        合并后的表格列表
    """
    if not all_tables:
        return []
    
    # 创建表格的副本，避免修改原始数据
    all_tables = [copy.deepcopy(table) for table in all_tables]
    
    # 为每个表格创建唯一ID
    for table in all_tables:
        table_id = (table['page_num'], table['table_index'])
        table['id'] = table_id
    
    # 按页码排序表格
    all_tables.sort(key=lambda x: (x['page_num'], x['bbox'][1]))
    
    # 按页面方向分组表格
    portrait_tables = [t for t in all_tables if t['orientation'] == 'portrait']
    landscape_tables = [t for t in all_tables if t['orientation'] == 'landscape']
    
    print(f"纵向页面表格数量: {len(portrait_tables)}")
    print(f"横向页面表格数量: {len(landscape_tables)}")
    
    # 按页码分组表格
    tables_by_page = defaultdict(list)
    for table in all_tables:
        tables_by_page[table['page_num']].append(table)
    
    # 获取各方向表格中的最小y0和最大y1值
    portrait_y0_values = [table['bbox'][1] for table in portrait_tables]
    portrait_y1_values = [table['bbox'][3] for table in portrait_tables]
    landscape_y0_values = [table['bbox'][1] for table in landscape_tables]
    landscape_y1_values = [table['bbox'][3] for table in landscape_tables]
    
    min_portrait_y0 = min(portrait_y0_values) if portrait_y0_values else 0
    max_portrait_y1 = max(portrait_y1_values) if portrait_y1_values else 0
    min_landscape_y0 = min(landscape_y0_values) if landscape_y0_values else 0
    max_landscape_y1 = max(landscape_y1_values) if landscape_y1_values else 0
    
    # 找出每页最底部的表格（y1最大）
    bottom_tables_by_page = {}
    for page_num, tables in tables_by_page.items():
        if tables:
            # 找出y1最大的表格
            bottom_table = max(tables, key=lambda x: x['bbox'][3])
            bottom_tables_by_page[page_num] = bottom_table
    
    # 找出每页最顶部的表格（y0最小）
    top_tables_by_page = {}
    for page_num, tables in tables_by_page.items():
        if tables:
            # 找出y0最小的表格
            top_table = min(tables, key=lambda x: x['bbox'][1])
            top_tables_by_page[page_num] = top_table
    
    # 创建合并后的表格列表
    merged_tables = []
    
    # 已处理的表格ID集合
    processed_table_ids = set()
    
    # 设置y0和y1的容差值（可根据实际情况调整）
    y0_tolerance = 2  # y0的容差值
    y1_tolerance = 12  # y1的容差值
    
    # 打印所有表格的关键信息，帮助调试
    print("\n--- 表格信息摘要 ---")
    for table in all_tables:
        print(f"页码: {table['page_num']}, 索引: {table['table_index']}, "
              f"方向: {table['orientation']}, "
              f"y0: {table['bbox'][1]}, y1: {table['bbox'][3]}, "
              f"列数: {table['max_cols']}")
    print(f"纵向页面 - 全局最小y0: {min_portrait_y0}, 全局最大y1: {max_portrait_y1}")
    print(f"横向页面 - 全局最小y0: {min_landscape_y0}, 全局最大y1: {max_landscape_y1}")
    print("-------------------\n")
    
    # 遍历页码
    page_nums = sorted(tables_by_page.keys())
    
    # 检查相邻页面的表格是否应该合并
    for i in range(len(page_nums) - 1):
        current_page = page_nums[i]
        next_page = page_nums[i + 1]
        
        # 如果不是连续页码，跳过
        if next_page != current_page + 1:
            continue
        
        # 获取当前页的所有表格
        current_page_tables = tables_by_page[current_page]
        next_page_tables = tables_by_page[next_page]
        
        # 如果任一页没有表格，跳过
        if not current_page_tables or not next_page_tables:
            continue
        
        # 获取当前页的底部表格
        current_bottom_table = bottom_tables_by_page.get(current_page)
        if not current_bottom_table or current_bottom_table['id'] in processed_table_ids:
            continue
        
        # 获取下一页的顶部表格
        next_top_table = top_tables_by_page.get(next_page)
        if not next_top_table or next_top_table['id'] in processed_table_ids:
            continue
        
        # 检查页面方向是否相同
        if current_bottom_table['orientation'] != next_top_table['orientation']:
            print(f"\n跳过合并: 第{current_page}页({current_bottom_table['orientation']})与第{next_page}页({next_top_table['orientation']})方向不同")
            continue
        
        # 根据页面方向获取相应的全局最大y1和最小y0值
        orientation = current_bottom_table['orientation']
        if orientation == 'portrait':
            max_global_y1 = max_portrait_y1
            min_global_y0 = min_portrait_y0
        else:  # landscape
            max_global_y1 = max_landscape_y1
            min_global_y0 = min_landscape_y0
        
        # 检查当前页底部表格的y1是否接近全局最大值
        is_bottom_y1_max = (max_global_y1 - current_bottom_table['bbox'][3]) <= y1_tolerance
        
        # 检查下一页顶部表格的y0是否接近全局最小值
        is_top_y0_min = (next_top_table['bbox'][1] - min_global_y0) <= y0_tolerance
        
        # 检查列数是否匹配
        cols_match = current_bottom_table['max_cols'] == next_top_table['max_cols']
        
        # 检查x坐标是否大致相同（表示表格在水平方向上对齐）
        x_aligned = abs(current_bottom_table['bbox'][0] - next_top_table['bbox'][0]) < 10 and \
                    abs(current_bottom_table['bbox'][2] - next_top_table['bbox'][2]) < 10
        
        # 打印详细的判断信息
        print(f"\n检查合并: 第{current_page}页表格{current_bottom_table['table_index']}与第{next_page}页表格{next_top_table['table_index']}")
        print(f"  页面方向: {orientation}")
        print(f"  底部表格y1: {current_bottom_table['bbox'][3]}, 同方向全局最大y1: {max_global_y1}, 差值: {max_global_y1 - current_bottom_table['bbox'][3]}, 容差: {y1_tolerance}")
        print(f"  顶部表格y0: {next_top_table['bbox'][1]}, 同方向全局最小y0: {min_global_y0}, 差值: {next_top_table['bbox'][1] - min_global_y0}, 容差: {y0_tolerance}")
        print(f"  列数匹配: {cols_match} (底部表格: {current_bottom_table['max_cols']}, 顶部表格: {next_top_table['max_cols']})")
        print(f"  x坐标对齐: {x_aligned}")
        
        # 判断是否应该合并
        should_merge = cols_match and x_aligned and (is_bottom_y1_max or is_top_y0_min)
        
        if should_merge:
            print(f"  决定: 合并表格")
            
            # 创建合并表格
            merged_table = copy.deepcopy(current_bottom_table)
            merged_table['data'].extend(next_top_table['data'])
            
            # 更新bbox
            merged_table['bbox'] = (
                merged_table['bbox'][0],    # x0
                merged_table['bbox'][1],    # y0 (第一个表格的顶部y坐标)
                merged_table['bbox'][2],    # x1
                next_top_table['bbox'][3]   # y1 (第二个表格的底部y坐标)
            )
            
            # 标记为已处理
            processed_table_ids.add(current_bottom_table['id'])
            processed_table_ids.add(next_top_table['id'])
            
            # 记录合并的页码
            merged_table['is_merged'] = True
            merged_table['merged_pages'] = [current_page, next_page]
            
            # 添加合并后的表格到结果列表
            merged_tables.append(merged_table)
        else:
            print(f"  决定: 不合并表格")
            # 不满足合并条件，添加当前页底部表格
            if current_bottom_table['id'] not in processed_table_ids:
                merged_tables.append(current_bottom_table)
                processed_table_ids.add(current_bottom_table['id'])
    
    # 添加最后一页的底部表格（如果未处理）
    last_page = page_nums[-1]
    last_bottom_table = bottom_tables_by_page.get(last_page)
    if last_bottom_table and last_bottom_table['id'] not in processed_table_ids:
        merged_tables.append(last_bottom_table)
        processed_table_ids.add(last_bottom_table['id'])
    
    # 添加未处理的表格
    for table in all_tables:
        if table['id'] not in processed_table_ids:
            merged_tables.append(table)
            processed_table_ids.add(table['id'])
    
    print(f"\n合并后的表格数量: {len(merged_tables)}")
    return merged_tables


def is_word_in_bbox(word, bbox):
    """
    判断词元是否在指定的bbox内
    """
    x0, y0, x1, y1 = bbox
    word_x0, word_top = word['x0'], word['top']
    word_x1, word_bottom = word['x1'], word['bottom']
    
    # 检查词元是否在bbox内（完全包含）
    return (word_x0 >= x0 and word_x1 <= x1 and 
            word_top >= y0 and word_bottom <= y1)


def estimate_table_columns(table_words):
    """
    估计表格的实际列数，基于词元的水平分布
    """
    # 如果词元数量太少，无法准确估计
    if len(table_words) < 3:
        return 3  # 返回一个合理的默认值
    
    # 按照x坐标排序词元
    sorted_words = sorted(table_words, key=lambda w: w['x0'])
    
    # 计算相邻词元之间的x距离
    x_distances = []
    for i in range(1, len(sorted_words)):
        dist = sorted_words[i]['x0'] - sorted_words[i-1]['x1']
        if dist > 5:  # 忽略非常小的距离
            x_distances.append(dist)
    
    if not x_distances:
        return 3  # 默认值
    
    # 找出距离的中位数，作为列分隔的参考
    x_distances.sort()
    median_dist = x_distances[len(x_distances) // 2]
    
    # 计算可能的列数
    # 这里我们使用一个启发式方法：
    # 找出x坐标差异显著的词元数量，再加1（因为最后一列没有后续词元）
    significant_gaps = sum(1 for d in x_distances if d > median_dist * 0.8)
    estimated_cols = significant_gaps + 1
    
    # 确保列数在合理范围内
    return max(2, min(10, estimated_cols))  # 限制在2到10列之间


def is_empty_cell(cell):
    """
    检查单元格是否为空
    """
    return cell is None or (isinstance(cell, str) and cell.strip() == '')


def is_empty_column(table, col_idx):
    """
    检查列是否为空
    """
    for row in table:
        if col_idx < len(row) and not is_empty_cell(row[col_idx]):
            return False
    return True


def fix_centered_text_issues(table_data, estimated_cols):
    """
    修复居中文本导致的问题
    
    策略:
    1. 在单元格级别检测居中文本模式（空单元格-内容单元格-空单元格）
    2. 将居中内容移到左边的空单元格中
    3. 最后删除变成空列的列
    """
    if not table_data or len(table_data) == 0:
        return table_data
    
    # 获取当前表格的列数
    current_cols = max(len(row) for row in table_data)
    
    # 如果当前列数与估计列数相差不大，可能不需要处理
    if abs(current_cols - estimated_cols) <= 1:
        return table_data
    
    # 创建表格的副本进行处理
    processed_table = [row[:] for row in table_data]
    
    # 对每一行进行处理
    for row_idx, row in enumerate(processed_table):
        col_idx = 0
        while col_idx < len(row) - 2:  # 确保有足够的列来检查模式
            # 检查是否是居中文本模式：空单元格-内容单元格-空单元格
            if (is_empty_cell(row[col_idx]) and 
                not is_empty_cell(row[col_idx + 1]) and 
                col_idx + 2 < len(row) and is_empty_cell(row[col_idx + 2])):
                
                # 将居中内容移到左边的空单元格
                row[col_idx] = row[col_idx + 1]
                # 清空原居中位置
                row[col_idx + 1] = None
                # 继续检查下一个可能的模式
                col_idx += 3
            else:
                # 不是居中文本模式，继续检查下一列
                col_idx += 1
    
    # 找出现在变成空列的列
    empty_cols = []
    for col_idx in range(current_cols):
        if is_empty_column(processed_table, col_idx):
            empty_cols.append(col_idx)
    
    # 删除空列
    return remove_empty_columns(processed_table, empty_cols)


def remove_empty_columns(table_data, empty_cols):
    """
    从表格中删除指定的空列
    """
    if not empty_cols:
        return table_data
        
    processed_table = []
    for row in table_data:
        new_row = []
        for col_idx in range(len(row)):
            if col_idx not in empty_cols:
                new_row.append(row[col_idx])
        processed_table.append(new_row)
    
    return processed_table


def save_table_with_coordinates_in_filename(table_data, bbox, page_num, table_index, output_dir, is_merged=False, merged_pages=None):
    """
    保存表格数据，将坐标信息放在文件名中
    
    参数:
        table_data: 表格数据
        bbox: 表格边界框坐标
        page_num: 页码
        table_index: 表格在页面中的索引
        output_dir: 输出目录
        is_merged: 是否为合并表格
        merged_pages: 合并的页码列表
    """
    # 从bbox中提取坐标，保留整数部分
    x0, y0, x1, y1 = [int(coord) for coord in bbox]
    
    # 创建文件名，包含坐标信息
    if is_merged and merged_pages:
        # 对于合并表格，在文件名中包含所有合并的页码
        pages_str = "_".join(map(str, merged_pages))
        # 使用页码开头，merge结尾的命名方式
        csv_filename = f"page_{pages_str}_table_{table_index}_x0{x0}_y0{y0}_x1{x1}_y1{y1}_merge.csv"
    else:
        csv_filename = f"page_{page_num}_table_{table_index}_lattice_x0{x0}_y0{y0}_x1{x1}_y1{y1}.csv"
    
    csv_path = os.path.join(output_dir, csv_filename)
    
    # 保存CSV文件
    with open(csv_path, 'w', newline='', encoding='utf-8-sig') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerows(table_data)
    
    if is_merged:
        print(f"  - 已保存合并表格到 {csv_filename} (跨页: {merged_pages})")
    else:
        print(f"  - 已保存表格到 {csv_filename} (坐标包含在文件名中)")


if __name__ == '__main__':
    if len(sys.argv) < 4 or len(sys.argv) > 5:
        print("用法: python lattice_table.py <pdf_file_path> <map_file_path> <output_dir> [merge_tables=True]")
        sys.exit(1)
    
    pdf_path = sys.argv[1]
    map_path = sys.argv[2]
    output_dir = sys.argv[3]
    
    # 解析可选的merge_tables参数
    merge_tables = True  # 默认值
    if len(sys.argv) == 5:
        merge_tables_arg = sys.argv[4].lower()
        if merge_tables_arg in ('false', 'no', '0'):
            merge_tables = False
    
    extract_lattice_tables(pdf_path, map_path, output_dir, merge_tables) 