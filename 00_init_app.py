import os
import sqlite3
import logging
import sys

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('app.log')
    ]
)
logger = logging.getLogger('InitApp')

class AppInitializer:
    def __init__(self, db_path='images.db'):
        self.db_path = db_path
        self.conn = None
        self.cursor = None
    
    def check_environment(self):
        """检查应用程序环境是否满足要求"""
        logger.info("检查应用程序环境...")
        
        # 检查PyQt5是否安装
        try:
            from PyQt5 import QtCore
            logger.info(f"PyQt5版本: {QtCore.QT_VERSION_STR}")
        except ImportError:
            logger.error("PyQt5未安装，请安装PyQt5")
            return False
        
        # 检查OpenCV是否安装
        try:
            import cv2
            logger.info(f"OpenCV版本: {cv2.__version__}")
        except ImportError:
            logger.error("OpenCV未安装，请安装OpenCV")
            return False
        
        # 检查torch是否安装
        try:
            import torch
            logger.info(f"PyTorch版本: {torch.__version__}")
        except ImportError:
            logger.error("PyTorch未安装，请安装PyTorch")
            return False
        
        logger.info("环境检查完成")
        return True
    
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
            
            # 创建原图信息表
            self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS images (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                original_filename TEXT NOT NULL,
                file_name TEXT NOT NULL,
                file_path TEXT NOT NULL,
                preview_path TEXT,
                upload_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                capture_time DATETIME,
                width INTEGER,
                height INTEGER,
                camera_model TEXT,
                lens_model TEXT,
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
            
            self.conn.commit()
            logger.info("数据库表初始化完成")
            return True
            
        except sqlite3.Error as e:
            logger.error(f"数据库初始化失败: {e}")
            return False
        finally:
            if self.conn:
                self.conn.close()
    
    def initialize_app(self):
        """执行完整的应用程序初始化"""
        logger.info("开始应用程序初始化...")
        
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
    else:
        print("应用程序初始化失败，请检查日志获取详细信息。") 