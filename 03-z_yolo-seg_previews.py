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
    
    log_filename = os.path.join(log_dir, f"segmentation_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
    
    # 配置日志格式
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_filename),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger()

# 载入YOLOv模型
class YOLOv11Seg:
    def __init__(self, model_path, logger):
        self.logger = logger
        self.logger.info(f"加载模型: {model_path}")
        try:
            # 方式1：尝试从ultralytics导入YOLO
            try:
                from ultralytics import YOLO
                self.model = YOLO(model_path)
                self.logger.info("使用ultralytics.YOLO加载模型成功")
            except (ImportError, Exception) as e:
                self.logger.warning(f"使用ultralytics.YOLO加载失败: {str(e)}，尝试备用方法")
                
                # 方式2：尝试使用YOLOv5直接加载
                import yolov5
                self.model = yolov5.load(model_path)
                self.logger.info("使用yolov5库加载模型成功")
                
            self.logger.info("模型加载成功")
        except Exception as e:
            self.logger.error(f"模型加载失败: {str(e)}")
            self.logger.error("请确保已安装所需的依赖: pip install ultralytics torch yolov5")
            raise

    def segment(self, img):
        # 对图片进行推理并进行分割
        self.logger.debug("开始图像分割")
        results = self.model(img)
        return results

# 文件处理线程
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
        
        # 设置日志
        self.logger = setup_logger(output_folder)
        self.yolo_model = None

    def log(self, message, level="info"):
        if level == "info":
            self.logger.info(message)
        elif level == "error":
            self.logger.error(message)
        elif level == "warning":
            self.logger.warning(message)
        elif level == "debug":
            self.logger.debug(message)
            
        # 发送到UI
        self.update_log.emit(message)

    def run(self):
        start_time = time.time()
        self.log(f"开始处理任务 - 时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self.log(f"输入文件夹: {self.input_folder}")
        self.log(f"输出文件夹: {self.output_folder}")
        
        try:
            # 加载模型
            self.yolo_model = YOLOv11Seg(self.model_path, self.logger)
            
            # 批量处理图片
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
                    self.log(f"图片尺寸: {w}x{h}, 通道数: {c}")
                    
                    # 分割处理
                    process_start = time.time()
                    results = self.yolo_model.segment(img)
                    process_time = time.time() - process_start
                    
                    # 检查结果格式，兼容不同版本的YOLO输出
                    try:
                        if hasattr(results, 'pandas'):
                            # YOLOv5格式
                            num_detections = len(results.pandas().xyxy[0])
                        else:
                            # Ultralytics YOLO格式
                            num_detections = len(results[0])
                    except Exception as e:
                        self.log(f"获取检测结果数量时出错: {str(e)}", "warning")
                        num_detections = "未知"
                        
                    self.log(f"检测到 {num_detections} 个目标，处理耗时: {process_time:.3f}秒")
                    
                    # 保存可视化结果
                    try:
                        output_filename = f"seg_{image_name}"
                        output_path = os.path.join(self.output_folder, output_filename)
                        
                        # 尝试不同的保存方法，兼容不同版本
                        try:
                            # 方法1: YOLOv5格式
                            if hasattr(results, 'save'):
                                results.save(save_dir=self.output_folder, exist_ok=True)
                            else:
                                # 方法2: Ultralytics YOLO格式
                                plotted_img = results[0].plot()
                                cv2.imwrite(output_path, plotted_img)
                        except Exception as e:
                            self.log(f"使用自带保存方法失败: {str(e)}", "warning")
                            
                            # 方法3: 手动绘制结果
                            plotted_img = img.copy()
                            # 这里需要根据实际模型输出格式定制绘制代码
                            # 简单示例：
                            try:
                                for det in results[0].boxes.data:
                                    x1, y1, x2, y2 = map(int, det[:4])
                                    cv2.rectangle(plotted_img, (x1, y1), (x2, y2), (0, 255, 0), 2)
                                cv2.imwrite(output_path, plotted_img)
                            except:
                                # 如果所有方法都失败，至少保存原图
                                cv2.imwrite(output_path, img)
                                self.log("无法渲染检测结果，已保存原图", "warning")
                        
                        self.log(f"结果已保存: {output_path}")
                        
                    except Exception as e:
                        self.log(f"保存结果时出错: {str(e)}", "error")
                        # 保存失败时至少保存原图
                        cv2.imwrite(os.path.join(self.output_folder, f"original_{image_name}"), img)
                        self.log(f"已保存原图: original_{image_name}")
                    
                    successful += 1
                    
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

# GUI界面类
class SegmentationApp(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("YOLOv-Seg 图像分割工具")
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
        self.log_text.append("欢迎使用YOLO图像分割工具！\n请先选择模型、输入及输出文件夹，然后点击开始处理。")
        self.log_text.append("注意：首次运行可能需要下载模型文件，请保持网络连接。")
        self.log_text.append("如遇到问题，请确保已安装必要的依赖：pip install ultralytics opencv-python PyQt5")

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
    window = SegmentationApp()
    window.show()
    sys.exit(app.exec_()) 