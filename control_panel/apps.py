from django.apps import AppConfig


class ControlPanelConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'control_panel'
    verbose_name = 'Painel de Controle'

    def ready(self):
        import control_panel.signals
