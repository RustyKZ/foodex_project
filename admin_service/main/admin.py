from django.contrib import admin
from main.db_models.app_users import AppUser, UserBlacklist, UserGreylist
from main.db_models.busineses import Business, BusinessTranslation
from main.db_models.interface import LanguageInterface
from main.db_models.monitoring import AppError, UserAction, SystemAction
from main.db_models.reviews import ReviewBusiness, ReviewProduct
from main.db_models.finances import TariffPlan, AdCampaignBusinessPromo, PaymentMethod, Payment, StarPaymentData
from main.db_models.messages import Message, Notification
from main.db_models.products import Measure, Product, ProductTranslation, Category
from main.db_models.orders import Order, OrderItem
from main.db_models.bot_models import BotMessages, BotCommands

from datetime import datetime, timezone
from django import forms
from django.contrib.admin.widgets import AdminSplitDateTime

@admin.register(AppUser)
class AppUsersAdmin(admin.ModelAdmin):
    list_display = ['id', 'tg_id', 'tg_username', 'username', 'reg_date_formatted']
    def reg_date_formatted(self, obj):
        if obj.reg_date:            
            dt = datetime.fromtimestamp(obj.reg_date, tz=timezone.utc)
            return dt.strftime("%Y-%m-%d - %H:%M:%S (UTC)")
        return ""
    reg_date_formatted.short_description = "Reg Date (formatted)"


@admin.register(UserGreylist)
class UserGreylistAdmin(admin.ModelAdmin):
    list_display = ['id', 'user_id', 'tg_id', 'phone', 'email', 'add_date_formatted', 'log_length']
    def add_date_formatted(self, obj):
        if obj.add_date:            
            dt = datetime.fromtimestamp(obj.add_date, tz=timezone.utc)
            return dt.strftime("%Y-%m-%d - %H:%M:%S (UTC)")
        return ""
    def log_length(self, obj):
        if isinstance(obj.log, list):
            return len(obj.log)
        return 0
    add_date_formatted.short_description = "Add Date (formatted)"
    log_length.short_description = "Log Length"


@admin.register(UserBlacklist)
class UserBlacklistAdmin(admin.ModelAdmin):
    list_display = ['id', 'user_id', 'tg_id', 'phone', 'email', 'add_date_formatted', 'log_length']
    def add_date_formatted(self, obj):
        if obj.add_date:            
            dt = datetime.fromtimestamp(obj.add_date, tz=timezone.utc)
            return dt.strftime("%Y-%m-%d - %H:%M:%S (UTC)")
        return ""
    def log_length(self, obj):
        if isinstance(obj.log, list):
            return len(obj.log)
        return 0
    add_date_formatted.short_description = "Add Date (formatted)"
    log_length.short_description = "Log Length"


@admin.register(Business)
class BusinessAdmin(admin.ModelAdmin):
    list_display = ['id', 'business_type', 'owner_id', 'name', 'reg_date_formatted', 'staff', 'tariff', 'end_tariff_date_formatted', 'active']
    def reg_date_formatted(self, obj):
        if obj.reg_date:            
            dt = datetime.fromtimestamp(obj.reg_date, tz=timezone.utc)
            return dt.strftime("%Y-%m-%d - %H:%M:%S (UTC)")
        return ""
    def end_tariff_date_formatted(self, obj):
        if obj.end_tariff_date and obj.end_tariff_date != 0:            
            dt = datetime.fromtimestamp(obj.end_tariff_date, tz=timezone.utc)
            return dt.strftime("%Y-%m-%d - %H:%M:%S (UTC)")
        return ""
    reg_date_formatted.short_description = "Reg Date:"
    end_tariff_date_formatted.short_description = "Tariff End:"


@admin.register(BusinessTranslation)
class BusinessTranslationAdmin(admin.ModelAdmin):
    list_display = ['id', 'language', 'business_id', 'name']



@admin.register(LanguageInterface)
class LanguageInterfaceAdmin(admin.ModelAdmin):
    list_display = ['id', 'label', 'name_english', 'name_native', 'available']


@admin.register(AppError)
class AppErrorAdmin(admin.ModelAdmin):
    list_display = ['id', 'date_formatted', 'service', 'function', 'error_short', 'context']
    def date_formatted(self, obj):
        if obj.date:
            dt = datetime.fromtimestamp(obj.date, tz=timezone.utc)
            return dt.strftime("%Y-%m-%d - %H:%M:%S (UTC)")
        return ""
    date_formatted.short_description = "Date:"


