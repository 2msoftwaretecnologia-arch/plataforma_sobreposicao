from django.conf import settings
from django.contrib.postgres.indexes import GinIndex
from django.db import models


class SearchHistory(models.Model):
    """Registro de cada busca de sobreposição executada por um usuário.

    Guarda o mesmo dict que hoje fica só em `request.session['last_analysis']`
    (ver `analysis/views.py`), para que o painel administrativo
    (`control_panel`) possa listar e reabrir o que os usuários pesquisaram.
    """

    class SearchType(models.TextChoices):
        CAR = 'car', 'Número do CAR'
        SHAPEFILE = 'shapefile', 'Upload de shapefile'
        COORDENADAS = 'coordenadas', 'Coordenadas'
        DEMONSTRATIVO = 'demonstrativo', 'PDF — Demonstrativo'
        RECIBO = 'recibo', 'PDF — Recibo'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='search_history',
    )
    search_type = models.CharField(max_length=20, choices=SearchType.choices, db_index=True)
    car_input = models.CharField(max_length=100, blank=True, default='')
    municipio = models.CharField(max_length=150, blank=True, default='')
    uf = models.CharField(max_length=2, blank=True, default='')
    area_ha = models.FloatField(null=True, blank=True)
    conflitos_count = models.PositiveIntegerField(default=0)
    sucesso = models.BooleanField(default=True)
    erro = models.TextField(blank=True, default='')
    result_data = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = 'tb_search_history'
        verbose_name = "Histórico de Busca"
        verbose_name_plural = "Histórico de Buscas"
        ordering = ['-created_at']
        indexes = [
            # `car_input`/`municipio` são filtrados com `icontains` (busca
            # livre no painel administrativo) — um índice btree comum não
            # acelera isso; GIN + pg_trgm sim, inclusive para o padrão
            # `%termo%` (não só prefixo).
            GinIndex(fields=['car_input'], name='idx_search_car_input_trgm', opclasses=['gin_trgm_ops']),
            GinIndex(fields=['municipio'], name='idx_search_municipio_trgm', opclasses=['gin_trgm_ops']),
        ]

    def __str__(self):
        alvo = self.car_input or self.municipio or 'busca'
        return f"{alvo} — {self.created_at:%d/%m/%Y %H:%M}"
