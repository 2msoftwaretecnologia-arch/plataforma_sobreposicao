# core/models.py
from django.db import models
from django.conf import settings
from django.contrib.gis.db import models as gis_models

class GeoBaseModel(models.Model):
    """Classe abstrata para modelos com dados geográficos."""
    geometry = models.TextField(
        verbose_name="Coordenadas Geográficas",
        db_column="coordenadas_geograficas"
    )
    
    geometry_new = gis_models.GeometryField(
        srid=4674,
        null=True,
        blank=True,
        spatial_index=True,
        db_column="geometria_tmp",
    )
    
    area_m2 = models.FloatField(
        verbose_name="Área (m²)",
        db_column="area_m2",
        null=True,
        blank=True
    )
    
    area_ha = models.FloatField(
        verbose_name="Área (ha)",
        db_column="area_ha",
        null=True,
        blank=True
    )
    
    source = models.CharField(
        max_length=100,
        verbose_name="Fonte de Dados",
        null=True, blank=True
    )
    created_at = models.DateTimeField(
        auto_now_add=True, 
        db_column='criado_em', 
        verbose_name='Criado em'
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        related_name='%(class)s_created', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        db_column='id_criado_por', 
        verbose_name='Criado por'
    )

    updated_at = models.DateTimeField(
        auto_now=True, 
        db_column='atualizado_em', 
        verbose_name='Atualizado em'
    )

    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        related_name='%(class)s_updated', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        db_column='id_atualizado_por', 
        verbose_name='Atualizado por'
    )

    class Meta:
        abstract = True
