from django.urls import path
from apps.v1.accounts.views import (
    PhoneLoginView,
    VerifySMSCodeView,
    ResendSMSCodeView,
    CreateMyIDSessionView,
    VerifyMyIDDataView,
)

urlpatterns = [
    path('login/', PhoneLoginView.as_view(), name='phone-login'),
    path('verify/', VerifySMSCodeView.as_view(), name='verify-sms-code'),
    path('resend/', ResendSMSCodeView.as_view(), name='resend-sms-code'),
    path('myid/verify/', VerifyMyIDDataView.as_view(), name='verify-myid-data'),
]