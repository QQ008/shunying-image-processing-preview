import os
import shutil
import logging
import sys
from datetime import datetime

# 配置简单日志输出
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

logger = logging.getLogger('项目清理工具')

class ProjectCleaner:
    """项目清理工具，用于删除初始化后生成的临时文件、日志和数据库"""
    
    def __init__(self):
        # 需要清理的文件
        self.files_to_clean = [
            'app.log',
            'config.json',
            'images.db',
            'images.db-shm',
            'images.db-wal'
        ]
        
        # 需要清理的目录
        self.dirs_to_clean = [
            'exif_data',
            '__pycache__'
        ]
        
        # 记录清理结果
        self.cleaned_files = []
        self.cleaned_dirs = []
        self.failed_operations = []
    
    def confirm_cleaning(self):
        """确认用户是否真的要清理项目"""
        print("\n" + "="*60)
        print("警告：此操作将删除所有日志、配置和数据库文件！")
        print("这将使项目恢复到初始状态，所有处理结果将丢失！")
        print("="*60)
        
        confirm = input("\n请输入'YES'确认清理操作（必须大写）: ")
        return confirm == 'YES'
    
    def clean_files(self):
        """清理单个文件"""
        logger.info("开始清理文件...")
        
        for file_name in self.files_to_clean:
            if os.path.exists(file_name):
                try:
                    os.remove(file_name)
                    logger.info(f"已删除文件: {file_name}")
                    self.cleaned_files.append(file_name)
                except Exception as e:
                    error_msg = f"删除文件 {file_name} 失败: {str(e)}"
                    logger.error(error_msg)
                    self.failed_operations.append(error_msg)
            else:
                logger.info(f"文件不存在，跳过: {file_name}")
    
    def clean_directories(self):
        """清理目录"""
        logger.info("开始清理目录...")
        
        for dir_name in self.dirs_to_clean:
            if os.path.exists(dir_name):
                try:
                    shutil.rmtree(dir_name)
                    logger.info(f"已删除目录: {dir_name}")
                    self.cleaned_dirs.append(dir_name)
                except Exception as e:
                    error_msg = f"删除目录 {dir_name} 失败: {str(e)}"
                    logger.error(error_msg)
                    self.failed_operations.append(error_msg)
            else:
                logger.info(f"目录不存在，跳过: {dir_name}")
    
    def find_and_clean_pycache(self):
        """查找并清理所有__pycache__目录"""
        logger.info("查找并清理所有Python缓存目录...")
        
        for root, dirs, _ in os.walk('.'):
            for dir_name in dirs:
                if dir_name == '__pycache__':
                    pycache_path = os.path.join(root, dir_name)
                    try:
                        shutil.rmtree(pycache_path)
                        logger.info(f"已删除Python缓存目录: {pycache_path}")
                        self.cleaned_dirs.append(pycache_path)
                    except Exception as e:
                        error_msg = f"删除缓存目录 {pycache_path} 失败: {str(e)}"
                        logger.error(error_msg)
                        self.failed_operations.append(error_msg)
    
    def print_report(self):
        """打印清理报告"""
        print("\n" + "="*60)
        print("项目清理报告")
        print("="*60)
        
        print(f"\n已删除 {len(self.cleaned_files)} 个文件:")
        for file in self.cleaned_files:
            print(f"  - {file}")
        
        print(f"\n已删除 {len(self.cleaned_dirs)} 个目录:")
        for directory in self.cleaned_dirs:
            print(f"  - {directory}")
        
        if self.failed_operations:
            print(f"\n失败操作 ({len(self.failed_operations)}):")
            for failure in self.failed_operations:
                print(f"  ! {failure}")
        
        print("\n项目清理完成！")
        print("="*60)
    
    def run(self):
        """运行清理程序"""
        logger.info("项目清理工具启动")
        
        if not self.confirm_cleaning():
            logger.info("用户取消了清理操作")
            print("清理操作已取消")
            return False
        
        # 执行清理操作
        self.clean_files()
        self.clean_directories()
        self.find_and_clean_pycache()
        
        # 打印报告
        self.print_report()
        
        return True

if __name__ == "__main__":
    cleaner = ProjectCleaner()
    cleaner.run() 