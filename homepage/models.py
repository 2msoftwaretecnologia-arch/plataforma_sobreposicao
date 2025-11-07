from django.db import models

# Create your models here.
class Base_Sicar(models.Model):
    numero_Car = models.CharField(max_length=43, unique=True)
    status = models.CharField(max_length=50)
    coordinates = models.TextField()

    def __str__(self):
        return self.numero_Car

class Base_Zoneamento(models.Model):
    NomeZona = models.CharField(max_length=100)
    SiglaZona = models.CharField(max_length=50)
    coordinates = models.TextField()

    def __str__(self):
        return self.NomeZona

class Base_Fitoecologias(models.Model):
    NomeFito = models.CharField(max_length=70)
    coordinates = models.TextField()

    def __str__(self):
        return self.NomeFito


class Base_APAs(models.Model):
    Unidade = models.CharField(max_length=100)
    Dominios = models.CharField(max_length=100)
    Classes = models.CharField(max_length=100)
    FundLegal = models.CharField(max_length=100)
    coordinates = models.TextField()

    def __str__(self):
        return self.Unidade
