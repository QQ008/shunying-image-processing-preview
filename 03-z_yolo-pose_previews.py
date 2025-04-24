import sys
import torch
import cv2
import os
import numpy as np
import time
import logging
import matplotlib.pyplot as plt
from datetime import datetime
from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout, QPushButton, QLineEdit, QFileDialog, QLabel, QTextEdit, QScrollArea, QCheckBox
from PyQt5.QtCore import QThread, pyqtSignal, Qt

# 配置日志
def setup_logger(output_dir):
    log_dir = os.path.join(output_dir, "logs")
    os.makedirs(log_dir, exist_ok=True)
    
    log_filename = os.path.join(log_dir, f"pose_detection_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
    
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

# 载入YOLO-Pose模型
class YOLOPose:
    def __init__(self, model_path, logger):
        self.logger = logger
        self.logger.info(f"加载模型: {model_path}")
        try:
            # 尝试从ultralytics导入YOLO
            try:
                from ultralytics import YOLO
                self.model = YOLO(model_path)
                self.logger.info("使用ultralytics.YOLO加载模型成功")
            except (ImportError, Exception) as e:
                self.logger.warning(f"使用ultralytics.YOLO加载失败: {str(e)}")
                # 由于pose特性，只能使用ultralytics库
                self.logger.error("YOLO-pose需要ultralytics库支持，请安装: pip install ultralytics")
                raise
                
            self.logger.info("模型加载成功")
        except Exception as e:
            self.logger.error(f"模型加载失败: {str(e)}")
            self.logger.error("请确保已安装所需的依赖: pip install ultralytics torch opencv-python")
            raise

    def detect_pose(self, img):
        # 对图片进行人体姿态检测
        self.logger.debug("开始人体姿态检测")
        results = self.model(img, task='pose')
        return results

# 文件处理线程
class FileProcessingThread(QThread):
    update_progress = pyqtSignal(int)
    update_log = pyqtSignal(str)
    process_complete = pyqtSignal()

    def __init__(self, model_path, input_folder, output_folder, save_keypoints=True, save_skeleton=True):
        super().__init__()
        self.model_path = model_path
        self.input_folder = input_folder
        self.output_folder = output_folder
        self.save_keypoints = save_keypoints
        self.save_skeleton = save_skeleton
        
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
            self.yolo_model = YOLOPose(self.model_path, self.logger)
            
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
            
            # 创建特征数据保存目录
            keypoints_dir = os.path.join(self.output_folder, "keypoints_data")
            if self.save_keypoints:
                os.makedirs(keypoints_dir, exist_ok=True)
            
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
                    
                    # 姿态检测
                    process_start = time.time()
                    results = self.yolo_model.detect_pose(img)
                    process_time = time.time() - process_start
                    
                    # 获取检测到的人数
                    try:
                        num_persons = len(results[0])
                        self.log(f"检测到 {num_persons} 个人体，处理耗时: {process_time:.3f}秒")
                    except Exception as e:
                        self.log(f"获取检测结果数量时出错: {str(e)}", "warning")
                        num_persons = "未知"
                    
                    # 保存可视化结果
                    try:
                        base_name = os.path.splitext(image_name)[0]
                        
                        # 基本可视化结果 - 骨架图
                        if self.save_skeleton:
                            output_filename = f"pose_{image_name}"
                            output_path = os.path.join(self.output_folder, output_filename)
                            
                            # 使用YOLO内置的可视化方法
                            try:
                                plotted_img = results[0].plot()
                                cv2.imwrite(output_path, plotted_img)
                                self.log(f"骨架可视化结果已保存: {output_path}")
                            except Exception as e:
                                self.log(f"使用自带可视化方法失败: {str(e)}", "warning")
                                
                                # 手动绘制骨架
                                plotted_img = img.copy()
                                try:
                                    # 遍历所有检测到的人体
                                    for person in results[0]:
                                        # 获取关键点
                                        keypoints = person.keypoints.data
                                        if len(keypoints) > 0:
                                            keypoints = keypoints[0].cpu().numpy()
                                            
                                            # 画关键点
                                            for kp in keypoints:
                                                x, y, conf = int(kp[0]), int(kp[1]), kp[2]
                                                if conf > 0.5:  # 只画置信度高的关键点
                                                    cv2.circle(plotted_img, (x, y), 5, (0, 255, 0), -1)
                                            
                                            # 画骨架连接 (简化版，实际应根据YOLO-pose的关键点定义调整)
                                            pairs = [  # 定义骨架连接对
                                                (0, 1), (0, 2), (1, 3), (2, 4),  # 头和肩膀
                                                (5, 6), (5, 7), (7, 9), (6, 8), (8, 10),  # 手臂
                                                (5, 11), (6, 12), (11, 13), (12, 14), (13, 15), (14, 16)  # 腿
                                            ]
                                            
                                            for p in pairs:
                                                if keypoints[p[0], 2] > 0.5 and keypoints[p[1], 2] > 0.5:
                                                    pt1 = (int(keypoints[p[0], 0]), int(keypoints[p[0], 1]))
                                                    pt2 = (int(keypoints[p[1], 0]), int(keypoints[p[1], 1]))
                                                    cv2.line(plotted_img, pt1, pt2, (0, 0, 255), 2)
                                                    
                                    cv2.imwrite(output_path, plotted_img)
                                    self.log(f"手动骨架绘制结果已保存: {output_path}")
                                except Exception as e:
                                    self.log(f"手动绘制骨架失败: {str(e)}", "error")
                                    cv2.imwrite(output_path, img)
                                    self.log("无法渲染姿态结果，已保存原图", "warning")
                            
                        # 保存关键点数据到文件
                        if self.save_keypoints:
                            keypoints_file = os.path.join(keypoints_dir, f"{base_name}_keypoints.json")
                            try:
                                import json
                                keypoints_data = []
                                
                                # 提取每个人的关键点
                                for person_idx, person in enumerate(results[0]):
                                    # 获取边界框和置信度
                                    try:
                                        box = person.boxes.data[0][:4].cpu().numpy().tolist()
                                        confidence = float(person.boxes.conf[0].cpu().numpy())
                                    except:
                                        box = []
                                        confidence = 0.0
                                    
                                    # 获取关键点
                                    try:
                                        kps = person.keypoints.data[0].cpu().numpy()
                                        keypoints_list = []
                                        for kp in kps:
                                            keypoints_list.append({
                                                'x': float(kp[0]),
                                                'y': float(kp[1]),
                                                'confidence': float(kp[2])
                                            })
                                    except:
                                        keypoints_list = []
                                    
                                    person_data = {
                                        'person_id': person_idx,
                                        'bounding_box': box,
                                        'confidence': confidence,
                                        'keypoints': keypoints_list
                                    }
                                    keypoints_data.append(person_data)
                                
                                # 保存到JSON文件
                                with open(keypoints_file, 'w') as f:
                                    json.dump({
                                        'image': image_name,
                                        'width': w,
                                        'height': h,
                                        'persons': keypoints_data
                                    }, f, indent=2)
                                
                                self.log(f"关键点数据已保存: {keypoints_file}")
                            except Exception as e:
                                self.log(f"保存关键点数据失败: {str(e)}", "error")
                        
                        successful += 1
                        
                    except Exception as e:
                        self.log(f"保存结果时出错: {str(e)}", "error")
                        # 保存失败时至少保存原图
                        cv2.imwrite(os.path.join(self.output_folder, f"original_{image_name}"), img)
                        self.log(f"已保存原图: original_{image_name}")
                        failed += 1
                    
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
class PoseDetectionApp(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("YOLO-Pose 人体姿态检测工具")
        self.setGeometry(100, 100, 800, 600)

        self.model_path = ""
        self.input_folder = ""
        self.output_folder = ""
        self.save_keypoints = True
        self.save_skeleton = True

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

        # 选项设置
        self.keypoints_checkbox = QCheckBox("保存关键点数据 (JSON格式)")
        self.keypoints_checkbox.setChecked(True)
        layout.addWidget(self.keypoints_checkbox)
        
        self.skeleton_checkbox = QCheckBox("保存骨架可视化图像")
        self.skeleton_checkbox.setChecked(True)
        layout.addWidget(self.skeleton_checkbox)

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
        self.log_text.append("欢迎使用YOLO-Pose人体姿态检测工具！\n请先选择模型、输入及输出文件夹，然后点击开始处理。")
        self.log_text.append("注意：请确保使用的是支持姿态检测的YOLO-pose模型（例如yolov8n-pose.pt）。")
        self.log_text.append("如遇到问题，请确保已安装必要的依赖：pip install ultralytics opencv-python PyQt5")

    def select_model(self):
        options = QFileDialog.Options()
        self.model_path, _ = QFileDialog.getOpenFileName(self, "选择YOLO-Pose模型", "",
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
        
        # 获取选项设置
        self.save_keypoints = self.keypoints_checkbox.isChecked()
        self.save_skeleton = self.skeleton_checkbox.isChecked()
        
        # 禁用按钮
        self.start_button.setEnabled(False)
        self.start_button.setText("处理中...")
        
        # 创建处理线程
        self.processing_thread = FileProcessingThread(
            self.model_path, 
            self.input_folder, 
            self.output_folder,
            self.save_keypoints,
            self.save_skeleton
        )
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
    window = PoseDetectionApp()
    window.show()
    sys.exit(app.exec_())