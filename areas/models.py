from django.db import models


class ZoningArea(models.Model):
    zone_name = models.CharField(
        max_length=100,
        verbose_name="Nome da Zona",
        db_column='nome_zona'
    )
    zone_acronym = models.CharField(
        max_length=50,
        verbose_name="Sigla da Zona",
        db_column='sigla_zona'
    )
    geo_coordinates = models.TextField(
        verbose_name="Coordenadas Geográficas",
        db_column='coordenadas_geograficas'
    )
    
    class Meta:
        db_table = 'tb_area_zoneamento'
        verbose_name = "Área de Zoneamento"
        verbose_name_plural = "Áreas de Zoneamento"

    def __str__(self):
        return self.zone_name


class PhytoecologyArea(models.Model):
    phyto_name = models.CharField(
        max_length=70,
        verbose_name="Nome da Fitoecologia",
        db_column='nome_fitoecologia'    
    )
    
    geo_coordinates = models.TextField(
        verbose_name="Coordenadas Geográficas",
        db_column='coordenadas_geograficas'
    )
    
    class Meta:
        db_table = 'tb_area_fitoecologia'
        verbose_name = "Área de Fitoecologia"
        verbose_name_plural = "Áreas de Fitoecologia"

    def __str__(self):
        return self.phyto_name


class EnvironmentalProtectionArea(models.Model):
    unit_name = models.CharField(
        max_length=100,
        verbose_name="Nome da Unidade de Conservação",
        db_column='nome_unidade_conservacao'
    )
    domains = models.CharField(
        max_length=100,
        verbose_name="Domínios",
        db_column='dominios'
    )
    class_group = models.CharField(
        max_length=100,
        verbose_name="Grupo de Classe",
        db_column='grupo_classe'
    )
    
    legal_basis = models.CharField(
        max_length=100,
        verbose_name="Fundo Legal",
        db_column='fundo_legal'
    )
    
    geo_coordinates = models.TextField(
        verbose_name="Coordenadas Geográficas",
        db_column='coordenadas_geograficas'
    )

    class Meta:
        db_table = 'tb_area_apa'
        verbose_name = "Área de APA"
        verbose_name_plural = "Áreas de APAs"
        
    def __str__(self):
        return self.unit_name