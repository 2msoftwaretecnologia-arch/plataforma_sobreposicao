import os
import shutil
from django.conf import settings


def limpar_uploads_dir(dir_path: str | None = None):
    """Esvazia a pasta de uploads, removendo todos os arquivos e subpastas.

    Args:
        dir_path (str | None): Caminho da pasta a esvaziar. Se None, usa BASE_DIR/uploads.
    """
    try:
        uploads_dir = dir_path or os.path.join(settings.BASE_DIR, 'uploads')
        if not os.path.isdir(uploads_dir):
            return

        for entry in os.listdir(uploads_dir):
            full_path = os.path.join(uploads_dir, entry)
            try:
                if os.path.isdir(full_path):
                    shutil.rmtree(full_path)
                else:
                    os.remove(full_path)
            except Exception:
                # Silencia erros individuais para garantir que o restante seja limpo
                pass
    except Exception:
        # Evita que qualquer falha de limpeza quebre o fluxo da aplicação
        pass