import json
import csv
import os
import sys
from collections import defaultdict

def extract_text_only_tables(map_path, output_dir):
    """
    提取地图文件中的text_only表格并保存为CSV
    text_only表格类型是基于文本对齐信息来确定表格结构
    """
    print(f"--- 开始从地图中提取text_only表格: {map_path} ---")
    
    try:
        with open(map_path, 'r', encoding='utf-8') as f:
            structure_map = json.load(f)
    except FileNotFoundError:
        print(f"错误: 找不到地图文件 {map_path}")
        sys.exit(1)
        
    if not os.path.exists(output_dir):
        print(f"输出目录 {output_dir} 不存在，正在创建...")
        os.makedirs(output_dir)

    extraction_count = 0
    
    for page_data in structure_map.get('pages', []):
        page_num = page_data['page_number']
        print(f"处理第 {page_num} 页...")
        
        # 收集所有页面元素
        all_page_elements = page_data.get('elements', [])
        text_elements = [el for el in all_page_elements if el['type'] == 'text_block']
        
        table_index_on_page = 0
        for element in all_page_elements:
            if element.get('type') == 'table' and element.get('parsing_strategy') == 'text_only':
                table_index_on_page += 1
                bbox = element['bbox']
                
                print(f"  - 找到text_only表格 {table_index_on_page}")
                
                # 1. 获取表格边界
                table_x0, table_y0, table_x1, table_y1 = bbox
                
                # 2. 获取表格几何形状信息
                geometries = element.get('geometries', [])
                virtual_lines = [g for g in geometries if g.get('geom_type') == 'virtual_line']
                
                # 3. 提取垂直分隔线作为列分隔符
                column_separators = []
                for line in virtual_lines:
                    if line['x0'] == line['x1']:  # 垂直线
                        column_separators.append(line['x0'])
                
                # 确保列分隔符按照从左到右排序
                column_separators.sort()
                
                # 4. 如果没有找到分隔符，则采用外部边界
                if not column_separators:
                    print(f"  - 警告: 表格中未找到垂直线，使用表格边界作为列分隔符")
                    column_separators = [table_x0, table_x1]
                else:
                    # 添加表格左右边界
                    if column_separators[0] > table_x0 + 5:  # 如果第一个分隔符距离左边界较远
                        column_separators.insert(0, table_x0)
                    if column_separators[-1] < table_x1 - 5:  # 如果最后一个分隔符距离右边界较远
                        column_separators.append(table_x1)
                
                print(f"  - 列分隔符位置: {column_separators}")
                
                # 5. 获取表格区域内的所有文本
                table_texts = []
                for text_el in text_elements:
                    text_bbox = text_el['bbox']
                    # 检查文本是否在表格区域内
                    if (text_bbox[0] >= table_x0 - 5 and 
                        text_bbox[2] <= table_x1 + 5 and 
                        text_bbox[1] >= table_y0 - 5 and 
                        text_bbox[3] <= table_y1 + 5):
                        
                        table_texts.append({
                            'text': text_el['text'],
                            'bbox': text_el['bbox'],
                            'top': text_el['bbox'][1],
                            'bottom': text_el['bbox'][3],
                            'x0': text_el['bbox'][0],
                            'x1': text_el['bbox'][2],
                            'words': text_el.get('words', [])
                        })
                
                if not table_texts:
                    print(f"警告: 表格 {table_index_on_page} 中未找到文本")
                    continue
                
                # 6. 根据垂直位置对文本分行
                table_texts.sort(key=lambda t: t['top'])
                text_rows = []
                current_row_texts = []
                current_top = table_texts[0]['top']
                
                for text in table_texts:
                    # 如果垂直位置差距大，认为是新的行
                    if text['top'] - current_top > 5:  # 5是行间距阈值
                        if current_row_texts:
                            current_row_texts.sort(key=lambda t: t['x0'])  # 按水平位置排序
                            text_rows.append(current_row_texts)
                            current_row_texts = []
                        current_top = text['top']
                    current_row_texts.append(text)
                
                # 添加最后一行
                if current_row_texts:
                    current_row_texts.sort(key=lambda t: t['x0'])
                    text_rows.append(current_row_texts)
                
                # 7. 根据列分隔符将每行文本分配到对应列
                processed_table = []
                for row in text_rows:
                    processed_row = [""] * (len(column_separators) - 1)
                    
                    for text_block in row:
                        # 处理文本块中的每个词元
                        for word in text_block.get('words', []):
                            word_x0 = word['x0']
                            word_x1 = word['x1']
                            word_center = (word_x0 + word_x1) / 2
                            
                            # 确定词元所在的列
                            col_idx = 0
                            for i in range(1, len(column_separators)):
                                if word_center < column_separators[i]:
                                    break
                                col_idx += 1
                            
                            # 确保列索引有效
                            if col_idx < len(processed_row):
                                if processed_row[col_idx]:
                                    processed_row[col_idx] += " " + word['text']
                                else:
                                    processed_row[col_idx] = word['text']
                    
                    processed_table.append(processed_row)
                
                # 8. 保存到CSV
                output_filename = f"page_{page_num}_table_{table_index_on_page}_text_only.csv"
                output_path = os.path.join(output_dir, output_filename)
                
                try:
                    with open(output_path, 'w', newline='', encoding='utf-8-sig') as csvfile:
                        writer = csv.writer(csvfile)
                        writer.writerows(processed_table)
                    extraction_count += 1
                    print(f"  - 已保存表格到 {output_filename}")
                except Exception as e:
                    print(f"保存CSV文件 {output_path} 时出错: {e}")

    print(f"--- 提取完成。共提取表格: {extraction_count} 个 ---")

if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("用法: python text_only.py <map_file_path> <output_dir>")
        sys.exit(1)
    
    map_path = sys.argv[1]
    output_dir = sys.argv[2]
    extract_text_only_tables(map_path, output_dir) 