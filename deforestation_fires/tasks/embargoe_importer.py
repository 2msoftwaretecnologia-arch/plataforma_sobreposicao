from deforestation_fires.models import Embargoes
from kernel.service.bulk_shapefile_importer import BulkShapefileImporter


class EmbargoesImporter(BulkShapefileImporter):
    model = Embargoes
    archive_field = "adm_embargos_ibama_a_zip_file"
    source = "Base Embargos IBAMA"

    def missing_archive_message(self):
        return "Nenhum arquivo de Embargoes foi configurado."

    def format_fields(self, row):
        return {
            "property_name": str(row.get("nome_imove")),
            "type_area": str(row.get("tipo_area")),
            "number_infraction_act": str(row.get("num_auto_i")),
            "nome_embargado": str(row.get("nome_embar")),
            "cpf_cnpj_embargado": str(row.get("cpf_cnpj_e")),
            "control_unity": str(row.get("unid_contr")),
            "process_number": str(row.get("num_proces")),
            "act_description": str(row.get("des_tad")),
            "infraction_description": str(row.get("des_infrac")),
            "embargoe_date": str(row.get("dat_embarg")),
            "priting_date": str(row.get("dat_impres")),
        }
