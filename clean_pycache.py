#!/usr/bin/env python3
"""
Script para limpar diretórios __pycache__ do projeto.
Este script remove todos os diretórios __pycache__ e arquivos .pyc encontrados.
"""

import os
import shutil
import sys
from pathlib import Path

RESET = "\033[0m"
BOLD = "\033[1m"
RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
GRAY = "\033[90m"
BLUE = "\033[94m"
MAGENTA = "\033[95m"
ENTRY_COLORS = [RED, GREEN, YELLOW, BLUE, MAGENTA, CYAN]

def clean_pycache(directory="."):
    """
    Remove todos os diretórios __pycache__ e arquivos .pyc do diretório especificado.
    
    Args:
        directory (str): Diretório para limpar (padrão: diretório atual)
    """
    directory = Path(directory).resolve()
    removed_count = 0
    
    print(f"{CYAN}{BOLD}Limpando cache Python em: {directory}{RESET}")
    print(f"{GRAY}{'-' * 50}{RESET}")
    
    # Procurar por diretórios __pycache__
    for i, pycache_dir in enumerate(directory.rglob("__pycache__")):
        try:
            color = ENTRY_COLORS[i % len(ENTRY_COLORS)]
            print(f"{color}Removendo: {pycache_dir}{RESET}")
            shutil.rmtree(pycache_dir)
            removed_count += 1
        except Exception as e:
            print(f"{RED}Erro ao remover {pycache_dir}: {e}{RESET}")
    
    # Procurar por arquivos .pyc individuais
    for pyc_file in directory.rglob("*.pyc"):
        try:
            print(f"{YELLOW}Removendo: {pyc_file}{RESET}")
            pyc_file.unlink()
            removed_count += 1
        except Exception as e:
            print(f"{RED}Erro ao remover {pyc_file}: {e}{RESET}")
    
    # Procurar por arquivos .pyo (Python optimized)
    for pyo_file in directory.rglob("*.pyo"):
        try:
            print(f"{YELLOW}Removendo: {pyo_file}{RESET}")
            pyo_file.unlink()
            removed_count += 1
        except Exception as e:
            print(f"{RED}Erro ao remover {pyo_file}: {e}{RESET}")
    
    print(f"{GRAY}{'-' * 50}{RESET}")
    if removed_count > 0:
        print(f"{GREEN}✅ Limpeza concluída! {removed_count} item(s) removido(s).{RESET}")
    else:
        print(f"{GREEN}✅ Nenhum cache Python encontrado para remover.{RESET}")


def main():
    """Função principal do script."""
    # Verificar se foi passado um diretório como argumento
    if len(sys.argv) > 1:
        target_dir = sys.argv[1]
        if not os.path.exists(target_dir):
            print(f"{RED}❌ Erro: Diretório '{target_dir}' não encontrado.{RESET}")
            sys.exit(1)
    else:
        target_dir = "."
    
    try:
        clean_pycache(target_dir)
    except KeyboardInterrupt:
        print(f"\n{RED}❌ Operação cancelada pelo usuário.{RESET}")
        sys.exit(1)
    except Exception as e:
        print(f"{RED}❌ Erro inesperado: {e}{RESET}")
        sys.exit(1)


if __name__ == "__main__":
    main()
