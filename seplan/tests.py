from django.test import TestCase
from .models import Highways

class HighwaysModelTest(TestCase):
    def test_create_highways(self):
        """Test creating a Highways instance with required fields."""
        highway = Highways.objects.create(
            NOME_2011="Rodovia Teste",
            CLAS_2011="Pavimentada",
            geometry="LINESTRING(0 0, 1 1)"
        )
        self.assertEqual(highway.NOME_2011, "Rodovia Teste")
        self.assertEqual(highway.CLAS_2011, "Pavimentada")
        self.assertTrue(Highways.objects.exists())

    def test_table_name(self):
        """Test that the table name is correct."""
        self.assertEqual(Highways._meta.db_table, 'tb_highways')

    def test_str_representation(self):
        """Test the string representation of the model."""
        highway = Highways.objects.create(
            NOME_2011="Rodovia BR-101",
            CLAS_2011="Federal"
        )
        self.assertEqual(str(highway), "Rodovia BR-101")
