from django.db import models
from abc import ABC, abstractmethod
class BaseFormatter(ABC):

    @abstractmethod
    def format(self, model_obj: models.Model, intersec_data):
        raise NotImplementedError
