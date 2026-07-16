from django.conf import settings
from django.db import models


class UserProfile(models.Model):
    OBJETIVO_ESTUDAR = 'estudar'
    OBJETIVO_ANALISAR_PROPRIEDADES = 'analisar_propriedades'
    OBJETIVO_AGILIZAR_DEMANDA = 'agilizar_demanda'
    OBJETIVO_OUTRO = 'outro'

    OBJETIVO_CHOICES = [
        (OBJETIVO_ESTUDAR, 'Estudar'),
        (OBJETIVO_ANALISAR_PROPRIEDADES, 'Analisar propriedades'),
        (OBJETIVO_AGILIZAR_DEMANDA, 'Agilizar demanda de trabalho'),
        (OBJETIVO_OUTRO, 'Outro'),
    ]

    PROFISSAO_ENGENHEIRO_AGRONOMO = 'engenheiro_agronomo'
    PROFISSAO_ENGENHEIRO_AMBIENTAL = 'engenheiro_ambiental'
    PROFISSAO_ENGENHEIRO_FLORESTAL = 'engenheiro_florestal'
    PROFISSAO_TOPOGRAFO = 'topografo'
    PROFISSAO_GEOLOGO = 'geologo'
    PROFISSAO_ADVOGADO = 'advogado'
    PROFISSAO_PRODUTOR_RURAL = 'produtor_rural'
    PROFISSAO_CONSULTOR_AMBIENTAL = 'consultor_ambiental'
    PROFISSAO_ESTUDANTE = 'estudante'
    PROFISSAO_OUTRO = 'outro'

    PROFISSAO_CHOICES = [
        (PROFISSAO_ENGENHEIRO_AGRONOMO, 'Engenheiro(a) Agrônomo(a)'),
        (PROFISSAO_ENGENHEIRO_AMBIENTAL, 'Engenheiro(a) Ambiental'),
        (PROFISSAO_ENGENHEIRO_FLORESTAL, 'Engenheiro(a) Florestal'),
        (PROFISSAO_TOPOGRAFO, 'Topógrafo(a)'),
        (PROFISSAO_GEOLOGO, 'Geólogo(a)'),
        (PROFISSAO_ADVOGADO, 'Advogado(a)'),
        (PROFISSAO_PRODUTOR_RURAL, 'Produtor(a) Rural'),
        (PROFISSAO_CONSULTOR_AMBIENTAL, 'Consultor(a) Ambiental'),
        (PROFISSAO_ESTUDANTE, 'Estudante'),
        (PROFISSAO_OUTRO, 'Outro'),
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='profile',
        verbose_name='Usuário',
    )
    objetivo = models.CharField(
        max_length=30,
        choices=OBJETIVO_CHOICES,
        blank=True,
        verbose_name='Objetivo na plataforma',
    )
    objetivo_outro = models.CharField(
        max_length=150,
        blank=True,
        verbose_name='Objetivo (outro)',
    )
    profissao = models.CharField(
        max_length=30,
        choices=PROFISSAO_CHOICES,
        blank=True,
        verbose_name='Profissão',
    )
    profissao_outro = models.CharField(
        max_length=150,
        blank=True,
        verbose_name='Profissão (outra)',
    )
    onboarding_completo = models.BooleanField(default=False, verbose_name='Onboarding concluído')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Criado em')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Atualizado em')

    class Meta:
        db_table = 'tb_usuario_perfil'
        verbose_name = 'Perfil de Usuário'
        verbose_name_plural = 'Perfis de Usuário'

    def __str__(self):
        return f'Perfil de {self.user.username}'

    def objetivo_exibicao(self):
        if self.objetivo == self.OBJETIVO_OUTRO and self.objetivo_outro:
            return self.objetivo_outro
        return self.get_objetivo_display() if self.objetivo else ''

    def profissao_exibicao(self):
        if self.profissao == self.PROFISSAO_OUTRO and self.profissao_outro:
            return self.profissao_outro
        return self.get_profissao_display() if self.profissao else ''
