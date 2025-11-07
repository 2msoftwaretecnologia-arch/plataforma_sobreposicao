#!/usr/bin/env python3
"""
Script para limpar diretórios __pycache__ do projeto.
Este script remove todos os diretórios __pycache__ e arquivos .pyc encontrados.
"""

import os
import shutil
import sys
from pathlib import Path


def clean_pycache(directory="."):
    """
    Remove todos os diretórios __pycache__ e arquivos .pyc do diretório especificado.
    
    Args:
        directory (str): Diretório para limpar (padrão: diretório atual)
    """
    directory = Path(directory).resolve()
    removed_count = 0
    
    print(f"Limpando cache Python em: {directory}")
    print("-" * 50)
    
    # Procurar por diretórios __pycache__
    for pycache_dir in directory.rglob("__pycache__"):
        try:
            print(f"Removendo: {pycache_dir}")
            shutil.rmtree(pycache_dir)
            removed_count += 1
        except Exception as e:
            print(f"Erro ao remover {pycache_dir}: {e}")
    
    # Procurar por arquivos .pyc individuais
    for pyc_file in directory.rglob("*.pyc"):
        try:
            print(f"Removendo: {pyc_file}")
            pyc_file.unlink()
            removed_count += 1
        except Exception as e:
            print(f"Erro ao remover {pyc_file}: {e}")
    
    # Procurar por arquivos .pyo (Python optimized)
    for pyo_file in directory.rglob("*.pyo"):
        try:
            print(f"Removendo: {pyo_file}")
            pyo_file.unlink()
            removed_count += 1
        except Exception as e:
            print(f"Erro ao remover {pyo_file}: {e}")
    
    print("-" * 50)
    if removed_count > 0:
        print(f"✅ Limpeza concluída! {removed_count} item(s) removido(s).")
    else:
        print("✅ Nenhum cache Python encontrado para remover.")


def main():
    """Função principal do script."""
    # Verificar se foi passado um diretório como argumento
    if len(sys.argv) > 1:
        target_dir = sys.argv[1]
        if not os.path.exists(target_dir):
            print(f"❌ Erro: Diretório '{target_dir}' não encontrado.")
            sys.exit(1)
    else:
        target_dir = "."
    
    try:
        clean_pycache(target_dir)
    except KeyboardInterrupt:
        print("\n❌ Operação cancelada pelo usuário.")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Erro inesperado: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()