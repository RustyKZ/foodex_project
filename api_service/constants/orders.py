from constants.business_types import SUPPLIER_ROLE, CUSTOMER_ROLE

# Order status
ORDER_STATUS_CREATED = "created" # Заказ создан контаргентом. OPENED
ORDER_STATUS_REJECTED = "rejected" # Заказ создан контаргентом, но отклонен бизнесом. CLOSED
ORDER_STATUS_LIVE = "live" # Заказ создан контаргентом и подтвержден бизнесом (стадия активного выполнения). OPENED
ORDER_STATUS_COMPLETED = "completed" # Заказ создан контаргентом, подтвержден бизнесом и выполнен бизнесом. OPENED
ORDER_STATUS_SUCCESS = "success" # Заказ создан контаргентом, подтвержден бизнесом, выполнен бизнесом. Выполнение подтвержедено контрагентом. CLOSED
ORDER_STATUS_CANCELLED = "cancelled" # Заказ создан контрагентом и отменен контрагентом. CLOSED
ORDER_STATUS_DROPPED = "dropped" # Заказ создан контрагентом, принят бизнесом к выполнению, но потом отменен бизнесом. CLOSED
ORDER_STATUS_DISPUTE = "dispute" # У заказа спорный статус (решается админом). OPENED
ORDER_STATUS_RESOLVED = "resolved" # Заказ имеет решение админа после Dispute. CLOSED

ALL_ORDER_TYPES = [
    ORDER_STATUS_CREATED, 
    ORDER_STATUS_REJECTED, 
    ORDER_STATUS_LIVE, 
    ORDER_STATUS_COMPLETED, 
    ORDER_STATUS_SUCCESS, 
    ORDER_STATUS_CANCELLED, 
    ORDER_STATUS_DROPPED, 
    ORDER_STATUS_DISPUTE, 
    ORDER_STATUS_RESOLVED
]

ORDER_OPENED_STATUSES = [
    ORDER_STATUS_CREATED,     
    ORDER_STATUS_LIVE, 
    ORDER_STATUS_COMPLETED,     
    ORDER_STATUS_DISPUTE
]

ORDER_OPENED_STATUSES_SUPPLIER = [    
    ORDER_STATUS_LIVE, 
    ORDER_STATUS_COMPLETED,
    ORDER_STATUS_DISPUTE
]

ORDER_OPENED_STATUSES_CUSTOMER = [
    ORDER_STATUS_CREATED,     
    ORDER_STATUS_LIVE,
    ORDER_STATUS_COMPLETED,
    ORDER_STATUS_DISPUTE
]

ORDER_CLOSED_STATUSES = [    
    ORDER_STATUS_REJECTED,     
    ORDER_STATUS_SUCCESS, 
    ORDER_STATUS_CANCELLED, 
    ORDER_STATUS_DROPPED,     
    ORDER_STATUS_RESOLVED
]

ORDER_ARCHIVED_STATE_TIME = 3600*24*5

ALL_ORDER_ACTIONS_POSSIBLE = [ "reject", "accept", "drop", "deliver", "dispute", "resolve", "cancel", "receive" ]

ORDER_ACTIONS_AVAILABLE = {
    "supplier": {
        "created": [
            {"reject": "rejected"},
            {"accept": "live"}
        ],
        "live": [
            {"drop": "dropped"},
            {"deliver": "completed"},
            {"dispute": "dispute"}
        ],
        "completed": [
            {"dispute": "dispute"}
        ],
        "dispute": [
            {"resolve": "resolved"}
        ]
    },
    "customer": {
        "created": [
            {"cancel": "cancelled"}        
        ],
        "live": [
            {"receive": "success"},
            {"dispute": "dispute"}
        ],
        "completed": [
            {"receive": "success"}, 
            {"dispute": "dispute"}
        ],
        "dispute": [
            {"resolve": "resolved"}
        ]
    }
}

RELIABILITY_STATUSES = {
    SUPPLIER_ROLE: {
        "consider_statuses": [            
            ORDER_STATUS_SUCCESS, 
            ORDER_STATUS_DROPPED, 
            ORDER_STATUS_DISPUTE, 
            ORDER_STATUS_RESOLVED
        ],
        "successfull_statuses": [
            ORDER_STATUS_SUCCESS,             
            ORDER_STATUS_RESOLVED          
        ]
    },
    CUSTOMER_ROLE: {
        "consider_statuses": [
            ORDER_STATUS_SUCCESS, 
            ORDER_STATUS_CANCELLED,             
            ORDER_STATUS_DISPUTE, 
            ORDER_STATUS_RESOLVED          
        ],
        "successfull_statuses": [
            ORDER_STATUS_SUCCESS, 
            ORDER_STATUS_RESOLVED          
        ]    
    }
}

