import sys
import torch
import cv2
import os
import numpy as np
import time
import logging
from datetime import datetime
from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout, QPushButton, QLineEdit, QFileDialog, QLabel, QTextEdit, QScrollArea
from PyQt5.QtCore import QThread, pyqtSignal, Qt

# 配置日志
def setup_logger(output_dir):
    log_dir = os.path.join(output_dir, "logs")
    os.makedirs(log_dir, exist_ok=True)
    
    log_filename = os.path.join(log_dir, f"human_segmentation_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_filename),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger()

class HumanSegmentor:
    def __init__(self, model_path, logger):
        self.logger = logger
        self.logger.info(f"加载模型: {model_path}")
        try:
            from ultralytics import YOLO
            self.model = YOLO(model_path)
            self.logger.info("使用ultralytics.YOLO加载模型成功")
            self.logger.info("模型加载成功")
        except Exception as e:
            self.logger.error(f"模型加载失败: {str(e)}")
            self.logger.error("请确保已安装所需的依赖: pip install ultralytics torch")
            raise

    def segment(self, img):
        # 对图片进行推理并进行分割
        self.logger.debug("开始人物分割")
        results = self.model(img, stream=True)
        return next(results)  # 返回第一个结果

class FileProcessingThread(QThread):
    update_progress = pyqtSignal(int)
    update_log = pyqtSignal(str)
    process_complete = pyqtSignal()

    def __init__(self, model_path, input_folder, output_folder):
        super().__init__()
        self.model_path = model_path
        self.input_folder = input_folder
        self.output_folder = output_folder
        
        # 确保输出目录存在
        os.makedirs(output_folder, exist_ok=True)
        os.makedirs(os.path.join(output_folder, "masks"), exist_ok=True)
        os.makedirs(os.path.join(output_folder, "overlays"), exist_ok=True)
        
        self.logger = setup_logger(output_folder)
        self.segmentor = None

    def log(self, message, level="info"):
        if level == "info":
            self.logger.info(message)
        elif level == "error":
            self.logger.error(message)
        elif level == "warning":
            self.logger.warning(message)
        elif level == "debug":
            self.logger.debug(message)
            
        self.update_log.emit(message)

    def run(self):
        start_time = time.time()
        self.log(f"开始处理任务 - 时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self.log(f"输入文件夹: {self.input_folder}")
        self.log(f"输出文件夹: {self.output_folder}")
        
        try:
            # 加载模型
            self.segmentor = HumanSegmentor(self.model_path, self.logger)
            
            # 获取所有图片文件
            images = [f for f in os.listdir(self.input_folder) if f.lower().endswith(('jpg', 'png', 'jpeg', 'bmp'))]
            total_images = len(images)
            
            self.log(f"找到 {total_images} 张图片待处理")
            
            if total_images == 0:
                self.log("没有找到可处理的图片，任务结束", "warning")
                self.process_complete.emit()
                return
                
            successful = 0
            failed = 0
            
            for i, image_name in enumerate(images):
                image_path = os.path.join(self.input_folder, image_name)
                self.log(f"处理图片 ({i+1}/{total_images}): {image_name}")
                
                try:
                    # 读取图片
                    img = cv2.imread(image_path)
                    if img is None:
                        self.log(f"无法读取图片: {image_path}", "error")
                        failed += 1
                        continue
                    
                    # 记录图片信息
                    h, w, c = img.shape
                    self.log(f"图片尺寸: {w}x{h}")
                    
                    # 分割处理
                    process_start = time.time()
                    results = self.segmentor.segment(img)
                    process_time = time.time() - process_start
                    
                    # 处理分割结果
                    if results.masks is not None and len(results.masks) > 0:
                        # 获取所有是人的mask和边界框
                        person_data = []  # 存储每个人的mask和边界框
                        for mask, cls, box in zip(results.masks.data, results.boxes.cls, results.boxes.xyxy):
                            if cls == 0:  # 0 表示 person 类别
                                person_data.append({
                                    'mask': mask.cpu().numpy(),
                                    'box': box.cpu().numpy()
                                })
                        
                        if person_data:
                            # 为每个人物单独处理
                            for idx, person in enumerate(person_data):
                                # 获取当前人物的mask和边界框
                                mask = person['mask']
                                box = person['box']
                                
                                # 转换mask为图像大小
                                mask = (mask * 255).astype(np.uint8)
                                mask = cv2.resize(mask, (w, h))
                                
                                # 获取边界框坐标
                                x1 = max(0, int(box[0]))
                                y1 = max(0, int(box[1]))
                                x2 = min(w, int(box[2]))
                                y2 = min(h, int(box[3]))
                                
                                # 裁剪mask和原图
                                cropped_mask = mask[y1:y2, x1:x2]
                                cropped_img = img[y1:y2, x1:x2].copy()
                                
                                # 创建透明背景的PNG
                                rgba = cv2.cvtColor(cropped_img, cv2.COLOR_BGR2BGRA)
                                # 将非人物区域设置为透明
                                rgba[cropped_mask == 0] = [0, 0, 0, 0]
                                
                                # 生成文件名（添加序号以区分同一图片中的不同人物）
                                base_name = os.path.splitext(image_name)[0]
                                
                                # 保存裁剪后的mask
                                mask_filename = f"mask_{base_name}_person{idx+1}.png"
                                mask_path = os.path.join(self.output_folder, "masks", mask_filename)
                                cv2.imwrite(mask_path, cropped_mask)
                                
                                # 保存裁剪后的透明PNG结果
                                person_filename = f"{base_name}_person{idx+1}.png"
                                person_path = os.path.join(self.output_folder, "overlays", person_filename)
                                cv2.imwrite(person_path, rgba)
                                
                                self.log(f"保存第 {idx+1} 个人物，裁剪尺寸: {x2-x1}x{y2-y1}")
                            
                            self.log(f"图片处理完成，共保存 {len(person_data)} 个人物")
                            successful += 1
                        else:
                            self.log(f"未检测到人物: {image_name}", "warning")
                            failed += 1
                    else:
                        self.log(f"未检测到任何目标: {image_name}", "warning")
                        failed += 1
                    
                    self.log(f"处理耗时: {process_time:.3f}秒")
                    
                except Exception as e:
                    self.log(f"处理图片 {image_name} 时发生错误: {str(e)}", "error")
                    failed += 1
                
                # 更新进度
                progress = int(((i + 1) / total_images) * 100)
                self.update_progress.emit(progress)
            
            # 完成处理
            total_time = time.time() - start_time
            self.log(f"处理完成，共处理: {total_images} 张图片，成功: {successful}，失败: {failed}")
            self.log(f"总耗时: {total_time:.2f}秒，平均每张: {total_time/total_images:.2f}秒")
            
        except Exception as e:
            self.log(f"处理过程中发生错误: {str(e)}", "error")
        
        self.process_complete.emit()

class HumanSegmentationApp(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("人物分割工具")
        self.setGeometry(100, 100, 800, 600)

        self.model_path = ""
        self.input_folder = ""
        self.output_folder = ""

        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()

        # 模型路径选择
        self.model_label = QLabel("选择模型路径")
        self.model_button = QPushButton("选择模型")
        self.model_button.clicked.connect(self.select_model)
        layout.addWidget(self.model_label)
        layout.addWidget(self.model_button)

        # 输入文件夹选择
        self.input_label = QLabel("选择输入文件夹")
        self.input_button = QPushButton("选择输入文件夹")
        self.input_button.clicked.connect(self.select_input_folder)
        layout.addWidget(self.input_label)
        layout.addWidget(self.input_button)

        # 输出文件夹选择
        self.output_label = QLabel("选择输出文件夹")
        self.output_button = QPushButton("选择输出文件夹")
        self.output_button.clicked.connect(self.select_output_folder)
        layout.addWidget(self.output_label)
        layout.addWidget(self.output_button)

        # 开始按钮
        self.start_button = QPushButton("开始处理")
        self.start_button.clicked.connect(self.start_processing)
        layout.addWidget(self.start_button)

        # 进度显示
        self.progress_label = QLabel("进度: 0%")
        layout.addWidget(self.progress_label)
        
        # 日志显示区域
        log_label = QLabel("处理日志:")
        layout.addWidget(log_label)
        
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setLineWrapMode(QTextEdit.NoWrap)
        
        # 创建滚动区域
        scroll_area = QScrollArea()
        scroll_area.setWidget(self.log_text)
        scroll_area.setWidgetResizable(True)
        scroll_area.setMinimumHeight(300)
        
        layout.addWidget(scroll_area)

        self.setLayout(layout)
        
        # 初始界面提示
        self.log_text.append("欢迎使用人物分割工具！\n")
        self.log_text.append("本工具专门用于分割图片中的人物。")
        self.log_text.append("处理后的结果将保存在两个子文件夹中：")
        self.log_text.append("- masks/: 包含人物区域的二值mask图")
        self.log_text.append("- overlays/: 只保留人物区域的图片")
        self.log_text.append("\n请先选择模型、输入及输出文件夹，然后点击开始处理。")
        self.log_text.append("注意：请确保使用支持分割任务的YOLO模型。")

    def select_model(self):
        options = QFileDialog.Options()
        self.model_path, _ = QFileDialog.getOpenFileName(self, "选择YOLO模型", "",
                                                         "Model Files (*.pt *.pth);;All Files (*)", options=options)
        if self.model_path:
            self.model_label.setText(f"模型路径: {self.model_path}")

    def select_input_folder(self):
        options = QFileDialog.Options()
        self.input_folder = QFileDialog.getExistingDirectory(self, "选择输入文件夹", options=options)
        if self.input_folder:
            self.input_label.setText(f"输入文件夹: {self.input_folder}")

    def select_output_folder(self):
        options = QFileDialog.Options()
        self.output_folder = QFileDialog.getExistingDirectory(self, "选择输出文件夹", options=options)
        if self.output_folder:
            self.output_label.setText(f"输出文件夹: {self.output_folder}")

    def start_processing(self):
        if not all([self.model_path, self.input_folder, self.output_folder]):
            self.log_text.append("错误: 请确保所有路径已选择！")
            return

        # 清空日志
        self.log_text.clear()
        self.log_text.append(f"初始化处理任务...\n时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        # 禁用按钮
        self.start_button.setEnabled(False)
        self.start_button.setText("处理中...")
        
        # 创建处理线程
        self.processing_thread = FileProcessingThread(self.model_path, self.input_folder, self.output_folder)
        self.processing_thread.update_progress.connect(self.update_progress)
        self.processing_thread.update_log.connect(self.update_log)
        self.processing_thread.process_complete.connect(self.processing_complete)
        self.processing_thread.start()

    def update_progress(self, progress):
        self.progress_label.setText(f"进度: {progress}%")

    def update_log(self, message):
        self.log_text.append(message)
        # 自动滚动到底部
        self.log_text.verticalScrollBar().setValue(self.log_text.verticalScrollBar().maximum())

    def processing_complete(self):
        self.progress_label.setText("处理完成！")
        self.start_button.setEnabled(True)
        self.start_button.setText("开始处理")
        self.log_text.append(f"\n处理任务完成 - 时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = HumanSegmentationApp()
    window.show()
    sys.exit(app.exec_()) 