@admin.register(SystemAction)
class SystemActionAdmin(admin.ModelAdmin):
    list_display = ['id', 'date_formatted', 'service', 'event', 'status', 'duration']
    def date_formatted(self, obj):
        if obj.date:
            dt = datetime.fromtimestamp(obj.date, tz=timezone.utc)
            return dt.strftime("%Y-%m-%d - %H:%M:%S (UTC)")
        return ""
    date_formatted.short_description = "Date:"


@admin.register(UserAction)
class UserActionAdmin(admin.ModelAdmin):
    list_display = ['id', 'date_formatted', 'user_id', 'action_type', 'entity_type', 'entity_id']
    def date_formatted(self, obj):
        if obj.date:
            dt = datetime.fromtimestamp(obj.date, tz=timezone.utc)
            return dt.strftime("%Y-%m-%d - %H:%M:%S (UTC)")
        return ""
    date_formatted.short_description = "Date:"


@admin.register(ReviewBusiness)
class ReviewBusinessAdmin(admin.ModelAdmin):
    list_display = ['id', 'banned_by_admin', 'date_formatted', 'business_id', 'author_user_id', 'author_business_id', 'rate']
    def date_formatted(self, obj):
        if obj.date:
            dt = datetime.fromtimestamp(obj.date, tz=timezone.utc)
            return dt.strftime("%Y-%m-%d - %H:%M:%S (UTC)")
        return ""
    date_formatted.short_description = "Date:"


@admin.register(ReviewProduct)
class ReviewProductAdmin(admin.ModelAdmin):
    list_display = ['id', 'banned_by_admin', 'date_formatted', 'product_id', 'business_id', 'author_user_id', 'author_business_id', 'rate']
    def date_formatted(self, obj):
        if obj.date:
            dt = datetime.fromtimestamp(obj.date, tz=timezone.utc)
            return dt.strftime("%Y-%m-%d - %H:%M:%S (UTC)")
        return ""
    date_formatted.short_description = "Date:"


@admin.register(TariffPlan)
class TariffPlanAdmin(admin.ModelAdmin):
    list_display = ['slug', 'name', 'day_cost', 'month_cost', 'year_cost', 'active']


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ['id', 'date_formatted', 'sender_business', 'receiver_business', 'read_users']
    def date_formatted(self, obj):
        if obj.date:
            dt = datetime.fromtimestamp(obj.date, tz=timezone.utc)
            return dt.strftime("%Y-%m-%d - %H:%M:%S (UTC)")
        return ""
    date_formatted.short_description = "Date:"


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ['id', 'date_formatted', 'receiver_user', 'receiver_business', 'type', 'is_sample', 'read_date_formatted']
    def date_formatted(self, obj):
        if obj.date:
            dt = datetime.fromtimestamp(obj.date, tz=timezone.utc)
            return dt.strftime("%Y-%m-%d - %H:%M:%S (UTC)")
        return ""
    date_formatted.short_description = "Date:"

    def read_date_formatted(self, obj):
        if obj.read_date:
            dt = datetime.fromtimestamp(obj.date, tz=timezone.utc)
            return dt.strftime("%Y-%m-%d - %H:%M:%S (UTC)")
        return ""
    read_date_formatted.short_description = "Read:"


@admin.register(Measure)
class MeasureAdmin(admin.ModelAdmin):
    list_display = [
        'code',
        'name',
        'name_short',
        'get_type_display',
        'get_system_display',
        'order',
        'active',
    ]



@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'order', 'active']


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ['id', 'business_id', 'name', 'sku', 'measure_code', 'price', 'category_code', 'active', 'deleted']


@admin.register(ProductTranslation)
class ProductTranslationAdmin(admin.ModelAdmin):
    list_display = ['product_id', 'language', 'name', 'description']


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ['id', 'date_formatted', 'name', 'supplier_id', 'customer_id', 'individual_id', 'status', 'cart_order_date']
    def date_formatted(self, obj):
        if obj.date:
            dt = datetime.fromtimestamp(obj.date, tz=timezone.utc)
            return dt.strftime("%Y-%m-%d - %H:%M:%S (UTC)")
        return ""
    date_formatted.short_description = "Date created:"


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ['id', 'order_id', 'product_id', 'measure_code', 'price', 'amount', 'cost', 'confirmed']
    def date_formatted(self, obj):
        if obj.date:
            dt = datetime.fromtimestamp(obj.date, tz=timezone.utc)
            return dt.strftime("%Y-%m-%d - %H:%M:%S (UTC)")
        return ""
    date_formatted.short_description = "Date created:"



