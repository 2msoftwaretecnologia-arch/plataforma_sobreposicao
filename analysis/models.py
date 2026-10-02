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
        SIGEF = 'sigef', 'Parcela do SIGEF'

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


class CrossBatch(models.Model):
    """Lote de cruzamento: vários CARs (os encontrados na tela de Localizações)
    cruzados com todas as bases em segundo plano. Cada CAR é um
    `CrossBatchItem`; o progresso fica salvo para a página poder ser fechada e
    o lote retomado se o processo cair (ver `cross_batch_service`)."""

    class Status(models.TextChoices):
        PENDING = 'pending', 'Na fila'
        RUNNING = 'running', 'Processando'
        DONE = 'done', 'Concluído'
        ERROR = 'error', 'Erro'

    class Kind(models.TextChoices):
        CAR = 'car', 'CARs do SICAR'
        SIGEF = 'sigef', 'Parcelas do SIGEF'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='cross_batches',
    )
    # Do que o lote é feito: CARs (item.car_number = número do CAR) ou
    # parcelas do SIGEF (item.car_number = código da parcela).
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.CAR)
    title = models.CharField(max_length=255, blank=True, default='')
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    total = models.PositiveIntegerField(default=0)
    processed = models.PositiveIntegerField(default=0)
    error = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    # Atualizado a cada CAR processado; sem atualização por muito tempo com o
    # lote "processando" quer dizer que o processo caiu.
    heartbeat_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'tb_lote_cruzamento'
        verbose_name = "Lote de cruzamento"
        verbose_name_plural = "Lotes de cruzamento"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.title or 'Lote'} — {self.created_at:%d/%m/%Y %H:%M}"

    @property
    def percent(self) -> int:
        return int(self.processed * 100 / self.total) if self.total else 0


class CrossBatchItem(models.Model):
    """Um CAR (ou parcela do SIGEF) de um lote e o resumo do cruzamento dele
    com as bases. Para parcelas, `car_number` guarda o código da parcela."""

    class Status(models.TextChoices):
        PENDING = 'pending', 'Na fila'
        DONE = 'done', 'Concluído'
        ERROR = 'error', 'Erro'

    batch = models.ForeignKey(CrossBatch, on_delete=models.CASCADE, related_name='items')
    car_number = models.CharField(max_length=43)
    municipio = models.CharField(max_length=150, blank=True, default='')
    car_status = models.CharField(max_length=50, blank=True, default='')
    area_ha = models.FloatField(null=True, blank=True)
    # Localizações do arquivo que caíram neste CAR: [{i, n, lat, lon}].
    points = models.JSONField(default=list, blank=True)
    # Dados que só existem no SIGEF: {'name': nome da área, 'property_code': código do imóvel}.
    extra = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True)
    # Resumo do resultado do `SearchAll` (sem as geometrias, que chegam a
    # vários MB por CAR) — ver `cross_batch_service.summarize_result`.
    summary = models.JSONField(default=dict, blank=True)
    critical_count = models.PositiveIntegerField(default=0)
    warning_count = models.PositiveIntegerField(default=0)
    overlap_count = models.PositiveIntegerField(default=0)
    error = models.TextField(blank=True, default='')
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'tb_lote_cruzamento_car'
        verbose_name = "CAR do lote de cruzamento"
        verbose_name_plural = "CARs do lote de cruzamento"
        ordering = ['id']
        constraints = [
            models.UniqueConstraint(fields=['batch', 'car_number'], name='uniq_lote_cruzamento_car'),
        ]

    def __str__(self):
        return self.car_number
