from kernel.service.abstract.base_formatter import BaseFormatter


class PathsFormatter(BaseFormatter):
    def format(self, model_obj, intersec):
        return {
            "area": intersec["intersection_area_ha"],
            "item_info": "Vereda",
            "hash_id": getattr(model_obj, "hash_id", None),
        }
