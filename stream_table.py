import json
import csv
import os
import sys
from collections import defaultdict

def extract_stream_tables(map_path, output_dir):
    """
    提取地图文件中的stream表格并保存为CSV
    使用严格的三步法：1.确定表格形式 2.确定单元格坐标区域 3.严格放置词元
    对合并单元格使用最大重叠原则
    """
    print(f"--- Starting stream table extraction from map: {map_path} ---")
    
    try:
        with open(map_path, 'r', encoding='utf-8') as f:
            structure_map = json.load(f)
    except FileNotFoundError:
        print(f"Error: Map file not found at {map_path}")
        sys.exit(1)
        
    if not os.path.exists(output_dir):
        print(f"Output directory {output_dir} does not exist. Creating it.")
        os.makedirs(output_dir)

    extraction_count = 0
    
    # 处理地图中的每一页
    for page_data in structure_map.get('pages', []):
        page_num = page_data['page_number']
        print(f"Processing page {page_num}...")
        
        all_page_elements = page_data.get('elements', [])
        text_elements = [el for el in all_page_elements if el['type'] == 'text_block']
        
        table_index_on_page = 0
        for element in all_page_elements:
            if element.get('type') == 'table' and element.get('parsing_strategy') == 'stream':
                table_index_on_page += 1
                bbox = element['bbox']
                
                print(f"  - Found stream table {table_index_on_page} on page {page_num}")
                
                # 步骤1：确定表格形式 - 收集表格区域内的所有文本块
                table_x0, table_y0, table_x1, table_y1 = bbox
                table_texts = []
                
                for text_el in text_elements:
                    text_bbox = text_el['bbox']
                    # 检查文本是否在表格区域内
                    if (text_bbox[0] >= table_x0 - 5 and text_bbox[2] <= table_x1 + 5 and 
                        text_bbox[1] >= table_y0 - 5 and text_bbox[3] <= table_y1 + 5):
                        table_texts.append({
                            'text': text_el['text'],
                            'bbox': text_el['bbox'],
                            'top': text_el['bbox'][1],
                            'bottom': text_el['bbox'][3],
                            'x0': text_el['bbox'][0],
                            'x1': text_el['bbox'][2],
                            'words': text_el.get('words', []),
                            'word_count': len(text_el.get('words', []))
                        })
                
                if not table_texts:
                    print(f"Warning: No text found in table {table_index_on_page} on page {page_num}")
                    continue
                
                # 按垂直位置排序文本块，分行
                table_texts.sort(key=lambda t: t['top'])
                
                # 根据垂直位置对文本分行
                text_rows = []
                current_row_texts = []
                current_top = table_texts[0]['top']
                
                for text in table_texts:
                    if text['top'] - current_top > 2:  # 行间距阈值
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
                
                # 从文本块行中提取词元行
                word_rows = []
                for text_row in text_rows:
                    words_in_row = []
                    for text_block in text_row:
                        for word in text_block.get('words', []):
                            word_info = {
                                'text': word['text'],
                                'x0': word['x0'],
                                'x1': word['x1'],
                                'top': word['top'],
                                'bottom': word['bottom']
                            }
                            words_in_row.append(word_info)
                    
                    # 按x0排序当前行的词元
                    words_in_row.sort(key=lambda w: w['x0'])
                    word_rows.append(words_in_row)
                
                # 找出一行词元最多的行数量作为列数基准
                max_words_count = 0
                max_words_rows = []
                
                for words_in_row in word_rows:
                    words_count = len(words_in_row)
                    if words_count > max_words_count:
                        max_words_count = words_count
                        max_words_rows = [words_in_row]
                    elif words_count == max_words_count:
                        max_words_rows.append(words_in_row)
                
                if max_words_count == 0:
                    print(f"Warning: No valid rows detected in table {table_index_on_page}")
                    continue
                
                print(f"  - Detected maximum {max_words_count} columns in table")
                
                # 步骤2：确定单元格坐标区域 - 严格定义列边界
                # 初始化每列的边界值集合
                column_x0s = [[] for _ in range(max_words_count)]
                column_x1s = [[] for _ in range(max_words_count)]
                
                # 只从标准行（具有最大词元数的行）中收集列边界
                for row in max_words_rows:
                    for col_idx, word in enumerate(row):
                        if col_idx < max_words_count:
                            column_x0s[col_idx].append(word['x0'])
                            column_x1s[col_idx].append(word['x1'])
                
                # 计算每列的严格边界
                column_boundaries = []
                for i in range(max_words_count):
                    if column_x0s[i] and column_x1s[i]:
                        # 使用该列所有词元的最小x0和最大x1
                        x0 = min(column_x0s[i])
                        x1 = max(column_x1s[i])
                        column_boundaries.append((x0, x1))
                
                # 检查是否有列边界重叠或间隔过小
                for i in range(len(column_boundaries)-1):
                    if column_boundaries[i][1] >= column_boundaries[i+1][0]:
                        print(f"Warning: Column boundaries overlap at column {i+1}")
                
                # 步骤3：放置词元 - 区分标准单元格和合并单元格
                processed_table = []
                
                # 处理每一行词元
                for row_idx, words_in_row in enumerate(word_rows):
                    processed_row = [""] * len(column_boundaries)
                    
                    # 判断是否为标准行（词元数等于最大列数）
                    is_standard_row = len(words_in_row) == max_words_count
                    
                    for word in words_in_row:
                        word_x0 = word['x0']
                        word_x1 = word['x1']
                        
                        if is_standard_row:
                            # 标准单元格：严格检查词元是否落在列边界内
                            assigned = False
                            for col_idx, (col_x0, col_x1) in enumerate(column_boundaries):
                                if word_x0 >= col_x0 - 1 and word_x1 <= col_x1 + 1:  # 允许1像素误差
                                    if processed_row[col_idx]:
                                        processed_row[col_idx] += " " + word['text']
                                    else:
                                        processed_row[col_idx] = word['text']
                                    assigned = True
                                    break
                            
                            if not assigned:
                                print(f"    Warning: Unable to strictly assign word '{word['text']}' on standard row {row_idx+1}")
                        else:
                            # 合并单元格：使用最大重叠原则
                            max_overlap = 0
                            best_col_idx = -1
                            
                            for col_idx, (col_x0, col_x1) in enumerate(column_boundaries):
                                # 计算词元与列的重叠部分
                                overlap_start = max(word_x0, col_x0)
                                overlap_end = min(word_x1, col_x1)
                                overlap = max(0, overlap_end - overlap_start)
                                
                                # 如果重叠部分更大，更新最佳列
                                if overlap > max_overlap:
                                    max_overlap = overlap
                                    best_col_idx = col_idx
                            
                            # 将词元放入重叠最多的列
                            if best_col_idx >= 0:
                                if processed_row[best_col_idx]:
                                    processed_row[best_col_idx] += " " + word['text']
                                else:
                                    processed_row[best_col_idx] = word['text']
                            else:
                                # 如果没有任何重叠，记录错误
                                print(f"    Warning: Word '{word['text']}' has no overlap with any column on row {row_idx+1}")
                    
                    # 添加行到表格（包括空行）
                    processed_table.append(processed_row)
                
                # 保存表格到CSV
                output_filename = f"page_{page_num}_table_{table_index_on_page}_stream.csv"
                output_path = os.path.join(output_dir, output_filename)
                
                try:
                    with open(output_path, 'w', newline='', encoding='utf-8-sig') as csvfile:
                        writer = csv.writer(csvfile)
                        writer.writerows(processed_table)
                    extraction_count += 1
                    print(f"  - Saved table to {output_filename}")
                except Exception as e:
                    print(f"Error writing to CSV file {output_path}: {e}")

    print(f"--- Extraction complete. Total tables extracted: {extraction_count} ---")


if __name__ == '__main__':
    if len(sys.argv) != 3:
        print("Usage: python stream_table_extractor.py <path_to_map.json> <output_directory>")
        sys.exit(1)
    
    map_path_arg = sys.argv[1]
    output_dir_arg = sys.argv[2]
    
    extract_stream_tables(map_path_arg, output_dir_arg) 