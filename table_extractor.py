#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import sys
import argparse
import subprocess
import time
from pathlib import Path

def run_command(command, description):
    """
    运行命令并输出执行状态
    """
    print(f"\n=== 开始执行: {description} ===")
    print(f"命令: {' '.join(command)}")
    
    start_time = time.time()
    result = subprocess.run(command, capture_output=True, text=True)
    end_time = time.time()
    
    if result.returncode == 0:
        print(f"✅ {description}执行成功 (耗时: {end_time - start_time:.2f}秒)")
        print(result.stdout)
        return True
    else:
        print(f"❌ {description}执行失败 (耗时: {end_time - start_time:.2f}秒)")
        print(f"错误信息: {result.stderr}")
        return False

def ensure_directory_exists(directory):
    """
    确保目录存在，如果不存在则创建
    """
    if not os.path.exists(directory):
        os.makedirs(directory)
        print(f"创建目录: {directory}")
    return directory

def main():
    # 解析命令行参数
    parser = argparse.ArgumentParser(description="PDF表格提取调度程序")
    
    parser.add_argument("pdf_path", help="PDF文件路径")
    parser.add_argument("json_path", help="结构地图JSON文件路径")
    parser.add_argument("output_dir", help="输出目录")
    parser.add_argument("--no-lattice", action="store_true", help="不提取lattice表格")
    parser.add_argument("--no-stream", action="store_true", help="不提取stream表格")
    parser.add_argument("--no-text_only", action="store_true", help="不提取text_only表格")
    parser.add_argument("--no-merge-lattice", action="store_true", help="不合并lattice跨页表格")
    
    args = parser.parse_args()
    
    # 获取当前Python解释器的路径
    python_executable = sys.executable
    
    # 验证输入文件是否存在
    if not os.path.isfile(args.pdf_path):
        print(f"错误: PDF文件不存在: {args.pdf_path}")
        return 1
    
    if not os.path.isfile(args.json_path):
        print(f"错误: JSON文件不存在: {args.json_path}")
        return 1
    
    # 获取脚本所在目录
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # 创建输出目录
    base_output_dir = ensure_directory_exists(args.output_dir)
    
    # 获取PDF文件名（不含扩展名）
    pdf_filename = Path(args.pdf_path).stem
    
    # 创建各类型表格的输出目录
    lattice_output_dir = os.path.join(base_output_dir, f"{pdf_filename}_lattice")
    stream_output_dir = os.path.join(base_output_dir, f"{pdf_filename}_stream")
    text_only_output_dir = os.path.join(base_output_dir, f"{pdf_filename}_text_only")
    
    success_count = 0
    total_count = 0
    
    # 提取lattice表格
    if not args.no_lattice:
        total_count += 1
        ensure_directory_exists(lattice_output_dir)
        
        lattice_script = os.path.join(script_dir, "lattice_table.py")
        
        command = [
            python_executable,
            lattice_script,
            os.path.abspath(args.pdf_path),
            os.path.abspath(args.json_path),
            os.path.abspath(lattice_output_dir)
        ]
        
        # 添加合并参数
        if not args.no_merge_lattice:
            command.append("True")
        else:
            command.append("False")
        
        if run_command(command, "Lattice表格提取"):
            success_count += 1
    
    # 提取stream表格
    if not args.no_stream:
        total_count += 1
        ensure_directory_exists(stream_output_dir)
        
        stream_script = os.path.join(script_dir, "stream_table.py")
        
        command = [
            python_executable,
            stream_script,
            os.path.abspath(args.json_path),  # 只传递json路径
            os.path.abspath(stream_output_dir)
        ]
        
        if run_command(command, "Stream表格提取"):
            success_count += 1
    
    # 提取text_only表格
    if not args.no_text_only:
        total_count += 1
        ensure_directory_exists(text_only_output_dir)
        
        text_only_script = os.path.join(script_dir, "text_only.py")
        
        command = [
            python_executable,
            text_only_script,
            os.path.abspath(args.json_path),  # 只传递json路径
            os.path.abspath(text_only_output_dir)
        ]
        
        if run_command(command, "Text-only表格提取"):
            success_count += 1
    
    # 打印总结
    print("\n=== 执行完成 ===")
    print(f"总任务数: {total_count}")
    print(f"成功任务数: {success_count}")
    print(f"失败任务数: {total_count - success_count}")
    
    if total_count == 0:
        print("警告: 所有表格提取任务都被禁用，请检查参数设置")
    
    return 0 if success_count == total_count else 1

if __name__ == "__main__":
    sys.exit(main()) 