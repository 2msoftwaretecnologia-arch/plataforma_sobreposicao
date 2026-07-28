import re

from django.core.exceptions import ValidationError

# Formato oficial do número do CAR (Cadastro Ambiental Rural), conforme consta
# no Recibo Federal: UF (2 letras) + código IBGE do município (7 dígitos) +
# hash (32 caracteres hexadecimais), ex.: TO-1721000-61FBE1B58B0243E68F515CBD6C2A2CC5
CAR_NUMBER_REGEX = re.compile(r'^[A-Z]{2}-\d{7}-[0-9A-F]{32}$')


def validate_car_number(value: str) -> str:
    """Normaliza e valida o número do CAR. Levanta `ValidationError` se o
    campo estiver vazio ou não seguir o formato oficial. Retorna o número
    normalizado (maiúsculo, sem pontos) quando válido."""
    normalized = (value or '').strip().upper().replace('.', '')

    if not normalized:
        raise ValidationError('Por favor, informe o número do CAR.')

    if not CAR_NUMBER_REGEX.match(normalized):
        raise ValidationError(
            'Número do CAR inválido. Utilize o formato UF-0000000-XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX '
            '(sem pontos), exatamente como consta no Recibo Federal.'
        )

    return normalized
