#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
视频切片和上传工具
功能：将视频切片为TS和M3U8文件，并上传到宝塔服务器
作者：MiniMax Agent
版本：3.2.1 - 界面优化版（已修复编码和GUI问题）

主要改进：
• 修复了UnicodeDecodeError编码问题
• 修复了cache_status_label属性缺失问题
• 增强了错误处理和GUI安全性
• 替换FTP上传为七牛云存储上传
• 添加AccessKey、SecretKey、BucketName等配置参数
• 优化上传流程和错误处理
• 支持批量文件上传和进度显示
• 智能目录状态管理，避免不必要的目录切换
• 增强的绝对路径处理，确保FTP操作稳定性
• 优化的工作目录选择逻辑
• 保留所有v2.6.0的诊断功能
• 新增其他文件上传功能，支持任意文件批量上传
• 自动生成可访问的URL地址，支持CDN域名配置
• URL批量复制和保存功能，方便分享和管理
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import os
import sys
import subprocess
import threading
import time
import json
import re
from pathlib import Path
import ftplib

# 七牛云存储相关导入
try:
    from qiniu import Auth, put_file_v2, etag
    QINIU_AVAILABLE = True
except ImportError:
    QINIU_AVAILABLE = False
    print("警告：七牛云SDK未安装，使用pip install qiniu安装")
import urllib.request
import zipfile
import tempfile


