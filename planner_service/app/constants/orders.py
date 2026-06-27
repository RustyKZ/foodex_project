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

REDIS_RELEVANT_ORDERS_STATUSES = [
    ORDER_STATUS_CREATED, ORDER_STATUS_LIVE, ORDER_STATUS_COMPLETED, ORDER_STATUS_SUCCESS, ORDER_STATUS_DISPUTE, ORDER_STATUS_RESOLVED    
]