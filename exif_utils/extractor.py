"""
EXIF数据提取工具 - 基于纯Python库实现，确保跨平台兼容
"""

import logging
import os
import re
from datetime import datetime
from PIL import Image, ExifTags
from PIL.ExifTags import TAGS, GPSTAGS
import sqlite3

class ExifExtractor:
    """图片EXIF信息提取器"""
    
    def __init__(self, db_path='images.db'):
        """
        初始化EXIF提取器
        
        Args:
            db_path: 数据库路径
        """
        self.logger = logging.getLogger('ExifExtractor')
        self.db_path = db_path
        
    def get_exif_data(self, image_path):
        """
        获取图片的EXIF数据
        
        Args:
            image_path: 图片路径
            
        Returns:
            dict: 包含EXIF信息的字典，如果没有EXIF或出错则返回空字典
        """
        try:
            image = Image.open(image_path)
            exif_data = {}
            
            # 检查图片是否有EXIF信息
            if hasattr(image, '_getexif') and image._getexif():
                exif_info = image._getexif()
                if exif_info:
                    for tag, value in exif_info.items():
                        decoded = ExifTags.TAGS.get(tag, tag)
                        if decoded == "GPSInfo":
                            gps_data = {}
                            for gps_tag in value:
                                gps_decoded = GPSTAGS.get(gps_tag, gps_tag)
                                gps_data[gps_decoded] = value[gps_tag]
                            exif_data[decoded] = gps_data
                        else:
                            exif_data[decoded] = value
            
            # 添加基本图片信息
            exif_data['ImageSize'] = image.size
            exif_data['ImageFormat'] = image.format
            exif_data['ImageMode'] = image.mode
            
            return exif_data
            
        except Exception as e:
            self.logger.error(f"从图片提取EXIF信息失败: {str(e)}")
            return {}
    
    def extract_core_exif(self, image_path):
        """
        提取核心EXIF信息，仅包含关键字段
        
        Args:
            image_path: 图片路径
            
        Returns:
            dict: 包含核心EXIF信息的字典
        """
        all_exif = self.get_exif_data(image_path)
        
        # 初始化核心信息字典
        core_exif = {
            'capture_time': None,
            'width': None,
            'height': None,
            'camera_model': None,
            'lens_model': None,
            'focal_length': None,
            'shutter_speed': None,
            'aperture': None,
            'iso': None,
            'exposure_compensation': None,
            'white_balance': None,
            'gps_latitude': None,
            'gps_longitude': None
        }
        
        # 图像尺寸
        if 'ImageSize' in all_exif:
            core_exif['width'] = all_exif['ImageSize'][0]
            core_exif['height'] = all_exif['ImageSize'][1]
        
        # 拍摄时间 - 增强处理逻辑
        # 先尝试获取DateTimeOriginal，这通常是照片实际拍摄时间
        date_time = None
        date_str = None
        
        time_fields = ['DateTimeOriginal', 'DateTimeDigitized', 'DateTime']
        for field in time_fields:
            if field in all_exif and all_exif[field]:
                date_str = str(all_exif[field])
                break
        
        if date_str:
            # 尝试多种格式解析时间
            date_formats = [
                '%Y:%m:%d %H:%M:%S',      # 标准EXIF格式 2023:01:01 12:00:00
                '%Y:%m:%d %H:%M:%S.%f',   # 带毫秒的EXIF格式 2023:01:01 12:00:00.123
                '%Y-%m-%d %H:%M:%S',      # 常见替代格式 2023-01-01 12:00:00
                '%Y-%m-%d %H:%M:%S.%f',   # 带毫秒的替代格式 2023-01-01 12:00:00.123
                '%Y/%m/%d %H:%M:%S',      # 斜杠分隔格式 2023/01/01 12:00:00
                '%Y/%m/%d %H:%M:%S.%f'    # 带毫秒的斜杠分隔格式 2023/01/01 12:00:00.123
            ]
            
            # 先检查是否有特殊格式，包含毫秒但格式不标准
            ms_match = re.search(r'(\d{4}[-:/]\d{2}[-:/]\d{2}\s\d{2}:\d{2}:\d{2})(\.\d+)', date_str)
            if ms_match:
                # 分离出基本时间和毫秒部分
                base_time_str = ms_match.group(1)
                ms_str = ms_match.group(2)
                
                # 尝试解析基本时间部分
                for fmt in date_formats[:3]:  # 只使用不含毫秒的格式
                    try:
                        base_time = datetime.strptime(base_time_str, fmt)
                        # 手动添加毫秒部分
                        microseconds = int(float(ms_str) * 1000000)
                        date_time = base_time.replace(microsecond=microseconds)
                        break
                    except ValueError:
                        continue
            
            # 如果特殊处理不成功，尝试标准格式
            if not date_time:
                for fmt in date_formats:
                    try:
                        date_time = datetime.strptime(date_str, fmt)
                        break
                    except ValueError:
                        continue
            
            # 如果仍然无法解析，记录原始字符串
            if not date_time:
                self.logger.warning(f"无法解析拍摄时间格式: {date_str}")
                core_exif['capture_time'] = date_str
            else:
                core_exif['capture_time'] = date_time
                self.logger.info(f"成功解析拍摄时间: {date_time} (原始格式: {date_str})")
        
        # 相机型号
        for model_field in ['Model', 'CameraModel', 'Camera']:
            if model_field in all_exif and all_exif[model_field]:
                core_exif['camera_model'] = all_exif[model_field]
                break
        
        # 镜头信息
        for lens_field in ['LensModel', 'Lens', 'LensInfo']:
            if lens_field in all_exif and all_exif[lens_field]:
                core_exif['lens_model'] = all_exif[lens_field]
                break
        
        # 焦距
        if 'FocalLength' in all_exif:
            try:
                focal_length = all_exif['FocalLength']
                if hasattr(focal_length, 'numerator') and hasattr(focal_length, 'denominator'):
                    core_exif['focal_length'] = f"{focal_length.numerator/focal_length.denominator:.1f}mm"
                else:
                    core_exif['focal_length'] = f"{float(focal_length):.1f}mm"
            except:
                core_exif['focal_length'] = str(all_exif['FocalLength'])
        
        # 快门速度
        if 'ExposureTime' in all_exif:
            try:
                exposure = all_exif['ExposureTime']
                if hasattr(exposure, 'numerator') and hasattr(exposure, 'denominator'):
                    if exposure.numerator == 1:
                        core_exif['shutter_speed'] = f"1/{exposure.denominator}s"
                    else:
                        core_exif['shutter_speed'] = f"{exposure.numerator}/{exposure.denominator}s"
                else:
                    core_exif['shutter_speed'] = f"{float(exposure):.5f}s"
            except:
                core_exif['shutter_speed'] = str(all_exif['ExposureTime'])
        
        # 光圈值
        if 'FNumber' in all_exif:
            try:
                aperture = all_exif['FNumber']
                if hasattr(aperture, 'numerator') and hasattr(aperture, 'denominator'):
                    core_exif['aperture'] = f"f/{aperture.numerator/aperture.denominator:.1f}"
                else:
                    core_exif['aperture'] = f"f/{float(aperture):.1f}"
            except:
                core_exif['aperture'] = str(all_exif['FNumber'])
        
        # ISO感光度
        for iso_field in ['ISOSpeedRatings', 'ISO', 'PhotographicSensitivity']:
            if iso_field in all_exif and all_exif[iso_field]:
                core_exif['iso'] = all_exif[iso_field]
                break
        
        # 曝光补偿
        if 'ExposureBiasValue' in all_exif:
            try:
                ev = all_exif['ExposureBiasValue']
                if hasattr(ev, 'numerator') and hasattr(ev, 'denominator'):
                    value = ev.numerator / ev.denominator
                    if value > 0:
                        core_exif['exposure_compensation'] = f"+{value:.1f}EV"
                    else:
                        core_exif['exposure_compensation'] = f"{value:.1f}EV"
                else:
                    value = float(ev)
                    if value > 0:
                        core_exif['exposure_compensation'] = f"+{value:.1f}EV"
                    else:
                        core_exif['exposure_compensation'] = f"{value:.1f}EV"
            except:
                core_exif['exposure_compensation'] = str(all_exif['ExposureBiasValue'])
        
        # 白平衡
        if 'WhiteBalance' in all_exif:
            wb = all_exif['WhiteBalance']
            wb_value = None
            if isinstance(wb, int) or isinstance(wb, str) and wb.isdigit():
                wb_int = int(wb)
                if wb_int == 0:
                    wb_value = "自动"
                elif wb_int == 1:
                    wb_value = "手动"
                else:
                    wb_value = str(wb)
            else:
                wb_value = str(wb)
            core_exif['white_balance'] = wb_value
        
        # GPS信息
        if 'GPSInfo' in all_exif:
            gps_info = all_exif['GPSInfo']
            
            # 提取纬度
            if 'GPSLatitude' in gps_info and 'GPSLatitudeRef' in gps_info:
                try:
                    lat = gps_info['GPSLatitude']
                    lat_ref = gps_info['GPSLatitudeRef']
                    
                    lat_value = lat[0] + lat[1]/60 + lat[2]/3600
                    if lat_ref == 'S':
                        lat_value = -lat_value
                    
                    core_exif['gps_latitude'] = f"{lat_value:.6f}"
                except:
                    self.logger.warning("解析GPS纬度失败")
            
            # 提取经度
            if 'GPSLongitude' in gps_info and 'GPSLongitudeRef' in gps_info:
                try:
                    lon = gps_info['GPSLongitude']
                    lon_ref = gps_info['GPSLongitudeRef']
                    
                    lon_value = lon[0] + lon[1]/60 + lon[2]/3600
                    if lon_ref == 'W':
                        lon_value = -lon_value
                    
                    core_exif['gps_longitude'] = f"{lon_value:.6f}"
                except:
                    self.logger.warning("解析GPS经度失败")
        
        return core_exif
    
    def update_image_exif_in_db(self, image_id, exif_data, exif_csv_path=None):
        """
        更新数据库中图片的EXIF信息
        
        Args:
            image_id: 图片ID
            exif_data: EXIF数据字典
            exif_csv_path: EXIF CSV文件路径
            
        Returns:
            bool: 更新成功返回True，否则返回False
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # 构建更新SQL
            set_clauses = []
            params = []
            
            # 添加EXIF CSV路径
            if exif_csv_path:
                set_clauses.append("exif_csv_path = ?")
                params.append(exif_csv_path)
            
            # 添加EXIF数据
            for key, value in exif_data.items():
                if value is not None:
                    set_clauses.append(f"{key} = ?")
                    params.append(value)
            
            # 如果没有数据更新，直接返回成功
            if not set_clauses:
                return True
            
            # 构建完整的SQL语句
            sql = f"UPDATE images SET {', '.join(set_clauses)} WHERE id = ?"
            params.append(image_id)
            
            # 执行更新
            cursor.execute(sql, params)
            conn.commit()
            
            self.logger.info(f"已更新图片ID {image_id}的EXIF信息")
            return True
            
        except Exception as e:
            self.logger.error(f"更新数据库中的EXIF信息失败: {str(e)}")
            return False
        finally:
            if conn:
                conn.close()
                
    def get_image_path_by_id(self, image_id):
        """
        通过ID获取图片路径
        
        Args:
            image_id: 图片ID
            
        Returns:
            str: 图片路径，如果未找到则返回None
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("SELECT file_path FROM images WHERE id = ?", (image_id,))
            result = cursor.fetchone()
            
            if result:
                return result[0]
            return None
            
        except Exception as e:
            self.logger.error(f"获取图片路径失败: {str(e)}")
            return None
        finally:
            if conn:
                conn.close()

    def get_unprocessed_images(self, limit=None):
        """
        获取未处理EXIF的图片列表
        
        Args:
            limit: 返回的最大记录数，None表示不限制
            
        Returns:
            list: 未处理图片ID和路径的元组列表
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # 查询所有EXIF信息不完整的图片
            # 更新判断标准：一条记录要同时满足两个条件
            # 1. status为success
            # 2. 任何一个必要EXIF字段为NULL
            query = """
            SELECT id, file_path FROM images 
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
            ORDER BY id ASC  -- 添加排序，保证每次返回相同顺序
            """
            
            # 添加限制条件
            if limit is not None:
                query += f" LIMIT {limit}"
            
            cursor.execute(query)
            result = cursor.fetchall()
            
            # 记录查询到的未处理图片数量
            self.logger.info(f"找到 {len(result)} 张未完全提取EXIF的图片")
            
            # 如果结果太多，记录前几个ID以便调试
            if result:
                ids = [str(r[0]) for r in result[:5]]
                self.logger.debug(f"未处理图片ID示例: {', '.join(ids)}{' ...' if len(result) > 5 else ''}")
            
            return result
            
        except Exception as e:
            self.logger.error(f"获取未处理图片列表失败: {str(e)}")
            return []
        finally:
            if conn:
                conn.close() 