class BotMessagesAdminForm(forms.ModelForm):
    sending_date_human = forms.SplitDateTimeField(
        label="🕒 Date message sending (human)",
        required=True,
        widget=AdminSplitDateTime()
    )

    class Meta:
        model = BotMessages
        exclude = []  # Либо перечисли поля явно

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        inst = self.instance
        if inst:
            if inst.sending_date:
                self.fields['sending_date_human'].initial = datetime.utcfromtimestamp(inst.sending_date)

    def save(self, commit=True):
        self.instance.sending_date = int(self.cleaned_data['sending_date_human'].timestamp())
        
        return super().save(commit)


@admin.register(BotMessages)
class BotMesagesAdmin(admin.ModelAdmin):
    form = BotMessagesAdminForm
    readonly_fields = ['date', 'sended', 'sending_date']

    list_display = ['id', 'date', 'theme', 'sending_date_formatted', 'confirmed', 'sended', 'not_actual']

    fields = [
        'sending_date', 
        'sending_date_human',
        'theme',
        'userlist',
        'message_data',
        'confirmed',
        'sended',
        'not_actual'
    ]

    def sending_date_formatted(self, obj):
        if obj.sending_date:            
            dt = datetime.fromtimestamp(obj.sending_date, tz=timezone.utc)
            return dt.strftime("%Y-%m-%d - %H:%M:%S (UTC)")
        return ""
    sending_date_formatted.short_description = "Sending date"


@admin.register(BotCommands)
class BotCommandsAdmin(admin.ModelAdmin):
    list_display = ['id', 'command', 'description']


@admin.register(AdCampaignBusinessPromo)
class AdCampaignBusinessPromoAdmin(admin.ModelAdmin):
    list_display = ['id', 'business_id', 'deposit_credits', 'date_start_formatted', 'date_end_formatted', 'daily_credits', 'remaining_credits', 'active', 'deleted']

    def date_start_formatted(self, obj):
        if obj.date_start:
            dt = datetime.fromtimestamp(obj.date_start, tz=timezone.utc)
            return dt.strftime("%Y-%m-%d - %H:%M:%S (UTC)")
        return ""
    def date_end_formatted(self, obj):
        if obj.date_end:
            dt = datetime.fromtimestamp(obj.date_end, tz=timezone.utc)
            return dt.strftime("%Y-%m-%d - %H:%M:%S (UTC)")
        return ""
    
    date_start_formatted.short_description = "Date start:"
    date_end_formatted.short_description = "Date end:"


@admin.register(PaymentMethod)
class PaymentMethodAdmin(admin.ModelAdmin):
    list_display = ['id', 'code', 'name', 'currency', 'active', 'show_on_frontend', 'credits_per_unit_display', 'type', 'priority']
    @admin.display(description='Credits/1 currency')
    def credits_per_unit_display(self, obj):
        return obj.credits_per_unit
    


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ['id', 'user_id', 'date_formatted', 'method_code', 'amount', 'currency', 'credits_received', 'confirmed', 'processed', 'deleted']

    def date_formatted(self, obj):
        if obj.date:
            dt = datetime.fromtimestamp(obj.date, tz=timezone.utc)
            return dt.strftime("%Y-%m-%d - %H:%M:%S (UTC)")
        return ""
    
    date_formatted.short_description = "Payment date:"
    

@admin.register(StarPaymentData)
class StarPaymentDataAdmin(admin.ModelAdmin):
    list_display = ['id', 'tg_id', 'date_formatted', 'amount', 'processed', 'payment_id']

    def date_formatted(self, obj):
        if obj.date:
            dt = datetime.fromtimestamp(obj.date, tz=timezone.utc)
            return dt.strftime("%Y-%m-%d - %H:%M:%S (UTC)")
        return ""
    
    date_formatted.short_description = "Payment date:"

    

