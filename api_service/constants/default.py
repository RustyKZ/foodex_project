UNCATEGORIZED = "uncategorized"
MINIMAL_SEARCH_RADIUS_KM = 10
MAXIMAL_SEARCH_RADIUS_KM = 1000
DEFAULT_SEARCH_RADIUS_KM = 30
CUSTOMER_PRODUCT_CATALOG_FILTERS = {
    "keyword": "",
    "hide_without_address": True,
    "search_radius_km": DEFAULT_SEARCH_RADIUS_KM,
    "all_categories": True,
    "allowed_categories": [],    
    "only_favorite_products": False,
    "only_favorite_businesses": False,
    "hide_without_price": False,
    "hide_without_photo": False,
    "supplier_id": None
}
INDIVIDUAL_PRODUCT_CATALOG_FILTERS = {
    "keyword": "",
    "hide_without_address": True,
    "search_radius_km": DEFAULT_SEARCH_RADIUS_KM,
    "all_categories": True,
    "allowed_categories": [],    
    "only_favorite_products": False,
    "only_favorite_businesses": False,
    "hide_without_price": False,
    "hide_without_photo": False,
    "supplier_id": None
}
CUSTOMER_PRODUCT_CATALOG_BUNDLE = 20
INDIVIDUAL_PRODUCT_CATALOG_BUNDLE = 20
DEFAULT_LANGUAGE = "en"
DEFAULT_CURRENCY = "USD"
DEFAULT_GEODATA = {
    "latitude": 0,
    "longitude": 0
}
DEFAULT_TIMEZONE = "UTC"
PRODUCTS_ORDERED_FORWARD_DAYS = 20

BUSINESS_MESSAGES_DEFAULT_FILTER_SETTINGS = {
    "messages_show_closed_order_messages": True,
    "messages_hide_order_statuses": []
}

BUSINESS_ORDERS_DEFAULT_FILTER_SETTINGS = {
    "orders_hide_order_statuses": [],
    "orders_bundle_size": 20,
    "orders_date_diapason": False,
    "orders_date_diapason_start": 0,
    "orders_date_diapason_end": 0
}

SEARCH_COUNTER_AGENT_FILTERS = {
    "keyword": "",
    "hide_without_geodata": True,
    "search_radius_km": DEFAULT_SEARCH_RADIUS_KM,
    "only_favorite_businesses": False
}

SEARCH_COUNTER_AGENT_BUNDLE_SIZE = 20

STRING_LENGTH_255 = 255
STRING_LENGTH_50 = 50
STRING_LENGTH_5 = 5

ONE_DAY_SECONDS = 86400

INACTIVE_TIME_LOGOUT = 1800 #seconds
INACTIVE_TIME_HARD_LOGOUT = 3600 #seconds (logout for all INSTANCE_ID)
