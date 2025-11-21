from pickle import TRUE
from django.db import models

class FileManagement(models.Model):
    phytoecology_zip_file = models.FileField(
        upload_to='documents/',
        verbose_name="Documentos Fitoecologia",
        help_text="Arquivo ZIP contendo dados da Área de Fitoecologia."
    )

    environmental_protection_zip_file = models.FileField(
        upload_to='documents/',
        verbose_name="Documentos Proteção Ambiental",
        help_text="Arquivo ZIP contendo dados da Área de Proteção Ambiental."
    )

    zoning_zip_file = models.FileField(
        upload_to='documents/',
        verbose_name="Documentos Zoneamento",
        help_text="Arquivo ZIP contendo dados da Área de Zoneamento."
    )

    sicar_zip_file = models.FileField(
        upload_to='documents/',
        verbose_name="Documentos SICAR",
        help_text="Arquivo ZIP contendo dados da Área SICAR."
    )

    indigenous_zip_file = models.FileField(
        upload_to='documents/',
        verbose_name="Documentos Terra Indígena",
        help_text="Arquivo ZIP contendo dados da Área de Terra Indígena.",
        null = True,
        blank = True
    )

    quilombolas_zip_file = models.FileField(
        upload_to='documents/',
        verbose_name="Documentos Quilombolas",
        help_text="Arquivo ZIP contendo dados da Área de Quilombolas.",
        null = True,
        blank = True
    )
    
    paths_zip_file = models.FileField(
        upload_to='documents/',
        verbose_name="Documentos Veredas",
        help_text="Arquivo ZIP contendo dados da Área de Veredas.",
        null = True,
        blank = True
    )

    conservation_units_zip_file = models.FileField(
        upload_to='documents/',
        verbose_name="Documentos Unidades de Conservação",
        help_text="Arquivo ZIP contendo dados da Área de Unidades de Conservação.",
        null = True,
        blank = True
    )
    
    municipal_boundaries_zip_file = models.FileField(
        upload_to='documents/',
        verbose_name="Documentos Municípios",
        help_text="Arquivo ZIP contendo dados da Área de Municípios.",
        null = True,
        blank = True
    )
    
    class Meta:
        db_table = 'tb_gerenciamento_arquivos'
        verbose_name = "Gerenciamento de Arquivos"
        verbose_name_plural = "Gerenciamento de Arquivos"

    def __str__(self):
        return f"Gerenciamento de Arquivos"
        
