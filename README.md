# PDF表格提取系统

该项目是一个专门用于从PDF文件中提取表格的工具集，支持多种表格类型的识别和提取，包括带有明确边框的表格(lattice)、基于文本流的表格(stream)以及仅基于文本对齐的表格(text_only)。该系统还支持跨页表格的智能合并，能够处理复杂的金融报表和其他结构化文档。

## 主要特性

- **多种表格类型支持**：
  - **Lattice表格**：具有明确边框线的表格
  - **Stream表格**：基于文本流和空间关系的表格
  - **Text-only表格**：仅基于文本对齐信息的表格

- **智能表格处理**：
  - 自动检测和修复居中文本导致的额外列和行问题
  - 智能处理合并单元格
  - 基于几何和文本对齐的表格结构识别

- **跨页表格合并**：
  - 自动检测和合并跨页表格
  - 考虑页面方向（横向/纵向）确保正确合并
  - 基于表格位置和结构的智能匹配算法

- **统一调度接口**：
  - 通过单一命令行接口调用不同的表格提取方法
  - 灵活的参数配置，支持选择性提取特定类型的表格

## 系统架构

系统由以下主要组件组成：

1. **表格提取器**：
   - `lattice_table.py`: 提取具有明确边框的表格
   - `stream_table.py`: 提取基于文本流的表格
   - `text_only.py`: 提取基于文本对齐的表格

2. **调度程序**：
   - `table_extractor.py`: 统一调用接口，协调不同表格提取器的工作

3. **辅助工具**：
   - `build_structure_map.py`: 生成PDF文档的结构地图
   - `geometric_table_finder.py`: 基于几何特征查找表格
   - `text_alignment_table_finder.py`: 基于文本对齐查找表格

## 安装

1. 安装依赖：
   ```bash
   pip install -r requirements.txt
   ```

## 使用方法

### 1. 生成PDF结构地图

首先需要为PDF文件生成结构地图：

```bash
python pdf-table-extractor/build_structure_map.py <pdf_path> <output_json_path>
```

### 2. 提取表格

使用统一调度接口提取表格：

```bash
python pdf-table-extractor/table_extractor.py <pdf_path> <json_path> <output_dir> [options]
```

#### 可选参数：

- `--no-lattice`: 不提取lattice表格
- `--no-stream`: 不提取stream表格
- `--no-text_only`: 不提取text_only表格
- `--no-merge-lattice`: 不合并lattice跨页表格

### 3. 单独使用各提取器

也可以单独使用各个表格提取器：

#### Lattice表格提取：

```bash
python pdf-table-extractor/lattice_table.py <pdf_path> <json_path> <output_dir> [merge_tables]
```

#### Stream表格提取：

```bash
python pdf-table-extractor/stream_table.py <json_path> <output_dir>
```

#### Text-only表格提取：

```bash
python pdf-table-extractor/text_only.py <json_path> <output_dir>
```

## 输出格式

所有提取的表格将以CSV格式保存在指定的输出目录中。文件命名格式为：

- Lattice表格: `page_{页码}_table_{表格索引}_lattice.csv`
- Stream表格: `page_{页码}_table_{表格索引}_stream.csv`
- Text-only表格: `page_{页码}_table_{表格索引}_text_only.csv`

对于跨页合并的表格，命名格式为：
`merged_pages_{起始页}-{结束页}_table_{表格索引}_lattice.csv`

## 依赖项

- pandas==2.3.0
- pdfplumber==0.11.7
- pypdf==5.7.0
- tabulate==0.9.0

## 示例

```bash
# 生成结构地图
python pdf-table-extractor/build_structure_map.py PDF/600050.pdf json/600050.json

# 提取所有类型表格
python pdf-table-extractor/table_extractor.py PDF/600050.pdf json/600050.json output/

# 只提取lattice表格，不合并跨页表格
python pdf-table-extractor/table_extractor.py PDF/600050.pdf json/600050.json output/ --no-stream --no-text_only --no-merge-lattice
```

## 注意事项

- 对于复杂的表格结构，可能需要调整提取参数以获得最佳结果
- 跨页表格合并功能仅适用于lattice表格
- 表格提取质量受原始PDF文档质量影响

