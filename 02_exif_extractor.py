import sys
import os
import time
import logging
import sqlite3
import json
from datetime import datetime
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QPushButton, QFileDialog, QLabel, 
    QVBoxLayout, QHBoxLayout, QWidget, QProgressBar, QTextEdit, 
    QRadioButton, QButtonGroup, QCheckBox, QGroupBox, QComboBox,
    QLineEdit, QMessageBox, QTableWidget, QTableWidgetItem, QHeaderView
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QPixmap, QImage

# 导入自定义EXIF处理模块
from exif_utils.extractor import ExifExtractor
from exif_utils.processor import ExifProcessor

# 配置日志 - 修改编码为utf-8
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('app.log', encoding='utf-8')  # 添加utf-8编码
    ]
)
logger = logging.getLogger('ExifExtractorApp')

class ExifExtractThread(QThread):
    """EXIF提取工作线程"""
    update_progress = pyqtSignal(int)
    update_log = pyqtSignal(str)
    update_image_info = pyqtSignal(int, dict)  # 图片ID和EXIF信息
    processing_finished = pyqtSignal()
    
    def __init__(self, mode, image_ids=None, save_csv=False, db_path='images.db'):
        """
        初始化线程
        
        Args:
            mode: 处理模式，'all'=处理所有，'selected'=处理选定图片
            image_ids: 选定的图片ID列表
            save_csv: 是否保存CSV
            db_path: 数据库路径
        """
        super().__init__()
        self.mode = mode
        self.image_ids = image_ids
        self.save_csv = save_csv
        self.db_path = db_path
        
    def run(self):
        """线程执行的主要逻辑"""
        self.update_log.emit("开始提取EXIF信息...")
        
        # 初始化EXIF处理器
        extractor = ExifExtractor(self.db_path)
        processor = ExifProcessor(self.db_path)
        
        try:
            # 根据模式获取需要处理的图片
            if self.mode == 'all':
                # 获取所有未处理的图片，不设置限制
                # 此方法已更新，只返回status为success的图片
                images = extractor.get_unprocessed_images(limit=None)
                self.update_log.emit(f"找到 {len(images)} 张未处理的图片")
            else:
                # 使用选定的图片ID
                images = []
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                
                # 只处理status为success的图片
                for image_id in self.image_ids:
                    try:
                        # 首先检查图片状态
                        cursor.execute("SELECT status, file_path FROM images WHERE id = ?", (image_id,))
                        result = cursor.fetchone()
                        
                        if result and result[0] == 'success':
                            file_path = result[1]
                            if file_path:
                                images.append((image_id, file_path))
                        else:
                            self.update_log.emit(f"跳过图片ID={image_id}，状态不是'success'")
                    except Exception as e:
                        self.update_log.emit(f"获取图片ID={image_id}信息失败: {str(e)}")
                
                if conn:
                    conn.close()
                
                self.update_log.emit(f"准备处理 {len(images)} 张选定的图片")
            
            # 处理每张图片
            total_images = len(images)
            if total_images == 0:
                self.update_log.emit("没有找到需要处理的图片")
                self.update_progress.emit(100)
                self.processing_finished.emit()
                return
                
            for i, (image_id, file_path) in enumerate(images):
                try:
                    # 更新进度
                    progress = int((i / total_images) * 100)
                    self.update_progress.emit(progress)
                    
                    # 检查文件是否存在
                    if not os.path.exists(file_path):
                        error_msg = f"文件不存在: {file_path}"
                        self.update_log.emit(f"错误: {error_msg}")
                        processor.mark_image_as_error(image_id, error_msg)
                        continue
                    
                    # 提取EXIF信息
                    self.update_log.emit(f"正在提取 ID={image_id} 的EXIF信息: {os.path.basename(file_path)}")
                    exif_data = extractor.extract_core_exif(file_path)
                    
                    # 保存CSV
                    csv_path = None
                    if self.save_csv:
                        # 获取原文件名作为CSV文件名基础
                        original_filename = os.path.splitext(os.path.basename(file_path))[0]
                        csv_filename = f"exif_{original_filename}.csv"
                        
                        # 获取完整EXIF数据用于CSV
                        full_exif = extractor.get_exif_data(file_path)
                        csv_path = processor.save_exif_to_csv(image_id, full_exif, csv_filename)
                        
                        if csv_path:
                            self.update_log.emit(f"已保存CSV: {csv_path}")
                        else:
                            self.update_log.emit(f"保存CSV失败")
                    
                    # 更新数据库
                    result = extractor.update_image_exif_in_db(image_id, exif_data, csv_path)
                    if result:
                        self.update_log.emit(f"已更新数据库中的EXIF信息")
                    else:
                        self.update_log.emit(f"更新数据库失败")
                    
                    # 发送信号更新界面
                    self.update_image_info.emit(image_id, exif_data)
                    
                except Exception as e:
                    error_msg = str(e)
                    self.update_log.emit(f"处理图片 ID={image_id} 时出错: {error_msg}")
                    processor.mark_image_as_error(image_id, error_msg)
            
            self.update_progress.emit(100)
            self.update_log.emit("所有图片EXIF提取完成")
            
        except Exception as e:
            self.update_log.emit(f"EXIF提取过程中出错: {str(e)}")
        
        self.processing_finished.emit()

