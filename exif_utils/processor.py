"""
EXIF处理和保存模块 - 处理EXIF数据并提供保存功能
"""

import os
import csv
import json
import logging
from datetime import datetime
import sqlite3
import pandas as pd

class ExifProcessor:
    """EXIF数据处理器"""
    
    def __init__(self, db_path='images.db', csv_output_dir=None):
        """
        初始化EXIF处理器
        
        Args:
            db_path: 数据库路径
            csv_output_dir: CSV输出目录，如果为None则使用配置中的目录
        """
        self.logger = logging.getLogger('ExifProcessor')
        self.db_path = db_path
        
        # 如果没有指定CSV输出目录，尝试从配置中读取
        if csv_output_dir is None:
            try:
                with open('config.json', 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    self.csv_output_dir = config.get('exif_extraction', {}).get('csv_output_dir', os.path.join(os.getcwd(), 'exif_data'))
            except Exception as e:
                self.logger.warning(f"读取配置文件失败: {e}，使用默认输出目录")
                self.csv_output_dir = os.path.join(os.getcwd(), 'exif_data')
        else:
            self.csv_output_dir = csv_output_dir
        
        # 确保输出目录存在
        os.makedirs(self.csv_output_dir, exist_ok=True)
        self.logger.info(f"EXIF CSV输出目录: {self.csv_output_dir}")
    
    def save_exif_to_csv(self, image_id, exif_data, filename=None):
        """
        将EXIF数据保存为CSV文件
        
        Args:
            image_id: 图片ID
            exif_data: EXIF数据字典
            filename: 自定义文件名，如果为None则使用图片ID
            
        Returns:
            str: CSV文件路径，保存失败则返回None
        """
        try:
            # 确定CSV文件名
            if filename is None:
                csv_filename = f"exif_{image_id}.csv"
            else:
                # 确保扩展名为.csv
                if not filename.lower().endswith('.csv'):
                    csv_filename = f"{filename}.csv"
                else:
                    csv_filename = filename
            
            # 完整CSV路径
            csv_path = os.path.join(self.csv_output_dir, csv_filename)
            
            # 将EXIF数据转换为列表格式
            exif_list = []
            for key, value in exif_data.items():
                # 处理嵌套字典
                if isinstance(value, dict):
                    for sub_key, sub_value in value.items():
                        exif_list.append([f"{key}.{sub_key}", str(sub_value)])
                # 处理列表
                elif isinstance(value, list):
                    exif_list.append([key, json.dumps(value)])
                # 处理其他类型
                else:
                    exif_list.append([key, str(value)])
            
            # 写入CSV
            with open(csv_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(['Tag', 'Value'])  # 写入表头
                writer.writerows(exif_list)
            
            self.logger.info(f"已保存EXIF数据到CSV: {csv_path}")
            return csv_path
            
        except Exception as e:
            self.logger.error(f"保存EXIF数据到CSV失败: {str(e)}")
            return None
    
    def generate_exif_report(self, image_ids=None, output_path=None):
        """
        生成多张图片的EXIF报告
        
        Args:
            image_ids: 图片ID列表，如果为None则处理所有已有EXIF的图片
            output_path: 输出文件路径，如果为None则自动生成
            
        Returns:
            str: 报告文件路径，生成失败则返回None
        """
        try:
            # 连接数据库
            conn = sqlite3.connect(self.db_path)
            
            # 构建查询
            if image_ids:
                # 将ID列表转换为用于SQL的字符串
                ids_str = ','.join(f'"{id_}"' for id_ in image_ids)
                query = f"""
                SELECT id, file_name, width, height, camera_model, lens_model,
                       focal_length, shutter_speed, aperture, iso, exposure_compensation,
                       white_balance, capture_time
                FROM images 
                WHERE id IN ({ids_str})
                ORDER BY capture_time
                """
            else:
                # 查询所有已有EXIF的图片
                query = """
                SELECT id, file_name, width, height, camera_model, lens_model,
                       focal_length, shutter_speed, aperture, iso, exposure_compensation,
                       white_balance, capture_time
                FROM images 
                WHERE capture_time IS NOT NULL
                ORDER BY capture_time
                """
            
            # 使用pandas读取数据
            df = pd.read_sql_query(query, conn)
            
            # 确定输出路径
            if output_path is None:
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                output_path = os.path.join(self.csv_output_dir, f"exif_report_{timestamp}.xlsx")
            
            # 保存为Excel
            df.to_excel(output_path, index=False, sheet_name='EXIF数据')
            
            self.logger.info(f"已生成EXIF报告: {output_path}")
            return output_path
            
        except Exception as e:
            self.logger.error(f"生成EXIF报告失败: {str(e)}")
            return None
        finally:
            if conn:
                conn.close()
    
    def get_processed_count(self):
        """
        获取已处理EXIF的图片数量
        
        Returns:
            int: 已处理图片数量
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # 首先获取所有有效图片数量
            cursor.execute("SELECT COUNT(*) FROM images WHERE status = 'success'")
            total_valid = cursor.fetchone()[0]
            
            # 使用更全面的标准：所有必要EXIF信息都存在的图片
            cursor.execute("""
            SELECT COUNT(*) FROM images 
            WHERE 
                status = 'success' AND
                capture_time IS NOT NULL AND 
                camera_model IS NOT NULL AND 
                width IS NOT NULL AND
                height IS NOT NULL AND
                focal_length IS NOT NULL AND
                shutter_speed IS NOT NULL AND
                aperture IS NOT NULL AND
                iso IS NOT NULL AND
                exposure_compensation IS NOT NULL AND
                white_balance IS NOT NULL
            """)
            count = cursor.fetchone()[0]
            
            self.logger.info(f"数据库中共有 {total_valid} 张有效图片, 其中 {count} 张已完整提取EXIF")
            return count
            
        except Exception as e:
            self.logger.error(f"获取已处理图片数量失败: {str(e)}")
            return 0
        finally:
            if conn:
                conn.close()
    
    def get_unprocessed_count(self):
        """
        获取未处理EXIF的图片数量
        
        Returns:
            int: 未处理图片数量
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # 首先获取所有有效图片数量
            cursor.execute("SELECT COUNT(*) FROM images WHERE status = 'success'")
            total_valid = cursor.fetchone()[0]
            
            # 使用更全面的标准：至少一个必要EXIF信息不存在的图片
            cursor.execute("""
            SELECT COUNT(*) FROM images 
            WHERE status = 'success' AND (
                capture_time IS NULL OR 
                camera_model IS NULL OR 
                width IS NULL OR
                height IS NULL OR
                focal_length IS NULL OR
                shutter_speed IS NULL OR
                aperture IS NULL OR
                iso IS NULL OR
                exposure_compensation IS NULL OR
                white_balance IS NULL
            )
            """)
            count = cursor.fetchone()[0]
            
            self.logger.info(f"数据库中共有 {total_valid} 张有效图片, 其中 {count} 张需要提取EXIF")
            return count
            
        except Exception as e:
            self.logger.error(f"获取未处理图片数量失败: {str(e)}")
            return 0
        finally:
            if conn:
                conn.close()
    
    def mark_image_as_error(self, image_id, error_message):
        """
        将图片标记为处理出错
        
        Args:
            image_id: 图片ID
            error_message: 错误信息
            
        Returns:
            bool: 标记成功返回True，否则返回False
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute(
                "UPDATE images SET status = 'error', error_message = ? WHERE id = ?",
                (error_message, image_id)
            )
            
            conn.commit()
            self.logger.info(f"已将图片ID {image_id}标记为处理出错: {error_message}")
            return True
            
        except Exception as e:
            self.logger.error(f"标记图片处理出错失败: {str(e)}")
            return False
        finally:
            if conn:
                conn.close() 