import os
import sqlite3
import logging
import sys
import platform
import json

# 配置日志 - 修改编码为utf-8
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('app.log', encoding='utf-8')  # 添加utf-8编码
    ]
)
logger = logging.getLogger('InitApp')

class AppInitializer:
    def __init__(self, db_path='images.db', config_path='config.json'):
        self.db_path = db_path
        self.config_path = config_path
        self.conn = None
        self.cursor = None
        self.system_info = {}
        self.config = {}
    
    def check_environment(self):
        """检查应用程序环境是否满足要求，并收集系统信息"""
        logger.info("检查应用程序环境...")
        
        # 收集系统信息
        self.system_info['os'] = platform.system()
        self.system_info['os_version'] = platform.version()
        self.system_info['os_release'] = platform.release()
        self.system_info['architecture'] = platform.architecture()[0]
        self.system_info['processor'] = platform.processor()
        self.system_info['machine'] = platform.machine()
        
        logger.info(f"操作系统: {self.system_info['os']} {self.system_info['os_release']} {self.system_info['os_version']}")
        logger.info(f"处理器架构: {self.system_info['architecture']} {self.system_info['processor']}")
        
        # 检查PyQt5是否安装
        try:
            from PyQt5 import QtCore
            self.system_info['pyqt_version'] = QtCore.QT_VERSION_STR
            logger.info(f"PyQt5版本: {self.system_info['pyqt_version']}")
        except ImportError:
            logger.error("PyQt5未安装，请安装PyQt5")
            return False
        
        # 检查OpenCV是否安装
        try:
            import cv2
            self.system_info['opencv_version'] = cv2.__version__
            logger.info(f"OpenCV版本: {self.system_info['opencv_version']}")
        except ImportError:
            logger.error("OpenCV未安装，请安装OpenCV")
            return False
        
        # 检查torch是否安装
        try:
            import torch
            self.system_info['pytorch_version'] = torch.__version__
            self.system_info['cuda_available'] = torch.cuda.is_available()
            self.system_info['cuda_version'] = torch.version.cuda if torch.cuda.is_available() else "Not available"
            self.system_info['gpu_count'] = torch.cuda.device_count() if torch.cuda.is_available() else 0
            self.system_info['gpu_names'] = [torch.cuda.get_device_name(i) for i in range(torch.cuda.device_count())] if torch.cuda.is_available() else []
            
            gpu_info = ""
            if torch.cuda.is_available():
                gpu_info = f"CUDA {self.system_info['cuda_version']}, GPU设备: {', '.join(self.system_info['gpu_names'])}"
            else:
                gpu_info = "仅CPU模式"
                
            logger.info(f"PyTorch版本: {self.system_info['pytorch_version']}, {gpu_info}")
        except ImportError:
            logger.error("PyTorch未安装，请安装PyTorch")
            return False
        
        # 创建默认配置
        self.config = {
            'use_gpu': torch.cuda.is_available(),
            'gpu_device': 0 if torch.cuda.is_available() and torch.cuda.device_count() > 0 else -1,
            'threads': os.cpu_count(),  # 添加CPU线程数配置
            'exif_extraction': {
                'extract_all': True,
                'csv_output_dir': os.path.join(os.getcwd(), 'exif_data')
            },
            'database': {
                'path': self.db_path,
                'location': os.path.abspath(self.db_path)
            },
            'system_info': self.system_info
        }
        
        # 确保EXIF输出目录存在
        os.makedirs(self.config['exif_extraction']['csv_output_dir'], exist_ok=True)
        
        # 保存配置信息
        self.save_config()
        
        logger.info("环境检查完成")
        return True
    
    def save_config(self):
        """保存配置信息到JSON文件"""
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, ensure_ascii=False, indent=4)
            logger.info(f"配置已保存到: {self.config_path}")
            return True
        except Exception as e:
            logger.error(f"保存配置失败: {e}")
            return False
    
    def load_config(self):
        """从JSON文件加载配置信息"""
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    self.config = json.load(f)
                logger.info(f"从 {self.config_path} 加载配置成功")
                return True
            else:
                logger.warning(f"配置文件 {self.config_path} 不存在，将使用默认配置")
                return False
        except Exception as e:
            logger.error(f"加载配置失败: {e}")
            return False
    
    def init_database(self):
        """初始化SQLite3数据库，使用WAL模式"""
        logger.info(f"初始化数据库: {self.db_path}")
        
        try:
            # 连接到数据库
            self.conn = sqlite3.connect(self.db_path)
            self.cursor = self.conn.cursor()
            
            # 启用WAL模式
            self.cursor.execute("PRAGMA journal_mode=WAL;")
            logger.info("已启用WAL模式")
            
            # 创建配置表
            self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS app_config (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                config_key TEXT NOT NULL UNIQUE,
                config_value TEXT NOT NULL,
                description TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            ''')
            
            # 创建图片信息表
            self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS images (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                original_filename TEXT NOT NULL,
                file_name TEXT NOT NULL,
                file_path TEXT NOT NULL,
                preview_path TEXT,
                exif_csv_path TEXT,
                upload_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                capture_time DATETIME,
                width INTEGER,
                height INTEGER,
                camera_model TEXT,
                lens_model TEXT,
                focal_length TEXT,
                shutter_speed TEXT,
                aperture TEXT,
                iso TEXT,
                exposure_compensation TEXT,
                white_balance TEXT,
                gps_latitude TEXT,
                gps_longitude TEXT,
                status TEXT DEFAULT 'success',
                remark TEXT,
                error_message TEXT
            )
            ''')
            
            # 为了未来扩展性，创建处理后图片表
            self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS processed_images (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                original_id INTEGER,
                image_path TEXT NOT NULL,
                image_name TEXT NOT NULL,
                image_type TEXT,
                status TEXT DEFAULT 'success',
                error_message TEXT,
                remark TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (original_id) REFERENCES images (id)
            )
            ''')
            
            # 将系统信息和配置保存到数据库
            self.save_system_info_to_db()
            
            self.conn.commit()
            logger.info("数据库表初始化完成")
            return True
            
        except sqlite3.Error as e:
            logger.error(f"数据库初始化失败: {e}")
            return False
        finally:
            if self.conn:
                self.conn.close()
    
    def save_system_info_to_db(self):
        """将系统信息和配置保存到配置表"""
        try:
            # 保存系统信息
            for key, value in self.system_info.items():
                if isinstance(value, (list, dict)):
                    value = json.dumps(value, ensure_ascii=False)
                self.cursor.execute(
                    "INSERT OR REPLACE INTO app_config (config_key, config_value, description) VALUES (?, ?, ?)",
                    (f"system_info.{key}", str(value), f"系统信息: {key}")
                )
            
            # 保存配置信息
            for section, items in self.config.items():
                if section == 'system_info':
                    continue  # 已单独处理
                
                if isinstance(items, dict):
                    for key, value in items.items():
                        if isinstance(value, (list, dict)):
                            value = json.dumps(value, ensure_ascii=False)
                        self.cursor.execute(
                            "INSERT OR REPLACE INTO app_config (config_key, config_value, description) VALUES (?, ?, ?)",
                            (f"{section}.{key}", str(value), f"配置项: {section}.{key}")
                        )
                else:
                    self.cursor.execute(
                        "INSERT OR REPLACE INTO app_config (config_key, config_value, description) VALUES (?, ?, ?)",
                        (section, str(items), f"配置项: {section}")
                    )
            
            logger.info("系统信息和配置已保存到数据库")
            return True
        except sqlite3.Error as e:
            logger.error(f"保存系统信息和配置到数据库失败: {e}")
            return False
    
    def initialize_app(self):
        """执行完整的应用程序初始化"""
        logger.info("开始应用程序初始化...")
        
        # 尝试加载已有配置
        self.load_config()
        
        # 检查环境
        if not self.check_environment():
            logger.error("环境检查失败，初始化中止")
            return False
        
        # 初始化数据库
        if not self.init_database():
            logger.error("数据库初始化失败，初始化中止")
            return False
        
        logger.info("应用程序初始化成功")
        return True

if __name__ == "__main__":
    initializer = AppInitializer()
    if initializer.initialize_app():
        print("应用程序初始化成功！")
        
        # 显示系统详细信息
        print("\n系统信息:")
        for key, value in initializer.system_info.items():
            print(f"- {key}: {value}")
        
        # 显示推荐设置
        if initializer.system_info.get('cuda_available', False):
            print("\n检测到CUDA可用，推荐使用GPU进行图像处理和机器学习推理")
            for i, gpu_name in enumerate(initializer.system_info.get('gpu_names', [])):
                print(f"- GPU #{i}: {gpu_name}")
        else:
            print("\n未检测到CUDA，将使用CPU模式运行（图像处理和机器学习推理速度可能较慢）")
    else:
        print("应用程序初始化失败，请检查日志获取详细信息。")