from django.contrib.admin.views.decorators import staff_member_required
from django.urls import path, reverse_lazy

from . import views

app_name = 'control_panel'


def _staff_only(view):
    return staff_member_required(view, login_url=reverse_lazy('authentication:login'))


urlpatterns = [
    path('', _staff_only(views.dashboard_home_view), name='home'),
    path('armazenamento/', _staff_only(views.armazenamento_view), name='armazenamento'),
    path('armazenamento/atualizar/', _staff_only(views.armazenamento_refresh_view), name='armazenamento_refresh'),
    path('usuarios/', _staff_only(views.usuarios_view), name='usuarios'),
]
