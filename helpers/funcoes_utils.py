def retornar_status_inteiro(valor):
    if valor == 'AT':
        return "Ativo"
    elif valor == 'CA':
        return "CAR em conflito"
    elif valor == 'SU':
        return "Suspenso"
    else:
        return "em Manutenção"

def retornar_lei(objeto):
    if objeto is None:
        return "Sem Lei"
    else:
        return str(objeto)