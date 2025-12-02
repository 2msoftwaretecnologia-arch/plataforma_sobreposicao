from django.core.management.base import BaseCommand
from django.db import connection

class Command(BaseCommand):
    help = (
        "Reprocessa geometrias da tabela tb_area_zoneamento: "
        "0) Corrige o SRID da COLUNA para 4674 (se estiver 4326) "
        "1) Converte WKT para geometry com SRID=4674 "
        "2) Corrige SRID incorreto diretamente na geometria "
        "3) Recalcula áreas em m² e ha usando UTM Zona 22S (EPSG:31982)"
    )

    def handle(self, *args, **options):
        table_name = "tb_area_deforestation_mapbiomas"

        with connection.cursor() as cursor:

            self.stdout.write(self.style.WARNING(
                f"\n🚀 Iniciando reprocessamento das geometrias de {table_name}...\n"
            ))

            # 0) AJUSTAR SRID DA COLUNA DO BANCO (IMPORTANTÍSSIMO)
            self.stdout.write("0️⃣ Ajustando SRID da coluna (se estiver diferente)...")

            cursor.execute(f"""
                ALTER TABLE {table_name}
                ALTER COLUMN geometria_util
                TYPE geometry(MultiPolygon, 4674)
                USING ST_SetSRID(geometria_util, 4674);
            """)

            self.stdout.write(self.style.SUCCESS("✔ Coluna ajustada para SRID 4674."))

            # 1) Converter WKT para geometria_util com SRID=4674
            self.stdout.write("1️⃣ Convertendo WKT → geometria_util (SRID 4674)...")
            cursor.execute(f"""
                UPDATE {table_name}
                SET geometria_util = ST_GeomFromText(coordenadas_geograficas, 4674)
                WHERE coordenadas_geograficas IS NOT NULL
                AND geometria_util IS NULL;
            """)
            cursor.execute(f"SELECT COUNT(*) FROM {table_name} WHERE geometria_util IS NOT NULL;")
            converted = cursor.fetchone()[0]
            self.stdout.write(self.style.SUCCESS(f"✔ Geometrias convertidas: {converted}"))

            # 2) Corrigir SRID se estiver incorreto
            self.stdout.write("2️⃣ Corrigindo SRID incorreto (se houver)...")
            cursor.execute(f"""
                UPDATE {table_name}
                SET geometria_util = ST_SetSRID(geometria_util, 4674)
                WHERE ST_SRID(geometria_util) <> 4674;
            """)
            self.stdout.write(self.style.SUCCESS("✔ SRIDs corrigidos."))

            # 3) Recalcular áreas fixas (m² e ha) em UTM zona 22S (EPSG 31982)
            self.stdout.write("3️⃣ Calculando áreas fixas (m² e ha) usando UTM 22S (EPSG:31982)...")
            cursor.execute(f"""
                UPDATE {table_name}
                SET 
                    area_m2 = ST_Area(ST_Transform(geometria_util, 31982)),
                    area_ha = ST_Area(ST_Transform(geometria_util, 31982)) / 10000
                WHERE geometria_util IS NOT NULL;
            """)
            self.stdout.write(self.style.SUCCESS("✔ Áreas calculadas e atualizadas!"))

        self.stdout.write(self.style.SUCCESS(
            "\n🎉 Reprocessamento concluído com sucesso!\n"
        ))
