import sys
import os
import time
import shutil
import hashlib
import sqlite3
import json
from datetime import datetime
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QPushButton, QFileDialog, QLabel, 
    QVBoxLayout, QHBoxLayout, QWidget, QProgressBar, QTextEdit, 
    QRadioButton, QButtonGroup, QCheckBox, QGroupBox, QComboBox,
    QLineEdit, QMessageBox
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QPixmap, QImage
import cv2

class ImageProcessor(QThread):
    update_progress = pyqtSignal(int)
    update_log = pyqtSignal(str)
    processing_finished = pyqtSignal()
    
    def __init__(self, image_files, output_dir, rename_option, prefix_option, keep_original, db_path):
        super().__init__()
        self.image_files = image_files
        self.output_dir = output_dir
        self.rename_option = rename_option  # 0=不重命名, 1=时间戳, 2=哈希
        self.prefix_option = prefix_option  # 空=无前缀, O=原图, P=预览图, C=封面图
        self.keep_original = keep_original
        self.db_path = db_path
    
    def run(self):
        self.update_log.emit("开始处理图片...")
        
        # 连接数据库
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            self.update_log.emit("已连接数据库")
        except sqlite3.Error as e:
            self.update_log.emit(f"数据库连接失败: {e}")
            return
        
        # 不重命名模式下只需创建错误目录
        if self.rename_option == 0:
            error_dir = os.path.join(os.getcwd(), "error")
            if not os.path.exists(error_dir):
                os.makedirs(error_dir)
                self.update_log.emit(f"创建错误图片目录: {error_dir}")
        else:
            # 确保输出目录存在
            if self.keep_original:
                # 保留原图模式：创建输出目录用于保存处理后的图片
                if not os.path.exists(self.output_dir):
                    os.makedirs(self.output_dir)
                    self.update_log.emit(f"创建输出目录: {self.output_dir}")
                
                # 创建错误图片目录
                error_dir = os.path.join(self.output_dir, "error")
                if not os.path.exists(error_dir):
                    os.makedirs(error_dir)
                    self.update_log.emit(f"创建错误图片目录: {error_dir}")
            else:
                # 不保留原图模式：使用原图所在目录作为输出和错误目录
                if self.image_files:
                    first_img_dir = os.path.dirname(self.image_files[0])
                    error_dir = os.path.join(first_img_dir, "error")
                    if not os.path.exists(error_dir):
                        os.makedirs(error_dir)
                        self.update_log.emit(f"创建错误图片目录: {error_dir}")
                else:
                    error_dir = os.path.join(os.getcwd(), "error")
                    if not os.path.exists(error_dir):
                        os.makedirs(error_dir)
                        self.update_log.emit(f"创建错误图片目录: {error_dir}")
        
        total_files = len(self.image_files)
        
        for i, image_file in enumerate(self.image_files):
            # 更新进度
            progress = int((i / total_files) * 100)
            self.update_progress.emit(progress)
            
            # 获取原文件信息
            file_name = os.path.basename(image_file)
            file_ext = os.path.splitext(file_name)[1]
            
            try:
                # 如果是不重命名模式，只需记录到数据库而不处理图片
                if self.rename_option == 0:
                    self.update_log.emit(f"导入图片信息: {file_name}")
                    
                    # 将信息写入数据库
                    cursor.execute(
                        "INSERT INTO images (original_filename, file_name, file_path, upload_time) VALUES (?, ?, ?, ?)",
                        (file_name, file_name, image_file, datetime.now())
                    )
                    continue
                
                # 确定新文件名
                if self.rename_option == 1:  # 时间戳
                    # 时间戳模式不需要读取图片内容，直接生成时间戳
                    timestamp = int(time.time() * 1000)
                    # 检查是否同一秒有多张图片
                    count = 0
                    new_filename = f"{timestamp}{file_ext}"
                    output_dir = self.output_dir if self.keep_original else os.path.dirname(image_file)
                    while os.path.exists(os.path.join(output_dir, new_filename)):
                        count += 1
                        new_filename = f"{timestamp}_{count}{file_ext}"
                else:  # 哈希重命名
                    # 使用文件内容计算哈希，无论是否保留原图
                    self.update_log.emit(f"计算文件哈希: {file_name}")
                    try:
                        with open(image_file, 'rb') as f:
                            img_hash = hashlib.md5(f.read()).hexdigest()
                    except Exception as e:
                        error_msg = f"无法读取文件进行哈希计算: {str(e)}"
                        self.update_log.emit(f"错误: {error_msg}")
                        self.handle_error_image(image_file, error_dir, error_msg, cursor)
                        continue
                        
                    new_filename = f"{img_hash}{file_ext}"
                
                # 添加前缀
                if self.prefix_option:
                    new_filename = f"{self.prefix_option}{new_filename}"
                
                # 确定保存路径
                if self.keep_original:
                    # 如果保留原图，使用指定的输出目录保存处理后图片
                    output_path = os.path.join(self.output_dir, new_filename)
                    
                    # 复制文件到新位置，而不是加载和保存图片
                    try:
                        shutil.copy2(image_file, output_path)
                        self.update_log.emit(f"已保存处理后图片到: {output_path}，原图保持不变")
                    except Exception as e:
                        error_msg = f"复制文件失败: {str(e)}"
                        self.update_log.emit(f"错误: {error_msg}")
                        self.handle_error_image(image_file, error_dir, error_msg, cursor)
                        continue
                else:
                    # 如果不保留原图，直接重命名原图（不创建新文件）
                    output_path = os.path.join(os.path.dirname(image_file), new_filename)
                    
                    # 先删除目标路径如果已存在（可能发生在同一目录处理多张图片时）
                    if os.path.exists(output_path) and image_file != output_path:
                        os.remove(output_path)
                    
                    # 如果目标文件名与原文件名不同，则重命名文件
                    if os.path.basename(image_file) != new_filename:
                        try:
                            os.rename(image_file, output_path)
                            self.update_log.emit(f"已将原图重命名为: {new_filename}")
                        except Exception as e:
                            error_msg = f"重命名文件失败: {str(e)}"
                            self.update_log.emit(f"错误: {error_msg}")
                            self.handle_error_image(image_file, error_dir, error_msg, cursor)
                            continue
                    else:
                        self.update_log.emit(f"文件名未改变: {new_filename}")
                
                # 确保路径使用标准格式，避免路径分隔符问题
                normalized_path = os.path.normpath(output_path)
                
                # 将信息写入数据库
                cursor.execute(
                    "INSERT INTO images (original_filename, file_name, file_path, upload_time) VALUES (?, ?, ?, ?)",
                    (file_name, new_filename, normalized_path, datetime.now())
                )
            
            except Exception as e:
                error_msg = str(e)
                self.update_log.emit(f"处理 {file_name} 时出错: {error_msg}")
                self.handle_error_image(image_file, error_dir, error_msg, cursor)
        
        # 提交数据库更改
        conn.commit()
        conn.close()
        
        self.update_progress.emit(100)
        self.update_log.emit("所有图片处理完成")
        self.processing_finished.emit()
    
    def handle_error_image(self, image_file, error_dir, error_msg, cursor):
        """处理出错的图片，将其移动到error目录并记录到数据库"""
        try:
            # 获取文件名
            file_name = os.path.basename(image_file)
            
            # 创建错误图片的目标路径
            error_path = os.path.join(error_dir, file_name)
            
            # 如果error目录下已有同名文件，添加时间戳避免冲突
            if os.path.exists(error_path):
                name, ext = os.path.splitext(file_name)
                timestamp = int(time.time())
                error_path = os.path.join(error_dir, f"{name}_{timestamp}{ext}")
            
            # 复制出错图片到error目录
            shutil.copy2(image_file, error_path)
            self.update_log.emit(f"已将出错图片复制到: {error_path}")
            
            # 确保路径使用标准格式
            normalized_path = os.path.normpath(error_path)
            
            # 记录到数据库
            cursor.execute(
                "INSERT INTO images (original_filename, file_name, file_path, status, error_message, upload_time) VALUES (?, ?, ?, ?, ?, ?)",
                (file_name, file_name, normalized_path, "error", error_msg, datetime.now())
            )
            
        except Exception as e:
            self.update_log.emit(f"处理错误图片时出现问题: {str(e)}")

class ImageProcessorApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.image_files = []
        
        # 从配置文件中读取数据库路径
        self.config_path = 'config.json'
        self.db_path = 'images.db'  # 默认路径
        
        self.initUI()
        self.load_config()  # 载入配置
        self.check_database()  # 检查数据库
    
    def load_config(self):
        """从配置文件加载配置"""
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    
                # 检查数据库配置是否存在
                if 'database' in config and 'path' in config['database']:
                    self.db_path = config['database']['path']
                    self.log(f"已从配置文件加载数据库路径: {self.db_path}")
            else:
                self.log(f"配置文件 {self.config_path} 不存在，使用默认数据库路径")
        except Exception as e:
            self.log(f"加载配置失败: {e}，使用默认数据库路径")
    
    def check_database(self):
        """检查数据库是否存在，不存在则提示用户初始化"""
        if not os.path.exists(self.db_path):
            self.log("数据库文件不存在，请先运行初始化程序 (init_app.py)")
            QMessageBox.warning(
                self, 
                '数据库未初始化', 
                '数据库文件不存在，请先运行初始化程序 (init_app.py)',
                QMessageBox.Ok
            )
    
    def initUI(self):
        self.setWindowTitle('图片处理工具')
        self.setGeometry(100, 100, 800, 600)
        
        # 主布局
        main_layout = QVBoxLayout()
        
        # 图片选择区域
        select_layout = QHBoxLayout()
        self.select_btn = QPushButton('选择图片')
        self.select_btn.clicked.connect(self.select_images)
        self.file_label = QLabel('未选择文件')
        select_layout.addWidget(self.select_btn)
        select_layout.addWidget(self.file_label)
        main_layout.addLayout(select_layout)
        
        # 设置区域
        settings_layout = QHBoxLayout()
        
        # 重命名选项
        rename_group = QGroupBox("重命名选项")
        rename_layout = QVBoxLayout()
        
        self.rename_none = QRadioButton("不重命名")
        self.rename_timestamp = QRadioButton("时间戳重命名")
        self.rename_hash = QRadioButton("哈希重命名")
        
        self.rename_group = QButtonGroup()
        self.rename_group.addButton(self.rename_none, 0)
        self.rename_group.addButton(self.rename_timestamp, 1)
        self.rename_group.addButton(self.rename_hash, 2)
        
        # 连接重命名选项变化的信号
        self.rename_group.buttonClicked.connect(self.toggle_rename_options)
        
        # 修改默认选择为哈希重命名
        self.rename_hash.setChecked(True)
        
        rename_layout.addWidget(self.rename_none)
        rename_layout.addWidget(self.rename_timestamp)
        rename_layout.addWidget(self.rename_hash)
        
        rename_group.setLayout(rename_layout)
        settings_layout.addWidget(rename_group)
        
        # 前缀选项
        prefix_group = QGroupBox("添加前缀")
        prefix_layout = QVBoxLayout()
        
        self.prefix_combo = QComboBox()
        self.prefix_combo.addItem("无前缀", "")
        self.prefix_combo.addItem("原图 (O)", "O")
        self.prefix_combo.addItem("预览图 (P)", "P")
        self.prefix_combo.addItem("封面图 (C)", "C")
        
        # 设置默认选项为原图(O)
        self.prefix_combo.setCurrentIndex(1)
        
        prefix_layout.addWidget(self.prefix_combo)
        prefix_group.setLayout(prefix_layout)
        settings_layout.addWidget(prefix_group)
        
        # 其他选项
        other_group = QGroupBox("其他选项")
        other_layout = QVBoxLayout()
        
        self.keep_original = QCheckBox("保留原图（处理后图片保存到输出目录）")
        self.keep_original.setChecked(True)
        self.keep_original.stateChanged.connect(self.toggle_output_dir)
        
        other_layout.addWidget(self.keep_original)
        other_group.setLayout(other_layout)
        settings_layout.addWidget(other_group)
        
        main_layout.addLayout(settings_layout)
        
        # 输出目录选择
        self.output_layout = QHBoxLayout()
        self.output_btn = QPushButton('选择输出目录')
        self.output_btn.clicked.connect(self.select_output_dir)
        self.output_label = QLabel('未选择输出目录')
        self.output_layout.addWidget(self.output_btn)
        self.output_layout.addWidget(self.output_label)
        main_layout.addLayout(self.output_layout)
        
        # 处理按钮
        self.process_btn = QPushButton('开始处理')
        self.process_btn.clicked.connect(self.process_images)
        self.process_btn.setEnabled(False)
        main_layout.addWidget(self.process_btn)
        
        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        main_layout.addWidget(self.progress_bar)
        
        # 日志区域
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        main_layout.addWidget(self.log_text)
        
        # 设置主窗口部件
        central_widget = QWidget()
        central_widget.setLayout(main_layout)
        self.setCentralWidget(central_widget)
        
        # 初始输出目录设为当前目录
        self.output_dir = os.getcwd()
        self.output_label.setText(self.output_dir)
        
        self.log("应用已启动")
        
        # 初始化界面控件状态
        self.toggle_rename_options(self.rename_hash)
        
        # 确保选择输出目录按钮初始状态正确
        self.output_btn.setEnabled(self.keep_original.isChecked())
    
    def toggle_rename_options(self, button):
        """根据重命名选项切换其他设置的可用性"""
        # 获取当前选择的重命名选项ID
        rename_option = self.rename_group.id(button)
        
        # 如果选择了"不重命名"，禁用其他选项
        is_no_rename = rename_option == 0
        
        # 前缀选项
        self.prefix_combo.setEnabled(not is_no_rename)
        
        # 保留原图选项
        self.keep_original.setEnabled(not is_no_rename)
        
        # 输出目录选项
        self.output_btn.setEnabled(not is_no_rename and self.keep_original.isChecked())
        
        # 更新提示信息
        if is_no_rename:
            self.output_label.setText("不重命名模式：仅导入图片信息至数据库")
            # 更新处理按钮状态
            if self.image_files:
                self.process_btn.setEnabled(True)
        else:
            self.toggle_output_dir(self.keep_original.isChecked())
    
    def toggle_output_dir(self, state):
        """根据保留原图选项的状态切换输出目录选择的可用性"""
        is_enabled = state == Qt.Checked
        
        # 如果选择了"不重命名"，始终禁用输出目录
        if self.rename_group.checkedId() == 0:
            self.output_btn.setEnabled(False)
            self.output_label.setText("不重命名模式：仅导入图片信息至数据库")
            return
        
        self.output_btn.setEnabled(is_enabled)
        
        if is_enabled:
            # 检查是否已选择有效的输出目录
            if os.path.exists(self.output_dir) and self.output_dir != os.getcwd():
                self.output_label.setText(self.output_dir)
            else:
                self.output_label.setText("请选择输出目录（不能使用程序当前目录）")
        else:
            self.output_label.setText("将直接对原图进行重命名")
        
        self.update_process_button()
    
    def log(self, message):
        """添加日志信息"""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        self.log_text.append(f"[{timestamp}] {message}")
        # 滚动到底部
        self.log_text.verticalScrollBar().setValue(
            self.log_text.verticalScrollBar().maximum()
        )
    
    def select_images(self):
        """选择图片文件"""
        files, _ = QFileDialog.getOpenFileNames(
            self, 
            '选择图片', 
            os.getcwd(), 
            'Image Files (*.png *.jpg *.jpeg *.bmp *.tif *.tiff)'
        )
        
        if files:
            self.image_files = files
            self.file_label.setText(f"已选择 {len(files)} 个文件")
            self.log(f"已选择 {len(files)} 个图片文件")
            self.update_process_button()
    
    def select_output_dir(self):
        """选择输出目录"""
        directory = QFileDialog.getExistingDirectory(
            self, 
            '选择输出目录', 
            os.getcwd()
        )
        
        if directory:
            self.output_dir = directory
            self.output_label.setText(self.output_dir)
            self.log(f"已选择输出目录: {self.output_dir}")
            self.update_process_button()
    
    def update_process_button(self):
        """根据选择情况更新处理按钮状态"""
        if self.image_files:
            # 如果是不重命名模式，无需检查输出目录
            if self.rename_group.checkedId() == 0:
                self.process_btn.setEnabled(True)
            # 如果保留原图，需要检查输出目录
            elif self.keep_original.isChecked():
                # 确保已选择输出目录且目录存在
                has_output_dir = os.path.exists(self.output_dir) and self.output_dir != os.getcwd()
                self.process_btn.setEnabled(has_output_dir)
                
                # 显示警告信息如果未选择输出目录
                if not has_output_dir:
                    self.output_label.setText("请选择输出目录（不能使用程序当前目录）")
                else:
                    self.output_label.setText(self.output_dir)
            else:
                # 如果不保留原图，直接启用处理按钮
                self.process_btn.setEnabled(True)
        else:
            self.process_btn.setEnabled(False)
    
    def process_images(self):
        """处理图片"""
        # 获取选项
        rename_option = self.rename_group.checkedId()
        prefix_option = self.prefix_combo.currentData()
        keep_original = self.keep_original.isChecked()
        
        # 检查是否选择了图片
        if not self.image_files:
            QMessageBox.warning(
                self, 
                '未选择图片', 
                '请先选择需要处理的图片',
                QMessageBox.Ok
            )
            return
            
        # 如果选择了保留原图，检查是否已选择输出目录
        if rename_option != 0 and keep_original:
            if not os.path.exists(self.output_dir) or self.output_dir == os.getcwd():
                QMessageBox.warning(
                    self, 
                    '未选择输出目录', 
                    '选择保留原图选项时，必须指定一个有效的输出目录（不能是程序当前目录）',
                    QMessageBox.Ok
                )
                return
        
        # 禁用界面控件
        self.select_btn.setEnabled(False)
        self.output_btn.setEnabled(False)
        self.process_btn.setEnabled(False)
        self.keep_original.setEnabled(False)
        self.rename_none.setEnabled(False)
        self.rename_timestamp.setEnabled(False)
        self.rename_hash.setEnabled(False)
        self.prefix_combo.setEnabled(False)
        
        # 确定输出目录（不重命名模式下无需输出目录）
        output_dir = ""
        if rename_option != 0:  # 不是不重命名模式
            output_dir = self.output_dir if keep_original else os.path.dirname(self.image_files[0])
        
        # 创建处理线程
        self.processor = ImageProcessor(
            self.image_files,
            output_dir,
            rename_option,
            prefix_option,
            keep_original,
            self.db_path
        )
        
        # 连接信号
        self.processor.update_progress.connect(self.update_progress)
        self.processor.update_log.connect(self.log)
        self.processor.processing_finished.connect(self.on_processing_finished)
        
        # 启动处理
        if rename_option == 0:
            self.log("开始导入图片信息到数据库...")
        else:
            self.log("开始处理图片...")
        self.processor.start()
    
    def update_progress(self, value):
        """更新进度条"""
        self.progress_bar.setValue(value)
    
    def on_processing_finished(self):
        """处理完成后的操作"""
        # 启用界面控件
        self.select_btn.setEnabled(True)
        self.rename_none.setEnabled(True)
        self.rename_timestamp.setEnabled(True)
        self.rename_hash.setEnabled(True)
        
        # 根据当前重命名选项设置其他控件状态
        is_no_rename = self.rename_group.checkedId() == 0
        self.prefix_combo.setEnabled(not is_no_rename)
        self.keep_original.setEnabled(not is_no_rename)
        self.output_btn.setEnabled(not is_no_rename and self.keep_original.isChecked())
        self.process_btn.setEnabled(True)
        
        # 显示处理完成信息
        if self.rename_group.checkedId() == 0:
            QMessageBox.information(
                self, 
                '导入完成', 
                '所有图片信息已导入数据库!',
                QMessageBox.Ok
            )
        else:
            QMessageBox.information(
                self, 
                '处理完成', 
                '所有图片处理完成!',
                QMessageBox.Ok
            )

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = ImageProcessorApp()
    window.show()
    sys.exit(app.exec_()) 