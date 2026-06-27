from celery.schedules import crontab
from .celery_app import celery_app
from .config import settings
DAILY_ACCOUNTING_HOUR = settings.DAILY_ACCOUNTING_HOUR
DAILY_ACCOUNTING_MINUTE = settings.DAILY_ACCOUNTING_MINUTE

celery_app.conf.beat_schedule = {
    'every_minute_task': {
        'task': 'app.task_management.every_minute_task',
        'schedule': crontab(minute='*/1'),
    },

    'every_three_minutes_task': {
        'task': 'app.task_management.every_three_minutes_task',
        'schedule': crontab(minute='*/3'),
    },

    'five_minutes_task': {
        'task': 'app.task_management.five_minutes_task',
        'schedule': crontab(minute='*/5'),
    },

    'ten_minutes_task': {
        'task': 'app.task_management.ten_minutes_task',
        'schedule': crontab(minute='*/10'),
    },

    'fifteen_minutes_task': {
        'task': 'app.task_management.fifteen_minutes_task',
        'schedule': crontab(minute='*/15'),
    },

    'twenty_minutes_task': {
        'task': 'app.task_management.twenty_minutes_task',
        'schedule': crontab(minute='*/20'),
    },

    'thirty_minutes_task': {
        'task': 'app.task_management.thirty_minutes_task',
        'schedule': crontab(minute='*/30'),
    },

    'daily_accounting': {
        'task': 'app.task_management.daily_accounting',
        'schedule': crontab(
            hour= DAILY_ACCOUNTING_HOUR,
            minute= DAILY_ACCOUNTING_MINUTE
        ),
    }

}