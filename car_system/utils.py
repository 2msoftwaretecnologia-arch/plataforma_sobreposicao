from typing import List
from .models import SicarRecord

def get_sicar_record(**filters) -> List[SicarRecord]:
    try:
        return SicarRecord.objects.filter(**filters)
    except SicarRecord.DoesNotExist:
        return SicarRecord.objects.none()