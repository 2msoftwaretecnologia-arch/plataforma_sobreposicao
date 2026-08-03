from functools import wraps

from django.shortcuts import redirect
from django.urls import path, reverse

from . import views

app_name = 'control_panel'


def _staff_only(view):
    """Exige usuário staff. Diferente de `staff_member_required`, não manda um
    usuário autenticado-mas-sem-permissão de volta para o login: isso criaria
    um loop infinito, já que `CustomLoginView` (redirect_authenticated_user=True)
    devolveria esse mesmo usuário para `next` (o próprio painel)."""
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            login_url = f"{reverse('authentication:login')}?next={request.path}"
            return redirect(login_url)
        if not (request.user.is_active and request.user.is_staff):
            return redirect('landing_page')
        return view(request, *args, **kwargs)
    return wrapped


urlpatterns = [
    path('', _staff_only(views.dashboard_home_view), name='home'),
    path('armazenamento/', _staff_only(views.armazenamento_view), name='armazenamento'),
    path('armazenamento/atualizar/', _staff_only(views.armazenamento_refresh_view), name='armazenamento_refresh'),
    path('usuarios/', _staff_only(views.usuarios_view), name='usuarios'),
    path('buscas/', _staff_only(views.buscas_view), name='buscas'),
    path('buscas/<int:pk>/', _staff_only(views.busca_detalhe_view), name='busca_detalhe'),
    path('bases-de-dados/', _staff_only(views.bases_dados_view), name='bases_dados'),
    path('bases-de-dados/<str:modelo>/upload/', _staff_only(views.base_upload_view), name='base_upload'),
    path('bases-de-dados/<str:modelo>/processar/', _staff_only(views.base_processar_view), name='base_processar'),
    path('bases-de-dados/<str:modelo>/colunas/', _staff_only(views.base_toggle_fields_view), name='base_toggle_fields'),
    path('bases-de-dados/<str:modelo>/excluir/', _staff_only(views.base_excluir_view), name='base_excluir'),
]
