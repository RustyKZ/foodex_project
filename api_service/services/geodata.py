import math
from decimal import Decimal

from constants.geodata import AVERAGE_KM_PER_DEGREE_LAT, EQUATOR_KM_PER_DEGREE_LON

from logger_config import get_logger
logger = get_logger(__name__)

def calculate_distance_km(point_1: dict, point_2: dict):
    try:
        if not isinstance(point_1, dict) or not isinstance(point_2, dict):
            logger.error(f"calculate_distance_km - incorrect input - point 1: {point_1}; point 2: {point_2}")
            return None    
        lat1 = float(point_1.get("latitude"))
        lon1 = float(point_1.get("longitude"))
        lat2 = float(point_2.get("latitude"))
        lon2 = float(point_2.get("longitude"))
        delta_lat = abs(lat1 - lat2)
        delta_lon = abs(lon1 - lon2)
        average_lat_rad = math.radians((lat1 + lat2) / 2)
        km_per_degree_lon = (EQUATOR_KM_PER_DEGREE_LON* math.cos(average_lat_rad))
        delta_lat_km = delta_lat * AVERAGE_KM_PER_DEGREE_LAT
        delta_lon_km = delta_lon * km_per_degree_lon
        distance_km = math.sqrt(delta_lat_km ** 2+ delta_lon_km ** 2)
        return Decimal(str(round(distance_km, 2)))
    
    except Exception as e:
        logger.error(f"calculate_distance_km - Exception error: {e} ")
        return None
    