class ExifExtractorApp(QMainWindow):
    """EXIF提取器应用界面"""
    
    def __init__(self):
        super().__init__()
        self.selected_image_ids = []
        
        # 从配置文件中读取数据库路径
        self.config_path = 'config.json'
        self.db_path = 'images.db'  # 默认路径
        
        self.initUI()
        self.load_config()  # 载入配置
        self.check_database()  # 检查数据库
        self.load_image_list()  # 加载图片列表
    
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
            self.log("数据库文件不存在，请先运行初始化程序 (00_init_app.py)")
            QMessageBox.warning(
                self, 
                '数据库未初始化', 
                '数据库文件不存在，请先运行初始化程序 (00_init_app.py)',
                QMessageBox.Ok
            )
    
    def initUI(self):
        """初始化用户界面"""
        self.setWindowTitle('EXIF信息提取工具')
        self.setGeometry(100, 100, 1200, 800)
        
        # 主布局
        main_layout = QVBoxLayout()
        
        # 顶部控制区域
        control_layout = QHBoxLayout()
        
        # 左侧处理选项
        process_group = QGroupBox("处理选项")
        process_layout = QVBoxLayout()
        
        self.process_all = QRadioButton("处理所有未提取EXIF的图片")
        self.process_selected = QRadioButton("仅处理选定的图片")
        
        self.process_group = QButtonGroup()
        self.process_group.addButton(self.process_all, 0)
        self.process_group.addButton(self.process_selected, 1)
        
        # 默认选择处理所有
        self.process_all.setChecked(True)
        
        process_layout.addWidget(self.process_all)
        process_layout.addWidget(self.process_selected)
        
        process_group.setLayout(process_layout)
        control_layout.addWidget(process_group)
        
        # 右侧保存选项
        save_group = QGroupBox("保存选项")
        save_layout = QVBoxLayout()
        
        self.save_csv = QCheckBox("保存完整EXIF信息到CSV文件")
        save_layout.addWidget(self.save_csv)
        
        # 添加按钮：生成EXIF报告
        self.generate_report_btn = QPushButton("生成所有图片的EXIF报告")
        self.generate_report_btn.clicked.connect(self.generate_exif_report)
        save_layout.addWidget(self.generate_report_btn)
        
        save_group.setLayout(save_layout)
        control_layout.addWidget(save_group)
        
        # 添加操作按钮
        action_group = QGroupBox("操作")
        action_layout = QVBoxLayout()
        
        self.refresh_btn = QPushButton("刷新图片列表")
        self.refresh_btn.clicked.connect(self.load_image_list)
        
        self.extract_btn = QPushButton("开始提取EXIF信息")
        self.extract_btn.clicked.connect(self.extract_exif)
        
        action_layout.addWidget(self.refresh_btn)
        action_layout.addWidget(self.extract_btn)
        
        action_group.setLayout(action_layout)
        control_layout.addWidget(action_group)
        
        main_layout.addLayout(control_layout)
        
        # 图片表格
        self.image_table = QTableWidget()
        self.image_table.setColumnCount(6)
        self.image_table.setHorizontalHeaderLabels(['ID', '文件名', '路径', '状态', '拍摄时间', '相机'])
        self.image_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.image_table.setSelectionMode(QTableWidget.MultiSelection)
        self.image_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.image_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.image_table.horizontalHeader().setStretchLastSection(True)
        
        main_layout.addWidget(self.image_table)
        
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
        
        self.log("EXIF提取器已启动")
    
    def log(self, message):
        """添加日志信息"""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        self.log_text.append(f"[{timestamp}] {message}")
        # 滚动到底部
        self.log_text.verticalScrollBar().setValue(
            self.log_text.verticalScrollBar().maximum()
        )
    
    def load_image_list(self):
        """从数据库加载图片列表"""
        try:
            # 连接数据库
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # 清空表格
            self.image_table.setRowCount(0)
            
            # 查询所有图片，包含所有需要的字段以判断是否完全提取
            cursor.execute("""
                SELECT id, file_name, file_path, status, 
                       capture_time, camera_model, width, height, 
                       focal_length, shutter_speed, aperture, iso, 
                       exposure_compensation, white_balance
                FROM images 
                ORDER BY id DESC
            """)
            
            rows = cursor.fetchall()
            
            # 初始化EXIF处理器以获取统计信息
            processor = ExifProcessor(self.db_path)
            unprocessed_count = processor.get_unprocessed_count()
            processed_count = processor.get_processed_count()
            
            self.log(f"数据库中共有 {len(rows)} 张图片, {processed_count} 张已提取EXIF, {unprocessed_count} 张未提取")
            
            # 填充表格
            self.image_table.setRowCount(len(rows))
            for i, row in enumerate(rows):
                id_ = row[0]
                file_name = row[1]
                file_path = row[2] 
                status = row[3]
                capture_time = row[4]
                camera_model = row[5]
                width = row[6]
                height = row[7]
                focal_length = row[8]
                shutter_speed = row[9]
                aperture = row[10]
                iso = row[11]
                exposure_compensation = row[12]
                white_balance = row[13]
                
                # ID
                self.image_table.setItem(i, 0, QTableWidgetItem(str(id_)))
                # 文件名
                self.image_table.setItem(i, 1, QTableWidgetItem(file_name))
                # 路径
                path_item = QTableWidgetItem(file_path)
                path_item.setToolTip(file_path)  # 添加工具提示，便于查看完整路径
                self.image_table.setItem(i, 2, path_item)
                
                # 状态 - 只有在status为success的情况下才考虑EXIF完整性
                status_item = QTableWidgetItem(status)
                if status == 'error':
                    status_item.setBackground(Qt.red)
                self.image_table.setItem(i, 3, status_item)
                
                # 检查是否完整提取了所有核心EXIF信息
                is_exif_complete = (
                    status == 'success' and
                    capture_time is not None and
                    camera_model is not None and
                    width is not None and
                    height is not None and
                    focal_length is not None and
                    shutter_speed is not None and
                    aperture is not None and
                    iso is not None and
                    exposure_compensation is not None and
                    white_balance is not None
                )
                
                # 如果任何一个关键EXIF字段为空，标记为未完全提取
                is_any_field_missing = (
                    status == 'success' and (
                        capture_time is None or
                        camera_model is None or
                        width is None or
                        height is None or
                        focal_length is None or
                        shutter_speed is None or
                        aperture is None or
                        iso is None or
                        exposure_compensation is None or
                        white_balance is None
                    )
                )
                
                # 拍摄时间
                time_item = QTableWidgetItem(str(capture_time) if capture_time else "未提取")
                if is_any_field_missing:
                    time_item.setBackground(Qt.yellow)
                    time_item.setToolTip("至少一个EXIF信息未提取完全")
                self.image_table.setItem(i, 4, time_item)
                
                # 相机型号
                camera_item = QTableWidgetItem(str(camera_model) if camera_model else "未提取")
                if not camera_model and status == 'success':
                    camera_item.setBackground(Qt.yellow)
                self.image_table.setItem(i, 5, camera_item)
            
            conn.close()
            
        except Exception as e:
            self.log(f"加载图片列表失败: {str(e)}")
    
    def extract_exif(self):
        """提取EXIF信息"""
        # 获取处理模式
        mode = 'all' if self.process_all.isChecked() else 'selected'
        
        # 如果选择处理选定图片，但未选择任何图片
        if mode == 'selected':
            selected_items = self.image_table.selectedItems()
            if not selected_items:
                QMessageBox.warning(
                    self, 
                    '未选择图片', 
                    '请先选择需要处理的图片',
                    QMessageBox.Ok
                )
                return
            
            # 获取选定的图片ID
            selected_rows = set()
            for item in selected_items:
                selected_rows.add(item.row())
            
            self.selected_image_ids = []
            for row in selected_rows:
                id_item = self.image_table.item(row, 0)
                status_item = self.image_table.item(row, 3)
                if id_item and status_item and status_item.text() == 'success':
                    self.selected_image_ids.append(int(id_item.text()))
            
            if not self.selected_image_ids:
                QMessageBox.warning(
                    self, 
                    '没有有效图片', 
                    '选定的图片中没有status为success的图片，无法处理',
                    QMessageBox.Ok
                )
                return
                
            self.log(f"已选择 {len(self.selected_image_ids)} 张有效图片进行处理")
        
        # 禁用界面控件
        self.extract_btn.setEnabled(False)
        self.refresh_btn.setEnabled(False)
        self.process_all.setEnabled(False)
        self.process_selected.setEnabled(False)
        self.save_csv.setEnabled(False)
        self.generate_report_btn.setEnabled(False)
        
        # 创建处理线程
        self.extractor_thread = ExifExtractThread(
            mode,
            self.selected_image_ids if mode == 'selected' else None,
            self.save_csv.isChecked(),
            self.db_path
        )
        
        # 连接信号
        self.extractor_thread.update_progress.connect(self.update_progress)
        self.extractor_thread.update_log.connect(self.log)
        self.extractor_thread.update_image_info.connect(self.update_image_info)
        self.extractor_thread.processing_finished.connect(self.on_processing_finished)
        
        # 启动处理
        self.log("开始提取EXIF信息...")
        self.extractor_thread.start()
    
    def update_progress(self, value):
        """更新进度条"""
        self.progress_bar.setValue(value)
    
    def update_image_info(self, image_id, exif_data):
        """更新界面中的图片信息"""
        # 查找图片ID对应的行
        for row in range(self.image_table.rowCount()):
            id_item = self.image_table.item(row, 0)
            if id_item and int(id_item.text()) == image_id:
                # 更新拍摄时间
                capture_time = str(exif_data.get('capture_time', ''))
                self.image_table.setItem(row, 4, QTableWidgetItem(capture_time))
                
                # 更新相机型号
                camera_model = str(exif_data.get('camera_model', ''))
                self.image_table.setItem(row, 5, QTableWidgetItem(camera_model))
                
                # 更新状态
                self.image_table.setItem(row, 3, QTableWidgetItem('success'))
                break
    
    def on_processing_finished(self):
        """处理完成后的操作"""
        # 启用界面控件
        self.extract_btn.setEnabled(True)
        self.refresh_btn.setEnabled(True)
        self.process_all.setEnabled(True)
        self.process_selected.setEnabled(True)
        self.save_csv.setEnabled(True)
        self.generate_report_btn.setEnabled(True)
        
        # 刷新图片列表
        self.load_image_list()
        
        # 显示处理完成信息
        QMessageBox.information(
            self, 
            '处理完成', 
            'EXIF信息提取完成!',
            QMessageBox.Ok
        )
    
    def generate_exif_report(self):
        """生成所有图片的EXIF报告"""
        try:
            processor = ExifProcessor(self.db_path)
            
            # 询问是否只包含已处理的图片
            reply = QMessageBox.question(
                self, 
                '生成报告', 
                '是否只包含已成功提取EXIF的图片?',
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes
            )
            
            # 确定输出路径
            file_path, _ = QFileDialog.getSaveFileName(
                self,
                '保存EXIF报告',
                os.path.join(os.getcwd(), f"exif_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"),
                'Excel文件 (*.xlsx)'
            )
            
            if not file_path:
                return
            
            self.log(f"正在生成EXIF报告: {file_path}")
            
            # 生成报告
            result = processor.generate_exif_report(output_path=file_path)
            
            if result:
                self.log(f"EXIF报告生成成功: {result}")
                QMessageBox.information(
                    self, 
                    '报告生成成功', 
                    f'EXIF报告已保存至:\n{result}',
                    QMessageBox.Ok
                )
            else:
                self.log("EXIF报告生成失败")
                QMessageBox.warning(
                    self, 
                    '报告生成失败', 
                    '生成EXIF报告时出错，请查看日志',
                    QMessageBox.Ok
                )
                
        except Exception as e:
            self.log(f"生成EXIF报告失败: {str(e)}")
            QMessageBox.critical(
                self, 
                '错误', 
                f'生成EXIF报告失败: {str(e)}',
                QMessageBox.Ok
            )

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = ExifExtractorApp()
    window.show()
    sys.exit(app.exec_()) 