class VideoSliceUploader:
    def __init__(self):
        self.root = tk.Tk()
        self.setup_window()
        self.setup_variables()
        self.setup_gui()
        self.check_ffmpeg()
        # 延迟初始化缓存状态检查，确保GUI完全初始化
        self.root.after(200, self.update_cache_status)
        self.root.after(300, self.initialization_complete)
        
    def setup_window(self):
        """设置主窗口"""
        self.root.title("视频切片和上传工具 - MiniMax Agent")
        self.root.geometry("1200x800")
        self.root.minsize(1000, 700)
        
        # 设置窗口图标和样式
        self.root.configure(bg='#f0f0f0')
        
    def setup_variables(self):
        """设置变量"""
        self.video_path = tk.StringVar()
        self.segment_duration = tk.StringVar(value="3")
        self.quality_crf = tk.StringVar(value="23")
        self.server_ip = tk.StringVar()
        self.server_port = tk.StringVar(value="21")
        self.username = tk.StringVar()
        self.password = tk.StringVar()
        self.upload_path = tk.StringVar()
        self.use_ssl = tk.BooleanVar(value=False)
        
        # 七牛云存储配置变量
        self.qiniu_access_key = tk.StringVar()
        self.qiniu_secret_key = tk.StringVar()
        self.qiniu_bucket_name = tk.StringVar()
        self.qiniu_domain = tk.StringVar()  # CDN域名
        self.use_qiniu = tk.BooleanVar(value=False)  # 是否使用七牛云存储
        
        # 其他文件上传相关变量
        self.other_files_path = tk.StringVar()
        self.selected_files = []  # 选中的文件列表
        self.uploaded_urls = []  # 上传后的URL列表
        
        # 缓存路径相关变量
        self.cache_path = tk.StringVar()
        self.set_default_cache_path()
        
        # 配置文件相关
        self.config_file = "server_config.json"
        self.config_vars = None
        
        self.ftp_connection = None
        self.is_processing = False
        self.has_cache_files = False  # 标记是否有缓存文件
        self.current_cache_dir = None  # 当前缓存目录
        
        # 按钮状态管理
        self.setup_button_styles()
        
    def setup_gui(self):
        """设置图形界面"""
        # 创建主框架
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # 配置网格权重
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        main_frame.rowconfigure(5, weight=1)  # 调整为日志区域（第5行）
        
        # 标题
        title_label = ttk.Label(main_frame, text="视频切片和上传工具", 
                               font=("Arial", 16, "bold"))
        title_label.grid(row=0, column=0, columnspan=3, pady=(0, 20))
        
        # 第一部分：视频文件选择
        self.setup_video_section(main_frame)
        
        # 第二部分：切片设置
        self.setup_slice_section(main_frame)
        
        # 第三部分：存储配置
        self.setup_server_section(main_frame)
        
        # 第四部分：核心操作区域（支持视频操作和其他文件上传切换）
        self.setup_core_operations_section(main_frame)
        
        # 第五部分：处理日志
        self.setup_log_section(main_frame)
        
        # 初始化按钮状态
        self.update_button_states()
        
    def setup_video_section(self, parent):
        """设置视频文件选择部分"""
        video_frame = ttk.LabelFrame(parent, text="1. 视频文件选择", padding="10")
        video_frame.grid(row=1, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(0, 10))
        video_frame.columnconfigure(1, weight=1)
        
        ttk.Label(video_frame, text="视频文件：").grid(row=0, column=0, sticky=tk.W, pady=(0, 5))
        ttk.Entry(video_frame, textvariable=self.video_path, width=60).grid(
            row=0, column=1, sticky=(tk.W, tk.E), padx=(10, 5), pady=(0, 5))
        ttk.Button(video_frame, text="浏览", command=self.select_video).grid(
            row=0, column=2, pady=(0, 5))
        
        # 视频信息显示
        self.video_info_label = ttk.Label(video_frame, text="未选择视频文件", 
                                         foreground="gray")
        self.video_info_label.grid(row=1, column=0, columnspan=3, sticky=tk.W, pady=(0, 5))
        
    def setup_slice_section(self, parent):
        """设置切片设置部分"""
        slice_frame = ttk.LabelFrame(parent, text="2. 切片设置", padding="10")
        slice_frame.grid(row=2, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(0, 10))
        
        # 切片时长
        ttk.Label(slice_frame, text="切片时长（秒）：").grid(row=0, column=0, sticky=tk.W)
        duration_frame = ttk.Frame(slice_frame)
        duration_frame.grid(row=0, column=1, sticky=tk.W, padx=(10, 0))
        
        self.duration_combo = ttk.Combobox(duration_frame, textvariable=self.segment_duration, 
                                          width=10, state="readonly")
        self.duration_combo['values'] = ("1", "2", "3", "5", "10", "15", "30", "60")
        self.duration_combo.grid(row=0, column=0)
        
        # 视频质量
        ttk.Label(slice_frame, text="视频质量（CRF值）：").grid(row=0, column=2, sticky=tk.W, padx=(20, 0))
        quality_frame = ttk.Frame(slice_frame)
        quality_frame.grid(row=0, column=3, sticky=tk.W, padx=(10, 0))
        
        self.quality_combo = ttk.Combobox(quality_frame, textvariable=self.quality_crf, 
                                         width=10, state="readonly")
        self.quality_combo['values'] = ("18", "20", "23", "25", "28", "30")
        self.quality_combo.grid(row=0, column=0)
        
        # 质量说明
        quality_note = ttk.Label(slice_frame, 
                                text="CRF值越小质量越高文件越大（18=高质量，30=低质量）", 
                                foreground="gray", font=("Arial", 8))
        quality_note.grid(row=1, column=0, columnspan=4, sticky=tk.W, pady=(5, 0))
        
    def setup_server_section(self, parent):
        """设置服务器配置部分"""
        server_frame = ttk.LabelFrame(parent, text="3. 存储配置", padding="10")
        server_frame.grid(row=3, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(0, 10))
        server_frame.columnconfigure(1, weight=1)
        
        # 存储类型选择
        storage_type_frame = ttk.Frame(server_frame)
        storage_type_frame.grid(row=0, column=0, columnspan=4, sticky=(tk.W, tk.E), pady=(0, 10))
        storage_type_frame.columnconfigure(1, weight=1)
        
        ttk.Label(storage_type_frame, text="存储类型：").grid(row=0, column=0, sticky=tk.W)
        ttk.Radiobutton(storage_type_frame, text="FTP服务器", 
                       variable=self.use_qiniu, value=False).grid(row=0, column=1, sticky=tk.W, padx=(10, 0))
        ttk.Radiobutton(storage_type_frame, text="七牛云存储", 
                       variable=self.use_qiniu, value=True).grid(row=0, column=2, sticky=tk.W, padx=(20, 0))
        
        # FTP配置区域（默认显示）
        self.ftp_frame = ttk.Frame(server_frame)
        self.ftp_frame.grid(row=1, column=0, columnspan=4, sticky=(tk.W, tk.E), pady=(0, 10))
        self.ftp_frame.columnconfigure(1, weight=1)
        
        # 服务器IP
        ttk.Label(self.ftp_frame, text="服务器IP/域名：").grid(row=0, column=0, sticky=tk.W)
        ttk.Entry(self.ftp_frame, textvariable=self.server_ip, width=30).grid(
            row=0, column=1, sticky=(tk.W, tk.E), padx=(10, 0))
        
        # 端口
        ttk.Label(self.ftp_frame, text="端口：").grid(row=0, column=2, sticky=tk.W, padx=(20, 0))
        ttk.Entry(self.ftp_frame, textvariable=self.server_port, width=10).grid(
            row=0, column=3, sticky=(tk.W, tk.E), padx=(10, 0))
        
        # 用户名
        ttk.Label(self.ftp_frame, text="用户名：").grid(row=1, column=0, sticky=tk.W, pady=(10, 0))
        ttk.Entry(self.ftp_frame, textvariable=self.username, width=30).grid(
            row=1, column=1, sticky=(tk.W, tk.E), padx=(10, 0))
        
        # 密码
        ttk.Label(self.ftp_frame, text="密码：").grid(row=1, column=2, sticky=tk.W, padx=(20, 0))
        ttk.Entry(self.ftp_frame, textvariable=self.password, width=10, show="*").grid(
            row=1, column=3, sticky=(tk.W, tk.E), padx=(10, 0))
        
        # 上传路径
        ttk.Label(self.ftp_frame, text="上传目录：").grid(row=2, column=0, sticky=tk.W, pady=(10, 0))
        ttk.Entry(self.ftp_frame, textvariable=self.upload_path, width=60).grid(
            row=2, column=1, columnspan=3, sticky=(tk.W, tk.E), padx=(10, 0))
        
        # SSL选项
        self.ssl_check = ttk.Checkbutton(self.ftp_frame, text="使用SSL/FTPS", 
                                        variable=self.use_ssl)
        self.ssl_check.grid(row=3, column=0, columnspan=2, sticky=tk.W, pady=(10, 0))
        
        # 路径示例
        path_example = ttk.Label(self.ftp_frame, 
                                text="例如：/www/wwwroot/yourdomain.com/videos", 
                                foreground="gray", font=("Arial", 8))
        path_example.grid(row=3, column=2, columnspan=2, sticky=tk.W, padx=(20, 0), pady=(10, 0))
        
        # 七牛云配置区域（默认隐藏）
        self.qiniu_frame = ttk.Frame(server_frame)
        self.qiniu_frame.grid(row=1, column=0, columnspan=4, sticky=(tk.W, tk.E), pady=(0, 10))
        self.qiniu_frame.columnconfigure(1, weight=1)
        
        # Access Key
        ttk.Label(self.qiniu_frame, text="Access Key：").grid(row=0, column=0, sticky=tk.W)
        ttk.Entry(self.qiniu_frame, textvariable=self.qiniu_access_key, width=60).grid(
            row=0, column=1, columnspan=3, sticky=(tk.W, tk.E), padx=(10, 0))
        
        # Secret Key
        ttk.Label(self.qiniu_frame, text="Secret Key：").grid(row=1, column=0, sticky=tk.W, pady=(10, 0))
        ttk.Entry(self.qiniu_frame, textvariable=self.qiniu_secret_key, width=60, show="*").grid(
            row=1, column=1, columnspan=3, sticky=(tk.W, tk.E), padx=(10, 0))
        
        # Bucket Name
        ttk.Label(self.qiniu_frame, text="存储桶名称：").grid(row=2, column=0, sticky=tk.W, pady=(10, 0))
        ttk.Entry(self.qiniu_frame, textvariable=self.qiniu_bucket_name, width=30).grid(
            row=2, column=1, sticky=(tk.W, tk.E), padx=(10, 0))
        
        # CDN域名（可选）
        ttk.Label(self.qiniu_frame, text="CDN域名（可选）：").grid(row=3, column=0, sticky=tk.W, pady=(10, 0))
        ttk.Entry(self.qiniu_frame, textvariable=self.qiniu_domain, width=30).grid(
            row=3, column=1, sticky=(tk.W, tk.E), padx=(10, 0))
        
        # 绑定存储类型切换事件
        self.use_qiniu.trace("w", self.on_storage_type_change)
        
        # 初始状态设置
        self.on_storage_type_change()
        
    def on_storage_type_change(self, *args):
        """处理存储类型切换事件"""
        if self.use_qiniu.get():
            # 显示七牛云配置，隐藏FTP配置
            self.qiniu_frame.grid()
            self.ftp_frame.grid_remove()
        else:
            # 显示FTP配置，隐藏七牛云配置
            self.ftp_frame.grid()
            self.qiniu_frame.grid_remove()
        
    def setup_core_operations_section(self, parent):
        """设置核心操作区域 - 支持视频操作和其他文件上传切换"""
        
        # 核心操作区域
        core_frame = ttk.LabelFrame(parent, text="4. 核心操作区域", padding="10")
        core_frame.grid(row=4, column=0, columnspan=3, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 10))
        core_frame.columnconfigure(0, weight=1)
        core_frame.rowconfigure(0, weight=1)
        
        # 创建标签页
        self.operation_notebook = ttk.Notebook(core_frame)
        self.operation_notebook.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 5))
        
        # 第一页：视频核心操作
        self.setup_video_operations_tab()
        
        # 第二页：其他文件上传
        self.setup_other_files_upload_tab()
        
        # 状态显示
        self.status_label = ttk.Label(core_frame, text="就绪", 
                                     foreground="green", font=("Arial", 10, "bold"))
        self.status_label.grid(row=1, column=0, sticky=tk.W, pady=(5, 0))
        
        # 缓存状态显示（新增）
        self.cache_status_label = ttk.Label(core_frame, text="缓存状态检查中...", 
                                           foreground="gray", font=("Arial", 9))
        self.cache_status_label.grid(row=2, column=0, sticky=tk.W, pady=(2, 0))
        
        # 配置网格权重
        parent.rowconfigure(4, weight=1)
        
    def setup_video_operations_tab(self):
        """设置视频核心操作标签页"""
        video_tab = ttk.Frame(self.operation_notebook)
        self.operation_notebook.add(video_tab, text="视频核心操作")
        
        # 主要操作按钮区域
        main_ops_frame = ttk.Frame(video_tab)
        main_ops_frame.pack(fill=tk.X, pady=(0, 15))
        
        # 测试连接按钮
        self.test_btn = ttk.Button(main_ops_frame, text="测试服务器连接", 
                                  command=self.test_connection, width=15)
        self.test_btn.pack(side=tk.LEFT, padx=(0, 10))
        
        # 开始处理按钮（主要操作，突出显示）
        self.start_btn = ttk.Button(main_ops_frame, text="开始切片和上传", 
                                   command=self.start_process, width=20)
        self.start_btn.pack(side=tk.LEFT, padx=(0, 20))
        
        # 停止按钮
        self.stop_btn = ttk.Button(main_ops_frame, text="停止任务", 
                                  command=self.stop_process, state="disabled", width=12)
        self.stop_btn.pack(side=tk.LEFT, padx=(0, 10))
        
        # 缓存操作按钮区域
        cache_ops_frame = ttk.Frame(video_tab)
        cache_ops_frame.pack(fill=tk.X)
        
        self.reupload_btn = ttk.Button(cache_ops_frame, text="从缓存重新上传", 
                                      command=self.reupload_from_cache, 
                                      state="disabled", width=15)
        self.reupload_btn.pack(side=tk.LEFT, padx=(0, 10))
        
        # 加载指定目录缓存按钮
        self.load_cache_btn = ttk.Button(cache_ops_frame, text="加载指定目录缓存", 
                                        command=self.load_specified_cache, width=18)
        self.load_cache_btn.pack(side=tk.LEFT, padx=(0, 10))
        
        # 配置管理按钮区域
        config_frame = ttk.Frame(cache_ops_frame)
        config_frame.pack(side=tk.LEFT, padx=(20, 0))
        
        # 配置相关按钮
        ttk.Button(config_frame, text="保存配置", command=self.save_config, width=10).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(config_frame, text="加载配置", command=self.load_config, width=10).pack(side=tk.LEFT)
        
    def setup_other_files_upload_tab(self):
        """设置其他文件上传标签页"""
        files_tab = ttk.Frame(self.operation_notebook)
        self.operation_notebook.add(files_tab, text="其他文件上传")
        
        # 文件夹选择区域
        folder_frame = ttk.Frame(files_tab)
        folder_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(folder_frame, text="选择文件夹：").pack(side=tk.LEFT)
        self.other_files_path = tk.StringVar()
        folder_entry = ttk.Entry(folder_frame, textvariable=self.other_files_path, width=50)
        folder_entry.pack(side=tk.LEFT, padx=(10, 5), fill=tk.X, expand=True)
        
        browse_btn = ttk.Button(folder_frame, text="浏览", command=self.select_other_files_folder)
        browse_btn.pack(side=tk.LEFT, padx=(0, 5))
        
        refresh_btn = ttk.Button(folder_frame, text="刷新列表", command=self.refresh_files_list)
        refresh_btn.pack(side=tk.LEFT)
        
        # 文件列表显示区域
        list_frame = ttk.LabelFrame(files_tab, text="文件列表", padding="5")
        list_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)
        
        # 文件列表
        self.files_listbox = tk.Listbox(list_frame, height=8)
        self.files_listbox.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # 滚动条
        files_scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.files_listbox.yview)
        files_scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        self.files_listbox.configure(yscrollcommand=files_scrollbar.set)
        
        # 文件操作按钮区域
        file_ops_frame = ttk.Frame(files_tab)
        file_ops_frame.pack(fill=tk.X, pady=(0, 10))
        
        # 上传相关按钮
        self.upload_other_files_btn = ttk.Button(file_ops_frame, text="开始上传", 
                                                command=self.upload_other_files, width=15)
        self.upload_other_files_btn.pack(side=tk.LEFT, padx=(0, 10))
        
        self.stop_upload_btn = ttk.Button(file_ops_frame, text="停止上传", 
                                         command=self.stop_upload_process, state="disabled", width=12)
        self.stop_upload_btn.pack(side=tk.LEFT, padx=(0, 10))
        
        # URL管理按钮
        self.view_urls_btn = ttk.Button(file_ops_frame, text="查看上传链接", 
                                       command=self.view_uploaded_urls, state="disabled", width=15)
        self.view_urls_btn.pack(side=tk.LEFT, padx=(0, 10))
        
        # 清除文件列表
        clear_btn = ttk.Button(file_ops_frame, text="清除列表", 
                              command=self.clear_files_list, width=10)
        clear_btn.pack(side=tk.LEFT, padx=(0, 10))
        
        # 文件计数和状态显示
        self.files_count_label = ttk.Label(file_ops_frame, text="已选择 0 个文件", foreground="gray")
        self.files_count_label.pack(side=tk.RIGHT)
        
        # 文件信息显示
        self.files_info_label = ttk.Label(files_tab, text="请选择要上传的文件夹", 
                                         foreground="gray", font=("Arial", 9))
        self.files_info_label.pack(anchor=tk.W, pady=(5, 0))
        
        # 初始化文件列表
        self.selected_files = []
        self.uploaded_urls = []
        
    def setup_log_section(self, parent):
        """设置日志显示部分"""
        log_frame = ttk.LabelFrame(parent, text="5. 处理日志", padding="10")
        log_frame.grid(row=5, column=0, columnspan=3, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 10))
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        
        self.log_text = scrolledtext.ScrolledText(log_frame, height=15, width=80)
        self.log_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # 进度条
        self.progress = ttk.Progressbar(log_frame, mode='indeterminate')
        self.progress.grid(row=1, column=0, sticky=(tk.W, tk.E), pady=(10, 0))
        
    def select_video(self):
        """选择视频文件"""
        filetypes = [
            ("视频文件", "*.mp4 *.avi *.mov *.mkv *.flv *.wmv *.m4v"),
            ("MP4文件", "*.mp4"),
            ("所有文件", "*.*")
        ]
        
        filename = filedialog.askopenfilename(
            title="选择视频文件",
            filetypes=filetypes
        )
        
        if filename:
            self.video_path.set(filename)
            self.update_video_info()
            
    def update_video_info(self):
        """更新视频信息显示"""
        video_file = self.video_path.get()
        if video_file and os.path.exists(video_file):
            try:
                # 获取文件大小
                file_size = os.path.getsize(video_file)
                size_mb = file_size / (1024 * 1024)
                
                # 获取视频信息
                duration = self.get_video_duration(video_file)
                
                info_text = f"文件: {os.path.basename(video_file)} | 大小: {size_mb:.2f} MB"
                if duration:
                    info_text += f" | 时长: {duration}"
                    
                self.video_info_label.config(text=info_text, foreground="blue")
                
            except Exception as e:
                self.video_info_label.config(text=f"获取视频信息失败: {str(e)}", 
                                           foreground="red")
        else:
            self.video_info_label.config(text="未选择视频文件", foreground="gray")
            
    def get_video_duration(self, video_path):
        """获取视频时长"""
        try:
            cmd = [
                self.ffmpeg_path, "-i", video_path, "-f", "null", "-"
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            # 查找时长信息
            output = result.stderr
            duration_match = re.search(r'Duration: (\d+):(\d+):(\d+\.\d+)', output)
            if duration_match:
                hours, minutes, seconds = duration_match.groups()
                total_seconds = int(hours) * 3600 + int(minutes) * 60 + float(seconds)
                mins, secs = divmod(total_seconds, 60)
                return f"{int(mins)}:{int(secs):02d}"
            return None
        except:
            return None
            
    def setup_button_styles(self):
        """设置按钮样式"""
        # 创建高亮样式
        style = ttk.Style()
        style.configure("Accent.TButton", 
                       foreground="white", 
                       background="#0078d4", 
                       padding=(20, 10))
        style.map("Accent.TButton",
                 background=[("active", "#106ebe"),
                           ("pressed", "#005a9e")])
        
    def update_button_states(self):
        """更新按钮状态"""
        if self.is_processing:
            # 处理中状态
            self.start_btn.config(state="disabled", text="正在处理...")
            self.reupload_btn.config(state="disabled")
            self.load_cache_btn.config(state="disabled")
            self.test_btn.config(state="disabled")
            self.stop_btn.config(state="normal")
            self.status_label.config(text="处理中...", foreground="orange")
        else:
            # 就绪状态
            self.start_btn.config(state="normal", text="开始切片和上传")
            self.test_btn.config(state="normal")
            self.stop_btn.config(state="disabled")
            
            if self.has_cache_files:
                self.reupload_btn.config(state="normal")
                self.status_label.config(text="就绪 (有缓存文件)", foreground="green")
            else:
                self.reupload_btn.config(state="disabled")
                self.status_label.config(text="就绪", foreground="green")
            
            # 加载指定目录缓存按钮始终可用
            self.load_cache_btn.config(state="normal")
                
    def log_message(self, message, level="INFO"):
        """添加日志消息"""
        timestamp = time.strftime("%H:%M:%S")
        log_entry = f"[{timestamp}] [{level}] {message}\n"
        
        self.log_text.insert(tk.END, log_entry)
        
    def safe_log(self, message, level="INFO"):
        """安全的日志记录，在GUI初始化前不会出错"""
        try:
            if hasattr(self, 'log_text') and self.log_text:
                self.log_message(message, level)
            else:
                print(f"[{level}] {message}")  # 备用日志到控制台
        except:
            print(f"[{level}] {message}")  # 最后的备用方案
    
    def safe_config_label(self, label, **kwargs):
        """安全的标签配置，避免GUI未初始化时的错误"""
        try:
            if hasattr(self, label) and getattr(self, label) is not None:
                getattr(self, label).config(**kwargs)
            else:
                # 如果标签不存在，使用安全日志
                text = kwargs.get('text', '')
                if text:
                    self.safe_log(f"标签配置: {text}")
        except Exception as e:
            self.safe_log(f"标签配置失败: {str(e)}", "WARNING")
    
    def safe_button_config(self, button_name, **kwargs):
        """安全的按钮配置"""
        try:
            if hasattr(self, button_name) and getattr(self, button_name) is not None:
                getattr(self, button_name).config(**kwargs)
        except Exception as e:
            self.safe_log(f"按钮配置失败 {button_name}: {str(e)}", "WARNING")
            
    def initialization_complete(self):
        """初始化完成后的处理"""
        self.safe_log("初始化完成，开始使用工具...")
        self.safe_log("程序版本: v3.2.1 - 界面优化版")
        self.log_text.see(tk.END)
        self.root.update()
        
    def test_connection(self):
        """测试存储连接"""
        # 验证配置
        if self.use_qiniu.get():
            if not all([self.qiniu_access_key.get(), self.qiniu_secret_key.get(), 
                       self.qiniu_bucket_name.get()]):
                messagebox.showerror("错误", "请填写完整的七牛云配置信息")
                return
        else:
            if not all([self.server_ip.get(), self.username.get(), 
                       self.password.get(), self.upload_path.get()]):
                messagebox.showerror("错误", "请填写完整的FTP服务器配置信息")
                return
            
        storage_type = "七牛云存储" if self.use_qiniu.get() else "FTP服务器"
        self.log_message(f"开始测试{storage_type}连接...")
        
        def test_thread():
            try:
                if self.use_qiniu.get():
                    # 测试七牛云连接
                    q = self.connect_qiniu()
                    if q:
                        self.log_message("七牛云存储连接测试成功")
                        messagebox.showinfo("成功", "七牛云存储连接测试成功！")
                    else:
                        self.log_message("七牛云存储连接测试失败", "ERROR")
                        messagebox.showerror("错误", "七牛云存储连接测试失败")
                else:
                    # 测试FTP连接
                    ftp = self.connect_ftp()
                    if ftp:
                        self.log_message("FTP服务器连接测试成功")
                        messagebox.showinfo("成功", "FTP服务器连接测试成功！")
                        ftp.quit()
                    else:
                        self.log_message("FTP服务器连接测试失败", "ERROR")
                        messagebox.showerror("错误", "FTP服务器连接测试失败")
            except Exception as e:
                self.log_message(f"连接测试异常: {str(e)}", "ERROR")
                messagebox.showerror("错误", f"连接测试异常: {str(e)}")
                
        threading.Thread(target=test_thread, daemon=True).start()
        
    def connect_qiniu(self):
        """初始化七牛云存储连接"""
        try:
            if not QINIU_AVAILABLE:
                self.log_message("错误：七牛云SDK未安装，请运行：pip install qiniu", "ERROR")
                return None
            
            # 验证七牛云配置
            if not all([self.qiniu_access_key.get(), self.qiniu_secret_key.get(), 
                       self.qiniu_bucket_name.get()]):
                self.log_message("七牛云配置不完整，请检查AccessKey、SecretKey和BucketName", "ERROR")
                return None
            
            # 创建七牛云认证对象
            q = Auth(self.qiniu_access_key.get(), self.qiniu_secret_key.get())
            
            self.log_message("七牛云存储连接初始化成功")
            return q
            
        except Exception as e:
            self.log_message(f"七牛云连接失败: {str(e)}", "ERROR")
            return None

    def connect_ftp(self):
        """连接FTP服务器（保留以兼容现有代码）"""
        try:
            use_ssl = self.use_ssl.get()
            
            if use_ssl:
                ftp = ftplib.FTP_TLS()
            else:
                ftp = ftplib.FTP()
                
            # 设置连接超时时间为120秒
            ftp.connect(self.server_ip.get(), int(self.server_port.get()), timeout=120)
            # 设置文件传输超时时间为600秒（10分钟）
            ftp.timeout = 600
            ftp.login(self.username.get(), self.password.get())
            
            # 设置FTP被动模式，避免防火墙问题
            ftp.set_pasv(True)
            
            # 定期发送NOOP命令保持连接活跃
            def keep_alive():
                try:
                    ftp.voidcmd('NOOP')
                except:
                    pass
            
            # 设置定时器，每30秒发送一次保活命令
            import threading
            def ftp_keep_alive():
                while True:
                    time.sleep(30)
                    keep_alive()
            
            keep_alive_thread = threading.Thread(target=ftp_keep_alive, daemon=True)
            keep_alive_thread.start()
            
            if use_ssl:
                ftp.prot_p()
                
            # 切换到上传目录
            try:
                ftp.cwd(self.upload_path.get())
            except:
                # 尝试创建目录
                self.log_message("上传目录不存在，尝试创建...")
                self.create_remote_directory(ftp, self.upload_path.get())
                
            return ftp
            
        except Exception as e:
            self.log_message(f"FTP连接失败: {str(e)}", "ERROR")
            return None

    def connect_storage(self):
        """通用存储连接方法 - 支持FTP和七牛云"""
        if self.use_qiniu.get():
            return self.connect_qiniu()
        else:
            return self.connect_ftp()
            
    def create_remote_directory(self, ftp, remote_dir):
        """创建远程目录 - 最终修复版本"""
        try:
            # 标准化路径
            normalized_dir = remote_dir.strip('/')
            
            self.log_message(f"开始创建目录: {normalized_dir}")
            
            # 先回到根目录，确保从根开始创建
            try:
                ftp.cwd('/')
                self.log_message("已返回根目录")
            except:
                pass  # 如果已经在根目录，忽略错误
            
            # 逐级创建目录，确保使用正确的路径
            parts = normalized_dir.split('/')
            current_path = ''
            
            for i, part in enumerate(parts):
                if part:
                    if i == 0:
                        # 第一级目录
                        current_path = part
                    else:
                        # 子目录，需要相对于当前目录
                        current_path = part
                    
                    # 创建目录（使用绝对路径以确保正确性）
                    full_path = '/' + '/'.join(parts[:i+1])
                    
                    try:
                        # 尝试直接创建
                        ftp.mkd(full_path)
                        self.log_message(f"创建目录: {full_path}")
                    except ftplib.error_perm as e:
                        if '550' in str(e):
                            self.log_message(f"目录可能已存在: {full_path}", "WARNING")
                        else:
                            self.log_message(f"创建目录失败 {full_path}: {str(e)}", "WARNING")
                    
                    # 切换到该目录
                    try:
                        ftp.cwd(full_path)
                        self.log_message(f"成功进入目录: {full_path}")
                    except ftplib.error_perm as e:
                        self.log_message(f"无法进入目录 {full_path}: {str(e)}", "ERROR")
                        # 如果不能进入，尝试相对路径
                        try:
                            ftp.cwd(part)
                            self.log_message(f"使用相对路径进入目录: {part}")
                        except:
                            self.log_message(f"完全无法访问目录: {part}", "ERROR")
                            continue
            
            # 最终验证：确保在目标目录
            try:
                ftp.cwd('/' + normalized_dir)
                current_pwd = ftp.pwd()
                self.log_message(f"成功切换到目标目录: {current_pwd}")
                return True
            except ftplib.error_perm as e:
                self.log_message(f"最终验证失败: {str(e)}", "ERROR")
                return False
                
        except Exception as e:
            self.log_message(f"创建目录异常: {str(e)}", "ERROR")
            return False
            
    def start_process(self):
        """开始处理视频"""
        if self.is_processing:
            messagebox.showwarning("警告", "正在处理中，请等待完成")
            return
            
        if not self.video_path.get() or not os.path.exists(self.video_path.get()):
            messagebox.showerror("错误", "请选择有效的视频文件")
            return
            
        # 验证存储配置
        if self.use_qiniu.get():
            if not all([self.qiniu_access_key.get(), self.qiniu_secret_key.get(), 
                       self.qiniu_bucket_name.get()]):
                messagebox.showerror("错误", "请填写完整的七牛云配置信息")
                return
        else:
            if not all([self.server_ip.get(), self.username.get(), 
                       self.password.get(), self.upload_path.get()]):
                messagebox.showerror("错误", "请填写完整的FTP服务器配置信息")
                return
            
        self.is_processing = True
        self.update_button_states()
        self.progress.start()
        
        # 在新线程中处理
        threading.Thread(target=self.process_video, daemon=True).start()
        
    def stop_process(self):
        """停止处理"""
        self.is_processing = False
        self.log_message("用户停止处理")
        
    def process_video(self):
        """处理视频（切片和上传）"""
        try:
            video_file = self.video_path.get()
            segment_duration = self.segment_duration.get()
            quality_crf = self.quality_crf.get()
            
            self.log_message(f"开始处理视频: {os.path.basename(video_file)}")
            self.log_message(f"切片时长: {segment_duration}秒, 质量CRF: {quality_crf}")
            
            # 创建输出目录
            output_dir = self.create_output_directory(video_file)
            playlist_file = os.path.join(output_dir, "playlist.m3u8")
            
            # 执行ffmpeg命令
            if self.execute_ffmpeg(video_file, output_dir, segment_duration, quality_crf, playlist_file):
                self.log_message("视频切片完成")
                
                # 上传到服务器
                if self.upload_to_server(output_dir, playlist_file):
                    self.log_message("文件上传完成")
                    
                    # 删除本地文件
                    self.cleanup_local_files(output_dir)
                    self.log_message("本地文件清理完成")
                    
                    self.log_message("所有任务完成！", "SUCCESS")
                    
                else:
                    self.log_message("文件上传失败，但切片文件已保存到缓存", "WARNING")
                    # 设置缓存状态
                    self.update_cache_status()
                    # 启用重新上传按钮
                    if not self.is_processing:
                        self.reupload_btn.config(state="normal")
            else:
                self.log_message("视频切片失败", "ERROR")
                
        except Exception as e:
            self.log_message(f"处理异常: {str(e)}", "ERROR")
        finally:
            self.is_processing = False
            self.update_button_states()
            self.update_cache_status()
            self.progress.stop()
            
    def create_output_directory(self, video_file):
        """创建输出目录"""
        video_name = os.path.splitext(os.path.basename(video_file))[0]
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        output_dir = os.path.join(self.cache_path.get(), f"{video_name}_{timestamp}")
        
        os.makedirs(output_dir, exist_ok=True)
        self.log_message(f"创建输出目录: {output_dir}")
        
        # 保存当前缓存目录
        self.current_cache_dir = output_dir
        
        return output_dir
        
    def execute_ffmpeg(self, input_file, output_dir, segment_duration, quality_crf, playlist_file):
        """执行ffmpeg命令"""
        try:
            cmd = [
                self.ffmpeg_path,
                "-i", input_file,
                "-force_key_frames", f"expr:gte(t,n_forced*{segment_duration})",
                "-c:v", "libx264",
                "-preset", "fast",
                "-crf", quality_crf,
                "-c:a", "aac",
                "-b:a", "128k",
                "-hls_time", segment_duration,
                "-hls_list_size", "0",
                "-hls_segment_filename", os.path.join(output_dir, "segment_%03d.ts"),
                "-f", "hls",
                playlist_file
            ]
            
            self.log_message(f"执行命令: {' '.join(cmd)}")
            
            # 修复编码问题：使用utf-8编码处理subprocess输出
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8',
                errors='replace'  # 替换无法解码的字符
            )
            
            # 实时输出日志
            while True:
                output = process.stderr.readline()
                if output == '' and process.poll() is not None:
                    break
                if output:
                    try:
                        # 安全地处理输出，避免编码错误
                        clean_output = output.strip()
                        self.log_message(f"FFmpeg: {clean_output}")
                    except Exception as log_error:
                        self.log_message(f"FFmpeg输出处理异常: {str(log_error)}", "WARNING")
                    
            return_code = process.wait()
            
            if return_code == 0:
                self.log_message("FFmpeg执行成功")
                return True
            else:
                self.log_message(f"FFmpeg执行失败，返回码: {return_code}", "ERROR")
                return False
                
        except UnicodeDecodeError as e:
            self.log_message(f"FFmpeg输出编码错误: {str(e)}", "WARNING")
            # 尝试使用不同编码重新执行
            return self._execute_ffmpeg_with_fallback_encoding(input_file, output_dir, segment_duration, quality_crf, playlist_file)
        except Exception as e:
            self.log_message(f"FFmpeg执行异常: {str(e)}", "ERROR")
            return False
    
    def _execute_ffmpeg_with_fallback_encoding(self, input_file, output_dir, segment_duration, quality_crf, playlist_file):
        """使用备用编码执行FFmpeg（处理编码问题）"""
        try:
            cmd = [
                self.ffmpeg_path,
                "-i", input_file,
                "-force_key_frames", f"expr:gte(t,n_forced*{segment_duration})",
                "-c:v", "libx264",
                "-preset", "fast",
                "-crf", quality_crf,
                "-c:a", "aac",
                "-b:a", "128k",
                "-hls_time", segment_duration,
                "-hls_list_size", "0",
                "-hls_segment_filename", os.path.join(output_dir, "segment_%03d.ts"),
                "-f", "hls",
                playlist_file
            ]
            
            self.log_message("使用备用编码重新执行FFmpeg...")
            
            # 使用二进制模式处理，避免编码问题
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            # 读取输出并安全处理
            try:
                stderr_output = process.stderr.read()
                if stderr_output:
                    # 尝试不同的编码方式解码
                    for encoding in ['utf-8', 'gbk', 'latin1']:
                        try:
                            decoded_output = stderr_output.decode(encoding, errors='ignore')
                            if decoded_output.strip():
                                self.log_message(f"FFmpeg: {decoded_output.strip()}")
                            break
                        except:
                            continue
            except Exception as read_error:
                self.log_message(f"读取FFmpeg输出失败: {str(read_error)}", "WARNING")
            
            return_code = process.wait()
            
            if return_code == 0:
                self.log_message("FFmpeg执行成功（使用备用编码）")
                return True
            else:
                self.log_message(f"FFmpeg执行失败，返回码: {return_code}", "ERROR")
                return False
                
        except Exception as e:
            self.log_message(f"备用FFmpeg执行异常: {str(e)}", "ERROR")
            return False

    def _create_remote_directory(self, ftp, remote_dir):
        """创建远程目录结构"""
        try:
            # 分割路径
            path_parts = remote_dir.split('/')
            current_path = ''
            
            # 逐级创建目录
            for part in path_parts:
                if part:  # 跳过空字符串
                    current_path += '/' + part
                    try:
                        # 尝试切换到目录
                        ftp.cwd(current_path)
                    except:
                        # 目录不存在，创建它
                        try:
                            ftp.mkd(current_path)
                            self.log_message(f"创建目录: {current_path}")
                        except ftplib.error_perm:
                            # 目录可能已存在，忽略错误
                            pass
            
            # 确保切换到目标目录
            ftp.cwd(remote_dir)
            self.log_message(f"确保目录存在: {remote_dir}")
            
        except Exception as e:
            self.log_message(f"创建远程目录失败: {e}", "ERROR")
            raise

    def upload_to_server(self, output_dir, playlist_file):
        """上传文件到存储服务器（支持FTP和七牛云）"""
        try:
            if self.use_qiniu.get():
                return self.upload_to_qiniu(output_dir, playlist_file)
            else:
                return self.upload_to_ftp(output_dir, playlist_file)
                
        except Exception as e:
            self.log_message(f"上传失败: {str(e)}", "ERROR")
            return False

    def upload_to_qiniu(self, output_dir, playlist_file):
        """上传文件到七牛云存储"""
        try:
            self.log_message("开始连接七牛云存储...")
            
            if not QINIU_AVAILABLE:
                self.log_message("错误：七牛云SDK未安装，请运行：pip install qiniu", "ERROR")
                return False
            
            # 验证七牛云配置
            if not all([self.qiniu_access_key.get(), self.qiniu_secret_key.get(), 
                       self.qiniu_bucket_name.get()]):
                self.log_message("七牛云配置不完整，请检查AccessKey、SecretKey和BucketName", "ERROR")
                return False
            
            # 创建七牛云认证对象
            q = Auth(self.qiniu_access_key.get(), self.qiniu_secret_key.get())
            bucket_name = self.qiniu_bucket_name.get()
            
            # 获取视频名称作为存储路径前缀
            video_name = os.path.basename(output_dir)
            
            # 上传所有文件
            files_uploaded = 0
            total_files = len([f for f in os.listdir(output_dir) if f.endswith(('.ts', '.m3u8'))])
            
            self.log_message(f"准备上传 {total_files} 个文件到七牛云存储桶: {bucket_name}")
            
            for filename in os.listdir(output_dir):
                if filename.endswith(('.ts', '.m3u8')):
                    local_file = os.path.join(output_dir, filename)
                    
                    # 构建七牛云存储键名（使用视频名作为前缀）
                    key = f"{video_name}/{filename}"
                    
                    # 带重试的文件上传
                    upload_success = False
                    max_retries = 3
                    
                    for attempt in range(1, max_retries + 1):
                        try:
                            self.log_message(f"上传文件: {filename} (尝试 {attempt}/{max_retries})")
                            
                            # 获取文件大小用于进度显示
                            file_size = os.path.getsize(local_file)
                            self.log_message(f"文件大小: {file_size/1024/1024:.2f} MB")
                            
                            # 生成上传Token
                            token = q.upload_token(bucket_name, key, 3600)
                            
                            # 上传文件
                            start_time = time.time()
                            ret, info = put_file_v2(token, key, local_file)
                            
                            end_time = time.time()
                            upload_time = end_time - start_time
                            
                            if ret and ret['key'] == key:
                                # 上传成功
                                if file_size > 0:
                                    speed = file_size / upload_time / 1024 / 1024  # MB/s
                                    self.log_message(f"上传完成，耗时: {upload_time:.2f}秒，速度: {speed:.2f} MB/s")
                                else:
                                    self.log_message(f"上传完成，耗时: {upload_time:.2f}秒")
                                
                                self.log_message(f"✅ {filename} 上传成功")
                                files_uploaded += 1
                                upload_success = True
                                break
                            else:
                                # 上传失败
                                self.log_message(f"七牛云上传失败: {info}", "ERROR")
                                if attempt < max_retries:
                                    time.sleep(2)
                                
                        except Exception as upload_error:
                            self.log_message(f"七牛云上传异常 (尝试 {attempt}): {str(upload_error)}", "ERROR")
                            if attempt < max_retries:
                                time.sleep(2)
                    
                    if not upload_success:
                        self.log_message(f"文件 {filename} 上传失败，已跳过", "ERROR")
            
            # 返回上传结果
            if files_uploaded == total_files:
                self.log_message(f"所有 {files_uploaded} 个文件上传完成！")
                return True
            else:
                self.log_message(f"部分文件上传失败: {files_uploaded}/{total_files}", "WARNING")
                return files_uploaded > 0
                
        except Exception as e:
            self.log_message(f"七牛云上传失败: {str(e)}", "ERROR")
            return False

    def upload_to_ftp(self, output_dir, playlist_file):
        """上传文件到FTP服务器"""
        try:
            self.log_message("开始连接FTP服务器...")
            ftp = self.connect_ftp()
            
            if not ftp:
                return False
                
            # 获取视频名称作为远程文件夹名
            video_name = os.path.basename(output_dir)
            
            # 宝塔面板FTP路径优化：避免不必要的前缀
            upload_path = self.upload_path.get().strip('/')
            if upload_path in ['', '.', 'v']:
                # 空路径、当前目录或v目录，直接使用video_name
                remote_dir = video_name
            else:
                # 有明确的子目录路径
                remote_dir = upload_path + '/' + video_name
            
            self.log_message(f"创建远程目录: {remote_dir}")
            if not self.create_remote_directory(ftp, remote_dir):
                return False
            
            # 上传所有文件
            files_uploaded = 0
            total_files = len([f for f in os.listdir(output_dir) if f.endswith(('.ts', '.m3u8'))])
            
            for filename in os.listdir(output_dir):
                if filename.endswith(('.ts', '.m3u8')):
                    local_file = os.path.join(output_dir, filename)
                    
                    # 检查FTP当前目录，避免重复路径前缀
                    try:
                        current_ftp_dir = ftp.pwd()
                        # 如果当前目录已匹配目标目录，只使用文件名
                        if current_ftp_dir.rstrip('/') == remote_dir.rstrip('/'):
                            remote_file = filename  # 只用文件名
                        else:
                            remote_file = remote_dir + '/' + filename  # 使用完整路径
                    except:
                        # 如果无法获取当前目录，使用默认逻辑
                        remote_file = remote_dir + '/' + filename
                    
                    # 带重试的文件上传
                    upload_success = False
                    max_retries = 3
                    
                    for attempt in range(1, max_retries + 1):
                        try:
                            self.log_message(f"上传文件: {filename} (尝试 {attempt}/{max_retries})")
                            
                            # 获取文件大小用于进度显示
                            file_size = os.path.getsize(local_file)
                            self.log_message(f"文件大小: {file_size/1024/1024:.2f} MB")
                            
                            # 上传文件并显示进度
                            start_time = time.time()
                            with open(local_file, 'rb') as f:
                                ftp.storbinary(f'STOR {remote_file}', f, 8192)
                            
                            end_time = time.time()
                            upload_time = end_time - start_time
                            if file_size > 0:
                                speed = file_size / upload_time / 1024 / 1024  # MB/s
                                self.log_message(f"上传完成，耗时: {upload_time:.2f}秒，速度: {speed:.2f} MB/s")
                            else:
                                self.log_message(f"上传完成，耗时: {upload_time:.2f}秒")
                            
                            upload_success = True
                            break
                            
                        except Exception as upload_error:
                            error_msg = str(upload_error)
                            if "10060" in error_msg:
                                self.log_message(f"连接超时错误，{max_retries - attempt}次重试剩余...", "WARNING")
                                time.sleep(5)  # 等待5秒后重试
                            elif "553" in error_msg:
                                self.log_message(f"FTP 553错误: 文件路径或权限问题", "ERROR")
                                self.log_message(f"本地文件: {local_file}", "ERROR")
                                self.log_message(f"远程文件: {remote_file}", "ERROR")
                                
                                # v2.9.0增强553错误诊断和修复
                                try:
                                    # 检查当前FTP目录状态
                                    current_dir = ftp.pwd()
                                    self.log_message(f"当前FTP目录: {current_dir}", "DEBUG")
                                    
                                    # 检查目标目录是否可访问
                                    target_dir = remote_dir.rsplit('/', 1)[0] if '/' in remote_dir else ''
                                    if target_dir:
                                        try:
                                            ftp.cwd(target_dir)
                                            self.log_message(f"目标目录存在且可访问: {target_dir}", "DEBUG")
                                            ftp.cwd("/")  # 回到根目录
                                        except Exception as dir_check:
                                            self.log_message(f"目标目录访问失败: {dir_check}", "DEBUG")
                                except Exception as debug_error:
                                    self.log_message(f"553错误诊断失败: {debug_error}", "DEBUG")
                                
                                # v2.6.0改进：确保FTP连接状态正确的目录重建逻辑
                                if os.path.exists(local_file):
                                    self.log_message("本地文件存在，尝试重新创建远程目录...", "WARNING")
                                    try:
                                        # Step 1: 确保回到根目录并验证连接状态
                                        self.log_message("验证FTP连接状态...", "INFO")
                                        ftp.cwd("/")
                                        current_dir = ftp.pwd()
                                        self.log_message(f"当前FTP目录: {current_dir}", "INFO")
                                        
                                        # Step 2: 分步重建目录结构，确保每个步骤都成功
                                        dirs = remote_dir.strip("/").split("/")
                                        current_path = ""
                                        
                                        for dir_name in dirs:
                                            current_path += "/" + dir_name
                                            try:
                                                # 尝试切换到目录
                                                ftp.cwd(current_path)
                                                self.log_message(f"目录存在: {current_path}", "INFO")
                                            except:
                                                try:
                                                    # 目录不存在，创建它
                                                    ftp.mkd(current_path)
                                                    self.log_message(f"创建目录: {current_path}", "INFO")
                                                    ftp.cwd(current_path)
                                                    self.log_message(f"进入目录: {current_path}", "INFO")
                                                except Exception as mkdir_error:
                                                    self.log_message(f"创建目录失败 {current_path}: {mkdir_error}", "ERROR")
                                                    raise mkdir_error
                                        
                                        # Step 3: 验证最终目录状态
                                        final_dir = ftp.pwd()
                                        self.log_message(f"目录重建完成，当前目录: {final_dir}", "INFO")
                                        
                                        # Step 4: 确保在正确的工作目录
                                        work_dir = remote_dir.rsplit('/', 1)[0]
                                        if final_dir != work_dir:
                                            # 确保使用绝对路径
                                            if not work_dir.startswith('/'):
                                                work_dir = '/' + work_dir
                                            self.log_message(f"切换到工作目录: {work_dir}", "INFO")
                                            try:
                                                ftp.cwd(work_dir)
                                                final_dir = ftp.pwd()
                                            except Exception as cwd_error:
                                                self.log_message(f"工作目录切换失败: {cwd_error}", "WARNING")
                                                # 回到重建成功的目录
                                                ftp.cwd(final_dir)
                                        
                                        if final_dir == work_dir or work_dir in final_dir:
                                            self.log_message(f"✅ 目录状态已恢复: {final_dir}", "INFO")
                                        else:
                                            self.log_message(f"❌ 目录状态异常，期望: {work_dir}, 实际: {final_dir}", "ERROR")
                                            
                                    except Exception as dir_error:
                                        self.log_message(f"目录重建失败: {dir_error}", "ERROR")
                                        self.log_message(f"建议检查FTP权限和目录结构", "ERROR")
                                else:
                                    self.log_message("本地文件不存在，跳过重试", "ERROR")
                                
                                # 553错误不重试，直接跳过
                                break
                            else:
                                self.log_message(f"上传错误: {error_msg}", "ERROR")
                                break
                    
                    if upload_success:
                        files_uploaded += 1
                        self.log_message(f"已上传 {files_uploaded}/{total_files} 个文件")
                    else:
                        self.log_message(f"文件 {filename} 上传失败，已跳过", "ERROR")
                    
            ftp.quit()
            self.log_message(f"目录 {video_name} 上传完成")
            return True
            
        except Exception as e:
            self.log_message(f"目录上传失败: {str(e)}", "ERROR")
            return False

    def upload_directory_to_server(self, directory, playlist_file):
        """上传指定目录到服务器（支持FTP和七牛云）"""
        try:
            if self.use_qiniu.get():
                return self.upload_to_qiniu(directory, playlist_file)
            else:
                return self.upload_to_ftp(directory, playlist_file)
        except Exception as e:
            self.log_message(f"目录上传失败: {str(e)}", "ERROR")
            return False
            
    def cleanup_local_files(self, output_dir):
        """清理本地文件"""
        try:
            for filename in os.listdir(output_dir):
                file_path = os.path.join(output_dir, filename)
                if os.path.isfile(file_path):
                    os.remove(file_path)
                    
            os.rmdir(output_dir)
            self.log_message("本地文件清理完成")
            
        except Exception as e:
            self.log_message(f"本地文件清理失败: {str(e)}", "WARNING")
            
    def set_default_cache_path(self):
        """设置默认缓存路径（新增）"""
        try:
            # 尝试使用用户的缓存目录
            cache_dir = os.path.join(os.path.expanduser("~"), "AppData", "Local", "VideoSliceUploader", "Cache")
            if not os.path.exists(cache_dir):
                os.makedirs(cache_dir, exist_ok=True)
            self.cache_path.set(cache_dir)
        except:
            # 如果失败，使用程序运行目录
            cache_dir = os.path.join(os.getcwd(), "cache")
            if not os.path.exists(cache_dir):
                os.makedirs(cache_dir, exist_ok=True)
            self.cache_path.set(cache_dir)
            
    def select_cache_path(self):
        """选择缓存路径（新增）"""
        directory = filedialog.askdirectory(
            title="选择缓存目录",
            initialdir=self.cache_path.get()
        )
        
        if directory:
            self.cache_path.set(directory)
            self.update_cache_status()
            
    def open_cache_directory(self):
        """打开缓存目录（新增）"""
        cache_path = self.cache_path.get()
        if cache_path and os.path.exists(cache_path):
            os.startfile(cache_path)  # Windows系统
        else:
            messagebox.showwarning("警告", "缓存目录不存在")
            
    def clear_cache(self):
        """清空缓存（新增）"""
        cache_path = self.cache_path.get()
        if not os.path.exists(cache_path):
            messagebox.showinfo("信息", "缓存目录不存在，无需清空")
            return
            
        if messagebox.askyesno("确认", "确定要清空缓存目录吗？\n此操作不可恢复！"):
            try:
                import shutil
                # 删除缓存目录下的所有文件和文件夹
                for item in os.listdir(cache_path):
                    item_path = os.path.join(cache_path, item)
                    if os.path.isfile(item_path):
                        os.remove(item_path)
                    elif os.path.isdir(item_path):
                        shutil.rmtree(item_path)
                        
                self.has_cache_files = False
                self.current_cache_dir = None
                self.update_cache_status()
                self.reupload_btn.config(state="disabled")
                self.log_message("缓存目录已清空")
                messagebox.showinfo("成功", "缓存目录已清空")
                
            except Exception as e:
                self.log_message(f"清空缓存失败: {str(e)}", "ERROR")
                messagebox.showerror("错误", f"清空缓存失败: {str(e)}")
                
    def update_cache_status(self):
        """更新缓存状态（新增）- 增强错误处理"""
        try:
            # 检查cache_status_label是否存在（GUI初始化安全检查）
            if not hasattr(self, 'cache_status_label') or self.cache_status_label is None:
                # GUI还未完全初始化，使用安全的日志记录
                self.safe_log("缓存状态标签未初始化，跳过状态更新")
                return
            
            cache_path = self.cache_path.get()
            if not os.path.exists(cache_path):
                self.safe_config_label('cache_status_label', text="缓存目录不存在", foreground="red")
                self.has_cache_files = False
                return
                
            # 查找缓存文件
            cache_files = []
            try:
                for item in os.listdir(cache_path):
                    item_path = os.path.join(cache_path, item)
                    if os.path.isdir(item_path):
                        try:
                            # 检查是否包含TS和M3U8文件
                            ts_files = [f for f in os.listdir(item_path) if f.endswith('.ts')]
                            m3u8_files = [f for f in os.listdir(item_path) if f.endswith('.m3u8')]
                            if ts_files and m3u8_files:
                                cache_files.append({
                                    'dir': item,
                                    'ts_count': len(ts_files),
                                    'm3u8_count': len(m3u8_files)
                                })
                        except Exception as dir_error:
                            self.safe_log(f"读取缓存目录 {item} 失败: {str(dir_error)}", "WARNING")
                            continue
            except Exception as list_error:
                self.safe_log(f"扫描缓存目录失败: {str(list_error)}", "ERROR")
                self.safe_config_label('cache_status_label', text="缓存目录扫描失败", foreground="red")
                return
                    
            if cache_files:
                total_videos = len(cache_files)
                try:
                    total_files = sum(len(os.listdir(os.path.join(cache_path, f['dir']))) for f in cache_files)
                    self.safe_config_label('cache_status_label', 
                                         text=f"缓存文件: {total_videos}个视频, {total_files}个文件", 
                                         foreground="green")
                except Exception as count_error:
                    self.safe_log(f"计算缓存文件数量失败: {str(count_error)}", "WARNING")
                    self.safe_config_label('cache_status_label', 
                                         text=f"缓存文件: {total_videos}个视频", 
                                         foreground="green")
                self.has_cache_files = True
                
                # 启用重新上传按钮
                if not self.is_processing:
                    self.update_button_states()
            else:
                self.safe_config_label('cache_status_label', text="无缓存文件", foreground="gray")
                self.has_cache_files = False
                self.safe_button_config('reupload_btn', state="disabled")
                self.update_button_states()
                
        except Exception as e:
            # 最后的错误处理，确保不会崩溃
            self.safe_log(f"更新缓存状态异常: {str(e)}", "ERROR")
            self.safe_config_label('cache_status_label', text="缓存状态检查失败", foreground="red")
            
    def reupload_from_cache(self):
        """从缓存重新上传（新增）"""
        if self.is_processing:
            messagebox.showwarning("警告", "正在处理中，请等待完成")
            return
            
        if not self.has_cache_files:
            messagebox.showerror("错误", "没有找到缓存文件，无法重新上传")
            return
            
        if not all([self.server_ip.get(), self.username.get(), 
                   self.password.get(), self.upload_path.get()]):
            messagebox.showerror("错误", "请填写完整的服务器配置信息")
            return
            
        self.is_processing = True
        self.update_button_states()
        self.progress.start()
        
        # 在新线程中处理
        threading.Thread(target=self.process_reupload, daemon=True).start()
        
    def load_specified_cache(self):
        """加载指定目录缓存进行上传"""
        if self.is_processing:
            messagebox.showwarning("警告", "正在处理中，请等待完成")
            return
            
        if not all([self.server_ip.get(), self.username.get(), 
                   self.password.get(), self.upload_path.get()]):
            messagebox.showerror("错误", "请填写完整的服务器配置信息")
            return
        
        # 选择包含TS和M3U8文件的目录
        directory = filedialog.askdirectory(
            title="选择包含TS和M3U8文件的目录",
            initialdir="."
        )
        
        if not directory:
            return
        
        # 验证目录是否包含必要的文件
        if not self.validate_cache_directory(directory):
            messagebox.showerror("错误", "选择的目录不包含有效的TS和M3U8文件")
            return
        
        self.log_message(f"准备上传指定目录: {os.path.basename(directory)}")
        
        self.is_processing = True
        self.update_button_states()
        self.progress.start()
        
        # 在新线程中处理
        threading.Thread(target=self._upload_specified_directory, 
                        args=(directory,), daemon=True).start()
    
    def validate_cache_directory(self, directory):
        """验证目录是否包含有效的缓存文件"""
        if not os.path.isdir(directory):
            return False
        
        ts_files = [f for f in os.listdir(directory) if f.endswith('.ts')]
        m3u8_files = [f for f in os.listdir(directory) if f.endswith('.m3u8')]
        
        return len(ts_files) > 0 and len(m3u8_files) > 0
    
    def _upload_specified_directory(self, directory):
        """上传指定的目录"""
        try:
            playlist_file = os.path.join(directory, "playlist.m3u8")
            
            if self.upload_directory_to_server(directory, playlist_file):
                self.log_message(f"指定目录 {os.path.basename(directory)} 上传成功！", "SUCCESS")
            else:
                self.log_message(f"指定目录 {os.path.basename(directory)} 上传失败", "ERROR")
                
        except Exception as e:
            self.log_message(f"上传指定目录异常: {str(e)}", "ERROR")
        finally:
            self.is_processing = False
            self.update_button_states()
            self.progress.stop()

    def process_reupload(self):
        """处理重新上传（新增）"""
        try:
            cache_path = self.cache_path.get()
            
            # 查找所有有效的缓存目录
            cache_dirs = []
            for item in os.listdir(cache_path):
                item_path = os.path.join(cache_path, item)
                if os.path.isdir(item_path):
                    # 检查是否包含TS和M3U8文件
                    ts_files = [f for f in os.listdir(item_path) if f.endswith('.ts')]
                    m3u8_files = [f for f in os.listdir(item_path) if f.endswith('.m3u8')]
                    if ts_files and m3u8_files:
                        cache_dirs.append(item_path)
                        
            if not cache_dirs:
                self.log_message("没有找到有效的缓存文件", "ERROR")
                return
                
            self.log_message(f"找到 {len(cache_dirs)} 个缓存视频，准备重新上传...")
            
            # 逐个上传缓存目录
            for i, cache_dir in enumerate(cache_dirs):
                cache_dir_name = os.path.basename(cache_dir)
                self.log_message(f"开始上传缓存视频 {i+1}/{len(cache_dirs)}: {cache_dir_name}")
                
                # 查找playlist.m3u8文件
                playlist_file = os.path.join(cache_dir, "playlist.m3u8")
                if os.path.exists(playlist_file):
                    if self.upload_directory_to_server(cache_dir, playlist_file):
                        self.log_message(f"缓存视频 {cache_dir_name} 上传成功")
                    else:
                        self.log_message(f"缓存视频 {cache_dir_name} 上传失败", "ERROR")
                else:
                    self.log_message(f"缓存视频 {cache_dir_name} 缺少playlist.m3u8文件", "WARNING")
                    
            self.log_message("所有缓存文件重新上传完成！", "SUCCESS")
            
        except Exception as e:
            self.log_message(f"重新上传异常: {str(e)}", "ERROR")
        finally:
            self.is_processing = False
            self.update_button_states()
            self.progress.stop()

    def check_ffmpeg(self):
        """检查ffmpeg是否可用"""
        try:
            self.ffmpeg_path = self.find_ffmpeg()
            
            if not self.ffmpeg_path:
                self.safe_log("未找到FFmpeg，尝试自动下载...")
                self.download_ffmpeg()
                
            if self.ffmpeg_path:
                self.safe_log(f"FFmpeg可用: {self.ffmpeg_path}")
            else:
                self.safe_log("FFmpeg不可用，某些功能可能受限", "WARNING")
        except Exception as e:
            self.safe_log(f"FFmpeg检查失败: {e}", "ERROR")
            
    def find_ffmpeg(self):
        """查找ffmpeg可执行文件"""
        # 检查PATH中是否有ffmpeg
        for cmd in ["ffmpeg", "ffmpeg.exe"]:
            try:
                result = subprocess.run([cmd, "-version"], 
                                      capture_output=True, text=True, timeout=10)
                if result.returncode == 0:
                    return cmd
            except:
                continue
                
        # 检查常见安装路径
        common_paths = [
            "C:/Program Files/ffmpeg/bin/ffmpeg.exe",
            "C:/Program Files (x86)/ffmpeg/bin/ffmpeg.exe",
            "D:/ffmpeg/bin/ffmpeg.exe",
            os.path.join(os.gettempdir(), "ffmpeg/bin/ffmpeg.exe")
        ]
        
        for path in common_paths:
            if os.path.exists(path):
                return path
                
        return None
        
    def download_ffmpeg(self):
        """下载FFmpeg"""
        try:
            self.log_message("正在下载FFmpeg...")
            
            # FFmpeg下载地址（Windows版本）
            ffmpeg_url = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
            ffmpeg_zip = os.path.join(tempfile.gettempdir(), "ffmpeg.zip")
            ffmpeg_extract_dir = os.path.join(tempfile.gettempdir(), "ffmpeg_temp")
            
            # 下载文件
            urllib.request.urlretrieve(ffmpeg_url, ffmpeg_zip)
            self.log_message("FFmpeg下载完成")
            
            # 解压文件
            with zipfile.ZipFile(ffmpeg_zip, 'r') as zip_ref:
                zip_ref.extractall(ffmpeg_extract_dir)
                
            # 查找解压后的bin目录
            for root, dirs, files in os.walk(ffmpeg_extract_dir):
                if "ffmpeg.exe" in files:
                    self.ffmpeg_path = os.path.join(root, "ffmpeg.exe")
                    break
                    
            # 清理临时文件
            os.remove(ffmpeg_zip)
            import shutil
            shutil.rmtree(ffmpeg_extract_dir)
            
            self.log_message("FFmpeg安装完成")
            
        except Exception as e:
            self.log_message(f"FFmpeg下载失败: {str(e)}", "ERROR")
            self.ffmpeg_path = None

    def save_config(self):
        """保存存储配置到JSON文件"""
        try:
            # 验证必要字段
            if self.use_qiniu.get():
                # 七牛云配置验证
                if not all([self.qiniu_access_key.get().strip(), self.qiniu_secret_key.get().strip(), 
                           self.qiniu_bucket_name.get().strip()]):
                    messagebox.showerror("错误", "请先填写完整的七牛云配置信息")
                    return
            else:
                # FTP配置验证
                if not all([self.server_ip.get().strip(), self.username.get().strip(), 
                           self.password.get().strip(), self.upload_path.get().strip()]):
                    messagebox.showerror("错误", "请先填写完整的FTP服务器配置信息")
                    return
            
            # 准备配置数据
            config_data = {
                "storage_type": "qiniu" if self.use_qiniu.get() else "ftp",
                "segment_duration": self.segment_duration.get().strip(),
                "quality_crf": self.quality_crf.get().strip(),
                "cache_path": self.cache_path.get().strip(),
                "saved_time": time.strftime('%Y-%m-%d %H:%M:%S')
            }
            
            # 根据存储类型添加相应的配置
            if self.use_qiniu.get():
                # 七牛云配置
                config_data.update({
                    "qiniu_access_key": self.qiniu_access_key.get().strip(),
                    "qiniu_secret_key": self.qiniu_secret_key.get().strip(),
                    "qiniu_bucket_name": self.qiniu_bucket_name.get().strip(),
                    "qiniu_domain": self.qiniu_domain.get().strip()
                })
            else:
                # FTP配置
                config_data.update({
                    "server_ip": self.server_ip.get().strip(),
                    "server_port": self.server_port.get().strip(),
                    "username": self.username.get().strip(),
                    "password": self.password.get().strip(),  # 注意：实际使用时应考虑加密
                    "upload_path": self.upload_path.get().strip(),
                    "use_ssl": self.use_ssl.get()
                })
            
            # 保存到JSON文件
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, ensure_ascii=False, indent=2)
            
            self.log_message(f"配置已保存到: {self.config_file}")
            messagebox.showinfo("成功", f"配置已成功保存到\n{self.config_file}")
            
        except Exception as e:
            error_msg = f"保存配置失败: {str(e)}"
            self.log_message(error_msg, "ERROR")
            messagebox.showerror("错误", error_msg)
    
    def load_config(self):
        """从JSON文件加载存储配置"""
        try:
            if not os.path.exists(self.config_file):
                messagebox.showwarning("警告", f"配置文件不存在: {self.config_file}")
                return
            
            # 读取配置文件
            with open(self.config_file, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
            
            # 确定存储类型（向后兼容）
            storage_type = config_data.get("storage_type", "ftp")
            if storage_type == "qiniu":
                self.use_qiniu.set(True)
            else:
                self.use_qiniu.set(False)
            
            # 应用基本配置
            if "segment_duration" in config_data:
                self.segment_duration.set(config_data["segment_duration"])
            if "quality_crf" in config_data:
                self.quality_crf.set(config_data["quality_crf"])
            if "cache_path" in config_data:
                self.cache_path.set(config_data["cache_path"])
            
            # 应用FTP配置
            if not self.use_qiniu.get():
                if "server_ip" in config_data:
                    self.server_ip.set(config_data["server_ip"])
                if "server_port" in config_data:
                    self.server_port.set(config_data["server_port"])
                if "username" in config_data:
                    self.username.set(config_data["username"])
                if "password" in config_data:
                    self.password.set(config_data["password"])
                if "upload_path" in config_data:
                    self.upload_path.set(config_data["upload_path"])
                if "use_ssl" in config_data:
                    self.use_ssl.set(config_data["use_ssl"])
            
            # 应用七牛云配置
            if self.use_qiniu.get():
                if "qiniu_access_key" in config_data:
                    self.qiniu_access_key.set(config_data["qiniu_access_key"])
                if "qiniu_secret_key" in config_data:
                    self.qiniu_secret_key.set(config_data["qiniu_secret_key"])
                if "qiniu_bucket_name" in config_data:
                    self.qiniu_bucket_name.set(config_data["qiniu_bucket_name"])
                if "qiniu_domain" in config_data:
                    self.qiniu_domain.set(config_data["qiniu_domain"])
            
            # 显示配置信息
            saved_time = config_data.get("saved_time", "未知")
            storage_name = "七牛云存储" if self.use_qiniu.get() else "FTP服务器"
            
            if self.use_qiniu.get():
                message = f"""配置加载成功！

存储类型: {storage_name}
存储桶: {config_data.get('qiniu_bucket_name', '')}
AccessKey: {config_data.get('qiniu_access_key', '')[:10]}...
CDN域名: {config_data.get('qiniu_domain', '未设置')}
保存时间: {saved_time}"""
            else:
                message = f"""配置加载成功！

存储类型: {storage_name}
服务器: {config_data.get('server_ip', '')}
端口: {config_data.get('server_port', '')}
用户名: {config_data.get('username', '')}
上传路径: {config_data.get('upload_path', '')}
保存时间: {saved_time}"""
            
            self.log_message(f"配置已从 {self.config_file} 加载")
            messagebox.showinfo("成功", message)
            
        except FileNotFoundError:
            messagebox.showwarning("警告", f"配置文件不存在: {self.config_file}")
        except json.JSONDecodeError:
            error_msg = f"配置文件格式错误: {self.config_file}"
            self.log_message(error_msg, "ERROR")
            messagebox.showerror("错误", error_msg)
        except Exception as e:
            error_msg = f"加载配置失败: {str(e)}"
            self.log_message(error_msg, "ERROR")
            messagebox.showerror("错误", error_msg)

    def select_other_files_folder(self):
        """选择其他文件上传文件夹"""
        folder = filedialog.askdirectory(
            title="选择包含要上传文件的文件夹",
            initialdir="."
        )
        
        if folder:
            self.other_files_path.set(folder)
            self.load_files_from_folder(folder)
            
    def load_files_from_folder(self, folder_path):
        """从文件夹加载文件列表"""
        try:
            self.selected_files = []
            self.files_listbox.delete(0, tk.END)
            
            # 获取所有文件（排除文件夹）
            for item in os.listdir(folder_path):
                item_path = os.path.join(folder_path, item)
                if os.path.isfile(item_path):
                    # 获取文件信息
                    file_size = os.path.getsize(item_path)
                    size_mb = file_size / (1024 * 1024)
                    
                    self.selected_files.append({
                        'name': item,
                        'path': item_path,
                        'size': file_size,
                        'size_mb': size_mb
                    })
                    
                    # 添加到列表框
                    display_text = f"{item} ({size_mb:.2f} MB)"
                    self.files_listbox.insert(tk.END, display_text)
            
            # 更新文件计数和信息
            file_count = len(self.selected_files)
            total_size = sum(f['size_mb'] for f in self.selected_files)
            
            self.files_count_label.config(text=f"已选择 {file_count} 个文件")
            self.files_info_label.config(
                text=f"文件夹: {os.path.basename(folder_path)} | 总大小: {total_size:.2f} MB",
                foreground="blue"
            )
            
            if file_count > 0:
                self.log_message(f"从文件夹加载了 {file_count} 个文件，总大小 {total_size:.2f} MB")
            else:
                self.log_message("文件夹中没有找到文件", "WARNING")
                
        except Exception as e:
            self.log_message(f"加载文件夹失败: {str(e)}", "ERROR")
            messagebox.showerror("错误", f"加载文件夹失败: {str(e)}")
            
    def clear_files_list(self):
        """清除文件列表"""
        self.selected_files = []
        self.files_listbox.delete(0, tk.END)
        self.files_count_label.config(text="已选择 0 个文件")
        self.files_info_label.config(text="请选择要上传的文件夹", foreground="gray")
        self.other_files_path.set("")
        
    def upload_other_files(self):
        """上传其他文件到七牛云"""
        if not self.selected_files:
            messagebox.showwarning("警告", "请先选择要上传的文件")
            return
            
        # 检查存储类型
        if not self.use_qiniu.get():
            messagebox.showwarning("警告", "其他文件上传功能仅支持七牛云存储\n请选择'七牛云存储'模式后重试")
            # 自动切换到七牛云模式
            self.use_qiniu.set(True)
            self.on_storage_type_change()
            return
            
        # 验证七牛云配置
        if not all([self.qiniu_access_key.get(), self.qiniu_secret_key.get(), 
                   self.qiniu_bucket_name.get()]):
            messagebox.showerror("错误", "请先配置七牛云存储信息")
            return
            
        self.log_message(f"开始上传 {len(self.selected_files)} 个文件到七牛云...")
        
        # 在新线程中处理上传
        threading.Thread(target=self._upload_other_files_thread, daemon=True).start()
        
    def _upload_other_files_thread(self):
        """在其他线程中上传文件"""
        try:
            self.uploaded_urls = []
            
            # 验证七牛云配置
            if not QINIU_AVAILABLE:
                self.log_message("错误：七牛云SDK未安装，请运行：pip install qiniu", "ERROR")
                return
                
            q = Auth(self.qiniu_access_key.get(), self.qiniu_secret_key.get())
            bucket_name = self.qiniu_bucket_name.get()
            cdn_domain = self.qiniu_domain.get().strip()
            
            # 上传每个文件
            for i, file_info in enumerate(self.selected_files):
                try:
                    filename = file_info['name']
                    local_file = file_info['path']
                    file_size = file_info['size']
                    
                    self.log_message(f"上传文件 {i+1}/{len(self.selected_files)}: {filename}")
                    
                    # 构建七牛云存储键名
                    key = f"uploads/{filename}"
                    
                    # 生成上传Token
                    token = q.upload_token(bucket_name, key, 3600)
                    
                    # 上传文件
                    start_time = time.time()
                    ret, info = put_file_v2(token, key, local_file)
                    
                    end_time = time.time()
                    upload_time = end_time - start_time
                    
                    if ret and ret['key'] == key:
                        # 上传成功，生成URL
                        if cdn_domain:
                            # 使用CDN域名
                            if not cdn_domain.startswith('http'):
                                cdn_domain = 'https://' + cdn_domain
                            file_url = f"{cdn_domain}/{key}"
                        else:
                            # 使用默认域名
                            file_url = f"https://{bucket_name}.s3-cn-north-1.qiniucs.com/{key}"
                        
                        self.uploaded_urls.append({
                            'filename': filename,
                            'url': file_url,
                            'key': key
                        })
                        
                        self.log_message(f"✅ {filename} 上传成功")
                        self.log_message(f"文件URL: {file_url}")
                        
                    else:
                        self.log_message(f"❌ {filename} 上传失败", "ERROR")
                        
                except Exception as e:
                    self.log_message(f"上传 {filename} 失败: {str(e)}", "ERROR")
            
            # 上传完成后显示URL列表
            self._show_uploaded_urls()
            
        except Exception as e:
            self.log_message(f"上传过程异常: {str(e)}", "ERROR")
            
    def _show_uploaded_urls(self):
        """显示上传后的URL列表"""
        if not self.uploaded_urls:
            self.log_message("没有文件上传成功", "WARNING")
            return
            
        self.log_message(f"上传完成！成功上传 {len(self.uploaded_urls)} 个文件")
        
        # 创建URL显示窗口
        self._create_url_display_window()
        
    def _create_url_display_window(self):
        """创建URL显示窗口"""
        url_window = tk.Toplevel(self.root)
        url_window.title("上传完成 - 文件访问地址")
        url_window.geometry("800x600")
        url_window.configure(bg='#f0f0f0')
        
        # 主框架
        main_frame = ttk.Frame(url_window, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # 标题
        title_label = ttk.Label(main_frame, text="文件上传完成 - 可访问地址列表", 
                               font=("Arial", 14, "bold"))
        title_label.pack(pady=(0, 10))
        
        # 信息标签
        info_label = ttk.Label(main_frame, 
                              text=f"共成功上传 {len(self.uploaded_urls)} 个文件，点击URL可复制到剪贴板",
                              foreground="blue")
        info_label.pack(pady=(0, 10))
        
        # 创建Treeview显示URL列表
        columns = ('文件名', '文件URL')
        tree = ttk.Treeview(main_frame, columns=columns, show='headings', height=15)
        
        # 设置列标题和宽度
        tree.heading('文件名', text='文件名')
        tree.heading('文件URL', text='文件URL')
        tree.column('文件名', width=200)
        tree.column('文件URL', width=580)
        
        # 滚动条
        scrollbar = ttk.Scrollbar(main_frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        
        # 填充数据
        for url_info in self.uploaded_urls:
            tree.insert('', tk.END, values=(url_info['filename'], url_info['url']))
        
        # 绑定点击事件
        def on_tree_click(event):
            item = tree.selection()[0] if tree.selection() else None
            if item:
                url = tree.item(item, 'values')[1]
                # 复制到剪贴板
                self.root.clipboard_clear()
                self.root.clipboard_append(url)
                self.root.update()  # 确保剪贴板更新
                
                # 显示提示
                messagebox.showinfo("已复制", f"URL已复制到剪贴板:\n{url}")
        
        tree.bind('<Double-1>', on_tree_click)
        
        # 布局
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 按钮框架
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(pady=(10, 0))
        
        # 复制所有URL按钮
        def copy_all_urls():
            all_urls_text = "\n".join([f"{url_info['filename']}: {url_info['url']}" 
                                     for url_info in self.uploaded_urls])
            self.root.clipboard_clear()
            self.root.clipboard_append(all_urls_text)
            self.root.update()
            messagebox.showinfo("已复制", "所有URL已复制到剪贴板")
        
        ttk.Button(button_frame, text="复制所有URL", command=copy_all_urls).pack(side=tk.LEFT, padx=(0, 10))
        
        # 保存到文件按钮
        def save_urls_to_file():
            filename = filedialog.asksaveasfilename(
                title="保存URL列表",
                defaultextension=".txt",
                filetypes=[("文本文件", "*.txt"), ("所有文件", "*.*")]
            )
            if filename:
                try:
                    with open(filename, 'w', encoding='utf-8') as f:
                        f.write("文件上传完成 - 访问地址列表\n")
                        f.write("="*50 + "\n\n")
                        for url_info in self.uploaded_urls:
                            f.write(f"文件名: {url_info['filename']}\n")
                            f.write(f"访问地址: {url_info['url']}\n")
                            f.write("-"*30 + "\n")
                    messagebox.showinfo("保存成功", f"URL列表已保存到:\n{filename}")
                except Exception as e:
                    messagebox.showerror("保存失败", f"保存文件失败: {str(e)}")
        
        ttk.Button(button_frame, text="保存URL列表", command=save_urls_to_file).pack(side=tk.LEFT, padx=(0, 10))
        
        # 关闭按钮
        ttk.Button(button_frame, text="关闭", command=url_window.destroy).pack(side=tk.RIGHT)
        
        # 说明文本
        note_label = ttk.Label(main_frame, 
                              text="💡 提示：双击任意行可复制对应URL到剪贴板",
                              foreground="gray", font=("Arial", 9))
        note_label.pack(pady=(5, 0))

    def refresh_files_list(self):
        """刷新文件列表"""
        folder = self.other_files_path.get()
        self.selected_files = []
        
        if folder and os.path.isdir(folder):
            try:
                files = []
                for file in os.listdir(folder):
                    filepath = os.path.join(folder, file)
                    if os.path.isfile(filepath):
                        # 获取文件大小
                        file_size = os.path.getsize(filepath)
                        files.append((file, file_size, filepath))
                
                # 按文件名排序
                files.sort(key=lambda x: x[0])
                self.selected_files = files
                
                # 更新列表显示
                self.files_listbox.delete(0, tk.END)
                for file, size, _ in files:
                    size_mb = size / (1024 * 1024)
                    self.files_listbox.insert(tk.END, f"{file} ({size_mb:.2f} MB)")
                
                # 更新计数
                count = len(files)
                self.files_count_label.config(text=f"已选择 {count} 个文件", foreground="gray" if count == 0 else "blue")
                self.files_info_label.config(text=f"文件夹: {os.path.basename(folder) if folder else ''}")
                
                # 启用/禁用按钮
                self.upload_other_files_btn.config(state="normal" if count > 0 else "disabled")
                
            except Exception as e:
                self.log_message(f"读取文件夹失败: {str(e)}", "ERROR")
                self.files_info_label.config(text="读取文件夹失败", foreground="red")
        else:
            self.files_listbox.delete(0, tk.END)
            self.files_count_label.config(text="已选择 0 个文件", foreground="gray")
            self.files_info_label.config(text="请选择要上传的文件夹", foreground="gray")
            self.upload_other_files_btn.config(state="disabled")

    def stop_upload_process(self):
        """停止上传进程"""
        self.is_processing = False
        self.log_message("正在停止上传...")

    def view_uploaded_urls(self):
        """查看上传后的文件链接"""
        if not self.uploaded_urls:
            messagebox.showinfo("提示", "没有可显示的上传链接")
            return
        
        # 创建URL显示窗口
        url_window = tk.Toplevel(self.root)
        url_window.title("上传文件链接")
        url_window.geometry("800x600")
        url_window.configure(bg='#f0f0f0')
        
        # 主框架
        main_frame = ttk.Frame(url_window, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # 标题
        title_label = ttk.Label(main_frame, text=f"上传文件链接列表 ({len(self.uploaded_urls)} 个文件)", 
                               font=("Arial", 14, "bold"))
        title_label.pack(pady=(0, 10))
        
        # URL列表
        list_frame = ttk.Frame(main_frame)
        list_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        # 创建树形视图
        columns = ("文件名", "文件大小", "URL链接")
        tree = ttk.Treeview(list_frame, columns=columns, show="headings", height=15)
        
        # 设置列标题和宽度
        tree.heading("文件名", text="文件名")
        tree.heading("文件大小", text="文件大小")
        tree.heading("URL链接", text="URL链接")
        
        tree.column("文件名", width=200)
        tree.column("文件大小", width=100)
        tree.column("URL链接", width=400)
        
        # 添加数据
        for item in self.uploaded_urls:
            size_mb = item['size'] / (1024 * 1024)
            tree.insert("", tk.END, values=(item['filename'], f"{size_mb:.2f} MB", item['url']))
        
        # 滚动条
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        
        # 布局
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 按钮区域
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=(10, 0))
        
        # 复制单个URL的函数
        def copy_single_url():
            selection = tree.selection()
            if selection:
                item = tree.item(selection[0])
                url = item['values'][2]
                self.root.clipboard_clear()
                self.root.clipboard_append(url)
                self.root.update()
                messagebox.showinfo("复制成功", "URL已复制到剪贴板")
        
        # 复制所有URL的函数
        def copy_all_urls():
            all_urls = [item['url'] for item in self.uploaded_urls]
            urls_text = '\n'.join(all_urls)
            self.root.clipboard_clear()
            self.root.clipboard_append(urls_text)
            self.root.update()
            messagebox.showinfo("复制成功", "所有URL已复制到剪贴板")
        
        # 保存URL列表的函数
        def save_urls_to_file():
            file_path = filedialog.asksaveasfilename(
                title="保存URL列表",
                defaultextension=".txt",
                filetypes=[("文本文件", "*.txt"), ("CSV文件", "*.csv"), ("所有文件", "*.*")],
                initialname="uploaded_urls.txt"
            )
            
            if file_path:
                try:
                    with open(file_path, 'w', encoding='utf-8') as f:
                        f.write(f"上传文件URL列表 - {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                        f.write("=" * 50 + "\n\n")
                        for i, item in enumerate(self.uploaded_urls, 1):
                            size_mb = item['size'] / (1024 * 1024)
                            f.write(f"{i}. 文件名: {item['filename']}\n")
                            f.write(f"   文件大小: {size_mb:.2f} MB\n")
                            f.write(f"   URL: {item['url']}\n\n")
                    
                    messagebox.showinfo("保存成功", f"URL列表已保存到:\n{file_path}")
                except Exception as e:
                    messagebox.showerror("保存失败", f"保存文件时出错:\n{str(e)}")
        
        # 复制和保存按钮
        ttk.Button(button_frame, text="复制选中URL", command=copy_single_url).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(button_frame, text="复制所有URL", command=copy_all_urls).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(button_frame, text="保存到文件", command=save_urls_to_file).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(button_frame, text="关闭", command=url_window.destroy).pack(side=tk.RIGHT)

    def run(self):
        """运行程序"""
        self.root.mainloop()


if __name__ == "__main__":
    try:
        app = VideoSliceUploader()
        app.run()
    except Exception as e:
        print(f"启动失败: {e}")
        import traceback
        traceback.print_exc()
        input("按回车键退出...")