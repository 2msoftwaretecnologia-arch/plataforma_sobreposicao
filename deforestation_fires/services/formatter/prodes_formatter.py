from kernel.service.abstract.base_formatter import BaseFormatter
from datetime import datetime

class ProdesFormatter(BaseFormatter):
    def _format_date(self, date_str):
        if not date_str:
            return None
        try:
            # Tenta remover a parte de hora se existir e formata
            # Aceita formatos comuns de banco como YYYY-MM-DD HH:MM:SS ou YYYY-MM-DD
            dt = None
            if ' ' in date_str:
                dt = datetime.strptime(date_str.split('.')[0], '%Y-%m-%d %H:%M:%S')
            else:
                dt = datetime.strptime(date_str, '%Y-%m-%d')
            return dt.strftime('%d/%m/%Y')
        except (ValueError, TypeError, IndexError):
            # Se falhar o parse, retorna a string original
            return date_str

    def format(self, model_obj, intersec):
        return {
            "area": intersec["intersection_area_ha"],
            "identification": model_obj.identification,
            "year": model_obj.year,
            "satelite": model_obj.satelite,
            "image_date": self._format_date(model_obj.image_date),
            "item_info": f"Prodes: {model_obj.identification} - {model_obj.year}",
            "polygon_wkt": intersec["intersection_geom"].wkt,
            "polygon_geojson": intersec["intersection_geom"].geojson,
        }
