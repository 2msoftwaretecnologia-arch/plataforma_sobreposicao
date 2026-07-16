from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User

from .models import UserProfile


class UserProfileInline(admin.StackedInline):
    model = UserProfile
    can_delete = False
    verbose_name_plural = 'Perfil'


class CustomUserAdmin(UserAdmin):
    inlines = (UserProfileInline,)
    list_display = UserAdmin.list_display + ('get_objetivo', 'get_profissao')

    def get_objetivo(self, obj):
        return getattr(obj, 'profile', None) and obj.profile.objetivo_exibicao()
    get_objetivo.short_description = 'Objetivo'

    def get_profissao(self, obj):
        return getattr(obj, 'profile', None) and obj.profile.profissao_exibicao()
    get_profissao.short_description = 'Profissão'


admin.site.unregister(User)
admin.site.register(User, CustomUserAdmin)
